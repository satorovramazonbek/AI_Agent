"""Tanilgan matnni qayta ishlash.

1. Avval bepul buyruqlar (`jarvis.core.commands`) — API'siz, lokal va tez.
2. Mos kelmasa va API kaliti bo'lsa — agent (Claude + tool'lar).
3. Aks holda — nima qila olishimni aytamiz.
"""

from __future__ import annotations

from jarvis.core.agent import ask, get_agent
from jarvis.core.commands import HELP, run_command
from jarvis.tools.system import NoArgs, system_status


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
    reply = await run_command(text)
    if reply is not None:
        return reply
    if get_agent().available:
        return await ask(text, session_id)
    return f"Tushunmadim: «{text}».\n\n{HELP}"
