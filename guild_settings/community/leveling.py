"""Pure leveling settings normalization."""
from typing import Any

def normalize(settings: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "text_notification_channel_id": None,
        "text_role_rewards": [],
        "voice_enabled": False,
        "voice_notification_channel_id": None,
        "voice_role_rewards": [],
        "voice_xp_per_minute": 5,
        "voice_allow_solo": False,
        "voice_allow_muted": False,
    }
    defaults.update(settings)
    return defaults
