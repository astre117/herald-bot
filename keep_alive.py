"""
Tiny web server so the service stays reachable.
"""
import os
from threading import Thread

from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return "CreateHaven cohort bot is alive."


def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
