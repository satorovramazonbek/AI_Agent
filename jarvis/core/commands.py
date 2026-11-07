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
from pathlib import Path

from jarvis.tools import macos, web
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
    "📓 «Obsidianni och va yozib qo'y: ...»"
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
