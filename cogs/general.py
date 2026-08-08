import ast
import operator
import random

import discord
from discord import app_commands
from discord.ext import commands


class GeneralCog(commands.Cog):
    """General-purpose slash commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="登録されているコマンド一覧を表示します。")
    async def help_command(self, interaction: discord.Interaction) -> None:
        command_list = [f"/{command.name} - {command.description}" for command in self.bot.tree.get_commands()]
        embed = discord.Embed(title="コマンド一覧", description="\n".join(command_list), color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(description="Botの応答速度を計測します。")
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Pong!🏓 {round(self.bot.latency * 1000)}ms")

    @app_commands.command(description="入力したメッセージをembedで返します。")
    async def echo(self, interaction: discord.Interaction, message: str) -> None:
        await interaction.response.send_message(embed=discord.Embed(title=message))

    @app_commands.command(description="四則演算と累乗を計算します。")
    async def calculate(self, interaction: discord.Interaction, expression: str) -> None:
        try:
            result = _safe_calculate(expression)
            await interaction.response.send_message(f"{expression} = {result}")
        except (SyntaxError, ValueError, ZeroDivisionError):
            await interaction.response.send_message("計算式が無効です。数値と + - * / % ** ( ) のみ使用できます。", ephemeral=True)

    @app_commands.command(description="指定された乱数を振ります。")
    async def roll(self, interaction: discord.Interaction, sides: float = 6) -> None:
        if sides <= 0:
            await interaction.response.send_message("正の数を指定してください。", ephemeral=True)
        elif sides.is_integer():
            await interaction.response.send_message(f"({int(sides)}面)の出目: {random.randint(1, int(sides))}")
        else:
            await interaction.response.send_message(f"範囲: 0～{sides}、結果: {random.random() * sides:.2f}")

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

    @app_commands.command(description="Botを安全に終了します。")
    @app_commands.checks.has_permissions(administrator=True)
    async def shutdown(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Botを終了します。")
        await self.bot.close()


_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


def _safe_calculate(expression: str) -> float | int:
    def evaluate(node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](evaluate(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](evaluate(node.left), evaluate(node.right))
        raise ValueError("Unsupported expression")
    return evaluate(ast.parse(expression, mode="eval").body)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GeneralCog(bot))
