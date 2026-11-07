"""Tanish ismlar: noto'g'ri eshitilgan ismni («o'ktan») haqiqiy ismga («O'ktam») tuzatish uchun.

Manbalar (hammasi lokal, API'siz):
1. macOS Kontaktlar (Contacts) — Telegram odatda ismlarni telefon kontaktlaridan oladi.
2. JARVIS xotirasi — xabar yuborilgan Telegram chatlari nomi (`known_chats.json`).

Ismlar Whisper'ga ham «hotwords» sifatida beriladi — shunda ularni to'g'riroq eshitadi.
"""

from __future__ import annotations

import difflib
import json
import logging
import time
from pathlib import Path

from jarvis.config import get_settings

log = logging.getLogger(__name__)
_cache: tuple[float, list[str]] | None = None
CACHE_TTL = 600


def _key(name: str) -> str:
    from jarvis.tools.telegram_user import name_key

    return name_key(name)


def chats_file() -> Path:
    return get_settings().places_file.parent / "known_chats.json"


def learned_names() -> list[str]:
    path = chats_file()
    try:
        return list(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def remember(chat_title: str) -> None:
    """Muvaffaqiyatli yozilgan chat nomini eslab qoladi."""
    global _cache
    title = chat_title.strip()
    if not title or title == "?":
        return
    names = learned_names()
    if title not in names:
        names.append(title)
        path = chats_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8")
        _cache = None


def mac_contacts(request: bool = False) -> list[str]:
    """macOS Kontaktlardagi ismlar (ruxsat bo'lmasa — bo'sh; `request` — ruxsat so'raydi)."""
    try:
        import Contacts as C
    except ImportError:
        return []
    store = C.CNContactStore.alloc().init()
    status = C.CNContactStore.authorizationStatusForEntityType_(C.CNEntityTypeContacts)
    if status == 0 and request:  # hali so'ralmagan — macOS oynasi chiqadi
        store.requestAccessForEntityType_completionHandler_(
            C.CNEntityTypeContacts, lambda ok, err: None
        )
        return []
    if status not in (3, 4):  # berilgan yoki cheklangan
        return []
    keys = [C.CNContactGivenNameKey, C.CNContactFamilyNameKey, C.CNContactNicknameKey]
    request_ = C.CNContactFetchRequest.alloc().initWithKeysToFetch_(keys)
    names: list[str] = []

    def collect(contact, stop):
        full = f"{contact.givenName()} {contact.familyName()}".strip()
        for n in (full, contact.nickname()):
            if n:
                names.append(str(n))

    ok, err = store.enumerateContactsWithFetchRequest_error_usingBlock_(request_, None, collect)
    if not ok:
        log.warning("Kontaktlarni o'qib bo'lmadi: %s", err)
    return names


def known_names() -> list[str]:
    global _cache
    if _cache and time.monotonic() - _cache[0] < CACHE_TTL:
        return _cache[1]
    names = list(dict.fromkeys(learned_names() + mac_contacts()))
    _cache = (time.monotonic(), names)
    return names


def best_match(spoken: str, names: list[str] | None = None) -> str | None:
    """«oktan» → «O'ktam Rahimov»: eng yaqin tanish ism (ishonchli bo'lsa), aks holda None."""
    names = known_names() if names is None else names
    key = _key(spoken)
    if not key or not names:
        return None
    scored = []
    for name in names:
        nk = _key(name)
        parts = nk.split()
        candidates = [nk, *parts, " ".join(parts[:2])] if parts else [nk]
        score = max(difflib.SequenceMatcher(None, key, c).ratio() for c in candidates)
        scored.append((score, name))
    scored.sort(reverse=True)
    best_score, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if best_score >= 0.8 and best_score - second >= 0.05:
        return best
    return None


def hotwords(limit: int = 60) -> str:
    """Whisper uchun: tanish ismlar (ism qismlari)."""
    words: list[str] = []
    for name in known_names():
        for part in name.split():
            if len(part) > 2 and part not in words:
                words.append(part)
    return " ".join(words[:limit])
