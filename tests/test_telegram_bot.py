import asyncio

from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove

from jarvis.core import commands
from jarvis.interfaces.telegram_bot import CONFIRM_KB, send_reply


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append(("message", text, reply_markup))

    async def send_location(self, chat_id, lat, lon, reply_markup=None):
        self.sent.append(("location", (lat, lon), reply_markup))


def run(coro):
    return asyncio.run(coro)


def setup_function():
    commands.EXTRAS.clear()
    commands.PENDING.clear()


def test_location_pin_with_navigation_buttons():
    commands.EXTRAS["tg:7"] = [("location", 41.3, 69.2, "Ofis")]
    bot = FakeBot()
    run(send_reply(bot, 7, "🧭 Ofis"))
    assert bot.sent[0][:2] == ("message", "🧭 Ofis")
    kind, coords, kb = bot.sent[1]
    assert kind == "location" and coords == (41.3, 69.2)
    urls = [b.url for row in kb.inline_keyboard for b in row]
    assert any("google.com/maps/dir" in u for u in urls) and any("yandex" in u for u in urls)


def test_request_location_button():
    commands.EXTRAS["tg:7"] = [("request_location",)]
    bot = FakeBot()
    run(send_reply(bot, 7, "Joylashuvni yuboring"))
    kb = bot.sent[0][2]
    assert isinstance(kb, ReplyKeyboardMarkup) and kb.keyboard[0][0].request_location


def test_done_removes_keyboard():
    commands.EXTRAS["tg:7"] = [("done",)]
    bot = FakeBot()
    run(send_reply(bot, 7, "Saqlandi"))
    assert isinstance(bot.sent[0][2], ReplyKeyboardRemove)


def test_pending_shows_confirm_buttons():
    async def noop():
        return "ok"

    commands.PENDING["tg:7"] = commands.Pending("?", noop, 1e18)
    bot = FakeBot()
    run(send_reply(bot, 7, "Yuboraymi?"))
    assert bot.sent[0][2] is CONFIRM_KB


def test_long_text_is_trimmed():
    bot = FakeBot()
    run(send_reply(bot, 7, "x" * 10_000))
    assert len(bot.sent[0][1]) == 4000
