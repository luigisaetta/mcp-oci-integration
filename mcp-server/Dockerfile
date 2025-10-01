# ---- build stage (to isolate deps if you add extras later) ----
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System updates + runtime deps (keep minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl tini && \
    rm -rf /var/lib/apt/lists/*

# Create app user and dir
RUN useradd -m -u 10001 appuser
WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY app.py config.py ./

# Expose only for streamable-http mode
EXPOSE 8080

# Healthcheck (simple TCP hit if HTTP mode)
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD sh -c 'test "${TRANSPORT}" = "streamable-http" && nc -z localhost ${PORT:-8080} || exit 0'

# Drop privileges
USER appuser

# Entrypoint via tini for signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default command: streamable-http (override as needed)
CMD ["python", "app.py"]

