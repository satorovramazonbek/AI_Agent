"""Telegram interfeysi: faqat egasidan kelgan xabarlarni qabul qiladi.

Matn, ovozli xabar va lokatsiya qabul qilinadi. Javobga qarab qo'shimchalar yuboriladi:
lokatsiya pini + navigatsiya tugmalari, «📍 Joylashuvni yuborish» tugmasi, tasdiqlash tugmalari.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from jarvis.config import get_settings
from jarvis.core import commands
from jarvis.core.commands import HELP
from jarvis.security.policy import CommandPolicy
from jarvis.tools.places import Place
from jarvis.voice.intents import handle_text, status_text
from jarvis.voice.stt import VoiceUnavailable, get_transcriber

log = logging.getLogger(__name__)
MAX_LEN = 4000

CONFIRM_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, bajar", callback_data="confirm"),
            InlineKeyboardButton(text="❌ Yo'q", callback_data="cancel"),
        ]
    ]
)
LOCATION_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📍 Joylashuvni yuborish", request_location=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


def session_of(chat_id: int) -> str:
    return f"tg:{chat_id}"


def nav_keyboard(lat: float, lon: float, name: str) -> InlineKeyboardMarkup:
    p = Place(name, lat, lon, "")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🧭 Google Maps", url=p.google),
                InlineKeyboardButton(text="🧭 Yandex", url=p.yandex),
            ],
            [InlineKeyboardButton(text="🍎 Apple Maps", url=f"https://maps.apple.com/?daddr={lat},{lon}")],
        ]
    )


async def send_reply(bot: Bot, chat_id: int, text: str) -> None:
    """Javob matni + buyruq qoldirgan qo'shimchalar (pin, tugmalar)."""
    session = session_of(chat_id)
    extras = commands.pop_extras(session)
    markup = None
    if commands.pending(session):
        markup = CONFIRM_KB
    elif any(e[0] == "request_location" for e in extras):
        markup = LOCATION_KB
    elif any(e[0] == "done" for e in extras):
        markup = ReplyKeyboardRemove()
    await bot.send_message(chat_id, text[:MAX_LEN], reply_markup=markup)
    for e in extras:
        if e[0] == "location":
            _, lat, lon, name = e
            await bot.send_location(chat_id, lat, lon, reply_markup=nav_keyboard(lat, lon, name))


def build_dispatcher(owner_id: int) -> Dispatcher:
    dp = Dispatcher()
    # Egasi bo'lmaganlarning xabarlari va tugma bosishlari jim e'tiborsiz qoldiriladi.
    dp.message.filter(F.from_user.id == owner_id)
    dp.callback_query.filter(F.from_user.id == owner_id)

    @dp.message(Command("start"))
    async def start(message: Message) -> None:
        await message.answer(
            "JARVIS ishga tushdi. Yozing, ovozli xabar yoki lokatsiya yuboring.\n\n"
            f"{HELP}\n\nQo'shimcha: /status, /check <buyruq>"
        )

    @dp.message(Command("status"))
    async def status(message: Message) -> None:
        await message.answer(await status_text())

    @dp.message(Command("check"))
    async def check(message: Message) -> None:
        cmd = (message.text or "").partition(" ")[2]
        policy = CommandPolicy.from_file(get_settings().policy_file)
        r = policy.check(cmd, remote=True)
        await message.answer(f"{r.decision.upper()} ({r.risk.name})\n" + "\n".join(r.reasons))

    @dp.message(F.location)
    async def location(message: Message, bot: Bot) -> None:
        loc = message.location
        reply = commands.on_location(session_of(message.chat.id), loc.latitude, loc.longitude)
        await send_reply(bot, message.chat.id, reply)

    @dp.message(F.voice | F.audio)
    async def voice(message: Message, bot: Bot) -> None:
        media = message.voice or message.audio
        limit = get_settings().voice_max_seconds
        if media.duration and media.duration > limit:
            await message.answer(f"Ovozli xabar juda uzun (maksimum {limit} soniya).")
            return
        await bot.send_chat_action(message.chat.id, "typing")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice.ogg"
            await bot.download(media, destination=path)
            try:
                t = await get_transcriber().transcribe(path)
            except VoiceUnavailable as e:
                await message.answer(f"Ovoz moduli ishlamayapti: {e}")
                return
        mark = f" (?) — ishonch {t.confidence:.0%}" if t.unsure else ""
        await message.answer(f"🎙 {t.text or '(eshitilmadi)'}{mark}")
        reply = await handle_text(t.text, session_of(message.chat.id))
        await send_reply(bot, message.chat.id, reply)

    @dp.callback_query(F.data.in_({"confirm", "cancel"}))
    async def decide(query: CallbackQuery, bot: Bot) -> None:
        session = session_of(query.message.chat.id)
        if query.data == "confirm":
            result = await commands.confirm(session)
        else:
            result = await commands.cancel(session)
        await query.answer()
        await query.message.edit_reply_markup(reply_markup=None)  # tugmalar qayta bosilmasin
        await send_reply(bot, query.message.chat.id, result)

    @dp.message()
    async def fallback(message: Message, bot: Bot) -> None:
        if not message.text:
            await message.answer("Matn, ovozli xabar yoki lokatsiya yuboring.")
            return
        await bot.send_chat_action(message.chat.id, "typing")
        reply = await handle_text(message.text, session_of(message.chat.id))
        await send_reply(bot, message.chat.id, reply)

    return dp


async def run_bot() -> None:
    settings = get_settings()
    if not settings.telegram_token or not settings.owner_telegram_id:
        log.warning("JARVIS_TELEGRAM_TOKEN yoki JARVIS_OWNER_TELEGRAM_ID yo'q — bot o'chirilgan")
        return
    bot = Bot(settings.telegram_token)
    await build_dispatcher(settings.owner_telegram_id).start_polling(bot)
