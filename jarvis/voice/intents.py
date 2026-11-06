"""Ovozdan olingan matnni oddiy buyruqlarga moslash.

Bu vaqtinchalik qoida asosidagi qatlam: agent sikli (LLM) ulanganda matn to'g'ridan-to'g'ri
orkestratorga `Task` sifatida uzatiladi, bu yerdagi qoidalar esa tezkor yo'l bo'lib qoladi.
"""

from __future__ import annotations

import re

from jarvis.tools.system import NoArgs, system_status

STATUS_WORDS = re.compile(
    r"\b(holat\w*|status\w*|ahvol\w*|состояни\w*|статус\w*)\b", re.IGNORECASE
)


async def status_text() -> str:
    s = await system_status(NoArgs())
    return (
        f"OT: {s['os']}\nCPU: {s['cpu_count']} yadro, yuklama {s['load_avg_1m']}\n"
        f"Disk: {s['disk_free_gb']} GB bo'sh ({s['disk_used_pct']}% band)"
    )


async def handle_text(text: str) -> str:
    """Tanilgan matnga javob qaytaradi."""
    text = text.strip()
    if not text:
        return "Hech narsa eshitilmadi — qaytadan, balandroq gapiring."
    if STATUS_WORDS.search(text):
        return await status_text()
    return (
        f"Tushundim: «{text}».\n"
        "Hozircha ovoz orqali faqat «holat» buyrug'i bajariladi; "
        "qolganlari agent sikli ulanganda ishlaydi."
    )
