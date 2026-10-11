# Use a stage to fetch the uv binary for maximum efficiency
FROM ghcr.io/astral-sh/uv:0.9.27 AS uv_bin

# Use Python 3.12 slim for stability and wheel compatibility
FROM python:3.12.12-slim-bookworm

# Copy uv binaries from the official image
COPY --from=uv_bin /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=300

# Install system dependencies (including runtime libs for OpenCV/MediaPipe)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libpq5 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Copy requirements first to leverage Docker layer caching
COPY --chown=appuser:appuser requirements.txt .

# Install dependencies using uv with a persistent cache mount
RUN --mount=type=cache,target=/root/.cache/uv \
    python -m pip install --upgrade pip &&uv pip install --system --index-strategy unsafe-best-match -r requirements.txt

# Purge build-only dependencies and clean up to minimize image size
RUN apt-get purge -y --auto-remove build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the rest of the application code
COPY --chown=appuser:appuser . .

# Switch to the non-root user
USER appuser

# Expose the application port
EXPOSE 5000

# Run the flask application
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

CMD ["python", "-m", "main"]
