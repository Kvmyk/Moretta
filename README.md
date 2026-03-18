# Moretta v0.5

Moretta is a self-hosted proxy for secure AI usage in enterprise environments. It automatically detects and anonymizes confidential data (PII) from uploaded documents before sending them to external AI models. After the AI processes the anonymized text, Moretta reinjects the original data back. This ensures no data leakage outside your local network.

## How It Works

1. User uploads a DOCX, XLSX, or EML file.
2. System parses the file and detects PII using Microsoft Presidio and a local Ollama model.
3. PII is replaced with UUID tokens and the mapping is saved in an encrypted local database.
4. Anonymized text is sent to an external AI API (Claude, GPT, Gemini).
5. The AI processes the text and returns the result.
6. The system replaces UUID tokens back to the original PII.
7. User downloads the final result.

## Security Model

- Authentication: OIDC SSO via Keycloak (login required for all `/api/*` endpoints).
- Authorization transport: Bearer access token verified against Keycloak JWKS.
- Audit trail: append-only JSONL in `data/logs/audit.jsonl` (no raw PII values).
- File safety: uploaded files are parsed and immediately removed from disk.
- Text safety: raw chat/text input is kept in memory only and not written to `data/uploads`.

## Quick Start

### Prerequisites
- Docker and Docker Compose

### Windows
Double-click the start.bat file in the project directory.

### Linux and macOS
Run the startup script in your terminal:
```bash
chmod +x start.sh
./start.sh
```

Navigate to http://localhost:3000 to use the application.
Configure API keys and vault encryption key in the .env file.
Keycloak endpoints are proxied via frontend at: http://localhost:3000/auth.

### Default App Login (SSO)
The repository provisions a default test realm. Use the following initial credentials:
- **Username:** `moretta.admin`
- **Password:** `ChangeMe123!`
*(Keycloak will force you to change this password on your first login for security).*
## Configuration (.env)

Variable | Default | Description
--- | --- | ---
LOCAL_MODEL | phi4-mini | Local Ollama model for PII detection
OLLAMA_URL | http://ollama:11434 | Ollama API endpoint
VAULT_ENCRYPTION_KEY | | 32-character key for SQLite encryption
DEFAULT_PROVIDER | claude | Default AI provider
DEFAULT_AI_MODEL | claude-sonnet-4 | Default model name
SSO_ENABLED | true | Enable OIDC bearer-token validation for `/api/*`
SSO_ISSUER_URL | http://keycloak:8080/auth/realms/moretta | Internal OIDC issuer URL for backend
SSO_ALLOWED_CLIENT_IDS | moretta-frontend | Comma-separated allowed OIDC clients
VITE_KEYCLOAK_URL | http://localhost:3000/auth | Browser URL for Keycloak (via frontend proxy)
VITE_KEYCLOAK_REALM | moretta | Realm name used by frontend login
VITE_KEYCLOAK_CLIENT_ID | moretta-frontend | OIDC client ID used by frontend
KEYCLOAK_ADMIN | admin | Keycloak bootstrap admin user
KEYCLOAK_ADMIN_PASSWORD | admin123 | Keycloak bootstrap admin password

## Local Models

You can change the model by setting the LOCAL_MODEL variable in your .env file.

Model | RAM Required | Notes
--- | --- | ---
phi4-mini | 4 GB | Recommended. Fast and perfect for logic tasks.
deepseek-r1:8b | 8 GB | Advanced reasoning.
qwen2.5:7b | 8 GB | Capable all-rounder model.
llama3.3:8b | 8 GB | Reliable baseline model.

## Architecture

- Backend: Python 3.11 with FastAPI
- PII Detection: Microsoft Presidio and Ollama
- Vault: Encrypted SQLite database
- Frontend: React 18, Vite, TypeScript, Tailwind CSS
- Infrastructure: Docker Compose

## License
MIT License
