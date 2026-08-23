"""Ticket V2 Discord workflow."""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import sqlite3
from datetime import datetime, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ticketing import TicketRepository, TicketService, TicketValidationError, TranscriptStorage


LOGGER = logging.getLogger(__name__)


class TicketFormModal(discord.ui.Modal):
    def __init__(self, cog: "TicketsCog", panel: dict[str, Any], form: dict[str, Any]) -> None:
        super().__init__(title=str(form["title"])[:45], timeout=900, custom_id=f"tueka-ticket:form:{panel['id']}")
        self.cog, self.panel, self.fields = cog, panel, form["fields"]
        for field in self.fields:
            self.add_item(discord.ui.TextInput(label=field["label"], custom_id=field["key"], placeholder=field["placeholder"] or None,
                style=discord.TextStyle.paragraph if field["style"] == "paragraph" else discord.TextStyle.short,
                required=field["required"], min_length=field["min_length"] or None, max_length=field["max_length"]))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = {field["key"]: str(child.value) for field, child in zip(self.fields, self.children)}
        await self.cog.create_ticket(interaction, self.panel["id"], answers)


class TicketCloseReasonModal(discord.ui.Modal):
    reason = discord.ui.TextInput(label="Close理由", style=discord.TextStyle.paragraph, min_length=1, max_length=1000)

    def __init__(self, cog: "TicketsCog", ticket_id: int) -> None:
        super().__init__(title="理由を入力してClose", custom_id=f"tueka-ticket:close-reason-submit:{ticket_id}")
        self.cog, self.ticket_id = cog, ticket_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        ticket = self.cog.repository.ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message("Ticketが見つかりません。", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        await self.cog.close_container(interaction, ticket, str(self.reason.value))


class TicketFeedbackModal(discord.ui.Modal):
    def __init__(self, cog: "TicketsCog", ticket_id: int, rating: int, form: dict[str, Any]) -> None:
        super().__init__(title=str(form["title"])[:45], custom_id=f"tueka-ticket-feedback-submit:{ticket_id}:{rating}")
        self.cog, self.ticket_id, self.rating, self.fields = cog, ticket_id, rating, form["fields"]
        for field in self.fields:
            self.add_item(discord.ui.TextInput(label=field["label"], custom_id=field["key"], placeholder=field["placeholder"] or None,
                style=discord.TextStyle.paragraph if field["style"] == "paragraph" else discord.TextStyle.short,
                required=field["required"], min_length=field["min_length"] or None, max_length=field["max_length"]))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = {field["key"]: self.cog.transcripts.encrypt_text(str(child.value)) for field, child in zip(self.fields, self.children)}
        try:
            ticket = self.cog.repository.ticket(self.ticket_id) or {}
            panel = self.cog.repository.panel(int(ticket.get("guild_id", 0)), int(ticket.get("panel_id", 0))) or {}
            self.cog.repository.save_feedback(self.ticket_id, interaction.user.id, self.rating, form_id=panel.get("exit_form_id"), answers_encrypted=answers)
            await interaction.response.send_message("評価を送信しました。", ephemeral=True)
        except sqlite3.IntegrityError:
            await interaction.response.send_message("このTicketは評価済みです。", ephemeral=True)
        except (PermissionError, ValueError):
            await interaction.response.send_message("この評価は受け付けられません。", ephemeral=True)


class TicketsCog(commands.Cog):
    ticket = app_commands.Group(name="ticket", description="サポートチケット操作")
    short = app_commands.Group(name="t", description="サポートチケット操作（短縮）")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        settings = bot.settings
        self.repository = TicketRepository(settings.database_path)
        self.transcripts = TranscriptStorage(settings.data_dir / "ticket-transcripts", settings.ticket_encryption_key, s3={
            "endpoint_url": settings.ticket_s3_endpoint_url, "region": settings.ticket_s3_region, "bucket": settings.ticket_s3_bucket,
            "access_key_id": settings.ticket_s3_access_key_id, "secret_access_key": settings.ticket_s3_secret_access_key,
            "prefix": settings.ticket_s3_prefix,
        })
        self.service = TicketService(self.repository, self.transcripts)
        self.owner = f"ticket:{socket.gethostname()}:{os.getpid()}"
        self.deliver_outbox.start()
        self.auto_close.start()
        self.publish_panels.start()
        self.maintain_transcripts.start()

    def cog_unload(self) -> None:
        self.deliver_outbox.cancel()
        self.auto_close.cancel()
        self.publish_panels.cancel()
        self.maintain_transcripts.cancel()

    def enabled(self, guild_id: int) -> bool:
        return bool(self.bot.settings.tickets_v2 and (not self.bot.settings.tickets_v2_guilds or guild_id in self.bot.settings.tickets_v2_guilds))

    async def _staff(self, member: discord.Member, panel: dict[str, Any] | None) -> bool:
        if member.guild_permissions.manage_guild:
            return True
        team = self.repository.team(member.guild.id, int(panel["team_id"])) if panel and panel.get("team_id") else None
        return bool(team and (member.id in team.get("user_ids", []) or member.id in team.get("admin_user_ids", []) or any(role.id in team.get("role_ids", []) for role in member.roles)))

    @staticmethod
    def _render(value: str, ticket: dict[str, Any], panel: dict[str, Any], member: discord.Member, team: dict[str, Any] | None) -> str:
        replacements = {"ticket_number": ticket["ticket_number"], "user": member.mention, "username": member.name,
                        "user_id": member.id, "panel": panel["name"], "team": (team or {}).get("name", "Support")}
        result = str(value or "")
        for key, replacement in replacements.items():
            result = result.replace("{" + key + "}", str(replacement))
        return result

    def _welcome_embed(self, ticket: dict[str, Any], panel: dict[str, Any], member: discord.Member, team: dict[str, Any] | None) -> discord.Embed:
        config = panel.get("welcome_embed") or {}
        timestamp = datetime.now(timezone.utc) if config.get("footer", {}).get("timestamp") else None
        embed = discord.Embed(title=self._render(config.get("title", ""), ticket, panel, member, team) or None,
            description=self._render(config.get("description", ""), ticket, panel, member, team) or None,
            url=config.get("title_url") or None, color=int(str(config.get("color") or "#5865F2").lstrip("#"), 16), timestamp=timestamp)
        author = config.get("author") or {}
        if author.get("enabled") and author.get("name"):
            embed.set_author(name=self._render(author["name"], ticket, panel, member, team), url=author.get("url") or None, icon_url=author.get("icon_url") or None)
        footer = config.get("footer") or {}
        if footer.get("enabled") and footer.get("text"):
            embed.set_footer(text=self._render(footer["text"], ticket, panel, member, team), icon_url=footer.get("icon_url") or None)
        if config.get("image_url"): embed.set_image(url=config["image_url"])
        if config.get("thumbnail_url"): embed.set_thumbnail(url=config["thumbnail_url"])
        for field in config.get("fields", []):
            embed.add_field(name=self._render(field["name"], ticket, panel, member, team), value=self._render(field["value"], ticket, panel, member, team), inline=bool(field.get("inline")))
        return embed

    async def _remove_open_mentions(self, message: discord.Message, ticket: dict[str, Any]) -> None:
        await asyncio.sleep(5)
        try:
            await message.edit(content=None, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            self.repository.audit(int(ticket["guild_id"]), "opening_mentions_remove_failed", self.bot.user.id if self.bot.user else None, int(ticket["id"]), {"error": type(exc).__name__})

    async def _capture_attachments(self, ticket: dict[str, Any], attachments: list[discord.Attachment]) -> list[dict[str, Any]]:
        existing = {int(item["discord_attachment_id"]): item for item in self.repository.attachments(int(ticket["id"]))}
        used = self.repository.attachment_usage(int(ticket["id"]))
        result: list[dict[str, Any]] = []
        for attachment in attachments[:10]:
            metadata = {"id": attachment.id, "filename": attachment.filename, "content_type": attachment.content_type, "size": attachment.size, "stored": False}
            if attachment.id in existing:
                metadata["stored"] = existing[attachment.id].get("status") == "ready"
            elif attachment.size <= 25 * 1024 * 1024 and used + attachment.size <= 100 * 1024 * 1024:
                try:
                    data = await attachment.read(use_cached=True)
                    stored = await self.transcripts.save_attachment(int(ticket["guild_id"]), int(ticket["id"]), attachment.id, data)
                    self.repository.save_attachment(int(ticket["id"]), attachment.id, attachment.filename, attachment.content_type, len(data), stored.backend, stored.object_key, stored.content_hash)
                    used += len(data); metadata["stored"] = True
                except Exception:
                    LOGGER.warning("Could not archive ticket attachment ticket=%s attachment=%s", ticket["id"], attachment.id, exc_info=True)
            result.append(metadata)
        return result

    async def _set_claim(self, ticket: dict[str, Any], panel: dict[str, Any], member: discord.Member | None, expected_revision: int | None) -> dict[str, Any]:
        guild = self.bot.get_guild(int(ticket["guild_id"]))
        channel = guild.get_channel(int(ticket["discord_container_id"])) if guild else None
        if not isinstance(channel, discord.TextChannel) or ticket["mode"] != "channel":
            raise ValueError("claim_unavailable")
        team = self.repository.team(guild.id, int(panel["team_id"])) if panel.get("team_id") else None
        subjects: list[discord.Role | discord.Member] = []
        for role_id in (team or {}).get("role_ids", []):
            role = guild.get_role(int(role_id))
            if role: subjects.append(role)
        previous = guild.get_member(int(ticket.get("claimed_by") or 0))
        if previous: subjects.append(previous)
        if member: subjects.append(member)
        snapshots = {subject: channel.overwrites_for(subject) for subject in subjects}
        try:
            for subject in subjects:
                if isinstance(subject, discord.Role):
                    visible = panel["claim_mode"] != "claim_only_view" or member is None
                    await channel.set_permissions(subject, view_channel=visible, send_messages=panel["claim_mode"] == "shared_reply", read_message_history=visible, manage_messages=visible, reason="Ticket claim updated")
            if previous and (member is None or previous.id != member.id):
                await channel.set_permissions(previous, overwrite=None, reason="Ticket claim transferred")
            if member:
                await channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True, manage_messages=True, reason="Ticket claimed")
            return self.repository.set_claim(ticket["id"], member.id if member else None, expected_revision)
        except Exception:
            for subject, overwrite in snapshots.items():
                try: await channel.set_permissions(subject, overwrite=overwrite, reason="Ticket claim rollback")
                except discord.HTTPException: pass
            self.repository.audit(guild.id, "claim_failed", member.id if member else None, ticket["id"], {"rollback": True})
            raise

    async def show_open(self, interaction: discord.Interaction, panel_id: int) -> None:
        if not interaction.guild or not self.enabled(interaction.guild.id):
            await interaction.response.send_message("この機能は現在利用できません。", ephemeral=True)
            return
        panel = self.repository.panel(interaction.guild.id, panel_id)
        if not panel:
            await interaction.response.send_message("チケット種別が見つかりません。", ephemeral=True)
            return
        form = self.repository.form(interaction.guild.id, int(panel["form_id"])) if panel.get("form_id") else None
        if form and form["fields"]:
            await interaction.response.send_modal(TicketFormModal(self, panel, form))
        else:
            await self.create_ticket(interaction, panel_id, {})

    async def create_ticket(self, interaction: discord.Interaction, panel_id: int, answers: dict[str, str]) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        member = interaction.user
        if not self.transcripts.available:
            await interaction.followup.send("Ticket暗号鍵が設定されていないため作成できません。", ephemeral=True)
            return
        panel = self.repository.panel(interaction.guild.id, panel_id)
        try:
            exempt = await self._staff(member, panel)
            ticket, panel = self.service.reserve(interaction.guild.id, panel_id, member.id, str(interaction.id), answers, role_ids={role.id for role in member.roles}, staff_exempt=exempt)
        except TicketValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except (OverflowError, KeyError, ValueError) as exc:
            await interaction.followup.send("チケットを作成できません。設定と上限を確認してください。", ephemeral=True)
            return
        guild, name = interaction.guild, self.service.channel_name(ticket, panel, member.name)
        team = self.repository.team(guild.id, int(panel["team_id"])) if panel.get("team_id") else None
        container: discord.TextChannel | discord.Thread | None = None
        try:
            if panel["mode"] == "channel":
                category = guild.get_channel(int(panel["category_id"]))
                if not isinstance(category, discord.CategoryChannel):
                    raise ValueError("category")
                overwrites: dict[Any, discord.PermissionOverwrite] = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True,
                        attach_files=panel["creator_permissions"]["attach_files"], add_reactions=panel["creator_permissions"]["add_reactions"],
                        send_tts_messages=panel["creator_permissions"]["send_tts_messages"], embed_links=panel["creator_permissions"]["embed_links"],
                        use_external_emojis=panel["creator_permissions"]["use_external_emojis"], use_external_stickers=panel["creator_permissions"]["use_external_stickers"],
                        send_voice_messages=panel["creator_permissions"]["send_voice_messages"]),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True, read_message_history=True),
                }
                for role_id in (team or {}).get("role_ids", []):
                    role = guild.get_role(int(role_id))
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=panel["claim_mode"] == "shared_reply", read_message_history=True, manage_messages=True)
                container = await guild.create_text_channel(name, category=category, overwrites=overwrites, reason=f"Ticket #{ticket['ticket_number']}")
            else:
                parent = guild.get_channel(int(panel["thread_parent_channel_id"]))
                if not isinstance(parent, discord.TextChannel):
                    raise ValueError("thread_parent")
                container = await parent.create_thread(name=name, type=discord.ChannelType.private_thread, invitable=False, reason=f"Ticket #{ticket['ticket_number']}")
                await container.add_user(member)
                with self.repository._connection() as connection:
                    on_call = connection.execute("SELECT user_id FROM ticket_on_call WHERE guild_id=? AND team_id=?", (guild.id, int(panel.get("team_id") or 0))).fetchall()
                for row in on_call:
                    staff = guild.get_member(int(row["user_id"]))
                    if staff:
                        try: await container.add_user(staff)
                        except discord.HTTPException: pass
            ticket = self.repository.activate_ticket(ticket["id"], container.id, container.parent_id)
            self.service.schedule_ticket(ticket)
        except Exception as exc:
            if container is not None:
                self.repository.record_orphan(guild.id, ticket["id"], container.id, panel["mode"], type(exc).__name__)
            self.repository.fail_ticket(ticket["id"], type(exc).__name__)
            LOGGER.warning("Ticket creation failed guild=%s ticket=%s", guild.id, ticket["id"], exc_info=True)
            await interaction.followup.send("Ticketを作成できませんでした。Bot権限と作成先を確認してください。", ephemeral=True)
            return
        controls = discord.ui.View(timeout=None)
        if panel.get("show_claim_button") and panel["mode"] == "channel":
            controls.add_item(discord.ui.Button(label="Claim", style=discord.ButtonStyle.secondary, custom_id=f"tueka-ticket:claim:{ticket['id']}"))
        if panel["mode"] == "private_thread":
            controls.add_item(discord.ui.Button(label="参加", style=discord.ButtonStyle.secondary, custom_id=f"tueka-ticket:join:{ticket['id']}"))
        if panel.get("show_close_button"):
            controls.add_item(discord.ui.Button(label="Close", style=discord.ButtonStyle.danger, custom_id=f"tueka-ticket:close:{ticket['id']}"))
        if panel.get("show_close_reason_button"):
            controls.add_item(discord.ui.Button(label="理由を入力してClose", style=discord.ButtonStyle.secondary, custom_id=f"tueka-ticket:close-reason:{ticket['id']}"))
        if panel.get("awaiting_category_id") and panel["mode"] == "channel":
            controls.add_item(discord.ui.Button(label="回答待ち", style=discord.ButtonStyle.secondary, custom_id=f"tueka-ticket:awaiting:{ticket['id']}"))
        embed = self._welcome_embed(ticket, panel, member, team)
        if answers:
            for key, encrypted in ticket.get("form_answers", {}).items():
                embed.add_field(name=key[:256], value=self.transcripts.decrypt_text(encrypted)[:1024] or "-", inline=False)
        mentions = [guild.get_role(int(role_id)) for role_id in panel.get("mention_role_ids", [])]
        content = " ".join([member.mention] + [role.mention for role in mentions if role])
        message = await container.send(content=content, embed=embed, view=controls,
            allowed_mentions=discord.AllowedMentions(everyone=False, users=[member], roles=[role for role in mentions if role]))
        if panel.get("remove_mentions"):
            asyncio.create_task(self._remove_open_mentions(message, ticket))
        self.service.record_message(ticket, message.id, self.bot.user.id if self.bot.user else None, str(self.bot.user), "Ticket opened", [], kind="system", created_at=int(message.created_at.timestamp()))
        if panel["mode"] == "private_thread":
            notify = guild.get_channel(int(panel["staff_notification_channel_id"]))
            if isinstance(notify, discord.TextChannel):
                view = discord.ui.View(timeout=None); view.add_item(discord.ui.Button(label="Ticketに参加", custom_id=f"tueka-ticket:join:{ticket['id']}"))
                await notify.send(f"新しいTicket #{ticket['ticket_number']} · {panel['name']}", view=view, allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send(f"Ticketを作成しました: {container.mention}", ephemeral=True)

    async def close_container(self, interaction: discord.Interaction, ticket: dict[str, Any], reason: str) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        panel = self.repository.panel(interaction.guild.id, int(ticket["panel_id"]))
        if interaction.user.id != ticket["opener_id"] and not await self._staff(interaction.user, panel):
            await interaction.followup.send("Ticket作成者またはStaffだけがCloseできます。", ephemeral=True)
            return
        if interaction.user.id == ticket["opener_id"] and not panel.get("allow_user_close", True):
            await interaction.followup.send("このTicketはStaffだけがCloseできます。", ephemeral=True)
            return
        try:
            channel = interaction.guild.get_channel_or_thread(int(ticket["discord_container_id"]))
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                await self._reconcile_history(ticket, channel)
            closed, transcript = await self.service.close(ticket["id"], interaction.user.id, reason)
        except (TicketValidationError, RuntimeError, ValueError) as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await interaction.followup.send(f"TicketをCloseしました。Transcript #{transcript['id']} を保存しました。", ephemeral=True)
        settings = self.repository.settings(interaction.guild.id)
        opener = interaction.guild.get_member(int(ticket["opener_id"]))
        if opener is None:
            try: opener = await self.bot.fetch_user(int(ticket["opener_id"]))
            except discord.HTTPException: opener = None
        if settings.get("close_dm") and opener:
            try:
                panel = self.repository.panel(interaction.guild.id, int(ticket["panel_id"])) or {}
                view = discord.ui.View(timeout=None)
                base = str(self.bot.settings.dashboard_base_url or "").rstrip("/")
                if base:
                    view.add_item(discord.ui.Button(label="Transcript", style=discord.ButtonStyle.link, url=f"{base}/tickets/transcripts/{transcript['id']}"))
                if panel.get("feedback_enabled"):
                    for rating in range(1, 6):
                        view.add_item(discord.ui.Button(label=str(rating), style=discord.ButtonStyle.secondary, custom_id=f"tueka-ticket-feedback:{ticket['id']}:{rating}"))
                await opener.send(f"Ticket #{ticket['ticket_number']} をCloseしました。", view=view, allowed_mentions=discord.AllowedMentions.none())
            except (discord.Forbidden, discord.HTTPException):
                self.repository.audit(interaction.guild.id, "close_dm_failed", interaction.user.id, ticket["id"])
        transcript_channel_id = panel.get("transcript_channel_id") or settings.get("transcript_channel_id")
        transcript_destination = interaction.guild.get_channel(int(transcript_channel_id or 0))
        if isinstance(transcript_destination, discord.TextChannel):
            try:
                base = str(self.bot.settings.dashboard_base_url or "").rstrip("/")
                link = f"[Transcript #{transcript['id']}]({base}/tickets/transcripts/{transcript['id']})" if base else f"Transcript #{transcript['id']}"
                await transcript_destination.send(f"Ticket #{ticket['ticket_number']} · {panel.get('name', 'Ticket')} · {link}\nClose理由: {reason[:1000]}", allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException as exc:
                self.repository.audit(interaction.guild.id, "transcript_notification_failed", interaction.user.id, ticket["id"], {"error": type(exc).__name__})
        if isinstance(channel, discord.Thread):
            await channel.edit(archived=True, locked=True, reason="Ticket closed")
        elif isinstance(channel, discord.TextChannel):
            await channel.delete(reason="Ticket closed and transcript saved")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component:
            return
        custom_id = str((interaction.data or {}).get("custom_id", ""))
        if custom_id.startswith("tueka-ticket-feedback:"):
            parts = custom_id.split(":")
            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                try:
                    ticket = self.repository.ticket(int(parts[1])) or {}
                    panel = self.repository.panel(int(ticket.get("guild_id", 0)), int(ticket.get("panel_id", 0))) or {}
                    if not panel.get("feedback_enabled"):
                        raise PermissionError("feedback_disabled")
                    form = self.repository.form(int(ticket["guild_id"]), int(panel["exit_form_id"])) if panel.get("exit_form_id") else None
                    if form and form.get("fields"):
                        await interaction.response.send_modal(TicketFeedbackModal(self, int(parts[1]), int(parts[2]), form))
                    else:
                        self.repository.save_feedback(int(parts[1]), interaction.user.id, int(parts[2]))
                        await interaction.response.send_message("評価を送信しました。", ephemeral=True)
                except sqlite3.IntegrityError:
                    await interaction.response.send_message("このTicketは評価済みです。", ephemeral=True)
                except (PermissionError, ValueError):
                    await interaction.response.send_message("この評価は受け付けられません。", ephemeral=True)
            return
        if not interaction.guild:
            return
        if custom_id.startswith("tueka-ticket-close-request:"):
            parts = custom_id.split(":")
            if len(parts) == 3 and parts[2].isdigit() and isinstance(interaction.user, discord.Member):
                request = self.repository.close_request(int(parts[2]))
                ticket = self.repository.ticket(int(request["ticket_id"])) if request else None
                panel = self.repository.panel(interaction.guild.id, int(ticket["panel_id"])) if ticket else None
                if not request or not ticket or not await self._staff(interaction.user, panel):
                    await interaction.response.send_message("Staffだけが回答できます。", ephemeral=True); return
                approved = parts[1] == "approve"
                self.repository.resolve_close_request(int(parts[2]), interaction.user.id, approved)
                if approved:
                    await interaction.response.defer(ephemeral=True)
                    await self.close_container(interaction, ticket, str(request.get("reason") or "Close Request"))
                else:
                    await interaction.response.send_message("Close Requestを却下しました。", ephemeral=True)
            return
        if custom_id == "tueka-ticket:create":
            panels = self.repository.panels(interaction.guild.id)
            if panels: await self.show_open(interaction, panels[0]["id"])
            return
        parts = custom_id.split(":")
        if len(parts) != 3 or parts[0] != "tueka-ticket" or not parts[2].isdigit():
            return
        action, entity_id = parts[1], int(parts[2])
        if action == "open":
            await self.show_open(interaction, entity_id); return
        ticket = self.repository.ticket(entity_id)
        if not ticket:
            await interaction.response.send_message("Ticketが見つかりません。", ephemeral=True); return
        if action == "close-reason":
            await interaction.response.send_modal(TicketCloseReasonModal(self, entity_id)); return
        await interaction.response.defer(ephemeral=True)
        if action == "join" and isinstance(interaction.user, discord.Member):
            panel = self.repository.panel(interaction.guild.id, int(ticket["panel_id"]))
            if not await self._staff(interaction.user, panel):
                await interaction.followup.send("Staffだけが参加できます。", ephemeral=True); return
            thread = interaction.guild.get_thread(int(ticket["discord_container_id"]))
            if thread: await thread.add_user(interaction.user)
            self.repository.add_participant(ticket["id"], "user", interaction.user.id, interaction.user.id, "staff")
            await interaction.followup.send("Ticketに参加しました。", ephemeral=True)
        elif action == "claim" and isinstance(interaction.user, discord.Member):
            panel = self.repository.panel(interaction.guild.id, int(ticket["panel_id"]))
            if not await self._staff(interaction.user, panel):
                await interaction.followup.send("StaffだけがClaimできます。", ephemeral=True); return
            await self._set_claim(ticket, panel, interaction.user, ticket["revision"])
            await interaction.followup.send("TicketをClaimしました。", ephemeral=True)
        elif action == "close":
            await self.close_container(interaction, ticket, "解決済み")
        elif action == "awaiting" and isinstance(interaction.user, discord.Member):
            panel = self.repository.panel(interaction.guild.id, int(ticket["panel_id"])) or {}
            if not await self._staff(interaction.user, panel):
                await interaction.followup.send("Staffだけが回答待ちへ変更できます。", ephemeral=True); return
            channel = interaction.guild.get_channel(int(ticket.get("discord_container_id") or 0))
            category = interaction.guild.get_channel(int(panel.get("awaiting_category_id") or 0))
            if not isinstance(channel, discord.TextChannel) or not isinstance(category, discord.CategoryChannel):
                await interaction.followup.send("回答待ちCategoryを確認してください。", ephemeral=True); return
            original_category = channel.category_id or int(panel.get("category_id") or 0)
            try:
                await channel.edit(category=category, reason="Ticket awaiting user")
                self.repository.set_awaiting_user(ticket["id"], original_category)
                self.repository.audit(interaction.guild.id, "ticket_awaiting_user", interaction.user.id, ticket["id"])
                await interaction.followup.send("Ticketを回答待ちへ変更しました。", ephemeral=True)
            except (discord.HTTPException, RuntimeError):
                await interaction.followup.send("回答待ちへ変更できませんでした。", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot or not self.enabled(message.guild.id):
            return
        ticket = self.repository.ticket_for_container(message.channel.id)
        if ticket and ticket["status"] in {"open", "awaiting_user"} and self.transcripts.available:
            attachments = await self._capture_attachments(ticket, message.attachments)
            self.service.record_message(ticket, message.id, message.author.id, str(message.author), message.content,
                attachments, created_at=int(message.created_at.timestamp()))
            if ticket["status"] == "awaiting_user" and message.author.id == int(ticket["opener_id"]) and isinstance(message.channel, discord.TextChannel):
                category = message.guild.get_channel(int(ticket.get("awaiting_return_category_id") or 0))
                if isinstance(category, discord.CategoryChannel):
                    try:
                        await message.channel.edit(category=category, reason="Ticket opener replied")
                        self.repository.resume_awaiting_user(ticket["id"])
                        self.repository.audit(message.guild.id, "ticket_resumed", message.author.id, ticket["id"])
                    except (discord.HTTPException, RuntimeError) as exc:
                        self.repository.audit(message.guild.id, "ticket_resume_failed", message.author.id, ticket["id"], {"error": type(exc).__name__})

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not after.guild or after.author.bot or not self.enabled(after.guild.id):
            return
        ticket = self.repository.ticket_for_container(after.channel.id)
        if ticket and ticket["status"] == "open" and self.transcripts.available:
            attachments = await self._capture_attachments(ticket, after.attachments)
            self.service.record_message(ticket, after.id, after.author.id, str(after.author), after.content,
                attachments, created_at=int(discord.utils.utcnow().timestamp()))

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        self.repository.mark_message_deleted(payload.message_id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not self.enabled(member.guild.id):
            return
        defaults = self.repository.settings(member.guild.id)["default_auto_close"]
        for ticket in self.repository.tickets(member.guild.id, status="open", limit=200):
            if int(ticket["opener_id"]) != member.id or ticket.get("auto_close_excluded"):
                continue
            panel = self.repository.panel(member.guild.id, int(ticket["panel_id"])) or {}
            auto = panel.get("auto_close") or defaults
            if auto.get("on_member_leave"):
                self.repository.queue_outbox(ticket["id"], "auto_close", self.bot.user.id if self.bot.user else 0, {"reason": "Ticket作成者がサーバーから退出"})

    @ticket.command(name="open", description="Ticketを作成します。")
    async def ticket_open(self, interaction: discord.Interaction, panel_id: int) -> None:
        await self.show_open(interaction, panel_id)

    @short.command(name="open", description="Ticketを作成します。")
    async def short_open(self, interaction: discord.Interaction, panel_id: int) -> None:
        await self.show_open(interaction, panel_id)

    @ticket.command(name="claim", description="現在のTicketをClaimします。")
    async def claim(self, interaction: discord.Interaction) -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0)
        if not ticket or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("開いているTicket内で実行してください。", ephemeral=True); return
        panel = self.repository.panel(interaction.guild_id or 0, int(ticket["panel_id"]))
        if not await self._staff(interaction.user, panel):
            await interaction.response.send_message("Staffだけが実行できます。", ephemeral=True); return
        await self._set_claim(ticket, panel, interaction.user, ticket["revision"])
        await interaction.response.send_message("TicketをClaimしました。")

    @ticket.command(name="unclaim", description="Claimを解除します。")
    async def unclaim(self, interaction: discord.Interaction) -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0)
        if not ticket or ticket.get("claimed_by") != interaction.user.id:
            await interaction.response.send_message("自分がClaimしたTicketで実行してください。", ephemeral=True); return
        panel = self.repository.panel(interaction.guild_id or 0, int(ticket["panel_id"]))
        await self._set_claim(ticket, panel or {}, None, ticket["revision"])
        await interaction.response.send_message("Claimを解除しました。")

    @ticket.command(name="close", description="TicketをCloseしてTranscriptを保存します。")
    async def close(self, interaction: discord.Interaction, reason: str = "解決済み") -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0)
        if not ticket:
            await interaction.response.send_message("Ticket内で実行してください。", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        await self.close_container(interaction, ticket, reason)

    @short.command(name="close", description="TicketをCloseします。")
    async def short_close(self, interaction: discord.Interaction, reason: str = "解決済み") -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0)
        if not ticket:
            await interaction.response.send_message("Ticket内で実行してください。", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        await self.close_container(interaction, ticket, reason)

    @ticket.command(name="reopen", description="Closed Thread Ticketを再開します。")
    @app_commands.checks.has_permissions(manage_threads=True)
    async def reopen(self, interaction: discord.Interaction, ticket_id: int) -> None:
        ticket = self.repository.reopen_ticket(ticket_id)
        thread = interaction.guild.get_thread(int(ticket["discord_container_id"])) if interaction.guild else None
        if not thread:
            await interaction.response.send_message("Threadが見つかりません。", ephemeral=True); return
        await thread.edit(archived=False, locked=False, reason="Ticket reopened")
        self.service.schedule_ticket(ticket)
        await interaction.response.send_message(f"Ticket #{ticket['ticket_number']}を再開しました。", ephemeral=True)

    @ticket.command(name="rename", description="Ticket名を変更します。")
    async def rename(self, interaction: discord.Interaction, name: str) -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0)
        if not ticket or not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("Ticket内で実行してください。", ephemeral=True); return
        await interaction.channel.edit(name=name[:100], reason=f"Ticket rename by {interaction.user}")
        await interaction.response.send_message("Ticket名を変更しました。", ephemeral=True)

    @ticket.command(name="add", description="Ticketへユーザーを追加します。")
    async def add(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0)
        if not ticket or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Ticket内で実行してください。", ephemeral=True); return
        panel = self.repository.panel(interaction.guild_id or 0, int(ticket["panel_id"]))
        if not await self._staff(interaction.user, panel):
            await interaction.response.send_message("Staffだけが実行できます。", ephemeral=True); return
        if isinstance(interaction.channel, discord.Thread): await interaction.channel.add_user(member)
        elif isinstance(interaction.channel, discord.TextChannel): await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True, reason="Ticket participant added")
        self.repository.add_participant(ticket["id"], "user", member.id, interaction.user.id)
        await interaction.response.send_message(f"{member.mention} を追加しました。", allowed_mentions=discord.AllowedMentions(users=[member]))

    @ticket.command(name="remove", description="Ticketからユーザーを削除します。")
    async def remove(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0)
        panel = self.repository.panel(interaction.guild_id or 0, int(ticket["panel_id"])) if ticket else None
        if not ticket or not isinstance(interaction.user, discord.Member) or not await self._staff(interaction.user, panel):
            await interaction.response.send_message("StaffだけがTicket内で実行できます。", ephemeral=True); return
        if member.id == int(ticket["opener_id"]):
            await interaction.response.send_message("Ticket作成者は削除できません。", ephemeral=True); return
        if isinstance(interaction.channel, discord.Thread): await interaction.channel.remove_user(member)
        elif isinstance(interaction.channel, discord.TextChannel): await interaction.channel.set_permissions(member, overwrite=None, reason="Ticket participant removed")
        self.repository.remove_participant(ticket["id"], "user", member.id)
        await interaction.response.send_message("ユーザーを削除しました。", ephemeral=True)

    @ticket.command(name="transfer", description="Claim担当者を変更します。")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0)
        panel = self.repository.panel(interaction.guild_id or 0, int(ticket["panel_id"])) if ticket else None
        if not ticket or not isinstance(interaction.user, discord.Member) or not await self._staff(interaction.user, panel) or not await self._staff(member, panel):
            await interaction.response.send_message("担当TeamのStaffを指定してください。", ephemeral=True); return
        await self._set_claim(ticket, panel or {}, member, ticket["revision"])
        await interaction.response.send_message(f"担当を {member.mention} へ変更しました。", allowed_mentions=discord.AllowedMentions(users=[member]))

    @ticket.command(name="notes", description="作成者には見えないStaff Noteを追加します。")
    async def notes(self, interaction: discord.Interaction, content: str) -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0)
        panel = self.repository.panel(interaction.guild_id or 0, int(ticket["panel_id"])) if ticket else None
        if not ticket or not isinstance(interaction.user, discord.Member) or not await self._staff(interaction.user, panel):
            await interaction.response.send_message("Staffだけが実行できます。", ephemeral=True); return
        self.service.queue_reply(ticket["id"], interaction.user.id, interaction.user.display_name, content, note=True)
        await interaction.response.send_message("Staff Noteを保存キューへ追加しました。", ephemeral=True)

    @ticket.command(name="close-request", description="StaffへCloseの承認を依頼します。")
    async def close_request_command(self, interaction: discord.Interaction, reason: str = "解決済み") -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0)
        if not ticket:
            await interaction.response.send_message("Ticket内で実行してください。", ephemeral=True); return
        request = self.repository.create_close_request(ticket["id"], interaction.user.id, reason)
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="承認", style=discord.ButtonStyle.danger, custom_id=f"tueka-ticket-close-request:approve:{request['id']}"))
        view.add_item(discord.ui.Button(label="却下", style=discord.ButtonStyle.secondary, custom_id=f"tueka-ticket-close-request:deny:{request['id']}"))
        await interaction.response.send_message("Close Request（24時間有効）", view=view, allowed_mentions=discord.AllowedMentions.none())

    @ticket.command(name="on-call", description="Thread Ticketへの自動参加を切り替えます。")
    async def on_call(self, interaction: discord.Interaction, team_id: int, enabled: bool) -> None:
        team = self.repository.team(interaction.guild_id or 0, team_id)
        if not team or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Staff Teamが見つかりません。", ephemeral=True); return
        if not (interaction.user.guild_permissions.manage_guild or await self._staff(interaction.user, {"team_id": team_id})):
            await interaction.response.send_message("このTeamのStaffだけが変更できます。", ephemeral=True); return
        self.repository.set_on_call(interaction.guild_id or 0, team_id, interaction.user.id, enabled)
        await interaction.response.send_message("On-Callを更新しました。", ephemeral=True)

    @ticket.command(name="join", description="Thread TicketへStaffとして参加します。")
    async def join(self, interaction: discord.Interaction, ticket_id: int) -> None:
        ticket = self.repository.ticket(ticket_id)
        panel = self.repository.panel(interaction.guild_id or 0, int(ticket["panel_id"])) if ticket else None
        if not ticket or ticket["mode"] != "private_thread" or not isinstance(interaction.user, discord.Member) or not await self._staff(interaction.user, panel):
            await interaction.response.send_message("参加できるThread Ticketが見つかりません。", ephemeral=True); return
        thread = interaction.guild.get_thread(int(ticket["discord_container_id"])) if interaction.guild else None
        if not thread:
            await interaction.response.send_message("Threadが見つかりません。", ephemeral=True); return
        await thread.add_user(interaction.user)
        self.repository.add_participant(ticket["id"], "user", interaction.user.id, interaction.user.id, "staff")
        await interaction.response.send_message("Ticketへ参加しました。", ephemeral=True)

    @ticket.command(name="blacklist", description="ユーザーのTicket作成制限を変更します。")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def blacklist(self, interaction: discord.Interaction, member: discord.Member, enabled: bool, reason: str = "管理者による制限") -> None:
        self.repository.set_blacklist(interaction.guild_id or 0, member.id, interaction.user.id, reason if enabled else None)
        await interaction.response.send_message("Blacklistを更新しました。", ephemeral=True)

    @ticket.command(name="switch-panel", description="同じModeの別Panelへ切り替えます。")
    async def switch_panel(self, interaction: discord.Interaction, panel_id: int) -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0); panel = self.repository.panel(interaction.guild_id or 0, panel_id)
        current = self.repository.panel(interaction.guild_id or 0, int(ticket["panel_id"])) if ticket else None
        if not ticket or not panel or panel["mode"] != ticket["mode"] or not isinstance(interaction.user, discord.Member) or not await self._staff(interaction.user, current):
            await interaction.response.send_message("同じModeの有効なPanelを指定してください。", ephemeral=True); return
        with self.repository._connection() as connection:
            connection.execute("UPDATE tickets_v2 SET panel_id=?,claimed_by=NULL,revision=revision+1 WHERE id=? AND status='open'", (panel_id, ticket["id"]))
        await interaction.response.send_message(f"Panelを {panel['name']} へ変更しました。", ephemeral=True)

    @ticket.command(name="stats", description="Ticketの概要を表示します。")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def stats(self, interaction: discord.Interaction) -> None:
        summary = self.repository.summary(interaction.guild_id or 0)
        await interaction.response.send_message(f"Open: {summary['open']}\nUnclaimed: {summary['unclaimed']}\nClosed (30d): {summary['closed_30d']}\nRating: {summary['average_rating'] or '-'}", ephemeral=True)

    @ticket.command(name="setup", description="Ticket設定画面を開きます。")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_command(self, interaction: discord.Interaction) -> None:
        base = str(self.bot.settings.dashboard_base_url or "").rstrip("/")
        await interaction.response.send_message(f"{base}/servers/{interaction.guild_id}/tickets" if base else "DASHBOARD_BASE_URLを設定してください。", ephemeral=True)

    @ticket.command(name="tag", description="定型文を送信します。")
    async def tag(self, interaction: discord.Interaction, name: str) -> None:
        if not interaction.guild:
            return
        with self.repository._connection() as connection:
            row = connection.execute("SELECT content FROM ticket_tags WHERE guild_id=? AND name=?", (interaction.guild.id, name.lower())).fetchone()
        if not row:
            await interaction.response.send_message("Tagが見つかりません。", ephemeral=True); return
        await interaction.response.send_message(str(row["content"]), allowed_mentions=discord.AllowedMentions.none())

    async def _reconcile_history(self, ticket: dict[str, Any], channel: discord.TextChannel | discord.Thread) -> None:
        try:
            async for message in channel.history(limit=None, oldest_first=True):
                attachments = await self._capture_attachments(ticket, message.attachments)
                self.service.record_message(ticket, message.id, message.author.id, str(message.author), message.content,
                    attachments,
                    kind="system" if message.author.bot else "message", created_at=int(message.created_at.timestamp()))
        except discord.Forbidden:
            self.repository.audit(ticket["guild_id"], "transcript_reconcile_failed", self.bot.user.id if self.bot.user else None, ticket["id"], {"reason": "forbidden"})

    async def _deliver_note(self, item: dict[str, Any], ticket: dict[str, Any], guild: discord.Guild, channel: discord.TextChannel | discord.Thread) -> None:
        payload = item["payload"]
        plain = self.transcripts.decrypt_text(payload.get("content_encrypted"))
        if ticket["mode"] == "private_thread":
            self.service.record_message(ticket, None, int(item["actor_id"]), payload["actor_name"], plain, [], kind="note")
            return
        notes = guild.get_thread(int(ticket.get("notes_thread_id") or 0))
        if notes is None:
            if not isinstance(channel, discord.TextChannel):
                raise RuntimeError("Ticket notes parent unavailable")
            notes = await channel.create_thread(name=f"staff-notes-{ticket['ticket_number']}", type=discord.ChannelType.private_thread, invitable=False, reason="Ticket staff notes")
            self.repository.set_notes_thread(ticket["id"], notes.id)
        actor = guild.get_member(int(item["actor_id"]))
        if actor:
            await notes.add_user(actor)
        message = await notes.send(f"**{payload['actor_name']}**\n{plain}", allowed_mentions=discord.AllowedMentions.none())
        self.service.record_message(ticket, message.id, int(item["actor_id"]), payload["actor_name"], plain, [], kind="note", created_at=int(message.created_at.timestamp()))

    @tasks.loop(seconds=5)
    async def deliver_outbox(self) -> None:
        for item in self.repository.claim_outbox(self.owner, limit=20, lease_seconds=60):
            ticket = self.repository.ticket(int(item["ticket_id"]))
            guild = self.bot.get_guild(int(ticket["guild_id"])) if ticket else None
            channel = guild.get_channel_or_thread(int(ticket["discord_container_id"])) if guild and ticket else None
            try:
                action = str(item["action"])
                if action in {"close", "auto_close"}:
                    if not ticket or not guild or not isinstance(channel, (discord.TextChannel, discord.Thread)):
                        raise RuntimeError("Ticket channel unavailable")
                    await self._reconcile_history(ticket, channel)
                    await self.service.close(ticket["id"], int(item["actor_id"]), str(item["payload"].get("reason") or "Close"))
                    if isinstance(channel, discord.Thread):
                        await channel.edit(archived=True, locked=True, reason="Ticket auto closed")
                    else:
                        await channel.delete(reason="Ticket auto closed")
                    self.repository.complete_outbox(item["id"], self.owner)
                    continue
                if action in {"claim", "unclaim"}:
                    panel = self.repository.panel(int(ticket["guild_id"]), int(ticket["panel_id"])) or {}
                    claimant = guild.get_member(int(item["actor_id"])) if action == "claim" and guild else None
                    if action == "claim" and claimant is None: raise RuntimeError("Claimant unavailable")
                    await self._set_claim(ticket, panel, claimant, item["payload"].get("revision"))
                    self.repository.complete_outbox(item["id"], self.owner)
                    continue
                if action == "reopen":
                    reopened = self.repository.reopen_ticket(ticket["id"])
                    if not isinstance(channel, discord.Thread):
                        raise RuntimeError("Ticket thread unavailable")
                    await channel.edit(archived=False, locked=False, reason="Ticket reopened from dashboard")
                    self.service.schedule_ticket(reopened)
                    self.repository.audit(reopened["guild_id"], "ticket_reopened", int(item["actor_id"]), reopened["id"])
                    self.repository.complete_outbox(item["id"], self.owner)
                    continue
                if action == "exclude_auto_close":
                    with self.repository._connection() as connection:
                        connection.execute("UPDATE tickets_v2 SET auto_close_excluded=?,revision=revision+1 WHERE id=?", (int(bool(item["payload"].get("excluded", True))), ticket["id"]))
                    self.service.schedule_ticket(self.repository.ticket(ticket["id"]) or ticket)
                    self.repository.complete_outbox(item["id"], self.owner)
                    continue
                if action == "awaiting_user":
                    panel = self.repository.panel(int(ticket["guild_id"]), int(ticket["panel_id"])) or {}
                    category = guild.get_channel(int(panel.get("awaiting_category_id") or 0)) if guild else None
                    if not isinstance(channel, discord.TextChannel) or not isinstance(category, discord.CategoryChannel):
                        raise RuntimeError("Awaiting category unavailable")
                    original_category = channel.category_id or int(panel.get("category_id") or 0)
                    await channel.edit(category=category, reason="Ticket awaiting user")
                    self.repository.set_awaiting_user(ticket["id"], original_category)
                    self.repository.audit(int(ticket["guild_id"]), "ticket_awaiting_user", int(item["actor_id"]), ticket["id"])
                    self.repository.complete_outbox(item["id"], self.owner)
                    continue
                if action == "delete":
                    if isinstance(channel, (discord.TextChannel, discord.Thread)):
                        await channel.delete(reason="Ticket deleted from dashboard")
                    with self.repository._connection() as connection:
                        connection.execute("UPDATE tickets_v2 SET deleted_at=?,revision=revision+1 WHERE id=?", (int(discord.utils.utcnow().timestamp()), ticket["id"]))
                    self.repository.complete_outbox(item["id"], self.owner)
                    continue
                if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                    raise RuntimeError("Ticket channel unavailable")
                payload, content = item["payload"], self.transcripts.decrypt_text(item["payload"].get("content_encrypted"))
                if action == "note":
                    await self._deliver_note(item, ticket, guild, channel)
                    self.repository.complete_outbox(item["id"], self.owner)
                    continue
                if payload.get("anonymous"):
                    content = f"**Support Staff**\n{content}"
                else:
                    content = f"**{payload['actor_name']}**\n{content}"
                message = await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
                self.service.record_message(ticket, message.id, int(item["actor_id"]), payload["actor_name"], self.transcripts.decrypt_text(payload.get("content_encrypted")), [], kind="staff_reply", created_at=int(message.created_at.timestamp()))
                self.repository.complete_outbox(item["id"], self.owner)
            except (discord.Forbidden, discord.NotFound) as exc:
                self.repository.complete_outbox(item["id"], self.owner, str(exc), retry=False)
            except (RuntimeError, ValueError) as exc:
                retry = str(exc) not in {"revision_conflict", "ticket_not_open", "reopen_unavailable", "claim_unavailable"}
                self.repository.complete_outbox(item["id"], self.owner, str(exc), retry=retry)
            except Exception as exc:
                self.repository.complete_outbox(item["id"], self.owner, str(exc), retry=True)

    @tasks.loop(minutes=1)
    async def auto_close(self) -> None:
        self.repository.expire_close_requests()
        for schedule in self.repository.due_schedules():
            ticket = self.repository.ticket(int(schedule["ticket_id"]))
            if ticket and ticket["status"] == "open" and not ticket.get("auto_close_excluded") and self.enabled(int(ticket["guild_id"])):
                self.repository.queue_outbox(ticket["id"], "auto_close", self.bot.user.id if self.bot.user else 0, {"reason": "Auto Close · " + str(schedule["kind"])})
            self.repository.complete_schedule(int(schedule["id"]))

    @tasks.loop(seconds=10)
    async def publish_panels(self) -> None:
        for config in self.repository.claim_panel_messages(self.owner):
            guild = self.bot.get_guild(int(config["guild_id"]))
            channel = guild.get_channel(int(config["channel_id"])) if guild else None
            try:
                if not isinstance(channel, discord.TextChannel):
                    raise RuntimeError("Panel channel unavailable")
                if config.get("status") == "delete":
                    if config.get("message_id"):
                        try:
                            message = await channel.fetch_message(int(config["message_id"]))
                            await message.delete()
                        except discord.NotFound:
                            pass
                    self.repository.mark_panel_published(config["id"], 0, deleted=True)
                    continue
                view = discord.ui.View(timeout=None)
                styles = {"primary": discord.ButtonStyle.primary, "secondary": discord.ButtonStyle.secondary,
                          "success": discord.ButtonStyle.success, "danger": discord.ButtonStyle.danger}
                for panel_id in config.get("panel_ids", []):
                    panel = self.repository.panel(guild.id, int(panel_id))
                    if panel and panel.get("enabled"):
                        button = panel.get("button") or {}
                        view.add_item(discord.ui.Button(label=str(button.get("label") or panel["name"])[:80], style=styles.get(str(button.get("style")), discord.ButtonStyle.primary),
                            emoji=str(button.get("emoji")) or None, custom_id=f"tueka-ticket:open:{panel['id']}"))
                if not view.children:
                    raise RuntimeError("No enabled panels")
                embed = discord.Embed(title=str(config["title"])[:256], description=str(config.get("description") or "")[:4000], color=int(str(config.get("color") or "#5865F2").lstrip("#"), 16))
                if config.get("image_url"): embed.set_image(url=str(config["image_url"]))
                if config.get("thumbnail_url"): embed.set_thumbnail(url=str(config["thumbnail_url"]))
                old = None
                if config.get("message_id"):
                    try: old = await channel.fetch_message(int(config["message_id"]))
                    except discord.NotFound: pass
                message = await old.edit(content=str(config.get("content") or "") or None, embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none()) if old else await channel.send(content=str(config.get("content") or "") or None, embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
                if config.get("previous_channel_id") and config.get("previous_message_id"):
                    previous_channel = guild.get_channel(int(config["previous_channel_id"]))
                    if isinstance(previous_channel, discord.TextChannel):
                        try:
                            previous = await previous_channel.fetch_message(int(config["previous_message_id"]))
                            await previous.delete()
                        except discord.NotFound:
                            pass
                        except discord.HTTPException as exc:
                            self.repository.audit(guild.id, "panel_reposition_partial", self.bot.user.id if self.bot.user else None, detail={"panel_message_id": config["id"], "error": type(exc).__name__})
                self.repository.mark_panel_published(config["id"], message.id)
            except Exception as exc:
                self.repository.mark_panel_published(config["id"], int(config.get("message_id") or 0), str(exc))

    @tasks.loop(hours=1)
    async def maintain_transcripts(self) -> None:
        await self.service.migrate_legacy_transcripts()
        if self.transcripts.s3.get("bucket"):
            for item in self.repository.local_transcripts():
                try:
                    await self.transcripts.promote_local(str(item["object_key"]))
                    self.repository.mark_transcript_promoted(int(item["id"]))
                except Exception:
                    LOGGER.warning("Could not promote ticket transcript id=%s", item["id"], exc_info=True)
            for item in self.repository.local_attachments():
                try:
                    await self.transcripts.promote_local(str(item["object_key"]))
                    self.repository.mark_attachment_promoted(int(item["id"]))
                except Exception:
                    LOGGER.warning("Could not promote ticket attachment id=%s", item["id"], exc_info=True)
        for item in self.repository.expired_transcripts():
            try:
                for attachment in self.repository.attachments(int(item["ticket_id"])):
                    if attachment.get("status") == "ready":
                        await self.transcripts.delete(str(attachment["backend"]), str(attachment["object_key"]))
                await self.transcripts.delete(str(item["backend"]), str(item["object_key"]))
                self.repository.mark_transcript_deleted(int(item["id"]), int(item["ticket_id"]))
            except Exception:
                LOGGER.warning("Could not expire ticket transcript id=%s", item["id"], exc_info=True)

    @deliver_outbox.before_loop
    async def before_outbox(self) -> None:
        await self.bot.wait_until_ready()

    @auto_close.before_loop
    async def before_auto_close(self) -> None:
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            if self.enabled(guild.id):
                for ticket in self.repository.tickets(guild.id, status="open", limit=200):
                    self.service.schedule_ticket(ticket)

    @publish_panels.before_loop
    async def before_publish_panels(self) -> None:
        await self.bot.wait_until_ready()

    @maintain_transcripts.before_loop
    async def before_maintain_transcripts(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TicketsCog(bot))
