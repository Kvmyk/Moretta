# PrivateProxy

**Self-hosted proxy for secure AI usage in enterprise environments.** PrivateProxy automatically detects and anonymizes confidential data (PII) from uploaded documents before sending them to external AI models like Claude, GPT-4o, or Gemini. After the AI processes the anonymized content, PrivateProxy reinjects the original data back — ensuring **zero data leakage**.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                     CORPORATE NETWORK                           │
│                                                                 │
│  ┌──────────┐    ┌───────────────────────────────────────┐      │
│  │ Employee  │───▶│  PrivateProxy (local server)          │      │
│  │ uploads   │    │                                       │      │
│  │ file      │    │  1. Parse DOCX/XLSX/EML               │      │
│  │ (DOCX,    │    │  2. Detect PII (Presidio + Ollama)    │      │
│  │  XLSX,    │    │  3. Replace PII → UUID tokens          │      │
│  │  EML)     │    │  4. Store mapping in encrypted vault   │      │
│  └──────────┘    └──────────┬────────────────────────────┘      │
│                              │                                   │
│                              │ Only anonymized text              │
│                              ▼                                   │
│  ┌──────────┐    ┌───────────────────────────────────────┐      │
│  │ Employee  │◀───│  PrivateProxy (reinjektion)           │      │
│  │ downloads │    │                                       │      │
│  │ result    │    │  7. Replace tokens → original PII      │      │
│  │           │    │  8. Verify all tokens resolved          │      │
│  └──────────┘    └──────────┬────────────────────────────┘      │
│                              ▲                                   │
└──────────────────────────────┼───────────────────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │  External AI API     │
                    │  (Claude/GPT/Gemini) │
                    │                      │
                    │  5. Process anon text │
                    │  6. Return result     │
                    └─────────────────────┘

     ⚠️  Confidential data NEVER leaves the corporate network
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- (Optional) NVIDIA GPU for faster local model inference

### Run

```bash
# 1. Clone the repository
git clone https://github.com/your-org/privateproxy.git
cd privateproxy

# 2. Configure environment
cp .env.example .env
# Edit .env — set VAULT_ENCRYPTION_KEY and at least one AI provider API key

# 3. Start all services
docker-compose up -d

# 4. Pull the local model (first run only)
docker exec privateproxy-ollama ollama pull mistral:7b

# 5. Open the UI
# Navigate to http://localhost:3000
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LOCAL_MODEL` | Local Ollama model for PII detection | `mistral:7b` |
| `OLLAMA_URL` | Ollama API endpoint | `http://ollama:11434` |
| `VAULT_ENCRYPTION_KEY` | 32-char key for SQLite vault encryption | *(required)* |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude | *(optional)* |
| `OPENAI_API_KEY` | OpenAI API key for GPT models | *(optional)* |
| `GOOGLE_AI_API_KEY` | Google AI API key for Gemini | *(optional)* |
| `DEFAULT_PROVIDER` | Default AI provider (`claude`/`openai`/`gemini`) | `claude` |
| `DEFAULT_AI_MODEL` | Default model name | `claude-sonnet-4-20250514` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DATA_DIR` | Data directory for vault and logs | `/app/data` |

## Local Models

| Model | RAM Required | GPU | Quality | Notes |
|-------|-------------|-----|---------|-------|
| `mistral:7b` | 8 GB | Recommended | ★★★★☆ | Best balance of speed & quality |
| `phi3:mini` | 4 GB | Not required | ★★★☆☆ | CPU-friendly, lighter |
| `llama3:8b` | 8 GB | Recommended | ★★★★★ | Highest quality, slower |
| `gemma:7b` | 8 GB | Recommended | ★★★★☆ | Good alternative |

Change the model by setting `LOCAL_MODEL` in your `.env` file.

## Architecture

- **Backend**: Python 3.11 + FastAPI
- **PII Detection**: Microsoft Presidio (deterministic) + Ollama (contextual LLM)
- **Vault**: SQLite with encryption for PII ↔ token mappings
- **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS
- **Infrastructure**: Docker Compose (3 services)

## Security

1. **No PII in logs** — only types and counts are logged
2. **Encrypted vault** — SQLite DB encrypted with PRAGMA key
3. **Temp file cleanup** — files deleted after task completion
4. **CORS restriction** — localhost only
5. **No external calls** — except explicit AI provider API calls (audited)
6. **UUID tokens** — impossible for external AI to guess original values

## License

MIT License — see [LICENSE](LICENSE) for details.
