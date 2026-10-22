from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/polis.db"
    frontend_url: str = "http://127.0.0.1:5173"
    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""
    admin_username: str = "admin"
    admin_password: str = "admin"
    admin_token_ttl_hours: int = 12
    map_dir: Path = Path("assets/maps")
    data_dir: Path = Path("data")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
