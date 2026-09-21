"""moderation_logs metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("moderation_logs", "moderation", "feature.moderation_logs", "feature.moderation_logs.description", "scroll-text", "/docs/features/moderation-logs", ("log_channel_id",), (), ("send_messages", "view_audit_log"), "moderation", copy_ja=("Moderation Logs", "検知、制裁、管理操作を一元的に記録します。"), order=9,
    bindings=(Binding('moderation_logs_api', 'api', 'dashboard.api.moderation.moderation_logs:create_router', 8), ))
