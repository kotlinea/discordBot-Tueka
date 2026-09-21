import discord
from discord import app_commands
from discord.ext import commands
import ast
import math
import operator
MAX_EXPRESSION_LENGTH = 200
MAX_EXPRESSION_NODES = 50
MAX_POWER_EXPONENT = 12
_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


class CalculateCog(commands.Cog):
    help_category = "基本"

    @app_commands.command(description="四則演算と累乗を計算します。", extras={'help_order': 3})
    async def calculate(self, interaction: discord.Interaction, expression: str) -> None:
        try:
            await interaction.response.send_message(f"{expression} = {_safe_calculate(expression)}")
        except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, RecursionError):
            await interaction.response.send_message("計算式が無効か、計算上限を超えています。数値と + - * / % ** ( ) のみ使用できます。", ephemeral=True)


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
    await bot.add_cog(CalculateCog())
