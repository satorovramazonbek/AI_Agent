import asyncio
import json

import pytest

from jarvis.core import commands
from jarvis.core.commands import match, normalize, run_command
from jarvis.tools import macos
from tests.conftest import ORIG

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
        ("Jarvis, skolka времени?", "time"),  # CT2 shunday yozgan
        ("Bugun nechanchi?", "date"),
        ("Batareya qancha?", "battery"),
        ("Zaryad qancha qoldi", "battery"),
        ("Kompyuterning holati qanday", "status"),
        ("Ekranni qulfla", "lock"),
        ("Eslatma: non olish", "notes.add"),
        ("Jarvis, yozib qo'y: ertaga 9 da uchrashuv", "notes.add"),
        ("Eslatmalarimni o'qi", "notes.list"),
        ("Nima qila olasan?", "help"),
        ("Bugun ob-havo yaxshimi", "weather"),
        ("Menga hazil aytib ber", None),
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
    async def linux_run(*args, timeout=15):
        raise macos.MacOnly("bu buyruq faqat Mac'da ishlaydi")

    monkeypatch.setattr(macos, "_run", linux_run)
    assert "faqat Mac'da" in run(run_command("Batareya qancha"))


def test_unknown_returns_none():
    assert run(run_command("Menga she'r yozib ber")) is None


# ---------- Obsidian ----------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Obsidianni och va yozib qo'y: ertaga uchrashuv", "ertaga uchrashuv"),
        ("Jarvis, Obsidian'ni och, bu ma'lumotlarni yozib qo'y: Django darsini takrorlash",
         "Django darsini takrorlash"),
        ("Obsidian'ga yoz: non olish", "non olish"),
        ("Obsidianga saqlab qo'y kitob ro'yxati", "kitob ro'yxati"),
        ("Yozib qo'y obsidianga: sut", "sut"),
        ("Открой обсидиан и запиши купить хлеб", "купить хлеб"),
        ("Запиши в обсидиан: позвонить маме", "позвонить маме"),
        ("Обсидианни оч ва ёзиб қўй: эртага учрашув", "эртага учрашув"),
        ("Obsidianni och va yozib qo'y", ""),
    ],
)
def test_obsidian_phrases(text, expected):
    rule, m = match(text)
    assert rule.name == "obsidian.write"
    assert m.group("text").strip() == expected


@pytest.mark.parametrize("text", ["Obsidianni och", "Obsidiandagi yozuvlarimni o'qi"])
def test_obsidian_open_is_not_write(text):
    assert rule_of(text) != "obsidian.write"


def test_obsidian_write_to_vault(tmp_path, monkeypatch, fake_mac):
    calls, _ = fake_mac
    vault = tmp_path / "Core"
    vault.mkdir()
    monkeypatch.setattr(macos, "obsidian_vault", lambda: vault)
    monkeypatch.setattr(macos, "notes_file", ORIG["notes_file"])
    monkeypatch.setattr(
        macos, "get_settings", lambda: type("S", (), {"notes_file": None, "obsidian_vault": None})
    )
    reply = run(run_command("Obsidianni och va yozib qo'y: ertaga uchrashuv"))
    assert "ertaga uchrashuv" in reply
    note = (vault / "JARVIS" / "Eslatmalar.md").read_text()
    assert note.startswith("# JARVIS eslatmalari") and "ertaga uchrashuv" in note
    assert ("open", "obsidian://open?vault=Core&file=JARVIS/Eslatmalar") in calls


def test_obsidian_empty_asks_what_to_write(fake_mac):
    calls, _ = fake_mac
    assert "Nima yozay" in run(run_command("Obsidianni och va yozib qo'y"))
    assert calls == []


def test_vault_autodetect(tmp_path, monkeypatch):
    v1, v2 = tmp_path / "Old", tmp_path / "Core"
    v1.mkdir()
    v2.mkdir()
    cfg = tmp_path / "obsidian.json"
    vaults = {
        "a": {"path": str(v1), "ts": 5},
        "b": {"path": str(v2), "ts": 1, "open": True},
        "c": {"path": "/yoq/papka", "ts": 9, "open": True},  # o'chirilgan vault
    }
    cfg.write_text(json.dumps({"vaults": vaults}))
    monkeypatch.setattr(macos, "OBSIDIAN_CONFIG", cfg)
    monkeypatch.setattr(macos, "get_settings", lambda: type("S", (), {"obsidian_vault": None}))
    assert ORIG["obsidian_vault"]() == v2  # ochiq va mavjud vault


def test_uri_outside_vault_is_none(tmp_path):
    assert macos.obsidian_uri(tmp_path / "x.md", tmp_path / "Core") is None


# ---------- Yangi buyruqlar ----------


@pytest.mark.parametrize(
    "text, rule",
    [
        ("Musiqani qo'y", "music.play"),
        ("Musiqani to'xtat", "music.pause"),
        ("Musiqani o'chir", "music.pause"),  # dastur yopish emas
        ("Keyingi qo'shiq", "music.next"),
        ("Oldingi trek", "music.previous"),
        ("5 daqiqaga taymer qo'y", "timer"),
        ("Taymer 30 soniya", "timer"),
        ("1 soatdan keyin eslat", "timer"),
        ("Ob-havo qanday?", "weather"),
        ("Samarqandda ob-havo qanday", "weather"),
        ("Какая погода", "weather"),
        ("Internet bormi?", "internet"),
        ("Tungi rejimni yoq", "dark"),
        ("Kunduzgi rejim", "dark"),
        ("Wi-Fi'ni o'chir", "wifi"),
        ("Vayfayni yoq", "wifi"),
        ("Kompyuterni uxlat", "sleep"),
        ("Skrinshot ol", "screenshot"),
        ("Ekran rasmini ol", "screenshot"),
        ("Oxirgi eslatmani o'chir", "notes.delete"),
        ("YouTube'da Shoxrux qo'shiqlarini qo'y", "search.youtube"),
        ("Python darslarini qidir", "search.google"),
        ("Internetdan Django haqida qidirib ber", "search.google"),
        ("Найди рецепт плова", "search.google"),
        ("YouTube'ni och", "app.open"),
        ("Yuklamalar papkasini och", "app.open"),
        ("12 plus 30", "calc"),
        ("25 ni 4 ga ko'paytir", "calc"),
    ],
)
def test_new_rule_selection(text, rule):
    assert rule_of(text) == rule


@pytest.mark.parametrize(
    "text, expected",
    [
        ("12 plus 30", "12 + 30 = 42"),
        ("12+30", "12 + 30 = 42"),
        ("7 karra 8", "7 × 8 = 56"),
        ("100 / 8", "100 ÷ 8 = 12.5"),
        ("25 ni 4 ga ko'paytir", "25 × 4 = 100"),
        ("100 dan 30 ni ayir", "100 - 30 = 70"),
        ("100 ni 4 ga bo'l", "100 ÷ 4 = 25"),
        ("25 ga 4 ni qo'sh", "25 + 4 = 29"),
        ("Hisobla 1500 minus 250", "1 500 - 250 = 1 250"),
        ("200 ning 15 foizi", "200 ning 15% i = 30"),
        ("15% of 80", "80 ning 15% i = 12"),
        ("Сколько будет 6 умножить на 7", "6 × 7 = 42"),
        ("5 ni 0 ga bo'l", "Nolga bo'lib bo'lmaydi."),
        ("2 ta non olish", None),
        ("Ovozni 40 ga qo'y", None),
    ],
)
def test_calculate(text, expected):
    assert commands.calculate(text) == expected


def test_search_opens_google(fake_mac):
    calls, _ = fake_mac
    reply = run(run_command("Python darslarini qidir"))
    assert "python darslarini" in reply
    assert ("open", "https://www.google.com/search?q=python+darslarini") in calls


def test_youtube_search(fake_mac):
    calls, _ = fake_mac
    run(run_command("YouTube'da Shoxrux qo'shiqlarini qo'y"))
    assert any("youtube.com/results?search_query=shoxrux" in " ".join(c) for c in calls)


def test_open_site_when_no_app(fake_mac):
    calls, _ = fake_mac
    assert run(run_command("YouTube'ni och")) == "www.youtube.com ochildi."
    assert ("open", "https://www.youtube.com") in calls


def test_open_folder(fake_mac):
    calls, _ = fake_mac
    assert run(run_command("Yuklamalar papkasini och")) == "Downloads papkasi ochildi."
    assert any(c[0] == "open" and c[1].endswith("/Downloads") for c in calls)


def test_music_pause_uses_running_player(fake_mac):
    calls, _ = fake_mac
    assert run(run_command("Musiqani to'xtat")) == "Spotify: to'xtatildi."  # pgrep → 0
    assert ("osascript", 'tell application "Spotify" to pause') in calls


def test_timer_rings(monkeypatch):
    rung = []

    async def fake_notify(title, text, sound=False):
        rung.append(text)

    monkeypatch.setattr(macos, "notify", fake_notify)
    monkeypatch.setattr(macos.sys, "platform", "darwin")

    async def scenario():
        reply = await run_command("Taymer 1 soniya")
        await asyncio.sleep(1.2)
        return reply

    assert run(scenario()) == "Taymer qo'yildi: 1 soniya."
    assert rung == ["1 soniya o'tdi"]


def test_timer_too_long():
    assert "24 soat" in run(run_command("100 soatga taymer qo'y"))


def test_weather_reply(monkeypatch):
    sample = {
        "current_condition": [
            {"temp_C": "12", "FeelsLikeC": "10", "weatherDesc": [{"value": "Partly cloudy"}]}
        ],
        "weather": [{"mintempC": "5", "maxtempC": "15"}],
    }
    seen = []

    def fake_fetch(url, timeout=8):
        seen.append(url)
        return sample

    monkeypatch.setattr("jarvis.tools.web._fetch_json", fake_fetch)
    reply = run(run_command("Samarqandda ob-havo qanday"))
    assert reply == "Samarqand: +12°C (his qilinishi +10°C), qisman bulutli. Bugun +5…+15°C."
    assert seen == ["https://wttr.in/Samarqand?format=j1"]


def test_delete_last_note(tmp_path, monkeypatch):
    f = tmp_path / "e.md"
    f.write_text("# JARVIS eslatmalari\n\n- [1] birinchi\n- [2] ikkinchi\n")
    monkeypatch.setattr(macos, "notes_file", lambda: f)
    assert run(run_command("Oxirgi eslatmani o'chir")) == "O'chirildi: «[2] ikkinchi»."
    assert f.read_text().endswith("- [1] birinchi\n")


# ---------- Haqiqiy noto'g'ri eshitishlar (JARVIS.app logidan) ----------


@pytest.mark.parametrize(
    "heard, app",
    [
        ("Safarin Ač", "Safari"),
        ("Telegram na oč.", "Telegram"),
        ("Safarini ach", "Safari"),
        ("Safari'ni aç", "Safari"),
        ("Telegramni achib ber", "Telegram"),
    ],
)
def test_misheard_open_commands(heard, app, fake_mac):
    calls, _ = fake_mac
    assert rule_of(heard) == "app.open"
    assert run(run_command(heard)) == f"{app} ochildi."
    assert ("open", "-a", app) in calls


def test_misheard_close_and_mute():
    assert rule_of("Telegramni achir") == "app.quit"
    assert rule_of("Ovozni achir") == "volume.mute"


def test_normalize_turkic_latin():
    assert normalize("Şu dasturni aç") == "shu dasturni och"
    assert normalize("Ŏzbekcha") == "ozbekcha"
