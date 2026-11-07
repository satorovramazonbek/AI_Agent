"""Telegram'ni ekran orqali boshqarish (API'siz): qidiruv → chat → xabar qoralamasi → Enter.

macOS Accessibility API (AX) orqali Telegram oynasidagi qidiruv maydoni va xabar maydoni
topiladi, tugmalar Quartz hodisalari bilan bosiladi. Kerakli ruxsat — bir marta:
System Settings → Privacy & Security → Accessibility → JARVIS.

Xavfsizlik: `open_chat_and_draft` faqat chatni ochib, xabarni **yozib qo'yadi**; Enter
(`press_send`) faqat foydalanuvchi tasdiqlagandan keyin bosiladi.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

from jarvis.tools.overlay import controlling

BUNDLE_IDS = ("ru.keepcoder.Telegram", "org.telegram.desktop")
KEY = {"a": 0, "v": 9, "k": 40, "return": 36, "down": 125, "esc": 53, "delete": 51}


class TelegramUIError(RuntimeError):
    pass


@dataclass
class Draft:
    chat_title: str | None  # ochilgan chat nomi (oyna sarlavhasidan), aniqlanmasa None


# ---------- Past darajadagi yordamchilar (faqat macOS) ----------


def _require_mac() -> None:
    if sys.platform != "darwin":
        raise TelegramUIError("bu faqat Mac'da ishlaydi")


def _ax():
    import ApplicationServices as AS

    return AS


def trusted(prompt: bool = False) -> bool:
    AS = _ax()
    if prompt:
        return bool(AS.AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True}))
    return bool(AS.AXIsProcessTrusted())


def _attr(el, name):
    AS = _ax()
    err, value = AS.AXUIElementCopyAttributeValue(el, name, None)
    return value if err == 0 else None


def _point(el, name, kind):
    AS = _ax()
    v = _attr(el, name)
    if v is None:
        return None
    ok, p = AS.AXValueGetValue(v, kind, None)
    return p if ok else None


def _telegram_app():
    from AppKit import NSWorkspace

    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if app.bundleIdentifier() in BUNDLE_IDS:
            return app
    return None


def _main_window(ax):
    """Asosiy oyna: AXWindows ba'zan bo'sh qaytadi — asosiy/fokusdagi oynani ham tekshiramiz."""
    AS = _ax()
    candidates = list(_attr(ax, AS.kAXWindowsAttribute) or [])
    for name in (AS.kAXMainWindowAttribute, AS.kAXFocusedWindowAttribute):
        w = _attr(ax, name)
        if w is not None:
            candidates.append(w)

    def area(w):
        if _attr(w, AS.kAXSubroleAttribute) != "AXStandardWindow":
            return 0  # qidiruv takliflari kabi kichik panellar emas
        size = _point(w, AS.kAXSizeAttribute, AS.kAXValueCGSizeType)
        return size.width * size.height if size else 0

    best = max(candidates, key=area, default=None)
    return best if best is not None and area(best) > 0 else None


def _activate() -> Any:
    """Telegram'ni ochadi/oldinga chiqaradi va asosiy oynasini qaytaradi.

    macOS 14+ fon ilovasiga boshqa dasturni oldinga chiqarishga ruxsat bermaydi
    (cooperative activation), shuning uchun Accessibility orqali AXFrontmost qo'yiladi.
    """
    AS = _ax()
    subprocess.run(["open", "-a", "Telegram"], check=False)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        app = _telegram_app()
        if app is not None:
            ax = AS.AXUIElementCreateApplication(app.processIdentifier())
            AS.AXUIElementSetAttributeValue(ax, "AXFrontmost", True)
            window = _main_window(ax)
            if window is not None:
                AS.AXUIElementPerformAction(window, "AXRaise")
                if _attr(ax, "AXFrontmost"):
                    return window
        time.sleep(0.2)
    raise TelegramUIError("Telegram oynasi ochilmadi (Telegram oldinga chiqmadi)")


def _walk(el, depth=0):
    AS = _ax()
    yield el, depth
    if depth > 30:
        return
    for child in _attr(el, AS.kAXChildrenAttribute) or []:
        yield from _walk(child, depth + 1)


def _find(window, roles: tuple[str, ...], subrole: str | None = None):
    """Berilgan roldagi elementlar, ekranda yuqoridan pastga tartibda."""
    AS = _ax()
    found = []
    for el, _ in _walk(window):
        if _attr(el, AS.kAXRoleAttribute) in roles:
            if subrole and _attr(el, AS.kAXSubroleAttribute) != subrole:
                continue
            p = _point(el, AS.kAXPositionAttribute, AS.kAXValueCGPointType)
            found.append(((p.y, p.x) if p else (1e9, 1e9), el))
    return [el for _, el in sorted(found, key=lambda x: x[0])]


def _focus(el) -> bool:
    AS = _ax()
    return AS.AXUIElementSetAttributeValue(el, AS.kAXFocusedAttribute, True) == 0


def _key(name: str, cmd: bool = False) -> None:
    import Quartz as Q

    for down in (True, False):
        e = Q.CGEventCreateKeyboardEvent(None, KEY[name], down)
        Q.CGEventSetFlags(e, Q.kCGEventFlagMaskCommand if cmd else 0)
        Q.CGEventPost(Q.kCGHIDEventTap, e)
        time.sleep(0.02)


def _clipboard_get() -> str | None:
    from AppKit import NSPasteboard, NSPasteboardTypeString

    return NSPasteboard.generalPasteboard().stringForType_(NSPasteboardTypeString)


def _clipboard_set(text: str) -> None:
    from AppKit import NSPasteboard, NSPasteboardTypeString

    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


def _paste(text: str) -> None:
    _clipboard_set(text)
    time.sleep(0.05)
    _key("v", cmd=True)
    time.sleep(0.15)


def _chat_title(window) -> str | None:
    """Ochiq chat nomi: o'ng panel tepasidagi birinchi tugma tavsifi (Telegram macOS)."""
    AS = _ax()
    wp = _point(window, AS.kAXPositionAttribute, AS.kAXValueCGPointType)
    search = _find(window, ("AXTextField",), "AXSearchField")
    left_edge = 0.0
    if search:
        sp = _point(search[0], AS.kAXPositionAttribute, AS.kAXValueCGPointType)
        ss = _point(search[0], AS.kAXSizeAttribute, AS.kAXValueCGSizeType)
        if sp and ss:
            left_edge = sp.x + ss.width + 20  # chatlar ro'yxatidan o'ngda
    best = None
    for el, _ in _walk(window):
        if _attr(el, AS.kAXRoleAttribute) != "AXButton":
            continue
        p = _point(el, AS.kAXPositionAttribute, AS.kAXValueCGPointType)
        desc = _attr(el, AS.kAXDescriptionAttribute)
        if not (p and desc and wp) or p.y > wp.y + 30 or p.x < left_edge:
            continue
        if best is None or p.x < best[0]:
            best = (p.x, str(desc))
    return best[1] if best else None


# ---------- Asosiy amallar ----------


def _open_chat_and_draft(name: str, message: str) -> Draft:
    _require_mac()
    if not trusted():
        trusted(prompt=True)  # macOS ruxsat oynasini ochadi
        raise TelegramUIError(
            "JARVIS'ga Accessibility ruxsati kerak: System Settings → Privacy & Security → "
            "Accessibility → JARVIS ni yoqing, keyin qaytadan ayting."
        )
    old_clipboard = _clipboard_get()
    try:
        window = _activate()
        search = _find(window, ("AXTextField",), "AXSearchField")
        if not (search and _focus(search[0])):
            _key("k", cmd=True)  # Telegram macOS: Поиск (⌘K)
        time.sleep(0.2)
        _key("a", cmd=True)
        _paste(name)
        time.sleep(1.3)  # qidiruv natijalari chiqishini kutamiz
        _key("return")  # birinchi natija o'zi belgilangan bo'ladi — «pastga» bosilmaydi
        time.sleep(1.0)

        window = _activate()
        title = _chat_title(window)
        inputs = _find(window, ("AXTextArea",))
        if not inputs:
            if title:
                raise TelegramUIError(
                    f"«{title}» ochildi, lekin unga yozib bo'lmaydi (kanal bo'lishi mumkin). "
                    "Ism-familiyani to'liqroq ayting."
                )
            raise TelegramUIError(f"«{name}» chati ochilmadi — Telegram'da topilmadi shekilli")
        _focus(inputs[-1])  # xabar maydoni — oynaning eng pastidagi
        time.sleep(0.1)
        _paste(message)
        return Draft(chat_title=title)
    finally:
        if old_clipboard is not None:
            _clipboard_set(old_clipboard)


def _press_send() -> None:
    _require_mac()
    window = _activate()
    inputs = _find(window, ("AXTextArea",))
    if inputs:
        _focus(inputs[-1])
    time.sleep(0.1)
    _key("return")


def _clear_draft() -> None:
    _require_mac()
    window = _activate()
    inputs = _find(window, ("AXTextArea",))
    if inputs and _focus(inputs[-1]):
        _key("a", cmd=True)
        _key("delete")


def _controlled(fn, *args):
    with controlling():
        return fn(*args)


async def open_chat_and_draft(name: str, message: str) -> Draft:
    return await asyncio.to_thread(_controlled, _open_chat_and_draft, name, message)


async def press_send() -> None:
    await asyncio.to_thread(_controlled, _press_send)


async def clear_draft() -> None:
    await asyncio.to_thread(_controlled, _clear_draft)
