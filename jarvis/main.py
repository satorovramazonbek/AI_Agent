"""JARVIS kirish nuqtasi: API serveri va Telegram botni bitta asyncio jarayonida ishga tushiradi."""

from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from jarvis.config import get_settings
from jarvis.interfaces.api import app
from jarvis.interfaces.telegram_bot import run_bot


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host=os.getenv("JARVIS_HOST", "127.0.0.1"), port=8000, log_level="info")
    )
    await asyncio.gather(server.serve(), run_bot())


if __name__ == "__main__":
    asyncio.run(main())
