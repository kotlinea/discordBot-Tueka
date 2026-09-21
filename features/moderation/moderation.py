"""moderation metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("moderation", "moderation", "feature.moderation", "feature.moderation.description", "shield-alert", "/docs/features/moderation", ("default_log_channel_id", "immune_role_ids", "immune_user_ids", "immune_channel_ids", "evidence_excluded_channel_ids", "evidence_retention_days", "exclude_bots", "exclude_webhooks"), (), ("manage_messages", "send_messages"), copy_ja=("モデレーション", "警告と制裁の設定を管理します。"), order=3,
    bindings=(
        Binding('moderation_bot', 'bot', 'cogs.moderation:setup', 3),
    ))

