from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str

    # LLM provider for /mode quality and /mode hybrid: openai or gemini.
    # Can be changed per project with /provider openai|gemini.
    llm_provider: str = "openai"

    # Optional in free mode. Required only when LLM_PROVIDER=openai and mode is quality/hybrid.
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"

    # Optional in free mode. Required only when LLM_PROVIDER=gemini and mode is quality/hybrid.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"

    # LibreTranslate can be local/self-hosted or a managed instance.
    libretranslate_url: str = "http://localhost:5000"
    libretranslate_api_key: str = ""
    libretranslate_timeout_seconds: int = 120

    # Default project mode: free, quality, or hybrid.
    default_translation_mode: str = "hybrid"

    database_path: Path = Path("storage/bot.sqlite3")
    storage_dir: Path = Path("storage")

    max_download_mb: int = 18
    chunk_max_chars: int = 6500
    max_parallel_jobs: int = 2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def input_dir(self) -> Path:
        return self.storage_dir / "input"

    @property
    def output_dir(self) -> Path:
        return self.storage_dir / "output"

    @property
    def max_download_bytes(self) -> int:
        return self.max_download_mb * 1024 * 1024
