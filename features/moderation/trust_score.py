"""trust_score metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("trust_score", "moderation", "feature.trust_score", "feature.trust_score.description", "shield-check", "/docs/features/trust-score", ("trust_retention_days", "trust_flag_threshold"), (), (), "moderation", copy_ja=("信頼度スコア", "違反履歴を管理者だけに可視化します。"), order=18,
    bindings=(
        Binding('trust_bot', 'bot', 'cogs.moderation.trust_score:setup', 12),
    ))

