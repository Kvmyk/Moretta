"""
Registry of available AI models per provider.
Source: https://models.dev  (March 2026)
"""

AVAILABLE_MODELS: dict[str, list[dict]] = {
    "claude": [
        # ── Flagship ──────────────────────────────────────────
        {"id": "claude-sonnet-4-6-20260217",  "name": "Claude Sonnet 4.6",   "tier": "flagship", "context": 1_000_000},
        {"id": "claude-opus-4-6-20260205",    "name": "Claude Opus 4.6",     "tier": "flagship", "context": 1_000_000},
        # ── Previous generation ───────────────────────────────
        {"id": "claude-sonnet-4-5-20250929",  "name": "Claude Sonnet 4.5",   "tier": "standard", "context": 1_000_000},
        {"id": "claude-opus-4-5-20251124",    "name": "Claude Opus 4.5",     "tier": "standard", "context": 200_000},
        {"id": "claude-opus-4-1-20250805",    "name": "Claude Opus 4.1",     "tier": "standard", "context": 200_000},
        {"id": "claude-sonnet-4-20250514",    "name": "Claude Sonnet 4",     "tier": "standard", "context": 1_000_000},
        {"id": "claude-opus-4-20250522",      "name": "Claude Opus 4",       "tier": "standard", "context": 200_000},
        # ── Fast / Budget ─────────────────────────────────────
        {"id": "claude-haiku-4-5-20251015",   "name": "Claude Haiku 4.5",    "tier": "fast",     "context": 200_000},
        {"id": "claude-3-5-haiku-20241104",   "name": "Claude 3.5 Haiku",    "tier": "fast",     "context": 200_000},
        # ── Legacy (still available) ──────────────────────────
        {"id": "claude-3-7-sonnet-20250224",  "name": "Claude 3.7 Sonnet",   "tier": "legacy",   "context": 200_000},
        {"id": "claude-3-5-sonnet-20241022",  "name": "Claude 3.5 Sonnet",   "tier": "legacy",   "context": 200_000},
    ],

    "openai": [
        # ── GPT-5 family ──────────────────────────────────────
        {"id": "gpt-5.4",            "name": "GPT-5.4",            "tier": "flagship", "context": 272_000},
        {"id": "gpt-5.4-pro",        "name": "GPT-5.4 Pro",        "tier": "flagship", "context": 272_000},
        {"id": "gpt-5.3-instant",    "name": "GPT-5.3 Instant",    "tier": "standard", "context": 400_000},
        {"id": "gpt-5-mini",         "name": "GPT-5 Mini",         "tier": "fast",     "context": 128_000},
        {"id": "gpt-5-nano",         "name": "GPT-5 Nano",         "tier": "fast",     "context": 32_000},
        # ── Previous iterations ───────────────────────────────
        {"id": "gpt-5.2",            "name": "GPT-5.2",            "tier": "legacy",   "context": 400_000},
        {"id": "gpt-5.1",            "name": "GPT-5.1",            "tier": "legacy",   "context": 400_000},
        # ── Specialized ─────────────────────────────────────
        {"id": "gpt-5.3-codex",      "name": "GPT-5.3 Codex",      "tier": "codex",    "context": 1_000_000},
        {"id": "gpt-4.1",            "name": "GPT-4.1",            "tier": "legacy",   "context": 1_000_000},
    ],

    "gemini": [
        # ── Gemini 3 family ───────────────────────────────────
        {"id": "gemini-3.1-pro-preview",   "name": "Gemini 3.1 Pro (Preview)",   "tier": "flagship", "context": 1_048_000},
        {"id": "gemini-3-flash-preview",   "name": "Gemini 3 Flash (Preview)",   "tier": "flagship", "context": 1_048_000},
        {"id": "gemini-3-pro-preview",     "name": "Gemini 3 Pro (Preview)",     "tier": "standard", "context": 1_048_000},
        # ── Gemini 2.5 family (GA) ────────────────────────────
        {"id": "gemini-2.5-pro",           "name": "Gemini 2.5 Pro",             "tier": "standard", "context": 1_048_000},
        {"id": "gemini-2.5-flash",         "name": "Gemini 2.5 Flash",           "tier": "fast",     "context": 1_048_000},
        {"id": "gemini-2.5-flash-lite",    "name": "Gemini 2.5 Flash Lite",      "tier": "fast",     "context": 1_048_000},
    ],
}


DEFAULT_MODELS = {
    "claude": "claude-sonnet-4-6-20260217",
    "openai": "gpt-5.4",
    "gemini": "gemini-2.5-flash",
}


def get_models_for_provider(provider_id: str) -> list[dict]:
    """Return available models for a given provider."""
    return AVAILABLE_MODELS.get(provider_id, [])


def get_default_model(provider_id: str) -> str:
    """Return the default model ID for a given provider."""
    return DEFAULT_MODELS.get(provider_id, "")
