"""audit_log metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("audit_log", "moderation", "feature.audit_log", "feature.audit_log.description", "scroll-text", "/docs/features/audit-log", ("management_channel_id", "log_message", "log_voice", "log_channel", "log_member", "log_role", "log_server"), (), ("send_messages",), "moderation", copy_ja=("サーバーログ", "サーバー内のイベントをカテゴリ別に記録します。"), order=10,
    bindings=(
        Binding('audit_log_bot', 'bot', 'cogs.audit_log:setup', 13),
    ))

