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
    docs_path: str
    fields: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    required_bot_permissions: tuple[str, ...] = ()
    parent: str | None = None


FEATURES = (
    Feature("welcome", "community", "feature.welcome", "feature.welcome.description", "door-open", "/docs/features/welcome", ("welcome_enabled", "welcome_channel_id", "welcome_format", "welcome_content", "leave_enabled", "leave_channel_id", "leave_format", "leave_content"), (), ("send_messages",)),
    Feature("autorole", "community", "field.default_role", "settings.enable.description", "badge-check", "/docs/features/autorole", ("default_role_id",), ("default_role_id",), ("manage_roles",)),
    Feature("leveling", "community", "feature.leveling", "feature.leveling.description", "trophy", "/docs/features/leveling", ("text_notification_channel_id", "text_role_rewards", "voice_enabled", "voice_notification_channel_id", "voice_role_rewards", "voice_xp_per_minute", "voice_allow_solo", "voice_allow_muted"), ("text_notification_channel_id",), ("send_messages",)),
    Feature("moderation", "moderation", "feature.moderation", "feature.moderation.description", "shield-alert", "/docs/features/moderation", ("default_log_channel_id", "immune_role_ids", "immune_user_ids", "immune_channel_ids", "evidence_excluded_channel_ids", "evidence_retention_days", "exclude_bots", "exclude_webhooks"), (), ("manage_messages", "send_messages")),
    Feature("automod", "moderation", "feature.automod", "feature.automod.description", "shield-ban", "/docs/features/automod", ("log_channel_id", "immune_role_ids", "immune_user_ids", "immune_channel_ids"), (), ("manage_messages", "send_messages"), "moderation"),
    Feature("anti_spam", "moderation", "feature.anti_spam", "feature.anti_spam.description", "shield-ban", "/docs/features/anti-spam", ("log_channel_id", "immune_role_ids", "immune_user_ids", "immune_channel_ids"), (), ("manage_messages", "moderate_members"), "moderation"),
    Feature("anti_raid", "moderation", "feature.anti_raid", "feature.anti_raid.description", "shield-alert", "/docs/features/anti-raid", ("log_channel_id", "notify_channel_id", "default_lockdown_minutes", "immune_role_ids", "immune_user_ids", "immune_channel_ids"), (), ("manage_channels", "moderate_members", "kick_members", "ban_members"), "moderation"),
    Feature("infractions", "moderation", "feature.infractions", "feature.infractions.description", "shield-check", "/docs/features/infractions", ("point_thresholds", "log_channel_id"), (), ("moderate_members", "kick_members", "ban_members"), "moderation"),
    Feature("moderation_actions", "moderation", "feature.moderation_actions", "feature.moderation_actions.description", "hand", "/docs/features/moderation-actions", (), (), ("manage_messages", "manage_channels", "moderate_members", "kick_members", "ban_members"), "moderation"),
    Feature("moderation_logs", "moderation", "feature.moderation_logs", "feature.moderation_logs.description", "scroll-text", "/docs/features/moderation-logs", ("log_channel_id",), (), ("send_messages", "view_audit_log"), "moderation"),
    Feature("audit_log", "moderation", "feature.audit_log", "feature.audit_log.description", "scroll-text", "/docs/features/audit-log", ("management_channel_id", "log_message", "log_voice", "log_channel", "log_member", "log_role", "log_server"), (), ("send_messages",), "moderation"),
    Feature("reaction_roles", "community", "feature.reaction_roles", "feature.reaction_roles.description", "hand", "/docs/features/reaction-roles", (), (), ("manage_roles", "send_messages", "add_reactions", "read_message_history", "manage_messages")),
    Feature("live_stats", "community", "feature.live_stats", "feature.live_stats.description", "chart-line", "/docs/features/live-stats", ("stats_channel_id", "stats_template"), ("stats_channel_id",), ("manage_channels",)),
    Feature("temporary_voice", "community", "feature.temporary_voice", "feature.temporary_voice.description", "microphone", "/docs/features/temporary-voice", ("temp_voice_trigger_id", "temp_voice_category_id", "temp_voice_name"), ("temp_voice_trigger_id",), ("manage_channels", "move_members")),
    Feature("tickets", "community", "feature.tickets", "feature.tickets.description", "ticket", "/docs/features/tickets", (), (), ("manage_channels", "manage_threads", "create_private_threads", "send_messages_in_threads", "send_messages", "read_message_history", "manage_messages", "embed_links", "attach_files")),
    Feature("advanced_polls", "engagement", "feature.advanced_polls", "feature.advanced_polls.description", "chart-bar", "/docs/features/polls", ()),
    Feature("suggestions", "engagement", "feature.suggestions", "feature.suggestions.description", "lightbulb", "/docs/features/suggestions", ("channel_id", "log_channel_id", "review_role_ids", "allow_voting", "show_author", "form_title", "form_fields"), ("channel_id",), ("send_messages", "embed_links")),
    Feature("minigames", "engagement", "feature.minigames", "feature.minigames.description", "gamepad", "/docs/features/minigames", ()),
    Feature("trust_score", "moderation", "feature.trust_score", "feature.trust_score.description", "shield-check", "/docs/features/trust-score", ("trust_retention_days", "trust_flag_threshold"), (), (), "moderation"),
    Feature("youtube_updates", "social", "feature.youtube_updates", "feature.youtube_updates.description", "youtube", "/docs/social/youtube", (), (), ("send_messages",)),
    Feature("twitch_updates", "social", "feature.twitch_updates", "feature.twitch_updates.description", "twitch", "/docs/social/twitch", (), (), ("send_messages",)),
    Feature("tiktok_updates", "social", "feature.tiktok_updates", "feature.tiktok_updates.description", "tiktok", "/docs/social/tiktok", (), (), ("send_messages",)),
    Feature("x_updates", "social", "feature.x_updates", "feature.x_updates.description", "x-twitter", "/docs/social/x", (), (), ("send_messages",)),
    Feature("instagram_updates", "social", "feature.instagram_updates", "feature.instagram_updates.description", "instagram", "/docs/social/instagram", (), (), ("send_messages",)),
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
    "automod": ("AutoMod", "柔軟なルール、例外、複数アクションでサーバーを保護します。"),
    "anti_spam": ("Anti-Spam", "連投、重複、メンション、リアクションスパムを検知します。"),
    "anti_raid": ("Anti-Raid", "参加・退出の急増を検知し、制裁やLockdownを実行します。"),
    "infractions": ("Warnings / Infractions", "警告ポイント、違反履歴、段階的制裁を管理します。"),
    "moderation_actions": ("Moderation Actions", "手動処置とLockdownの状態を管理します。"),
    "moderation_logs": ("Moderation Logs", "検知、制裁、管理操作を一元的に記録します。"),
    "reaction_roles": ("リアクションロール", "EmojiへのリアクションでRoleを自己付与・解除できます。"),
    "live_stats": ("ライブ統計チャンネル", "メンバー数などをボイスチャンネル名に自動表示します。"),
    "temporary_voice": ("一時的な音声チャンネル", "トリガー参加時に専用VCを作成し、空になると削除します。"),
    "tickets": ("サポートチケット", "プライベートな会員サポートと議事録を管理します。"),
    "advanced_polls": ("拡張投票", "最大10択、期限、画像付きのボタン投票を作成します。"),
    "suggestions": ("Suggestions", "メンバーの提案をフォームで受け付け、投票と審査を管理します。"),
    "minigames": ("ミニゲーム", "コミュニティ向けの軽量ゲームを提供します。"),
    "trust_score": ("信頼度スコア", "違反履歴を管理者だけに可視化します。"),
    "youtube_updates": ("YouTube通知", "新規動画・ライブ開始を通知します。"),
    "twitch_updates": ("Twitch通知", "配信開始・終了を通知します。"),
    "tiktok_updates": ("TikTok通知", "本人連携済みアカウントの新規投稿を通知します。"),
    "x_updates": ("X通知", "新規ポストを通知します。"),
    "instagram_updates": ("Instagram通知", "本人連携済みProfessionalアカウントの投稿・Reelsを通知します。"),
}


def get_feature(feature_id: str) -> Feature:
    try:
        return FEATURE_BY_ID[feature_id]
    except KeyError as exc:
        raise ValueError("Unknown feature") from exc


def japanese_copy(feature_id: str) -> tuple[str, str]:
    return JAPANESE_COPY[feature_id]
