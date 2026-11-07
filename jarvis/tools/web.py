"""Bepul internet tool'lari (API kalitsiz): ob-havo (wttr.in), internet tekshiruvi, qidiruv."""

from __future__ import annotations

import asyncio
import json
import socket
import ssl
import time
import urllib.request
from urllib.parse import quote_plus

from pydantic import BaseModel, Field

from jarvis.config import get_settings
from jarvis.security.policy import Risk
from jarvis.tools.registry import tool

WEATHER_UZ = {
    "sunny": "quyoshli", "clear": "ochiq osmon", "partly cloudy": "qisman bulutli",
    "cloudy": "bulutli", "overcast": "qalin bulutli", "mist": "tuman", "fog": "tuman",
    "light rain": "yengil yomg'ir", "patchy rain possible": "yomg'ir yog'ishi mumkin",
    "patchy rain nearby": "atrofda yomg'ir", "moderate rain": "yomg'ir",
    "heavy rain": "kuchli yomg'ir",
    "light snow": "yengil qor", "snow": "qor", "heavy snow": "kuchli qor",
    "light drizzle": "mayda yomg'ir", "thundery outbreaks possible": "momaqaldiroq bo'lishi mumkin",
}  # fmt: skip


class WeatherArgs(BaseModel):
    city: str | None = Field(default=None, description="Shahar; bo'sh bo'lsa sozlamadagi")


def _ssl_context() -> ssl.SSLContext:
    # python.org Python'ida tizim sertifikatlari yo'q — certifi to'plamini ishlatamiz.
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _fetch_json(url: str, timeout: float = 8) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8 (JARVIS)"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:  # noqa: S310
        return json.loads(r.read().decode())


@tool(name="web.weather", description="Ob-havo (wttr.in, bepul)", risk=Risk.R0, tags=["web"])
async def weather(args: WeatherArgs) -> dict:
    city = args.city or get_settings().city
    data = await asyncio.to_thread(_fetch_json, f"https://wttr.in/{quote_plus(city)}?format=j1")
    now = data["current_condition"][0]
    today = data["weather"][0]
    desc = now["weatherDesc"][0]["value"].strip()
    return {
        "city": city,
        "temp_c": int(now["temp_C"]),
        "feels_c": int(now["FeelsLikeC"]),
        "desc": WEATHER_UZ.get(desc.lower(), desc),
        "min_c": int(today["mintempC"]),
        "max_c": int(today["maxtempC"]),
    }


def _ping(host: str = "1.1.1.1", port: int = 443, timeout: float = 3) -> float | None:
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return (time.monotonic() - start) * 1000
    except OSError:
        return None


class NoArgs(BaseModel):
    pass


@tool(name="web.internet_check", description="Internet bormi va tezligi", risk=Risk.R0)
async def internet_check(args: NoArgs) -> dict:
    ms = await asyncio.to_thread(_ping)
    return {"online": ms is not None, "latency_ms": round(ms) if ms is not None else None}


def search_url(query: str, site: str = "google") -> str:
    if site == "youtube":
        return f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    return f"https://www.google.com/search?q={quote_plus(query)}"
