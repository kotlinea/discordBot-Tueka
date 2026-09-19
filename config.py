"""Environment-based application configuration."""
from dataclasses import dataclass
import os
from pathlib import Path

from database import database_url
from runtime.environment import load_environment


BASE_DIR = Path(__file__).resolve().parent
load_environment()


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
    social_webhook_secret: str | None
    social_x_mode: str
    social_max_subscriptions_per_provider: int
    social_poll_interval_seconds: int
    instagram_rss_url_template: str | None
    instagram_rss_auth_token: str | None
    ticket_encryption_key: str | None
    ticket_s3_endpoint_url: str | None
    ticket_s3_region: str | None
    ticket_s3_bucket: str | None
    ticket_s3_access_key_id: str | None
    ticket_s3_secret_access_key: str | None
    ticket_s3_prefix: str
    reaction_role_max_mappings_per_message: int
    dashboard_base_url: str | None
    data_dir: Path
    database_url: str
    log_level: str = "INFO"
    extensions: tuple[str, ...] = (
        "cogs.general",
        "cogs.ai",
        "cogs.leveling",
        "cogs.moderation",
        "cogs.safety",
        "cogs.reaction_roles",
        "cogs.automod",
        "cogs.moderation_commands",
        "cogs.community",
        "cogs.tickets",
        "cogs.engagement",
        "cogs.suggestions",
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
            social_webhook_secret=os.getenv("SOCIAL_WEBHOOK_SECRET"),
            social_x_mode=os.getenv("SOCIAL_X_MODE", "stream").lower() if os.getenv("SOCIAL_X_MODE", "stream").lower() in {"stream", "poll"} else "stream",
            social_max_subscriptions_per_provider=max(1, min(int(os.getenv("SOCIAL_MAX_SUBSCRIPTIONS_PER_PROVIDER", "10")), 100)),
            social_poll_interval_seconds=max(30, min(int(os.getenv("SOCIAL_POLL_INTERVAL_SECONDS", "120")), 3600)),
            instagram_rss_url_template=os.getenv("INSTAGRAM_RSS_URL_TEMPLATE"),
            instagram_rss_auth_token=os.getenv("INSTAGRAM_RSS_AUTH_TOKEN"),
            ticket_encryption_key=os.getenv("TICKET_ENCRYPTION_KEY"),
            ticket_s3_endpoint_url=os.getenv("TICKET_S3_ENDPOINT_URL"),
            ticket_s3_region=os.getenv("TICKET_S3_REGION"),
            ticket_s3_bucket=os.getenv("TICKET_S3_BUCKET"),
            ticket_s3_access_key_id=os.getenv("TICKET_S3_ACCESS_KEY_ID"),
            ticket_s3_secret_access_key=os.getenv("TICKET_S3_SECRET_ACCESS_KEY"),
            ticket_s3_prefix=os.getenv("TICKET_S3_PREFIX", "ticket-transcripts"),
            reaction_role_max_mappings_per_message=max(1, min(int(os.getenv("REACTION_ROLE_MAX_MAPPINGS_PER_MESSAGE", "20")), 100)),
            dashboard_base_url=os.getenv("DASHBOARD_BASE_URL"),
            data_dir=BASE_DIR / os.getenv("DATA_DIR", "data"),
            database_url=database_url(),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
