"""
Moretta — Application configuration.
All settings are loaded from environment variables with sensible defaults.
"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Single source of truth for the application version. Surfaced by the FastAPI
# app metadata, the /api/health probe and the startup banner.
APP_VERSION = "0.9"


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseSettings):
    """Central configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Local Model (Ollama) ──────────────────────────────────────
    local_model: str = "phi4-mini"
    ollama_url: str = "http://ollama:11434"

    # ── Vault ─────────────────────────────────────────────────────
    vault_encryption_key: str = ""

    # ── External AI Providers ─────────────────────────────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_ai_api_key: str = ""
    openrouter_api_key: str = ""

    # ── Defaults ──────────────────────────────────────────────────
    default_provider: str = "claude"
    default_ai_model: str = "claude-sonnet-4-6-20260217"

    # ── Application ───────────────────────────────────────────────
    log_level: str = "INFO"
    data_dir: str = "/app/data"

    # Comma-separated list of browser origins allowed to call the API.
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Only trust X-Forwarded-For when the backend actually sits behind a
    # reverse proxy; otherwise a client can forge its own address in the
    # audit trail.
    trust_proxy_headers: bool = False

    # ── Limits ────────────────────────────────────────────────────
    max_upload_bytes: int = 25 * 1024 * 1024
    max_text_chars: int = 500_000
    deep_scan_max_chars: int = 4_000

    # How long an uploaded document and its PII mapping stay usable.
    session_ttl_seconds: int = 3_600
    # How long a finished conversation is kept before it is purged entirely.
    task_retention_seconds: int = 30 * 24 * 3_600

    # ── SSO / OIDC ───────────────────────────────────────────────
    sso_enabled: bool = True
    sso_issuer_url: str = "http://keycloak:8080/auth/realms/moretta"
    sso_allowed_client_ids: str = "moretta-frontend"
    # Roles allowed to read the instance-wide audit log and dashboard.
    sso_admin_roles: str = "moretta-admin"

    # ── Derived Paths ─────────────────────────────────────────────
    @property
    def vault_path(self) -> Path:
        return Path(self.data_dir) / "vault.db"

    @property
    def audit_log_path(self) -> Path:
        return Path(self.data_dir) / "logs" / "audit.jsonl"

    @property
    def upload_dir(self) -> Path:
        return Path(self.data_dir) / "uploads"

    @property
    def store_db_path(self) -> Path:
        return Path(self.data_dir) / "store.db"

    # ── Derived Lists ─────────────────────────────────────────────
    @property
    def allowed_client_id_list(self) -> list[str]:
        return _split_csv(self.sso_allowed_client_ids)

    @property
    def admin_role_list(self) -> list[str]:
        return _split_csv(self.sso_admin_roles)

    @property
    def cors_origin_list(self) -> list[str]:
        return _split_csv(self.cors_allowed_origins)

@lru_cache()
def get_settings() -> Settings:
    """Cached singleton for application settings."""
    return Settings()
