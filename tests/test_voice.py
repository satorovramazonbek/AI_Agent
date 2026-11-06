import asyncio

from fastapi.testclient import TestClient

from jarvis.interfaces import api
from jarvis.voice import intents
from jarvis.voice.stt import Transcriber, Transcript, VoiceUnavailable


def run(coro):
    return asyncio.run(coro)


def test_status_intent_uzbek():
    reply = run(intents.handle_text("Kompyuterning holati qanday?"))
    assert "CPU" in reply and "Disk" in reply


def test_status_intent_russian():
    assert "CPU" in run(intents.handle_text("Какое состояние системы"))


def test_computer_word_alone_is_not_status():
    assert "CPU" not in run(intents.handle_text("Kompyuterni o'chir"))


def test_unknown_text_echoed():
    reply = run(intents.handle_text("Ertaga soat beshda uchrashuv"))
    assert "Ertaga soat beshda uchrashuv" in reply


def test_empty_text():
    assert "eshitilmadi" in run(intents.handle_text("   "))


class FakeTranscriber:
    async def transcribe(self, path, language=None):
        assert path.read_bytes() == b"fake-audio"
        return Transcript(text="holat qanday", language=language or "uz", duration=1.2)


class BrokenTranscriber:
    async def transcribe(self, path, language=None):
        raise VoiceUnavailable("o'rnatilmagan")


def test_transcribe_endpoint(monkeypatch):
    monkeypatch.setattr(api, "get_transcriber", lambda: FakeTranscriber())
    r = TestClient(api.app).post(
        "/voice/transcribe", files={"file": ("v.ogg", b"fake-audio", "audio/ogg")}
    )
    body = r.json()
    assert r.status_code == 200
    assert body["text"] == "holat qanday"
    assert "CPU" in body["reply"]


def test_transcribe_endpoint_without_voice_module(monkeypatch):
    monkeypatch.setattr(api, "get_transcriber", lambda: BrokenTranscriber())
    r = TestClient(api.app).post("/voice/transcribe", files={"file": ("v.ogg", b"x")})
    assert r.status_code == 503


def test_missing_dependency_raises_voice_unavailable(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "faster_whisper":
            raise ImportError
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    try:
        Transcriber("tiny", "uz")._load()
    except VoiceUnavailable:
        pass
    else:
        raise AssertionError("VoiceUnavailable kutilgan edi")
