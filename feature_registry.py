"""Single source of truth for dashboard feature modules."""
from dataclasses import dataclass

from dashboard.icon_registry import ICON_IDS


@dataclass(frozen=True)
class Feature:
    id: str
    category: str
    title_key: str
    description_key: str
    icon: str
    fields: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    required_bot_permissions: tuple[str, ...] = ()


FEATURES = (
    Feature("welcome", "community", "feature.welcome", "feature.welcome.description", "door-open", ("welcome_enabled", "welcome_channel_id", "welcome_format", "welcome_content", "leave_enabled", "leave_channel_id", "leave_format", "leave_content"), (), ("send_messages",)),
    Feature("autorole", "community", "field.default_role", "settings.enable.description", "badge-check", ("default_role_id",), ("default_role_id",), ("manage_roles",)),
    Feature("leveling", "community", "feature.leveling", "feature.leveling.description", "trophy", ("text_notification_channel_id", "text_role_rewards", "voice_enabled", "voice_notification_channel_id", "voice_role_rewards", "voice_xp_per_minute", "voice_allow_solo", "voice_allow_muted"), ("text_notification_channel_id",), ("send_messages",)),
    Feature("audit_log", "moderation", "feature.audit_log", "feature.audit_log.description", "scroll-text", ("management_channel_id", "log_message", "log_voice", "log_channel", "log_member", "log_role", "log_server"), (), ("send_messages",)),
    Feature("moderation", "moderation", "feature.moderation", "feature.moderation.description", "shield-alert", ("escalation_enabled", "escalation_threshold", "escalation_action", "escalation_timeout_minutes", "dm_notify"), (), ("moderate_members", "kick_members", "ban_members")),
    Feature("chat_filter", "moderation", "feature.chat_filter", "feature.chat_filter.description", "funnel", ("filter_keywords", "filter_regex", "filter_action", "safe_browsing_enabled"), (), ("manage_messages",)),
    Feature("anti_spam", "moderation", "feature.anti_spam", "feature.anti_spam.description", "shield-ban", ("spam_window_seconds", "spam_message_limit", "spam_mention_limit", "spam_duplicate_limit", "spam_action", "spam_timeout_minutes"), (), ("manage_messages",)),
    Feature("reaction_roles", "community", "feature.reaction_roles", "feature.reaction_roles.description", "hand", ("reaction_role_channel_id", "reaction_role_ids", "reaction_role_title", "reaction_role_description"), ("reaction_role_channel_id", "reaction_role_ids"), ("manage_roles", "send_messages")),
    Feature("live_stats", "community", "feature.live_stats", "feature.live_stats.description", "chart-line", ("stats_channel_id", "stats_template"), ("stats_channel_id",), ("manage_channels",)),
    Feature("temporary_voice", "community", "feature.temporary_voice", "feature.temporary_voice.description", "microphone", ("temp_voice_trigger_id", "temp_voice_category_id", "temp_voice_name"), ("temp_voice_trigger_id",), ("manage_channels", "move_members")),
    Feature("tickets", "community", "feature.tickets", "feature.tickets.description", "ticket", ("ticket_panel_channel_id", "ticket_category_id", "ticket_staff_role_id", "ticket_log_channel_id", "ticket_panel_title", "ticket_panel_description"), ("ticket_panel_channel_id", "ticket_category_id", "ticket_staff_role_id"), ("manage_channels", "send_messages")),
    Feature("advanced_polls", "community", "feature.advanced_polls", "feature.advanced_polls.description", "chart-bar", ()),
    Feature("minigames", "community", "feature.minigames", "feature.minigames.description", "gamepad", ()),
    Feature("trust_score", "moderation", "feature.trust_score", "feature.trust_score.description", "shield-check", ("trust_retention_days", "trust_flag_threshold")),
    Feature("social_updates", "social", "feature.social_updates", "feature.social_updates.description", "bell-ring", (), (), ("send_messages",)),
)
FEATURE_BY_ID = {feature.id: feature for feature in FEATURES}

if unknown_icons := {feature.icon for feature in FEATURES} - ICON_IDS:
    raise RuntimeError(f"Unregistered dashboard icons: {', '.join(sorted(unknown_icons))}")

# Server-rendered fallbacks.  They keep the dashboard legible if JavaScript is
# blocked, cached incorrectly, or finishes loading after the first paint.
JAPANESE_COPY = {
    "welcome": ("入退室", "歓迎・退出メッセージを管理します。"),
    "autorole": ("初期ロール", "参加したメンバーへ初期ロールを付与します。"),
    "leveling": ("レベリング", "メッセージでXPを獲得するシステムです。"),
    "audit_log": ("サーバーログ", "サーバー内のイベントをカテゴリ別に記録します。"),
    "moderation": ("モデレーション", "警告と制裁の設定を管理します。"),
    "chat_filter": ("チャットフィルター", "キーワード、正規表現、危険なURLを検出します。"),
    "anti_spam": ("スパム対策", "連投、メンション、重複メッセージを検出します。"),
    "reaction_roles": ("リアクションロール", "ボタンでメンバーがロールを選択できます。"),
    "live_stats": ("ライブ統計チャンネル", "メンバー数などをボイスチャンネル名に自動表示します。"),
    "temporary_voice": ("一時的な音声チャンネル", "トリガー参加時に専用VCを作成し、空になると削除します。"),
    "tickets": ("サポートチケット", "プライベートな会員サポートと議事録を管理します。"),
    "advanced_polls": ("拡張投票", "最大10択、期限、画像付きのボタン投票を作成します。"),
    "minigames": ("ミニゲーム", "コミュニティ向けの軽量ゲームを提供します。"),
    "trust_score": ("信頼度スコア", "違反履歴を管理者だけに可視化します。"),
    "social_updates": ("ソーシャルメディア更新通知", "各サービスの投稿・配信を通知します。"),
}


def get_feature(feature_id: str) -> Feature:
    try:
        return FEATURE_BY_ID[feature_id]
    except KeyError as exc:
        raise ValueError("Unknown feature") from exc


def japanese_copy(feature_id: str) -> tuple[str, str]:
    return JAPANESE_COPY[feature_id]
