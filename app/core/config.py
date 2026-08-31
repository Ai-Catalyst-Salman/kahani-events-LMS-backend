"""
app/core/config.py
------------------
Loads environment variables from .env using pydantic-settings.
All secrets are consumed here and nowhere else.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str
    supabase_service_role_key: str
    gemini_api_key: str | None = None

    # Email Settings
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""

    # CORS origin — change this env var (not the code) when deploying.
    # For production, set FRONTEND_ORIGIN to your deployed frontend URL,
    # e.g. https://training.kahaniEvents.com
    frontend_origin: str = "http://localhost:5173"
    live_platform_url: str = "https://kahani-events-lms-frontend.vercel.app"

settings = Settings()
