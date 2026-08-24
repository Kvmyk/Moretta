# ── Build stage: compile wheels with a toolchain we do not ship ──
FROM python:3.11-slim AS build

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

COPY --from=build /install /usr/local

RUN python -m spacy download pl_core_news_sm

# Run as an unprivileged user; the container has no reason to be root.
RUN useradd --create-home --uid 10001 moretta \
    && mkdir -p /app/data/logs /app/data/uploads \
    && chown -R moretta:moretta /app

COPY --chown=moretta:moretta . .

USER moretta

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
