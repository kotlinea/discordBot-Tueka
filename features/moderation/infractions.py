"""infractions metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("infractions", "moderation", "feature.infractions", "feature.infractions.description", "shield-check", "/docs/features/infractions", ("point_thresholds", "log_channel_id"), (), ("moderate_members", "kick_members", "ban_members"), "moderation", copy_ja=("Warnings / Infractions", "警告ポイント、違反履歴、段階的制裁を管理します。"), order=7,
    bindings=(Binding('infractions_api', 'api', 'dashboard.api.moderation.infractions:create_router', 8), ))
