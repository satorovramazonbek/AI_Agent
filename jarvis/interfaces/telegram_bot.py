"""Telegram interfeysi: faqat egasidan kelgan xabarlarni qabul qiladi."""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from jarvis.config import get_settings
from jarvis.security.policy import CommandPolicy
from jarvis.tools.system import NoArgs, system_status

log = logging.getLogger(__name__)


def build_dispatcher(owner_id: int) -> Dispatcher:
    dp = Dispatcher()
    # Egasi bo'lmaganlarning xabarlari jim e'tiborsiz qoldiriladi.
    dp.message.filter(F.from_user.id == owner_id)

    @dp.message(Command("start"))
    async def start(message: Message) -> None:
        await message.answer("JARVIS ishga tushdi. Buyruqlar: /status, /check <buyruq>")

    @dp.message(Command("status"))
    async def status(message: Message) -> None:
        s = await system_status(NoArgs())
        await message.answer(
            f"OT: {s['os']}\nCPU: {s['cpu_count']} yadro, yuklama {s['load_avg_1m']}\n"
            f"Disk: {s['disk_free_gb']} GB bo'sh ({s['disk_used_pct']}% band)"
        )

    @dp.message(Command("check"))
    async def check(message: Message) -> None:
        cmd = (message.text or "").partition(" ")[2]
        policy = CommandPolicy.from_file(get_settings().policy_file)
        r = policy.check(cmd, remote=True)
        await message.answer(f"{r.decision.upper()} ({r.risk.name})\n" + "\n".join(r.reasons))

    @dp.message()
    async def fallback(message: Message) -> None:
        # Keyingi bosqich: bu yerda xabar agent orkestratoriga Task sifatida uzatiladi.
        await message.answer("Qabul qilindi. Agent sikli MVP'ning keyingi bosqichida ulanadi.")

    return dp


async def run_bot() -> None:
    settings = get_settings()
    if not settings.telegram_token or not settings.owner_telegram_id:
        log.warning("JARVIS_TELEGRAM_TOKEN yoki JARVIS_OWNER_TELEGRAM_ID yo'q — bot o'chirilgan")
        return
    bot = Bot(settings.telegram_token)
    await build_dispatcher(settings.owner_telegram_id).start_polling(bot)
