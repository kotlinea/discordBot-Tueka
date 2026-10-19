import discord
from io import BytesIO
from google import genai
from discord import app_commands
from discord.ext import commands


class AICog(commands.Cog):
    help_category = 'AI'
    help_module = None

    @property
    def help_available(self):
        return bool(self.client)

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        key = bot.settings.gemini_api_key
        self.client = genai.Client(api_key=key) if key else None

    @app_commands.command(name="gemini", description="Gemini APIから質問します。")
    async def gemini(self, interaction: discord.Interaction, message: str) -> None:
        if not self.client:
            await interaction.response.send_message("Gemini APIは未設定です。", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            response = await self.client.aio.models.generate_content(
                model=self.bot.settings.gemini_model,
                contents=message,
            )
            answer = response.text or "適切な応答を生成できませんでした。"
            if len(answer) > 2000:
                await interaction.followup.send(
                    "回答が長いため、テキストファイルで送信します。",
                    file=discord.File(BytesIO(answer.encode('utf-8')), filename='gemini-response.txt'),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                await interaction.followup.send(answer, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            await interaction.followup.send("Gemini の応答生成に失敗しました。", allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AICog(bot))
