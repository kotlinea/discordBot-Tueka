"""Application intake and review registration."""
from ..contracts import Binding, Feature

FEATURE = Feature('applications','community','feature.applications','feature.applications.description','scroll-text',
    '/docs/features/applications',copy_ja=('申請フォーム','応募や申請を受け付け、回答と審査履歴を管理します。'), order=25,
    bindings=(Binding('applications_bot','bot','cogs.community.applications:setup',25),
              Binding('applications_api','api','dashboard.api.community.applications:create_router',25)))
