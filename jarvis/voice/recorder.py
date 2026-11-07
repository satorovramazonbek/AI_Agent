"""Mikrofondan bitta gapni yozib olish: gap boshlanishini va jimlikni o'zi aniqlaydi.

Shovqin darajasi birinchi ~0.3 soniyada o'lchanadi, gap undan balandroq ovoz bilan
boshlanadi va `silence_seconds` jimlikdan keyin yozish to'xtaydi.
"""

from __future__ import annotations

import queue
import threading

SAMPLE_RATE = 16_000
BLOCK = 1600  # 0.1 soniya


def rms(block) -> float:
    import numpy as np

    return float(np.sqrt(np.mean(np.square(block), dtype="float64")))


class Segmenter:
    """Bloklar oqimidan bitta gapni ajratadi (mikrofonsiz test qilish mumkin)."""

    def __init__(
        self,
        silence_seconds: float = 1.2,
        start_timeout: float = 6.0,
        max_seconds: float = 20.0,
        calibration_blocks: int = 3,
    ):
        self.silence_blocks = int(silence_seconds * SAMPLE_RATE / BLOCK)
        self.start_blocks = int(start_timeout * SAMPLE_RATE / BLOCK)
        self.max_blocks = int(max_seconds * SAMPLE_RATE / BLOCK)
        self.calibration_blocks = calibration_blocks
        self.noise: list[float] = []
        self.blocks: list = []
        self.started = False
        self.quiet = 0
        self.seen = 0

    @property
    def threshold(self) -> float:
        floor = sum(self.noise) / len(self.noise) if self.noise else 0.0
        return max(0.012, floor * 3)

    def feed(self, block) -> bool:
        """Blokni qo'shadi; yozishni to'xtatish kerak bo'lsa True qaytaradi."""
        self.seen += 1
        level = rms(block)
        if len(self.noise) < self.calibration_blocks and not self.started:
            self.noise.append(level)
            self.blocks.append(block)
            return False
        loud = level > self.threshold
        if not self.started:
            self.blocks = self.blocks[-3:] + [block]  # gap boshidan oldingi 0.3 s ham qolsin
            if loud:
                self.started = True
            return self.seen >= self.start_blocks
        self.blocks.append(block)
        self.quiet = 0 if loud else self.quiet + 1
        return self.quiet >= self.silence_blocks or len(self.blocks) >= self.max_blocks

    def audio(self):
        import numpy as np

        if not self.started or not self.blocks:
            return np.zeros(0, dtype="float32")
        return np.concatenate(self.blocks).astype("float32")


def record_utterance(stop: threading.Event | None = None, **kwargs):
    """Bitta gapni yozib, 16 kHz mono float32 massiv qaytaradi (gap bo'lmasa — bo'sh)."""
    import sounddevice as sd

    seg = Segmenter(**kwargs)
    blocks: queue.Queue = queue.Queue()

    def callback(indata, frames, time, status):  # noqa: ARG001
        blocks.put(indata[:, 0].copy())

    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=BLOCK, callback=callback
    ):
        while not (stop and stop.is_set()):
            try:
                block = blocks.get(timeout=1)
            except queue.Empty:
                continue
            if seg.feed(block):
                break
    if stop and stop.is_set():
        seg.started = seg.started or bool(seg.blocks)
    return seg.audio()
