"""Lokal boshqaruv API'si (FastAPI): holat, tool'lar ro'yxati, siyosat tekshiruvi."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from jarvis import __version__
from jarvis.config import get_settings
from jarvis.security.policy import CommandPolicy
from jarvis.tools import system  # noqa: F401  (tool'larni ro'yxatga olish uchun)
from jarvis.tools.registry import registry

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
