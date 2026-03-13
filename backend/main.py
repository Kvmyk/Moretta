"""
PrivateProxy — Main FastAPI application.
Provides all API endpoints for file upload, PII detection, anonymization,
AI processing, and result retrieval.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
import io

from config import get_settings
from anonymizer.detector import PiiDetector
from anonymizer.replacer import PiiReplacer
from anonymizer.vault import Vault
from reinjektor.reinjektor import Reinjektor
from parsers.docx_parser import parse_docx
from parsers.xlsx_parser import parse_xlsx
from parsers.email_parser import parse_email
from rebuilders import rebuild_xlsx, rebuild_docx
from providers.base import get_provider
from audit.audit_log import AuditLogger

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
replacer = PiiReplacer()
reinjektor = Reinjektor()


# ── Helpers ────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".docx", ".xlsx", ".eml", ".msg"}


def _parse_file(path: Path, ext: str) -> str:
    """Route file to the correct parser and return extracted text."""
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


# ── Endpoints ──────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)) -> dict:
    """Upload a file for processing. Returns file_id."""
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    file_id = str(uuid.uuid4())
    save_path = settings.upload_dir / f"{file_id}{ext}"

    contents = await file.read()
    save_path.write_bytes(contents)

    # Parse file text
    try:
        text = _parse_file(save_path, ext)
    except Exception as exc:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {exc}")

    # Detect PII (Stage 1: Presidio, Stage 2: Ollama)
    pii_results = await detector.detect(text)

    file_store[file_id] = {
        "path": str(save_path),
        "filename": filename,
        "ext": ext,
        "text": text,
        "pii": pii_results,
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

    return {
        "file_id": file_id,
        "filename": filename,
        "size_bytes": len(contents),
        "pii_count": len(pii_results),
    }


class TextInputRequest(BaseModel):
    text: str


@app.post("/api/text")
async def process_text(request: TextInputRequest) -> dict:
    """Accept raw text for processing and PII detection."""
    text = request.text
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    file_id = str(uuid.uuid4())
    filename = "text_message.txt"
    ext = ".txt"

    # Detect PII
    pii_results = await detector.detect(text)

    # Save to store
    file_bytes = text.encode("utf-8")
    save_path = settings.upload_dir / f"{file_id}{ext}"
    save_path.write_bytes(file_bytes)

    file_store[file_id] = {
        "path": str(save_path),
        "filename": filename,
        "ext": ext,
        "text": text,
        "pii": pii_results,
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
        "types": sorted(type_details, key=lambda x: {"critical": 0, "warning": 1, "info": 2}[x["severity"]]),
    }


@app.get("/api/file/{file_id}/preview")
async def get_preview(file_id: str) -> dict:
    """Return anonymized preview of the file text."""
    info = file_store.get(file_id)
    if not info:
        raise HTTPException(status_code=404, detail="File not found")

    anonymized_text, token_map = replacer.anonymize(info["text"], info["pii"])

    return {
        "file_id": file_id,
        "original_length": len(info["text"]),
        "anonymized_text": anonymized_text,
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

    info = file_store[file_id]
    task_id = str(uuid.uuid4())

    # Anonymize text
    anonymized_text, token_map = replacer.anonymize(info["text"], info["pii"])

    # Store mapping in vault
    vault.store_session(task_id, token_map)

    task_store[task_id] = {
        "file_id": file_id,
        "filename": info["filename"],
        "provider": provider_name,
        "model": model_id or "",
        "instruction": instruction,
        "status": "processing",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pii_masked": len(token_map),
        "result_text": None,
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
        _process_task, task_id, anonymized_text, instruction, provider_name, token_map, model_id
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
        "result_text": task["result_text"],
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
    text = task["result_text"] or ""

    try:
        if ext == ".xlsx":
            content_bytes = rebuild_xlsx(text)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif ext == ".docx":
            content_bytes = rebuild_docx(text)
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
        raise HTTPException(status_code=500, detail=f"Failed to rebuild file: {exc}")


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
    anonymized_text: str,
    instruction: str,
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

        # Send anonymized text to external AI
        ai_response = await provider.process(anonymized_text, instruction)

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

        task_store[task_id]["result_text"] = result_text
        task_store[task_id]["status"] = "completed"

        # Clean up vault session
        vault.delete_session(task_id)

        # Clean up uploaded file
        file_id = task_store[task_id]["file_id"]
        if file_id in file_store:
            upload_path = Path(file_store[file_id]["path"])
            upload_path.unlink(missing_ok=True)

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
    "PERSON": "Imię i nazwisko",
    "EMAIL_ADDRESS": "Adres e-mail",
    "PHONE_NUMBER": "Numer telefonu",
    "IBAN_CODE": "Numer IBAN",
    "NRP": "PESEL / NIP",
    "PESEL": "PESEL",
    "NIP": "NIP",
    "LOCATION": "Adres zamieszkania",
    "DATE_TIME": "Data",
    "CREDIT_CARD": "Karta kredytowa",
    "CRYPTO": "Adres kryptowalutowy",
    "SALARY": "Kwoty wynagrodzenia",
    "FINANCIAL": "Dane finansowe",
    "PROJECT_ID": "Kod projektu",
    "CLIENT_NAME": "Nazwa klienta",
    "CONTRACT_NUMBER": "Numer umowy",
    "INTERNAL_ID": "Identyfikator wewnętrzny",
    "IP_ADDRESS": "Adres IP",
}

_SEVERITY_MAP = {
    "PERSON": "critical",
    "NRP": "critical",
    "PESEL": "critical",
    "NIP": "critical",
    "CREDIT_CARD": "critical",
    "IBAN_CODE": "critical",
    "EMAIL_ADDRESS": "critical",
    "PHONE_NUMBER": "critical",
    "SALARY": "warning",
    "FINANCIAL": "warning",
    "LOCATION": "warning",
    "CLIENT_NAME": "warning",
    "CONTRACT_NUMBER": "warning",
}


def _get_label(pii_type: str) -> str:
    return _LABEL_MAP.get(pii_type, pii_type)


def _get_severity(pii_type: str) -> str:
    return _SEVERITY_MAP.get(pii_type, "info")
