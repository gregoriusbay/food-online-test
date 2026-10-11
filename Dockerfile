# Backend image: Flask API (extraction, embeddings, agent). Built from the repo root:
#   docker build -t receipt-backend .
# The vision/embedding models are NOT in the image: the app talks to an Ollama server
# (OLLAMA_HOST, default http://host.docker.internal:11434 via docker-compose).
FROM python:3.12.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Non-root user; the uploads folder must be writable by it
RUN useradd -m -u 1000 appuser && mkdir -p /app/uploads && chown appuser:appuser /app/uploads

# Dependencies first so this layer is cached between code changes
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# Code stays owned by root (read-only for appuser); only /app/uploads is writable
COPY backend/*.py ./

USER appuser
EXPOSE 5000

# 1 worker + threads: requests mostly wait on Ollama; long timeout because
# extraction on CPU can take several minutes.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "900", "api:app"]
