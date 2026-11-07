import asyncio

import pytest

from jarvis.core import commands
from jarvis.core.commands import fix_message, run_command
from jarvis.tools import contacts, telegram_ui

NAMES = ["O'ktam Rahimov", "Oybek", "Sardor Psixolog", "Ali Valiyev", "Alisher Yusupov"]


@pytest.mark.parametrize(
    "spoken, expected",
    [
        ("oktan", "O'ktam Rahimov"),  # haqiqiy logdan: «O'ktamga» → «oktanga»
        ("Öktan", "O'ktam Rahimov"),
        ("o'ktam", "O'ktam Rahimov"),
        ("sardor", "Sardor Psixolog"),
        ("Oybek", "Oybek"),
        ("Bahodir", None),  # tanish emas — o'zgarmaydi
        ("ali", "Ali Valiyev"),  # ism aniq mos — «Alisher» emas
    ],
)
def test_best_match(spoken, expected):
    assert contacts.best_match(spoken, NAMES) == expected


def test_same_first_name_is_not_guessed():
    assert contacts.best_match("jasur", ["Jasur Toshev", "Jasur Rahimov"]) is None


@pytest.mark.parametrize(
    "raw, fixed",
    [
        ("salon", "salom"),
        ("Salon, qalesan?", "Salom, qalaysan?"),
        ("ertega kelaman, raxmat", "ertaga kelaman, rahmat"),
        ("Assalom aleykum", "Assalomu alaykum"),
        ("salonga boraman", "salonga boraman"),  # butun so'z emas — tegilmaydi
    ],
)
def test_fix_message(raw, fixed):
    assert fix_message(raw) == fixed


def test_remember_and_hotwords():
    contacts.remember("O'ktam Rahimov")
    contacts.remember("O'ktam Rahimov")  # takror yozilmaydi
    contacts._cache = None
    assert contacts.learned_names() == ["O'ktam Rahimov"]
    assert "O'ktam" in contacts.hotwords() and "Rahimov" in contacts.hotwords()


def test_voice_sample_end_to_end(monkeypatch):
    """«Telegram'dan oktanga salon de bibor.» → O'ktam'ga «salom»; yuborilgach eslab qolinadi."""
    contacts.remember("O'ktam Rahimov")
    contacts._cache = None
    log = []

    async def draft(name, message):
        log.append(("draft", name, message))
        return telegram_ui.Draft(chat_title="O'ktam Rahimov")

    async def send():
        log.append(("send",))

    monkeypatch.setattr(telegram_ui, "open_chat_and_draft", draft)
    monkeypatch.setattr(telegram_ui, "press_send", send)
    monkeypatch.setattr(commands, "_telegram_backend", lambda: "ui")
    commands.PENDING.clear()

    async def flow():
        q = await run_command("Telegram'dan oktanga salon de bibor.", "s")
        assert log == [("draft", "O'ktam Rahimov", "salom")]
        assert "«oktan» deb eshitdim → «O'ktam Rahimov»" in q and "Diqqat" not in q
        return await run_command("Ha", "s")

    assert asyncio.run(flow()) == "✅ Yuborildi → O'ktam Rahimov: «salom»"
