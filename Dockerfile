FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY requirements.txt .

RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --upgrade pip \
    && /opt/venv/bin/python -m pip install -r requirements.txt


FROM python:3.13-slim

ARG APP_VERSION=dev

LABEL org.opencontainers.image.title="SIT223 DevOps Task Manager" \
      org.opencontainers.image.description="Flask task management application built through Jenkins" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION="${APP_VERSION}" \
    DATABASE="/app/data/taskmanager.db"

RUN useradd \
    --system \
    --uid 10001 \
    --create-home \
    --home-dir /app \
    --shell /usr/sbin/nologin \
    appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY app.py schema.sql ./
COPY templates ./templates
COPY static ./static

RUN mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

HEALTHCHECK \
    --interval=10s \
    --timeout=3s \
    --start-period=10s \
    --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=2)"

CMD ["gunicorn", "--workers", "2", "--threads", "2", "--bind", "0.0.0.0:5000", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
