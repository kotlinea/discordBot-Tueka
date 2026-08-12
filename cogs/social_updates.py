"""Deliver normalized social-provider events stored by polling and webhooks."""
import re

import discord
from discord.ext import commands, tasks

from storage import GuildStorage


MODULE_FOR_PROVIDER = {"youtube": "youtube_updates", "twitch": "twitch_updates", "tiktok": "tiktok_updates", "x": "x_updates", "instagram": "instagram_updates"}


class SocialUpdatesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.storage = GuildStorage(bot.settings.database_path)
        self.deliver_events.start()

    def cog_unload(self) -> None:
        self.deliver_events.cancel()

    @staticmethod
    def render_template(template: str, payload: dict) -> str:
        values = {key: str(payload.get(key, "")) for key in ("account", "title", "url", "platform", "type")}
        return re.sub(r"\{(account|title|url|platform|type)\}", lambda match: values[match.group(1)], template)[:1900]

    async def _deliver(self, event: dict) -> bool:
        payload = event["payload"]
        event_type = str(payload.get("type", ""))
        matching_type = "live" if event_type == "live_end" else event_type
        retry_needed = False
        for subscription in self.storage.matching_social_subscriptions(event["provider"], event["account_id"], matching_type):
            if not self.storage.module_enabled(subscription["guild_id"], MODULE_FOR_PROVIDER[event["provider"]]):
                continue
            guild = self.bot.get_guild(subscription["guild_id"])
            channel = guild.get_channel(subscription["channel_id"]) if guild else None
            if not isinstance(channel, discord.TextChannel):
                continue
            if event_type == "live_end" and event["provider"] == "twitch":
                saved = self.storage.social_live_message(subscription["id"], "twitch", event["account_id"])
                if saved:
                    saved_channel = guild.get_channel(saved["discord_channel_id"])
                    if isinstance(saved_channel, discord.TextChannel):
                        try:
                            message = await saved_channel.fetch_message(saved["discord_message_id"])
                            await message.edit(embed=discord.Embed(title="配信終了", description=self.render_template(subscription["template"] or "{account} の配信は終了しました。", {**payload, "type": "配信終了"}), color=discord.Color.dark_grey()))
                        except discord.HTTPException:
                            retry_needed = True
                    self.storage.clear_social_live_message(subscription["id"], "twitch", event["account_id"])
                continue
            if not self.storage.record_social_delivery(subscription["id"], event["event_key"], channel.id, None, "pending"):
                continue
            text = self.render_template(subscription["template"] or "{account} が {type} を公開しました: {url}", payload)
            role = guild.get_role(subscription["role_id"]) if subscription["role_id"] else None
            content = f"{role.mention}\n{text}" if role else text
            embed = discord.Embed(title=payload.get("title") or f"{payload.get('account', subscription['account_name'])} の更新", url=payload.get("url") or None, color=discord.Color.blurple())
            embed.set_footer(text=payload.get("platform", event["provider"]))
            try:
                message = await channel.send(content=content, embed=embed, allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=[role] if role else False))
                self.storage.update_social_delivery(subscription["id"], event["event_key"], message.id)
                if event["provider"] == "twitch" and event_type == "live":
                    self.storage.set_social_live_message(subscription["id"], "twitch", event["account_id"], channel.id, message.id)
            except discord.HTTPException:
                retry_needed = True
        return not retry_needed

    @tasks.loop(seconds=5)
    async def deliver_events(self) -> None:
        for event in self.storage.pending_social_events():
            if await self._deliver(event):
                self.storage.mark_social_event_processed(event["id"])

    @deliver_events.before_loop
    async def before_deliver_events(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SocialUpdatesCog(bot))
