"""Bepul buyruqlar: API'siz, qoidalar asosida matnni macOS amallariga aylantiradi.

Whisper bir xil gapni turlicha yozadi ("Safari'ni och", "safarini och", "Сафарини оч"),
shuning uchun matn avval normallashtiriladi: kichik harf, kirill → lotin, apostrof va
tinish belgilarisiz. Keyin tartib bo'yicha birinchi mos kelgan qoida bajariladi.
"""

from __future__ import annotations

import contextvars
import re
import time
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jarvis.config import get_settings
from jarvis.tools import macos, places, telegram_ui, telegram_user, web
from jarvis.tools.system import NoArgs, system_status

# ---------- Normallashtirish ----------

_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ь": "", "ы": "i", "э": "e", "ю": "yu",
    "я": "ya", "ў": "o", "қ": "q", "ғ": "g", "ҳ": "h",
}  # fmt: skip

_WAKE = re.compile(r"^(hey |hi |salom |эй )?(jarvis|djarvis|jarvys|jarviz|dzharvis)\b\s*")


# Whisper o'zbekchani ba'zan turk/chex lotinida yozadi: «oč», «aç», «şu» → och, ach, shu
_LATIN = {"č": "ch", "ç": "ch", "š": "sh", "ş": "sh", "ž": "j", "ğ": "g", "ı": "i"}
# Tez-tez uchraydigan noto'g'ri eshitishlar (so'z boshida): «ach» → «och», «achir» → «ochir»
_HEARD = [(re.compile(r"\bach"), "och"), (re.compile(r"\buchir"), "ochir")]


def _plain_latin(t: str) -> str:
    """Lotin harflaridagi belgilarni olib tashlaydi (ŏ, é, ü → o, e, u); kirillga tegmaydi."""
    out = []
    for ch in t:
        ch = _LATIN.get(ch, ch)
        base = unicodedata.normalize("NFKD", ch)[0] if len(ch) == 1 else ch
        out.append(base if base.isascii() and not ch.isascii() else ch)
    return "".join(out)


def normalize(text: str) -> str:
    t = "".join(_CYR.get(ch, ch) for ch in text.lower())
    t = _plain_latin(t)
    t = re.sub(r"[ʻʼ‘’`´']", "", t)  # o'/g' va tutuq belgisi
    t = re.sub(r"[^\w\s:]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    for rx, repl in _HEARD:
        t = rx.sub(repl, t)
    return _WAKE.sub("", t).strip()


# ---------- Javob matnlari ----------

MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust",
          "sentyabr", "oktyabr", "noyabr", "dekabr"]  # fmt: skip
WEEKDAYS = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]

HELP = (
    "Men bajara oladigan buyruqlar:\n"
    "🖥 «Safari'ni och», «Telegram'ni yop», «YouTube'ni och», «Yuklamalar papkasini och»\n"
    "🔎 «Python darslarini qidir», «YouTube'da Shoxrux qo'shiqlarini qo'y»\n"
    "🔊 «Ovozni ko'tar / pasaytir / o'chir», «Ovozni 40 ga qo'y»\n"
    "🎵 «Musiqani qo'y / to'xtat», «Keyingi qo'shiq», «Oldingi qo'shiq»\n"
    "⏰ «Soat necha?», «Bugun nechanchi?», «5 daqiqaga taymer qo'y»\n"
    "🧮 «25 ni 4 ga ko'paytir», «12 plus 30», «200 ning 15 foizi»\n"
    "🌤 «Ob-havo qanday?», «Samarqandda ob-havo», «Internet bormi?»\n"
    "🔋 «Batareya qancha?», «Kompyuter holati»\n"
    "🌙 «Tungi rejimni yoq / o'chir», «Wi-Fi'ni o'chir / yoq»\n"
    "📸 «Skrinshot ol», «Ekranni qulfla», «Kompyuterni uxlat»\n"
    "📝 «Eslatma: non olish», «Eslatmalarimni o'qi», «Oxirgi eslatmani o'chir»\n"
    "📓 «Obsidianni och va yozib qo'y: ...»\n"
    "✉️ «Telegramni ochib Aliga salom deb yubor» (yuborishdan oldin so'rayman)\n"
    "📍 «Turgan joyimni Pismadonchani uyi deb saqla», «Pismadonchani uyiga yo'l ko'rsat»"
)


async def _status(_m) -> str:
    s = await system_status(NoArgs())
    return (
        f"OT: {s['os']}\nCPU: {s['cpu_count']} yadro, yuklama {s['load_avg_1m']}\n"
        f"Disk: {s['disk_free_gb']} GB bo'sh ({s['disk_used_pct']}% band)"
    )


async def _time(_m) -> str:
    return f"Soat {datetime.now():%H:%M}."


async def _date(_m) -> str:
    t = datetime.now()
    return f"Bugun {t.day}-{MONTHS[t.month - 1]}, {WEEKDAYS[t.weekday()]}."


async def _battery(_m) -> str:
    b = await macos.battery(macos.NoArgs())
    if not b["present"]:
        return "Batareya topilmadi."
    state = {
        "charging": "quvvatlanmoqda",
        "discharging": "batareyadan ishlayapti",
        "charged": "to'liq quvvatlangan",
    }.get(b["state"], b["state"])
    left = f", taxminan {b['remaining']} qoldi" if b["remaining"] else ""
    return f"Batareya {b['percent']}%, {state}{left}."


async def _lock(_m) -> str:
    await macos.lock_screen(macos.NoArgs())
    return "Ekran o'chirildi."


def _volume(action: str) -> Callable[[re.Match], Awaitable[str]]:
    async def handler(m: re.Match) -> str:
        level = int(m.group("n")) if "n" in m.groupdict() and m.group("n") else None
        if action == "set" and (level is None or level > 100):
            return "Ovoz darajasini 0 dan 100 gacha ayting."
        v = await macos.volume(macos.VolumeArgs(action=action, level=level))
        if v["muted"]:
            return "Ovoz o'chirildi."
        return f"Ovoz {v['level']}%."

    return handler


_APP_NOISE = re.compile(r"\b(ilova|dastur|programma|prilojenie|app|papka|sayt|saytini)\w*\b")


def _app_name(raw: str) -> str:
    """'safarini' → 'safari', 'telegram ilovasini' → 'telegram'."""
    name = _APP_NOISE.sub("", raw).strip()
    name = re.sub(r"\s+(ni|na|ne|ny|n|ga)$", "", name)  # «telegram na» — alohida qo'shimcha
    return re.sub(r"(?<=\w)(ni|ga|ny)$", "", name).strip()


def _app(action: str) -> Callable[[re.Match], Awaitable[str]]:
    async def handler(m: re.Match) -> str:
        spoken = _app_name(m.group("app"))
        if action == "open":
            # papka → o'rnatilgan dastur → sayt
            key = macos._norm(spoken)
            if key in macos.FOLDERS:
                r = await macos.open_folder(macos.OpenFolderArgs(name=key))
                return f"{Path(r['path']).name or 'Uy'} papkasi ochildi."
            if not macos.resolve_app(spoken):
                url = macos.SITES.get(key) or macos.SITES.get(key.replace(" ", ""))
                if url:
                    await macos.open_url(macos.OpenUrlArgs(url=url))
                    return f"{url.split('//')[1]} ochildi."
        fn = macos.open_app if action == "open" else macos.quit_app
        r = await fn(macos.AppArgs(name=spoken))
        if r["status"] == "not_found":
            return f"«{spoken}» degan dastur topilmadi."
        if r["status"] != "ok":
            return f"{r['app']}ni ochib bo'lmadi: {r.get('error')}"
        return f"{r['app']} ochildi." if action == "open" else f"{r['app']} yopildi."

    return handler


_NOTE_ADD = re.compile(
    r"^\s*(?:(?:hey\s+)?(?:jarvis|джарвис)[,!.\s]*)?"
    r"(?:eslatma(?:\s+yoz)?|eslatib\s+qo\W?y|yozib\s+qo\W?y|эслатма|запиши|note)\b"
    r"\s*[:,\-]?\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)


async def _note_add(m: re.Match) -> str:
    await macos.add_note(macos.NoteArgs(text=m.group(1)))
    return f"Yozib qo'ydim: «{m.group(1).strip()}»."


_WAKE_RAW = r"^\s*(?:(?:hey|эй)\s+)?(?:(?:jarvis|джарвис)[,!.\s]*)?"
_OBS = r"(?:obsidian|обсидиан)\S*"
_OPEN_WORD = r"(?:och\w*|оч\w*|открой|open)"
_WRITE = (
    r"(?:yoz(?:ib|gin|ing)?\b(?:\s+qo\W?y\w*)?|qayd\s+et\w*|saqla(?:b|gin|ng)?\b(?:\s+qo\W?y\w*)?"
    r"|ёз(?:иб|гин)?\b(?:\s+қўй\w*)?|запиши|сохрани|write)"
)
_FILLER = r"(?:(?:bu|shu|бу|шу)\s+ma\W?lumot\w*\s+|(?:bu|shu|бу|шу)\s+маълумот\w*\s+)?"
_OBSIDIAN = [
    # «Obsidianni och va yozib qo'y: ...», «Obsidian'ga yoz: ...», «Открой обсидиан и запиши ...»
    re.compile(
        _WAKE_RAW + rf"(?:{_OPEN_WORD}\s+)?{_OBS}(?:\s+{_OPEN_WORD})?\s*(?:,|\bva\b|\bва\b|\bи\b)?"
        rf"\s*{_FILLER}{_WRITE}\s*[:,\-]?\s*(?P<text>.*)$",
        re.IGNORECASE | re.DOTALL,
    ),
    # «Yozib qo'y obsidianga: ...», «Запиши в обсидиан ...»
    re.compile(
        _WAKE_RAW + rf"{_FILLER}{_WRITE}\s+(?:в\s+)?{_OBS}\s*[:,\-]?\s*(?P<text>.*)$",
        re.IGNORECASE | re.DOTALL,
    ),
]


async def _obsidian(m: re.Match) -> str:
    text = m.group("text").strip()
    if not text:
        return "Nima yozay? Masalan: «Obsidian'ga yoz: ertaga soat 9 da uchrashuv»."
    await macos.obsidian_write(macos.NoteArgs(text=text))
    return f"Obsidian'ga yozdim va ochdim: «{text}»."


# ---------- Telegram: «Aliga salom deb yubor» ----------

_TG = r"(?:telegram|telegramm|телеграм)\S*"
_DAT = r"(?:ga|ka|qa|га|ка|қа)"
_NAME = r"(?P<name>[^\s,:]+?(?:\s+[^\s,:]+?)?)" + _DAT + r"\b"
_SEND = (r"(?:yoz|yubor|jo\W?nat|ayt|ёз|юбор|жўнат|айт)\w*"
         r"(?:\s+(?:ber|qo\W?y|yubor|jo\W?nat|бер|қўй|юбор)\w*)?")  # fmt: skip
_DEB = r"(?:deb|deya|degin|деб|дея)"
_TG_PRE = (_WAKE_RAW + rf"(?:{_TG}\s*(?:ni\s+|ни\s+)?(?:och\w*|оч\w*|orqali|орқали)?"
           r"\s*(?:va\s+|ва\s+|,\s*)?)?")  # fmt: skip
_TELEGRAM = [
    # «Telegramni ochib Aliga salom deb yubor», «Sardorga ertaga kelaman deb yoz»
    re.compile(_TG_PRE + _NAME + rf"\s+(?:{_TG}\s+)?(?:xabar\s+)?(?P<msg>.+?)\s*,?\s+{_DEB}\s+"
               rf"{_SEND}\s*[.!]?$", re.IGNORECASE | re.DOTALL),
    # «Telegramda Aliga yoz: salom» (ikki nuqta yoki «telegram» so'zi bo'lsa)
    re.compile(_TG_PRE + _NAME + rf"\s+(?:{_TG}\s+)?{_SEND}\s*(?P<colon>[:,\-])?\s*(?P<msg>.+)$",
               re.IGNORECASE | re.DOTALL),
    # «Напиши Али в телеграм привет», «Отправь Сардору сообщение: завтра приду»
    re.compile(rf"^(?:напиши|отправь|скажи)\s+(?:в\s+{_TG}\s+)?(?P<name>\S+)\s+"
               rf"(?:в\s+{_TG}\s+)?(?:сообщение\s*)?[:,\-]?\s*(?P<msg>.+)$",
               re.IGNORECASE | re.DOTALL),
]  # fmt: skip


def _telegram_match(text: str):
    t = _plain_latin(text.strip())
    for i, rx in enumerate(_TELEGRAM):
        m = rx.match(t)
        if not m:
            continue
        # 2-shakl xavfliroq («Aliga yoz salom»): telegram so'zi yoki ikki nuqta bo'lishi shart
        if i == 1 and not (m.group("colon") or re.search(_TG, t, re.IGNORECASE)):
            continue
        name, msg = m.group("name").strip(" '’ʻ"), m.group("msg").strip(" «»\"'.")
        if name and msg and not re.fullmatch(f"{_TG}|{_OBS}", name, re.IGNORECASE):
            return name, msg
    return None


def _telegram_backend() -> str:
    """«api» — my.telegram.org kalitlari sozlangan bo'lsa; aks holda ekran orqali («ui»)."""
    s = get_settings()
    return "api" if s.tg_api_id and s.tg_api_hash else "ui"


def _looks_like(spoken: str, title: str) -> bool:
    a, b = telegram_user.name_key(spoken), telegram_user.name_key(title)
    return bool(a and b) and (a in b or b in a or a.split()[0] in b.split())


async def _telegram_send(found) -> str:
    if _telegram_backend() == "ui":
        return await _telegram_send_ui(found)
    return await _telegram_send_api(found)


async def _telegram_send_ui(found) -> str:
    spoken, msg = found
    try:
        draft = await telegram_ui.open_chat_and_draft(spoken, msg)
    except telegram_ui.TelegramUIError as e:
        return str(e)
    chat = draft.chat_title or "?"
    warn = ""
    if draft.chat_title and not _looks_like(spoken, draft.chat_title):
        warn = f"\n⚠️ Diqqat: siz «{spoken}» dedingiz, lekin «{chat}» chati ochildi!"

    async def do_send() -> str:
        await telegram_ui.press_send()
        return f"✅ Yuborildi → {chat}: «{msg}»"

    return ask_confirmation(
        f"Telegram'da «{chat}» chati ochildi, xabar yozib qo'yildi:\n«{msg}»{warn}\n"
        "Ekranga qarang — to'g'ri odammi? Yuboraymi?",
        do_send,
        on_cancel=telegram_ui.clear_draft,
    )


async def _telegram_send_api(found) -> str:
    spoken, msg = found
    contact, candidates = await telegram_user.find_contact(spoken)
    if contact is None:
        if not candidates:
            return f"Telegram'da «{spoken}» degan kontakt topilmadi."
        names = ", ".join(c.name for c in candidates)
        return f"«{spoken}» — bir nechta odam bor: {names}. Ism-familiyasi bilan ayting."

    async def do_send() -> str:
        await telegram_user.send(contact, msg)
        return f"✅ Yuborildi → {contact.name}: «{msg}»"

    who = contact.name + (f" (@{contact.username})" if contact.username else "")
    return ask_confirmation(f"Telegram → {who}:\n«{msg}»\nYuboraymi?", do_send)


async def _note_list(_m) -> str:
    r = await macos.list_notes(macos.ListNotesArgs(limit=5))
    if not r["notes"]:
        return "Hozircha eslatma yo'q."
    return f"Oxirgi eslatmalar ({r['total']} ta):\n" + "\n".join(f"• {n}" for n in r["notes"])


async def _help(_m) -> str:
    return HELP


async def _note_delete(_m) -> str:
    r = await macos.delete_last_note(macos.NoArgs())
    if r["status"] != "ok":
        return "O'chiradigan eslatma yo'q."
    return f"O'chirildi: «{r['removed']}»."


def _music(action: str):
    async def handler(_m) -> str:
        r = await macos.music(macos.MusicArgs(action=action))
        return {
            "play": f"{r['player']}: ijro etilmoqda.",
            "pause": f"{r['player']}: to'xtatildi.",
            "next": "Keyingi qo'shiq.",
            "previous": "Oldingi qo'shiq.",
        }[action]

    return handler


UNITS = {"soniya": 1, "sekund": 1, "daqiqa": 60, "minut": 60, "soat": 3600, "chas": 3600}


def _unit_seconds(word: str) -> int:
    return next(v for k, v in UNITS.items() if word.startswith(k))


def _human(seconds: int) -> str:
    for name, size in (("soat", 3600), ("daqiqa", 60)):
        if seconds % size == 0:
            return f"{seconds // size} {name}"
    return f"{seconds} soniya"


async def _timer(m: re.Match) -> str:
    gd = m.groupdict()
    n, unit = int(gd.get("n") or gd["n2"]), gd.get("u") or gd["u2"]
    seconds = n * _unit_seconds(unit)
    if not 1 <= seconds <= 24 * 3600:
        return "Taymer 1 soniyadan 24 soatgacha bo'ladi."
    await macos.set_timer(macos.TimerArgs(seconds=seconds, label=f"{_human(seconds)} o'tdi"))
    return f"Taymer qo'yildi: {_human(seconds)}."


async def _weather(m: re.Match) -> str:
    city = (m.groupdict().get("city") or "").strip()
    w = await web.weather(web.WeatherArgs(city=city.capitalize() or None))
    return (
        f"{w['city']}: {w['temp_c']:+d}°C (his qilinishi {w['feels_c']:+d}°C), {w['desc']}. "
        f"Bugun {w['min_c']:+d}…{w['max_c']:+d}°C."
    )


async def _internet(_m) -> str:
    r = await web.internet_check(web.NoArgs())
    if not r["online"]:
        return "Internet yo'q."
    speed = "tez" if r["latency_ms"] < 80 else "sekin" if r["latency_ms"] > 250 else "o'rtacha"
    return f"Internet bor, javob vaqti {r['latency_ms']} ms ({speed})."


def _toggle(word: str | None) -> bool | None:
    if not word:
        return None
    return not word.startswith(("ochir", "uchir", "vykl", "off"))


async def _dark(m: re.Match) -> str:
    gd = m.groupdict()
    on = False if gd.get("light") else _toggle(gd.get("v"))
    r = await macos.dark_mode(macos.ToggleArgs(on=on))
    return "Tungi rejim yoqildi." if r["dark"] else "Kunduzgi rejim yoqildi."


async def _wifi(m: re.Match) -> str:
    r = await macos.wifi(macos.ToggleArgs(on=_toggle(m.groupdict().get("v"))))
    return "Wi-Fi yoqilgan." if r["on"] else "Wi-Fi o'chirilgan."


async def _sleep(_m) -> str:
    await macos.sleep_now(macos.NoArgs())
    return "Kompyuter uxlayapti."


async def _screenshot(_m) -> str:
    r = await macos.screenshot(macos.NoArgs())
    return f"Skrinshot ish stoliga saqlandi: {Path(r['file']).name}"


def _search(site: str):
    async def handler(m: re.Match) -> str:
        gd = m.groupdict()
        q = (gd.get("q") or gd.get("q2") or "").strip()
        if not q:
            return "Nimani qidiray?"
        await macos.open_url(macos.OpenUrlArgs(url=web.search_url(q, site)))
        return f"{'YouTube' if site == 'youtube' else 'Google'}'da qidiryapman: «{q}»."

    return handler


# ---------- Kalkulyator (belgilarni saqlab qolish uchun alohida tahlil) ----------

_NUM = r"(\d+(?:[.,]\d+)?)"
_OPS = {
    "+": "+", "plus": "+", "plyus": "+", "qosh": "+", "add": "+",
    "-": "-", "minus": "-", "ayir": "-",
    "*": "*", "x": "*", "×": "*", "kopaytir": "*", "karra": "*", "marta": "*", "umnoj": "*",
    "times": "*",
    "/": "/", "÷": "/", "bol": "/", "razdel": "/", "divided": "/",
}  # fmt: skip
_OP_RE = r"(\+|-|\*|×|/|÷|x\b|plus|plyus|qosh\w*|add|minus|ayir\w*|kopaytir\w*|karra|marta" \
         r"|umnoj\w*|times|bol\w*|razdel\w*|divided)"  # fmt: skip
_CALC = [
    # «12 plus 30», «12 + 30», «7 karra 8», «100 bo'lingan 4»
    re.compile(rf"^(?:hisobla\w*\s+|skolko budet\s+|calculate\s+)?{_NUM}\s*{_OP_RE}\s*"
               rf"(?:na\s+|by\s+|ga\s+)?{_NUM}\s*(?:nechchi|necha|qancha|boladi|\?|=)*\s*$"),
    # O'zbekcha tartib: «25 ni 4 ga ko'paytir», «100 dan 30 ni ayir», «25 ga 4 ni qo'sh»
    re.compile(rf"^{_NUM}\s*(?:ni|ga|dan)\s+{_NUM}\s*(?:ni|ga)\s+{_OP_RE}\w*\s*$"),
]
_PERCENT = [
    re.compile(rf"^{_NUM}\s*(?:ning|dan)\s+{_NUM}\s*foiz\w*"),  # «200 ning 15 foizi»
    re.compile(rf"^{_NUM}\s*(?:foiz|%)\s*(?:ot\s+|of\s+)?{_NUM}"),  # «15 foiz 200», «15% of 200»
]


def _calc_text(text: str) -> str:
    t = "".join(_CYR.get(ch, ch) for ch in text.lower())
    t = re.sub(r"[\u02bb\u02bc\u2018\u2019`´']", "", t)
    t = _WAKE.sub("", t.strip())
    return re.sub(r"\s+", " ", t.rstrip(" ?.!")).strip()


def _fmt(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}".replace(",", " ")
    return f"{x:,.4f}".rstrip("0").rstrip(".").replace(",", " ")


def calculate(text: str) -> str | None:
    t = _calc_text(text)
    num = lambda s: float(s.replace(",", "."))  # noqa: E731
    for i, rx in enumerate(_PERCENT):
        m = rx.match(t)
        if m:
            base, pct = (num(m.group(1)), num(m.group(2))) if i == 0 else (
                num(m.group(2)), num(m.group(1)))
            return f"{_fmt(base)} ning {_fmt(pct)}% i = {_fmt(base * pct / 100)}"
    for rx in _CALC:
        m = rx.match(t)
        if not m:
            continue
        if rx is _CALC[0]:  # «a op b»
            a, op_word, b = num(m.group(1)), m.group(2), num(m.group(3))
        else:  # «a ni b ga op»
            a, op_word, b = num(m.group(1)), m.group(3), num(m.group(2))
        op = next(v for k, v in _OPS.items() if op_word.startswith(k))
        if op == "/" and b == 0:
            return "Nolga bo'lib bo'lmaydi."
        res = {"+": a + b, "-": a - b, "*": a * b, "/": a / b if b else 0}[op]
        return f"{_fmt(a)} {op.replace('*', '×').replace('/', '÷')} {_fmt(b)} = {_fmt(res)}"
    return None


async def _calc(m) -> str:
    return m


# ---------- Qoidalar (tartib muhim: aniqroqlari oldinda) ----------

OPEN = r"(och|ochib ber|ochib qoy|ochgin|ochiber|ishga tushir|yurgiz|yoqib ber)"
CLOSE = r"(yop|yopib qoy|yopgin|yopib ber|ochir|ochirib qoy|ochirib ber)"
VOL = r"\b(ovoz\w*|tovush\w*|zvuk\w*|gromkost\w*|volume)"


@dataclass
class Rule:
    name: str
    pattern: re.Pattern
    handler: Callable[[re.Match], Awaitable[str]]


def _r(name: str, pattern: str, handler) -> Rule:
    return Rule(name, re.compile(pattern), handler)


MEDIA = r"\b(musiqa|qoshiq|kuy|muzyk|muzik|music|pesn)\w*"
UNIT = r"soniya|sekund|daqiqa|minut|soat|chas"
ONOFF = r"(?P<v>yoq\w*|ochir\w*|uchir\w*|vkl\w*|vykl\w*|on|off)"

RULES: list[Rule] = [
    _r("help", r"\b(yordam|nima qila olasan|nimalar qila olasan|buyruqlar|help|"
               r"pomogi|chto ty umeesh)\b", _help),
    _r("notes.delete", r"\b(oxirgi|songgi)\s+eslatma\w*\s+(ochir|uchir)|"
                       r"\budali poslednyuyu zametku\b", _note_delete),
    _r("timer", rf"\b(?P<n>\d+)\s*(?P<u>{UNIT})\w*\b.*\b(taymer|timer|budilnik|eslat)\w*", _timer),
    _r("timer", rf"\b(taymer|timer)\w*\s+(?P<n2>\d+)\s*(?P<u2>{UNIT})\w*", _timer),
    _r("search.youtube", r"\b(youtube|yutub|yutube|utub)\w*\s+(?P<q>.+?)\s+(ni\s+)?"
                         r"(qidir|qoy|top|izla|kor|ijro)\w*$"
                         r"|^(naydi|nayti|search)\s+(na\s+|on\s+)?(youtube|yutub)\w*\s+(?P<q2>.+)$",
       _search("youtube")),
    _r("music.next", r"\b(keyingi|navbatdagi)\s+(qoshiq|trek|kuy|musiqa)|\bsleduyuschiy\b|"
                     r"\bnext (song|track)\b", _music("next")),
    _r("music.previous", r"\boldingi\s+(qoshiq|trek|kuy|musiqa)|\bpredyduschiy\b|"
                         r"\bprevious (song|track)\b", _music("previous")),
    _r("music.pause", MEDIA + r"\s+(toxtat|pauza|ochir|uchir|stop|ostanov)|\bpauza\b|"
                      r"\bpause\b", _music("pause")),
    _r("music.play", MEDIA + r"\s+(qoy|yoq|davom|ijro|vklyuch|play)|\b(vklyuchi|postav)\s+muzyk|"
                     r"\bplay music\b", _music("play")),
    _r("weather", r"(?:\b(?P<city>[a-z]+?)(?:da|dagi)\s+)?\b(ob ?havo|obhavo|pogoda|weather|"
                  r"havo qanday|harorat)\b", _weather),
    _r("internet", r"\binternet\s+(bormi|ishla\w*|tezlig\w*|qanday|yoqmi)|"
                   r"\best li internet\b|\binternet check\b", _internet),
    _r("dark", r"\b(tungi|qorongi|dark|temn\w*)\s+(rejim|mode|tema|temu)\w*(\s+" + ONOFF + r")?"
               r"|\b(?P<light>kunduzgi|yorug|light|svetl\w*)\s+(rejim|mode|tema|temu)", _dark),
    _r("wifi", r"\b(wi ?fi|vay ?fay|vayfay|wifi)\w*\s+(ni\s+)?" + ONOFF +
               r"|\b(wi ?fi|vay ?fay|wifi)\w*\s+holat", _wifi),
    _r("sleep", r"\b(kompyuter|mak|noutbuk)\w*\s+uxlat|\buxlat\b|\bsleep mode\b", _sleep),
    _r("screenshot", r"\b(skrinshot|screenshot|skrin shot|snimok ekrana)\b|"
                     r"\bekran\w*\s+rasm\w*\s+(ol|tush)", _screenshot),
    _r("search.google", r"^(?:(?:google|gugl|internet)\w*\s+)?(?P<q>.+?)\s+(haqida\s+)?(ni\s+)?"
                        r"(qidir|izla|qidirib)\w*(\s+ber)?$"
                        r"|^(naydi|nayti|zagugli|search|google)\s+(?P<q2>.+)$", _search("google")),
    _r("notes.list", r"\b(eslatmalar\w*|zametki|my notes)\b.*\b(oqi|korsat|ayt|qanday|bormi)"
                     r"|\beslatmalarim\b|\bmy notes\b", _note_list),
    # ovoz: aniq raqam → o'chirish/yoqish → ko'tarish/pasaytirish
    _r("volume.set", VOL + r".*?\b(?P<n>\d{1,3})\b", _volume("set")),
    _r("volume.mute", VOL + r"\s*(ni\s+)?(ochir|uchir|ochirib)|\b(mute|vyklyuchi zvuk|bez zvuka)\b",
       _volume("mute")),
    _r("volume.unmute", VOL + r"\s*(ni\s+)?(yoq|qaytar)\b|\b(unmute|vklyuchi zvuk)\b",
       _volume("unmute")),
    _r("volume.up", VOL + r".*\b(kotar|baland|oshir|kuchaytir|kattaroq|up)|"
                    r"\b(gromche|louder)\b", _volume("up")),
    _r("volume.down", VOL + r".*\b(pasaytir|past|kamaytir|sekin|down|kichik)|"
                      r"\b(tishe|quieter)\b", _volume("down")),
    _r("time", r"\b(soat|vaqt)\s+(necha|nechchi|nechi|qancha)|\bhozir soat\b|\bskolko vremeni\b|"
               r"\bkotoriy chas\b|\bwhat time\b", _time),
    _r("date", r"\bbugun\s+(nechanchi|qanaqa kun|qaysi kun|sana)|\bsana\b|"
               r"\bkakoe segodnya chislo\b|\bwhat day\b|\bdate today\b", _date),
    _r("battery", r"\b(batareya|batarey|batareyka|zaryad|quvvat|battery)\w*\b", _battery),
    _r("lock", r"\b(ekran\w*|kompyuter\w*)\s+qulfla|\bqulfla\b|\bzablokiruy\b|\block screen\b",
       _lock),
    _r("status", r"\b(holat\w*|status\w*|ahvol\w*|sostoyani\w*)\b", _status),
    _r("app.open", r"^(?P<app>.+?)\s+" + OPEN + r"$"
                   r"|^(open|otkroy|zapusti|vklyuchi)\s+(?P<app2>.+)$", _app("open")),
    _r("app.quit", r"^(?P<app>.+?)\s+" + CLOSE + r"$"
                   r"|^(close|quit|zakroy)\s+(?P<app2>.+)$", _app("quit")),
]


class _AppMatch:
    """`app` / `app2` guruhlaridan qaysi biri to'lgan bo'lsa, shuni `app` deb beradi."""

    def __init__(self, m: re.Match):
        self._m = m

    def group(self, name):
        if name == "app":
            return self._m.group("app") or self._m.group("app2")
        return self._m.group(name)

    def groupdict(self):
        return self._m.groupdict()


def match(text: str) -> tuple[Rule, object] | None:
    """Mos kelgan qoida va match obyekti; hech biri mos kelmasa None."""
    result = calculate(text)
    if result is not None:
        return Rule("calc", re.compile(""), _calc), result
    for pattern in _OBSIDIAN:
        obs = pattern.match(text.strip())
        if obs:
            return Rule("obsidian.write", pattern, _obsidian), obs
    note = _NOTE_ADD.match(text.strip())
    if note:
        return Rule("notes.add", _NOTE_ADD, _note_add), note
    place = _place_match(text)
    if place:
        return Rule(f"place.{place[0]}", re.compile(""), _place_handler), place
    tg = _telegram_match(text)
    if tg:
        return Rule("telegram.send", re.compile(""), _telegram_send), tg
    norm = normalize(text)
    for rule in RULES:
        m = rule.pattern.search(norm)
        if m:
            return rule, (_AppMatch(m) if rule.name.startswith("app.") else m)
    return None


# ---------- Interfeys uchun qo'shimchalar (Telegram: lokatsiya pini, tugmalar) ----------

EXTRAS: dict[str, list[tuple]] = {}


def _extra(*item) -> None:
    EXTRAS.setdefault(_session.get(), []).append(item)


def pop_extras(session_id: str) -> list[tuple]:
    """Javobga qo'shimcha: ("location", lat, lon, nom), ("request_location",), ("done",)."""
    return EXTRAS.pop(session_id, [])


# ---------- Saqlangan joylar ----------

LOCATION_TTL = 10 * 60
LAST_LOCATION: dict[str, tuple[float, float, float]] = {}  # sessiya → (lat, lon, vaqt)
AWAIT_LOCATION: dict[str, tuple[str, float]] = {}  # sessiya → (nom, muddat): joy nomi bor
AWAIT_NAME: dict[str, float] = {}  # sessiya → muddat: lokatsiya bor, nom kutilmoqda

_HERE = (r"(?:turgan\s+joy\w*|men\s+turgan\s+joy\w*|hozirgi\s+joy\w*|joylashuv\w*|lokatsiya\w*"
         r"|lokatsiyam\w*|manzilim\w*|bu\s+(?:joy|yer)\w*|shu\s+(?:joy|yer)\w*)")  # fmt: skip
_SAVE_VERB = r"(?:saqla\w*|eslab\s+qol\w*|yozib\s+qo\W?y\w*)(?:\s+qo\W?y\w*)?"
_PLACE_SAVE = [
    # «Turgan joyimni Pismadonchani uyi deb saqla», «turgan joyim pismadonchani uyi saqlab qo'y»
    re.compile(_WAKE_RAW + _HERE + r"\s+(?P<name>.+?)\s+(?:deb\s+|deya\s+|qilib\s+)?"
               + _SAVE_VERB + r"\s*[.!]?$", re.IGNORECASE),
    # «Сохрани это место как дом Али»
    re.compile(r"^(?:сохрани|запомни)\s+(?:это\s+место|мо[её]\s+местоположение|где\s+я)"
               r"\s+(?:как\s+)?(?P<name>.+?)\s*[.!]?$", re.IGNORECASE),
]
_PLACE_GO = re.compile(
    _WAKE_RAW + r"(?P<name>.+?)(?:\s*(?:ga|ka|qa))?\s+(?P<how>qanday\s+bora\w*|qanday\s+bors\w*"
    r"|yol\w*(?:\s+(?:korsat|ber|och)\w*)?|marshrut\w*|navigator\w*|qayerda\w*|qayer\w*"
    r"|lokatsiya\w*(?:\s+(?:yubor|ber|korsat)\w*)?|manzil\w*(?:\s+(?:yubor|ber|korsat)\w*)?)"
    r"\s*[?.!]?$",
    re.IGNORECASE,
)
_PLACE_LIST = re.compile(r"\b(saqlangan\s+joylar\w*|joylarim\w*|mening\s+joylarim|"
                         r"joylar\s+royxat\w*|moi mesta|saved places)\b")  # fmt: skip
_PLACE_DELETE = re.compile(r"^(?P<name>.+?)\s+(?:degan\s+)?(?:joy\w*\s+|ni\s+joylardan\s+)"
                           r"(?:ochir|uchir)\w*$")  # fmt: skip


def _place_text(text: str) -> str:
    t = _plain_latin(text.strip())
    return re.sub(r"[\u02bb\u02bc\u2018\u2019`´']", "", t)


def _clean_place_name(name: str) -> str:
    name = re.sub(r"\s+(ni|ga)$", "", name.strip(" ,.!?«»\"'"))
    return name[:1].upper() + name[1:] if name else name


def _place_match(text: str):
    t = _place_text(text)
    for rx in _PLACE_SAVE:
        m = rx.match(t)
        if m:
            return "save", _clean_place_name(m.group("name"))
    m = _PLACE_GO.match(t)
    if m:
        name = _clean_place_name(m.group("name"))
        explicit = not m.group("how").lower().startswith("qayer")
        # «… qayerda» faqat shunday joy saqlangan bo'lsa (aks holda boshqa savol bo'lishi mumkin)
        if places.find(name) or (explicit and len(name.split()) <= 4):
            return "go", name
    norm = normalize(text)
    if _PLACE_LIST.search(norm):
        return "list", None
    m = _PLACE_DELETE.match(norm)
    if m and places.find(m.group("name")):
        return "delete", m.group("name")
    return None


def _saved_reply(place, existed: bool) -> str:
    _extra("done")
    verb = "yangilandi" if existed else "saqlandi"
    return f"📍 «{place.name}» {verb}.\nKeyin «{place.name}ga yo'l ko'rsat» desangiz bo'ldi."


def _save_place(name: str, lat: float, lon: float) -> str:
    place, existed = places.save(name, lat, lon)
    return _saved_reply(place, existed)


def _recent_location(session_id: str):
    loc = LAST_LOCATION.get(session_id)
    if loc and time.monotonic() - loc[2] < LOCATION_TTL:
        return loc[0], loc[1]
    return None


async def _place_handler(found) -> str:
    action, name = found
    session_id = _session.get()
    if action == "save":
        loc = _recent_location(session_id)
        if loc:
            AWAIT_NAME.pop(session_id, None)
            return _save_place(name, *loc)
        AWAIT_LOCATION[session_id] = (name, time.monotonic() + LOCATION_TTL)
        if session_id.startswith("tg:"):
            _extra("request_location")
            return f"«{name}» uchun joylashuvingizni yuboring — pastdagi 📍 tugmani bosing."
        return (
            f"«{name}» uchun joylashuv kerak. Mac joylashuvi aniq emas — telefondan JARVIS "
            "botiga lokatsiya yuboring (📎 → Location), 10 daqiqa ichida shu nom bilan saqlayman."
        )
    if action == "go":
        place = places.find(name)
        if place is None:
            return f"«{name}» degan joy saqlanmagan. Saqlanganlar: «Saqlangan joylar» deb so'rang."
        if session_id.startswith("tg:"):
            _extra("location", place.lat, place.lon, place.name)
            return f"🧭 «{place.name}» — navigatsiya ilovasini tanlang va «Start» ni bosing."
        await macos.open_url(macos.OpenUrlArgs(url=place.google))
        return f"🧭 «{place.name}» xaritada ochildi (Google Maps)."
    if action == "list":
        saved = sorted(places.load().values(), key=lambda p: p.name.lower())
        if not saved:
            return "Hali saqlangan joy yo'q. «Turgan joyimni … deb saqla» deng."
        return "📍 Saqlangan joylar:\n" + "\n".join(f"• {p.name}" for p in saved)
    if action == "delete":
        place = places.delete(name)
        return f"«{place.name}» o'chirildi." if place else f"«{name}» topilmadi."
    return "?"


def on_location(session_id: str, lat: float, lon: float) -> str:
    """Telegram'dan lokatsiya keldi: kutilayotgan nom bo'lsa saqlaydi, bo'lmasa nom so'raydi."""
    now = time.monotonic()
    LAST_LOCATION[session_id] = (lat, lon, now)
    waiting = [(sid, v) for sid, v in AWAIT_LOCATION.items() if v[1] > now]
    # avval shu chatdagi so'rov, keyin boshqa interfeysdagi (masalan Mac'da aytilgan) so'rov
    mine = [w for w in waiting if w[0] == session_id] or sorted(waiting, key=lambda w: -w[1][1])
    token = _session.set(session_id)
    try:
        if mine:
            sid, (name, _) = mine[0]
            AWAIT_LOCATION.pop(sid, None)
            return _save_place(name, lat, lon)
        AWAIT_NAME[session_id] = now + LOCATION_TTL
        return "📍 Joylashuv olindi. Qanday nom bilan saqlay? (masalan: «Pismadonchani uyi»)"
    finally:
        _session.reset(token)


# ---------- Tasdiqlash (tashqariga ketadigan amallar uchun) ----------


@dataclass
class Pending:
    question: str  # foydalanuvchiga ko'rsatiladigan savol
    action: Callable[[], Awaitable[str]]
    expires: float
    on_cancel: Callable[[], Awaitable[None]] | None = None


PENDING: dict[str, Pending] = {}
CONFIRM_SECONDS = 90
_session: contextvars.ContextVar[str] = contextvars.ContextVar("session", default="default")
_YES = re.compile(r"^(ha|xa|haa|xop|hop|ha yubor|yubor|jonat|tasdiqla\w*|albatta|mayli|ok|okey|"
                  r"yes|da|davay|otprav\w*)\b")  # fmt: skip
_NO = re.compile(r"^(yoq|kerak emas|bekor\w*|toxta\w*|net|no|otmena|cancel)\b")


def ask_confirmation(
    question: str,
    action: Callable[[], Awaitable[str]],
    on_cancel: Callable[[], Awaitable[None]] | None = None,
) -> str:
    """Amalni darhol bajarmaydi: savol qaytaradi, «ha» kelsa keyin bajaradi."""
    PENDING[_session.get()] = Pending(
        question, action, time.monotonic() + CONFIRM_SECONDS, on_cancel
    )
    return f"{question}\n«Ha» desangiz yuboraman, «yo'q» — bekor qilaman."


def pending(session_id: str) -> Pending | None:
    p = PENDING.get(session_id)
    if p and time.monotonic() > p.expires:
        PENDING.pop(session_id, None)
        return None
    return p


async def confirm(session_id: str) -> str:
    p = PENDING.pop(session_id, None)
    if not p or time.monotonic() > p.expires:
        return "Tasdiqlanadigan amal yo'q (vaqti o'tgan bo'lishi mumkin)."
    try:
        return await p.action()
    except Exception as e:
        return f"Bajarib bo'lmadi: {e}"


async def cancel(session_id: str) -> str:
    p = PENDING.pop(session_id, None)
    if not p:
        return "Bekor qiladigan amal yo'q."
    if p.on_cancel:
        try:
            await p.on_cancel()
        except Exception:  # bekor qilish xatosi asosiy javobni buzmasin
            pass
    return "Bekor qilindi."


async def run_command(text: str, session_id: str = "default") -> str | None:
    """Matnni bepul buyruq sifatida bajaradi; tanilmasa None qaytaradi."""
    if pending(session_id):
        norm = normalize(text)
        if _YES.match(norm):
            return await confirm(session_id)
        if _NO.match(norm):
            return await cancel(session_id)
        PENDING.pop(session_id, None)  # boshqa gap — eski so'rov bekor, yangisi bajariladi
    elif re.fullmatch(r"(ha|xa|yoq|ok|yes|no|da|net)", normalize(text)):
        return "Hozir tasdiqlanadigan narsa yo'q."
    if AWAIT_NAME.get(session_id, 0) > time.monotonic() and match(text) is None:
        # lokatsiya yuborilgan, endi faqat nomi aytildi: «Pismadonchani uyi»
        # (buyruqqa o'xshagan gap — masalan «… deb saqla» — oddiy buyruq sifatida bajariladi)
        AWAIT_NAME.pop(session_id, None)
        if _NO.match(normalize(text)):
            return "Bekor qilindi — joy saqlanmadi."
        loc = _recent_location(session_id)
        if loc:
            name = re.sub(rf"\s+(?:deb\s+)?{_SAVE_VERB}\s*$", "", _place_text(text), flags=re.I)
            token = _session.set(session_id)
            try:
                return _save_place(_clean_place_name(name), *loc)
            finally:
                _session.reset(token)
    found = match(text)
    if not found:
        return None
    rule, m = found
    token = _session.set(session_id)
    try:
        return await rule.handler(m)
    except macos.MacOnly:
        return "Bu buyruq faqat Mac'da ishlaydi (Docker ichida emas)."
    except telegram_user.TelegramNotReady as e:
        return str(e)
    except Exception as e:  # macOS buyrug'i xato bersa, foydalanuvchiga aytamiz
        return f"Bajarib bo'lmadi: {e}"
    finally:
        _session.reset(token)
