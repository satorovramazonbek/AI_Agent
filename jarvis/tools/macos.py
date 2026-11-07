"""macOS tool'lari: dastur ochish/yopish, ovoz, batareya, ekran, vaqt, eslatmalar.

Hammasi lokal va bepul: faqat macOS'ning o'z buyruqlari (`open`, `osascript`, `pmset`).
Buyruqlar shell'siz, argumentlar ro'yxati bilan ishga tushiriladi — matn buyruqqa aylanmaydi.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import re
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

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


OBSIDIAN_CONFIG = Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"


def obsidian_vault() -> Path | None:
    """Sozlamadagi vault yoki Obsidian'da oxirgi ochilgan vault."""
    s = get_settings()
    if s.obsidian_vault:
        return s.obsidian_vault
    try:
        vaults = json.loads(OBSIDIAN_CONFIG.read_text(encoding="utf-8"))["vaults"].values()
    except (OSError, ValueError, KeyError):
        return None
    vaults = [v for v in vaults if Path(v.get("path", "")).is_dir()]
    if not vaults:
        return None
    best = max(vaults, key=lambda v: (bool(v.get("open")), v.get("ts", 0)))
    return Path(best["path"])


def notes_file() -> Path:
    s = get_settings()
    if s.notes_file:
        return s.notes_file
    vault = obsidian_vault()
    if vault:
        return vault / "JARVIS" / "Eslatmalar.md"
    return Path.home() / "Documents" / "JARVIS" / "eslatmalar.md"


class NoteArgs(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@tool(name="notes.add", description="Eslatma yozib qo'yadi", risk=Risk.R1, tags=["secretary"])
async def add_note(args: NoteArgs) -> dict:
    path = notes_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    new = not path.exists()
    with path.open("a", encoding="utf-8") as f:
        if new:
            f.write("# JARVIS eslatmalari\n\n")
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


def obsidian_uri(path: Path, vault: Path | None) -> str | None:
    """Fayl vault ichida bo'lsa, uni Obsidian'da ochadigan obsidian:// havola."""
    if vault is None:
        return None
    try:
        rel = path.resolve().relative_to(vault.resolve())
    except ValueError:
        return None
    return f"obsidian://open?vault={quote(vault.name)}&file={quote(str(rel.with_suffix('')))}"


@tool(
    name="obsidian.write",
    description="Matnni Obsidian'dagi JARVIS eslatmalariga yozadi va Obsidian'da ochadi",
    risk=Risk.R1,
    tags=["macos", "secretary"],
)
async def obsidian_write(args: NoteArgs) -> dict:
    saved = await add_note(args)
    path = Path(saved["file"])
    uri = obsidian_uri(path, obsidian_vault())
    if uri:
        await _run("open", uri)
    else:
        await _run("open", "-a", "Obsidian")
    return {"status": "ok", "file": str(path), "opened": uri or "Obsidian"}


@tool(name="notes.delete_last", description="Oxirgi eslatmani o'chiradi", risk=Risk.R1)
async def delete_last_note(args: NoArgs) -> dict:
    path = notes_file()
    if not path.exists():
        return {"status": "empty"}
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("- "):
            removed = lines.pop(i)
            path.write_text("".join(lines), encoding="utf-8")
            return {"status": "ok", "removed": removed[2:].strip()}
    return {"status": "empty"}


# ---------- Bildirishnoma va taymer ----------


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


async def notify(title: str, text: str, sound: bool = False) -> None:
    await _run("osascript", "-e", f'display notification "{_esc(text)}" with title "{_esc(title)}"')
    if sound:
        await _run("afplay", "/System/Library/Sounds/Glass.aiff", timeout=10)


_timers: set[asyncio.Task] = set()  # tugamagan taymerlar (GC o'chirib yubormasligi uchun)


class TimerArgs(BaseModel):
    seconds: int = Field(ge=1, le=24 * 3600)
    label: str = Field(default="", max_length=200)


@tool(name="timer.set", description="Taymer: vaqt tugaganda bildirishnoma", risk=Risk.R0)
async def set_timer(args: TimerArgs) -> dict:
    if sys.platform != "darwin":
        raise MacOnly("taymer bildirishnomasi faqat Mac'da")

    async def ring() -> None:
        await asyncio.sleep(args.seconds)
        await notify("⏰ JARVIS taymer", args.label or "Vaqt tugadi!", sound=True)

    task = asyncio.get_running_loop().create_task(ring())
    _timers.add(task)
    task.add_done_callback(_timers.discard)
    return {"status": "ok", "seconds": args.seconds, "active": len(_timers)}


# ---------- Musiqa ----------


class MusicArgs(BaseModel):
    action: Literal["play", "pause", "playpause", "next", "previous"]


@tool(name="macos.music", description="Musiqa: qo'yish, to'xtatish, keyingi", risk=Risk.R1)
async def music(args: MusicArgs) -> dict:
    code, _, _ = await _run("pgrep", "-x", "Spotify")
    player = "Spotify" if code == 0 else "Music"
    command = {
        "play": "play",
        "pause": "pause",
        "playpause": "playpause",
        "next": "next track",
        "previous": "previous track",
    }[args.action]
    await _osascript(f'tell application "{player}" to {command}')
    return {"status": "ok", "player": player}


# ---------- Tizim: tungi rejim, Wi-Fi, uyqu, skrinshot ----------


class ToggleArgs(BaseModel):
    on: bool | None = Field(default=None, description="True/False; None — almashtirish")


@tool(name="macos.dark_mode", description="Tungi (qorong'i) rejim", risk=Risk.R1)
async def dark_mode(args: ToggleArgs) -> dict:
    value = "not dark mode" if args.on is None else str(args.on).lower()
    prefs = 'tell application "System Events" to tell appearance preferences to'
    await _osascript(f"{prefs} set dark mode to {value}")
    out = await _osascript(f"{prefs} get dark mode")
    return {"dark": out == "true"}


async def _wifi_device() -> str:
    _, out, _ = await _run("networksetup", "-listallhardwareports")
    m = re.search(r"Hardware Port: Wi-Fi\s*\nDevice: (\S+)", out)
    return m.group(1) if m else "en0"


@tool(name="macos.wifi", description="Wi-Fi'ni yoqish/o'chirish", risk=Risk.R2)
async def wifi(args: ToggleArgs) -> dict:
    dev = await _wifi_device()
    if args.on is not None:
        code, _, err = await _run(
            "networksetup", "-setairportpower", dev, "on" if args.on else "off"
        )
        if code != 0:
            raise RuntimeError(err or "Wi-Fi o'zgarmadi")
    _, out, _ = await _run("networksetup", "-getairportpower", dev)
    return {"on": out.strip().endswith("On"), "device": dev}


@tool(name="macos.sleep", description="Kompyuterni uxlatadi", risk=Risk.R1)
async def sleep_now(args: NoArgs) -> dict:
    await _run("pmset", "sleepnow")
    return {"status": "ok"}


@tool(name="macos.screenshot", description="Ekran rasmini ish stoliga saqlaydi", risk=Risk.R1)
async def screenshot(args: NoArgs) -> dict:
    path = Path.home() / "Desktop" / f"JARVIS {datetime.now():%Y-%m-%d %H.%M.%S}.png"
    code, _, err = await _run("screencapture", "-x", str(path))
    if code != 0 or not path.exists():
        raise RuntimeError(err or "ekranni olib bo'lmadi (Screen Recording ruxsatini bering)")
    return {"status": "ok", "file": str(path)}


# ---------- Papkalar va saytlar ----------

FOLDERS = {
    "downloads": "Downloads", "yuklamalar": "Downloads", "yuklanmalar": "Downloads",
    "zagruzki": "Downloads", "yuklab olinganlar": "Downloads",
    "desktop": "Desktop", "ish stoli": "Desktop", "rabochiy stol": "Desktop",
    "documents": "Documents", "hujjatlar": "Documents", "dokumenty": "Documents",
    "pictures": "Pictures", "suratlar": "Pictures", "izobrazheniya": "Pictures",
    "movies": "Movies", "videolar": "Movies",
    "music papka": "Music", "uy papka": "", "home": "", "uy": "",
}  # fmt: skip

SITES = {
    "youtube": "https://www.youtube.com", "yutub": "https://www.youtube.com",
    "yutube": "https://www.youtube.com", "utub": "https://www.youtube.com",
    "gmail": "https://mail.google.com", "pochta google": "https://mail.google.com",
    "github": "https://github.com", "gitxab": "https://github.com", "githab": "https://github.com",
    "google": "https://www.google.com", "gugl": "https://www.google.com",
    "instagram": "https://www.instagram.com", "instagramm": "https://www.instagram.com",
    "chatgpt": "https://chatgpt.com", "chat gpt": "https://chatgpt.com",
    "claude ai": "https://claude.ai", "tarjimon": "https://translate.google.com",
    "translate": "https://translate.google.com", "perevodchik": "https://translate.google.com",
    "kun uz": "https://kun.uz", "kunuz": "https://kun.uz",
    "linkedin": "https://www.linkedin.com", "facebook": "https://www.facebook.com",
    "x com": "https://x.com", "twitter": "https://x.com",
    "olx": "https://www.olx.uz", "hh": "https://hh.uz", "uzum": "https://uzum.uz",
    "netflix": "https://www.netflix.com", "wikipedia": "https://www.wikipedia.org",
}  # fmt: skip


class OpenFolderArgs(BaseModel):
    name: str


@tool(name="macos.open_folder", description="Finder'da papka ochadi", risk=Risk.R0)
async def open_folder(args: OpenFolderArgs) -> dict:
    key = _norm(args.name)
    if key not in FOLDERS:
        return {"status": "not_found"}
    path = Path.home() / FOLDERS[key]
    await _run("open", str(path))
    return {"status": "ok", "path": str(path)}


class OpenUrlArgs(BaseModel):
    url: str = Field(pattern=r"^https://")


@tool(name="web.open_url", description="Brauzerda https havolani ochadi", risk=Risk.R1)
async def open_url(args: OpenUrlArgs) -> dict:
    await _run("open", args.url)
    return {"status": "ok", "url": args.url}
