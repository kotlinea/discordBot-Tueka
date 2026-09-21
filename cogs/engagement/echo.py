import discord
from discord import app_commands
from discord.ext import commands
import json
from datetime import datetime, timezone
from urllib.parse import urlparse
MAX_EMBED_TOTAL_LENGTH = 6_000


class EchoCog(commands.Cog):
    help_category = "基本"

    @app_commands.command(description="自由にEmbedを組み立てて送信します。", extras={'help_order': 2})
    async def echo(
        self,
        interaction: discord.Interaction,
        title: str | None = None,
        description: str | None = None,
        color: str | None = None,
        url: str | None = None,
        author_name: str | None = None,
        author_url: str | None = None,
        author_icon_url: str | None = None,
        footer_text: str | None = None,
        footer_icon_url: str | None = None,
        thumbnail_url: str | None = None,
        image_url: str | None = None,
        fields_json: str | None = None,
        timestamp: bool = False,
        ephemeral: bool = False,
    ) -> None:
        try:
            embed = _build_embed(title, description, color, url, author_name, author_url, author_icon_url, footer_text, footer_icon_url, thumbnail_url, image_url, fields_json, timestamp)
        except ValueError as exc:
            await interaction.response.send_message(f"Embedを作成できません: {exc}", ephemeral=True)
            return
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral, allowed_mentions=discord.AllowedMentions.none())


def _valid_url(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if urlparse(value).scheme not in {"http", "https"}:
        raise ValueError(f"{field} は http:// または https:// URLにしてください")
    return value


def _build_embed(title, description, color, url, author_name, author_url, author_icon_url, footer_text, footer_icon_url, thumbnail_url, image_url, fields_json, timestamp) -> discord.Embed:
    if title and len(title) > 256:
        raise ValueError("title は256文字以内です")
    if description and len(description) > 4096:
        raise ValueError("description は4096文字以内です")
    if author_name and len(author_name) > 256:
        raise ValueError("author_name は256文字以内です")
    if footer_text and len(footer_text) > 2048:
        raise ValueError("footer_text は2048文字以内です")
    colour = discord.Color.default()
    if color:
        try:
            colour = discord.Color(int(color.removeprefix("#"), 16))
        except ValueError as exc:
            raise ValueError("color は #5865F2 のような6桁の16進数です") from exc
    embed = discord.Embed(title=title, description=description, color=colour, url=_valid_url(url, "url"), timestamp=datetime.now(timezone.utc) if timestamp else None)
    if author_name:
        embed.set_author(name=author_name, url=_valid_url(author_url, "author_url"), icon_url=_valid_url(author_icon_url, "author_icon_url"))
    if footer_text:
        embed.set_footer(text=footer_text, icon_url=_valid_url(footer_icon_url, "footer_icon_url"))
    if thumbnail_url:
        embed.set_thumbnail(url=_valid_url(thumbnail_url, "thumbnail_url"))
    if image_url:
        embed.set_image(url=_valid_url(image_url, "image_url"))
    if fields_json:
        try:
            fields = json.loads(fields_json)
        except json.JSONDecodeError as exc:
            raise ValueError('fields_json は [{"name":"項目","value":"内容","inline":true}] のJSON配列です') from exc
        if not isinstance(fields, list) or len(fields) > 25:
            raise ValueError("fields_json は最大25件の配列です")
        for field in fields:
            if not isinstance(field, dict) or not isinstance(field.get("name"), str) or not isinstance(field.get("value"), str):
                raise ValueError("各fieldには文字列の name と value が必要です")
            if len(field["name"]) > 256 or len(field["value"]) > 1024:
                raise ValueError("field nameは256文字、valueは1024文字以内です")
            embed.add_field(name=field["name"], value=field["value"], inline=bool(field.get("inline", False)))
    if len(embed) > MAX_EMBED_TOTAL_LENGTH:
        raise ValueError(f"Embed全体は {MAX_EMBED_TOTAL_LENGTH:,} 文字以内です")
    return embed


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EchoCog())
