import asyncio
from types import SimpleNamespace as NS

import pytest

from jarvis.core import commands
from jarvis.core.commands import _telegram_match, run_command
from jarvis.tools import telegram_user
from jarvis.tools.telegram_user import Contact, _contact_from_user, match_contacts, name_key
from tests.conftest import ORIG


def run(coro):
    return asyncio.run(coro)


def user(id, first, last="", username=None, **kw):
    return NS(id=id, first_name=first, last_name=last, username=username, bot=False,
              is_self=False, deleted=False, **kw)  # fmt: skip


CONTACTS = [
    _contact_from_user(user(1, "Ali", "Valiyev", "ali_v")),
    _contact_from_user(user(2, "Sardor", "Karimov")),
    _contact_from_user(user(3, "Onam")),
    _contact_from_user(user(4, "Aziz aka")),
    _contact_from_user(user(5, "Алишер", "Юсупов")),
    _contact_from_user(user(6, "Jasur", "Toshev")),
    _contact_from_user(user(7, "Jasur", "Rahimov")),
]


# ---------- Gapni tahlil qilish ----------


@pytest.mark.parametrize(
    "text, name, msg",
    [
        ("Telegramni ochib Aliga salom deb yubor", "Ali", "salom"),
        ("Telegram'ni ochib Ali'ga ertaga uchrashamiz deb yoz", "Ali", "ertaga uchrashamiz"),
        ("Sardorga ertaga kelaman deb yozib yubor", "Sardor", "ertaga kelaman"),
        ("Jarvis, onamga tez orada boraman deb ayt", "onam", "tez orada boraman"),
        ("Aziz akaga qalaysiz deb yubor", "Aziz aka", "qalaysiz"),
        ("Telegramda Aliga yoz: soat 5 da kelaman", "Ali", "soat 5 da kelaman"),
        ("Aliga yoz: salom", "Ali", "salom"),
        ("Telegramdan Sardorga yubor hujjatni oldim", "Sardor", "hujjatni oldim"),
        ("Алишерга салом деб ёз", "Алишер", "салом"),
        ("Напиши Али в телеграм привет", "Али", "привет"),
        ("Отправь Сардору сообщение: завтра приду", "Сардору", "завтра приду"),
    ],
)
def test_parse(text, name, msg):
    assert _telegram_match(text) == (name, msg)


@pytest.mark.parametrize(
    "text",
    [
        "Telegramni och",  # faqat ochish
        "Aliga yoz salom",  # telegram so'zi ham, ikki nuqta ham yo'q — shubhali
        "Obsidian'ga yoz: non olish",  # Obsidian buyrug'i
        "Ovozni 40 ga qo'y",
    ],
)
def test_not_a_message(text):
    assert _telegram_match(text) is None


def test_obsidian_and_open_still_win():
    assert commands.match("Obsidian'ga yoz: non olish")[0].name == "obsidian.write"
    assert commands.match("Telegramni och")[0].name == "app.open"


# ---------- Kontaktni topish ----------


@pytest.mark.parametrize(
    "spoken, expected",
    [
        ("Ali", "Ali Valiyev"),
        ("ali valiyev", "Ali Valiyev"),
        ("Sardor", "Sardor Karimov"),
        ("onam", "Onam"),
        ("Aziz aka", "Aziz aka"),
        ("Alisher", "Алишер Юсупов"),  # lotinda aytilgan, kontakt kirillda
        ("Алишер", "Алишер Юсупов"),
        ("ali_v", "Ali Valiyev"),  # username
    ],
)
def test_match_contact(spoken, expected):
    contact, _ = match_contacts(spoken, CONTACTS)
    assert contact is not None and contact.name == expected


def test_ambiguous_contact_asks():
    contact, candidates = match_contacts("Jasur", CONTACTS)
    assert contact is None
    assert {c.name for c in candidates} == {"Jasur Toshev", "Jasur Rahimov"}


def test_unknown_contact():
    assert match_contacts("Bahodir", CONTACTS) == (None, [])


def test_bots_and_self_skipped():
    assert _contact_from_user(user(9, "Bot", bot=False) | {} if False else NS(
        id=9, first_name="X", last_name="", username=None, bot=True, is_self=False, deleted=False
    )) is None


def test_name_key():
    assert name_key("Алишер Юсупов") == "alisher yusupov"
    assert name_key("O‘tkir") == "otkir"


# ---------- Tasdiqlash oqimi: tasdiqsiz hech narsa yuborilmaydi ----------


@pytest.fixture
def fake_tg(monkeypatch):
    sent = []

    async def fake_find(spoken):
        return match_contacts(spoken, CONTACTS)

    async def fake_send(contact, text):
        sent.append((contact.name, text))

    monkeypatch.setattr(telegram_user, "find_contact", fake_find)
    monkeypatch.setattr(telegram_user, "send", fake_send)
    monkeypatch.setattr(commands, "_telegram_backend", lambda: "api")
    commands.PENDING.clear()
    yield sent
    commands.PENDING.clear()


def test_send_requires_confirmation(fake_tg):
    async def flow():
        q = await run_command("Telegramni ochib Aliga salom deb yubor", "s1")
        assert "Ali Valiyev (@ali_v)" in q and "«salom»" in q and "Yuboraymi" in q
        assert fake_tg == []  # hali yuborilmagan
        done = await run_command("Ha", "s1")
        return done

    assert run(flow()) == "✅ Yuborildi → Ali Valiyev: «salom»"
    assert fake_tg == [("Ali Valiyev", "salom")]


def test_cancel(fake_tg):
    async def flow():
        await run_command("Sardorga kelaman deb yoz", "s2")
        return await run_command("Yo'q", "s2")

    assert run(flow()) == "Bekor qilindi."
    assert fake_tg == []


def test_other_command_drops_pending(fake_tg):
    async def flow():
        await run_command("Sardorga kelaman deb yoz", "s3")
        await run_command("Soat necha?", "s3")  # boshqa buyruq
        return await run_command("Ha", "s3")  # endi tasdiqlanadigan narsa yo'q

    run(flow())
    assert fake_tg == []


def test_confirmation_is_per_session(fake_tg):
    async def flow():
        await run_command("Aliga salom deb yubor", "telegram-chat")
        return await run_command("Ha", "boshqa-sessiya")

    run(flow())
    assert fake_tg == []


def test_confirmation_expires(fake_tg, monkeypatch):
    async def flow():
        await run_command("Aliga salom deb yubor", "s4")
        commands.PENDING["s4"].expires = 0
        return await run_command("Ha", "s4")

    run(flow())
    assert fake_tg == []


def test_ambiguous_does_not_ask_to_send(fake_tg):
    reply = run(run_command("Jasurga salom deb yubor", "s5"))
    assert "bir nechta" in reply and "s5" not in commands.PENDING


def test_not_configured(monkeypatch):
    commands.PENDING.clear()
    monkeypatch.setattr(commands, "_telegram_backend", lambda: "api")

    async def not_ready(spoken):
        raise telegram_user.TelegramNotReady("Telegram ulanmagan: ...")

    monkeypatch.setattr(telegram_user, "find_contact", not_ready)
    assert run(run_command("Aliga salom deb yubor")) == "Telegram ulanmagan: ..."


def test_get_client_without_keys(monkeypatch):
    monkeypatch.setattr(
        telegram_user, "get_settings", lambda: NS(tg_api_id=0, tg_api_hash="", tg_session=None)
    )
    with pytest.raises(telegram_user.TelegramNotReady, match="my.telegram.org"):
        run(ORIG["get_client"]())


def test_contact_dataclass_keys():
    c = _contact_from_user(user(1, "Ali", "Valiyev", "ali_v"))
    assert isinstance(c, Contact)
    assert {"ali", "valiyev", "ali valiyev", "ali_v"} == set(c.keys)
