import json
import os

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"'{name}' to'ldirilmagan. .env faylini (yoki Railway Variables) tekshiring.")
    return value


BOT_TOKEN = _required("BOT_TOKEN")
GEMINI_API_KEY = _required("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
SHEET_ID = _required("SHEET_ID")

SUPER_ADMIN_IDS = {
    int(x) for x in os.getenv("SUPER_ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()
}
NOTIFY_SUPER_ADMINS = os.getenv("NOTIFY_SUPER_ADMINS", "1") == "1"

SHEET_CACHE_SECONDS = int(os.getenv("SHEET_CACHE_SECONDS", "60"))
AI_LIMIT_PER_HOUR = int(os.getenv("AI_LIMIT_PER_HOUR", "20"))


def google_credentials() -> dict:
    """Service account ma'lumotlari: JSON matn (Railway) yoki fayl (kompyuter)."""
    raw = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
    if raw:
        return json.loads(raw)
    path = os.getenv("GOOGLE_CREDENTIALS_FILE", "service-account.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)
