"""automod metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("automod", "moderation", "feature.automod", "feature.automod.description", "shield-ban", "/docs/features/automod", ("log_channel_id", "immune_role_ids", "immune_user_ids", "immune_channel_ids"), (), ("manage_messages", "send_messages"), "moderation", copy_ja=("AutoMod", "柔軟なルール、例外、複数アクションでサーバーを保護します。"), order=4,
    bindings=())

