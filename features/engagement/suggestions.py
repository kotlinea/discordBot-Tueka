"""suggestions metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("suggestions", "engagement", "feature.suggestions", "feature.suggestions.description", "lightbulb", "/docs/features/suggestions", ("channel_id", "log_channel_id", "review_role_ids", "allow_voting", "show_author", "discussion_enabled", "form_title", "form_fields", "categories", "tags", "retention_days"), ("channel_id",), ("send_messages", "embed_links"), copy_ja=("Suggestions", "メンバーの提案をフォームで受け付け、投票と審査を管理します。"), order=16,
    bindings=(
        Binding('suggestions_bot', 'bot', 'cogs.engagement.suggestions:setup', 11),
        Binding('suggestions_api', 'api', 'dashboard.api.engagement.suggestions:create_router', 2),
    ))

