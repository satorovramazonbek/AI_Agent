import pytest

from jarvis.voice.tts import number_words, prepare, speakable, to_turkish


@pytest.mark.parametrize(
    "n, words",
    [(0, "nol"), (7, "yetti"), (10, "o'n"), (17, "o'n yetti"), (52, "ellik ikki"),
     (100, "yuz"), (245, "ikki yuz qirq besh"), (1000, "ming"), (1500, "ming besh yuz"),
     (2026, "ikki ming yigirma olti"), (3_000_000, "uch million")],
)  # fmt: skip
def test_number_words(n, words):
    assert number_words(n) == words


@pytest.mark.parametrize(
    "text, spoken",
    [
        ("Soat 17:03.", "Soat o'n yetti dan uch daqiqa o'tdi"),
        ("Soat 9:00.", "Soat to'qqiz"),
        ("Batareya 52%, quvvatlanmoqda.", "Batareya ellik ikki foiz, quvvatlanmoqda"),
        ("Tashkent: +15°C", "Tashkent: o'n besh daraja"),
        ("25 × 4 = 100", "yigirma besh ko'paytirilsa to'rt teng yuz"),
        ("✅ Yuborildi → Ali: «salom»", "Yuborildi → Ali: salom"),
    ],
)
def test_speakable(text, spoken):
    assert speakable(text) == spoken


def test_confirmation_instruction_not_spoken():
    q = "Telegram'da «Ali» chati ochildi.\nYuboraymi?\n«Ha» desangiz yuboraman, «yo'q» — bekor"
    assert speakable(q) == "Telegram'da Ali chati ochildi. Yuboraymi?"


def test_long_list_only_head_spoken():
    from jarvis.core.commands import HELP

    assert speakable(HELP) == "Men bajara oladigan buyruqlar"


@pytest.mark.parametrize(
    "uz, tr",
    [("Telegram ochildi", "Telegram oçildi"), ("Xabar yuborildi", "Habar yuborildi"),
     ("O'zbekiston", "Ozbekiston"), ("tog'", "toğ"), ("quvvat", "kuvvat"),
     ("shanba", "şanba"), ("jo'nat", "conat")],
)  # fmt: skip
def test_to_turkish(uz, tr):
    assert to_turkish(uz) == tr


def test_prepare_for_yelda():
    assert prepare("Telegram ochildi.", "Yelda") == "Telegram oçildi"


# ---------- Haqiqiy o'zbekcha ovoz (MMS-TTS) ----------

from jarvis.voice import tts  # noqa: E402


@pytest.mark.parametrize(
    "uz, cyr",
    [
        ("Telegram ochildi", "телеграм очилди"),
        ("Obsidian'ga yozdim", "обсидианга ёздим"),
        ("Telegram'ni yop", "телеграмни ёп"),
        ("ma'no", "маъно"),
        ("mas'uliyat", "масъулият"),
        ("Ertaga g'alaba", "эртага ғалаба"),
        ("o'zbekiston", "ўзбекистон"),
        ("Xabar yuborildi", "хабар юборилди"),
        ("shanba, choy", "шанба, чой"),
        ("Ёз", "ёз"),  # kirill matnga tegilmaydi
    ],
)
def test_uz_cyrillic(uz, cyr):
    assert tts.uz_cyrillic(uz) == cyr


def test_ids_intersperse_blank():
    v = tts.UzbekVoice("x")
    v._vocab, v._pad = {"|": 0, "а": 5, "б": 7}, 0
    assert v.ids("аб!") == [0, 5, 0, 7, 0]  # noma'lum belgi tashlanadi


def test_uzbek_voice_plays_wav(monkeypatch):
    import numpy as np

    played = []

    class FakeVoice:
        def synth(self, text):
            played.append(("synth", text))
            return np.zeros(1600, dtype="float32")

    monkeypatch.setattr(tts, "uzbek_voice", lambda name: FakeVoice())
    def fake_play(cmd, gen, cleanup=None):
        played.append(cmd[0])
        if cleanup:
            import os

            os.unlink(cleanup)  # test fayl qoldirmasin

    monkeypatch.setattr(tts, "_play", fake_play)
    tts._speak_worker("Telegram ochildi.", "uz", 175, tts._generation)
    assert played == [("synth", "Telegram ochildi"), "afplay"]


def test_falls_back_to_yelda(monkeypatch):
    played = []

    class Broken:
        def synth(self, text):
            raise RuntimeError("model yo'q")

    monkeypatch.setattr(tts, "uzbek_voice", lambda name: Broken())
    monkeypatch.setattr(tts, "_play", lambda cmd, gen, cleanup=None: played.append(cmd[:3]))
    tts._speak_worker("Xabar yuborildi.", "uz", 175, tts._generation)
    assert played == [["say", "-v", "Yelda"]]
