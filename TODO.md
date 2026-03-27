# Moretta TODO

## Features & Enhancements

- [ ] **Soft-Update Notification System (Option 1)**
  - Implement a mechanism in the backend that periodically (e.g., every 24h) polls the GitHub API for the latest release tag.
  - Compare the fetched GitHub tag with the local `VERSION`.
  - If a new version is available, surface this information to the frontend.
  - Display a non-intrusive banner or notification badge (e.g., a red dot on the "Settings" or "Update Available" tab) in the UI.
  - The notification should direct the administrator to a documentation page or provide instructions on how to manually update safely (e.g., `git pull && docker compose pull && docker compose up -d`).
  - Create a lightweight `update.sh` / `update.bat` script in the repository to make the process a 1-click execution for the administrator.

## CI/CD Pipeline (GitHub Actions)

- [ ] **1. Standard CI / Tests (Priority)**
  - Implement automated unit tests (`pytest`), ensuring that `detector.py` and PII logic always work correctly before merging.
  - Write specific unit tests masking the Deep Scan / Ollama (`detect_deep_async`), utilizing `unittest.mock` to simulate context-aware AI detections.
  - Configure formatters and linters (e.g., Ruff for Python, ESLint/Prettier for React) to enforce clean and consistent code.
  - Add static type checking (MyPy for Python, TSC for TypeScript) to catch errors early at the Pull Request stage.

- [ ] **2. Security & Compliance (Critical for AI Gateway)**
  - Configure Secret Scanning (TruffleHog / GitHub Advanced Security) to prevent accidental API key leaks (e.g., OpenAI) in the repository.
  - Add Dependency Scanning (Dependabot/Snyk/Trivy) to monitor vulnerabilities (CVEs) in packages.
  - Add SAST tools (e.g., Bandit) to scan for structural vulnerabilities in Python code.

- [ ] **3. Continuous Delivery & Docker**
  - Configure a build test using `docker-compose` on every PR to prevent broken environments for clients.
  - Automate Docker image builds after merges to `main` or new releases (pushing them to GitHub Container Registry - GHCR), making Moretta deployment easier without building from source locally.
  - 
## UI/UX Enhancements

- [ ] **1. Improve Deep Scan feedback**
  - Add a "Deep scan in progress (message)..." bubble or indicator to inform the user that their prompt (which is send to provider after the local deep scan) is being scanned for PII before being sent to the AI provider.
- [ ] **2. Chat Interface Scaling**
  - Implement auto-scaling for the chat input and message containers to handle varying message lengths and keep the input bar visible at the bottom.
- [ ] **3. Fix Message Display Delay**
  - Ensure the user's message appears immediately in the chat thread, even while the PII scan/processing is running in the background.

