"""Nutqni matnga o'girish (STT): lokal Whisper (faster-whisper), audio Mac'dan chiqmaydi.

`faster-whisper` ixtiyoriy bog'liqlik: `pip install -e ".[voice]"`. U o'rnatilmagan bo'lsa
(masalan Docker'da), `VoiceUnavailable` ko'tariladi va ilovaning qolgan qismi ishlayveradi.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jarvis.config import get_settings

log = logging.getLogger(__name__)


class VoiceUnavailable(RuntimeError):
    """Ovoz moduli o'rnatilmagan yoki model yuklanmadi."""


@dataclass
class Transcript:
    text: str
    language: str
    duration: float
    confidence: float = 1.0  # 0..1 — Whisper qanchalik ishonch bilan tanigani

    @property
    def unsure(self) -> bool:
        return self.confidence < LOW_CONFIDENCE


LOW_CONFIDENCE = 0.5


class Transcriber:
    def __init__(
        self,
        model_name: str,
        language: str | None,
        compute_type: str = "int8",
        prompt: str | None = None,
    ):
        self.model_name = model_name
        self.language = language or None
        self.prompt = prompt or None
        self.compute_type = compute_type
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise VoiceUnavailable(
                    'faster-whisper o\'rnatilmagan: pip install -e ".[voice]"'
                ) from e
            log.info("Whisper modeli yuklanmoqda: %s", self.model_name)
            try:  # avval Mac'dagi nusxa — internetsiz va tez ochiladi
                self._model = WhisperModel(
                    self.model_name,
                    device="cpu",
                    compute_type=self.compute_type,
                    local_files_only=True,
                )
            except Exception:
                log.info("Model Mac'da yo'q — yuklab olinmoqda (~1.6 GB, bir marta)")
                self._model = WhisperModel(
                    self.model_name, device="cpu", compute_type=self.compute_type
                )
        return self._model

    def transcribe_sync(self, audio: str | Path | Any, language: str | None = None) -> Transcript:
        """`audio` — fayl yo'li (ogg, mp3, wav, m4a...) yoki 16 kHz mono float32 numpy massivi."""
        with self._lock:  # bitta model bir vaqtda bitta audio bilan ishlaydi
            model = self._load()
            if isinstance(audio, Path):
                audio = str(audio)
            lang = language or self.language
            segments, info = model.transcribe(
                audio,
                language=lang,
                beam_size=5,
                vad_filter=True,  # jimlik va shovqinni tashlab yuboradi
                # O'zbekcha namuna faqat uz/avtomatik tilda — rus/inglizga xalaqit bermasin.
                initial_prompt=self.prompt if lang in (None, "uz") else None,
            )
            segs = list(segments)
        text = " ".join(s.text.strip() for s in segs).strip()
        conf = math.exp(sum(s.avg_logprob for s in segs) / len(segs)) if segs else 0.0
        return Transcript(
            text=text,
            language=info.language,
            duration=round(info.duration, 1),
            confidence=round(min(conf, 1.0), 2),
        )

    async def transcribe(self, audio: str | Path | Any, language: str | None = None) -> Transcript:
        return await asyncio.to_thread(self.transcribe_sync, audio, language)


@lru_cache
def get_transcriber() -> Transcriber:
    s = get_settings()
    return Transcriber(s.stt_model, s.stt_language, prompt=s.stt_prompt)
