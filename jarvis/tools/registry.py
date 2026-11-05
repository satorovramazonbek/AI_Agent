"""Tool Registry: barcha vositalar shu yerda ro'yxatga olinadi.

Yangi tool qo'shish — `@tool(...)` dekoratori bilan funksiya yozish (hujjat, 10-bo'lim).
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, get_type_hints

from pydantic import BaseModel

from jarvis.security.policy import Risk


@dataclass
class ToolSpec:
    name: str
    description: str
    risk: Risk
    args_model: type[BaseModel]
    func: Callable[..., Awaitable[Any]]
    tags: list[str] = field(default_factory=list)
    timeout: float = 60.0

    def schema(self) -> dict:
        """Modelga beriladigan JSON Schema (tool-calling formati)."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.args_model.model_json_schema(),
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool allaqachon mavjud: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def list(self, *, max_risk: Risk = Risk.R3, tags: set[str] | None = None) -> list[ToolSpec]:
        """Modelga faqat ruxsat darajasi va vazifa turiga mos tool'larni ko'rsatish."""
        return [
            t
            for t in self._tools.values()
            if t.risk <= max_risk and (not tags or tags & set(t.tags))
        ]


registry = ToolRegistry()


def tool(
    *,
    name: str,
    description: str,
    risk: Risk,
    tags: list[str] | None = None,
    timeout: float = 60.0,
):
    def decorator(func: Callable[..., Awaitable[Any]]):
        params = list(inspect.signature(func).parameters.values())
        hints = get_type_hints(func)
        args_model = hints.get(params[0].name) if params else None
        if not (inspect.isclass(args_model) and issubclass(args_model, BaseModel)):
            raise TypeError(f"{name}: birinchi argument Pydantic modeli bo'lishi kerak")
        registry.register(
            ToolSpec(name, description, risk, args_model, func, tags or [], timeout)
        )
        return func

    return decorator
