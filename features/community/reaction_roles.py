"""reaction_roles metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("reaction_roles", "community", "feature.reaction_roles", "feature.reaction_roles.description", "hand", "/docs/features/reaction-roles", (), (), ("manage_roles", "send_messages", "add_reactions", "read_message_history", "manage_messages"), copy_ja=("リアクションロール", "EmojiへのリアクションでRoleを自己付与・解除できます。"), order=11,
    bindings=(
        Binding('reaction_roles_bot', 'bot', 'cogs.community.reaction_roles:setup', 5),
        Binding('reaction_roles_api', 'api', 'dashboard.api.community.reaction_roles:create_router', 6),
    ), settings_factory='dashboard.api.community.reaction_roles:create_settings', module_write=False)
