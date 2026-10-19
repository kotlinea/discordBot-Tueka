"""Independent appeal review and private ModMail registration."""
from ..contracts import Binding, Feature
FEATURE=Feature('appeals','moderation','feature.appeals','feature.appeals.description','scroll-text',
    '/docs/features/appeals',('retention_days',),copy_ja=('異議申立て・ModMail','本人と管理者の非公開のやり取り、処置の再審査と履歴を管理します。'),order=26,
    bindings=(Binding('appeals_bot','bot','cogs.moderation.appeals:setup',26),Binding('appeals_api','api','dashboard.api.moderation.appeals:create_router',26)))
