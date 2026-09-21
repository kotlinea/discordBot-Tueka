"""Welcome settings defaults and validation, independent of transport."""
from typing import Any
from template_defaults import TEMPLATE_DEFAULTS


def validate(enabled: bool, settings: dict[str, Any]) -> None:
    if not enabled:
        return
    for event in ('welcome', 'leave'):
        if settings.get(f'{event}_enabled'):
            content = str(settings.get(f'{event}_content') or '').strip()
            if not settings.get(f'{event}_channel_id') or not content or (settings.get(f'{event}_format', 'text') == 'text' and len(content) > 2000):
                raise ValueError('welcome_settings')

def normalize(settings: dict[str, Any]) -> dict[str, Any]:
    """Apply defaults without silently enabling messages."""
    defaults = {
        "welcome_enabled": False,
        "welcome_channel_id": None,
        "welcome_format": "text",
        "welcome_content": TEMPLATE_DEFAULTS["welcome_content"],
        "leave_enabled": False,
        "leave_channel_id": None,
        "leave_format": "text",
        "leave_content": TEMPLATE_DEFAULTS["leave_content"],
    }
    defaults.update(settings)
    for field in ("welcome_content", "leave_content"):
        if not str(defaults.get(field) or "").strip():
            defaults[field] = TEMPLATE_DEFAULTS[field]
    if defaults["welcome_format"] not in {"text", "embed"}:
        defaults["welcome_format"] = "text"
    if defaults["leave_format"] not in {"text", "embed"}:
        defaults["leave_format"] = "text"
    return defaults

