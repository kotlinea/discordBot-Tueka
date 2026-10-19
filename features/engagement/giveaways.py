"""Giveaway and community registration feature registration."""
from ..contracts import Binding, Feature

FEATURE = Feature('giveaways', 'engagement', 'feature.giveaways', 'feature.giveaways.description', 'trophy', '/docs/features/giveaways',
                  required_bot_permissions=('view_channel', 'read_message_history', 'send_messages', 'embed_links'),
                  copy_ja=('Giveaways / Community Events', '参加条件と締切を設定し、抽選やイベント参加受付を管理します。'), order=29,
                  bindings=(Binding('giveaways_bot', 'bot', 'cogs.engagement.giveaways:setup', 29),
                            Binding('giveaways_api', 'api', 'dashboard.api.engagement.giveaways:create_router', 29)))
