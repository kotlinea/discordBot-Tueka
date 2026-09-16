"""Discord presentation for suggestion messages and persistent controls."""
from typing import Any
import discord
from .models import normalize_settings

STATUS_LABELS = {
    "pending": "審査待ち",
    "reviewing": "審査中",
    "approved": "承認済み",
    "rejected": "却下",
    "delivery_failed": "投稿失敗",
}
STATUS_COLORS = {
    "pending": 0x64748B,
    "reviewing": 0xD97706,
    "approved": 0x15803D,
    "rejected": 0xB91C1C,
    "delivery_failed": 0xB91C1C,
}


def suggestion_embed(item: dict[str, Any], settings: dict[str, Any]) -> discord.Embed:
    status = str(item["status"])
    embed = discord.Embed(
        title=f"提案 #{item['id']} · {STATUS_LABELS.get(status, status)}",
        color=STATUS_COLORS.get(status, STATUS_COLORS["pending"]),
    )
    fields_by_key = {field["key"]: field for field in normalize_settings(settings)["form_fields"]}
    for key, value in item["answers"].items():
        if not value:
            continue
        label = fields_by_key.get(key, {}).get("label", key)
        embed.add_field(name=str(label)[:256], value=str(value)[:1024], inline=False)
    if settings.get("show_author", True):
        embed.set_author(name=f"投稿者: {item['author_id']}")
    reviewer = f" · 担当 <@{item['reviewer_id']}>" if item.get("reviewer_id") else ""
    embed.set_footer(text=f"賛成 {item.get('upvotes', 0)} · 反対 {item.get('downvotes', 0)}{reviewer} · Tueka suggestion:{item['id']}:{item['created_at']}")
    return embed


def suggestion_view(item: dict[str, Any], settings: dict[str, Any]) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    closed = item["status"] in {"approved", "rejected", "delivery_failed"}
    if settings.get("allow_voting", True):
        view.add_item(discord.ui.Button(
            label=f"賛成 {item.get('upvotes', 0)}", emoji="👍", style=discord.ButtonStyle.secondary,
            custom_id=f"tueka-suggestion:vote:{item['id']}:up", disabled=closed,
        ))
        view.add_item(discord.ui.Button(
            label=f"反対 {item.get('downvotes', 0)}", emoji="👎", style=discord.ButtonStyle.secondary,
            custom_id=f"tueka-suggestion:vote:{item['id']}:down", disabled=closed,
        ))
    view.add_item(discord.ui.Button(
        label="審査中", style=discord.ButtonStyle.secondary,
        custom_id=f"tueka-suggestion:review:{item['id']}:reviewing", disabled=closed or item["status"] == "reviewing",
    ))
    view.add_item(discord.ui.Button(
        label="承認", style=discord.ButtonStyle.success,
        custom_id=f"tueka-suggestion:review:{item['id']}:approved", disabled=closed,
    ))
    view.add_item(discord.ui.Button(
        label="却下", style=discord.ButtonStyle.danger,
        custom_id=f"tueka-suggestion:review:{item['id']}:rejected", disabled=closed,
    ))
    return view
