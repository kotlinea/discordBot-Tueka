"""advanced_polls metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("advanced_polls", "engagement", "feature.advanced_polls", "feature.advanced_polls.description", "chart-bar", "/docs/features/polls", (), copy_ja=("拡張投票", "最大10択、期限、画像付きのボタン投票を作成します。"), order=15,
    bindings=(Binding('advanced_polls_bot', 'bot', 'cogs.engagement.advanced_polls:setup', 10), ))
