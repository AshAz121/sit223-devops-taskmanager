import json
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request


app = Flask(__name__)

ALERT_FILE = Path(
    os.environ.get("ALERT_FILE", "/data/alerts.jsonl")
)


def read_saved_alerts():
    if not ALERT_FILE.exists():
        return []

    alerts = []

    for line in ALERT_FILE.read_text().splitlines():
        if line.strip():
            alerts.append(json.loads(line))

    return alerts


@app.get("/health")
def health():
    return jsonify(
        status="healthy",
        service="SIT223 Alert Receiver",
    )


@app.post("/alerts")
def receive_alert():
    payload = request.get_json(silent=True) or {}

    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "status": payload.get("status", "unknown"),
        "alerts": payload.get("alerts", []),
    }

    ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with ALERT_FILE.open("a", encoding="utf-8") as alert_log:
        alert_log.write(json.dumps(record) + "\n")

    print(json.dumps(record), flush=True)

    return jsonify(received=True), 200


@app.get("/alerts")
def list_alerts():
    return jsonify(read_saved_alerts())
