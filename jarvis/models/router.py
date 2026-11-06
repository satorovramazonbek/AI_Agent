"""Model Router: LLM chaqiruvlarining yagona nuqtasi (hujjat, 5.10-bo'lim).

Hozircha bitta provayder — Anthropic Claude. Boshqa modullar SDK'ni to'g'ridan-to'g'ri
chaqirmaydi, shuning uchun keyin zaxira provayder yoki byudjet qoidalarini faqat shu yerda
qo'shish kifoya.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from jarvis.config import get_settings


class ModelUnavailable(RuntimeError):
    """API kaliti yo'q yoki SDK o'rnatilmagan."""


class ModelRouter:
    def __init__(self, api_key: str, model: str, effort: str):
        self.api_key = api_key
        self.model = model
        self.effort = effort
        self._client: Any = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _get_client(self) -> Any:
        if not self.available:
            raise ModelUnavailable("ANTHROPIC_API_KEY sozlanmagan")
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def complete(
        self, *, system: str, messages: list, tools: list[dict], max_tokens: int = 16000
    ) -> Any:
        client = self._get_client()
        return await client.beta.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tools,
            output_config={"effort": self.effort},
            cache_control={"type": "ephemeral"},
            # Xavfsizlik filtri so'rovni rad etsa, server o'zi mos zaxira modelga o'tadi.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )


@lru_cache
def get_router() -> ModelRouter:
    s = get_settings()
    return ModelRouter(s.anthropic_api_key, s.model, s.model_effort)
