import discord
from discord import app_commands
from discord.ext import commands

from guild_settings import GuildSettingsRepository


def _leaf_commands(command: app_commands.Command | app_commands.Group) -> list[app_commands.Command]:
    """Expand command groups because Group itself has no Cog binding."""
    if isinstance(command, app_commands.Group):
        return [leaf for child in command.commands for leaf in _leaf_commands(child)]
    return [command]


class HelpView(discord.ui.View):
    def __init__(self, author_id: int, pages: list[tuple[str, list[app_commands.Command]]], docs_url: str | None = None) -> None:
        super().__init__(timeout=120)
        self.author_id, self.pages, self.index, self.docs_url = author_id, pages, 0, docs_url
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1
        self.page.label = f"{self.index + 1} / {len(self.pages)}"

    def embed(self) -> discord.Embed:
        category, commands_for_page = self.pages[self.index]
        lines = [f"`/{command.qualified_name}`\n{command.description or '説明はありません。'}" for command in commands_for_page]
        embed = discord.Embed(title=f"コマンド一覧 · {category}", description="\n\n".join(lines), color=discord.Color.blue())
        if self.docs_url:
            embed.add_field(name="詳しい使い方", value=f"[公式ドキュメント]({self.docs_url.rstrip('/')}/docs/)", inline=False)
        return embed

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
    help_category = "基本"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)

    async def _available_commands(self, interaction: discord.Interaction, include_all: bool) -> list[tuple[str, list[app_commands.Command]]]:
        categories: dict[str, list[app_commands.Command]] = {}
        for top_level_command in self.bot.tree.get_commands():
            for command in _leaf_commands(top_level_command):
                binding = getattr(command, "binding", None)
                if not include_all:
                    module_id = getattr(binding, "help_module", None)
                    if module_id and interaction.guild and not self.guild_settings.module_enabled(interaction.guild.id, module_id):
                        continue
                    if not getattr(binding, "help_available", True):
                        continue
                    try:
                        if not await command._check_can_run(interaction):
                            continue
                    except app_commands.AppCommandError:
                        continue
                categories.setdefault(getattr(binding, "help_category", "その他" if binding else "基本"), []).append(command)
        for commands_for_page in categories.values():
            commands_for_page.sort(key=lambda command: command.extras.get('help_order', 100))
        return list(categories.items())

    @app_commands.command(name="help", description="利用できるコマンド一覧を表示します。", extras={'help_order': 0})
    async def help_command(self, interaction: discord.Interaction, all: bool = False) -> None:
        pages = await self._available_commands(interaction, include_all=all)
        if not pages:
            await interaction.response.send_message("利用できるコマンドはありません。", ephemeral=True)
            return
        view = HelpView(interaction.user.id, pages, self.bot.settings.dashboard_base_url)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=not all)

    @app_commands.command(description="Botの応答速度を計測します。", extras={'help_order': 1})
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Pong!🏓 {round(self.bot.latency * 1000)}ms")




    @app_commands.command(description="ユーザー情報を表示します。", extras={'help_order': 5})
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

    @app_commands.command(description="サーバー情報を表示します。", extras={'help_order': 6})
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








async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GeneralCog(bot))
