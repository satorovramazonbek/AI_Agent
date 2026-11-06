"""Lokal boshqaruv API'si (FastAPI): holat, tool'lar ro'yxati, siyosat tekshiruvi."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from pydantic import BaseModel

from jarvis import __version__
from jarvis.config import get_settings
from jarvis.security.policy import CommandPolicy
from jarvis.tools import system  # noqa: F401  (tool'larni ro'yxatga olish uchun)
from jarvis.tools.registry import registry
from jarvis.voice.intents import handle_text
from jarvis.voice.stt import VoiceUnavailable, get_transcriber

app = FastAPI(title="JARVIS", version=__version__)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__, "env": get_settings().env}


@app.get("/tools")
async def list_tools() -> list[dict]:
    return [{**t.schema(), "risk": t.risk.name, "tags": t.tags} for t in registry.list()]


class PolicyCheck(BaseModel):
    command: str
    remote: bool = False


@app.post("/policy/check")
async def policy_check(body: PolicyCheck) -> dict:
    policy = CommandPolicy.from_file(get_settings().policy_file)
    result = policy.check(body.command, remote=body.remote)
    return {"decision": result.decision, "risk": result.risk.name, "reasons": result.reasons}


@app.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile, language: str | None = None) -> dict:
    """Audio faylni matnga o'giradi va unga JARVIS javobini qaytaradi."""
    suffix = Path(file.filename or "audio").suffix or ".ogg"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(await file.read())
        try:
            t = await get_transcriber().transcribe(path, language)
        except VoiceUnavailable as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
    return {
        "text": t.text,
        "language": t.language,
        "duration": t.duration,
        "reply": await handle_text(t.text),
    }
