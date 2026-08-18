"""Deliver normalized social-provider events stored by polling and webhooks."""
import os
import re
import socket

import discord
from discord.ext import commands, tasks

from storage import GuildStorage
from social_models import default_templates, render_template


MODULE_FOR_PROVIDER = {"youtube": "youtube_updates", "twitch": "twitch_updates", "tiktok": "tiktok_updates", "x": "x_updates", "instagram": "instagram_updates"}


class SocialUpdatesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.storage = GuildStorage(bot.settings.database_path)
        self.owner = f"discord:{socket.gethostname()}:{os.getpid()}"
        self.deliver_events.start()

    def cog_unload(self) -> None:
        self.deliver_events.cancel()

    @staticmethod
    def render_template(template: str, payload: dict) -> str:
        values = {**payload, "event": payload.get("event") or payload.get("type", ""), "type": payload.get("type", "")}
        rendered = render_template(template, values, limit=1900)
        return re.sub(r"\{type\}", str(values["type"]), rendered)[:1900]

    @staticmethod
    def _notification(subscription: dict, event_type: str, payload: dict) -> tuple[str, discord.Embed]:
        templates = subscription.get("templates") or {}
        template = templates.get(event_type) or default_templates(subscription["provider"], [event_type])[event_type]
        content = render_template(str(template.get("content", "")), payload, limit=1900)
        title = render_template(str(template.get("title", "")), payload, limit=256)
        description = render_template(str(template.get("description", "")), payload, limit=4096)
        url = render_template(str(template.get("url", "")), payload, limit=500)
        try:
            color = int(str(template.get("color", "#5865F2")).lstrip("#"), 16)
        except ValueError:
            color = 0x5865F2
        embed = discord.Embed(title=title or None, description=description or None, url=url or None, color=color)
        thumbnail = render_template(str(template.get("thumbnail_url", "")), payload, limit=500)
        image = render_template(str(template.get("image_url", "")), payload, limit=500)
        footer = render_template(str(template.get("footer", "")), payload, limit=2048)
        if thumbnail.startswith(("http://", "https://")):
            embed.set_thumbnail(url=thumbnail)
        if image.startswith(("http://", "https://")):
            embed.set_image(url=image)
        if footer:
            embed.set_footer(text=footer)
        return content, embed

    async def _deliver(self, event: dict) -> bool:
        payload = event["payload"]
        event_type = str(event.get("event_type") or payload.get("event") or payload.get("type", ""))
        matching_type = "live" if event_type in {"live_start", "live_end"} and not self.storage.matching_social_subscriptions(event["provider"], event["account_id"], event_type) else event_type
        retry_needed = False
        for subscription in self.storage.matching_social_subscriptions(event["provider"], event["account_id"], matching_type):
            if not self.storage.module_enabled(subscription["guild_id"], MODULE_FOR_PROVIDER[event["provider"]]):
                continue
            guild = self.bot.get_guild(subscription["guild_id"])
            channel_id = int(subscription.get("event_channels", {}).get(event_type) or subscription["channel_id"])
            channel = guild.get_channel(channel_id) if guild else None
            if not isinstance(channel, discord.TextChannel):
                if self.storage.record_social_delivery(subscription["id"], event["event_key"], channel_id, None, "pending"):
                    self.storage.fail_social_delivery(subscription["id"], event["event_key"], "Discord channel is unavailable", retry=False)
                continue
            if event_type == "live_end":
                saved = self.storage.social_live_message(subscription["id"], event["provider"], event["account_id"])
                if saved:
                    saved_channel = guild.get_channel(saved["discord_channel_id"])
                    if isinstance(saved_channel, discord.TextChannel):
                        try:
                            message = await saved_channel.fetch_message(saved["discord_message_id"])
                            _, ended_embed = self._notification(subscription, event_type, payload)
                            await message.edit(embed=ended_embed, allowed_mentions=discord.AllowedMentions.none())
                            self.storage.record_social_delivery(subscription["id"], event["event_key"], saved_channel.id, message.id, "sent")
                            self.storage.clear_social_live_message(subscription["id"], event["provider"], event["account_id"])
                            continue
                        except discord.NotFound:
                            pass
                        except discord.HTTPException as exc:
                            retry_needed = True
                            self.storage.fail_social_delivery(subscription["id"], event["event_key"], str(exc), retry=True)
                            continue
            if not self.storage.record_social_delivery(subscription["id"], event["event_key"], channel.id, None, "pending"):
                continue
            text, embed = self._notification(subscription, event_type, payload)
            role = guild.get_role(subscription["role_id"]) if subscription["role_id"] else None
            content = f"{role.mention}\n{text}" if role else text
            try:
                message = await channel.send(content=content or None, embed=embed, allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=[role] if role else False))
                self.storage.update_social_delivery(subscription["id"], event["event_key"], message.id)
                if event_type in {"live", "live_start"}:
                    self.storage.set_social_live_message(subscription["id"], event["provider"], event["account_id"], channel.id, message.id)
            except discord.HTTPException as exc:
                retry = not isinstance(exc, discord.Forbidden) and getattr(exc, "status", 500) in {429, 500, 502, 503, 504}
                self.storage.fail_social_delivery(subscription["id"], event["event_key"], str(exc), retry=retry)
                retry_needed = retry_needed or retry
        return not retry_needed

    @tasks.loop(seconds=5)
    async def deliver_events(self) -> None:
        for event in self.storage.claim_social_events(self.owner, limit=10, lease_seconds=120):
            if await self._deliver(event):
                self.storage.mark_social_event_processed(event["id"])
            else:
                self.storage.retry_social_event(event["id"], "One or more Discord deliveries need retry")

    @deliver_events.before_loop
    async def before_deliver_events(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SocialUpdatesCog(bot))
