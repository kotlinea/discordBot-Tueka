"""Durable announcements and Discord external-event registration."""
from ..contracts import Binding, Feature

FEATURE = Feature('scheduled_messages','engagement','feature.scheduled_messages','feature.scheduled_messages.description',
    'bell-ring','/docs/features/scheduled-messages',('retention_days',),
    copy_ja=('予約メッセージ・イベント','メッセージの予約投稿とDiscordイベントの作成を管理します。'),order=27,
    bindings=(Binding('scheduled_messages_bot','bot','cogs.engagement.scheduled_messages:setup',27),
              Binding('scheduled_messages_api','api','dashboard.api.engagement.scheduled_messages:create_router',27)))
