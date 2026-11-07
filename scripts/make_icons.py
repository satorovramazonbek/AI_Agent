"""JARVIS belgilarini chizadi (tashqi kutubxonasiz, sof Python PNG).

- jarvis/assets/menubar.png — menyu paneli uchun shablon belgi (qora halqa, shaffof fon)
- build/JARVIS.iconset/ — ilova belgisi o'lchamlari (keyin `iconutil` .icns ga aylantiradi)
"""

from __future__ import annotations

import math
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def write_png(path: Path, size: int, pixel) -> None:
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            r, g, b, a = pixel((x + 0.5) / size, (y + 0.5) / size)
            rows += bytes((int(r), int(g), int(b), int(a)))

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + data))
        return struct.pack(">I", len(data)) + kind + data + crc

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(rows), 9))
    png += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def smooth(edge: float, x: float, width: float) -> float:
    """0..1 yumshoq o'tish (chetlari silliq bo'lishi uchun)."""
    return max(0.0, min(1.0, 0.5 - (x - edge) / width))


def app_pixel(u: float, v: float):
    # Yumaloq burchakli kvadrat (macOS belgisi shakli)
    m, rad = 0.09, 0.2
    qx = max(abs(u - 0.5) - (0.5 - m - rad), 0.0)
    qy = max(abs(v - 0.5) - (0.5 - m - rad), 0.0)
    inside = smooth(rad, math.hypot(qx, qy), 0.004)
    if inside <= 0:
        return 0, 0, 0, 0
    d = math.hypot(u - 0.5, v - 0.5)
    # Fon: to'q ko'k, markazga qarab biroz yorug'roq
    bg = (11 + 22 * (1 - d), 18 + 30 * (1 - d), 34 + 50 * (1 - d))
    # Halqa va uning nuri
    ring = math.exp(-(((d - 0.25) / 0.022) ** 2))
    glow = math.exp(-(((d - 0.25) / 0.09) ** 2)) * 0.45
    core = math.exp(-((d / 0.07) ** 2))
    light = min(1.0, ring + glow + core)
    cyan = (90, 220, 255)
    r, g, b = (bg[i] * (1 - light) + cyan[i] * light for i in range(3))
    white = max(ring, core) ** 3  # eng yorug' joylari oqqa yaqin
    r, g, b = (c + (255 - c) * white * 0.6 for c in (r, g, b))
    return r, g, b, 255 * inside


def menubar_pixel(u: float, v: float):
    d = math.hypot(u - 0.5, v - 0.5)
    ring = smooth(0.06, abs(d - 0.32), 0.03)
    dot = smooth(0.12, d, 0.03)
    return 0, 0, 0, 255 * max(ring, dot)


def main() -> None:
    write_png(ROOT / "jarvis" / "assets" / "menubar.png", 44, menubar_pixel)
    iconset = ROOT / "build" / "JARVIS.iconset"
    big = iconset / "icon_512x512@2x.png"
    write_png(big, 1024, app_pixel)
    for s in (16, 32, 128, 256, 512):
        for scale, name in ((1, f"icon_{s}x{s}.png"), (2, f"icon_{s}x{s}@2x.png")):
            px = s * scale
            if px == 1024:
                continue
            subprocess.run(
                ["sips", "-z", str(px), str(px), str(big), "--out", str(iconset / name)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
    print("belgilar tayyor:", iconset)


if __name__ == "__main__":
    sys.exit(main())
