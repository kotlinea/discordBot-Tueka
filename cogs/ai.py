import asyncio

import discord
import google.generativeai as genai
from discord import app_commands
from discord.ext import commands


class AICog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        key = bot.settings.gemini_api_key
        self.model = None
        if key:
            genai.configure(api_key=key)
            self.model = genai.GenerativeModel("models/gemini-1.5-pro-001")

    @app_commands.command(name="gemini", description="Gemini APIから質問します。")
    async def gemini(self, interaction: discord.Interaction, message: str) -> None:
        if not self.model:
            await interaction.response.send_message("Gemini APIは未設定です。", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            response = await asyncio.to_thread(self.model.generate_content, message)
            await interaction.followup.send(response.text or "適切な応答を生成できませんでした。")
        except Exception:
            await interaction.followup.send("Gemini の応答生成に失敗しました。")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AICog(bot))
