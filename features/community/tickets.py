"""tickets metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("tickets", "community", "feature.tickets", "feature.tickets.description", "ticket", "/docs/features/tickets", (), (), ("manage_channels", "manage_threads", "create_private_threads", "send_messages_in_threads", "send_messages", "read_message_history", "manage_messages", "embed_links", "attach_files"), copy_ja=("サポートチケット", "非公開の問い合わせ対応と対応履歴を管理します。"), order=14,
    bindings=(
        Binding('tickets_bot', 'bot', 'cogs.community.tickets:setup', 9),
        Binding('ticket_configuration_api', 'api', 'dashboard.api.community.ticket_support.configuration:create_router', 4),
        Binding('tickets_api', 'api', 'dashboard.api.community.tickets:create_router', 5),
    ), settings_factory='dashboard.api.community.tickets:create_settings', module_write=False)
