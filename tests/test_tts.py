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
