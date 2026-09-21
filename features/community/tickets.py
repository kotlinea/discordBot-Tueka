"""tickets metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("tickets", "community", "feature.tickets", "feature.tickets.description", "ticket", "/docs/features/tickets", (), (), ("manage_channels", "manage_threads", "create_private_threads", "send_messages_in_threads", "send_messages", "read_message_history", "manage_messages", "embed_links", "attach_files"), copy_ja=("サポートチケット", "プライベートな会員サポートと議事録を管理します。"), order=14,
    bindings=(
        Binding('tickets_bot', 'bot', 'cogs.tickets:setup', 9),
        Binding('ticket_configuration_api', 'api', 'dashboard.api.ticket_configuration:create_router', 4),
        Binding('tickets_api', 'api', 'dashboard.api.tickets:create_router', 5),
    ))

