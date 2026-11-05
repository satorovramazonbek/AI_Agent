"""Policy Gateway: har bir terminal buyrug'i bajarilishidan oldin shu yerda tekshiriladi.

Qaror model tomonidan emas, deterministik kod tomonidan qabul qilinadi.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

import yaml


class Risk(IntEnum):
    R0 = 0  # faqat o'qish
    R1 = 1  # xavfsiz yozish
    R2 = 2  # o'zgartirish — tasdiq
    R3 = 3  # qaytarilmas / tashqi — har safar tasdiq
    R4 = 4  # taqiqlangan


class Decision:
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass
class PolicyResult:
    decision: str
    risk: Risk
    reasons: list[str] = field(default_factory=list)


# Buyruqlarni bir-biridan ajratuvchi operatorlar: ; && || | va yangi qator.
_SPLIT_RE = re.compile(r"\|\||&&|;|\||\n")
_SHELLS = {"sh", "bash", "zsh", "fish"}


class CommandPolicy:
    def __init__(self, rules: dict):
        self.levels: dict[str, Risk] = {}
        for bucket in ("allow", "confirm"):
            for level, cmds in (rules.get(bucket) or {}).items():
                for cmd in cmds:
                    self.levels[cmd] = Risk[level]
        self.deny: set[str] = set(rules.get("deny") or [])
        self.subcommands: dict[str, Risk] = {
            k: Risk[v] for k, v in (rules.get("subcommands") or {}).items()
        }
        self.deny_patterns: list[str] = list(rules.get("deny_patterns") or [])

    @classmethod
    def from_file(cls, path: Path) -> CommandPolicy:
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")))

    def check(self, command: str, *, remote: bool = False) -> PolicyResult:
        """Buyruqni baholaydi. remote=True — Telegram orqali kelgan (qattiqroq)."""
        risk, reasons = self._evaluate(command, depth=0)
        if remote and risk == Risk.R1:
            risk = Risk.R2
            reasons.append("masofaviy buyruq: R1 -> R2")
        return PolicyResult(_decision_for(risk), risk, reasons)

    def _evaluate(self, command: str, depth: int) -> tuple[Risk, list[str]]:
        reasons: list[str] = []
        normalized = " ".join(command.split())
        if not normalized:
            return Risk.R4, ["bo'sh buyruq"]
        if depth > 3:
            return Risk.R4, ["juda chuqur ichma-ich buyruq"]

        for pat in self.deny_patterns:
            if pat in normalized:
                return Risk.R4, [f"taqiqlangan naqsh: {pat!r}"]

        worst = Risk.R0
        if "$(" in command or "`" in command:
            worst = Risk.R3
            reasons.append("buyruq ichida buyruq ($(...) yoki `...`)")
        if re.search(r"(?<![<>])>{1,2}(?!&)", command):
            worst = max(worst, Risk.R2)
            reasons.append("faylga yo'naltirish (>)")

        for segment in _SPLIT_RE.split(command):
            if not segment.strip():
                continue
            seg_risk, seg_reasons = self._evaluate_segment(segment, depth)
            reasons.extend(seg_reasons)
            worst = max(worst, seg_risk)
            if worst == Risk.R4:
                break
        return worst, reasons

    def _evaluate_segment(self, segment: str, depth: int) -> tuple[Risk, list[str]]:
        try:
            tokens = shlex.split(segment)
        except ValueError:
            return Risk.R4, [f"tahlil qilib bo'lmadi: {segment.strip()!r}"]
        # VAR=qiymat prefikslarini tashlab yuborish
        while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
            tokens.pop(0)
        if not tokens:
            return Risk.R0, []

        name = Path(tokens[0]).name  # /bin/rm -> rm
        if name in self.deny:
            return Risk.R4, [f"taqiqlangan buyruq: {name}"]

        # bash -c "..." -> ichki buyruqni ham tekshirish
        if name in _SHELLS:
            if len(tokens) >= 3 and tokens[1] == "-c":
                inner, inner_reasons = self._evaluate(tokens[2], depth + 1)
                return max(inner, Risk.R2), inner_reasons + [f"{name} -c orqali bajarish"]
            return Risk.R3, [f"interaktiv shell: {name}"]

        for n in (3, 2):
            key = " ".join([name, *tokens[1:n]])
            if key in self.subcommands:
                return self.subcommands[key], [f"{key}: {self.subcommands[key].name}"]

        if name in self.levels:
            return self.levels[name], [f"{name}: {self.levels[name].name}"]
        return Risk.R2, [f"ro'yxatda yo'q buyruq: {name} (tasdiq kerak)"]


def _decision_for(risk: Risk) -> str:
    if risk <= Risk.R1:
        return Decision.ALLOW
    if risk <= Risk.R3:
        return Decision.CONFIRM
    return Decision.DENY


def is_path_allowed(path: str | Path, allowed_roots: list[Path]) -> bool:
    """Yo'l ruxsat etilgan papkalardan biri ichidami (symlink va .. hal qilinadi)."""
    resolved = Path(path).expanduser().resolve()
    for root in allowed_roots:
        root_resolved = Path(root).expanduser().resolve()
        if resolved == root_resolved or root_resolved in resolved.parents:
            return True
    return False
