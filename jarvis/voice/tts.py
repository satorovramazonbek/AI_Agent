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


_UZ_CYR_PAIRS = [
    ("o\u0000", "ў"), ("g\u0000", "ғ"), ("sh", "ш"), ("ch", "ч"), ("yo", "ё"), ("yu", "ю"),
    ("ya", "я"), ("ye", "е"), ("ts", "тс"), ("e", "е"),
    ("a", "а"), ("b", "б"), ("d", "д"), ("f", "ф"), ("g", "г"), ("h", "ҳ"), ("i", "и"),
    ("j", "ж"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"),
    ("q", "қ"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"), ("v", "в"), ("x", "х"),
    ("y", "й"), ("z", "з"), ("w", "в"), ("c", "к"),
]  # fmt: skip


def uz_cyrillic(text: str) -> str:
    """O'zbek lotini → o'zbek kirili (haqiqiy o'zbekcha ovoz modeli uchun).

    o'→ў, g'→ғ, so'z boshidagi e→э, tutuq (ʼ)→ъ; kirilldagi matnga tegmaydi.
    """
    t = text.lower()
    t = re.sub(r"([og])[\u02bb\u2018`']", lambda m: m.group(1) + "\u0000", t)  # o', g'
    # «Telegram'ni», «Obsidian'ga» — qo'shimcha oldidagi ajratgich olib tashlanadi;
    # qolganlari — tutuq belgisi: «ma'no» → маъно, «mas'uliyat» → масъулият
    t = re.sub(r"[\u02bc\u2019'](?=(?:ni|ga|da|dan|ning|ka|qa|gacha|dagi|lar|larni|ning)\b)", "", t)
    t = re.sub(r"[\u02bc\u2019']", "ъ", t)
    t = re.sub(r"(?<![\w\u0000])e", "э", t)  # so'z boshidagi e
    for a, b in _UZ_CYR_PAIRS:
        t = t.replace(a, b)
    return t.replace("\u0000", "")


VOICES = {"Yelda": to_turkish, "Aru": to_cyrillic, "uz": uz_cyrillic}
_lock = threading.Lock()
_current: subprocess.Popen | None = None
_generation = 0  # yangi gap kelsa, eskisi (hali sintez qilinayotgan bo'lsa ham) aytilmaydi


def prepare(text: str, voice: str) -> str:
    return VOICES.get(voice, lambda s: s)(speakable(text))


def _play(cmd: list[str], gen: int, cleanup: str | None = None) -> None:
    global _current
    proc = None
    with _lock:
        if gen == _generation:
            if _current and _current.poll() is None:
                _current.terminate()
            try:
                proc = _current = subprocess.Popen(cmd)
            except OSError:
                log.warning("ovoz ijro etilmadi: %s", cmd[0], exc_info=True)
    if cleanup:  # vaqtinchalik wav — ijro tugagach (yoki umuman ijro etilmasa) o'chiriladi
        import os

        if proc is not None:
            proc.wait()
        try:
            os.unlink(cleanup)
        except OSError:
            pass


def _sweep_stale(tmpdir: str, older_than: float = 120) -> None:
    """Jarayon to'satdan yopilganda qolib ketgan eski wav fayllarni o'chiradi."""
    import os
    import time
    from pathlib import Path

    for f in Path(tmpdir).glob("jarvis-*.wav"):
        try:
            if time.time() - f.stat().st_mtime > older_than:
                os.unlink(f)
        except OSError:
            pass


def _speak_worker(text: str, voice: str, rate: int, gen: int) -> None:
    if voice in UZ_MODELS:
        import tempfile

        try:
            wave = uzbek_voice(voice).synth(speakable(text))
        except Exception:
            log.warning("o'zbekcha ovoz ishlamadi — Yelda bilan aytaman", exc_info=True)
            return _speak_worker(text, "Yelda", rate, gen)
        if not len(wave):
            return
        _sweep_stale(tempfile.gettempdir())
        path = tempfile.NamedTemporaryFile(prefix="jarvis-", suffix=".wav", delete=False).name
        write_wav(path, wave)
        _play(["afplay", "-r", f"{rate / 175:.2f}", path], gen, cleanup=path)
    else:
        line = prepare(text, voice)
        if line:
            _play(["say", "-v", voice, "-r", str(rate), line], gen)


def speak(text: str, voice: str = "uz", rate: int = 185) -> None:
    """Fonda aytadi (UI qotmaydi); oldingi gap tugamagan bo'lsa — to'xtatib, yangisini aytadi."""
    global _generation
    if sys.platform != "darwin" or not speakable(text):
        return
    with _lock:
        _generation += 1
        gen = _generation
    threading.Thread(target=_speak_worker, args=(text, voice, rate, gen), daemon=True).start()


# ---------- Haqiqiy o'zbekcha ovoz: MMS-TTS (VITS, ONNX) — lokal, internetsiz ----------

UZ_MODELS = {
    "uz": "davron112/mms-tts-uzb-cyrl-onnx",  # Meta MMS, o'zbekcha (erkak/neytral ovoz)
    "uz-qiz": "davron112/mms-tts-uzbek-girl-cyrl-onnx",  # o'zbekcha qiz ovozi
}
SAMPLE_RATE = 16_000


class UzbekVoice:
    """MMS-TTS modeli: o'zbek kirill matni → 16 kHz ovoz to'lqini."""

    def __init__(self, repo: str):
        self.repo = repo
        self._session = None
        self._vocab: dict[str, int] = {}
        self._pad = 0
        self._lock = threading.Lock()

    def _load(self):
        if self._session is None:
            import json
            from pathlib import Path

            import onnxruntime as ort
            from huggingface_hub import snapshot_download

            patterns = ["*.json", "onnx/model.onnx"]
            try:
                path = Path(snapshot_download(self.repo, allow_patterns=patterns,
                                              local_files_only=True))  # fmt: skip
            except Exception:
                log.info("O'zbekcha ovoz modeli yuklanmoqda (~115 MB, bir marta): %s", self.repo)
                path = Path(snapshot_download(self.repo, allow_patterns=patterns))
            self._vocab = json.loads((path / "vocab.json").read_text(encoding="utf-8"))
            pad = json.loads((path / "tokenizer_config.json").read_text()).get("pad_token", "|")
            self._pad = self._vocab.get(pad, 0)
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2  # qisqa gap — ko'p yadro shart emas (kam qizdiradi)
            self._session = ort.InferenceSession(
                str(path / "onnx" / "model.onnx"), opts, providers=["CPUExecutionProvider"]
            )
        return self._session

    def ids(self, cyrillic: str) -> list[int]:
        tokens = [self._vocab[ch] for ch in cyrillic.lower() if ch in self._vocab]
        out = [self._pad] * (2 * len(tokens) + 1)  # add_blank: har belgi orasiga pad
        out[1::2] = tokens
        return out

    def synth(self, text: str):
        import numpy as np

        with self._lock:
            session = self._load()
            ids = self.ids(uz_cyrillic(text))
            if len(ids) <= 1:
                return np.zeros(0, dtype="float32")
            arr = np.array([ids], dtype="int64")
            feed = {"input_ids": arr, "attention_mask": np.ones_like(arr)}
            wave = session.run(["waveform"], feed)
        return wave[0][0].astype("float32")


_uz_voices: dict[str, UzbekVoice] = {}


def uzbek_voice(name: str) -> UzbekVoice:
    if name not in _uz_voices:
        _uz_voices[name] = UzbekVoice(UZ_MODELS[name])
    return _uz_voices[name]


def write_wav(path, wave, rate: int = SAMPLE_RATE) -> None:
    import wave as wavmod

    import numpy as np

    pcm = (np.clip(wave, -1, 1) * 32767).astype("<i2").tobytes()
    with wavmod.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
