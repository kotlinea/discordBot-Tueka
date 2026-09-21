"""live_stats metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("live_stats", "community", "feature.live_stats", "feature.live_stats.description", "chart-line", "/docs/features/live-stats", ("stats_channel_id", "stats_template"), ("stats_channel_id",), ("manage_channels",), copy_ja=("ライブ統計チャンネル", "メンバー数などをボイスチャンネル名に自動表示します。"), order=12,
    bindings=(Binding('live_stats_bot', 'bot', 'cogs.community.live_stats:setup', 8), ))
