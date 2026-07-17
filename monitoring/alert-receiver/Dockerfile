FROM python:3.13-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd \
    --system \
    --uid 10002 \
    --create-home \
    --home-dir /app \
    --shell /usr/sbin/nologin \
    receiver

WORKDIR /app

COPY requirements.txt .

RUN python -m pip install -r requirements.txt

COPY app.py .

RUN mkdir -p /data \
    && chown -R receiver:receiver /app /data

USER receiver

EXPOSE 5001

HEALTHCHECK \
    --interval=10s \
    --timeout=3s \
    --start-period=5s \
    --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/health', timeout=2)"

CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "1", "--threads", "2", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
