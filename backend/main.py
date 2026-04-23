"""
Moretta — Main FastAPI application.
Provides all API endpoints for file upload, PII detection, anonymization,
AI processing, and result retrieval.
"""

from __future__ import annotations

import asyncio
import re as _re
import tempfile
import time
import logging
import os
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
import io

from config import get_settings
from anonymizer.detector import PiiDetector
from anonymizer.guard import SecurityGuard
from anonymizer.replacer import PiiReplacer
from anonymizer.vault import Vault
from reinjektor.reinjektor import Reinjektor
from parsers.docx_parser import parse_docx
from parsers.xlsx_parser import parse_xlsx
from parsers.email_parser import parse_email
from parsers.pdf_parser import parse_pdf
from rebuilders import rebuild_xlsx, rebuild_docx, rebuild_pdf
from providers.base import get_provider
from providers.models_registry import get_default_model
from audit.audit_log import AuditLogger
from auth import AuthConfig, AuthError, OIDCValidator
from store import PersistentStore

# ── Setup ──────────────────────────────────────────────────────────

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("moretta")
access_logger = logging.getLogger("moretta.access")

app = FastAPI(
    title="Moretta",
    description="Self-hosted AI proxy with PII anonymization",
    version="0.8",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── State stores (persistent — survive restarts) ───────────────────

file_store = PersistentStore(
    "files",
    database_backend=settings.database_backend,
    database_url=settings.database_url,
    sqlite_path=settings.store_db_path,
    encryption_key=settings.vault_encryption_key,
)
task_store = PersistentStore(
    "tasks",
    database_backend=settings.database_backend,
    database_url=settings.database_url,
    sqlite_path=settings.store_db_path,
)

vault = Vault(
    database_backend=settings.database_backend,
    database_url=settings.database_url,
    sqlite_path=settings.vault_path,
    encryption_key=settings.vault_encryption_key,
)
audit = AuditLogger(settings.audit_log_path)
detector = PiiDetector(settings.ollama_url, settings.local_model)
guard = SecurityGuard(settings.ollama_url, settings.local_model)
replacer = PiiReplacer()
reinjektor = Reinjektor()

# ── TTL cleanup ───────────────────────────────────────────────────

SESSION_TTL_SECONDS = 3600  # 1 hour

async def _cleanup_expired_sessions():
    """Periodically remove sessions older than SESSION_TTL_SECONDS."""
    while True:
        await asyncio.sleep(600)  # Check every 10 minutes
        expired_files = file_store.cleanup_older_than(SESSION_TTL_SECONDS, "uploaded_at")
        expired_task_contexts = _expired_task_context_ids(SESSION_TTL_SECONDS)
        for tid in expired_task_contexts:
            vault.delete_session(tid)
            if tid in task_store:
                task_store[tid]["context_expired"] = True
                task_store.persist(tid)
        if expired_files or expired_task_contexts:
            logger.info(
                f"TTL cleanup: removed {len(expired_files)} files and expired {len(expired_task_contexts)} task contexts"
            )

auth_validator = OIDCValidator(
    AuthConfig(
        issuer_url=settings.sso_issuer_url,
        allowed_client_ids=[
            client_id.strip()
            for client_id in settings.sso_allowed_client_ids.split(",")
            if client_id.strip()
        ],
    )
)


# ── Helpers ────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".docx", ".xlsx", ".pdf", ".eml", ".msg"}


def _parse_file(path: Path, ext: str) -> dict[str, Any]:
    """Route file to the correct parser and return dict with text and structured preview."""
    if ext == ".docx":
        return parse_docx(path)
    elif ext == ".xlsx":
        return parse_xlsx(path)
    elif ext == ".pdf":
        return parse_pdf(path)
    elif ext in (".eml", ".msg"):
        return parse_email(path)
    raise ValueError(f"Unsupported file extension: {ext}")


def _get_user(request: Request) -> str:
    """Extract username from JWT token on the request, or return 'anonymous'."""
    try:
        payload = getattr(request.state, "user", None)
        if payload and isinstance(payload, dict):
            return payload.get("preferred_username") or payload.get("sub", "unknown")
    except Exception:
        pass
    return "anonymous"


def _get_user_identity(request: Request) -> dict[str, str]:
    """Extract stable user identity fields used for per-user record ownership."""
    try:
        payload = getattr(request.state, "user", None)
        if payload and isinstance(payload, dict):
            user_id = str(payload.get("sub") or payload.get("preferred_username") or "anonymous")
            username = str(payload.get("preferred_username") or payload.get("sub") or "anonymous")
            return {"user_id": user_id, "username": username}
    except Exception:
        pass
    return {"user_id": "anonymous", "username": "anonymous"}


def _record_belongs_to_user(record: dict[str, Any], user_identity: dict[str, str]) -> bool:
    """Check whether a stored record belongs to the authenticated user."""
    record_user_id = str(record.get("user_id") or "").strip()
    record_username = str(record.get("username") or record.get("user") or "").strip()

    if record_user_id:
        return record_user_id == user_identity["user_id"]
    if record_username:
        return record_username == user_identity["username"]
    return user_identity["user_id"] == "anonymous"


def _require_owned_file(request: Request, file_id: str) -> dict[str, Any]:
    info = file_store.get(file_id)
    if not info:
        raise HTTPException(status_code=404, detail="File not found")
    if not _record_belongs_to_user(info, _get_user_identity(request)):
        raise HTTPException(status_code=403, detail="Forbidden")
    return info


def _require_owned_task(request: Request, task_id: str) -> dict[str, Any]:
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not _record_belongs_to_user(task, _get_user_identity(request)):
        raise HTTPException(status_code=403, detail="Forbidden")
    return task


def _resolve_model(provider_name: str, model_id: str | None) -> str:
    """Return requested model or the provider default when omitted."""
    requested = (model_id or "").strip()
    return requested or get_default_model(provider_name)


def _new_message(
    role: str,
    content: str,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Build a chat turn with metadata so mixed-model conversations stay auditable."""
    message = {
        "role": role,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if provider:
        message["provider"] = provider
    if model:
        message["model"] = model
    return message


def _conversation_title(filename: str, instruction: str) -> str:
    """Generate a short title for the conversation list."""
    cleaned_instruction = " ".join(instruction.strip().split())
    if filename and filename != "text_message.txt":
        return filename
    if cleaned_instruction:
        return cleaned_instruction[:72]
    return filename or "Untitled conversation"


def _conversation_summary(task_id: str, task: dict[str, Any]) -> dict[str, Any]:
    """Map a task record into conversation list metadata."""
    messages = task.get("messages", [])
    latest_message = messages[-1] if messages else {}
    last_activity_at = task.get("last_activity_at") or task.get("created_at") or ""
    latest_model = task.get("model") or ""
    latest_provider = task.get("provider") or ""

    return {
        "conversation_id": task_id,
        "task_id": task_id,
        "title": task.get("title") or _conversation_title(task.get("filename", ""), ""),
        "filename": task.get("filename", ""),
        "provider": latest_provider,
        "model": latest_model,
        "status": task.get("status", "unknown"),
        "pii_masked": task.get("pii_masked", 0),
        "created_at": task.get("created_at", ""),
        "last_activity_at": last_activity_at,
        "message_count": len(messages),
        "last_message_preview": str(latest_message.get("content", ""))[:160],
        "context_expired": bool(task.get("context_expired")),
    }


def _get_client_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For from reverse proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _sanitize_filename(filename: str) -> str:
    """
    Strip potentially sensitive data from filenames before logging.
    Keeps only the extension so audit trail knows the file type,
    but doesn't leak names like 'Jan_Kowalski_umowa.docx'.
    """
    ext = Path(filename).suffix.lower()
    return f"***{ext}" if ext else "***"


def _sanitize_error(error: str, max_length: int = 200) -> str:
    """
    Sanitize error messages before logging to prevent PII leakage.
    Strips common PII patterns and truncates to max_length.
    """
    sanitized = error[:max_length]
    # Strip common PII patterns that might appear in exception messages
    sanitized = _re.sub(r'\b\d{11}\b', '[PESEL]', sanitized)           # PESEL
    sanitized = _re.sub(r'\b\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b', '[PHONE]', sanitized)  # phone
    sanitized = _re.sub(r'[\w.+-]+@[\w-]+\.[\w.]+', '[EMAIL]', sanitized)  # email
    sanitized = _re.sub(r'\b[A-Z]{2}\d{2}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}\b', '[IBAN]', sanitized)  # IBAN
    if len(error) > max_length:
        sanitized += "...[truncated]"
    return sanitized


def _expired_task_context_ids(seconds: int) -> list[str]:
    """Return task ids whose sensitive processing context should expire."""
    now = datetime.now(timezone.utc)
    expired: list[str] = []
    for task_id, task in task_store.items():
        if task.get("context_expired"):
            continue
        ts = task.get("last_activity_at") or task.get("created_at")
        if not ts:
            continue
        try:
            age = (now - datetime.fromisoformat(ts)).total_seconds()
        except (ValueError, TypeError):
            continue
        if age > seconds:
            expired.append(task_id)
    return expired


# ── Startup / Shutdown ─────────────────────────────────────────────

@app.on_event("startup")
async def startup_event() -> None:
    """Ensure required directories exist."""
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    file_store.initialize()
    task_store.initialize()
    vault.initialize()
    asyncio.create_task(_cleanup_expired_sessions())
    logger.info(f"Moretta backend v0.8 started ({len(file_store)} files, {len(task_store)} tasks restored)")


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    """Log every HTTP request with user, IP, method, path, status, and duration."""
    start_time = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000)

    if request.url.path.startswith("/api/"):
        user = _get_user(request)
        client_ip = _get_client_ip(request)
        access_logger.info(
            f"{request.method} {request.url.path} "
            f"→ {response.status_code} "
            f"({duration_ms}ms) "
            f"user={user} ip={client_ip}"
        )

    return response


@app.middleware("http")
async def require_sso_token(request: Request, call_next):
    """Require valid bearer token for all API endpoints when SSO is enabled."""
    if request.method == "OPTIONS":
        return await call_next(request)

    if settings.sso_enabled and request.url.path.startswith("/api/"):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            audit.log(
                event="auth_failed",
                reason="missing_bearer_token",
                path=request.url.path,
                ip=_get_client_ip(request),
            )
            return JSONResponse(status_code=401, content={"detail": "Missing bearer token"})

        token = auth_header.removeprefix("Bearer ").strip()
        try:
            request.state.user = auth_validator.validate(token)
        except AuthError as exc:
            logger.warning(f"Auth failed for {request.url.path}: {exc}")
            audit.log(
                event="auth_failed",
                reason=str(exc),
                path=request.url.path,
                ip=_get_client_ip(request),
            )
            return JSONResponse(status_code=401, content={"detail": str(exc)})

    return await call_next(request)


# ── Endpoints ──────────────────────────────────────────────────────

async def _run_deep_scan(file_id: str, text: str, existing_pii: list[dict[str, Any]]):
    """Background task to run Ollama Deep Scan and update the file store."""
    try:
        new_pii = await detector.detect_deep_async(text, existing_pii)
        if file_id in file_store:
            file_store[file_id]["deep_scan_completed"] = True
            if new_pii:
                file_store[file_id]["pii"].extend(new_pii)
                logger.info(f"Deep scan finished for {file_id}, added {len(new_pii)} new PII elements.")
            file_store.persist(file_id)
    except Exception as exc:
        logger.error(f"Deep scan background task failed: {exc}")


@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks()) -> dict:
    """Upload a file for processing. Returns file_id."""
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    file_id = str(uuid.uuid4())
    contents = await file.read()
    save_path = settings.upload_dir / f"{file_id}{ext}"
    save_path.write_bytes(contents)

    # Parse file text and structure
    try:
        parsed = _parse_file(save_path, ext)
        text = parsed["text"]
        preview_data = parsed["preview_data"]
    except Exception as exc:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {exc}")
    finally:
        # Remove plaintext copy from disk right after parse.
        save_path.unlink(missing_ok=True)

    # Detect PII (Stage 1: Presidio, Stage 2: Ollama)
    pii_results = await detector.detect(text)

    user_identity = _get_user_identity(request)
    file_store[file_id] = {
        "path": None,
        "filename": filename,
        "ext": ext,
        "text": text,
        "preview_data": preview_data,
        "original_bytes": contents,
        "pii": pii_results,
        "deep_scan_completed": False,
        "size_bytes": len(contents),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_identity["user_id"],
        "username": user_identity["username"],
    }

    user = user_identity["username"]
    audit.log(
        event="file_uploaded",
        user=user,
        session_id=file_id,
        filename=_sanitize_filename(filename),
        size_bytes=len(contents),
        pii_count=len(pii_results),
        pii_types=list({p["type"] for p in pii_results}),
    )

    # Launch Async Deep Scan
    background_tasks.add_task(_run_deep_scan, file_id, text, pii_results)

    return {
        "file_id": file_id,
        "filename": filename,
        "size_bytes": len(contents),
        "pii_count": len(pii_results),
    }


class TextInputRequest(BaseModel):
    text: str


@app.post("/api/text")
async def process_text(http_request: Request, request: TextInputRequest, background_tasks: BackgroundTasks) -> dict:
    """Accept raw text for processing and PII detection."""
    text = request.text
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    file_id = str(uuid.uuid4())
    filename = "text_message.txt"
    ext = ".txt"

    # Detect PII
    pii_results = await detector.detect(text)
    preview_data = {"type": "document", "text": text}

    # Keep text in memory only (do not persist plaintext to uploads).
    file_bytes = text.encode("utf-8")

    user_identity = _get_user_identity(http_request)
    file_store[file_id] = {
        "path": None,
        "filename": filename,
        "ext": ext,
        "text": text,
        "preview_data": preview_data,
        "original_bytes": file_bytes,
        "pii": pii_results,
        "deep_scan_completed": False,
        "size_bytes": len(file_bytes),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_identity["user_id"],
        "username": user_identity["username"],
    }

    user = user_identity["username"]
    audit.log(
        event="text_submitted",
        user=user,
        session_id=file_id,
        filename=_sanitize_filename(filename),
        size_bytes=len(file_bytes),
        pii_count=len(pii_results),
        pii_types=list({p["type"] for p in pii_results}),
    )

    # Launch Async Deep Scan
    background_tasks.add_task(_run_deep_scan, file_id, text, pii_results)

    return {
        "file_id": file_id,
        "filename": filename,
        "size_bytes": len(file_bytes),
        "pii_count": len(pii_results),
    }


@app.get("/api/file/{file_id}/pii")
async def get_pii(request: Request, file_id: str) -> dict:
    """Return list of detected PII with types and counts."""
    info = _require_owned_file(request, file_id)

    audit.log(
        event="pii_viewed",
        user=_get_user(request),
        session_id=file_id,
        filename=_sanitize_filename(info["filename"]),
    )

    pii_list = info["pii"]

    # Group by type with counts and specific matches
    type_info: dict[str, dict] = {}
    for item in pii_list:
        t = item["type"]
        matched_text = item.get("text", "")
        if t not in type_info:
            type_info[t] = {"count": 0, "matches": set()}
        
        type_info[t]["count"] += 1
        if matched_text:
            type_info[t]["matches"].add(matched_text)

    # Map to display categories
    type_details = []
    for pii_type, info_dict in type_info.items():
        severity = _get_severity(pii_type)
        type_details.append({
            "type": pii_type,
            "label": _get_label(pii_type),
            "count": info_dict["count"],
            "severity": severity,
            "matches": sorted(list(info_dict["matches"])),
        })

    return {
        "file_id": file_id,
        "filename": info["filename"],
        "total_pii": len(pii_list),
        "deep_scan_completed": info.get("deep_scan_completed", True),
        "types": sorted(type_details, key=lambda x: {"critical": 0, "warning": 1, "info": 2}[x["severity"]]),
    }


@app.get("/api/file/{file_id}/preview")
async def get_preview(request: Request, file_id: str) -> dict:
    """Return anonymized preview of the file text/structure."""
    info = _require_owned_file(request, file_id)

    audit.log(
        event="preview_viewed",
        user=_get_user(request),
        session_id=file_id,
        filename=_sanitize_filename(info["filename"]),
    )

    # Generate token map from full text first to ensure consistency
    anonymized_text, token_map = replacer.anonymize(info["text"], info["pii"])

    # Anonymize structured preview data
    preview_data = info.get("preview_data", {})
    if preview_data.get("type") == "spreadsheet":
        # Process each sheet and row
        new_sheets = []
        for sheet in preview_data.get("sheets", []):
            new_rows = []
            for row in sheet.get("rows", []):
                new_row = []
                for cell in row:
                    cell_str = str(cell)
                    # Simple replacement using the token map
                    # (Note: this is a heuristic, but works since tokens are unique)
                    masked_cell = cell_str
                    for token, original in token_map.items():
                        if original in masked_cell:
                            masked_cell = masked_cell.replace(original, token)
                    new_row.append(masked_cell)
                new_rows.append(new_row)
            new_sheets.append({"name": sheet["name"], "rows": new_rows})
        preview_data = {"type": "spreadsheet", "sheets": new_sheets}
    else:
        # For document/email, just use anonymized_text
        preview_data = {
            "type": preview_data.get("type", "document"),
            "text": anonymized_text
        }

    return {
        "file_id": file_id,
        "original_length": len(info["text"]),
        "anonymized_text": anonymized_text,
        "preview_data": preview_data,
        "tokens_used": len(token_map),
    }


@app.post("/api/task")
async def create_task(
    request: Request,
    body: dict,
    background_tasks: BackgroundTasks,
) -> dict:
    """Create an AI processing task. Body: {file_id, instruction, provider?, model?}."""
    file_id = body.get("file_id")
    instruction = body.get("instruction", "")
    provider_name = body.get("provider", settings.default_provider)
    model_id = body.get("model")  # optional specific model
    resolved_model = _resolve_model(provider_name, model_id)

    if not file_id:
        raise HTTPException(status_code=404, detail="File not found")

    if not instruction.strip():
        raise HTTPException(status_code=400, detail="Instruction is required")

    # SECURITY GUARD (Prompt DLP) Check
    is_safe = await guard.check_instruction(instruction)
    if not is_safe:
        audit.log(
            event="security_incident",
            user=_get_user(request),
            details="Blocked by Security Guard (PII Leak in prompt)",
        )
        raise HTTPException(
            status_code=400,
            detail="Polityka Bezpieczeństwa (Security Guard): Instrukcja zawiera chronione dane wrażliwe (PII). Usuń je z okna czatu i polegaj tylko na maskowaniu treści dokumentu."
        )

    info = _require_owned_file(request, file_id)
    task_id = str(uuid.uuid4())

    # Anonymize text
    anonymized_text, token_map = replacer.anonymize(info["text"], info["pii"])

    # Detect & anonymize PII in user instruction
    inst_pii = await detector.detect(instruction)
    if inst_pii:
        _, inst_token_map = replacer.anonymize(instruction, inst_pii)
        token_map.update(inst_token_map)

    # Store mapping in vault
    vault.store_session(task_id, token_map)

    user_identity = _get_user_identity(request)
    now = datetime.now(timezone.utc).isoformat()
    task_store[task_id] = {
        "file_id": file_id,
        "filename": info["filename"],
        "provider": provider_name,
        "model": resolved_model,
        "title": _conversation_title(info["filename"], instruction),
        "anonymized_text": anonymized_text,
        "messages": [
            _new_message("user", instruction, provider=provider_name, model=resolved_model)
        ],
        "status": "processing",
        "created_at": now,
        "last_activity_at": now,
        "pii_masked": len(token_map),
        "error": None,
        "context_expired": False,
        "user_id": user_identity["user_id"],
        "username": user_identity["username"],
    }

    user = user_identity["username"]
    audit.log(
        event="task_created",
        user=user,
        session_id=task_id,
        filename=_sanitize_filename(info["filename"]),
        provider=provider_name,
        model=resolved_model,
        pii_count=len(token_map),
        pii_types=list({p["type"] for p in info["pii"]}),
        data_left_boundary=False,
    )

    # Process in background
    background_tasks.add_task(
        _process_task, task_id, provider_name, token_map, resolved_model
    )

    return {"task_id": task_id, "conversation_id": task_id, "status": "processing"}

class ChatRequest(BaseModel):
    instruction: str
    provider: str | None = None
    model: str | None = None

@app.post("/api/task/{task_id}/chat")
async def chat_task(
    http_request: Request,
    task_id: str,
    request: ChatRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Add a follow-up message to an existing task and process it."""
    task = _require_owned_task(http_request, task_id)

    if task["status"] == "processing":
        raise HTTPException(status_code=400, detail="Task is currently processing")

    if task.get("context_expired"):
        raise HTTPException(
            status_code=410,
            detail="This conversation context expired after inactivity. Open it for history, but start a new conversation to continue processing securely.",
        )

    instruction = request.instruction
    if not instruction.strip():
        raise HTTPException(status_code=400, detail="Instruction is required")

    # SECURITY GUARD (Prompt DLP) Check
    is_safe = await guard.check_instruction(instruction)
    if not is_safe:
        audit.log(
            event="chat_blocked",
            user=_get_user(http_request),
            session_id=task_id,
            details="Blocked by Security Guard (PII in chat)",
        )
        raise HTTPException(
            status_code=400,
            detail="Polityka Bezpieczeństwa (Security Guard): Instrukcja zawiera chronione dane wrażliwe (PII). Usuń je z okna czatu."
        )

    provider_name = request.provider or task.get("provider") or settings.default_provider
    resolved_model = _resolve_model(provider_name, request.model or task.get("model"))

    user = _get_user(http_request)
    task["messages"].append(_new_message("user", instruction, provider=provider_name, model=resolved_model))
    task["status"] = "processing"
    task["error"] = None
    task["context_expired"] = False
    task["provider"] = provider_name
    task["model"] = resolved_model
    task["last_activity_at"] = datetime.now(timezone.utc).isoformat()
    task_store.persist(task_id)

    audit.log(
        event="chat_followup",
        user=user,
        session_id=task_id,
        filename=_sanitize_filename(task["filename"]),
        provider=provider_name,
        model=resolved_model,
        message_count=len(task["messages"]),
    )

    # We need the token_map from the vault
    token_map = vault.get_session(task_id)

    # Detect any NEW PII the user just typed and add to the token map
    new_pii_results = await detector.detect(instruction)
    if new_pii_results:
        _, new_token_map = replacer.anonymize(instruction, new_pii_results)
        token_map.update(new_token_map)
        vault.store_session(task_id, token_map)

    # Process in background
    background_tasks.add_task(
        _process_task, task_id, provider_name, token_map, resolved_model
    )

    return {"task_id": task_id, "conversation_id": task_id, "status": "processing"}


@app.get("/api/task/{task_id}/status")
async def get_task_status(request: Request, task_id: str) -> dict:
    """Poll task status."""
    task = _require_owned_task(request, task_id)

    return {
        "task_id": task_id,
        "status": task["status"],
        "filename": task["filename"],
        "provider": task["provider"],
        "model": task.get("model", ""),
        "pii_masked": task["pii_masked"],
        "created_at": task["created_at"],
        "last_activity_at": task.get("last_activity_at", task["created_at"]),
        "error": task.get("error"),
    }


@app.get("/api/task/{task_id}/result")
async def get_task_result(request: Request, task_id: str) -> dict:
    """Get the processed result with reinjected PII."""
    task = _require_owned_task(request, task_id)

    if task["status"] == "processing":
        raise HTTPException(status_code=202, detail="Task still processing")

    if task["status"] == "failed":
        raise HTTPException(status_code=500, detail=task.get("error", "Unknown error"))

    audit.log(
        event="result_viewed",
        user=_get_user(request),
        session_id=task_id,
        filename=_sanitize_filename(task["filename"]),
    )

    return {
        "task_id": task_id,
        "conversation_id": task_id,
        "status": task["status"],
        "filename": task["filename"],
        "title": task.get("title", task["filename"]),
        "provider": task.get("provider", ""),
        "model": task.get("model", ""),
        "messages": task["messages"],
        "has_solution": "solution_text" in task,
        "result_preview": task.get("result_preview"),
        "created_at": task.get("created_at", ""),
        "last_activity_at": task.get("last_activity_at", task.get("created_at", "")),
    }


@app.get("/api/task/{task_id}/download")
async def download_task_result(request: Request, task_id: str):
    """Download the processed file rebuilt in its original type."""
    task = _require_owned_task(request, task_id)

    audit.log(
        event="result_downloaded",
        user=_get_user(request),
        session_id=task_id,
        filename=_sanitize_filename(task["filename"]),
    )

    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Task not completed")

    filename = task["filename"]
    ext = Path(filename).suffix.lower()
    
    # Use pre-extracted solution text, or fall back to last assistant message
    text = task.get("solution_text", "")
    if not text:
        for msg in reversed(task["messages"]):
            if msg["role"] == "assistant":
                text = msg["content"].strip()
                break

    # Recreate template as temporary file only for rebuild, then delete.
    file_id = task["file_id"]
    info = file_store.get(file_id, {})
    template_bytes = info.get("original_bytes")

    try:
        template_path = None
        temp_file = None
        if ext in {".xlsx", ".docx"} and template_bytes:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            temp_file.write(template_bytes)
            temp_file.flush()
            temp_file.close()
            template_path = temp_file.name

        if ext == ".xlsx":
            content_bytes = rebuild_xlsx(text, template_path=template_path)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif ext == ".docx":
            content_bytes = rebuild_docx(text, template_path=template_path)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif ext == ".pdf":
            content_bytes = rebuild_pdf(text)
            media_type = "application/pdf"
        else:
            content_bytes = text.encode("utf-8")
            media_type = "text/plain"

        out_name = f"result_{filename}"
        stream = io.BytesIO(content_bytes)
        
        return StreamingResponse(
            stream,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{out_name}"'
            }
        )
    except Exception as exc:
        logger.exception(f"Task {task_id}: Failed to rebuild file")
        raise HTTPException(status_code=500, detail=f"Failed to rebuild file: {exc}")
    finally:
        if "temp_file" in locals() and temp_file:
            Path(temp_file.name).unlink(missing_ok=True)


@app.get("/api/audit")
async def get_audit_log(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Return audit log entries."""
    audit.log(
        event="audit_log_viewed",
        user=_get_user(request),
        limit=limit,
        offset=offset,
    )
    entries = audit.read(limit=limit, offset=offset)
    return {
        "entries": entries,
        "total": audit.count(),
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/providers")
async def get_providers() -> dict:
    """Return list of available AI providers with all model options."""
    from providers.models_registry import get_models_for_provider, get_default_model

    provider_configs = [
        {"id": "claude",      "name": "Anthropic (Claude)",      "key": settings.anthropic_api_key},
        {"id": "openai",      "name": "OpenAI (GPT)",            "key": settings.openai_api_key},
        {"id": "gemini",      "name": "Google (Gemini)",          "key": settings.google_ai_api_key},
        {"id": "openrouter",  "name": "OpenRouter (Multi-model)", "key": settings.openrouter_api_key},
        {"id": "ollama",      "name": "Ollama (Local)",           "key": "local"},
    ]

    providers = []
    for cfg in provider_configs:
        models = get_models_for_provider(cfg["id"])
        default_model = get_default_model(cfg["id"])
        providers.append({
            "id": cfg["id"],
            "name": cfg["name"],
            "configured": bool(cfg["key"]),
            "default_model": default_model,
            "models": models,
        })

    return {
        "providers": providers,
        "default_provider": settings.default_provider,
        "default_model": settings.default_ai_model,
    }


@app.get("/api/tasks")
async def list_tasks(request: Request) -> dict:
    """Return all tasks for history view."""
    user_identity = _get_user_identity(request)
    tasks = []
    for task_id, task in task_store.items():
        if not _record_belongs_to_user(task, user_identity):
            continue
        tasks.append({
            "task_id": task_id,
            "filename": task["filename"],
            "title": task.get("title", task["filename"]),
            "provider": task["provider"],
            "model": task.get("model", ""),
            "status": task["status"],
            "pii_masked": task["pii_masked"],
            "created_at": task["created_at"],
            "last_activity_at": task.get("last_activity_at", task["created_at"]),
        })

    tasks.sort(key=lambda t: t["last_activity_at"], reverse=True)
    return {"tasks": tasks}


@app.get("/api/conversations")
async def list_conversations(request: Request) -> dict:
    """Return the authenticated user's conversation list."""
    user_identity = _get_user_identity(request)
    conversations = []
    for task_id, task in task_store.items():
        if not _record_belongs_to_user(task, user_identity):
            continue
        conversations.append(_conversation_summary(task_id, task))

    conversations.sort(key=lambda item: item["last_activity_at"], reverse=True)
    return {"conversations": conversations}


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(request: Request, conversation_id: str) -> dict:
    """Return a full conversation payload for reopening an existing thread."""
    task = _require_owned_task(request, conversation_id)
    return {
        "conversation_id": conversation_id,
        "task_id": conversation_id,
        "title": task.get("title", task["filename"]),
        "filename": task["filename"],
        "file_id": task.get("file_id"),
        "provider": task.get("provider", ""),
        "model": task.get("model", ""),
        "status": task["status"],
        "messages": task.get("messages", []),
        "has_solution": "solution_text" in task,
        "result_preview": task.get("result_preview"),
        "created_at": task.get("created_at", ""),
        "last_activity_at": task.get("last_activity_at", task.get("created_at", "")),
        "pii_masked": task.get("pii_masked", 0),
        "context_expired": bool(task.get("context_expired")),
    }


@app.get("/api/dashboard")
async def get_dashboard() -> dict:
    """Aggregate audit data into dashboard statistics."""
    from collections import Counter, defaultdict

    entries = audit.read(limit=10000, offset=0)

    total_files = 0
    total_tasks = 0
    total_pii = 0
    pii_breakdown: Counter = Counter()
    provider_usage: Counter = Counter()
    daily_activity: defaultdict[str, int] = defaultdict(int)
    security_incidents = 0

    for entry in entries:
        event = entry.get("event", "")
        timestamp = entry.get("timestamp", "")
        day = timestamp[:10] if len(timestamp) >= 10 else "unknown"

        if event in ("file_uploaded", "text_submitted"):
            total_files += 1
            total_pii += entry.get("pii_count", 0)
            for pii_type in entry.get("pii_types", []):
                pii_breakdown[pii_type] += 1
            daily_activity[day] += 1

        elif event == "task_created":
            total_tasks += 1
            provider = entry.get("provider", "unknown")
            provider_usage[provider] += 1
            daily_activity[day] += 1

        elif event == "security_incident":
            security_incidents += 1

        elif event == "auth_failed":
            security_incidents += 1

    # Sort daily activity by date, last 30 entries
    sorted_days = sorted(daily_activity.items())[-30:]

    return {
        "stats": {
            "total_files": total_files,
            "total_tasks": total_tasks,
            "total_pii_detected": total_pii,
            "security_incidents": security_incidents,
            "active_sessions": len(file_store),
            "active_tasks": len(task_store),
        },
        "pii_breakdown": [
            {"type": t, "count": c}
            for t, c in pii_breakdown.most_common(15)
        ],
        "provider_usage": [
            {"provider": p, "count": c}
            for p, c in provider_usage.most_common()
        ],
        "daily_activity": [
            {"date": d, "count": c}
            for d, c in sorted_days
        ],
    }


async def _process_task(
    task_id: str,
    provider_name: str,
    token_map: dict[str, str],
    model_id: str | None = None,
) -> None:
    """Process a task in the background: send to AI, reinject PII."""
    try:
        resolved_model = _resolve_model(provider_name, model_id)
        # Get AI provider
        provider = get_provider(provider_name, get_settings(), model=resolved_model)
        if not provider:
            raise ValueError(f"Provider '{provider_name}' is not configured")

        # Send anonymized history to external AI
        anonymized_text = task_store[task_id]["anonymized_text"]
        messages = task_store[task_id]["messages"]

        # CRITICAL: Re-anonymize ALL messages before sending to AI.
        # User messages might contain PII that was manually typed.
        # Assistant messages were reinjected with real PII after the last response.
        # We must replace real PII back with tokens before sending the history.
        reverse_map = {v: k for k, v in token_map.items()}  # original_value → token
        # Sort keys by length descending to replace longest PII first (e.g., "Jan Kowalski" before "Jan")
        keys_sorted = sorted(reverse_map.keys(), key=len, reverse=True)

        safe_messages = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, str):
                for original_value in keys_sorted:
                    if original_value in content:
                        content = content.replace(original_value, reverse_map[original_value])
            safe_messages.append({"role": msg["role"], "content": content})

        ai_response = await provider.process(anonymized_text, safe_messages)

        audit.log(
            event="ai_response_received",
            session_id=task_id,
            provider=provider_name,
            data_left_boundary=False,
        )

        # Reinject original PII
        result_text, unresolved = reinjektor.reinject(ai_response, token_map)

        if unresolved:
            logger.warning(f"Task {task_id}: {len(unresolved)} unresolved tokens")

        audit.log(
            event="reinjection_complete",
            session_id=task_id,
            unresolved_tokens=len(unresolved),
            data_left_boundary=False,
        )

        # Extract solution from tags if present
        import re
        solution_match = re.search(r"<ROZWIAZANIE>(.*?)</ROZWIAZANIE>", result_text, re.DOTALL)
        if solution_match:
            solution_content = solution_match.group(1).strip()
            # Store clean solution for download and preview
            task_store[task_id]["solution_text"] = solution_content
            # Generate preview data from solution
            file_id = task_store[task_id]["file_id"]
            file_ext = file_store[file_id]["ext"] if file_id in file_store else ""
            if file_ext == ".xlsx":
                # Parse solution text into spreadsheet preview
                sheets = []
                current_sheet_name = "Arkusz1"
                current_sheet_data = {}  # dict of row -> dict of col -> val
                
                cell_pattern = re.compile(r"^([a-zA-Z]+)(\d+):\s*(.*)$")
                from openpyxl.utils import column_index_from_string
                
                for line in solution_content.splitlines():
                    line_s = line.strip()
                    if not line_s:
                        continue
                        
                    if line_s.startswith("[Arkusz:") and line_s.endswith("]"):
                        # Save previous sheet
                        if current_sheet_data:
                            # Convert dict to list of lists for UI preview
                            max_preview_row = min(50, max(current_sheet_data.keys()))
                            if max_preview_row > 0:
                                max_col_idx = max(max(cols.keys()) for cols in current_sheet_data.values() if cols)
                                preview_rows = []
                                for r in range(1, max_preview_row + 1):
                                    row_vals = []
                                    for c in range(1, max_col_idx + 1):
                                        row_vals.append(current_sheet_data.get(r, {}).get(c, ""))
                                    preview_rows.append(row_vals)
                                sheets.append({"name": current_sheet_name, "rows": preview_rows})
                        # Reset for next sheet
                        current_sheet_name = line_s[8:-1].strip()
                        current_sheet_data = {}
                        continue
                        
                    match = cell_pattern.match(line_s)
                    if match:
                        try:
                            col_letter = match.group(1).upper()
                            row_idx = int(match.group(2))
                            val = match.group(3)
                            
                            if row_idx not in current_sheet_data:
                                current_sheet_data[row_idx] = {}
                                
                            col_idx = column_index_from_string(col_letter)
                            current_sheet_data[row_idx][col_idx] = val
                        except Exception:
                            pass
                
                # Save last sheet
                if current_sheet_data:
                    max_preview_row = min(50, max(current_sheet_data.keys()))
                    if max_preview_row > 0:
                        max_col_idx = max(max(cols.keys()) for cols in current_sheet_data.values() if cols)
                        preview_rows = []
                        for r in range(1, max_preview_row + 1):
                            row_vals = []
                            for c in range(1, max_col_idx + 1):
                                row_vals.append(current_sheet_data.get(r, {}).get(c, ""))
                            preview_rows.append(row_vals)
                        sheets.append({"name": current_sheet_name, "rows": preview_rows})
                        
                task_store[task_id]["result_preview"] = {"type": "spreadsheet", "sheets": sheets}
            else:
                task_store[task_id]["result_preview"] = {"type": "document", "text": solution_content}

            # Clean message: remove tags, keep any text outside them
            clean_msg = re.sub(r"<ROZWIAZANIE>.*?</ROZWIAZANIE>", "", result_text, flags=re.DOTALL).strip()
            if not clean_msg:
                clean_msg = "Plik został przetworzony. Sprawdź podgląd poniżej i pobierz wynik."
            task_store[task_id]["messages"].append(
                _new_message("assistant", clean_msg, provider=provider_name, model=resolved_model)
            )
        else:
            # Normal chat message (no file result)
            task_store[task_id]["messages"].append(
                _new_message("assistant", result_text, provider=provider_name, model=resolved_model)
            )

        task_store[task_id]["status"] = "completed"
        task_store[task_id]["provider"] = provider_name
        task_store[task_id]["model"] = resolved_model
        task_store[task_id]["last_activity_at"] = datetime.now(timezone.utc).isoformat()
        task_store.persist(task_id)

        # Do not delete session or file yet, the user might want to continue chat
        # vault.delete_session(task_id)
        # file_id = task_store[task_id]["file_id"]
        # if file_id in file_store:
        #    upload_path = Path(file_store[file_id]["path"])
        #    upload_path.unlink(missing_ok=True)

    except Exception as exc:
        safe_error = _sanitize_error(str(exc))
        logger.error(f"Task {task_id} failed: {safe_error}")
        task_store[task_id]["status"] = "failed"
        task_store[task_id]["error"] = safe_error
        task_store[task_id]["last_activity_at"] = datetime.now(timezone.utc).isoformat()
        task_store.persist(task_id)

        audit.log(
            event="task_failed",
            session_id=task_id,
            error=safe_error,
            data_left_boundary=False,
        )


# ── PII Label & Severity Helpers ──────────────────────────────────

_LABEL_MAP = {
    "PERSON": "Full Name",
    "EMAIL_ADDRESS": "Email Address",
    "PHONE_NUMBER": "Phone Number",
    "IBAN_CODE": "IBAN Code",
    "NRP": "ID / VAT Number",
    "PESEL": "PESEL (ID)",
    "NIP": "VAT Number",
    "LOCATION": "Address",
    "DATE_TIME": "Date",
    "CREDIT_CARD": "Credit Card",
    "CRYPTO": "Crypto Address",
    "SECRET_PROJECT": "Secret Project",
    "FINANCE": "Financial Amount",
    "INTERNAL_ID": "Internal ID",
    "IT_INFRA": "IT Infrastructure",
    "SALARY": "Salary Amounts",
    "FINANCIAL": "Financial Data",
    "PROJECT_ID": "Project Code",
    "CLIENT_NAME": "Client Name",
    "CONTRACT_NUMBER": "Contract Number",
    "IP_ADDRESS": "IP Address",
}

_SEVERITY_MAP = {
    "SECRET_PROJECT": "critical",
    "FINANCE": "warning",
    "INTERNAL_ID": "warning",
    "IT_INFRA": "critical",
    "PERSON": "critical",
    "NRP": "critical",
    "PESEL": "critical",
    "NIP": "critical",
    "CREDIT_CARD": "critical",
    "IBAN_CODE": "critical",
    "EMAIL_ADDRESS": "warning",
    "PHONE_NUMBER": "warning",
    "SALARY": "warning",
    "FINANCIAL": "warning",
    "LOCATION": "info",
    "CLIENT_NAME": "warning",
    "CONTRACT_NUMBER": "warning",
}


def _get_label(pii_type: str) -> str:
    return _LABEL_MAP.get(pii_type, pii_type)


def _get_severity(pii_type: str) -> str:
    return _SEVERITY_MAP.get(pii_type, "info")
