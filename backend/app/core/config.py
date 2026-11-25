from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "MemoryShield AI"
    environment: str = "development"
    database_url: str = (
        "postgresql+psycopg://memoryshield:memoryshield_dev@localhost:5434/memoryshield"
    )

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
