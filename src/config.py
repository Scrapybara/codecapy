from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    github_webhook_secret: str
    github_app_id: str
    github_private_key: str
    scrapybara_api_key: str
    openai_api_key: str
    anthropic_api_key: Optional[str] = (
        None  # Optional, will use Scrapybara agent credit if not provided
    )
    supabase_url: Optional[str] = (
        None  # Optional, will not store any data if not provided
    )
    supabase_key: Optional[str] = (
        None  # Optional, will not store any data if not provided
    )

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
