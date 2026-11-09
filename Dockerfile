FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts

# Non-root runtime user; local-storage fallback directory is writable by it.
RUN useradd --system --uid 10001 appuser \
    && mkdir -p /srv/var/storage \
    && chown -R appuser /srv/var
USER appuser

EXPOSE 8000
# Render injects $PORT; default 8000 for docker compose / local use.
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
