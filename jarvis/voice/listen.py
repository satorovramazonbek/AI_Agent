"""Mac mikrofoni orqali ovozli buyruq (push-to-talk): `jarvis-voice`.

Enter — gapirishni boshlash, yana Enter — to'xtatish. Audio lokal Whisper'da matnga o'giriladi.
Birinchi ishga tushirishda macOS Terminal'ga mikrofon ruxsatini so'raydi.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from jarvis.voice.intents import handle_text
from jarvis.voice.stt import Transcriber, VoiceUnavailable, get_transcriber

SAMPLE_RATE = 16_000  # Whisper kutadigan chastota


def record_until_enter():
    import numpy as np
    import sounddevice as sd

    chunks: list = []

    def callback(indata, frames, time, status):  # noqa: ARG001
        chunks.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback):
        input("🔴 Yozilmoqda... tugatish uchun Enter bosing ")
    if not chunks:
        return np.zeros(0, dtype="float32")
    return np.concatenate(chunks)[:, 0]


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS: mikrofon orqali ovozli buyruq")
    parser.add_argument("--language", help="til kodi: uz, ru, en (standart: JARVIS_STT_LANGUAGE)")
    parser.add_argument("--model", help="Whisper modeli (standart: JARVIS_STT_MODEL)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        import sounddevice  # noqa: F401
    except ImportError:
        sys.exit('sounddevice o\'rnatilmagan: pip install -e ".[voice]"')

    transcriber = get_transcriber()
    if args.model:
        transcriber = Transcriber(args.model, args.language or transcriber.language)
    try:
        transcriber._load()  # modelni oldindan yuklab, birinchi javobni tezlashtiramiz
    except VoiceUnavailable as e:
        sys.exit(str(e))

    print("JARVIS tinglashga tayyor. Ctrl+C — chiqish.")
    try:
        asyncio.run(_listen_loop(transcriber, args.language))
    except (KeyboardInterrupt, EOFError):
        print("\nXayr!")


async def _listen_loop(transcriber: Transcriber, language: str | None) -> None:
    # Bitta event loop: API klienti va suhbat xotirasi gaplar orasida saqlanib qoladi.
    while True:
        await asyncio.to_thread(input, "\n🎙  Gapirish uchun Enter bosing ")
        audio = await asyncio.to_thread(record_until_enter)
        if len(audio) < SAMPLE_RATE // 2:
            print("Juda qisqa yozuv, qaytadan urinib ko'ring.")
            continue
        t = await transcriber.transcribe(audio, language)
        mark = " (?) — aniq eshitmadim" if t.unsure else ""
        print(f"📝 Siz: {t.text or '(eshitilmadi)'}  [{t.language}, {t.confidence:.0%}]{mark}")
        print(f"🤖 JARVIS: {await handle_text(t.text, 'mic')}")


if __name__ == "__main__":
    main()
