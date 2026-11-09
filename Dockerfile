# syntax=docker/dockerfile:1
FROM python:3.13-slim

WORKDIR /app

# System libraries reflex may need at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libstdc++6 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Dependency metadata first, for better layer caching.
COPY pyproject.toml tox.ini ./

# Application source needed for the editable install to register packages.
COPY rxconfig.py app.py ./
COPY src/ ./src/

# Install the package and its runtime dependencies.
RUN pip install --no-cache-dir -e .

# Non-root user for runtime.
RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /app/data && chown appuser:appuser /app/data && \
    chown -R appuser:appuser /app
USER appuser

# Reflex web UI port.
EXPOSE 8080

# `python -m reflex run` boots the UI; `build_app()` in app.py starts the
# Discord bridge in a daemon thread on app init (best-effort).
# `data/` holds ./data/app.sqlite (the SQLite default path) and is mounted
# as a volume by docker-compose.
CMD ["python", "-m", "reflex", "run", "--env", "prod", "--host", "0.0.0.0", "--port", "8080"]
