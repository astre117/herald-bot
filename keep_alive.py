"""
Tiny web server. It keeps the service reachable and receives Flutterwave
payment webhooks.
"""
import logging
import os
import json
from threading import Thread

from flask import Flask, request

import payments

app = Flask(__name__)


@app.route("/")
def home():
    return "CreateHaven cohort bot is alive."


@app.route("/flutterwave-webhook", methods=["POST"])
def flutterwave_webhook():
    raw = request.get_data()

    if not payments.signature_ok(request.headers, raw):
        return "forbidden", 401

    try:
        payload = json.loads(raw)
    except ValueError:
        return "bad request", 400

    try:
        payments.process_webhook(payload)
    except Exception:
        logging.exception("Flutterwave webhook failed")
        return "error", 500  # makes Flutterwave retry later

    return "ok", 200


def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
