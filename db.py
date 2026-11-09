"""Firebase Firestore: foydalanuvchilar, leadlar, statistika."""
import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

import config

TZ = ZoneInfo("Asia/Tashkent")
_db = None


def _client():
    global _db
    if _db is None:
        firebase_admin.initialize_app(credentials.Certificate(config.google_credentials()))
        _db = firestore.client()
    return _db


def _now():
    return datetime.now(timezone.utc)


# ---------- sinxron ichki funksiyalar ----------

def _upsert_user(uid, first_name, username, source):
    ref = _client().collection("users").document(str(uid))
    snap = ref.get()
    if snap.exists:
        ref.update({"first_name": first_name, "username": username, "last_seen": _now()})
    else:
        ref.set({
            "first_name": first_name, "username": username, "source": source,
            "lang": None, "created_at": _now(), "last_seen": _now(),
        })


def _set_lang(uid, lang):
    _client().collection("users").document(str(uid)).set({"lang": lang}, merge=True)


def _get_lang(uid):
    snap = _client().collection("users").document(str(uid)).get()
    return (snap.to_dict() or {}).get("lang") if snap.exists else None


def _user_source(uid):
    snap = _client().collection("users").document(str(uid)).get()
    return (snap.to_dict() or {}).get("source", "direct") if snap.exists else "direct"


def _save_lead(data):
    ref = _client().collection("leads").document()
    ref.set({**data, "created_at": _now()})
    return ref.id


def _inc_stat(gym_id, field):
    _client().collection("gym_stats").document(gym_id).set(
        {field: firestore.Increment(1)}, merge=True
    )


def _gym_stats():
    return {d.id: d.to_dict() for d in _client().collection("gym_stats").stream()}


def _recent_leads(gym_ids, limit):
    col = _client().collection("leads")
    if gym_ids is None:
        docs = col.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit).stream()
        return [d.to_dict() for d in docs]
    items = []
    for gid in gym_ids:
        q = col.where(filter=FieldFilter("gym_id", "==", gid)).limit(200)
        items.extend(d.to_dict() for d in q.stream())
    items.sort(key=lambda x: x.get("created_at"), reverse=True)
    return items[:limit]


def _overview():
    c = _client()
    users = [d.to_dict() for d in c.collection("users").select(["source"]).stream()]
    sources = Counter((u or {}).get("source", "direct") for u in users)
    leads_col = c.collection("leads")
    total_leads = sum(1 for _ in leads_col.select([]).stream())
    start_today = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    start_7d = start_today - timedelta(days=6)

    def count_since(dt):
        q = leads_col.where(filter=FieldFilter("created_at", ">=", dt)).select([])
        return sum(1 for _ in q.stream())

    return {
        "users": len(users),
        "sources": dict(sources),
        "leads": total_leads,
        "leads_today": count_since(start_today),
        "leads_7d": count_since(start_7d),
    }


# ---------- async o'ramlar ----------

async def upsert_user(uid, first_name, username, source):
    await asyncio.to_thread(_upsert_user, uid, first_name, username, source)


async def set_lang(uid, lang):
    await asyncio.to_thread(_set_lang, uid, lang)


async def get_lang(uid):
    return await asyncio.to_thread(_get_lang, uid)


async def user_source(uid):
    return await asyncio.to_thread(_user_source, uid)


async def save_lead(data):
    return await asyncio.to_thread(_save_lead, data)


async def inc_stat(gym_id, field):
    await asyncio.to_thread(_inc_stat, gym_id, field)


async def gym_stats():
    return await asyncio.to_thread(_gym_stats)


async def recent_leads(gym_ids=None, limit=10):
    return await asyncio.to_thread(_recent_leads, gym_ids, limit)


async def overview():
    return await asyncio.to_thread(_overview)
