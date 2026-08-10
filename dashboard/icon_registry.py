"""Fixed, local dashboard icons following Lucide's 24px outline style."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardIcon:
    label: str
    paths: str


ICONS: dict[str, DashboardIcon] = {
    "door-open": DashboardIcon("Door open", '<path d="M14 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><path d="M14 21H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8z"/><path d="M10 12h.01"/><path d="m14 8 4 4-4 4"/>'),
    "badge-check": DashboardIcon("Verified badge", '<path d="m12 2.7 2.1 2.3 3.1-.2.7 3 2.7 1.6-1.5 2.7 1.5 2.7-2.7 1.6-.7 3-3.1-.2-2.1 2.3-2.1-2.3-3.1.2-.7-3-2.7-1.6 1.5-2.7-1.5-2.7 2.7-1.6.7-3 3.1.2z"/><path d="m8.5 12 2.2 2.2 4.8-4.8"/>'),
    "trophy": DashboardIcon("Trophy", '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM7 6H4v1a4 4 0 0 0 4 4M17 6h3v1a4 4 0 0 1-4 4"/>'),
    "scroll-text": DashboardIcon("Activity log", '<path d="M8 3h8l3 3v13a2 2 0 0 1-2 2H8a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3zM8 8h8M8 12h8M8 16h5"/>'),
    "shield-alert": DashboardIcon("Moderation shield", '<path d="M12 3 4 7v5c0 5 3.4 8.8 8 10 4.6-1.2 8-5 8-10V7zM12 8v4M12 16h.01"/>'),
    "funnel": DashboardIcon("Filter", '<path d="M3 5h18l-7 8v5l-4 2v-7z"/>'),
    "shield-ban": DashboardIcon("Spam protection", '<path d="M12 3 4 7v5c0 5 3.4 8.8 8 10 4.6-1.2 8-5 8-10V7zM8 8l8 8"/>'),
    "hand": DashboardIcon("Hand", '<path d="M18 11V6a2 2 0 0 0-4 0v4M14 10V4a2 2 0 0 0-4 0v6M10 10V6a2 2 0 0 0-4 0v7a7 7 0 0 0 7 7h1a6 6 0 0 0 6-6v-3a2 2 0 0 0-4 0"/>'),
    "chart-line": DashboardIcon("Line chart", '<path d="M3 3v18h18M7 16l4-5 3 3 5-7"/>'),
    "microphone": DashboardIcon("Microphone", '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v4M8 21h8"/>'),
    "ticket": DashboardIcon("Support ticket", '<path d="M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4a2 2 0 0 0 0 4v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-4a2 2 0 0 0 0-4zM13 5v2M13 11v2M13 17v2"/>'),
    "chart-bar": DashboardIcon("Bar chart", '<path d="M3 3v18h18M7 16v-5M12 16V7M17 16v-8"/>'),
    "gamepad": DashboardIcon("Gamepad", '<path d="M6 9h12a4 4 0 0 1 3.8 5.3l-1 3A3 3 0 0 1 18 19.5l-2.2-1.1a8.5 8.5 0 0 0-7.6 0L6 19.5a3 3 0 0 1-2.8-2.2l-1-3A4 4 0 0 1 6 9zM7 14h4M9 12v4M16 13h.01M18 15h.01"/>'),
    "shield-check": DashboardIcon("Trust shield", '<path d="M12 3 4 7v5c0 5 3.4 8.8 8 10 4.6-1.2 8-5 8-10V7zM9 12l2 2 4-4"/>'),
}

ICON_IDS = frozenset(ICONS)


def get_icon(icon_id: str) -> DashboardIcon:
    try:
        return ICONS[icon_id]
    except KeyError as exc:
        raise ValueError(f"Unknown dashboard icon: {icon_id}") from exc
