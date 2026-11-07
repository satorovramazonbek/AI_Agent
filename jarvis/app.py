"""JARVIS.app — macOS menyu paneli ilovasi.

Menyu panelida belgi turadi: «Gapirish» — bir marta bosiladi, gapirasiz, jim qolsangiz
yozish o'zi to'xtaydi; javob bildirishnoma bo'lib keladi. API va Telegram bot shu
jarayonning fon oqimida ishlaydi (alohida server kerak emas).

Ishga tushirish: `python -m jarvis.app` yoki `scripts/build-app.sh` yig'gan JARVIS.app.
"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import subprocess
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

import rumps

from jarvis.config import get_settings

log = logging.getLogger("jarvis.app")

ICON = Path(__file__).resolve().parent / "assets" / "menubar.png"
IDLE, LISTENING, THINKING = "idle", "listening", "thinking"


def notify(title: str, text: str) -> None:
    """macOS bildirishnomasi (osascript — har qanday muhitda ishlaydi)."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')[:240]

    subprocess.Popen(
        ["osascript", "-e", f'display notification "{esc(text)}" with title "{esc(title)}"'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class Backend:
    """Fon oqimidagi asyncio loop: API serveri, Telegram bot va buyruqlarni bajarish."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.api_error: str | None = None
        self.thread = threading.Thread(target=self._run, name="jarvis-backend", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.create_task(self._serve_api())
        self.loop.create_task(self._run_bot())
        self.loop.run_forever()

    async def _serve_api(self) -> None:
        import uvicorn

        from jarvis.interfaces.api import app

        s = get_settings()
        host = os.getenv("JARVIS_HOST", "127.0.0.1")
        server = uvicorn.Server(
            uvicorn.Config(app, host=host, port=s.app_port, log_level="warning")
        )
        try:
            await server.serve()
        except (SystemExit, OSError):
            self.api_error = f"{s.app_port}-port band"
            log.warning("API ishga tushmadi: %s (ovozli buyruqlar ishlayveradi)", self.api_error)

    async def _run_bot(self) -> None:
        from jarvis.interfaces.telegram_bot import run_bot

        try:
            await run_bot()
        except Exception:
            log.exception("Telegram bot to'xtadi")

    def submit(self, coro, timeout: float = 120):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)


class JarvisApp(rumps.App):
    def __init__(self, backend: Backend) -> None:
        super().__init__(
            "JARVIS",
            icon=str(ICON) if ICON.exists() else None,
            title=None if ICON.exists() else "J",
            template=True,
            quit_button=None,
        )
        self.backend = backend
        self.ui: queue.Queue = queue.Queue()  # fon oqimlaridan UI'ga xabarlar
        self.state = IDLE
        self.stop_event = threading.Event()

        self.talk = rumps.MenuItem("🎙  Gapirish", callback=self.on_talk, key="g")
        self.heard = rumps.MenuItem("Siz: —")
        self.reply = rumps.MenuItem("JARVIS: —")
        self.history_menu = rumps.MenuItem("🕘  Oxirgi buyruqlar")
        self.tts_item = rumps.MenuItem("🔈  Javobni ovozda aytish", callback=self.on_toggle_tts)
        self.tts_item.state = int(get_settings().tts_enabled)
        self.voice = get_settings().tts_voice
        self.voice_menu = rumps.MenuItem("🗣  Ovoz")
        for key, label in (("uz", "O'zbekcha"), ("uz-qiz", "O'zbekcha (qiz)"),
                           ("Yelda", "Turkcha (Yelda)")):  # fmt: skip
            item = rumps.MenuItem(label, callback=self.on_voice)
            item.voice_key = key
            item.state = int(key == self.voice)
            self.voice_menu.add(item)
        self.history: list[str] = []
        port = get_settings().app_port
        self.menu = [
            self.talk,
            rumps.MenuItem("⌨️  Yozib buyruq berish…", callback=self.on_type, key="y"),
            None,
            self.heard,
            self.reply,
            self.history_menu,
            None,
            self.tts_item,
            self.voice_menu,
            rumps.MenuItem("📝  Eslatmalarni ochish", callback=self.on_notes),
            rumps.MenuItem("❓  Nima qila olaman", callback=self.on_help),
            rumps.MenuItem(f"🌐  API: 127.0.0.1:{port}", callback=self.on_api),
            None,
            rumps.MenuItem("Chiqish", callback=self.on_quit, key="q"),
        ]
        rumps.Timer(self._drain_ui, 0.2).start()
        threading.Thread(target=self._preload, daemon=True).start()

    # ---------- UI (faqat asosiy oqimda) ----------

    def _set_state(self, state: str) -> None:
        self.state = state
        self.talk.title = {
            IDLE: "🎙  Gapirish",
            LISTENING: "⏹  To'xtatish (tinglayapman…)",
            THINKING: "⏳  O'ylayapman…",
        }[state]
        if ICON.exists():
            self.title = {IDLE: None, LISTENING: "●", THINKING: "…"}[state]

    def _drain_ui(self, _timer) -> None:
        while True:
            try:
                kind, value = self.ui.get_nowait()
            except queue.Empty:
                return
            if kind == "state":
                self._set_state(value)
            elif kind == "result":
                self._show_result(*value)
            elif kind == "reply":
                self.reply.title = f"JARVIS: {_short(value)}"
                notify("JARVIS", value)
                self._say(value)

    def _say(self, text: str) -> None:
        if self.tts_item.state:
            from jarvis.voice.tts import speak

            speak(text, voice=self.voice, rate=get_settings().tts_rate)

    def on_voice(self, item) -> None:
        self.voice = item.voice_key
        for other in self.voice_menu.values():
            other.state = int(other is item)
        self._say("Salom! Men shu ovozda gapiraman.")

    def on_toggle_tts(self, item) -> None:
        item.state = 0 if item.state else 1
        if item.state:
            self._say("Javoblarni ovozda aytaman.")

    def _show_result(self, heard: str, reply: str, confidence: float | None) -> None:
        from jarvis.voice.stt import LOW_CONFIDENCE

        unsure = confidence is not None and confidence < LOW_CONFIDENCE
        mark = f"  (?) {confidence:.0%}" if unsure else ""
        self.heard.title = f"Siz: «{_short(heard, 50)}»{mark}"
        self.reply.title = f"JARVIS: {_short(reply)}"
        # Sarlavhada — eshitilgan gap (to'g'ri tanildimi, darrov ko'rinadi), matnda — javob.
        title = f"🎙 «{_short(heard, 70)}»" + (" (?)" if unsure else "")
        notify(title, reply)
        self._say(reply)
        line = f"{datetime.now():%H:%M}  «{_short(heard, 40)}» → {_short(reply, 40)}"
        self.history.insert(0, line)
        del self.history[10:]
        if self.history_menu._menu is not None:
            self.history_menu.clear()
        for line in self.history:
            self.history_menu.add(rumps.MenuItem(line))
        self._maybe_confirm()

    def _maybe_confirm(self) -> None:
        """Tasdiq kutayotgan amal bo'lsa (masalan Telegram xabari) — tugmali oyna."""
        from jarvis.core import commands

        p = commands.pending("app")
        if not p:
            return
        ok = rumps.alert(title="JARVIS — tasdiqlang", message=p.question, ok="✅ Ha, bajar",
                         cancel="❌ Yo'q")  # fmt: skip
        decide = commands.confirm if ok == 1 else commands.cancel

        def work() -> None:
            try:
                result = self.backend.submit(decide("app"))
            except Exception as e:
                result = f"Xato: {e}"
            log.info("Tasdiq: %s → %s", "ha" if ok == 1 else "yo'q", result)
            self.ui.put(("reply", result))

        threading.Thread(target=work, daemon=True).start()

    # ---------- Fon ishlari ----------

    def _preload(self) -> None:
        from jarvis.tools import contacts
        from jarvis.voice.stt import VoiceUnavailable, get_transcriber

        contacts.mac_contacts(request=True)  # birinchi marta macOS Kontaktlar ruxsatini so'raydi
        try:
            get_transcriber()._load()  # birinchi buyruq kutib qolmasin
        except VoiceUnavailable as e:
            self.ui.put(("reply", str(e)))

    def _answer(self, text: str, confidence: float | None = None) -> None:
        from jarvis.voice.intents import handle_text

        try:
            reply = self.backend.submit(handle_text(text, "app"))
        except Exception as e:
            log.exception("Buyruq xatosi")
            reply = f"Xato: {e}"
        conf = f" [{confidence:.0%}]" if confidence is not None else ""
        log.info("Siz: %s%s → JARVIS: %s", text, conf, reply.replace("\n", " | "))
        self.ui.put(("result", (text, reply, confidence)))

    def _listen(self) -> None:
        from jarvis.voice.recorder import record_utterance
        from jarvis.voice.stt import get_transcriber

        try:
            audio = record_utterance(self.stop_event)
            if len(audio) < 8000:  # 0.5 soniyadan qisqa
                self.ui.put(("reply", "Hech narsa eshitilmadi."))
                return
            self.ui.put(("state", THINKING))
            _save_last_audio(audio)
            t = get_transcriber().transcribe_sync(audio)
            if t.text:
                self._answer(t.text, t.confidence)
            else:
                self.ui.put(("reply", "Gapni tushunib bo'lmadi, qaytadan ayting."))
        except Exception as e:
            log.exception("Tinglash xatosi")
            self.ui.put(("reply", f"Mikrofon xatosi: {e}"))
        finally:
            self.ui.put(("state", IDLE))

    # ---------- Menyu tugmalari ----------

    def on_talk(self, _item) -> None:
        if self.state == LISTENING:
            self.stop_event.set()  # qo'lda to'xtatish: yozilgan qismi qayta ishlanadi
            return
        if self.state == THINKING:
            return
        self.stop_event.clear()
        self._set_state(LISTENING)
        threading.Thread(target=self._listen, daemon=True).start()

    def on_type(self, _item) -> None:
        w = rumps.Window(
            message="Masalan: «Safari'ni och», «Obsidian'ga yoz: …»",
            title="JARVIS'ga buyruq",
            ok="Yuborish",
            cancel="Bekor qilish",
            dimensions=(320, 60),
        )
        r = w.run()
        if r.clicked and r.text.strip():
            self._set_state(THINKING)
            text = r.text.strip()
            threading.Thread(target=self._answer_then_idle, args=(text,), daemon=True).start()

    def _answer_then_idle(self, text: str) -> None:
        try:
            self._answer(text)
        finally:
            self.ui.put(("state", IDLE))

    def on_notes(self, _item) -> None:
        from jarvis.tools import macos

        path = macos.notes_file()
        uri = macos.obsidian_uri(path, macos.obsidian_vault()) if path.exists() else None
        subprocess.Popen(["open", uri] if uri else ["open", str(path.parent)])

    def on_help(self, _item) -> None:
        from jarvis.core.commands import HELP

        rumps.alert("JARVIS", HELP)

    def on_api(self, _item) -> None:
        if self.backend.api_error:
            rumps.alert("JARVIS API", f"API ishga tushmadi: {self.backend.api_error}.")
        else:
            webbrowser.open(f"http://127.0.0.1:{get_settings().app_port}/docs")

    def on_quit(self, _item) -> None:
        rumps.quit_application()


LAST_AUDIO = Path.home() / "Library" / "Logs" / "jarvis" / "last.wav"


def _save_last_audio(audio) -> None:
    """Oxirgi buyruqni WAV qilib saqlaydi — noto'g'ri tanilsa, qayta tinglab tekshirish uchun."""
    if not get_settings().save_last_audio:
        return
    import wave

    import numpy as np

    try:
        LAST_AUDIO.parent.mkdir(parents=True, exist_ok=True)
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
        with wave.open(str(LAST_AUDIO), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16_000)
            w.writeframes(pcm)
    except OSError:
        log.warning("Oxirgi audioni saqlab bo'lmadi", exc_info=True)


def _short(text: str, n: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def main() -> None:
    logging.basicConfig(
        level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:  # Dock'da belgi chiqmasin — faqat menyu paneli
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except ImportError:
        pass
    backend = Backend()
    backend.start()
    JarvisApp(backend).run()


if __name__ == "__main__":
    main()
