"""
Free Replit instances sleep after inactivity. This tiny Flask server gives
an external uptime pinger (e.g. UptimeRobot, free tier) something to hit
every few minutes to keep the Repl awake. Not needed if you're on a paid
Replit "Always On" plan — see README.
"""
from flask import Flask
from threading import Thread

app = Flask(__name__)


@app.route("/")
def home():
    return "CreateHaven cohort bot is alive."


def run():
    app.run(host="0.0.0.0", port=8080)


def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
