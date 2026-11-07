"""macOS tool'lari: dastur ochish/yopish, ovoz, batareya, ekran, vaqt, eslatmalar.

Hammasi lokal va bepul: faqat macOS'ning o'z buyruqlari (`open`, `osascript`, `pmset`).
Buyruqlar shell'siz, argumentlar ro'yxati bilan ishga tushiriladi — matn buyruqqa aylanmaydi.
"""

from __future__ import annotations

import asyncio
import difflib
import re
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from jarvis.config import get_settings
from jarvis.security.policy import Risk
from jarvis.tools.registry import tool

APP_DIRS = [
    Path("/Applications"),
    Path("/System/Applications"),
    Path("/System/Applications/Utilities"),
    Path.home() / "Applications",
]

# Og'zaki nomlar → dastur nomi (kalitlar normallashtirilgan: kichik harf, apostrofsiz).
APP_ALIASES = {
    "brauzer": "Safari",
    "brovzer": "Safari",
    "internet": "Safari",
    "safari": "Safari",
    "xrom": "Google Chrome",
    "chrome": "Google Chrome",
    "krom": "Google Chrome",
    "gugl": "Google Chrome",
    "google": "Google Chrome",
    "telegram": "Telegram",
    "telegramm": "Telegram",
    "telegrem": "Telegram",
    "terminal": "Terminal",
    "kalkulyator": "Calculator",
    "kalkulator": "Calculator",
    "calculator": "Calculator",
    "kalendar": "Calendar",
    "taqvim": "Calendar",
    "musiqa": "Music",
    "muzika": "Music",
    "sozlamalar": "System Settings",
    "nastroyki": "System Settings",
    "settings": "System Settings",
    "fayllar": "Finder",
    "papkalar": "Finder",
    "finder": "Finder",
    "qaydlar": "Notes",
    "zametki": "Notes",
    "notes": "Notes",
    "xabarlar": "Messages",
    "pochta": "Mail",
    "mail": "Mail",
    "rasmlar": "Photos",
    "fotosuratlar": "Photos",
    "xarita": "Maps",
    "karta": "Maps",
    "ob havo": "Weather",
    "obhavo": "Weather",
    "pogoda": "Weather",
    "eslatmalar": "Reminders",
    "vs kod": "Visual Studio Code",
    "vskod": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "pycharm": "PyCharm",
    "paycharm": "PyCharm",
    "word": "Microsoft Word",
    "vord": "Microsoft Word",
    "excel": "Microsoft Excel",
    "eksel": "Microsoft Excel",
    "ekstel": "Microsoft Excel",
    "powerpoint": "Microsoft PowerPoint",
    "diskord": "Discord",
    "discord": "Discord",
    "slack": "Slack",
    "slek": "Slack",
    "obsidian": "Obsidian",
    "app store": "App Store",
    "appstore": "App Store",
    "epp stor": "App Store",
    "yandeks muzika": "Яндекс Музыка",
    "yandeks muzyka": "Яндекс Музыка",
    "yandex music": "Яндекс Музыка",
    "docker": "Docker",
    "doker": "Docker",
    "claude": "Claude",
    "klod": "Claude",
}


class MacOnly(RuntimeError):
    """Bu amal faqat macOS'da ishlaydi (Docker/Linux'da emas)."""


def _norm(s: str) -> str:
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


async def _run(*args: str, timeout: float = 15) -> tuple[int, str, str]:
    if sys.platform != "darwin":
        raise MacOnly("bu buyruq faqat Mac'da ishlaydi")
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode or 0, out.decode().strip(), err.decode().strip()


async def _osascript(script: str) -> str:
    code, out, err = await _run("osascript", "-e", script)
    if code != 0:
        raise RuntimeError(err or "osascript xatosi")
    return out


# ---------- Dasturlar ----------


@lru_cache
def installed_apps() -> dict[str, str]:
    """{normallashtirilgan nom: haqiqiy nom} — o'rnatilgan .app'lar."""
    apps: dict[str, str] = {}
    for d in APP_DIRS:
        if d.is_dir():
            for p in d.glob("*.app"):
                apps[_norm(p.stem)] = p.stem
    return apps


def resolve_app(spoken: str, apps: dict[str, str] | None = None) -> str | None:
    """Og'zaki nomni o'rnatilgan dastur nomiga aylantiradi; topilmasa None."""
    apps = installed_apps() if apps is None else apps
    key = _norm(spoken)
    if not key:
        return None
    alias = APP_ALIASES.get(key) or APP_ALIASES.get(key.replace(" ", ""))
    if alias and _norm(alias) in apps:
        return apps[_norm(alias)]
    if key in apps:
        return apps[key]
    # "chrome" → "google chrome": so'zlardan biri to'liq mos kelsa
    for norm_name, real in apps.items():
        if key in norm_name.split():
            return real
    # 0.85: "telegarm"→Telegram, "discort"→Discord topiladi, lekin "photoshop"→Photos emas —
    # noto'g'ri dastur ochgandan ko'ra «topilmadi» degan yaxshi.
    close = difflib.get_close_matches(key, list(apps), n=1, cutoff=0.85)
    return apps[close[0]] if close else None


class AppArgs(BaseModel):
    name: str = Field(description="Dastur nomi, masalan Safari, Telegram, brauzer")


@tool(name="macos.open_app", description="Mac'da dasturni ochadi", risk=Risk.R1, tags=["macos"])
async def open_app(args: AppArgs) -> dict:
    app = resolve_app(args.name)
    if not app:
        return {"status": "not_found", "name": args.name}
    code, _, err = await _run("open", "-a", app)
    return {"status": "ok" if code == 0 else "error", "app": app, "error": err or None}


@tool(name="macos.quit_app", description="Mac'da dasturni yopadi", risk=Risk.R1, tags=["macos"])
async def quit_app(args: AppArgs) -> dict:
    app = resolve_app(args.name)
    if not app:
        return {"status": "not_found", "name": args.name}
    # Oddiy yopish: saqlanmagan ish bo'lsa, dastur o'zi so'raydi (majburan o'ldirilmaydi).
    await _osascript(f'tell application "{app}" to quit')
    return {"status": "ok", "app": app}


# ---------- Ovoz ----------


class VolumeArgs(BaseModel):
    action: Literal["get", "set", "up", "down", "mute", "unmute"]
    level: int | None = Field(default=None, ge=0, le=100, description="action=set uchun 0–100")


VOLUME_STEP = 10


@tool(name="macos.volume", description="Mac ovoz balandligi", risk=Risk.R1, tags=["macos"])
async def volume(args: VolumeArgs) -> dict:
    current = int(await _osascript("output volume of (get volume settings)"))
    if args.action == "mute":
        await _osascript("set volume with output muted")
    elif args.action == "unmute":
        await _osascript("set volume without output muted")
    elif args.action in ("set", "up", "down"):
        target = {
            "set": args.level if args.level is not None else current,
            "up": current + VOLUME_STEP,
            "down": current - VOLUME_STEP,
        }[args.action]
        target = max(0, min(100, target))
        await _osascript(f"set volume output volume {target}")
        if target > 0:
            await _osascript("set volume without output muted")
        current = target
    muted = await _osascript("output muted of (get volume settings)") == "true"
    return {"level": current, "muted": muted}


# ---------- Batareya, ekran, vaqt ----------


class NoArgs(BaseModel):
    pass


@tool(name="macos.battery", description="Batareya quvvati va holati", risk=Risk.R0, tags=["macos"])
async def battery(args: NoArgs) -> dict:
    _, out, _ = await _run("pmset", "-g", "batt")
    m = re.search(r"(\d+)%;\s*([^;]+);\s*(\S+)?", out)
    if not m:
        return {"present": False}
    return {
        "present": True,
        "percent": int(m.group(1)),
        "state": m.group(2).strip(),  # charging | discharging | charged | AC attached
        "remaining": m.group(3) if m.group(3) and ":" in m.group(3) else None,
        "on_ac": "AC Power" in out,
    }


@tool(name="macos.lock_screen", description="Ekranni o'chiradi/qulflaydi", risk=Risk.R1)
async def lock_screen(args: NoArgs) -> dict:
    await _run("pmset", "displaysleepnow")
    return {"status": "ok"}


@tool(name="clock.now", description="Hozirgi sana va vaqt", risk=Risk.R0, tags=["system"])
async def now(args: NoArgs) -> dict:
    t = datetime.now().astimezone()
    return {"iso": t.isoformat(timespec="seconds"), "weekday": t.isoweekday()}


# ---------- Eslatmalar (lokal fayl, ruxsat so'ramaydi) ----------


def notes_file() -> Path:
    return get_settings().notes_file


class NoteArgs(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@tool(name="notes.add", description="Eslatma yozib qo'yadi", risk=Risk.R1, tags=["secretary"])
async def add_note(args: NoteArgs) -> dict:
    path = notes_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"- [{stamp}] {args.text.strip()}\n")
    return {"status": "ok", "file": str(path)}


class ListNotesArgs(BaseModel):
    limit: int = Field(default=5, ge=1, le=50)


@tool(name="notes.list", description="Oxirgi eslatmalar", risk=Risk.R0, tags=["secretary"])
async def list_notes(args: ListNotesArgs) -> dict:
    path = notes_file()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    notes = [ln[2:] for ln in lines if ln.startswith("- ")]
    return {"total": len(notes), "notes": notes[-args.limit :]}
