"""Pure audit_log settings normalization."""
from typing import Any

def normalize(settings: dict[str, Any]) -> dict[str, Any]:
    """Apply explicit category defaults."""
    defaults: dict[str, Any] = {
        "management_channel_id": None,
        "log_message": False,
        "log_voice": False,
        "log_channel": False,
        "log_member": False,
        "log_role": False,
        "log_server": False,
    }
    defaults.update(settings)
    return defaults
