"""Saqlangan joylar: «Pismadonchani uyi» → koordinata → xaritada yo'l.

Joylashuv telefondan Telegram bot orqali keladi (GPS — aniq). Joylar
~/Library/Application Support/JARVIS/places.json da saqlanadi va Obsidian'da ko'rinishi uchun
<vault>/JARVIS/Joylar.md ga ham yoziladi. Hech qanday pullik API ishlatilmaydi.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from jarvis.config import get_settings


@dataclass
class Place:
    name: str
    lat: float
    lon: float
    saved_at: str

    @property
    def google(self) -> str:
        return f"https://www.google.com/maps/dir/?api=1&destination={self.lat},{self.lon}"

    @property
    def yandex(self) -> str:
        return f"https://yandex.uz/maps/?rtext=~{self.lat},{self.lon}&rtt=auto"


def store_path() -> Path:
    return get_settings().places_file


def _key(name: str) -> str:
    from jarvis.tools.telegram_user import name_key

    return name_key(name)


def load() -> dict[str, Place]:
    path = store_path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: Place(**v) for k, v in data.items()}


def _write(places: dict[str, Place]) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({k: asdict(p) for k, p in places.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)
    _write_obsidian(places)


def _write_obsidian(places: dict[str, Place]) -> None:
    from jarvis.tools import macos

    vault = macos.obsidian_vault()
    if vault is None:
        return
    lines = ["# Saqlangan joylar", "", "JARVIS avtomatik yangilaydi.", ""]
    for p in sorted(places.values(), key=lambda p: p.name.lower()):
        lines.append(
            f"- **{p.name}** — [Google xarita]({p.google}) · [Yandex]({p.yandex}) "
            f"· `{p.lat:.6f}, {p.lon:.6f}` · {p.saved_at}"
        )
    target = vault / "JARVIS" / "Joylar.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save(name: str, lat: float, lon: float) -> tuple[Place, bool]:
    """(joy, avval bormidi). Bir xil nom qayta saqlansa — yangilanadi."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("noto'g'ri koordinata")
    places = load()
    key = _key(name)
    existed = key in places
    place = Place(name.strip(), round(lat, 6), round(lon, 6), f"{datetime.now():%Y-%m-%d %H:%M}")
    places[key] = place
    _write(places)
    return place, existed


def find(name: str) -> Place | None:
    places = load()
    key = _key(name)
    if key in places:
        return places[key]
    close = difflib.get_close_matches(key, list(places), n=1, cutoff=0.75)
    return places[close[0]] if close else None


def delete(name: str) -> Place | None:
    places = load()
    place = find(name)
    if place is None:
        return None
    places.pop(_key(place.name), None)
    _write(places)
    return place
