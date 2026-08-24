# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Repository conventions in `AGENTS.md` also apply (structure, style, commit/PR expectations, security boundaries). This file covers architecture and workflow specifics not documented there.

## Commands

Backend tests must be run from `backend/` — `backend/pytest.ini` sets `testpaths = tests` and `asyncio_mode = auto`, and `tests/conftest.py` puts `backend/` on `sys.path`:

```bash
cd backend && pytest                                  # full suite
cd backend && pytest tests/test_detector.py           # one file
cd backend && pytest tests/test_core.py::TestUploadFlow::test_upload_docx_file   # one test
cd backend && pytest -k deep_scan                     # by keyword
```

Frontend:

```bash
cd frontend && npm install && npm run dev    # Vite dev server on :3000, proxies /api → localhost:8000
cd frontend && npm run build                 # tsc typecheck + vite build (this is the CI typecheck)
```

Full stack: `docker-compose up -d`, or `./start.sh` / `start.bat` which also bootstraps `.env` and pulls the Ollama model. UI at http://localhost:3000, Keycloak at http://localhost:3000/auth.

Tests never hit Ollama or a real provider — `conftest.py` sets `SSO_ENABLED=false`, an empty API key for every provider, and a temp `DATA_DIR` **before** importing `main`. Anything that needs the local LLM must be mocked (see `TestDetectorDeepScan`).

## Architecture

The whole product is one pipeline: **parse → detect → mask → send out → reinject → rebuild**. Understanding where PII is plaintext vs tokenized is the key invariant in this codebase.

1. `POST /api/upload` (or `/api/text`) — `_parse_file` routes by extension to `parsers/{docx,xlsx,pdf,email}_parser.py`. Each parser returns `{"text": str, "preview_data": {...}}`; `preview_data` is either `{"type": "spreadsheet", "sheets": [{"name", "rows"}]}` or `{"type": "document", "text"}`. The uploaded file is written to `data/uploads/`, parsed, then **deleted immediately** in a `finally` block; the original bytes live on only as the encrypted `original_bytes` blob in the store (used later as a rebuild template).
2. `anonymizer/detector.py` runs two stages: Presidio + Polish regex rules (`POLISH_REGEX_RULES` — PESEL, NIP, REGON, KRS, IBAN, PL phones) synchronously, then `detect_deep_async` (Ollama, contextual/business PII) as a FastAPI `BackgroundTask` that appends to `file_store[file_id]["pii"]` and sets `deep_scan_completed`.
3. `POST /api/task` — `anonymizer/guard.py` (`SecurityGuard`) asks the local LLM whether the *user instruction* leaks PII and **fails closed**: if Ollama is unreachable, the request is blocked. Then `anonymizer/replacer.py` swaps PII for `[PREFIX_xxxx]` tokens (prefixes are Polish: `PERSON`→`OSOBA`, `LOCATION`→`ADRES`, …) and the `{token: original}` map goes into the encrypted `Vault` keyed by `task_id`.
4. `_process_task` (background) — before every provider call it **re-anonymizes the entire message history**, because assistant turns were reinjected with real PII after the previous response and users may type PII manually. It builds a reverse map and replaces longest-original-first. Skipping this leaks PII to the external API.
5. Providers (`providers/*.py`, created by `get_provider` in `providers/base.py`, model defaults in `models_registry.py`) all share the same Polish system prompt contract: the model returns a full modified document wrapped in `<ROZWIAZANIE>…</ROZWIAZANIE>`, or a plain clarifying message with no tags. `main.py` extracts the tagged block into `solution_text` and strips the tags from the chat bubble. Changing that contract means changing all five providers plus the parsing in `_process_task`.
6. `reinjektor/reinjektor.py` restores originals and reports unresolved tokens (`TOKEN_PATTERN` must stay in sync with `replacer._generate_token`).
7. `GET /api/task/{id}/download` — `rebuilders.py` reconstructs DOCX/XLSX from `solution_text` using the stored original bytes as a formatting template (written to a `NamedTemporaryFile` and deleted in `finally`).

### Storage

`store.py` (`PersistentStore`) and `anonymizer/vault.py` (`Vault`) both wrap SQLite via `db.connect`. `PersistentStore` is a dict-like write-through cache: everything is held in memory and every write persists JSON to a `files` or `tasks` table. **Mutating a nested value in place does not persist** — call `store.persist(key)` or `store.update_field(key, field, value)` afterwards.

App-level encryption (`storage_crypto.py`, Fernet keyed by SHA-256 of `VAULT_ENCRYPTION_KEY`) covers vault token maps and the `BLOB_FIELDS` (`original_bytes`) only — the rest of the row is plaintext JSON. With no key set, encryption is a no-op, which is how tests run.

TTL: `SESSION_TTL_SECONDS = 3600` in `main.py`; a loop every 10 min drops expired files and marks tasks `context_expired` while deleting their vault sessions.

`README.md` documents a PostgreSQL backend (`DATABASE_BACKEND`, `DATABASE_URL`) and a `backend/scripts/migrate_sqlite_to_postgres.py`. **The working tree has reverted to SQLite-only** — those settings do not exist in `config.py` and the script is deleted. `.github/workflows/ci-tests.yml` still references the deleted `backend/tests/test_migration_formats.py`, so backend CI currently fails; fix the workflow (or restore Postgres) rather than assuming either doc is current.

### Auth

`auth.py` validates Keycloak RS256 tokens against JWKS. Note that `verify_aud` and `verify_iss` are both disabled in `jwt.decode`; the only client check is the `azp` claim against `SSO_ALLOWED_CLIENT_IDS`. The `require_sso_token` middleware in `main.py` gates `/api/*` and can be disabled with `SSO_ENABLED=false` (tests only). Every record carries `user_id`/`username`, and `_require_owned_file` / `_require_owned_task` enforce per-user ownership on all read endpoints — new endpoints touching stored records must use them.

### Audit logging

`audit/audit_log.py` appends JSONL to `data/logs/audit.jsonl`. Log PII **types and counts, never values**; run filenames through `_sanitize_filename` (→ `***.docx`) and exception text through `_sanitize_error` (strips PESEL/email/phone/IBAN patterns). `data_left_boundary=True` triggers a CRITICAL alert and should stay `False` everywhere.

### Frontend

React 18 + Vite + Tailwind. `src/pages/` are routed views (`NewTask`, `History`, `Dashboard`, `AuditLog`, `Settings`), `src/auth/keycloak.ts` + `apiFetch.ts` attach the bearer token, `src/auth/components/` holds the flow-specific UI (upload, PII card, mask preview). In Docker the frontend nginx proxies `/api/` to the backend and `/auth/`, `/realms/`, `/resources/` to Keycloak — the browser never talks to port 8000 or 8080 directly.

## Notes

User-facing strings, prompts, and detection rules are Polish; keep new ones consistent. `backend/main.py` is already ~1300 lines — put new logic in the appropriate module rather than growing it further.
