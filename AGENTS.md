# Repository Guidelines

## Domain Knowledge
Moretta is a self-hosted AI proxy for document workflows in regulated environments. This repo owns the local flow: parse uploads, detect and mask PII, send anonymized content to AI providers, reinject original values, and expose the UI/API behind Keycloak SSO. The backend stores encrypted vault data and audit logs under `data/`; model APIs, Ollama, and Keycloak are integrations rather than code owned here.

## Project Structure & Module Organization
- `backend/`: FastAPI service, PII pipeline, provider adapters, audit logging, and pytest suite in `backend/tests/`.
- `frontend/src/`: React 18 + Vite UI; pages live in `pages/`, shared auth helpers in `auth/`, reusable UI in `components/`.
- `keycloak/`: realm export and theme overrides for local SSO.
- `data/`: runtime storage for logs, vault, and persisted task/file state.
- `docs/`: install and published documentation.

## Build, Test, and Development Commands
- `docker-compose up -d`: start the full stack locally.
- `.\start.bat` or `./start.sh`: bootstrap `.env`, start containers, and pull the configured Ollama model.
- `cd frontend; npm install; npm run dev`: run the Vite frontend in development.
- `cd frontend; npm run build`: type-check and build the frontend bundle.
- `cd backend; pytest`: run backend tests from `backend/pytest.ini`.

## Coding Style & Naming Conventions
Use 4 spaces in Python and 2 spaces in TypeScript/TSX. Follow existing naming: snake_case for backend modules/functions (`openai_provider.py`), PascalCase for React components/pages (`AuditLog.tsx`), and `UPPER_SNAKE_CASE` for constants. Keep backend logic split by responsibility instead of growing `backend/main.py`. No dedicated lint config is checked in, so match surrounding style before introducing new tooling.

## Testing Guidelines
Backend tests use `pytest` and `pytest-asyncio`. Place tests in `backend/tests/`, name files `test_*.py`, and cover both happy paths and security-sensitive failures. When changing API flows, update or add end-to-end style tests similar to `backend/tests/test_core.py`.

## Commit & Pull Request Guidelines
Recent history uses short imperative subjects without prefixes, for example `Add pending instruction bubble and textarea resize` or `Trim regex matches; add tests; tweak docs`. Keep commits focused and descriptive. PRs should explain the user-visible change, call out any `.env`, auth, or data-format impact, link issues when applicable, and include screenshots for UI changes.

## Security & Boundaries
Never commit real secrets or production `.env` values. Preserve PII-safe logging, avoid writing raw uploads back to disk outside the established flow, and treat changes under `auth.py`, provider adapters, audit logging, and `data/` persistence as high-risk.
