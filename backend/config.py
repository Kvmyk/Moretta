"""
Moretta — Application configuration.
All settings are loaded from environment variables with sensible defaults.
"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration loaded from environment variables."""

    # ── Local Model (Ollama) ──────────────────────────────────────
    local_model: str = "phi4-mini"
    ollama_url: str = "http://ollama:11434"

    # ── Vault ─────────────────────────────────────────────────────
    vault_encryption_key: str = ""
    database_backend: str = "postgres"
    database_url: str = "postgresql://moretta:moretta@postgres:5432/moretta"

    # ── External AI Providers ─────────────────────────────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_ai_api_key: str = ""
    openrouter_api_key: str = ""

    # ── Defaults ──────────────────────────────────────────────────
    default_provider: str = "claude"
    default_ai_model: str = "claude-sonnet-4.6-20260217"

    # ── Application ───────────────────────────────────────────────
    log_level: str = "INFO"
    data_dir: str = "/app/data"

    # ── SSO / OIDC ───────────────────────────────────────────────
    sso_enabled: bool = True
    sso_issuer_url: str = "http://keycloak:8080/auth/realms/moretta"
    sso_allowed_client_ids: str = "moretta-frontend"

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton for application settings."""
    return Settings()
