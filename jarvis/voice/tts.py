"""Javobni ovoz chiqarib aytish (TTS): macOS `say`, bepul va internetsiz.

macOS'da o'zbekcha ovoz yo'q, shuning uchun o'zbekcha matn turkiy tildagi ovozga mos imloga
o'giriladi (turkcha «Yelda» yoki qozoqcha «Aru»), sonlar esa o'zbekcha so'z bilan yoziladi:
«Soat 17:03» → «Soat o'n yetti-yu uch daqiqa».
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
import threading

log = logging.getLogger(__name__)

ONES = ["nol", "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz"]
TENS = ["", "o'n", "yigirma", "o'ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to'qson"]


def number_words(n: int) -> str:
    """0..999 999 999 → o'zbekcha so'z bilan."""
    if n < 0:
        return "minus " + number_words(-n)
    if n < 10:
        return ONES[n]
    if n < 100:
        t, o = divmod(n, 10)
        return TENS[t] + (f" {ONES[o]}" if o else "")
    if n < 1000:
        h, r = divmod(n, 100)
        head = "yuz" if h == 1 else f"{ONES[h]} yuz"
        return head + (f" {number_words(r)}" if r else "")
    for size, name in ((1_000_000, "million"), (1000, "ming")):
        if n >= size:
            q, r = divmod(n, size)
            head = name if (q == 1 and size == 1000) else f"{number_words(q)} {name}"
            return head + (f" {number_words(r)}" if r else "")
    return str(n)


MAX_SPOKEN = 220  # uzun javobning faqat boshi aytiladi (to'liq matn ekranda)


def _shorten(text: str) -> str:
    out = ""
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith(("•", "🖥", "🔎", "🔊")):
            break  # ro'yxat boshlandi — ekranda o'qiladi
        if out and len(out) + len(line) > MAX_SPOKEN:
            break
        out = f"{out} {line}".strip()
    return out or text[:MAX_SPOKEN]


def speakable(text: str) -> str:
    """Ovozga tayyorlash: emoji/belgilar olib tashlanadi, sonlar so'zga aylanadi."""
    t = _shorten(text.split("\n«Ha» desangiz")[0])  # tasdiqlash yo'riqnomasi o'qilmaydi
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[«»\"“”•✅❌⚠️🎙🧭📍📝📓✉️🔎🔊🎵⏰🧮🌤🔋🌙📸🖥🤖…]", " ", t)

    def clock(m: re.Match) -> str:
        h, mnt = int(m.group(1)), int(m.group(2))
        return f"{number_words(h)}" + (f" dan {number_words(mnt)} daqiqa o'tdi" if mnt else "")

    t = re.sub(r"\b(\d{1,2}):(\d{2})\b", clock, t)
    t = re.sub(r"(\d+)\s*%", lambda m: f"{number_words(int(m.group(1)))} foiz", t)
    t = re.sub(r"([+-])(\d+)°C", lambda m: ("minus " if m.group(1) == "-" else "")
               + number_words(int(m.group(2))) + " daraja", t)  # fmt: skip
    t = re.sub(r"(\d+)[.,](\d+)", lambda m: f"{number_words(int(m.group(1)))} butun "
               f"{number_words(int(m.group(2)))}", t)  # fmt: skip
    t = re.sub(r"\d+", lambda m: number_words(int(m.group(0))), t)
    t = t.replace("×", " ko'paytirilsa ").replace("÷", " bo'linsa ").replace("=", " teng ")
    return re.sub(r"\s+", " ", t).strip(" .,:;-")


def to_turkish(text: str) -> str:
    """O'zbek lotini → turk imlosi (Yelda ovozi to'g'ri talaffuz qilishi uchun)."""
    t = re.sub(r"([OoGg])[ʻʼ‘’'`]", lambda m: m.group(1) + "\u0000", text)
    rules = [
        ("sh", "ş"), ("Sh", "Ş"), ("SH", "Ş"), ("ch", "ç"), ("Ch", "Ç"), ("CH", "Ç"),
        ("g\u0000", "ğ"), ("G\u0000", "Ğ"), ("o\u0000", "o"), ("O\u0000", "O"),
        ("x", "h"), ("X", "H"), ("q", "k"), ("Q", "K"), ("j", "c"), ("J", "C"),
    ]  # fmt: skip
    for a, b in rules:
        t = t.replace(a, b)
    return re.sub(r"[ʻʼ‘’'`]", "", t)  # tutuq belgisi


_CYR = [
    ("sh", "ш"), ("ch", "ч"), ("yo", "ё"), ("yu", "ю"), ("ya", "я"), ("ye", "е"),
    ("o\u0000", "ў"), ("g\u0000", "ғ"), ("ng", "нг"),
    ("a", "а"), ("b", "б"), ("d", "д"), ("e", "е"), ("f", "ф"), ("g", "г"), ("h", "ҳ"),
    ("i", "и"), ("j", "ж"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"),
    ("p", "п"), ("q", "қ"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"), ("v", "в"),
    ("x", "х"), ("y", "й"), ("z", "з"),
]  # fmt: skip


def to_cyrillic(text: str) -> str:
    """O'zbek lotini → kirill (qozoqcha Aru ovozi uchun)."""
    t = re.sub(r"([OoGg])[ʻʼ‘’'`]", lambda m: m.group(1).lower() + "\u0000",
               text.lower())  # fmt: skip
    for a, b in _CYR:
        t = t.replace(a, b)
    return re.sub(r"[ʻʼ‘’'`\u0000]", "", t)


VOICES = {"Yelda": to_turkish, "Aru": to_cyrillic}
_lock = threading.Lock()
_current: subprocess.Popen | None = None


def prepare(text: str, voice: str) -> str:
    return VOICES.get(voice, lambda s: s)(speakable(text))


def speak(text: str, voice: str = "Yelda", rate: int = 185) -> None:
    """Fonda aytadi; oldingi gap tugamagan bo'lsa — to'xtatib, yangisini aytadi."""
    global _current
    if sys.platform != "darwin":
        return
    line = prepare(text, voice)
    if not line:
        return
    with _lock:
        if _current and _current.poll() is None:
            _current.terminate()
        try:
            _current = subprocess.Popen(["say", "-v", voice, "-r", str(rate), line])
        except OSError:
            log.warning("say ishlamadi", exc_info=True)
