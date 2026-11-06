"""Tanilgan matnni qayta ishlash.

API kaliti bo'lsa matn agentga (Claude + tool'lar) uzatiladi. Bo'lmasa — oddiy qoidalar
(hozircha faqat «holat») ishlaydi, shunda JARVIS kalitsiz ham javob beradi.
"""

from __future__ import annotations

import re

from jarvis.core.agent import ask, get_agent
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


async def handle_text(text: str, session_id: str = "default") -> str:
    """Tanilgan matnga javob qaytaradi."""
    text = text.strip()
    if not text:
        return "Hech narsa eshitilmadi — qaytadan, balandroq gapiring."
    if get_agent().available:
        return await ask(text, session_id)
    if STATUS_WORDS.search(text):
        return await status_text()
    return (
        f"Tushundim: «{text}».\n"
        "Agent o'chiq (ANTHROPIC_API_KEY yo'q), shuning uchun hozircha faqat "
        "«holat» buyrug'i bajariladi."
    )
