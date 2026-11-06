"""Agent sikli: matn → model → tool'lar → javob.

Tool'lar faqat Tool Registry orqali chaqiriladi; `shell.run` ichida har bir buyruq
Policy Gateway'dan o'tadi. Agent tasdiq bermaydi: R2+ buyruqlar `needs_approval` qaytaradi.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache

from jarvis.models.router import ModelRouter, get_router
from jarvis.security.policy import Risk
from jarvis.tools import system  # noqa: F401  (tool'larni ro'yxatga olish uchun)
from jarvis.tools.registry import ToolRegistry, registry

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Sen JARVIS — egangning MacBook'ida ishlaydigan shaxsiy yordamchisan.

- Foydalanuvchi tilida javob ber (odatda o'zbek, ba'zan rus yoki ingliz).
- Xabarlar ko'pincha ovozdan matnga o'girilgan bo'ladi: so'zlarda xato bo'lishi mumkin, \
ma'noga qarab tushun. Ma'no noaniq bo'lsa, taxmin qilmasdan qisqa savol ber.
- Javoblar qisqa bo'lsin (2–4 gap), chunki ular ovoz yoki Telegram orqali o'qiladi.
- Kompyuter haqidagi savollarga tool'lar orqali haqiqiy ma'lumot olib javob ber.
- `shell_run` natijasi `denied` yoki `needs_approval` bo'lsa, buyruqni boshqacha yo'l bilan \
aylanib o'tishga urinma: nima uchun bajarilmaganini va qaysi buyruq tasdiq kutayotganini ayt.
- Bajara olmaydigan ishni bajardim dema.
"""

MAX_STEPS = 8  # bitta so'rovda model–tool aylanishlari soni
SESSION_IDLE_SECONDS = 30 * 60
SESSION_MAX_MESSAGES = 40


def _wire_name(name: str) -> str:
    """API tool nomlarida nuqta bo'lmaydi: `system.status` → `system__status`."""
    return name.replace(".", "__")


@dataclass
class Session:
    messages: list = field(default_factory=list)
    last_used: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def expired(self) -> bool:
        idle = time.monotonic() - self.last_used > SESSION_IDLE_SECONDS
        return idle or len(self.messages) > SESSION_MAX_MESSAGES


class Agent:
    def __init__(
        self, router: ModelRouter, tools: ToolRegistry = registry, max_risk: Risk = Risk.R1
    ):
        self.router = router
        self.specs = {_wire_name(t.name): t for t in tools.list(max_risk=max_risk)}
        self.tools = [{**t.schema(), "name": wire} for wire, t in self.specs.items()]
        self.sessions: dict[str, Session] = {}

    @property
    def available(self) -> bool:
        return self.router.available

    def _session(self, session_id: str) -> Session:
        s = self.sessions.get(session_id)
        if s is None or s.expired():
            # Tarix tahrirlanmaydi: muddati o'tgan suhbat butunlay yangisiga almashadi.
            s = self.sessions[session_id] = Session()
        return s

    async def _run_tool(self, block) -> dict:
        spec = self.specs.get(block.name)
        result = {"type": "tool_result", "tool_use_id": block.id}
        if spec is None:
            return {**result, "content": f"Noma'lum tool: {block.name}", "is_error": True}
        try:
            args = spec.args_model.model_validate(block.input)
            out = await asyncio.wait_for(spec.func(args), timeout=spec.timeout)
            log.info("tool %s → %s", spec.name, str(out)[:200])
            return {**result, "content": json.dumps(out, ensure_ascii=False, default=str)}
        except Exception as e:  # tool xatosi modelga qaytariladi, sikl to'xtamaydi
            log.warning("tool %s xato: %s", spec.name, e)
            return {**result, "content": f"Xato: {e}", "is_error": True}

    async def run(self, text: str, session_id: str = "default") -> str:
        session = self._session(session_id)
        async with session.lock:
            session.last_used = time.monotonic()
            session.messages.append({"role": "user", "content": text})
            try:
                return await self._loop(session)
            except Exception:
                # Yarim qolgan tarix (javobsiz tool_use) keyingi so'rovni buzmasligi uchun.
                self.sessions.pop(session_id, None)
                raise

    async def _loop(self, session: Session) -> str:
        for _ in range(MAX_STEPS):
            response = await self.router.complete(
                system=SYSTEM_PROMPT, messages=session.messages, tools=self.tools
            )
            session.messages.append({"role": "assistant", "content": response.content})
            text = "\n".join(b.text for b in response.content if b.type == "text").strip()

            if response.stop_reason == "refusal":
                return "Bu so'rovni bajara olmayman."
            if response.stop_reason == "pause_turn":
                continue
            if response.stop_reason != "tool_use":
                return text or "(javob bo'sh)"

            calls = [b for b in response.content if b.type == "tool_use"]
            results = await asyncio.gather(*(self._run_tool(b) for b in calls))
            session.messages.append({"role": "user", "content": list(results)})
        return "Vazifa juda ko'p qadam talab qildi — to'xtatdim. Aniqroq qilib so'rang."


@lru_cache
def get_agent() -> Agent:
    return Agent(get_router())


async def ask(text: str, session_id: str = "default") -> str:
    """Interfeyslar uchun: agentga so'rov, API xatolari foydalanuvchiga tushunarli matnga."""
    import anthropic

    try:
        return await get_agent().run(text, session_id)
    except anthropic.AuthenticationError:
        return "Anthropic API kaliti noto'g'ri — .env dagi ANTHROPIC_API_KEY ni tekshiring."
    except anthropic.PermissionDeniedError:
        return "API kalitining bu modelga ruxsati yo'q (JARVIS_MODEL ni tekshiring)."
    except anthropic.RateLimitError:
        return "Model limiti oshdi — bir daqiqadan keyin qayta urinib ko'ring."
    except anthropic.APIStatusError as e:
        log.error("Model xatosi %s: %s", e.status_code, e.message)
        return f"Model xatosi ({e.status_code}). Keyinroq urinib ko'ring."
    except anthropic.APIConnectionError:
        return "Model serveriga ulanib bo'lmadi — internetni tekshiring."
