"""youtube_updates metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("youtube_updates", "social", "feature.youtube_updates", "feature.youtube_updates.description", "youtube", "/docs/social/youtube", (), (), ("send_messages",), copy_ja=("YouTube通知", "新規動画・ライブ開始を通知します。"), order=19,
    bindings=())

