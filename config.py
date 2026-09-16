import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANNOUNCEMENT_CHAT_ID = os.environ.get("ANNOUNCEMENT_CHAT_ID")
ANNOUNCEMENT_TOPIC_ID = os.environ.get("ANNOUNCEMENT_TOPIC_ID")
ANNOUNCEMENT_TOPIC_ID = int(ANNOUNCEMENT_TOPIC_ID) if ANNOUNCEMENT_TOPIC_ID else None
RESOURCE_TOPIC_ID = os.environ.get("RESOURCE_TOPIC_ID")
RESOURCE_TOPIC_ID = int(RESOURCE_TOPIC_ID) if RESOURCE_TOPIC_ID else None
WINS_TOPIC_ID = os.environ.get("WINS_TOPIC_ID")
WINS_TOPIC_ID = int(WINS_TOPIC_ID) if WINS_TOPIC_ID else None
ADMIN_NOTIFY_CHAT_ID = os.environ.get("ADMIN_NOTIFY_CHAT_ID")

ADMIN_USER_IDS = {
    int(uid.strip())
    for uid in os.environ.get("ADMIN_USER_IDS", "").split(",")
    if uid.strip().isdigit()
}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS
