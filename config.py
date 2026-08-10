"""Environment-based application configuration."""
from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _optional_int(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value else None


@dataclass(frozen=True)
class Settings:
    discord_token: str
    gemini_api_key: str | None
    gemini_model: str
    google_safe_browsing_api_key: str | None
    youtube_api_key: str | None
    twitch_client_id: str | None
    twitch_client_secret: str | None
    tiktok_client_key: str | None
    tiktok_client_secret: str | None
    tiktok_redirect_uri: str | None
    instagram_app_id: str | None
    instagram_app_secret: str | None
    instagram_redirect_uri: str | None
    x_bearer_token: str | None
    social_token_encryption_key: str | None
    dashboard_base_url: str | None
    data_dir: Path
    database_path: Path
    banned_words_file: Path
    log_level: str = "INFO"
    extensions: tuple[str, ...] = (
        "cogs.general",
        "cogs.ai",
        "cogs.leveling",
        "cogs.moderation",
        "cogs.safety",
        "cogs.community",
        "cogs.engagement",
        "cogs.trust",
        "cogs.audit_log",
        "cogs.welcome",
        "cogs.social_updates",
    )

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise RuntimeError("DISCORD_TOKEN is not set. Copy .env.example to .env and configure it.")
        return cls(
            discord_token=token,
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            google_safe_browsing_api_key=os.getenv("GOOGLE_SAFE_BROWSING_API_KEY"),
            youtube_api_key=os.getenv("YOUTUBE_API_KEY"),
            twitch_client_id=os.getenv("TWITCH_CLIENT_ID"),
            twitch_client_secret=os.getenv("TWITCH_CLIENT_SECRET"),
            tiktok_client_key=os.getenv("TIKTOK_CLIENT_KEY"),
            tiktok_client_secret=os.getenv("TIKTOK_CLIENT_SECRET"),
            tiktok_redirect_uri=os.getenv("TIKTOK_REDIRECT_URI"),
            instagram_app_id=os.getenv("INSTAGRAM_APP_ID"),
            instagram_app_secret=os.getenv("INSTAGRAM_APP_SECRET"),
            instagram_redirect_uri=os.getenv("INSTAGRAM_REDIRECT_URI"),
            x_bearer_token=os.getenv("X_BEARER_TOKEN"),
            social_token_encryption_key=os.getenv("SOCIAL_TOKEN_ENCRYPTION_KEY"),
            dashboard_base_url=os.getenv("DASHBOARD_BASE_URL"),
            data_dir=BASE_DIR / os.getenv("DATA_DIR", "data"),
            database_path=BASE_DIR / os.getenv("DATABASE_PATH", "data/tueka.sqlite3"),
            banned_words_file=BASE_DIR / os.getenv("BANNED_WORDS_FILE", "banned_words.csv"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
