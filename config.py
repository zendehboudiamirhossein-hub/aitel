import os
from dotenv import load_dotenv

load_dotenv()


def _split_ids(raw: str):
    ids = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = _split_ids(os.getenv("ADMIN_IDS", ""))

ANYMODEL_API_KEY = os.getenv("ANYMODEL_API_KEY", "")
ANYMODEL_BASE_URL = os.getenv("ANYMODEL_BASE_URL", "https://anymodel.org/v1").rstrip("/")

ANYMODEL_CHAT_MODEL = os.getenv("ANYMODEL_CHAT_MODEL", "gpt-5.6-sol")
ANYMODEL_IMAGE_MODEL = os.getenv("ANYMODEL_IMAGE_MODEL", "gpt-image-1")
ANYMODEL_STT_MODEL = os.getenv("ANYMODEL_STT_MODEL", "whisper-1")
ANYMODEL_TTS_MODEL = os.getenv("ANYMODEL_TTS_MODEL", "tts-1")
ANYMODEL_TTS_VOICE = os.getenv("ANYMODEL_TTS_VOICE", "alloy")

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

PORT = int(os.getenv("PORT", "8080"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/bot.db")
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "20"))

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful, friendly AI assistant inside a Telegram bot. "
    "Reply in the same language the user writes in. Keep answers clear and well formatted for Telegram."
)

AVAILABLE_CHAT_MODELS = [
    m.strip() for m in os.getenv(
        "AVAILABLE_CHAT_MODELS",
        "gpt-5.6-sol,gpt-5.5,claude-opus-4.8,gemini-3.1-pro,deepseek-v3.2"
    ).split(",") if m.strip()
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "assets", "fonts", "Vazirmatn-Regular.ttf")
