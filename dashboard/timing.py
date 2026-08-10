"""Request-local timing used by the dashboard's Server-Timing header."""
from contextvars import ContextVar


_metrics: ContextVar[dict[str, float] | None] = ContextVar("dashboard_timing", default=None)


def begin() -> object:
    return _metrics.set({"discord_ms": 0.0, "template_ms": 0.0})


def end(token: object) -> dict[str, float]:
    metrics = _metrics.get() or {"discord_ms": 0.0, "template_ms": 0.0}
    _metrics.reset(token)
    return metrics


def add(name: str, milliseconds: float) -> None:
    if metrics := _metrics.get():
        metrics[name] = metrics.get(name, 0.0) + milliseconds
