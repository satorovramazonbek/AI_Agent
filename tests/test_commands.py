import asyncio

import pytest

from jarvis.core import commands
from jarvis.core.commands import match, normalize, run_command
from jarvis.tools import macos

APPS = {
    "safari": "Safari",
    "google chrome": "Google Chrome",
    "telegram": "Telegram",
    "calculator": "Calculator",
    "visual studio code": "Visual Studio Code",
    "system settings": "System Settings",
    "яндекс музыка": "Яндекс Музыка",
    "photos": "Photos",
    "discord": "Discord",
}


def run(coro):
    return asyncio.run(coro)


def rule_of(text):
    found = match(text)
    return found[0].name if found else None


# ---------- normallashtirish ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Safari'ni och.", "safarini och"),
        ("Jarvis, ovozni ko‘tar!", "ovozni kotar"),
        ("Сафарини оч", "safarini och"),
        ("Сколько времени?", "skolko vremeni"),
        ("  Hey Jarvis   soat necha? ", "soat necha"),
    ],
)
def test_normalize(raw, expected):
    assert normalize(raw) == expected


# ---------- qoidalarni tanlash ----------


@pytest.mark.parametrize(
    "text, rule",
    [
        ("Safari'ni och", "app.open"),
        ("Jarvis, brauzerni ochib ber", "app.open"),
        ("Telegram ilovasini ishga tushir", "app.open"),
        ("Открой телеграм", "app.open"),
        ("Сафарини оч", "app.open"),
        ("Telegram'ni yop", "app.quit"),
        ("Safarini o'chir", "app.quit"),
        ("Ovozni ko'tar", "volume.up"),
        ("ovozni balandroq qil", "volume.up"),
        ("Ovozni pasaytir", "volume.down"),
        ("Громче", "volume.up"),
        ("Ovozni o'chir", "volume.mute"),
        ("Ovozni yoq", "volume.unmute"),
        ("Ovozni 40 ga qo'y", "volume.set"),
        ("Soat necha?", "time"),
        ("Сколько времени", "time"),
        ("Bugun nechanchi?", "date"),
        ("Batareya qancha?", "battery"),
        ("Zaryad qancha qoldi", "battery"),
        ("Kompyuterning holati qanday", "status"),
        ("Ekranni qulfla", "lock"),
        ("Eslatma: non olish", "notes.add"),
        ("Jarvis, yozib qo'y: ertaga 9 da uchrashuv", "notes.add"),
        ("Eslatmalarimni o'qi", "notes.list"),
        ("Nima qila olasan?", "help"),
        ("Bugun ob-havo yaxshimi", None),
        ("Menga she'r yozib ber", None),
    ],
)
def test_rule_selection(text, rule):
    assert rule_of(text) == rule


# ---------- dastur nomini aniqlash ----------


@pytest.mark.parametrize(
    "spoken, app",
    [
        ("brauzer", "Safari"),
        ("safari", "Safari"),
        ("chrome", "Google Chrome"),
        ("xrom", "Google Chrome"),
        ("telegramm", "Telegram"),
        ("kalkulyator", "Calculator"),
        ("vs kod", "Visual Studio Code"),
        ("sozlamalar", "System Settings"),
        ("yandeks muzika", "Яндекс Музыка"),
        ("photoshop", None),  # o'rnatilmagan; "Photos" ga adashmasligi kerak
        ("telegarm", "Telegram"),  # Whisper imlo xatosi
        ("discort", "Discord"),
    ],
)
def test_resolve_app(spoken, app):
    assert macos.resolve_app(spoken, APPS) == app


def test_app_suffix_stripped():
    assert commands._app_name("safarini") == "safari"
    assert commands._app_name("telegram ilovasini") == "telegram"


# ---------- bajarish (macOS buyruqlari soxtalashtirilgan) ----------


BATT = (
    "Now drawing from 'Battery Power'\n"
    " -InternalBattery-0\t53%; discharging; 5:53 remaining present: true"
)


@pytest.fixture
def fake_mac(monkeypatch):
    calls = []
    state = {"volume": 30, "muted": "false"}

    async def fake_run(*args, timeout=15):
        calls.append(args)
        if args[:2] == ("pmset", "-g"):
            return 0, BATT, ""
        return 0, "", ""

    async def fake_osascript(script):
        calls.append(("osascript", script))
        if script.startswith("output volume"):
            return str(state["volume"])
        if script.startswith("output muted"):
            return state["muted"]
        if script.startswith("set volume output volume"):
            state["volume"] = int(script.rsplit(" ", 1)[1])
        if script == "set volume with output muted":
            state["muted"] = "true"
        return ""

    monkeypatch.setattr(macos, "_run", fake_run)
    monkeypatch.setattr(macos, "_osascript", fake_osascript)
    monkeypatch.setattr(macos, "installed_apps", lambda: APPS)
    return calls, state


def test_open_app_runs_open(fake_mac):
    calls, _ = fake_mac
    assert run(run_command("Brauzerni och")) == "Safari ochildi."
    assert ("open", "-a", "Safari") in calls


def test_unknown_app(fake_mac):
    assert "topilmadi" in run(run_command("Photoshopni och"))


def test_volume_up_and_set(fake_mac):
    _, state = fake_mac
    assert run(run_command("Ovozni ko'tar")) == "Ovoz 40%."
    assert run(run_command("Ovozni 75 ga qo'y")) == "Ovoz 75%."
    assert state["volume"] == 75


def test_volume_out_of_range(fake_mac):
    assert "0 dan 100" in run(run_command("Ovozni 150 ga qo'y"))


def test_mute(fake_mac):
    assert run(run_command("Ovozni o'chir")) == "Ovoz o'chirildi."


def test_battery(fake_mac):
    assert run(run_command("Batareya qancha")) == (
        "Batareya 53%, batareyadan ishlayapti, taxminan 5:53 qoldi."
    )


def test_notes_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(macos, "notes_file", lambda: tmp_path / "eslatmalar.md")
    assert "non olish" in run(run_command("Eslatma: non olish"))
    run(run_command("Yozib qo'y: sut olish"))
    reply = run(run_command("Eslatmalarimni o'qi"))
    assert "2 ta" in reply and "non olish" in reply and "sut olish" in reply


def test_not_on_mac(monkeypatch):
    monkeypatch.setattr(macos.sys, "platform", "linux")
    assert "faqat Mac'da" in run(run_command("Batareya qancha"))


def test_unknown_returns_none():
    assert run(run_command("Menga she'r yozib ber")) is None
