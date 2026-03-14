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

MODEL=$(grep "^LOCAL_MODEL=" .env | cut -d '=' -f2)
if [ -z "$MODEL" ]; then
    MODEL="phi4-mini"
fi

echo "[INFO] Local model selected: $MODEL"

echo "[INFO] Starting containers..."
docker-compose up -d

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
echo "Frontend: http://localhost:3000"
echo "Backend: http://localhost:8000"
