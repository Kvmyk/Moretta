# Installation and Configuration

Follow these steps to deploy Moretta on your infrastructure.

## Prerequisites
- **Docker** and **Docker Compose** installed.
- Minimum **8 GB RAM** (16 GB recommended if running large local models).

## Setup Instructions

### 1. Clone & Environment
```bash
git clone https://github.com/Kvmyk/moretta.git
cd moretta
cp .env.example .env
```

### 2. Configure .env
Edit the `.env` file and set the following essential variables:
- `VAULT_ENCRYPTION_KEY`: A 32-64 hex character string to encrypt the local vault.
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_AI_API_KEY` / `OPENROUTER_API_KEY`: At least one external AI provider key (unless using only local Ollama).

### 3. Launch

#### **Windows**
Simply double-click the `start.bat` file in the root directory.

#### **Linux / macOS**
Run the startup script:
```bash
chmod +x start.sh
./start.sh
```

## Accessing the Application

- **Frontend:** [http://localhost:3000](http://localhost:3000)
- **Keycloak Admin:** [http://localhost:8080/auth](http://localhost:8080/auth)

### Initial Credentials (SSO)
Moretta comes with a pre-configured test realm.
- **Username:** `moretta.admin`
- **Password:** `ChangeMe123!`
*Note: You will be forced to change this password on the first login.*

## Detailed Configuration Reference

| Variable | Default | Description |
| --- | --- | --- |
| `LOCAL_MODEL` | `phi4-mini` | Model used for local PII detection. |
| `OLLAMA_URL` | `http://ollama:11434` | Internal endpoint for Ollama container. |
| `DEFAULT_PROVIDER` | `claude` | Main AI engine (`claude`, `openai`, `gemini`, `openrouter`, `ollama`). |
| `SSO_ENABLED` | `true` | Toggles OIDC validation for backend endpoints. |

## Troubleshooting

- **Container Logs:** Run `docker compose logs -f` to see real-time output.
- **Port Conflicts:** Ensure ports `3000`, `8000`, and `8080` are available on your host.
- **Ollama Initialization:** On the first run, the system will download the local model (approx 2.5GB). This may take several minutes depending on your connection.
