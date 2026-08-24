#!/bin/bash

echo "Starting Moretta environment..."

if ! command -v docker &> /dev/null
then
    echo "[ERROR] Docker is not installed or not running."
    exit 1
fi

if [ ! -f .env ]; then
    echo "[INFO] Creating .env file from .env.example..."
    cp .env.example .env
fi

# Generate any secret that is still blank. Shipping a default would mean every
# install shares the same encryption key and admin password.
generate_secret() {
    if command -v openssl &> /dev/null; then
        openssl rand -base64 36 | tr -d '\n/+=' | cut -c1-40
    else
        python3 -c "import secrets; print(secrets.token_urlsafe(30))"
    fi
}

fill_if_empty() {
    local key="$1"
    local current
    current=$(grep "^${key}=" .env | cut -d '=' -f2- | tr -d '[:space:]')
    if [ -z "$current" ]; then
        local value
        value=$(generate_secret)
        # Portable in-place edit (GNU sed and BSD/macOS sed differ on -i).
        sed "s|^${key}=.*|${key}=${value}|" .env > .env.tmp && mv .env.tmp .env
        echo "[INFO] Generated ${key}."
    fi
}

fill_if_empty "VAULT_ENCRYPTION_KEY"
fill_if_empty "KEYCLOAK_ADMIN_PASSWORD"

MODEL=$(grep "^LOCAL_MODEL=" .env | cut -d '=' -f2)
if [ -z "$MODEL" ]; then
    MODEL="phi4-mini"
fi

echo "[INFO] Local model selected: $MODEL"

echo "[INFO] Starting containers..."
docker compose up -d

echo "[INFO] Waiting 10 seconds for Ollama service to start..."
sleep 10

echo "[INFO] Pulling model $MODEL inside container..."
docker exec privateproxy-ollama ollama pull "$MODEL"

if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to pull the model."
else
    echo "[SUCCESS] Model pulled successfully."
fi

echo ""
echo "Moretta is running."
echo "Frontend:      http://localhost:3000"
echo "Keycloak (SSO): http://localhost:3000/auth"
echo ""
echo "The backend (8000), Keycloak (8080) and Ollama (11434) are bound to"
echo "localhost only and are not reachable from the network."
echo "Keycloak admin password is in your .env file (KEYCLOAK_ADMIN_PASSWORD)."
