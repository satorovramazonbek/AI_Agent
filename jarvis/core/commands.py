"""Bepul buyruqlar: API'siz, qoidalar asosida matnni macOS amallariga aylantiradi.

Whisper bir xil gapni turlicha yozadi ("Safari'ni och", "safarini och", "Сафарини оч"),
shuning uchun matn avval normallashtiriladi: kichik harf, kirill → lotin, apostrof va
tinish belgilarisiz. Keyin tartib bo'yicha birinchi mos kelgan qoida bajariladi.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from jarvis.tools import macos
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


def normalize(text: str) -> str:
    t = "".join(_CYR.get(ch, ch) for ch in text.lower())
    t = re.sub(r"[ʻʼ‘’`´']", "", t)  # o'/g' va tutuq belgisi
    t = re.sub(r"[^\w\s:]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return _WAKE.sub("", t).strip()


# ---------- Javob matnlari ----------

MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust",
          "sentyabr", "oktyabr", "noyabr", "dekabr"]  # fmt: skip
WEEKDAYS = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]

HELP = (
    "Men bajara oladigan buyruqlar:\n"
    "• «Safari'ni och», «Telegram'ni yop»\n"
    "• «Ovozni ko'tar / pasaytir / o'chir / yoq», «Ovozni 40 ga qo'y»\n"
    "• «Soat necha?», «Bugun nechanchi?»\n"
    "• «Batareya qancha?», «Kompyuter holati»\n"
    "• «Ekranni qulfla»\n"
    "• «Eslatma: non olish», «Eslatmalarimni o'qi»\n"
    "• «Obsidianni och va yozib qo'y: ...», «Obsidian'ga yoz: ...»"
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


_APP_NOISE = re.compile(r"\b(ilova|dastur|programma|prilojenie|app)\w*\b")


def _app_name(raw: str) -> str:
    """'safarini' → 'safari', 'telegram ilovasini' → 'telegram'."""
    name = _APP_NOISE.sub("", raw).strip()
    return re.sub(r"(?<=\w)(ni|ga|ny)$", "", name).strip()


def _app(action: str) -> Callable[[re.Match], Awaitable[str]]:
    async def handler(m: re.Match) -> str:
        spoken = _app_name(m.group("app"))
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


async def _note_list(_m) -> str:
    r = await macos.list_notes(macos.ListNotesArgs(limit=5))
    if not r["notes"]:
        return "Hozircha eslatma yo'q."
    return f"Oxirgi eslatmalar ({r['total']} ta):\n" + "\n".join(f"• {n}" for n in r["notes"])


async def _help(_m) -> str:
    return HELP


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


RULES: list[Rule] = [
    _r("help", r"\b(yordam|nima qila olasan|nimalar qila olasan|buyruqlar|help|"
               r"pomogi|chto ty umeesh)\b", _help),
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
    for pattern in _OBSIDIAN:
        obs = pattern.match(text.strip())
        if obs:
            return Rule("obsidian.write", pattern, _obsidian), obs
    note = _NOTE_ADD.match(text.strip())
    if note:
        return Rule("notes.add", _NOTE_ADD, _note_add), note
    norm = normalize(text)
    for rule in RULES:
        m = rule.pattern.search(norm)
        if m:
            return rule, (_AppMatch(m) if rule.name.startswith("app.") else m)
    return None


async def run_command(text: str) -> str | None:
    """Matnni bepul buyruq sifatida bajaradi; tanilmasa None qaytaradi."""
    found = match(text)
    if not found:
        return None
    rule, m = found
    try:
        return await rule.handler(m)
    except macos.MacOnly:
        return "Bu buyruq faqat Mac'da ishlaydi (Docker ichida emas)."
    except Exception as e:  # macOS buyrug'i xato bersa, foydalanuvchiga aytamiz
        return f"Bajarib bo'lmadi: {e}"
