import ast
import json
import math
import operator
import random
from datetime import datetime, timezone
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from storage import GuildStorage


MAX_EMBED_TOTAL_LENGTH = 6_000
MAX_EXPRESSION_LENGTH = 200
MAX_EXPRESSION_NODES = 50
MAX_POWER_EXPONENT = 12
MAX_ROLL_SIDES = 1_000_000
_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
_CATEGORY_NAMES = {
    "GeneralCog": "基本",
    "AICog": "AI",
    "LevelingCog": "レベリング",
    "ModerationCog": "モデレーション",
    "ModerationCommandsCog": "モデレーション",
    "TicketsCog": "チケット",
    "AuditLogCog": "サーバーログ",
    "WelcomeCog": "入退室",
}
_COG_MODULES = {
    "AICog": None,
    "LevelingCog": "leveling",
    "ModerationCog": "moderation",
    "ModerationCommandsCog": "moderation",
    "TicketsCog": "tickets",
    "AuditLogCog": "audit_log",
    "WelcomeCog": "welcome",
}


def _leaf_commands(command: app_commands.Command | app_commands.Group) -> list[app_commands.Command]:
    """Expand command groups because Group itself has no Cog binding."""
    if isinstance(command, app_commands.Group):
        return [leaf for child in command.commands for leaf in _leaf_commands(child)]
    return [command]


class HelpView(discord.ui.View):
    def __init__(self, author_id: int, pages: list[tuple[str, list[app_commands.Command]]]) -> None:
        super().__init__(timeout=120)
        self.author_id, self.pages, self.index = author_id, pages, 0
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1
        self.page.label = f"{self.index + 1} / {len(self.pages)}"

    def embed(self) -> discord.Embed:
        category, commands_for_page = self.pages[self.index]
        lines = [f"`/{command.qualified_name}`\n{command.description or '説明はありません。'}" for command in commands_for_page]
        return discord.Embed(title=f"コマンド一覧 · {category}", description="\n\n".join(lines), color=discord.Color.blue())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("このヘルプは実行者のみ操作できます。", ephemeral=True)
        return False

    @discord.ui.button(emoji="◀", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.index -= 1
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="1 / 1", disabled=True, style=discord.ButtonStyle.secondary)
    async def page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass

    @discord.ui.button(emoji="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.index += 1
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)


class GeneralCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.storage = GuildStorage(bot.settings.database_path)

    async def _available_commands(self, interaction: discord.Interaction, include_all: bool) -> list[tuple[str, list[app_commands.Command]]]:
        categories: dict[str, list[app_commands.Command]] = {}
        for top_level_command in self.bot.tree.get_commands():
            for command in _leaf_commands(top_level_command):
                binding = getattr(command, "binding", None)
                cog_name = type(binding).__name__ if binding else "GeneralCog"
                if not include_all:
                    module_id = _COG_MODULES.get(cog_name)
                    if module_id and interaction.guild and not self.storage.module_enabled(interaction.guild.id, module_id):
                        continue
                    if cog_name == "AICog" and not getattr(binding, "client", None):
                        continue
                    try:
                        if not await command._check_can_run(interaction):
                            continue
                    except app_commands.AppCommandError:
                        continue
                categories.setdefault(_CATEGORY_NAMES.get(cog_name, "その他"), []).append(command)
        return list(categories.items())

    @app_commands.command(name="help", description="利用できるコマンド一覧を表示します。")
    async def help_command(self, interaction: discord.Interaction, all: bool = False) -> None:
        pages = await self._available_commands(interaction, include_all=all)
        if not pages:
            await interaction.response.send_message("利用できるコマンドはありません。", ephemeral=True)
            return
        view = HelpView(interaction.user.id, pages)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=not all)

    @app_commands.command(description="Botの応答速度を計測します。")
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Pong!🏓 {round(self.bot.latency * 1000)}ms")

    @app_commands.command(description="自由にEmbedを組み立てて送信します。")
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

    @app_commands.command(description="四則演算と累乗を計算します。")
    async def calculate(self, interaction: discord.Interaction, expression: str) -> None:
        try:
            await interaction.response.send_message(f"{expression} = {_safe_calculate(expression)}")
        except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, RecursionError):
            await interaction.response.send_message("計算式が無効か、計算上限を超えています。数値と + - * / % ** ( ) のみ使用できます。", ephemeral=True)

    @app_commands.command(description="指定された乱数を振ります。")
    async def roll(self, interaction: discord.Interaction, sides: float = 6.0) -> None:
        if not math.isfinite(sides) or sides <= 0 or sides > MAX_ROLL_SIDES:
            await interaction.response.send_message(f"1 から {MAX_ROLL_SIDES:,} までの有限な正の数を指定してください。", ephemeral=True)
        elif sides.is_integer():
            await interaction.response.send_message(f"({int(sides)}面)の出目: {random.randint(1, int(sides))}")
        else:
            await interaction.response.send_message(f"範囲: 0～{sides}、結果: {random.uniform(0, sides):.2f}")

    @app_commands.command(description="ユーザー情報を表示します。")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        member = member or interaction.user
        embed = discord.Embed(title=f"ユーザー情報 · {member}", color=getattr(member, "color", discord.Color.blue()))
        embed.add_field(name="表示名", value=getattr(member, "display_name", member.name), inline=True)
        embed.add_field(name="ユーザー名", value=f"{member.name} (@{member.name})", inline=True)
        embed.add_field(name="ユーザーID", value=str(member.id), inline=True)
        if getattr(member, "global_name", None):
            embed.add_field(name="グローバル表示名", value=member.global_name, inline=True)
        embed.add_field(name="アカウント作成", value=discord.utils.format_dt(member.created_at, "F"), inline=False)
        if isinstance(member, discord.Member):
            if member.joined_at:
                embed.add_field(name="サーバー参加", value=discord.utils.format_dt(member.joined_at, "F"), inline=False)
            roles = [role.mention for role in member.roles if not role.is_default()]
            embed.add_field(name=f"ロール ({len(roles)})", value=" ".join(roles)[-1024:] if roles else "なし", inline=False)
            embed.add_field(name="最上位ロール", value=member.top_role.mention if not member.top_role.is_default() else "なし", inline=True)
            embed.add_field(name="ステータス", value=str(member.status), inline=True)
            if member.voice and member.voice.channel:
                embed.add_field(name="ボイスチャンネル", value=member.voice.channel.mention, inline=True)
            if member.premium_since:
                embed.add_field(name="サーバーブースト開始", value=discord.utils.format_dt(member.premium_since, "F"), inline=False)
            if member.timed_out_until:
                embed.add_field(name="タイムアウト期限", value=discord.utils.format_dt(member.timed_out_until, "F"), inline=False)
        flags = [flag.name.replace("_", " ") for flag in member.public_flags.all()]
        if flags:
            embed.add_field(name="公開フラグ", value=", ".join(flags), inline=False)
        embed.add_field(name="アカウント種別", value="Bot" if member.bot else "ユーザー", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(description="サーバー情報を表示します。")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None
        embed = discord.Embed(title="サーバー情報", color=discord.Color.green())
        embed.add_field(name="サーバー名", value=guild.name)
        embed.add_field(name="サーバーID", value=str(guild.id))
        embed.add_field(name="メンバー数", value=str(guild.member_count))
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await interaction.response.send_message(embed=embed)


def _safe_calculate(expression: str) -> float | int:
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ValueError("Expression too long")
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > MAX_EXPRESSION_NODES:
        raise ValueError("Expression too complex")

    def evaluate(node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            if not math.isfinite(float(node.value)) or abs(node.value) > 1_000_000_000_000:
                raise ValueError("Number out of range")
            return node.value
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
            result = _OPERATORS[type(node.op)](evaluate(node.operand))
        elif isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Pow) and (not float(right).is_integer() or abs(right) > MAX_POWER_EXPONENT):
                raise ValueError("Power out of range")
            result = _OPERATORS[type(node.op)](left, right)
        else:
            raise ValueError("Unsupported expression")
        if isinstance(result, float) and not math.isfinite(result):
            raise ValueError("Result out of range")
        if isinstance(result, int) and result.bit_length() > 256:
            raise ValueError("Result out of range")
        return result

    return evaluate(tree.body)


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
    await bot.add_cog(GeneralCog(bot))
