"""Server activity aggregates and content-free observation registration."""
from ..contracts import Binding, Feature

FEATURE = Feature('insights', 'community', 'feature.insights', 'feature.insights.description', 'chart-line',
                  '/docs/features/insights', copy_ja=('Server Insights', '投稿・入退室・音声チャンネルの接続時間を日別に確認します。'),
                  order=30, module_write=False,
                  bindings=(Binding('insights_bot', 'bot', 'cogs.community.insights:setup', 30),
                            Binding('insights_api', 'api', 'dashboard.api.community.insights:create_router', 30)))
