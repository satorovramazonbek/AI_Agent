"""Telegram interfeysi: faqat egasidan kelgan xabarlarni qabul qiladi."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from jarvis.config import get_settings
from jarvis.security.policy import CommandPolicy
from jarvis.voice.intents import handle_text, status_text
from jarvis.voice.stt import VoiceUnavailable, get_transcriber

log = logging.getLogger(__name__)


def build_dispatcher(owner_id: int) -> Dispatcher:
    dp = Dispatcher()
    # Egasi bo'lmaganlarning xabarlari jim e'tiborsiz qoldiriladi.
    dp.message.filter(F.from_user.id == owner_id)

    @dp.message(Command("start"))
    async def start(message: Message) -> None:
        await message.answer(
            "JARVIS ishga tushdi. Buyruqlar: /status, /check <buyruq>.\n"
            "Ovozli xabar ham yuborishingiz mumkin."
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
        await message.answer(f"🎙 {t.text or '(eshitilmadi)'}")
        await message.answer(await handle_text(t.text, f"tg:{message.chat.id}"))

    @dp.message()
    async def fallback(message: Message, bot: Bot) -> None:
        if not message.text:
            await message.answer("Hozircha matn va ovozli xabarlarni tushunaman.")
            return
        await bot.send_chat_action(message.chat.id, "typing")
        await message.answer(await handle_text(message.text, f"tg:{message.chat.id}"))

    return dp


async def run_bot() -> None:
    settings = get_settings()
    if not settings.telegram_token or not settings.owner_telegram_id:
        log.warning("JARVIS_TELEGRAM_TOKEN yoki JARVIS_OWNER_TELEGRAM_ID yo'q — bot o'chirilgan")
        return
    bot = Bot(settings.telegram_token)
    await build_dispatcher(settings.owner_telegram_id).start_polling(bot)
