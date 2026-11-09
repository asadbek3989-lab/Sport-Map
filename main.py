import asyncio
import html
import logging
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.types.error_event import ErrorEvent
from aiogram.utils.keyboard import InlineKeyboardBuilder

import ai
import config
import db
import sheets
from texts import CHOOSE_LANG, DISTRICT_NAMES, DISTRICTS, GOAL_KEYS, LANGS, TEXTS, t

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mygym")

TZ = ZoneInfo("Asia/Tashkent")
router = Router()
LANG_CACHE: dict[int, str] = {}
AI_CALLS: dict[int, list[float]] = defaultdict(list)


class Ask(StatesGroup):
    chatting = State()


class Lead(StatesGroup):
    name = State()
    phone = State()
    goal = State()


# ---------------------------------------------------------------- yordamchilar

def esc(value) -> str:
    return html.escape(str(value or ""), quote=False)


def is_super(uid: int) -> bool:
    return uid in config.SUPER_ADMIN_IDS


async def safe(coro):
    """Statistika kabi ikkinchi darajali ishlar botni to'xtatib qo'ymasin."""
    try:
        return await coro
    except Exception:
        log.exception("Ikkinchi darajali amal xato berdi")
        return None


async def get_lang(uid: int) -> str:
    if uid not in LANG_CACHE:
        lang = await safe(db.get_lang(uid))
        LANG_CACHE[uid] = lang if lang in LANGS else "uz"
    return LANG_CACHE[uid]


def ai_allowed(uid: int) -> bool:
    now = time.time()
    calls = [x for x in AI_CALLS[uid] if now - x < 3600]
    if len(calls) >= config.AI_LIMIT_PER_HOUR:
        AI_CALLS[uid] = calls
        return False
    calls.append(now)
    AI_CALLS[uid] = calls
    return True


def contact_text(g: dict, lang: str) -> str:
    parts = []
    if g["phone"]:
        parts.append(esc(g["phone"]))
    if g["tg_username"]:
        parts.append("@" + esc(g["tg_username"]))
    return " · ".join(parts) if parts else t(lang, "no_contact")


def norm_phone(raw: str):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    if 11 <= len(digits) <= 15:
        return "+" + digits
    return None


# ---------------------------------------------------------------- klaviaturalar

def lang_kb():
    b = InlineKeyboardBuilder()
    for code, label in LANGS.items():
        b.button(text=label, callback_data=f"lang:{code}")
    b.adjust(1)
    return b.as_markup()


async def districts_kb(lang: str):
    counts = Counter(g["district_key"] for g in await sheets.get_gyms())
    b = InlineKeyboardBuilder()
    for key, names in DISTRICTS:
        n = counts.get(key, 0)
        b.button(text=names[lang] + (f" ({n})" if n else ""), callback_data=f"d:{key}")
    b.adjust(2)
    return b.as_markup()


def gym_kb(g: dict, lang: str):
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "btn_ask"), callback_data=f"ask:{g['id']}")
    b.button(text=t(lang, "btn_join"), callback_data=f"join:{g['id']}")
    if g["free_trial"]:
        b.button(text=t(lang, "btn_trial"), callback_data=f"trial:{g['id']}")
    b.adjust(2, 1)
    return b.as_markup()


def after_answer_kb(gym_id: str, lang: str):
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "btn_join"), callback_data=f"join:{gym_id}")
    b.button(text=t(lang, "btn_menu"), callback_data="menu")
    b.adjust(2)
    return b.as_markup()


def back_kb(lang: str):
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "back_districts"), callback_data="menu")
    return b.as_markup()


def goals_kb(lang: str):
    b = InlineKeyboardBuilder()
    for key in GOAL_KEYS:
        b.button(text=t(lang, f"goal_{key}"), callback_data=f"goal:{key}")
    b.adjust(2)
    return b.as_markup()


# ---------------------------------------------------------------- zal kartochkasi

def gym_card(g: dict, lang: str) -> str:
    lines = [f"🏋️ <b>{esc(g['name'])}</b>"]
    if g["address"]:
        lines.append(f"{t(lang, 'lbl_address')}: {esc(g['address'])}")
    if g["hours"]:
        lines.append(f"{t(lang, 'lbl_hours')}: {esc(g['hours'])}")
    if g["prices"]:
        lines.append(f"{t(lang, 'lbl_prices')}: {esc(g['prices'])}")
    if g["amenities"]:
        lines.append(f"{t(lang, 'lbl_amenities')}: {esc(g['amenities'])}")
    if g["phone"] or g["tg_username"]:
        lines.append(f"{t(lang, 'lbl_phone')}: {contact_text(g, lang)}")
    if g["free_trial"]:
        lines.append(t(lang, "lbl_trial"))
    if g["notes"]:
        lines.append(f"ℹ️ {esc(g['notes'])}")
    return "\n".join(lines)


async def send_gym(bot: Bot, chat_id: int, g: dict, lang: str):
    if g["photos"]:
        try:
            if len(g["photos"]) == 1:
                await bot.send_photo(chat_id, g["photos"][0])
            else:
                await bot.send_media_group(
                    chat_id, [InputMediaPhoto(media=p) for p in g["photos"][:10]]
                )
        except Exception:
            log.warning("Rasm yuborilmadi (zal %s): havola/file_id ni tekshiring", g["id"])
    if g["lat"] is not None and g["lon"] is not None:
        try:
            await bot.send_location(chat_id, g["lat"], g["lon"])
        except Exception:
            log.warning("Lokatsiya yuborilmadi (zal %s)", g["id"])
    await bot.send_message(chat_id, gym_card(g, lang), reply_markup=gym_kb(g, lang))
    await safe(db.inc_stat(g["id"], "views"))


# ---------------------------------------------------------------- buyruqlar

@router.message(CommandStart())
async def cmd_start(msg: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    source = re.sub(r"[^A-Za-z0-9_-]", "", command.args or "")[:40] or "direct"
    u = msg.from_user
    await safe(db.upsert_user(u.id, u.first_name, u.username, source))
    await msg.answer(CHOOSE_LANG, reply_markup=lang_kb())


@router.message(Command("language"))
async def cmd_language(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(CHOOSE_LANG, reply_markup=lang_kb())


@router.message(Command("menu"))
async def cmd_menu(msg: Message, state: FSMContext):
    await state.clear()
    lang = await get_lang(msg.from_user.id)
    await msg.answer(t(lang, "pick_district"), reply_markup=await districts_kb(lang))


@router.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    lang = await get_lang(msg.from_user.id)
    await msg.answer(t(lang, "cancelled"), reply_markup=ReplyKeyboardRemove())
    await msg.answer(t(lang, "pick_district"), reply_markup=await districts_kb(lang))


@router.message(Command("id"))
async def cmd_id(msg: Message):
    await msg.answer(f"Telegram ID: <code>{msg.from_user.id}</code>")


@router.message(Command("reload"))
async def cmd_reload(msg: Message):
    if not is_super(msg.from_user.id):
        return
    gyms = await sheets.get_gyms(force=True)
    await msg.answer(f"♻️ Jadval qayta o'qildi. Faol zallar: {len(gyms)}")


@router.message(Command("gyms"))
async def cmd_gyms(msg: Message):
    if not is_super(msg.from_user.id):
        return
    gyms = await sheets.get_gyms(force=True)
    if not gyms:
        await msg.answer("Faol zallar yo'q (yoki jadvalni o'qib bo'lmadi, loglarni tekshiring).")
        return
    lines = ["🏋️ <b>Faol zallar</b>"]
    for g in gyms:
        warn = []
        if not g["owner_tg_id"]:
            warn.append("owner_tg_id yo'q")
        if not g["photos"]:
            warn.append("rasm yo'q")
        if g["lat"] is None:
            warn.append("lokatsiya yo'q")
        lines.append(
            f"• <code>{esc(g['id'])}</code> {esc(g['name'])} ({esc(g['district'])})"
            + (f" ⚠️ {', '.join(warn)}" if warn else "")
        )
    await msg.answer("\n".join(lines))


def _fmt_dt(dt) -> str:
    try:
        return dt.astimezone(TZ).strftime("%d.%m %H:%M")
    except Exception:
        return "-"


def _lead_line(x: dict, with_gym: bool) -> str:
    gym = f"{esc(x.get('gym_name'))} | " if with_gym else ""
    trial = " 🎁" if x.get("type") == "trial" else ""
    return (
        f"• {_fmt_dt(x.get('created_at'))} | {gym}{esc(x.get('name'))} | "
        f"{esc(x.get('phone'))} | {esc(x.get('goal'))}{trial}"
    )


@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    if not is_super(msg.from_user.id):
        return
    ov = await db.overview()
    stats = await db.gym_stats()
    names = {g["id"]: g["name"] for g in await sheets.get_gyms()}
    lines = [
        "📊 <b>My Gym statistikasi</b>",
        f"👥 Foydalanuvchilar: {ov['users']}",
        f"📝 Leadlar: {ov['leads']} (bugun: {ov['leads_today']}, 7 kun: {ov['leads_7d']})",
    ]
    if ov["sources"]:
        src = ", ".join(f"{esc(k)}: {v}" for k, v in sorted(ov["sources"].items(), key=lambda x: -x[1]))
        lines.append(f"📣 Manbalar: {src}")
    if stats:
        lines.append("\n<b>Zallar bo'yicha</b> (👁 ko'rildi / ❓ savol / 📝 lead / 🎁 sinov)")
        for gid, s in sorted(stats.items(), key=lambda x: -x[1].get("leads", 0)):
            lines.append(
                f"• {esc(names.get(gid, gid))}: {s.get('views', 0)} / {s.get('questions', 0)} / "
                f"{s.get('leads', 0)} / {s.get('trials', 0)}"
            )
    await msg.answer("\n".join(lines))


async def _owner_gyms(uid: int) -> list[dict]:
    return [g for g in await sheets.get_gyms() if g["owner_tg_id"] == uid]


@router.message(Command("mystats"))
async def cmd_mystats(msg: Message):
    mine = await _owner_gyms(msg.from_user.id)
    if not mine:
        return
    stats = await db.gym_stats()
    lines = ["📊 <b>Zalingiz statistikasi</b>"]
    for g in mine:
        s = stats.get(g["id"], {})
        lines.append(
            f"\n🏋️ <b>{esc(g['name'])}</b>\n"
            f"👁 Ko'rildi: {s.get('views', 0)}\n❓ Savollar: {s.get('questions', 0)}\n"
            f"📝 Leadlar: {s.get('leads', 0)}\n🎁 Sinovga yozilganlar: {s.get('trials', 0)}"
        )
    await msg.answer("\n".join(lines))


@router.message(Command("leads"))
async def cmd_leads(msg: Message):
    uid = msg.from_user.id
    if is_super(uid):
        items = await db.recent_leads(None, 10)
        with_gym = True
    else:
        mine = await _owner_gyms(uid)
        if not mine:
            return
        items = await db.recent_leads([g["id"] for g in mine], 10)
        with_gym = len(mine) > 1
    if not items:
        await msg.answer("Hozircha leadlar yo'q.")
        return
    await msg.answer("📝 <b>So'nggi leadlar</b>\n" + "\n".join(_lead_line(x, with_gym) for x in items))


@router.message(F.photo, F.from_user.id.in_(config.SUPER_ADMIN_IDS))
async def admin_photo(msg: Message):
    """Super admin rasm yuborsa, jadvalga qo'yish uchun file_id qaytaramiz."""
    file_id = msg.photo[-1].file_id
    await msg.answer(
        "Jadvalning <b>photos</b> ustuniga shuni qo'ying (bir nechta bo'lsa | bilan ajrating):\n"
        f"<code>{file_id}</code>"
    )


# ---------------------------------------------------------------- til va tuman

@router.callback_query(F.data.startswith("lang:"))
async def on_lang(cb: CallbackQuery, state: FSMContext):
    lang = cb.data.split(":", 1)[1]
    if lang not in LANGS:
        await cb.answer()
        return
    LANG_CACHE[cb.from_user.id] = lang
    await safe(db.set_lang(cb.from_user.id, lang))
    await state.clear()
    kb = await districts_kb(lang)
    try:
        await cb.message.edit_text(t(lang, "welcome"), reply_markup=kb)
    except Exception:
        await cb.message.answer(t(lang, "welcome"), reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data == "menu")
async def on_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = await get_lang(cb.from_user.id)
    await cb.message.answer(t(lang, "pick_district"), reply_markup=await districts_kb(lang))
    await cb.answer()


@router.callback_query(F.data.startswith("d:"))
async def on_district(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = await get_lang(cb.from_user.id)
    key = cb.data.split(":", 1)[1]
    gyms = [g for g in await sheets.get_gyms() if g["district_key"] == key]
    if not gyms:
        await cb.answer(t(lang, "no_gyms"), show_alert=True)
        return
    await cb.answer()
    dname = DISTRICT_NAMES.get(key, {}).get(lang, key)
    await cb.message.answer(t(lang, "gyms_in", district=esc(dname)))
    for g in gyms:
        await send_gym(cb.bot, cb.message.chat.id, g, lang)
        await asyncio.sleep(0.3)
    await cb.message.answer(t(lang, "gyms_footer"), reply_markup=back_kb(lang))


# ---------------------------------------------------------------- savol-javob (AI)

@router.callback_query(F.data.startswith("ask:"))
async def on_ask(cb: CallbackQuery, state: FSMContext):
    lang = await get_lang(cb.from_user.id)
    gym = await sheets.get_gym(cb.data.split(":", 1)[1])
    if not gym:
        await cb.answer(t(lang, "gym_missing"), show_alert=True)
        return
    await state.set_state(Ask.chatting)
    await state.update_data(gym_id=gym["id"], history=[])
    await cb.message.answer(
        t(lang, "ask_prompt", gym=esc(gym["name"])), reply_markup=after_answer_kb(gym["id"], lang)
    )
    await cb.answer()


@router.message(Ask.chatting, F.text)
async def on_question(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    lang = await get_lang(uid)
    data = await state.get_data()
    gym = await sheets.get_gym(data.get("gym_id", ""))
    if not gym:
        await state.clear()
        await msg.answer(t(lang, "gym_missing"))
        return
    if not ai_allowed(uid):
        await msg.answer(t(lang, "too_many"))
        return

    question = msg.text.strip()[:500]
    await msg.bot.send_chat_action(msg.chat.id, "typing")
    history = data.get("history", [])
    try:
        reply = await ai.answer(gym, question, lang, history)
    except Exception:
        log.exception("Gemini xatosi")
        await msg.answer(t(lang, "ai_error"))
        return

    await safe(db.inc_stat(gym["id"], "questions"))
    if not reply or reply.strip().startswith("NO_INFO"):
        await msg.answer(
            t(lang, "no_info", contact=contact_text(gym, lang)),
            reply_markup=after_answer_kb(gym["id"], lang),
        )
        return

    history += [{"role": "user", "text": question}, {"role": "model", "text": reply}]
    await state.update_data(history=history[-8:])
    await msg.answer(reply, parse_mode=None, reply_markup=after_answer_kb(gym["id"], lang))


# ---------------------------------------------------------------- yozilish (lead)

@router.callback_query(F.data.regexp(r"^(join|trial):"))
async def on_join(cb: CallbackQuery, state: FSMContext):
    lang = await get_lang(cb.from_user.id)
    kind, gym_id = cb.data.split(":", 1)
    gym = await sheets.get_gym(gym_id)
    if not gym:
        await cb.answer(t(lang, "gym_missing"), show_alert=True)
        return
    await state.clear()
    await state.set_state(Lead.name)
    await state.update_data(gym_id=gym_id, trial=(kind == "trial" and gym["free_trial"]))
    await cb.message.answer(t(lang, "ask_name"))
    await cb.answer()


@router.message(Lead.name, F.text)
async def lead_name(msg: Message, state: FSMContext):
    lang = await get_lang(msg.from_user.id)
    name = msg.text.strip()[:60]
    if len(name) < 2:
        await msg.answer(t(lang, "bad_name"))
        return
    await state.update_data(name=name)
    await state.set_state(Lead.phone)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "btn_share_phone"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await msg.answer(t(lang, "ask_phone"), reply_markup=kb)


async def _take_phone(msg: Message, state: FSMContext, raw: str):
    lang = await get_lang(msg.from_user.id)
    phone = norm_phone(raw)
    if not phone:
        await msg.answer(t(lang, "bad_phone"))
        return
    await state.update_data(phone=phone)
    await state.set_state(Lead.goal)
    await msg.answer("✅", reply_markup=ReplyKeyboardRemove())
    await msg.answer(t(lang, "ask_goal"), reply_markup=goals_kb(lang))


@router.message(Lead.phone, F.contact)
async def lead_phone_contact(msg: Message, state: FSMContext):
    await _take_phone(msg, state, msg.contact.phone_number)


@router.message(Lead.phone, F.text)
async def lead_phone_text(msg: Message, state: FSMContext):
    await _take_phone(msg, state, msg.text)


@router.callback_query(Lead.goal, F.data.startswith("goal:"))
async def lead_goal(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    lang = await get_lang(uid)
    goal_key = cb.data.split(":", 1)[1]
    if goal_key not in GOAL_KEYS:
        await cb.answer()
        return
    data = await state.get_data()
    await state.clear()
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.answer()

    gym = await sheets.get_gym(data.get("gym_id", ""))
    if not gym:
        await cb.message.answer(t(lang, "gym_missing"))
        return

    trial = bool(data.get("trial"))
    goal_uz = TEXTS["uz"][f"goal_{goal_key}"]
    source = await safe(db.user_source(uid)) or "direct"
    u = cb.from_user
    lead = {
        "gym_id": gym["id"],
        "gym_name": gym["name"],
        "name": data.get("name", ""),
        "phone": data.get("phone", ""),
        "goal": goal_uz,
        "type": "trial" if trial else "join",
        "lang": lang,
        "source": source,
        "tg_id": uid,
        "tg_username": u.username or "",
    }
    await safe(db.save_lead(lead))
    await safe(db.inc_stat(gym["id"], "leads"))
    if trial:
        await safe(db.inc_stat(gym["id"], "trials"))
    await safe(
        sheets.append_lead([
            datetime.now(TZ).strftime("%Y-%m-%d %H:%M"), gym["id"], gym["name"], lead["name"],
            lead["phone"], goal_uz, lead["type"], lang, source, str(uid), lead["tg_username"],
        ])
    )
    await notify_owner(cb.bot, gym, lead)

    key = "done_trial" if trial else "done"
    await cb.message.answer(
        t(lang, key, name=esc(lead["name"]), gym=esc(gym["name"])),
        reply_markup=await _menu_kb(lang),
    )


async def _menu_kb(lang: str):
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "btn_menu"), callback_data="menu")
    return b.as_markup()


async def notify_owner(bot: Bot, gym: dict, lead: dict):
    who = f'<a href="tg://user?id={lead["tg_id"]}">profil</a>'
    if lead["tg_username"]:
        who = f"@{esc(lead['tg_username'])}"
    text = (
        "🔔 <b>Yangi lead!</b>\n"
        f"🏋️ Zal: {esc(gym['name'])}\n"
        f"👤 Ism: {esc(lead['name'])}\n"
        f"📱 Telefon: {esc(lead['phone'])}\n"
        f"🎯 Maqsad: {esc(lead['goal'])}\n"
        + ("🎁 Bepul sinovga yozildi\n" if lead["type"] == "trial" else "")
        + f"🌐 Til: {lead['lang']}\n📣 Manba: {esc(lead['source'])}\n🔗 Telegram: {who}"
    )
    recipients = set()
    if gym["owner_tg_id"]:
        recipients.add(gym["owner_tg_id"])
    if config.NOTIFY_SUPER_ADMINS or not recipients:
        recipients |= config.SUPER_ADMIN_IDS
    for rid in recipients:
        try:
            await bot.send_message(rid, text)
        except Exception:
            log.warning("Xabar yuborilmadi (id=%s). U botga /start bosganmi?", rid)


# ---------------------------------------------------------------- qolgan xabarlar

@router.message(StateFilter(None), F.text)
async def fallback(msg: Message):
    lang = await get_lang(msg.from_user.id)
    await msg.answer(t(lang, "help_choose"), reply_markup=await districts_kb(lang))


async def main():
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    @dp.errors()
    async def on_error(event: ErrorEvent):
        log.exception("Handlerda xato: %s", event.exception)
        return True

    await bot.delete_webhook(drop_pending_updates=True)
    gyms = await sheets.get_gyms(force=True)
    log.info("Faol zallar soni: %d", len(gyms))
    await bot.set_my_commands([
        BotCommand(command="start", description="Boshlash / Start"),
        BotCommand(command="menu", description="Tumanlar / Districts"),
        BotCommand(command="language", description="Til / Language"),
    ])
    log.info("My Gym bot ishga tushdi")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
