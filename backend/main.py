"""
PrivateProxy — Main FastAPI application.
Provides all API endpoints for file upload, PII detection, anonymization,
AI processing, and result retrieval.
"""

from __future__ import annotations

import asyncio
import tempfile
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
from rebuilders import rebuild_xlsx, rebuild_docx
from providers.base import get_provider
from audit.audit_log import AuditLogger
from auth import AuthConfig, AuthError, OIDCValidator

# ── Setup ──────────────────────────────────────────────────────────

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("privateproxy")

app = FastAPI(
    title="PrivateProxy",
    description="Self-hosted AI proxy with PII anonymization",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── State stores ───────────────────────────────────────────────────

# In-memory stores (per-process; fine for single-instance deployment)
file_store: dict[str, dict[str, Any]] = {}   # file_id → {path, filename, text, pii, ...}
task_store: dict[str, dict[str, Any]] = {}   # task_id → {status, result_path, ...}

vault = Vault(settings.vault_path, settings.vault_encryption_key)
audit = AuditLogger(settings.audit_log_path)
detector = PiiDetector(settings.ollama_url, settings.local_model)
guard = SecurityGuard(settings.ollama_url, settings.local_model)
replacer = PiiReplacer()
reinjektor = Reinjektor()

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

SUPPORTED_EXTENSIONS = {".docx", ".xlsx", ".eml", ".msg"}


def _parse_file(path: Path, ext: str) -> dict[str, Any]:
    """Route file to the correct parser and return dict with text and structured preview."""
    if ext == ".docx":
        return parse_docx(path)
    elif ext == ".xlsx":
        return parse_xlsx(path)
    elif ext in (".eml", ".msg"):
        return parse_email(path)
    raise ValueError(f"Unsupported file extension: {ext}")


# ── Startup / Shutdown ─────────────────────────────────────────────

@app.on_event("startup")
async def startup_event() -> None:
    """Ensure required directories exist."""
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    vault.initialize()
    logger.info("PrivateProxy backend started")


@app.middleware("http")
async def require_sso_token(request: Request, call_next):
    """Require valid bearer token for all API endpoints when SSO is enabled."""
    if request.method == "OPTIONS":
        return await call_next(request)

    if settings.sso_enabled and request.url.path.startswith("/api/"):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            print(f"Auth failed: Missing bearer token for {request.url.path}")
            return JSONResponse(status_code=401, content={"detail": "Missing bearer token"})

        token = auth_header.removeprefix("Bearer ").strip()
        try:
            request.state.user = auth_validator.validate(token)
        except AuthError as exc:
            print(f"AuthError validating token: {exc}")
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
    except Exception as exc:
        logger.error(f"Deep scan background task failed: {exc}")


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks()) -> dict:
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
    }

    audit.log(
        event="file_uploaded",
        session_id=file_id,
        filename=filename,
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
async def process_text(request: TextInputRequest, background_tasks: BackgroundTasks) -> dict:
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
    }

    audit.log(
        event="text_submitted",
        session_id=file_id,
        filename=filename,
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
async def get_pii(file_id: str) -> dict:
    """Return list of detected PII with types and counts."""
    info = file_store.get(file_id)
    if not info:
        raise HTTPException(status_code=404, detail="File not found")

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
async def get_preview(file_id: str) -> dict:
    """Return anonymized preview of the file text/structure."""
    info = file_store.get(file_id)
    if not info:
        raise HTTPException(status_code=404, detail="File not found")

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
    body: dict,
    background_tasks: BackgroundTasks,
) -> dict:
    """Create an AI processing task. Body: {file_id, instruction, provider?, model?}."""
    file_id = body.get("file_id")
    instruction = body.get("instruction", "")
    provider_name = body.get("provider", settings.default_provider)
    model_id = body.get("model")  # optional specific model

    if not file_id or file_id not in file_store:
        raise HTTPException(status_code=404, detail="File not found")

    if not instruction.strip():
        raise HTTPException(status_code=400, detail="Instruction is required")

    # SECURITY GUARD (Prompt DLP) Check
    is_safe = await guard.check_instruction(instruction)
    if not is_safe:
        audit.log(
            event="security_incident",
            details="Blocked by Security Guard (PII Leak in prompt)",
        )
        raise HTTPException(
            status_code=400,
            detail="Polityka Bezpieczeństwa (Security Guard): Instrukcja zawiera chronione dane wrażliwe (PII). Usuń je z okna czatu i polegaj tylko na maskowaniu treści dokumentu."
        )

    info = file_store[file_id]
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

    task_store[task_id] = {
        "file_id": file_id,
        "filename": info["filename"],
        "provider": provider_name,
        "model": model_id or "",
        "anonymized_text": anonymized_text,
        "messages": [
            {"role": "user", "content": instruction}
        ],
        "status": "processing",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pii_masked": len(token_map),
        "error": None,
    }

    audit.log(
        event="task_created",
        session_id=task_id,
        filename=info["filename"],
        provider=provider_name,
        model=model_id or "default",
        pii_count=len(token_map),
        pii_types=list({p["type"] for p in info["pii"]}),
        data_left_boundary=False,
    )

    # Process in background
    background_tasks.add_task(
        _process_task, task_id, provider_name, token_map, model_id
    )

    return {"task_id": task_id, "status": "processing"}

class ChatRequest(BaseModel):
    instruction: str

@app.post("/api/task/{task_id}/chat")
async def chat_task(
    task_id: str,
    request: ChatRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Add a follow-up message to an existing task and process it."""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] == "processing":
        raise HTTPException(status_code=400, detail="Task is currently processing")

    instruction = request.instruction
    if not instruction.strip():
        raise HTTPException(status_code=400, detail="Instruction is required")

    # SECURITY GUARD (Prompt DLP) Check
    is_safe = await guard.check_instruction(instruction)
    if not is_safe:
        raise HTTPException(
            status_code=400,
            detail="Polityka Bezpieczeństwa (Security Guard): Instrukcja zawiera chronione dane wrażliwe (PII). Usuń je z okna czatu."
        )

    task["messages"].append({"role": "user", "content": instruction})
    task["status"] = "processing"
    task["error"] = None

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
        _process_task, task_id, task["provider"], token_map, task["model"]
    )

    return {"task_id": task_id, "status": "processing"}


@app.get("/api/task/{task_id}/status")
async def get_task_status(task_id: str) -> dict:
    """Poll task status."""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task_id": task_id,
        "status": task["status"],
        "filename": task["filename"],
        "provider": task["provider"],
        "pii_masked": task["pii_masked"],
        "created_at": task["created_at"],
        "error": task.get("error"),
    }


@app.get("/api/task/{task_id}/result")
async def get_task_result(task_id: str) -> dict:
    """Get the processed result with reinjected PII."""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["status"] == "processing":
        raise HTTPException(status_code=202, detail="Task still processing")

    if task["status"] == "failed":
        raise HTTPException(status_code=500, detail=task.get("error", "Unknown error"))

    return {
        "task_id": task_id,
        "status": task["status"],
        "filename": task["filename"],
        "messages": task["messages"],
        "has_solution": "solution_text" in task,
        "result_preview": task.get("result_preview"),
    }


@app.get("/api/task/{task_id}/download")
async def download_task_result(task_id: str):
    """Download the processed file rebuilt in its original type."""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

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
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Return audit log entries."""
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
        {"id": "claude",  "name": "Anthropic (Claude)",  "key": settings.anthropic_api_key},
        {"id": "openai",  "name": "OpenAI (GPT)",        "key": settings.openai_api_key},
        {"id": "gemini",  "name": "Google (Gemini)",      "key": settings.google_ai_api_key},
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
async def list_tasks() -> dict:
    """Return all tasks for history view."""
    tasks = []
    for task_id, task in task_store.items():
        tasks.append({
            "task_id": task_id,
            "filename": task["filename"],
            "provider": task["provider"],
            "status": task["status"],
            "pii_masked": task["pii_masked"],
            "created_at": task["created_at"],
        })

    tasks.sort(key=lambda t: t["created_at"], reverse=True)
    return {"tasks": tasks}


# ── Background Processing ─────────────────────────────────────────

async def _process_task(
    task_id: str,
    provider_name: str,
    token_map: dict[str, str],
    model_id: str | None = None,
) -> None:
    """Process a task in the background: send to AI, reinject PII."""
    try:
        # Get AI provider
        provider = get_provider(provider_name, get_settings(), model=model_id)
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
            task_store[task_id]["messages"].append({"role": "assistant", "content": clean_msg})
        else:
            # Normal chat message (no file result)
            task_store[task_id]["messages"].append({"role": "assistant", "content": result_text})

        task_store[task_id]["status"] = "completed"

        # Do not delete session or file yet, the user might want to continue chat
        # vault.delete_session(task_id)
        # file_id = task_store[task_id]["file_id"]
        # if file_id in file_store:
        #    upload_path = Path(file_store[file_id]["path"])
        #    upload_path.unlink(missing_ok=True)

    except Exception as exc:
        logger.error(f"Task {task_id} failed: {exc}")
        task_store[task_id]["status"] = "failed"
        task_store[task_id]["error"] = str(exc)

        audit.log(
            event="task_failed",
            session_id=task_id,
            error=str(exc),
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
