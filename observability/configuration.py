"""Shared operational thresholds for HTTP metrics and operator commands."""
import os


def thresholds():
    return {
        'heartbeat_age': max(5, min(3600, int(os.getenv('HEARTBEAT_MAX_AGE_SECONDS', '30')))),
        'queue_age': max(1, min(86400, int(os.getenv('OUTBOX_MAX_AGE_SECONDS', '300')))),
    }
