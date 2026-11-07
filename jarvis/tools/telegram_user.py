"""Telegram'da sizning nomingizdan xabar yuborish (Telegram'ning bepul rasmiy API'si — MTProto).

Bir martalik sozlash:
1. https://my.telegram.org → API development tools → `api_id` va `api_hash` oling.
2. `.env` ga yozing: JARVIS_TG_API_ID=..., JARVIS_TG_API_HASH=...
3. `.venv/bin/jarvis-telegram-login` — telefon raqam va Telegram yuborgan kod bilan kiring.

Sessiya fayli hisobingizga to'liq kirish beradi: u faqat shu Mac'da, egasigina o'qiy oladigan
papkada saqlanadi va hech qayerga yuborilmaydi. Xabar faqat tasdiqdan keyin yuboriladi
(bu `jarvis.core.commands` dagi tasdiqlash oqimida).
"""

from __future__ import annotations

import asyncio
import difflib
import re
import time
from dataclasses import dataclass
from typing import Any

from jarvis.config import get_settings


class TelegramNotReady(RuntimeError):
    """Telegram ulanmagan: api_id/api_hash yo'q yoki hali login qilinmagan."""


@dataclass
class Contact:
    id: int
    name: str
    username: str | None
    keys: list[str]  # solishtirish uchun normallashtirilgan variantlar
    entity: Any = None


_client: Any = None
_contacts: tuple[float, list[Contact]] | None = None
_lock = asyncio.Lock()
CONTACTS_TTL = 300


def session_path():
    path = get_settings().tg_session
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


async def get_client():
    """Ulangan va avtorizatsiyadan o'tgan klient (bir marta yaratiladi)."""
    global _client
    s = get_settings()
    if not s.tg_api_id or not s.tg_api_hash:
        raise TelegramNotReady(
            "Telegram ulanmagan: .env ga JARVIS_TG_API_ID va JARVIS_TG_API_HASH yozing "
            "(my.telegram.org), keyin .venv/bin/jarvis-telegram-login ni ishga tushiring."
        )
    try:
        from telethon import TelegramClient
    except ImportError as e:
        raise TelegramNotReady("telethon o'rnatilmagan: pip install -e \".[telegram]\"") from e
    async with _lock:
        if _client is None:
            _client = TelegramClient(str(session_path()), s.tg_api_id, s.tg_api_hash)
        if not _client.is_connected():
            await _client.connect()
        if not await _client.is_user_authorized():
            raise TelegramNotReady(
                "Telegram'ga kirilmagan: terminalda .venv/bin/jarvis-telegram-login "
                "ni ishga tushiring."
            )
    return _client


# ---------- Kontaktni ismi bo'yicha topish ----------


def name_key(text: str) -> str:
    """Solishtirish uchun: kichik harf, kirill → lotin, apostrof va belgilarsiz."""
    from jarvis.core.commands import _CYR, _plain_latin

    t = _plain_latin("".join(_CYR.get(ch, ch) for ch in text.lower()))
    t = re.sub(r"[ʻʼ‘’`´'@]", "", t)
    return " ".join(re.sub(r"[^\w\s]", " ", t).split())


def _contact_from_user(user) -> Contact | None:
    if getattr(user, "bot", False) or getattr(user, "is_self", False) or getattr(
        user, "deleted", False
    ):
        return None
    first, last = user.first_name or "", user.last_name or ""
    name = f"{first} {last}".strip() or (user.username or str(user.id))
    keys = {name_key(x) for x in (first, last, f"{first} {last}", user.username or "") if x}
    keys.discard("")
    return Contact(user.id, name, user.username, sorted(keys), user)


async def load_contacts(client) -> list[Contact]:
    """Telefon kontaktlari + oxirgi suhbatlar (5 daqiqa keshlanadi)."""
    global _contacts
    if _contacts and time.monotonic() - _contacts[0] < CONTACTS_TTL:
        return _contacts[1]
    from telethon.tl.functions.contacts import GetContactsRequest

    found: dict[int, Contact] = {}
    result = await client(GetContactsRequest(hash=0))
    for u in getattr(result, "users", []):
        c = _contact_from_user(u)
        if c:
            found[c.id] = c
    async for d in client.iter_dialogs(limit=300):
        if d.is_user:
            c = _contact_from_user(d.entity)
            if c:
                found.setdefault(c.id, c)
    _contacts = (time.monotonic(), list(found.values()))
    return _contacts[1]


def score(spoken: str, contact: Contact) -> float:
    best = 0.0
    for key in contact.keys:
        r = difflib.SequenceMatcher(None, spoken, key).ratio()
        if key == spoken:
            r = 1.0
        elif key.split() and spoken == key.split()[0]:
            r = max(r, 0.95)  # «ali» → «ali valiyev» (ism bo'yicha)
        best = max(best, r)
    return best


def match_contacts(spoken: str, contacts: list[Contact]) -> tuple[Contact | None, list[Contact]]:
    """(aniq topilgan kontakt, o'xshash nomzodlar). Shubhali bo'lsa birinchisi None."""
    key = name_key(spoken)
    ranked = sorted(((score(key, c), c) for c in contacts), key=lambda x: -x[0])
    ranked = [(s, c) for s, c in ranked if s >= 0.75]
    if not ranked:
        return None, []
    top_score, top = ranked[0]
    rivals = [c for s, c in ranked[1:] if s >= top_score - 0.05]
    if top_score < 0.85 or rivals:
        return None, [c for _, c in ranked[:3]]
    return top, []


async def find_contact(spoken: str) -> tuple[Contact | None, list[Contact]]:
    client = await get_client()
    return match_contacts(spoken, await load_contacts(client))


async def send(contact: Contact, text: str) -> None:
    client = await get_client()
    await client.send_message(contact.entity or contact.id, text)


# ---------- Bir martalik login (terminal) ----------


def login_main() -> None:
    """`jarvis-telegram-login`: telefon raqam va kod bilan kirib, sessiyani saqlaydi."""
    import os

    s = get_settings()
    if not s.tg_api_id or not s.tg_api_hash:
        raise SystemExit(
            "Avval https://my.telegram.org → API development tools dan api_id va api_hash oling\n"
            "va .env ga yozing:\n  JARVIS_TG_API_ID=1234567\n  JARVIS_TG_API_HASH=abcdef..."
        )
    from telethon import TelegramClient

    path = session_path()

    async def run() -> None:
        client = TelegramClient(str(path), s.tg_api_id, s.tg_api_hash)
        await client.start()  # telefon, kod va (bo'lsa) 2FA parolni so'raydi
        me = await client.get_me()
        await client.disconnect()
        print(f"✅ Kirildi: {me.first_name} (@{me.username}). JARVIS endi xabar yubora oladi.")

    asyncio.run(run())
    for f in path.parent.glob(path.name + "*"):
        os.chmod(f, 0o600)
