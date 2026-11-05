"""Konfiguratsiya: muhit o'zgaruvchilari yoki .env fayldan o'qiladi."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="JARVIS_", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"

    # Telegram: token bo'sh bo'lsa bot ishga tushmaydi (faqat API ishlaydi).
    telegram_token: str = ""
    owner_telegram_id: int = 0

    database_url: str = "postgresql://jarvis:jarvis@localhost:5432/jarvis"

    # Fayl tool'lari faqat shu papkalar ichida ishlaydi.
    allowed_roots: list[Path] = [Path.home() / "Documents", Path("/tmp/jarvis")]

    policy_file: Path = Path(__file__).resolve().parent.parent / "config" / "commands.yaml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
