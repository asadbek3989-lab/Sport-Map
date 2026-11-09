"""Google Sheets: zallar ma'lumotini o'qish (kesh bilan) va leadlarni yozish."""
import asyncio
import logging
import re
import time

import gspread

import config

log = logging.getLogger("sheets")

GYMS_SHEET = "Zallar"
LEADS_SHEET = "Leads"
LEAD_HEADERS = [
    "date", "gym_id", "gym", "name", "phone", "goal",
    "type", "lang", "source", "tg_id", "tg_username",
]
_FALSE = {"yo'q", "yoq", "yo`q", "no", "0", "false", "нет", "n"}
_TRUE = {"ha", "yes", "1", "true", "да", "y"}

_sh = None
_cache = {"ts": 0.0, "gyms": []}
_lock = asyncio.Lock()


def _spreadsheet():
    global _sh
    if _sh is None:
        client = gspread.service_account_from_dict(config.google_credentials())
        _sh = client.open_by_key(config.SHEET_ID)
    return _sh


def district_key(value: str) -> str:
    """'Mirzo Ulug'bek tumani' -> 'mirzoulugbek'"""
    v = (value or "").lower().replace("tumani", "")
    return re.sub(r"[^a-z]", "", v)


def _to_float(value):
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _to_int(value):
    digits = re.sub(r"\D", "", str(value or ""))
    return int(digits) if digits else None


def _normalize(row: dict):
    r = {str(k).strip().lower(): str(v).strip() for k, v in row.items()}
    gym_id = r.get("id", "")
    if not gym_id or not r.get("name"):
        return None
    active_raw = r.get("active", "").lower()
    active = active_raw not in _FALSE
    return {
        "id": gym_id,
        "name": r.get("name", ""),
        "district": r.get("district", ""),
        "district_key": district_key(r.get("district", "")),
        "address": r.get("address", ""),
        "lat": _to_float(r.get("lat")),
        "lon": _to_float(r.get("lon")),
        "phone": r.get("phone", ""),
        "tg_username": r.get("tg_username", "").lstrip("@"),
        "owner_tg_id": _to_int(r.get("owner_tg_id")),
        "hours": r.get("hours", ""),
        "prices": r.get("prices", ""),
        "amenities": r.get("amenities", ""),
        "photos": [p.strip() for p in re.split(r"[|\n]+", r.get("photos", "")) if p.strip()],
        "free_trial": r.get("free_trial", "").lower() in _TRUE,
        "notes": r.get("notes", ""),
        "active": active,
    }


def _read_rows() -> list[dict]:
    ws = _spreadsheet().worksheet(GYMS_SHEET)
    return ws.get_all_records(numericise_ignore=["all"])


async def get_gyms(force: bool = False) -> list[dict]:
    async with _lock:
        fresh = (time.time() - _cache["ts"]) < config.SHEET_CACHE_SECONDS
        if fresh and not force:
            return _cache["gyms"]
        try:
            rows = await asyncio.to_thread(_read_rows)
            gyms = [g for g in (_normalize(r) for r in rows) if g and g["active"]]
            _cache["gyms"] = gyms
            _cache["ts"] = time.time()
        except Exception:
            log.exception("Zallar jadvalini o'qib bo'lmadi")
            # eski keshni ishlatib turamiz (bo'sh bo'lsa ham)
        return _cache["gyms"]


async def get_gym(gym_id: str):
    for g in await get_gyms():
        if g["id"] == gym_id:
            return g
    return None


def _append_lead(row: list):
    sh = _spreadsheet()
    try:
        ws = sh.worksheet(LEADS_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(LEADS_SHEET, rows=1000, cols=len(LEAD_HEADERS))
        ws.append_row(LEAD_HEADERS)
    ws.append_row(row, value_input_option="RAW")


async def append_lead(row: list):
    await asyncio.to_thread(_append_lead, row)
