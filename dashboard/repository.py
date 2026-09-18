"""Dashboard identity, OAuth state, and per-user preferences persistence."""
from typing import Any
import time

from contextlib import nullcontext
from database import require_current, transaction, lock_resource


class DashboardRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        require_current(self.database_url)

    def _connection(self):
        return transaction(self.database_url)

    def create_dashboard_session(self, session_id: str, access_token: str, expires_in: int) -> None:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("DELETE FROM dashboard_sessions WHERE expires_at <= %s", (now,))
            connection.execute("INSERT INTO dashboard_sessions (session_id, access_token, expires_at) VALUES (%s, %s, %s)", (session_id, access_token, now + expires_in))

    def dashboard_session_token(self, session_id: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute("SELECT access_token FROM dashboard_sessions WHERE session_id = %s AND expires_at > %s", (session_id, int(time.time()))).fetchone()
        return row["access_token"] if row else None

    def delete_dashboard_session(self, session_id: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM dashboard_sessions WHERE session_id = %s", (session_id,))

    def dashboard_preferences(self, user_id: int, *, _conn=None) -> dict[str, Any]:
        with (nullcontext(_conn) if _conn is not None else self._connection()) as connection:
            row = connection.execute("SELECT * FROM dashboard_preferences WHERE user_id=%s", (user_id,)).fetchone()
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
        with self._connection() as connection:
            lock_resource(connection, 'dashboard-preferences', user_id)
            current = self.dashboard_preferences(user_id, _conn=connection)
            if expected_revision is not None and current["revision"] != expected_revision:
                raise RuntimeError("revision_conflict")
            connection.execute("""INSERT INTO dashboard_preferences
                (user_id,locale,appearance,color_scheme,navigation_collapsed,revision,updated_at)
                VALUES(%s,%s,%s,%s,%s,1,%s) ON CONFLICT(user_id) DO UPDATE SET locale=excluded.locale,
                appearance=excluded.appearance,color_scheme=excluded.color_scheme,
                navigation_collapsed=excluded.navigation_collapsed,revision=dashboard_preferences.revision+1,
                updated_at=excluded.updated_at""",
                (user_id, locale, appearance, color_scheme, int(navigation_collapsed), int(time.time())))
            return self.dashboard_preferences(user_id, _conn=connection)

    def create_oauth_state(self, state: str, expires_in: int = 600) -> None:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("DELETE FROM oauth_states WHERE expires_at <= %s", (now,))
            connection.execute("INSERT INTO oauth_states (state, expires_at) VALUES (%s, %s)", (state, now + expires_in))

    def consume_oauth_state(self, state: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM oauth_states WHERE state = %s AND expires_at > %s", (state, int(time.time())))
        return cursor.rowcount == 1
