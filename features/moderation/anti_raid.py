"""anti_raid metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("anti_raid", "moderation", "feature.anti_raid", "feature.anti_raid.description", "shield-alert", "/docs/features/anti-raid", ("log_channel_id", "notify_channel_id", "default_lockdown_minutes", "immune_role_ids", "immune_user_ids", "immune_channel_ids"), (), ("manage_channels", "moderate_members", "kick_members", "ban_members"), "moderation", copy_ja=("Anti-Raid", "参加・退出の急増を検知し、制裁やLockdownを実行します。"), order=6,
    bindings=())

