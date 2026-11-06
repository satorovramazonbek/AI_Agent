"""Konfiguratsiya: muhit o'zgaruvchilari yoki .env fayldan o'qiladi."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="JARVIS_", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"

    # API porti. Docker konteyner ichida 8000 (compose tashqariga JARVIS_PORT ni ochadi).
    port: int = 8010

    # Telegram: token bo'sh bo'lsa bot ishga tushmaydi (faqat API ishlaydi).
    telegram_token: str = ""
    owner_telegram_id: int = 0

    # Ovoz (STT): lokal Whisper. Model birinchi ishlatilganda yuklab olinadi.
    # O'zbek tili uchun kichik modellar sust; large-v3-turbo — sifat va tezlik muvozanati.
    stt_model: str = "large-v3-turbo"
    stt_language: str = "uz"  # bo'sh qoldirilsa til avtomatik aniqlanadi
    voice_max_seconds: int = 300

    database_url: str = "postgresql://jarvis:jarvis@localhost:5432/jarvis"

    # Fayl tool'lari faqat shu papkalar ichida ishlaydi.
    allowed_roots: list[Path] = [Path.home() / "Documents", Path("/tmp/jarvis")]

    policy_file: Path = Path(__file__).resolve().parent.parent / "config" / "commands.yaml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
