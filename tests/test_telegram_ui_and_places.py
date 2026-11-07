import asyncio

import pytest

from jarvis.core import commands
from jarvis.core.commands import on_location, pop_extras, run_command
from jarvis.tools import macos, places, telegram_ui


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clean_state():
    for d in (commands.PENDING, commands.EXTRAS, commands.LAST_LOCATION,
              commands.AWAIT_LOCATION, commands.AWAIT_NAME):  # fmt: skip
        d.clear()
    yield


# ---------- Telegram ekran orqali (soxta UI) ----------


@pytest.fixture
def fake_ui(monkeypatch):
    log = []
    state = {"title": "Ali Valiyev"}

    async def draft(name, message):
        log.append(("draft", name, message))
        return telegram_ui.Draft(chat_title=state["title"])

    async def send():
        log.append(("send",))

    async def clear():
        log.append(("clear",))

    monkeypatch.setattr(telegram_ui, "open_chat_and_draft", draft)
    monkeypatch.setattr(telegram_ui, "press_send", send)
    monkeypatch.setattr(telegram_ui, "clear_draft", clear)
    monkeypatch.setattr(commands, "_telegram_backend", lambda: "ui")
    return log, state


def test_ui_drafts_then_sends_only_after_yes(fake_ui):
    log, _ = fake_ui

    async def flow():
        q = await run_command("Telegramni ochib Aliga salom deb yubor", "s")
        assert log == [("draft", "Ali", "salom")]  # faqat qoralama
        assert "«Ali Valiyev» chati ochildi" in q and "Diqqat" not in q
        return await run_command("Ha", "s")

    assert run(flow()) == "✅ Yuborildi → Ali Valiyev: «salom»"
    assert log == [("draft", "Ali", "salom"), ("send",)]


def test_ui_cancel_clears_draft(fake_ui):
    log, _ = fake_ui

    async def flow():
        await run_command("Aliga salom deb yubor", "s")
        return await run_command("Yo'q", "s")

    assert run(flow()) == "Bekor qilindi."
    assert ("send",) not in log and ("clear",) in log


def test_ui_warns_when_wrong_chat_opened(fake_ui):
    _, state = fake_ui
    state["title"] = "My Soul🫀"
    q = run(run_command("Aliga salom deb yubor", "s"))
    assert "⚠️ Diqqat" in q and "My Soul🫀" in q


def test_ui_error_is_reported_without_pending(fake_ui, monkeypatch):
    async def broken(name, message):
        raise telegram_ui.TelegramUIError("JARVIS'ga Accessibility ruxsati kerak")

    monkeypatch.setattr(telegram_ui, "open_chat_and_draft", broken)
    assert "Accessibility" in run(run_command("Aliga salom deb yubor", "s"))
    assert "s" not in commands.PENDING


# ---------- Joylar ----------


@pytest.mark.parametrize(
    "text, action, name",
    [
        ("Turgan joyimni Pismadonchani uyi deb saqla", "save", "Pismadonchani uyi"),
        ("turgan joyim pismadonchani uyi saqlab qo'y", "save", "Pismadonchani uyi"),
        ("Jarvis, shu yerni Ali akaning uyi deb eslab qol", "save", "Ali akaning uyi"),
        ("Bu joyni ofis deb saqla", "save", "Ofis"),
        ("Сохрани это место как дом Али", "save", "Дом Али"),
        ("Pismadonchani uyiga qanday boraman?", "go", "Pismadonchani uyi"),
        ("Pismadonchani uyiga yo'l ko'rsat", "go", "Pismadonchani uyi"),
        ("Ofisga yo'l", "go", "Ofis"),
        ("Saqlangan joylar", "list", None),
    ],
)
def test_place_parse(text, action, name):
    assert commands._place_match(text) == (action, name)


def test_where_is_only_for_saved_places():
    assert commands._place_match("Telefonim qayerda") is None
    places.save("Ofis", 41.3, 69.2)
    assert commands._place_match("Ofis qayerda?") == ("go", "Ofis")


def test_place_rules_do_not_steal_other_commands():
    assert commands.match("Obsidian'ga yoz: non olish")[0].name == "obsidian.write"
    assert commands.match("Eslatma: non olish")[0].name == "notes.add"
    assert commands.match("Aliga salom deb yubor")[0].name == "telegram.send"


def test_say_then_share_location_on_phone():
    async def flow():
        reply = await run_command("Turgan joyimni Pismadonchani uyi deb saqla", "tg:1")
        assert "📍" in reply and pop_extras("tg:1") == [("request_location",)]
        return on_location("tg:1", 41.311081, 69.240562)

    reply = run(flow())
    assert "«Pismadonchani uyi» saqlandi" in reply
    assert pop_extras("tg:1") == [("done",)]
    p = places.find("pismadonchani uyi")
    assert (p.lat, p.lon) == (41.311081, 69.240562)


def test_share_location_then_say_name():
    first = on_location("tg:1", 41.0, 69.0)
    assert "Qanday nom bilan" in first
    reply = run(run_command("Pismadonchani uyi", "tg:1"))
    assert "«Pismadonchani uyi» saqlandi" in reply
    assert places.find("Pismadonchani uyi").lat == 41.0


def test_recent_location_is_used_directly():
    on_location("tg:1", 40.0, 70.0)
    run(run_command("Turgan joyimni ofis deb saqla", "tg:1"))
    assert places.find("ofis").lon == 70.0


def test_said_on_mac_saved_from_phone():
    reply = run(run_command("Turgan joyimni dacha deb saqla", "app"))
    assert "telefondan" in reply
    assert "saqlandi" in on_location("tg:1", 41.5, 69.5)
    assert places.find("Dacha") is not None


def test_directions_on_phone_send_pin():
    places.save("Pismadonchani uyi", 41.311081, 69.240562)
    reply = run(run_command("Pismadonchani uyiga yo'l ko'rsat", "tg:1"))
    assert "Start" in reply
    assert pop_extras("tg:1") == [("location", 41.311081, 69.240562, "Pismadonchani uyi")]


def test_directions_on_mac_open_maps(monkeypatch):
    opened = []

    async def fake_open(args):
        opened.append(args.url)

    monkeypatch.setattr(macos, "open_url", fake_open)
    places.save("Ofis", 41.3, 69.2)
    assert "xaritada" in run(run_command("Ofisga yo'l ko'rsat", "app"))
    assert opened == ["https://www.google.com/maps/dir/?api=1&destination=41.3,69.2"]


def test_unknown_place():
    assert "saqlanmagan" in run(run_command("Dachaga yo'l ko'rsat", "tg:1"))


def test_list_and_resave_updates():
    places.save("Ofis", 1, 2)
    p, existed = places.save("ofis", 3, 4)
    assert existed and places.find("Ofis").lat == 3
    assert "• ofis" in run(run_command("Saqlangan joylar", "app")).lower()


def test_invalid_coordinates():
    with pytest.raises(ValueError):
        places.save("x", 200, 0)


def test_links():
    p = places.Place("A", 41.3, 69.2, "")
    assert p.google.endswith("destination=41.3,69.2")
    assert "rtext=~41.3,69.2" in p.yandex
