"""Ticket V2 Discord workflow."""
from __future__ import annotations

import logging
import os
import socket
from database import IntegrityError
from typing import Any

from jobs import LostLease, Outcome, run_batch
from jobs.leases import ResourceLease

import discord
from discord_io import DiscordFailure
from discord import app_commands
from discord.ext import commands, tasks

from ticketing.discord_adapter import DiscordTicketAdapter
from ticketing.panel_delivery import PanelDeliveryService
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
        except IntegrityError:
            await interaction.response.send_message("このTicketは評価済みです。", ephemeral=True)
        except (PermissionError, ValueError):
            await interaction.response.send_message("この評価は受け付けられません。", ephemeral=True)


class TicketsCog(commands.Cog):
    help_category = 'チケット'
    help_module = 'tickets'

    ticket = app_commands.Group(name="ticket", description="サポートチケット操作")
    short = app_commands.Group(name="t", description="サポートチケット操作（短縮）")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.discord = DiscordTicketAdapter(bot)
        settings = bot.settings
        self.repository = TicketRepository(settings.database_url)
        self.panel_delivery = PanelDeliveryService(self.repository, self.discord)
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


    async def _staff(self, member: discord.Member, panel: dict[str, Any] | None) -> bool:
        if member.guild_permissions.manage_guild:
            return True
        team = self.repository.team(member.guild.id, int(panel["team_id"])) if panel and panel.get("team_id") else None
        return bool(team and (member.id in team.get("user_ids", []) or member.id in team.get("admin_user_ids", []) or any(role.id in team.get("role_ids", []) for role in member.roles)))

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
                    data = await self.discord.read_attachment(attachment)
                    stored = await self.transcripts.save_attachment(int(ticket["guild_id"]), int(ticket["id"]), attachment.id, data)
                    self.repository.save_attachment(int(ticket["id"]), attachment.id, attachment.filename, attachment.content_type, len(data), stored.backend, stored.object_key, stored.content_hash)
                    used += len(data); metadata["stored"] = True
                except Exception:
                    LOGGER.warning("Could not archive ticket attachment ticket=%s attachment=%s", ticket["id"], attachment.id, exc_info=True)
            result.append(metadata)
        return result

    async def _set_claim(self, ticket: dict[str, Any], panel: dict[str, Any], member: discord.Member | None, expected_revision: int | None) -> dict[str, Any]:
        return await self.service.change_claim(self.discord, ticket, panel, member.id if member else None, expected_revision)

    async def show_open(self, interaction: discord.Interaction, panel_id: int) -> None:
        if not interaction.guild:
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
            ticket, panel = self.service.reserve(interaction.guild.id, panel_id, member.id, str(interaction.id),
                role_ids={role.id for role in member.roles}, answers=answers, staff_exempt=exempt)
        except TicketValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except (OverflowError, KeyError, ValueError) as exc:
            await interaction.followup.send("チケットを作成できません。設定と上限を確認してください。", ephemeral=True)
            return
        guild, name = interaction.guild, self.service.channel_name(ticket, panel, member.name)
        team = self.repository.team(guild.id, int(panel["team_id"])) if panel.get("team_id") else None
        try:
            ticket, resource = await self.service.open_container(self.discord, ticket, panel, name)
            container = self.discord.container(resource.id)
            if container is None:
                raise RuntimeError('Created Ticket container unavailable')
        except Exception as exc:
            LOGGER.warning("Ticket creation failed guild=%s ticket=%s", guild.id, ticket["id"], exc_info=True)
            await interaction.followup.send("Ticketを作成できませんでした。Bot権限と作成先を確認してください。", ephemeral=True)
            return
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
            await self._reconcile_history(ticket, channel)
            closed, transcript = await self.service.close(ticket["id"], interaction.user.id, reason)
        except (TicketValidationError, RuntimeError, ValueError, DiscordFailure) as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await interaction.followup.send(f"TicketをCloseしました。Transcript #{transcript['id']} を保存しました。", ephemeral=True)
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component:
            return
        custom_id = str((interaction.data or {}).get("custom_id", ""))
        if custom_id.startswith("tueka-ticket-feedback:"):
            parts = custom_id.split(":")
            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                try:
                    message_id = interaction.message.id if interaction.message else 0
                    if not self.repository.notice_message_recorded(int(parts[1]), message_id):
                        raise PermissionError("feedback_origin_unknown")
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
                except IntegrityError:
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
                if not request or not ticket or ticket['guild_id'] != interaction.guild.id or ticket.get('discord_container_id') != interaction.channel_id or not await self._staff(interaction.user, panel):
                    await interaction.response.send_message("Staffだけが回答できます。", ephemeral=True); return
                approved = parts[1] == "approve"
                self.repository.resolve_close_request(int(parts[2]), interaction.user.id, approved)
                if approved:
                    await interaction.response.defer(ephemeral=True)
                    await self.close_container(interaction, ticket, str(request.get("reason") or "Close Request"))
                else:
                    await interaction.response.send_message("Close Requestを却下しました。", ephemeral=True)
            return
        parts = custom_id.split(":")
        if len(parts) != 3 or parts[0] != "tueka-ticket" or not parts[2].isdigit():
            return
        action, entity_id = parts[1], int(parts[2])
        if action == "open":
            message_id = interaction.message.id if interaction.message else 0
            if not self.repository.panel_message_contains(interaction.guild.id, interaction.channel_id or 0, message_id, entity_id):
                await interaction.response.send_message("このPanelは現在の設定に登録されていません。管理者に確認してください。", ephemeral=True)
                return
            await self.show_open(interaction, entity_id); return
        ticket = self.repository.ticket(entity_id)
        if not ticket or ticket['guild_id'] != interaction.guild.id:
            await interaction.response.send_message("Ticketが見つかりません。", ephemeral=True); return
        if ticket.get('discord_container_id') != interaction.channel_id:
            panel = self.repository.panel(interaction.guild.id, int(ticket['panel_id'])) or {}
            message_id = interaction.message.id if interaction.message else 0
            notification_join = (action == 'join' and ticket['mode'] == 'private_thread'
                and panel.get('staff_notification_channel_id') == interaction.channel_id
                and self.repository.notice_message_recorded(ticket['id'], message_id))
            if not notification_join:
                await interaction.response.send_message("Ticketが見つかりません。", ephemeral=True); return
        if action == "close-reason":
            await interaction.response.send_modal(TicketCloseReasonModal(self, entity_id)); return
        await interaction.response.defer(ephemeral=True)
        if action == "join" and isinstance(interaction.user, discord.Member):
            panel = self.repository.panel(interaction.guild.id, int(ticket["panel_id"]))
            if not await self._staff(interaction.user, panel):
                await interaction.followup.send("Staffだけが参加できます。", ephemeral=True); return
            self.repository.queue_outbox(ticket['id'], 'participant_add', interaction.user.id, {'user_id': interaction.user.id, 'access': 'staff'})
            await interaction.followup.send("Ticketへの参加を予約しました。", ephemeral=True)
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
            self.repository.queue_outbox(ticket['id'], 'awaiting_user', interaction.user.id, {})
            await interaction.followup.send("回答待ちへの変更を予約しました。", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        ticket = self.repository.ticket_for_container(message.channel.id)
        if ticket and ticket["status"] in {"open", "awaiting_user"} and self.transcripts.available:
            attachments = await self._capture_attachments(ticket, message.attachments)
            self.service.record_message(ticket, message.id, message.author.id, str(message.author), message.content,
                attachments, created_at=int(message.created_at.timestamp()))
            if ticket["status"] == "awaiting_user" and message.author.id == int(ticket["opener_id"]) and isinstance(message.channel, discord.TextChannel):
                self.repository.queue_outbox(ticket['id'], 'resume_awaiting', message.author.id, {})

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not after.guild or after.author.bot:
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
        ticket = self.repository.ticket(ticket_id)
        if ticket is None or ticket['guild_id'] != interaction.guild_id:
            await interaction.response.send_message("Ticketが見つかりません。", ephemeral=True)
            return
        self.repository.queue_outbox(ticket_id, 'reopen', interaction.user.id, {})
        await interaction.response.send_message(f"Ticket #{ticket['ticket_number']} の再開を予約しました。", ephemeral=True)

    @ticket.command(name="rename", description="Ticket名を変更します。")
    async def rename(self, interaction: discord.Interaction, name: str) -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0)
        if not ticket or not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("Ticket内で実行してください。", ephemeral=True); return
        panel = self.repository.panel(interaction.guild_id or 0, int(ticket['panel_id']))
        if not isinstance(interaction.user, discord.Member) or not await self._staff(interaction.user, panel):
            await interaction.response.send_message("Staffだけが実行できます。", ephemeral=True); return
        await self.discord.rename(ticket, name)
        await interaction.response.send_message("Ticket名を変更しました。", ephemeral=True)

    @ticket.command(name="add", description="Ticketへユーザーを追加します。")
    async def add(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0)
        if not ticket or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Ticket内で実行してください。", ephemeral=True); return
        panel = self.repository.panel(interaction.guild_id or 0, int(ticket["panel_id"]))
        if not await self._staff(interaction.user, panel):
            await interaction.response.send_message("Staffだけが実行できます。", ephemeral=True); return
        self.repository.queue_outbox(ticket['id'], 'participant_add', interaction.user.id, {'user_id': member.id})
        await interaction.response.send_message("ユーザーの追加を予約しました。", ephemeral=True)

    @ticket.command(name="remove", description="Ticketからユーザーを削除します。")
    async def remove(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ticket = self.repository.ticket_for_container(interaction.channel_id or 0)
        panel = self.repository.panel(interaction.guild_id or 0, int(ticket["panel_id"])) if ticket else None
        if not ticket or not isinstance(interaction.user, discord.Member) or not await self._staff(interaction.user, panel):
            await interaction.response.send_message("StaffだけがTicket内で実行できます。", ephemeral=True); return
        if member.id == int(ticket["opener_id"]):
            await interaction.response.send_message("Ticket作成者は削除できません。", ephemeral=True); return
        self.repository.queue_outbox(ticket['id'], 'participant_remove', interaction.user.id, {'user_id': member.id})
        await interaction.response.send_message("ユーザーの削除を予約しました。", ephemeral=True)

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
        self.repository.queue_outbox(ticket['id'], 'participant_add', interaction.user.id, {'user_id': interaction.user.id, 'access': 'staff'})
        await interaction.response.send_message("Ticketへの参加を予約しました。", ephemeral=True)

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
        self.repository.transfer_panel(ticket["id"], panel_id)
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
        row = self.repository.tag(interaction.guild.id, name)
        if not row:
            await interaction.response.send_message("Tagが見つかりません。", ephemeral=True); return
        await interaction.response.send_message(str(row["content"]), allowed_mentions=discord.AllowedMentions.none())

    async def _reconcile_history(self, ticket: dict[str, Any], channel: discord.TextChannel | discord.Thread) -> None:
        try:
            async for message in self.discord.history(ticket):
                attachments = await self._capture_attachments(ticket, message.attachments)
                self.service.record_message(ticket, message.id, message.author.id, str(message.author), message.content,
                    attachments,
                    kind="system" if message.author.bot else "message", created_at=int(message.created_at.timestamp()))
        except DiscordFailure as exc:
            self.repository.audit(ticket['guild_id'], 'transcript_reconcile_failed', self.bot.user.id if self.bot.user else None,
                                  ticket['id'], {'reason': str(exc)})
            raise

    @tasks.loop(seconds=5)
    async def deliver_outbox(self) -> None:
        await run_batch(self.repository.outbox_jobs, self.owner, self._deliver_outbox_item)

    async def _deliver_outbox_item(self, item: dict) -> Outcome:
        ticket = self.repository.ticket(int(item["ticket_id"]))
        guild = self.bot.get_guild(int(ticket["guild_id"])) if ticket else None
        channel = guild.get_channel_or_thread(int(ticket["discord_container_id"])) if guild and ticket else None
        try:
            action = str(item["action"])
            if action in {'welcome', 'notify_open', 'close_dm', 'close_log', 'remove_open_mentions'}:
                if ticket is None:
                    return Outcome('Ticket unavailable')
                await self.service.deliver_notice(self.discord, ticket, item, str(self.bot.settings.dashboard_base_url or ''))
                return Outcome()
            if action in {'participant_add', 'participant_remove'}:
                if ticket is None:
                    return Outcome('Ticket unavailable')
                await self.service.change_participant(self.discord, ticket, int(item['payload']['user_id']),
                    int(item['actor_id']), add=action == 'participant_add', access=item['payload'].get('access', 'member'))
                return Outcome()
            if action == 'close_resource':
                if ticket is None:
                    return Outcome('Ticket unavailable')
                async def close_resource(owned):
                    current = self.repository.ticket(ticket['id'])
                    if current is None or current['status'] != 'closed' or current['revision'] != item['payload']['revision']:
                        return Outcome('revision_conflict')
                    if self.repository.transcript_for_ticket(current['id']) is None:
                        return Outcome('Transcript unavailable; resource retained')
                    owned.check()
                    await self.discord.set_closed(current, closed=True)
                    return Outcome()
                return await ResourceLease(self.repository.database_url, 'ticket_close', ticket['id']).run(close_resource)
            if action in {"close", "auto_close"}:
                if ticket is None:
                    return Outcome('Ticket unavailable')
                if ticket['status'] != 'closed':
                    if guild is None or not isinstance(channel, (discord.TextChannel, discord.Thread)):
                        raise RuntimeError('Ticket channel unavailable')
                    await self._reconcile_history(ticket, channel)
                    await self.service.close(ticket['id'], int(item['actor_id']), str(item['payload'].get('reason') or 'Close'))
                if self.repository.transcript_for_ticket(ticket['id']) is None:
                    return Outcome('Transcript unavailable; resource retained')
                return Outcome()
            if action in {"claim", "unclaim"}:
                panel = self.repository.panel(int(ticket["guild_id"]), int(ticket["panel_id"])) or {}
                claimant = guild.get_member(int(item["actor_id"])) if action == "claim" and guild else None
                if action == "claim" and claimant is None: raise RuntimeError("Claimant unavailable")
                await self._set_claim(ticket, panel, claimant, item["payload"].get("revision"))
                return Outcome()
            if action == "reopen":
                if ticket is None:
                    return Outcome('Ticket unavailable')
                async def reopen_resource(owned):
                    current = self.repository.ticket(ticket['id'])
                    if current is None or current['mode'] != 'private_thread' or current['status'] not in {'open', 'closed'} or current.get('deleted_at'):
                        return Outcome('reopen_unavailable')
                    owned.check()
                    await self.discord.set_closed(current, closed=False)
                    reopened = current if current['status'] == 'open' else self.repository.reopen_ticket(current['id'], lease=owned)
                    self.service.schedule_ticket(reopened)
                    self.repository.audit(reopened['guild_id'], 'ticket_reopened', int(item['actor_id']), reopened['id'])
                    return Outcome()
                return await ResourceLease(self.repository.database_url, 'ticket_close', ticket['id']).run(reopen_resource)
            if action == "exclude_auto_close":
                self.repository.set_auto_close_excluded(ticket["id"], bool(item["payload"].get("excluded", True)))
                self.service.schedule_ticket(self.repository.ticket(ticket["id"]) or ticket)
                return Outcome()
            if action in {'awaiting_user', 'resume_awaiting'}:
                if ticket is None:
                    return Outcome('Ticket unavailable')
                await self.service.change_category(self.discord, ticket, item)
                return Outcome()
            if action == "delete":
                if ticket is None:
                    return Outcome('Ticket unavailable')
                await self.service.delete_ticket(self.discord, ticket)
                return Outcome()
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                raise RuntimeError("Ticket channel unavailable")
            await self.service.deliver_message(self.discord, ticket, item)
            return Outcome()
        except LostLease as exc:
            return Outcome(str(exc), retry=True)
        except DiscordFailure as exc:
            return Outcome(str(exc), retry=exc.retry or exc.partial)
        except (discord.Forbidden, discord.NotFound) as exc:
            return Outcome(str(exc), retry=False)
        except (RuntimeError, ValueError) as exc:
            retry = str(exc) not in {"revision_conflict", "ticket_not_open", "reopen_unavailable", "claim_unavailable", "opener_removal_forbidden", "awaiting_category_unavailable", "ticket_not_awaiting"}
            return Outcome(str(exc), retry=retry)
        except Exception as exc:
            return Outcome(str(exc), retry=True)

    @tasks.loop(minutes=1)
    async def auto_close(self) -> None:
        self.repository.recover_incomplete_closes()
        self.repository.expire_close_requests()
        await run_batch(self.repository.schedule_jobs, self.owner, self._expire_ticket_schedule, limit=100)

    async def _expire_ticket_schedule(self, schedule: dict) -> Outcome:
        ticket = self.repository.ticket(int(schedule["ticket_id"]))
        if ticket and ticket["status"] == "open" and not ticket.get("auto_close_excluded"):
            self.repository.queue_outbox(ticket["id"], "auto_close", self.bot.user.id if self.bot.user else 0, {"reason": "Auto Close · " + str(schedule["kind"])})
        return Outcome()

    @tasks.loop(seconds=10)
    async def publish_panels(self) -> None:
        for config in self.repository.claim_panel_messages(self.owner, limit=1):
            try:
                await self.panel_delivery.deliver(config)
            except Exception:
                LOGGER.exception("Panel publication requires recovery config=%s", config['id'])

    @tasks.loop(hours=1)
    async def maintain_transcripts(self) -> None:
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
                expiration = self.repository.begin_transcript_expiration(int(item['id']), int(item['ticket_id']))
                if expiration is None:
                    continue
                for attachment in expiration['attachments']:
                    await self.transcripts.delete(str(attachment["backend"]), str(attachment["object_key"]))
                    self.repository.mark_attachment_deleted(int(attachment['id']))
                if not expiration['shared_blob']:
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
            for ticket in self.repository.pending_container_creations(guild.id):
                try:
                    await self.service.recover_creation(self.discord, ticket)
                except Exception:
                    LOGGER.exception("Ticket creation reconciliation failed ticket=%s", ticket['id'])
            for operation in self.repository.pending_claim_changes(guild.id):
                try:
                    await self.service.recover_claim(self.discord, operation)
                except Exception:
                    LOGGER.exception("Ticket claim recovery failed operation=%s", operation['id'])
            for orphan in self.repository.pending_orphans(guild.id):
                try:
                    await self.service.recover_orphan(self.discord, guild.id, orphan['id'])
                except Exception:
                    LOGGER.warning('Ticket orphan recovery requires attention guild=%s orphan=%s', guild.id, orphan['id'], exc_info=True)
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
