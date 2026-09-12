"""Dashboard identity, OAuth state, and per-user preferences persistence."""
from pathlib import Path
from typing import Any
import time

from database import require_current, transaction


class DashboardRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        require_current(self.database_path)

    def _connection(self):
        return transaction(self.database_path)

    def create_dashboard_session(self, session_id: str, access_token: str, expires_in: int) -> None:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("DELETE FROM dashboard_sessions WHERE expires_at <= ?", (now,))
            connection.execute("INSERT INTO dashboard_sessions (session_id, access_token, expires_at) VALUES (?, ?, ?)", (session_id, access_token, now + expires_in))

    def dashboard_session_token(self, session_id: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute("SELECT access_token FROM dashboard_sessions WHERE session_id = ? AND expires_at > ?", (session_id, int(time.time()))).fetchone()
        return row["access_token"] if row else None

    def delete_dashboard_session(self, session_id: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM dashboard_sessions WHERE session_id = ?", (session_id,))

    def dashboard_preferences(self, user_id: int) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM dashboard_preferences WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            return {"locale": "ja", "appearance": "precision", "color_scheme": "system",
                    "navigation_collapsed": False, "revision": 0}
        value = dict(row)
        value.pop("user_id", None)
        value.pop("updated_at", None)
        value["navigation_collapsed"] = bool(value["navigation_collapsed"])
        return value

    def set_dashboard_preferences(self, user_id: int, *, locale: str, appearance: str, color_scheme: str,
                                  navigation_collapsed: bool, expected_revision: int | None = None) -> dict[str, Any]:
        if locale not in {"ja", "en"} or appearance not in {"precision", "community", "atmosphere"} \
                or color_scheme not in {"system", "light", "dark"}:
            raise ValueError("invalid_preferences")
        current = self.dashboard_preferences(user_id)
        if expected_revision is not None and current["revision"] != expected_revision:
            raise RuntimeError("revision_conflict")
        with self._connection() as connection:
            connection.execute("""INSERT INTO dashboard_preferences
                (user_id,locale,appearance,color_scheme,navigation_collapsed,revision,updated_at)
                VALUES(?,?,?,?,?,1,?) ON CONFLICT(user_id) DO UPDATE SET locale=excluded.locale,
                appearance=excluded.appearance,color_scheme=excluded.color_scheme,
                navigation_collapsed=excluded.navigation_collapsed,revision=dashboard_preferences.revision+1,
                updated_at=excluded.updated_at""",
                (user_id, locale, appearance, color_scheme, int(navigation_collapsed), int(time.time())))
        return self.dashboard_preferences(user_id)

    def create_oauth_state(self, state: str, expires_in: int = 600) -> None:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("DELETE FROM oauth_states WHERE expires_at <= ?", (now,))
            connection.execute("INSERT INTO oauth_states (state, expires_at) VALUES (?, ?)", (state, now + expires_in))

    def consume_oauth_state(self, state: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM oauth_states WHERE state = ? AND expires_at > ?", (state, int(time.time())))
        return cursor.rowcount == 1
