"""twitch_updates metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("twitch_updates", "social", "feature.twitch_updates", "feature.twitch_updates.description", "twitch", "/docs/social/twitch", (), (), ("send_messages",), copy_ja=("Twitch通知", "配信開始・終了を通知します。"), order=20,
    bindings=())

