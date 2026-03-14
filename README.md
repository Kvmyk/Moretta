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

## Configuration (.env)

Variable | Default | Description
--- | --- | ---
LOCAL_MODEL | phi4-mini | Local Ollama model for PII detection
OLLAMA_URL | http://ollama:11434 | Ollama API endpoint
VAULT_ENCRYPTION_KEY | | 32-character key for SQLite encryption
DEFAULT_PROVIDER | claude | Default AI provider
DEFAULT_AI_MODEL | claude-sonnet-4 | Default model name

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
