"""Guild-scoped AutoMod event adapter and background maintenance."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import discord
import httpx
from discord.ext import commands, tasks

from moderation import AutoModEngine, MessageContext, validate_rule
from moderation.service import ActionContext, ModerationService
from moderation import ModerationRepository
from guild_settings import GuildSettingsRepository


LOGGER = logging.getLogger(__name__)


class AutoModCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.moderation_repository = ModerationRepository(bot.settings.database_path)
        self.guild_settings = GuildSettingsRepository(bot.settings.database_path)
        self.engine = AutoModEngine()
        self.service = ModerationService(bot, self.moderation_repository, self.guild_settings)
        self.http = httpx.AsyncClient(timeout=3)
        self.safe_browsing_limit = asyncio.Semaphore(4)
        self._cache: dict[int, tuple[int, list[dict[str, Any]]]] = {}
        self._locks: dict[tuple[int, int], asyncio.Lock] = {}


    async def cog_load(self) -> None:
        self.maintenance.start()

    async def cog_unload(self) -> None:
        self.maintenance.cancel()
        await self.http.aclose()

    def invalidate(self, guild_id: int) -> None:
        self._cache.pop(guild_id, None)

    def _rules(self, guild_id: int, module: dict[str, Any]) -> list[dict[str, Any]]:
        revision = int(module["settings"].get("rules_revision", 0))
        cached = self._cache.get(guild_id)
        if cached and cached[0] == revision:
            return cached[1]
        rules: list[dict[str, Any]] = []
        for stored in self.moderation_repository.moderation_rules(guild_id, enabled_only=True):
            try:
                normalized = validate_rule(stored)
                normalized.update({key: stored[key] for key in ("id", "revision")})
                rules.append(normalized)
            except ValueError:
                LOGGER.warning("Skipping invalid AutoMod rule %s in guild %s", stored.get("id"), guild_id, exc_info=True)
        self._cache[guild_id] = (revision, rules)
        return rules

    async def _unsafe_url(self, urls: list[str]) -> str | None:
        api_key = self.bot.settings.google_safe_browsing_api_key
        if not api_key:
            return None
        pending: list[tuple[str, str]] = []
        for url in dict.fromkeys(filter(None, (self._normalize_url(item) for item in urls[:5]))):
            digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
            cached = self.moderation_repository.cached_url_result(digest)
            if cached is True:
                return url
            if cached is None:
                pending.append((url, digest))
        if not pending:
            return None
        payload = {"client": {"clientId": "tueka", "clientVersion": "2"}, "threatInfo": {
            "threatTypes": ["SOCIAL_ENGINEERING", "MALWARE", "UNWANTED_SOFTWARE"], "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"], "threatEntries": [{"url": url} for url, _ in pending]}}
        try:
            async with self.safe_browsing_limit:
                response = await self.http.post("https://safebrowsing.googleapis.com/v4/threatMatches:find", params={"key": api_key}, json=payload)
                response.raise_for_status()
            unsafe_urls = {item.get("threat", {}).get("url") for item in response.json().get("matches", [])}
            for url, digest in pending:
                unsafe = url in unsafe_urls
                self.moderation_repository.cache_url_result(digest, unsafe)
                if unsafe:
                    return url
        except (httpx.HTTPError, ValueError):
            LOGGER.warning("Safe Browsing lookup failed open", exc_info=True)
        return None

    @staticmethod
    def _normalize_url(url: str) -> str | None:
        try:
            value = url.strip().rstrip(".,;:!?)]}")
            value = value if "://" in value else f"https://{value}"
            parts = urlsplit(value)
            if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
                return None
            host = parts.hostname.rstrip(".").lower().encode("idna").decode("ascii")
            port = parts.port
            netloc = host if port is None or (parts.scheme.lower(), port) in {("http", 80), ("https", 443)} else f"{host}:{port}"
            return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))
        except (ValueError, UnicodeError):
            return None

    @staticmethod
    def _context(message: discord.Message, *, edited: bool = False) -> MessageContext:
        member = message.author if isinstance(message.author, discord.Member) else None
        channel = message.channel
        category_id = getattr(channel, "category_id", None)
        if category_id is None and isinstance(channel, discord.Thread):
            category_id = getattr(channel.parent, "category_id", None)
        return MessageContext(
            guild_id=message.guild.id, user_id=message.author.id, channel_id=channel.id, content=message.content or "",
            category_id=category_id, role_ids={role.id for role in member.roles} if member else set(),
            mention_count=len({item.id for item in message.mentions}) + len({item.id for item in message.role_mentions}),
            attachment_count=len(message.attachments), sticker_count=len(message.stickers), account_created_at=message.author.created_at,
            joined_at=member.joined_at if member else None,
            actor_kind="webhook" if message.webhook_id is not None else "bot" if message.author.bot else "human",
            webhook_id=message.webhook_id, event_type="message_edit" if edited else "message_create", target_id=message.id,
        )

    async def _process(self, message: discord.Message, *, edited: bool = False) -> None:
        if message.guild is None:
            return
        module = self.guild_settings.get_module(message.guild.id, "moderation")
        if not module["enabled"] or isinstance(message.author, discord.Member) and message.author.guild_permissions.administrator:
            return
        context = self._context(message, edited=edited)
        if self.engine.globally_exempt(context, module["settings"]):
            return
        rules = self._rules(message.guild.id, module)
        if not rules:
            return
        key = (message.guild.id, message.author.id)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            matches = await self.engine.evaluate(context, rules, edited=edited, unsafe_url_checker=self._unsafe_url)
            for match in matches:
                family_module = self.guild_settings.get_module(message.guild.id, match.rule["family"])
                if not family_module["enabled"]:
                    continue
                if self.engine.globally_exempt(context, family_module["settings"]):
                    continue
                excluded = message.channel.id in set(module["settings"].get("evidence_excluded_channel_ids", []))
                evidence = None if excluded else (message.content or "")[:1000]
                attachments = [] if excluded else [{"filename": item.filename[:255], "content_type": item.content_type, "size": item.size} for item in message.attachments[:10]]
                event_id = self.moderation_repository.create_moderation_event(message.guild.id, family=match.rule["family"], event_type=context.event_type,
                    source=match.rule["family"], reason=match.reason, rule_id=match.rule.get("id"), actor_id=message.author.id,
                    actor_kind=context.actor_kind, target_user_id=message.author.id, channel_id=message.channel.id, target_id=message.id,
                    evidence_text=evidence, evidence={"attachments": attachments, "details": match.details}, mode=match.rule["mode"],
                    retention_days=int(module["settings"].get("evidence_retention_days", 30)),
                    dedupe_key=f"{context.event_type}:{message.id}:{match.rule.get('id')}")
                if event_id is None:
                    continue
                action_context = ActionContext(message.guild, message.author if isinstance(message.author, discord.Member) else None, message, message.channel, actor=message.author)
                results = await self.service.execute_actions(action_context, match.rule, match.reason, event_id, family_module["settings"])
                self.moderation_repository.finish_moderation_event(event_id, results)
                await self.service.log_event(action_context, match.rule, event_id, match.reason, results, family_module["settings"])
        if len(self._locks) > 5000:
            self._locks = {item_key: item for item_key, item in self._locks.items() if item.locked()}

    async def _process_signal(self, context: MessageContext, guild: discord.Guild, member: discord.Member | None,
            action_context: ActionContext, *, dedupe_target: str, evidence: dict[str, Any] | None = None) -> None:
        core = self.guild_settings.get_module(guild.id, "moderation")
        if not core["enabled"] or member and member.guild_permissions.administrator or self.engine.globally_exempt(context, core["settings"]):
            return
        rules = self._rules(guild.id, core)
        key = (guild.id, context.user_id)
        async with self._locks.setdefault(key, asyncio.Lock()):
            matches = await self.engine.evaluate(context, rules)
            for match in matches:
                family_module = self.guild_settings.get_module(guild.id, match.rule["family"])
                if not family_module["enabled"] or self.engine.globally_exempt(context, family_module["settings"]):
                    continue
                event_id = self.moderation_repository.create_moderation_event(guild.id, family=match.rule["family"], event_type=context.event_type,
                    source=match.rule["family"], reason=match.reason, rule_id=match.rule.get("id"), actor_id=context.user_id,
                    actor_kind=context.actor_kind, target_user_id=member.id if member else context.user_id,
                    channel_id=context.channel_id or None, target_id=context.target_id, evidence=evidence or {"details": match.details},
                    mode=match.rule["mode"], retention_days=int(core["settings"].get("evidence_retention_days", 30)),
                    dedupe_key=f"{context.event_type}:{dedupe_target}:{match.rule.get('id')}")
                if event_id is None:
                    continue
                results = await self.service.execute_actions(action_context, match.rule, match.reason, event_id, family_module["settings"])
                self.moderation_repository.finish_moderation_event(event_id, results)
                await self.service.log_event(action_context, match.rule, event_id, match.reason, results, family_module["settings"])
                if match.rule["family"] == "anti_raid":
                    lockdown_id = next((item.get("lockdown_id") for item in results if item.get("lockdown_id")), None)
                    self.moderation_repository.set_raid_state(guild.id, True, source_rule_id=match.rule.get("id"), lockdown_id=lockdown_id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        await self._process(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.content != after.content:
            await self._process(after, edited=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        channel = guild.get_channel(payload.channel_id) if guild else None
        if guild is None or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        member = payload.member or guild.get_member(payload.user_id)
        if member is None:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
        reaction = next((item for item in message.reactions if str(item.emoji) == str(payload.emoji)), None)
        context = MessageContext(guild.id, member.id, channel.id, category_id=getattr(channel, "category_id", None),
            role_ids={role.id for role in member.roles}, reaction_count=1, target_id=message.id,
            actor_kind="bot" if member.bot else "human", event_type="reaction_add",
            account_created_at=member.created_at, joined_at=member.joined_at)
        await self._process_signal(context, guild, member, ActionContext(guild, member, message, channel, reaction, member),
            dedupe_target=f"{message.id}:{member.id}:{payload.emoji}:{int(time.time() // 2)}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        context = MessageContext(member.guild.id, member.id, 0, role_ids={role.id for role in member.roles},
            actor_kind="bot" if member.bot else "human", event_type="member_join", target_id=member.id,
            account_created_at=member.created_at, joined_at=member.joined_at)
        joined_key = int(member.joined_at.timestamp()) if member.joined_at else int(time.time())
        await self._process_signal(context, member.guild, member, ActionContext(member.guild, member, actor=member),
            dedupe_target=f"{member.id}:{joined_key}", evidence={"account_created_at": member.created_at.isoformat()})

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        context = MessageContext(member.guild.id, member.id, 0, role_ids={role.id for role in member.roles},
            actor_kind="bot" if member.bot else "human", event_type="member_remove", target_id=member.id,
            account_created_at=member.created_at, joined_at=member.joined_at)
        await self._process_signal(context, member.guild, member, ActionContext(member.guild, member, actor=member),
            dedupe_target=f"{member.id}:{int(time.time() // 2)}")

    @tasks.loop(seconds=60)
    async def maintenance(self) -> None:
        self.moderation_repository.purge_moderation_evidence()
        self.engine.prune()
        for pending in self.moderation_repository.due_moderation_actions():
            guild = self.bot.get_guild(int(pending["guild_id"]))
            if guild is None:
                continue
            try:
                if pending["action"] == "unban":
                    await guild.unban(discord.Object(id=int(pending["user_id"])), reason="一時Banの期限切れ")
                self.moderation_repository.complete_moderation_action(int(pending["id"]))
            except discord.NotFound:
                self.moderation_repository.complete_moderation_action(int(pending["id"]))
            except (discord.Forbidden, discord.HTTPException) as exc:
                self.moderation_repository.complete_moderation_action(int(pending["id"]), str(exc))
        for pending in self.moderation_repository.due_lockdowns():
            guild = self.bot.get_guild(int(pending["guild_id"]))
            if guild is None:
                continue
            try:
                await self.service.unlock_lockdown(guild, int(pending["id"]))
            except (discord.Forbidden, discord.HTTPException) as exc:
                LOGGER.warning("Lockdown restore failed for guild %s: %s", guild.id, exc)
        for raid in self.moderation_repository.stale_raid_states(int(time.time()) - 300):
            guild_id = int(raid["guild_id"])
            self.moderation_repository.set_raid_state(guild_id, False)
            self.moderation_repository.create_moderation_event(guild_id, family="anti_raid", event_type="member_join",
                source="raid_state", reason="5分間シグナルがなかったためRaid状態を自動解除しました", mode="monitor",
                dedupe_key=f"raid-clear:{guild_id}:{raid['last_signal_at']}")
        for request in self.moderation_repository.pending_moderation_actions():
            await self._execute_requested_action(request)

    async def _execute_requested_action(self, request: dict[str, Any]) -> None:
        guild = self.bot.get_guild(int(request["guild_id"]))
        if guild is None:
            return
        action = str(request["action"])
        moderator = guild.get_member(int(request["moderator_id"]))
        member = guild.get_member(int(request["target_user_id"])) if request.get("target_user_id") else None
        channel = guild.get_channel(int(request["channel_id"])) if request.get("channel_id") else None
        reason = str(request.get("reason") or "Dashboard moderation action")
        event_id = self.moderation_repository.create_moderation_event(guild.id, family="infraction", event_type="infraction_change", source="dashboard",
            reason=reason, actor_id=request["moderator_id"], actor_kind="human", target_user_id=request.get("target_user_id"),
            channel_id=request.get("channel_id"), target_id=request["id"], dedupe_key=f"action-request:{request['id']}")
        if event_id is None:
            self.moderation_repository.complete_moderation_request(int(request["id"]), result={"status": "duplicate"})
            return
        try:
            if not self.guild_settings.module_enabled(guild.id, "moderation"):
                raise PermissionError("Moderationが無効です")
            if moderator is None or not moderator.guild_permissions.administrator:
                raise PermissionError("実行者のAdministrator権限を再確認できません")
            if action == "warn":
                if member is None:
                    raise ValueError("対象メンバーが見つかりません")
                await self.service.warn(guild, member, reason, int(request["moderator_id"]), actor=moderator)
                results = [{"type": action, "status": "success"}]
            elif action == "unban":
                if not request.get("target_user_id"):
                    raise ValueError("対象ユーザーIDが必要です")
                await guild.unban(discord.Object(id=int(request["target_user_id"])), reason=reason)
                results = [{"type": action, "status": "success"}]
            else:
                if action in {"timeout", "untimeout", "kick", "ban", "softban", "points"}:
                    if member is None:
                        raise ValueError("対象メンバーが見つかりません")
                    if action != "points":
                        hierarchy_error = self.service.manageable(moderator, member, action)
                        if hierarchy_error:
                            raise PermissionError(hierarchy_error)
                options = request["options"]
                action_value: dict[str, Any] = {"type": action}
                if action in {"timeout", "tempban"}:
                    action_value["duration_minutes"] = int(options.get("duration_minutes", 10))
                elif action == "purge":
                    action_value["count"] = int(options.get("count", 10))
                elif action == "lockdown":
                    action_value["duration_minutes"] = int(options.get("duration_minutes", 30))
                elif action == "points":
                    action_value.update({"points": int(options.get("points",1)), "expires_days": int(options.get("expires_days",30))})
                rule = {"id": None, "family": "infraction", "name": "Dashboard action", "mode": "enforce", "actions": [action_value]}
                results = await self.service.execute_actions(ActionContext(guild, member, channel=channel, actor=moderator), rule, reason, event_id, {})
            self.moderation_repository.finish_moderation_event(event_id, results)
            failed = any(item.get("status") == "failed" for item in results)
            self.moderation_repository.complete_moderation_request(int(request["id"]), result={"event_id": event_id, "actions": results}, failed=failed)
        except (ValueError, PermissionError, discord.Forbidden, discord.HTTPException) as exc:
            results = [{"type": action, "status": "failed", "error": str(exc)[:300]}]
            self.moderation_repository.finish_moderation_event(event_id, results)
            self.moderation_repository.complete_moderation_request(int(request["id"]), result={"event_id": event_id, "actions": results}, failed=True)

    @maintenance.before_loop
    async def before_maintenance(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoModCog(bot))
