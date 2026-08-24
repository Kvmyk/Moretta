# Moretta v0.9

Moretta is a self-hosted proxy for secure AI usage in enterprise environments. It automatically detects and anonymizes confidential data (PII) from uploaded documents before sending them to external AI models. After the AI processes the anonymized text, Moretta reinjects the original data back. This ensures no data leakage outside your local network.

## How It Works

1. User uploads a DOCX, XLSX, PDF, TXT, or EML/MSG file (or pastes raw text).
2. System parses the file and detects PII in two stages: Microsoft Presidio plus checksum-verified Polish regex rules, then a contextual "deep scan" via a local Ollama model.
3. PII is replaced with UUID tokens and the mapping is saved in the encrypted vault.
4. Anonymized text is sent to an external AI API (Claude, GPT, Gemini, OpenRouter, or local Ollama).
5. The AI processes the text and returns the result.
6. The system replaces UUID tokens back to the original PII.
7. User downloads the final result, rebuilt in the original file format.

## Security Model

- **Authentication:** OIDC SSO via Keycloak. A valid bearer token is required for every `/api/*` endpoint except `/api/health`.
- **Token validation:** RS256 signature checked against the Keycloak JWKS endpoint, with issuer and expiry verified. The client is checked against `SSO_ALLOWED_CLIENT_IDS` using the `azp` claim, falling back to `aud`.
- **Authorization:** every stored record carries its owner; files, tasks and conversations are only readable by the user who created them. The audit log and dashboard aggregate the whole instance and additionally require a role from `SSO_ADMIN_ROLES`.
- **Encryption at rest:** `VAULT_ENCRYPTION_KEY` encrypts the PII token maps, the parsed document text, chat history and stored file blobs. Without the key everything is written in plaintext and the backend logs a CRITICAL warning at startup.
- **Security Guard:** local LLM-based DLP that blocks prompts containing PII. Fail-closed — if the local model is unreachable, the request is refused.
- **Deep scan gate:** a task cannot be created while contextual PII detection is still running, so a document is never sent out under-masked.
- **Vault fail-closed:** if a PII mapping is missing or cannot be decrypted, the conversation is refused rather than forwarded without re-anonymization.
- **Audit trail:** append-only JSONL in `data/logs/audit.jsonl`, containing no raw PII values.
- **File safety:** uploaded files are parsed and immediately removed from disk. Raw text input is never written to `data/uploads`.
- **Limits:** uploads are capped by `MAX_UPLOAD_BYTES` and raw text by `MAX_TEXT_CHARS`.
- **Session TTL:** documents and their PII mappings expire after `SESSION_TTL_SECONDS` (1 hour by default); conversations are purged entirely after `TASK_RETENTION_SECONDS`.
- **Network exposure:** only the frontend (port 3000) is published to the host. The backend, Keycloak and Ollama are bound to `127.0.0.1`.

## Quick Start

### Prerequisites
- Docker and Docker Compose

### Windows
Double-click the `start.bat` file in the project directory.

### Linux and macOS
```bash
chmod +x start.sh
./start.sh
```

Both scripts create `.env` from `.env.example` and generate a `VAULT_ENCRYPTION_KEY` and a Keycloak admin password if those are still empty. Add your AI provider API keys to `.env` afterwards.

Navigate to http://localhost:3000 to use the application. Keycloak is proxied through the frontend at http://localhost:3000/auth.

> **Do not change `VAULT_ENCRYPTION_KEY` after first use.** Existing vault entries and stored records become unreadable; the backend logs the affected rows and skips them.

### Initial User Setup
For security, the realm starts with an empty user list.
- Log in to Keycloak Admin at http://localhost:8080/auth using `KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD` from your `.env`.
- Switch to the **`moretta`** realm (top-left dropdown).
- Create a user in the **Users** section and set a password in **Credentials**.
- To let that user see the Dashboard and Audit log, create a realm role named `moretta-admin` (see `SSO_ADMIN_ROLES`) and assign it under **Role mapping**. Users without it can still use the full anonymization workflow.
- Log in at http://localhost:3000.

## AI Providers

Moretta supports 5 AI providers. Configure one or more via `.env`:

Provider | Env Variable | Description
--- | --- | ---
Anthropic (Claude) | `ANTHROPIC_API_KEY` | Claude Sonnet 4.6, Opus 4.6, Haiku
OpenAI (GPT) | `OPENAI_API_KEY` | GPT-5.4, GPT-5.4 Pro, GPT-5 Mini
Google (Gemini) | `GOOGLE_AI_API_KEY` | Gemini 3 Pro, 2.5 Flash
OpenRouter | `OPENROUTER_API_KEY` | 200+ models from multiple vendors via single API key (openrouter.ai)
Ollama (Local) | — | Uses existing local Ollama instance. Zero data leaves the network.

Available model ids are defined in `backend/providers/models_registry.py`. A model id that is not in the registry is rejected with HTTP 400 rather than being forwarded to the provider.

## Configuration (.env)

Variable | Default | Description
--- | --- | ---
LOCAL_MODEL | phi4-mini | Local Ollama model for PII detection
OLLAMA_URL | http://ollama:11434 | Ollama API endpoint
VAULT_ENCRYPTION_KEY | *(required)* | Encrypts vault mappings, document text, chat history and blobs
ANTHROPIC_API_KEY | | Anthropic Claude API key
OPENAI_API_KEY | | OpenAI API key
GOOGLE_AI_API_KEY | | Google AI API key
OPENROUTER_API_KEY | | OpenRouter API key (access 200+ models)
DEFAULT_PROVIDER | claude | Default AI provider (`claude` / `openai` / `gemini` / `openrouter` / `ollama`)
DEFAULT_AI_MODEL | claude-sonnet-4-6-20260217 | Default model id; must exist in the registry
LOG_LEVEL | INFO | Python log level
DATA_DIR | /app/data | Runtime data directory
CORS_ALLOWED_ORIGINS | http://localhost:3000,http://127.0.0.1:3000 | Comma-separated browser origins allowed to call the API
TRUST_PROXY_HEADERS | false | Honour `X-Forwarded-For` for audit IPs. Enable only behind a trusted proxy
MAX_UPLOAD_BYTES | 26214400 | Maximum upload size (25 MB)
MAX_TEXT_CHARS | 500000 | Maximum length of pasted text
DEEP_SCAN_MAX_CHARS | 4000 | Size of each deep-scan chunk sent to the local model
SESSION_TTL_SECONDS | 3600 | Lifetime of an uploaded document and its PII mapping
TASK_RETENTION_SECONDS | 2592000 | Conversations are purged after 30 days
SSO_ENABLED | true | Enable OIDC bearer-token validation for `/api/*`
SSO_ISSUER_URL | http://keycloak:8080/auth/realms/moretta | Internal OIDC issuer URL for backend
SSO_ALLOWED_CLIENT_IDS | moretta-frontend | Comma-separated allowed OIDC clients
SSO_ADMIN_ROLES | moretta-admin | Roles allowed to read the audit log and dashboard
VITE_KEYCLOAK_URL | http://localhost:3000/auth | Browser URL for Keycloak (via frontend proxy)
VITE_KEYCLOAK_REALM | moretta | Realm name used by frontend login
VITE_KEYCLOAK_CLIENT_ID | moretta-frontend | OIDC client ID used by frontend
KEYCLOAK_ADMIN | admin | Keycloak bootstrap admin user
KEYCLOAK_ADMIN_PASSWORD | *(required)* | Keycloak bootstrap admin password

## Local Models

You can change the model by setting the `LOCAL_MODEL` variable in your `.env` file.

Model | RAM Required | Notes
--- | --- | ---
phi4-mini | 4 GB | Recommended. Fast and perfect for logic tasks.
deepseek-r1:8b | 8 GB | Advanced reasoning.
qwen2.5:7b | 8 GB | Capable all-rounder model.
llama3.3:8b | 8 GB | Reliable baseline model.

## PII Detection

Detection runs in two stages:

1. **Deterministic** — Microsoft Presidio (Polish NLP model) plus regex rules for Polish business identifiers. PESEL, NIP, REGON and IBAN matches are verified against their check digits, so ordinary invoice numbers and amounts are not masked by accident.
2. **Contextual deep scan** — a local Ollama model looks for data that has no fixed format: project codenames, salary figures, internal identifiers and infrastructure addresses. Long documents are scanned in chunks (`DEEP_SCAN_MAX_CHARS`) rather than truncated.

The deep scan runs in the background after upload. Task creation is blocked until it finishes.

## Architecture

- Backend: Python 3.11 with FastAPI
- PII Detection: Microsoft Presidio and Ollama
- Storage: SQLite (WAL mode) with app-level Fernet encryption
- Frontend: React 18, Vite, TypeScript, Tailwind CSS
- Infrastructure: Docker Compose

## Development

```bash
# Backend tests (must be run from backend/)
cd backend && pytest
cd backend && pytest tests/test_detector.py -q

# Frontend
cd frontend && npm install && npm run dev
cd frontend && npm run build      # tsc typecheck + production build
```

## Data Handling & Logs

Moretta implements a PII-safe logging strategy. The system maintains two log streams:

**1. Audit Log (JSONL)** — `data/logs/audit.jsonl`
- Logs every user action: uploads, PII viewing, task creation, chat, downloads.
- **Does NOT log PII values** — only types and counts (e.g. `pii_types: ["PERSON","PESEL"]`).
- **Filenames are sanitized** — logged as `***.docx` instead of original names (which may contain personal data).
- **Error messages are sanitized** — PII patterns (PESEL, email, phone, IBAN) are stripped from exception messages.

**2. Access Log (stdout / Docker logs)**
- Logs every HTTP request with: method, path, status code, duration, username, client IP.
- Does not log request or response bodies.

**Data stored in logs:**
- `user` (SSO username) — required for security audit trail. Justified under GDPR Art. 6(1)(f) (legitimate interest for security monitoring).
- `ip` (client IP address) — logged for failed authentication attempts. Taken from the socket unless `TRUST_PROXY_HEADERS` is enabled.
- No PII values, no file contents, no instruction text are ever logged.

**Retention:** The audit log file is append-only and not automatically rotated. For production use, configure log rotation via Docker or an external tool (e.g. `logrotate`).

## License

GNU AGPLv3 — This project is licensed under the GNU Affero General Public License v3.0. See the [LICENSE](LICENSE) file for the full text. This ensures that Moretta remains open-source, even when provided as a network service.
