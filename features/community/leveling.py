"""leveling metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("leveling", "community", "feature.leveling", "feature.leveling.description", "trophy", "/docs/features/leveling", ("text_notification_channel_id", "text_role_rewards", "voice_enabled", "voice_notification_channel_id", "voice_role_rewards", "voice_xp_per_minute", "voice_allow_solo", "voice_allow_muted"), ("text_notification_channel_id",), ("send_messages",), copy_ja=("レベリング", "メッセージでXPを獲得するシステムです。"), order=2,
    bindings=(
        Binding('leveling_bot', 'bot', 'cogs.community.leveling:setup', 2),
    ), settings_factory='dashboard.api.community.leveling:create_settings')
