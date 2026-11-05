"""Birinchi tool'lar: tizim holati va xavfsiz terminal buyrug'i."""

from __future__ import annotations

import asyncio
import os
import platform
import shutil

from pydantic import BaseModel, Field

from jarvis.config import get_settings
from jarvis.security.policy import CommandPolicy, Decision, Risk
from jarvis.tools.registry import tool


class NoArgs(BaseModel):
    pass


@tool(
    name="system.status",
    description="Kompyuter holati: OT, CPU yadrolari, yuklama, disk joyi",
    risk=Risk.R0,
    tags=["macos", "system"],
)
async def system_status(args: NoArgs) -> dict:
    total, used, free = shutil.disk_usage("/")
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu_count": os.cpu_count(),
        "load_avg_1m": round(load[0], 2),
        "disk_free_gb": round(free / 1e9, 1),
        "disk_used_pct": round(used / total * 100, 1),
    }


class ShellArgs(BaseModel):
    command: str = Field(description="Bajariladigan terminal buyrug'i")
    cwd: str | None = Field(default=None, description="Ishchi papka")


@tool(
    name="shell.run",
    description="Terminal buyrug'ini Policy Gateway orqali bajaradi",
    risk=Risk.R1,
    tags=["macos", "dev"],
    timeout=60,
)
async def shell_run(args: ShellArgs, *, approved: bool = False) -> dict:
    settings = get_settings()
    policy = CommandPolicy.from_file(settings.policy_file)
    result = policy.check(args.command)

    if result.decision == Decision.DENY:
        return {"status": "denied", "risk": result.risk.name, "reasons": result.reasons}
    if result.decision == Decision.CONFIRM and not approved:
        return {"status": "needs_approval", "risk": result.risk.name, "reasons": result.reasons}

    proc = await asyncio.create_subprocess_shell(
        args.command,
        cwd=args.cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
    except TimeoutError:
        proc.kill()
        return {"status": "timeout", "risk": result.risk.name}
    return {
        "status": "ok",
        "exit_code": proc.returncode,
        "stdout": out.decode(errors="replace")[-4000:],
        "stderr": err.decode(errors="replace")[-2000:],
        "risk": result.risk.name,
    }
