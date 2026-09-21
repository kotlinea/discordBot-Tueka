"""welcome metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("welcome", "community", "feature.welcome", "feature.welcome.description", "door-open", "/docs/features/welcome", ("welcome_enabled", "welcome_channel_id", "welcome_format", "welcome_content", "leave_enabled", "leave_channel_id", "leave_format", "leave_content"), (), ("send_messages",), copy_ja=("入退室", "歓迎・退出メッセージを管理します。"), order=0,
    bindings=(
        Binding('welcome_bot', 'bot', 'cogs.community.welcome:setup', 14),
    ), settings_factory='dashboard.api.community.welcome:create_settings')
