"""Shared defaults for user-editable message and channel-name templates."""

WELCOME_CONTENT_DEFAULT = "{user} さん、{server}へようこそ！"
LEAVE_CONTENT_DEFAULT = "{displayname} さんが {server} から退出しました。"
STATS_TEMPLATE_DEFAULT = "メンバー: {members} | Bot: {bots} | ロール: {roles}"
TEMP_VOICE_NAME_DEFAULT = "{member} のチャンネル"


TEMPLATE_DEFAULTS = {
    "welcome_content": WELCOME_CONTENT_DEFAULT,
    "leave_content": LEAVE_CONTENT_DEFAULT,
    "stats_template": STATS_TEMPLATE_DEFAULT,
    "temp_voice_name": TEMP_VOICE_NAME_DEFAULT,
}
