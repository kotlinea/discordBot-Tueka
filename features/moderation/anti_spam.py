"""anti_spam metadata and explicit runtime bindings."""
from ..contracts import Binding, Feature

FEATURE = Feature("anti_spam", "moderation", "feature.anti_spam", "feature.anti_spam.description", "shield-ban", "/docs/features/anti-spam", ("log_channel_id", "immune_role_ids", "immune_user_ids", "immune_channel_ids"), (), ("manage_messages", "moderate_members"), "moderation", copy_ja=("Anti-Spam", "連投、重複、メンション、リアクションスパムを検知します。"), order=5,
    bindings=())

