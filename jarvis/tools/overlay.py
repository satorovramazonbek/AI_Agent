"""«JARVIS boshqaryapti» belgisi: kompyuter boshqarilayotgan paytda ekranda turadi.

Ekran tepasida yozuv va ekran chetida rangli hoshiya chiqadi. Oynalar fokusni olmaydi
(tugma bosishlar Telegram'ga borishi kerak) va sichqonchani o'tkazib yuboradi.

Faqat JARVIS.app ichida ko'rinadi (AppKit asosiy oqimi ishlayotgan bo'lsa); terminal yoki
testlarda hech narsa qilmaydi.
"""

from __future__ import annotations

import contextlib
import logging
import threading

log = logging.getLogger(__name__)

DEFAULT_TEXT = "🤖  JARVIS boshqaryapti — sichqoncha va klaviaturaga tegmang"
_lock = threading.Lock()
_depth = 0
_panels: list = []


def _appkit_running() -> bool:
    try:
        from AppKit import NSApplication

        return bool(NSApplication.sharedApplication().isRunning())
    except Exception:
        return False


def _panel(rect, mouse_through: bool = True):
    from AppKit import (
        NSBackingStoreBuffered,
        NSColor,
        NSPanel,
        NSStatusWindowLevel,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorFullScreenAuxiliary,
        NSWindowCollectionBehaviorStationary,
        NSWindowStyleMaskBorderless,
        NSWindowStyleMaskNonactivatingPanel,
    )

    p = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        rect,
        NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
        NSBackingStoreBuffered,
        False,
    )
    p.setLevel_(NSStatusWindowLevel)
    p.setOpaque_(False)
    p.setBackgroundColor_(NSColor.clearColor())
    p.setIgnoresMouseEvents_(mouse_through)
    p.setHidesOnDeactivate_(False)
    p.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces
        | NSWindowCollectionBehaviorStationary
        | NSWindowCollectionBehaviorFullScreenAuxiliary
    )
    return p


def _show(text: str) -> None:
    from AppKit import (
        NSColor,
        NSFont,
        NSMakeRect,
        NSScreen,
        NSTextAlignmentCenter,
        NSTextField,
        NSView,
    )
    from Quartz import CGColorCreateSRGB

    screen = NSScreen.mainScreen()
    if screen is None:
        return
    frame = screen.frame()
    orange = CGColorCreateSRGB(1.0, 0.55, 0.1, 0.95)

    # 1) Butun ekran bo'ylab hoshiya
    border = _panel(frame)
    bview = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, frame.size.width, frame.size.height))
    bview.setWantsLayer_(True)
    bview.layer().setBorderWidth_(5.0)
    bview.layer().setBorderColor_(orange)
    bview.layer().setCornerRadius_(10.0)
    border.setContentView_(bview)

    # 2) Tepada yozuv
    w, h = 560, 46
    x = frame.origin.x + (frame.size.width - w) / 2
    y = frame.origin.y + frame.size.height - h - 48
    pill = _panel(NSMakeRect(x, y, w, h))
    pill.setHasShadow_(True)
    pview = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
    pview.setWantsLayer_(True)
    pview.layer().setBackgroundColor_(CGColorCreateSRGB(0.08, 0.09, 0.12, 0.92))
    pview.layer().setCornerRadius_(h / 2)
    pview.layer().setBorderWidth_(2.0)
    pview.layer().setBorderColor_(orange)
    label = NSTextField.labelWithString_(text)
    label.setTextColor_(NSColor.whiteColor())
    label.setFont_(NSFont.boldSystemFontOfSize_(14))
    label.setAlignment_(NSTextAlignmentCenter)
    label.setFrame_(NSMakeRect(12, (h - 20) / 2 - 1, w - 24, 20))
    pview.addSubview_(label)
    pill.setContentView_(pview)

    for p in (border, pill):
        p.orderFrontRegardless()  # fokusni olmasdan oldinga chiqadi
        _panels.append(p)


def _hide() -> None:
    while _panels:
        _panels.pop().orderOut_(None)


def _on_main(fn, *args) -> None:
    from PyObjCTools import AppHelper

    def safe():
        try:
            fn(*args)
        except Exception:
            log.exception("overlay xatosi")

    AppHelper.callAfter(safe)


@contextlib.contextmanager
def controlling(text: str = DEFAULT_TEXT):
    """`with controlling():` — blok davomida «JARVIS boshqaryapti» ko'rinib turadi."""
    global _depth
    enabled = _appkit_running()
    with _lock:
        _depth += 1
        first = _depth == 1
    if enabled and first:
        _on_main(_show, text)
    try:
        yield
    finally:
        with _lock:
            _depth -= 1
            last = _depth == 0
        if enabled and last:
            _on_main(_hide)
