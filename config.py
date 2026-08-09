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
            data_dir=BASE_DIR / os.getenv("DATA_DIR", "data"),
            database_path=BASE_DIR / os.getenv("DATABASE_PATH", "data/tueka.sqlite3"),
            banned_words_file=BASE_DIR / os.getenv("BANNED_WORDS_FILE", "banned_words.csv"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
