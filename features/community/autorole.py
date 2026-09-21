"""autorole metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("autorole", "community", "field.default_role", "settings.enable.description", "badge-check", "/docs/features/autorole", ("default_role_id",), ("default_role_id",), ("manage_roles",), copy_ja=("初期ロール", "参加したメンバーへ初期ロールを付与します。"), order=1,
    bindings=(Binding('autorole_bot', 'bot', 'cogs.community.autorole:setup', 14),))
