"""Konfiguratsiya: muhit o'zgaruvchilari yoki .env fayldan o'qiladi."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="JARVIS_", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"

    # API porti. Docker konteyner ichida 8000 (compose tashqariga JARVIS_PORT ni ochadi).
    port: int = 8010
    # JARVIS.app (menyu paneli) API porti — Docker (8010) bilan to'qnashmasligi uchun alohida.
    app_port: int = 8020

    # Telegram: token bo'sh bo'lsa bot ishga tushmaydi (faqat API ishlaydi).
    telegram_token: str = ""
    owner_telegram_id: int = 0

    # Agent modeli (Model Router). Kalit bo'lmasa agent o'chiq, oddiy qoidalar ishlaydi.
    anthropic_api_key: str = Field(
        default="", validation_alias=AliasChoices("JARVIS_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
    )
    model: str = "claude-opus-5-5"
    model_effort: str = "medium"  # low | medium | high | xhigh | max

    # Ovoz (STT): lokal Whisper. Model birinchi ishlatilganda yuklab olinadi.
    # O'zbek tili uchun kichik modellar sust; large-v3-turbo — sifat va tezlik muvozanati.
    stt_model: str = "large-v3-turbo"
    stt_language: str = "uz"  # bo'sh qoldirilsa til avtomatik aniqlanadi
    voice_max_seconds: int = 300

    database_url: str = "postgresql://jarvis:jarvis@localhost:5432/jarvis"

    # Fayl tool'lari faqat shu papkalar ichida ishlaydi.
    allowed_roots: list[Path] = [Path.home() / "Documents", Path("/tmp/jarvis")]

    # Eslatmalar fayli. Bo'sh bo'lsa: Obsidian vault topilsa <vault>/JARVIS/Eslatmalar.md,
    # aks holda ~/Documents/JARVIS/eslatmalar.md.
    notes_file: Path | None = None
    # Obsidian vault papkasi. Bo'sh bo'lsa Obsidian sozlamalaridan avtomatik topiladi.
    obsidian_vault: Path | None = None

    policy_file: Path = Path(__file__).resolve().parent.parent / "config" / "commands.yaml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
