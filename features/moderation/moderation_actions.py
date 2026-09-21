"""moderation_actions metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("moderation_actions", "moderation", "feature.moderation_actions", "feature.moderation_actions.description", "hand", "/docs/features/moderation-actions", (), (), ("manage_messages", "manage_channels", "moderate_members", "kick_members", "ban_members"), "moderation", copy_ja=("Moderation Actions", "手動処置とLockdownの状態を管理します。"), order=8,
    bindings=(
        Binding('safety_bot', 'bot', 'cogs.safety:setup', 4),
        Binding('moderation_commands_bot', 'bot', 'cogs.moderation_commands:setup', 7),
    ))

