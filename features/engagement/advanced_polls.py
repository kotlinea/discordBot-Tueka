"""advanced_polls metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("advanced_polls", "engagement", "feature.advanced_polls", "feature.advanced_polls.description", "chart-bar", "/docs/features/polls", (), copy_ja=("拡張投票", "最大25択の投票、匿名性、予約、結果の公開範囲を管理します。"), order=15,
    bindings=(Binding('advanced_polls_bot', 'bot', 'cogs.engagement.advanced_polls:setup', 10),
              Binding('advanced_polls_api', 'api', 'dashboard.api.engagement.advanced_polls:create_router', 10)),
    access_factory='dashboard.api.engagement.advanced_polls:create_access')
