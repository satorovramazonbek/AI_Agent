"""Testlar hech qachon haqiqiy dunyoga tegmaydi: API, Telegram, ekran, macOS buyruqlari, fayllar.

Biror test buni tasodifan qilmoqchi bo'lsa, `RealWorldTouched` bilan darhol yiqiladi.
Kerakli joyda test o'zining soxta (fake) funksiyasini monkeypatch bilan qo'yadi.
"""

from types import SimpleNamespace

import pytest

from jarvis.tools import macos as _macos
from jarvis.tools import telegram_user as _telegram_user

# Asl funksiyalar — aynan shularni tekshiradigan testlar uchun (`from tests.conftest import ORIG`).
ORIG = {
    "notes_file": _macos.notes_file,
    "obsidian_vault": _macos.obsidian_vault,
    "get_client": _telegram_user.get_client,
}


class RealWorldTouched(AssertionError):
    pass


def _forbid(what):
    def guard(*args, **kwargs):
        raise RealWorldTouched(f"test haqiqiy {what} ni chaqirdi: {args!r}")

    async def aguard(*args, **kwargs):
        guard(*args, **kwargs)

    return guard, aguard


@pytest.fixture(autouse=True)
def no_real_world(monkeypatch, tmp_path):
    from jarvis.tools import contacts, macos, places, telegram_ui, telegram_user

    # Claude API
    monkeypatch.setattr("jarvis.voice.intents.get_agent", lambda: SimpleNamespace(available=False))
    # Telegram ekran orqali (Accessibility, klaviatura)
    for name in ("_open_chat_and_draft", "_press_send", "_clear_draft", "_activate", "_key"):
        monkeypatch.setattr(telegram_ui, name, _forbid(f"telegram_ui.{name}")[0])
    # Telegram API (Telethon)
    monkeypatch.setattr(telegram_user, "get_client", _forbid("telegram_user.get_client")[1])
    # macOS buyruqlari (open, osascript, pmset, screencapture…)
    monkeypatch.setattr(macos, "_run", _forbid("macos._run")[1])
    # Fayllar: joylar va eslatmalar vaqtinchalik papkada
    monkeypatch.setattr(places, "store_path", lambda: tmp_path / "places.json")
    monkeypatch.setattr(macos, "obsidian_vault", lambda: None)
    monkeypatch.setattr(macos, "notes_file", lambda: tmp_path / "eslatmalar.md")
    # Ismlar: haqiqiy Mac Kontaktlari o'qilmaydi, eslab qolinganlar vaqtinchalik faylda
    monkeypatch.setattr(contacts, "mac_contacts", lambda request=False: [])
    monkeypatch.setattr(contacts, "chats_file", lambda: tmp_path / "known_chats.json")
    monkeypatch.setattr(contacts, "_cache", None)
