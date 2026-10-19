"""Explicit reaction-driven highlights registration."""
from ..contracts import Binding,Feature

FEATURE=Feature('starboard','engagement','feature.starboard','feature.starboard.description','star','/docs/features/starboard',
    required_bot_permissions=('view_channel','read_message_history','send_messages','embed_links'),
    copy_ja=('Starboard / Highlights','選択したチャンネルの人気投稿を、リアクション数に応じて紹介します。'),order=28,
    bindings=(Binding('starboard_bot','bot','cogs.engagement.starboard:setup',28),Binding('starboard_api','api','dashboard.api.engagement.starboard:create_router',28)))
