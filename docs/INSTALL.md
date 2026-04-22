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
- `DATABASE_URL`: PostgreSQL DSN used by the backend (`postgresql://moretta:moretta@postgres:5432/moretta` by default).
- `VAULT_ENCRYPTION_KEY`: App-level encryption key for vault payloads and stored blobs.
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

### Initial User Setup

For enhanced security, the repository does **not** include pre-provisioned users. To access Moretta for the first time:

1.  Go to the **[Keycloak Admin Console](http://localhost:8080/auth)**.
2.  Login with **Master Admin** credentials from your `.env` (default: `admin` / `admin123`).
3.  Switch the realm from `master` to **`moretta`** (dropdown menu in the top left).
4.  Navigate to **Users** -> **Add user** and create your primary account.
5.  Set your password in the **Credentials** tab (set "Temporary" to **on**, so you can change your password later).
6.  You can now login to the main dashboard at [http://localhost:3000](http://localhost:3000).

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
