import ast
import math
import operator
import random

import discord
from discord import app_commands
from discord.ext import commands

from storage import GuildStorage


MAX_ECHO_LENGTH = 4_000
MAX_EXPRESSION_LENGTH = 200
MAX_EXPRESSION_NODES = 50
MAX_POWER_EXPONENT = 12
MAX_ROLL_SIDES = 1_000_000
_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
_CATEGORY_NAMES = {"GeneralCog": "基本", "AICog": "AI", "LevelingCog": "レベリング", "ModerationCog": "モデレーション", "AuditLogCog": "管理ログ", "WelcomeCog": "入退室"}
_COG_MODULES = {"AICog": None, "LevelingCog": "leveling", "ModerationCog": "moderation", "AuditLogCog": "audit_log", "WelcomeCog": "welcome"}


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
        for command in self.bot.tree.get_commands():
            cog_name = type(command.binding).__name__ if command.binding else "GeneralCog"
            if not include_all:
                module_id = _COG_MODULES.get(cog_name)
                if module_id and interaction.guild and not self.storage.module_enabled(interaction.guild.id, module_id):
                    continue
                if cog_name == "AICog" and not getattr(command.binding, "client", None):
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

    @app_commands.command(description="入力したメッセージをembedで返します。")
    async def echo(self, interaction: discord.Interaction, message: str) -> None:
        if len(message) > MAX_ECHO_LENGTH:
            await interaction.response.send_message(f"メッセージは {MAX_ECHO_LENGTH:,} 文字以内で入力してください。", ephemeral=True)
            return
        await interaction.response.send_message(embed=discord.Embed(title="Echo", description=message), allowed_mentions=discord.AllowedMentions.none())

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
        embed = discord.Embed(title="ユーザー情報", color=discord.Color.blue())
        embed.add_field(name="ユーザー名", value=str(member))
        embed.add_field(name="ID", value=str(member.id))
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GeneralCog(bot))
