"""Native reaction-based self-role workflow."""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
import unicodedata
from collections import defaultdict
from typing import Any

from jobs import Outcome, run_batch

import discord
from discord import app_commands
from discord.ext import commands, tasks

from reaction_roles import BEHAVIOR_TYPES, ReactionRoleRepository, ReactionRoleService, ReactionRoleValidationError, default_message, normalize_emoji


LOGGER = logging.getLogger(__name__)


def _emoji_key(emoji: discord.PartialEmoji | str) -> str:
    if isinstance(emoji, discord.PartialEmoji) and emoji.id:
        return f"custom:{emoji.id}"
    return f"unicode:{unicodedata.normalize('NFC', str(emoji))}"


class AddManyModal(discord.ui.Modal, title="EmojiとRoleをまとめて追加"):
    pairs = discord.ui.TextInput(label="1行に Emoji と Role ID", style=discord.TextStyle.paragraph,
        placeholder="🎮 123456789012345678\n🎨 234567890123456789", min_length=3, max_length=4000)

    def __init__(self, cog: "ReactionRolesCog", config_id: int) -> None:
        super().__init__(); self.cog, self.config_id = cog, config_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        errors: list[str] = []; pairs: list[tuple[str, int]] = []
        for index, line in enumerate(str(self.pairs.value).splitlines(), 1):
            parts = line.strip().rsplit(maxsplit=1)
            try:
                if len(parts) != 2: raise ValueError
                normalize_emoji(parts[0]); role_id = int(parts[1].strip("<@&>")); pairs.append((parts[0], role_id))
            except (ValueError, ReactionRoleValidationError): errors.append(f"{index}行目: EmojiとRole IDを確認してください。")
        if errors:
            await interaction.response.send_message("\n".join(errors[:10]), ephemeral=True); return
        await self.cog.add_many(interaction, self.config_id, pairs)


class ConfirmPurgeView(discord.ui.View):
    def __init__(self, cog: "ReactionRolesCog", guild_id: int, actor_id: int) -> None:
        super().__init__(timeout=30); self.cog, self.guild_id, self.actor_id = cog, guild_id, actor_id

    @discord.ui.button(label="すべて削除", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.actor_id:
            await interaction.response.send_message("この確認は実行者だけが使用できます。", ephemeral=True); return
        count = 0
        for item in self.cog.repository.messages(self.guild_id):
            self.cog.repository.queue_action(self.guild_id, item["id"], "delete", {"channel_id":item["channel_id"],"message_id":item.get("message_id"),"source":item["source"]})
            self.cog.repository.delete_message(self.guild_id, item["id"], recoverable=False, actor_id=self.actor_id); count += 1
        await interaction.response.edit_message(content=f"{count}件のReaction Role設定を削除しました。", view=None)


class ReactionRolesCog(commands.Cog):
    reactionrole = app_commands.Group(name="reactionrole", description="Reaction Rolesを管理します")
    short = app_commands.Group(name="r", description="Reaction Rolesの短縮操作")
    modify = app_commands.Group(name="modify", description="Typeと制約", parent=reactionrole)
    whitelist = app_commands.Group(name="whitelist", description="利用を許可するRole", parent=reactionrole)
    blacklist = app_commands.Group(name="blacklist", description="利用を拒否するRole", parent=reactionrole)
    link = app_commands.Group(name="link", description="複数メッセージの選択を連携", parent=reactionrole)
    manage = app_commands.Group(name="manage", description="メッセージの保守", parent=reactionrole)

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repository = ReactionRoleRepository(bot.settings.database_path)
        self.service = ReactionRoleService(self.repository, max_mappings=bot.settings.reaction_role_max_mappings_per_message)
        self.owner = f"rr:{socket.gethostname()}:{os.getpid()}"
        self._locks: defaultdict[tuple[int, int, int], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._role_locks: defaultdict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._dm_recent: dict[tuple[int, int, str], float] = {}
        self.process_outbox.start(); self.process_schedules.start(); self.maintenance.start()

    def cog_unload(self) -> None:
        self.process_outbox.cancel(); self.process_schedules.cancel(); self.maintenance.cancel()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_guild:
            if not interaction.response.is_done(): await interaction.response.send_message("Manage Server権限が必要です。", ephemeral=True)
            return False
        return True

    def _config(self, guild_id: int, config_id: int) -> dict[str, Any]:
        config = self.repository.message(guild_id, config_id)
        if not config: raise ReactionRoleValidationError("not_found", "Reaction Role設定が見つかりません。")
        return config

    @staticmethod
    def _editable(config: dict[str, Any]) -> dict[str, Any]:
        return {key: config.get(key) for key in default_message()}

    @staticmethod
    def _validate_guild_emojis(interaction: discord.Interaction, value: dict[str, Any]) -> None:
        allowed_ids = {emoji.id for emoji in interaction.guild.emojis} if interaction.guild else set()
        for index, mapping in enumerate(value.get("mappings", [])):
            normalized = normalize_emoji(str(mapping.get("emoji") or ""))
            if normalized["emoji_id"] is not None and normalized["emoji_id"] not in allowed_ids:
                raise ReactionRoleValidationError(
                    "emoji_invalid",
                    "標準絵文字またはこのサーバーの絵文字を選択してください。",
                    f"mappings.{index}.emoji",
                )

    async def _save_edit(self, interaction: discord.Interaction, config: dict[str, Any], value: dict[str, Any]) -> None:
        try:
            self._validate_guild_emojis(interaction, value)
            updated = self.service.update(interaction.guild_id, config["id"], value, config["revision"], interaction.user.id)
            await interaction.response.send_message(f"{updated['name']} を更新しました。", ephemeral=True)
        except ReactionRoleValidationError as exc:
            await interaction.response.send_message(exc.message, ephemeral=True)

    @reactionrole.command(name="create", description="Bot投稿または既存メッセージへReaction Rolesを作成します")
    @app_commands.describe(channel="対象チャンネル", message_id="既存メッセージID。未指定ならBotが投稿", title="パネルタイトル")
    async def create_command(self, interaction: discord.Interaction, channel: discord.TextChannel, emoji: str, role: discord.Role, title: str = "ロールを選択", message_id: str | None = None) -> None:
        value = default_message(); value.update({"channel_id": channel.id, "source": "external" if message_id else "bot", "message_id": int(message_id) if message_id else None})
        value["embed"]["title"] = title; value["mappings"]=[{"emoji":emoji,"role_id":role.id}]
        try:
            self._validate_guild_emojis(interaction, value)
            created=self.service.create(interaction.guild_id,value,interaction.user.id);await interaction.response.send_message(f"Reaction Role #{created['id']} を作成しました。",ephemeral=True)
        except ReactionRoleValidationError as exc:await interaction.response.send_message(exc.message,ephemeral=True)

    @reactionrole.command(name="add", description="EmojiとRoleの対応を追加します")
    async def add_command(self, interaction: discord.Interaction, config_id: int, emoji: str, role: discord.Role) -> None:
        await self.add_many(interaction, config_id, [(emoji, role.id)])

    async def add_many(self, interaction: discord.Interaction, config_id: int, pairs: list[tuple[str, int]]) -> None:
        config=self._config(interaction.guild_id,config_id); value=self._editable(config); value["mappings"]=[{"emoji":item["emoji"],"role_id":item["role_id"],"max_members":item.get("max_members")} for item in config["mappings"]]
        value["mappings"].extend({"emoji":emoji,"role_id":role_id} for emoji,role_id in pairs)
        await self._save_edit(interaction,config,value)

    @reactionrole.command(name="addmany", description="複数のEmojiとRoleをまとめて追加します")
    async def addmany_command(self, interaction: discord.Interaction, config_id: int) -> None:
        await interaction.response.send_modal(AddManyModal(self,config_id))

    @reactionrole.command(name="remove", description="Roleの対応を削除します")
    async def remove_command(self, interaction: discord.Interaction, config_id: int, role: discord.Role) -> None:
        config=self._config(interaction.guild_id,config_id); value=self._editable(config); value["mappings"]=[{"emoji":item["emoji"],"role_id":item["role_id"],"max_members":item.get("max_members")} for item in config["mappings"] if item["role_id"]!=role.id]
        await self._save_edit(interaction,config,value)

    @reactionrole.command(name="purge", description="Reaction Role設定を削除します")
    async def purge_command(self, interaction: discord.Interaction, config_id: int | None = None) -> None:
        if config_id is None:
            await interaction.response.send_message("サーバー内のすべてのReaction Role設定を削除します。30秒以内に確認してください。",view=ConfirmPurgeView(self,interaction.guild_id,interaction.user.id),ephemeral=True); return
        config=self._config(interaction.guild_id,config_id); self.repository.queue_action(interaction.guild_id,config_id,"delete",{"channel_id":config["channel_id"],"message_id":config.get("message_id"),"source":config["source"]}); self.repository.delete_message(interaction.guild_id,config_id,recoverable=False,actor_id=interaction.user.id)
        await interaction.response.send_message(f"{config['name']} を削除しました。",ephemeral=True)

    @modify.command(name="type", description="動作Typeを変更します")
    @app_commands.choices(behavior=[app_commands.Choice(name=item,value=item) for item in sorted(BEHAVIOR_TYPES)])
    async def type_command(self, interaction: discord.Interaction, config_id: int, behavior: app_commands.Choice[str], duration_minutes: int | None = None) -> None:
        config=self._config(interaction.guild_id,config_id); value=self._editable(config); value["behavior_type"]=behavior.value; value["temp_duration_seconds"]=duration_minutes*60 if behavior.value=="temp" and duration_minutes else None
        await self._save_edit(interaction,config,value)

    @modify.command(name="limit", description="ユーザーごとの選択上限を変更します")
    async def limit_command(self,interaction:discord.Interaction,config_id:int,limit:int)->None:
        config=self._config(interaction.guild_id,config_id);value=self._editable(config);value["selection_limit"]=limit;await self._save_edit(interaction,config,value)

    @modify.command(name="maxroles", description="Roleの実人数上限を変更します")
    async def maxroles_command(self,interaction:discord.Interaction,config_id:int,role:discord.Role,maximum:int)->None:
        config=self._config(interaction.guild_id,config_id);value=self._editable(config);value["mappings"]=[{"emoji":item["emoji"],"role_id":item["role_id"],"max_members":maximum if item["role_id"]==role.id else item.get("max_members")} for item in config["mappings"]];await self._save_edit(interaction,config,value)

    @modify.command(name="lock", description="Role変更を停止します")
    async def lock_command(self,interaction:discord.Interaction,config_id:int)->None:
        config=self._config(interaction.guild_id,config_id);value=self._editable(config);value["locked"]=True;await self._save_edit(interaction,config,value)

    @modify.command(name="unlock", description="Role変更を再開します")
    async def unlock_command(self,interaction:discord.Interaction,config_id:int)->None:
        config=self._config(interaction.guild_id,config_id);value=self._editable(config);value["locked"]=False;await self._save_edit(interaction,config,value)

    async def _access(self,interaction:discord.Interaction,config_id:int,policy:str,operation:str,role:discord.Role|None)->None:
        config=self._config(interaction.guild_id,config_id);value=self._editable(config);key=f"{policy}_role_ids";values=list(config[key])
        if operation=="add" and role and role.id not in values:values.append(role.id)
        elif operation=="remove" and role:values=[item for item in values if item!=role.id]
        elif operation=="clear":values=[]
        value[key]=values;await self._save_edit(interaction,config,value)

    @whitelist.command(name="add")
    async def wl_add(self,interaction:discord.Interaction,config_id:int,role:discord.Role)->None:await self._access(interaction,config_id,"whitelist","add",role)
    @whitelist.command(name="remove")
    async def wl_remove(self,interaction:discord.Interaction,config_id:int,role:discord.Role)->None:await self._access(interaction,config_id,"whitelist","remove",role)
    @whitelist.command(name="clear")
    async def wl_clear(self,interaction:discord.Interaction,config_id:int)->None:await self._access(interaction,config_id,"whitelist","clear",None)
    @blacklist.command(name="add")
    async def bl_add(self,interaction:discord.Interaction,config_id:int,role:discord.Role)->None:await self._access(interaction,config_id,"blacklist","add",role)
    @blacklist.command(name="remove")
    async def bl_remove(self,interaction:discord.Interaction,config_id:int,role:discord.Role)->None:await self._access(interaction,config_id,"blacklist","remove",role)
    @blacklist.command(name="clear")
    async def bl_clear(self,interaction:discord.Interaction,config_id:int)->None:await self._access(interaction,config_id,"blacklist","clear",None)

    @link.command(name="create")
    async def link_create(self,interaction:discord.Interaction,name:str,message_ids:str)->None:
        try: group=self.repository.create_link_group(interaction.guild_id,name,[int(item.strip()) for item in message_ids.split(",") if item.strip()]);await interaction.response.send_message(f"Link Group #{group['id']} を作成しました。",ephemeral=True)
        except ValueError:await interaction.response.send_message("2件以上の互換性がある未Link設定を指定してください。",ephemeral=True)
    @link.command(name="list")
    async def link_list(self,interaction:discord.Interaction)->None:
        groups=self.repository.link_groups(interaction.guild_id);await interaction.response.send_message("\n".join(f"#{item['id']} {item['name']}: {', '.join(map(str,item['message_ids']))}" for item in groups) or "Link Groupはありません。",ephemeral=True)
    @link.command(name="unlink")
    async def link_unlink(self,interaction:discord.Interaction,group_id:int)->None:
        self.repository.dissolve_link_group(interaction.guild_id,group_id);await interaction.response.send_message("Link Group全体を解除しました。",ephemeral=True)

    @manage.command(name="show")
    async def show_command(self,interaction:discord.Interaction,config_id:int)->None:
        config=self._config(interaction.guild_id,config_id);lines=[f"{item['emoji']} → <@&{item['role_id']}>" for item in config["mappings"]];await interaction.response.send_message(f"**{config['name']}** · {config['behavior_type']}\n"+"\n".join(lines),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    @manage.command(name="fix")
    async def fix_command(self,interaction:discord.Interaction,config_id:int)->None:self.repository.queue_action(interaction.guild_id,config_id,"fix",{});await interaction.response.send_message("修復をキューへ登録しました。",ephemeral=True)
    @manage.command(name="fixforeign")
    async def fixforeign_command(self,interaction:discord.Interaction,config_id:int)->None:self.repository.queue_action(interaction.guild_id,config_id,"fix",{"foreign":True});await interaction.response.send_message("既存リアクションを使って修復します。",ephemeral=True)
    @manage.command(name="edit")
    async def edit_command(self,interaction:discord.Interaction,config_id:int,title:str,description:str="")->None:
        config=self._config(interaction.guild_id,config_id)
        if config["source"]!="bot":await interaction.response.send_message("Bot以外の投稿は編集できません。",ephemeral=True);return
        value=self._editable(config);value["embed"]={**config["embed"],"title":title,"description":description};await self._save_edit(interaction,config,value)
    @manage.command(name="color")
    async def color_command(self,interaction:discord.Interaction,config_id:int,color:str)->None:
        config=self._config(interaction.guild_id,config_id);value=self._editable(config);value["embed"]={**config["embed"],"color":color};await self._save_edit(interaction,config,value)
    @manage.command(name="move")
    async def move_command(self,interaction:discord.Interaction,config_id:int,channel:discord.TextChannel,message_id:str)->None:
        config=self._config(interaction.guild_id,config_id)
        try:
            target=await channel.fetch_message(int(message_id))
            for mapping in config["mappings"]:await target.add_reaction(mapping["emoji"])
            old_channel=interaction.guild.get_channel(config["channel_id"]);old_message_id=config.get("message_id")
            self.repository.move_message(interaction.guild_id,config_id,channel.id,target.id,"bot" if self.bot.user and target.author.id==self.bot.user.id else "external",config["revision"],interaction.user.id)
            if config["source"]=="bot" and old_message_id and isinstance(old_channel,(discord.TextChannel,discord.Thread)):
                try:old=await old_channel.fetch_message(old_message_id);await old.delete()
                except discord.HTTPException:self.repository.audit(interaction.guild_id,config_id,"move_cleanup","partial",actor_id=interaction.user.id,reason="old_message_delete_failed")
            await interaction.response.send_message("設定を新しいメッセージへ移動しました。",ephemeral=True)
        except (ValueError,discord.HTTPException):await interaction.response.send_message("移動先メッセージとBot権限を確認してください。",ephemeral=True)
    @manage.command(name="selfdestruct")
    async def selfdestruct_command(self,interaction:discord.Interaction,config_id:int,minutes:int)->None:
        config=self._config(interaction.guild_id,config_id)
        if config["source"]!="bot":await interaction.response.send_message("Bot以外の投稿にはSelfdestructを設定できません。",ephemeral=True);return
        if not 5<=minutes<=525600:await interaction.response.send_message("期限は5分～365日で指定してください。",ephemeral=True);return
        value=self._editable(config);value["self_destruct_at"]=int(time.time())+minutes*60;await self._save_edit(interaction,config,value)
    @manage.command(name="reset-binding")
    async def reset_binding_command(self,interaction:discord.Interaction,config_id:int,user:discord.Member)->None:
        changed=self.repository.reset_binding(config_id,user.id);await interaction.response.send_message("選択履歴を解除しました。" if changed else "選択履歴はありません。",ephemeral=True)

    @reactionrole.command(name="channel",description="Reaction Roles専用チャンネルを作成します")
    async def channel_command(self,interaction:discord.Interaction,name:str="roles")->None:
        guild=interaction.guild;me=guild.me
        if not me or not me.guild_permissions.manage_channels:await interaction.response.send_message("BotにManage Channels権限が必要です。",ephemeral=True);return
        overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=True,read_message_history=True,add_reactions=True,send_messages=False),me:discord.PermissionOverwrite(view_channel=True,read_message_history=True,add_reactions=True,send_messages=True,manage_messages=True)}
        channel=await guild.create_text_channel(name[:100],overwrites=overwrites,reason=f"Reaction Roles channel by {interaction.user}");await interaction.response.send_message(f"{channel.mention} を作成しました。",ephemeral=True)

    @reactionrole.command(name="aio",description="投稿とEmoji→Role対応を一括作成します")
    async def aio_command(self,interaction:discord.Interaction,channel:discord.TextChannel,emoji:str,role:discord.Role,behavior:str="normal",title:str="ロールを選択")->None:
        if behavior not in BEHAVIOR_TYPES:await interaction.response.send_message("Typeを確認してください。",ephemeral=True);return
        value=default_message();value.update({"channel_id":channel.id,"behavior_type":behavior});value["embed"]["title"]=title;value["mappings"]=[{"emoji":emoji,"role_id":role.id}]
        if behavior=="temp":value["temp_duration_seconds"]=3600
        try:self._validate_guild_emojis(interaction,value);created=self.service.create(interaction.guild_id,value,interaction.user.id);await interaction.response.send_message(f"Reaction Role #{created['id']} を作成しました。",ephemeral=True)
        except ReactionRoleValidationError as exc:await interaction.response.send_message(exc.message,ephemeral=True)

    @short.command(name="show")
    async def short_show(self,interaction:discord.Interaction,config_id:int)->None:await self.show_command.callback(self,interaction,config_id)
    @short.command(name="fix")
    async def short_fix(self,interaction:discord.Interaction,config_id:int)->None:await self.fix_command.callback(self,interaction,config_id)
    @short.command(name="add")
    async def short_add(self,interaction:discord.Interaction,config_id:int,emoji:str,role:discord.Role)->None:await self.add_many(interaction,config_id,[(emoji,role.id)])
    @short.command(name="addmany")
    async def short_addmany(self,interaction:discord.Interaction,config_id:int)->None:await interaction.response.send_modal(AddManyModal(self,config_id))
    @short.command(name="remove")
    async def short_remove(self,interaction:discord.Interaction,config_id:int,role:discord.Role)->None:
        config=self._config(interaction.guild_id,config_id);value=self._editable(config);value["mappings"]=[{"emoji":item["emoji"],"role_id":item["role_id"],"max_members":item.get("max_members")} for item in config["mappings"] if item["role_id"]!=role.id];await self._save_edit(interaction,config,value)
    async def _short_aio(self,interaction:discord.Interaction,channel:discord.TextChannel,emoji:str,role:discord.Role,behavior:str)->None:
        value=default_message();value.update({"channel_id":channel.id,"behavior_type":behavior,"selection_limit":1 if behavior in {"unique","binding"} else None});value["mappings"]=[{"emoji":emoji,"role_id":role.id}]
        try:self._validate_guild_emojis(interaction,value);created=self.service.create(interaction.guild_id,value,interaction.user.id);await interaction.response.send_message(f"Reaction Role #{created['id']} を作成しました。",ephemeral=True)
        except ReactionRoleValidationError as exc:await interaction.response.send_message(exc.message,ephemeral=True)
    @short.command(name="aio")
    async def short_aio(self,interaction:discord.Interaction,channel:discord.TextChannel,emoji:str,role:discord.Role)->None:await self._short_aio(interaction,channel,emoji,role,"normal")
    @short.command(name="aiou")
    async def short_aiou(self,interaction:discord.Interaction,channel:discord.TextChannel,emoji:str,role:discord.Role)->None:await self._short_aio(interaction,channel,emoji,role,"unique")
    @short.command(name="aiov")
    async def short_aiov(self,interaction:discord.Interaction,channel:discord.TextChannel,emoji:str,role:discord.Role)->None:await self._short_aio(interaction,channel,emoji,role,"verify")
    @short.command(name="aioi")
    async def short_aioi(self,interaction:discord.Interaction,channel:discord.TextChannel,emoji:str,role:discord.Role)->None:await self._short_aio(interaction,channel,emoji,role,"binding")
    @short.command(name="normal")
    async def short_normal(self,interaction:discord.Interaction,config_id:int)->None:await self._set_short_type(interaction,config_id,"normal")
    @short.command(name="unique")
    async def short_unique(self,interaction:discord.Interaction,config_id:int)->None:await self._set_short_type(interaction,config_id,"unique")
    @short.command(name="verify")
    async def short_verify(self,interaction:discord.Interaction,config_id:int)->None:await self._set_short_type(interaction,config_id,"verify")
    @short.command(name="binding")
    async def short_binding(self,interaction:discord.Interaction,config_id:int)->None:await self._set_short_type(interaction,config_id,"binding")
    @short.command(name="drop")
    async def short_drop(self,interaction:discord.Interaction,config_id:int)->None:await self._set_short_type(interaction,config_id,"drop")
    @short.command(name="reversed")
    async def short_reversed(self,interaction:discord.Interaction,config_id:int)->None:await self._set_short_type(interaction,config_id,"reversed")
    @short.command(name="lock")
    async def short_lock(self,interaction:discord.Interaction,config_id:int)->None:
        config=self._config(interaction.guild_id,config_id);value=self._editable(config);value["locked"]=True;await self._save_edit(interaction,config,value)
    @short.command(name="unlock")
    async def short_unlock(self,interaction:discord.Interaction,config_id:int)->None:
        config=self._config(interaction.guild_id,config_id);value=self._editable(config);value["locked"]=False;await self._save_edit(interaction,config,value)
    @short.command(name="temp")
    async def short_temp(self,interaction:discord.Interaction,config_id:int,minutes:int)->None:
        config=self._config(interaction.guild_id,config_id);value=self._editable(config);value["behavior_type"]="temp";value["temp_duration_seconds"]=minutes*60;await self._save_edit(interaction,config,value)
    async def _set_short_type(self,interaction:discord.Interaction,config_id:int,behavior:str)->None:
        config=self._config(interaction.guild_id,config_id);value=self._editable(config);value["behavior_type"]=behavior;await self._save_edit(interaction,config,value)

    async def _deny(self,member:discord.Member,message:discord.Message,emoji:discord.PartialEmoji|str,config:dict[str,Any],mapping:dict[str,Any],reason:str)->None:
        try:await message.remove_reaction(emoji,member)
        except discord.HTTPException:pass
        settings=self.repository.settings(member.guild.id);key=(member.id,config["id"],reason);now=time.monotonic()
        if settings.get("denial_dm") and now-self._dm_recent.get(key,0)>=int(settings.get("denial_dm_cooldown_seconds",300)):
            self._dm_recent[key]=now
            try:await member.send(f"{config['name']}: {reason}")
            except discord.HTTPException:pass
        self.repository.audit(member.guild.id,config["id"],"reaction_denied","denied",user_id=member.id,emoji_key=mapping["emoji_key"],role_id=mapping["role_id"],reason=reason)
        await self._send_log(member.guild,config,"denied",member.id,mapping,reason)

    async def _send_log(self,guild:discord.Guild,config:dict[str,Any],result:str,user_id:int,mapping:dict[str,Any],reason:str|None=None)->None:
        channel_id=self.repository.settings(guild.id).get("log_channel_id")
        channel=guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel,discord.TextChannel):return
        embed=discord.Embed(title="Reaction Roles",color=discord.Color.orange() if result!="success" else discord.Color.green())
        embed.add_field(name="設定",value=f"#{config['id']} {config['name']}",inline=False)
        embed.add_field(name="対象",value=f"<@{user_id}>",inline=True)
        embed.add_field(name="対応",value=f"{mapping['emoji']} → <@&{mapping['role_id']}>",inline=True)
        if reason:embed.add_field(name="結果",value=reason[:1024],inline=False)
        try:await channel.send(embed=embed,allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:pass

    async def _handle_reaction(self,payload:discord.RawReactionActionEvent,event:str)->None:
        if not payload.guild_id or not payload.user_id or self.bot.user and payload.user_id==self.bot.user.id:return
        settings=self.repository.settings(payload.guild_id)
        if not settings.get("enabled"):return
        config=self.repository.message_by_discord_id(payload.guild_id,payload.message_id)
        if not config:return
        mapping=self.service.mapping(config,_emoji_key(payload.emoji))
        if not mapping:return
        guild=self.bot.get_guild(payload.guild_id)
        if not guild:return
        member=payload.member if event=="add" and isinstance(payload.member,discord.Member) else guild.get_member(payload.user_id)
        if not member or member.bot:return
        channel=guild.get_channel(payload.channel_id)
        if not isinstance(channel,(discord.TextChannel,discord.Thread)):return
        try:message=await channel.fetch_message(payload.message_id)
        except discord.HTTPException:return
        role=guild.get_role(mapping["role_id"]);me=guild.me
        lock_key=(guild.id,member.id,int(config.get("link_group_id") or config["id"]))
        async with self._locks[lock_key]:
            decision=self.service.decide(config,mapping,event=event,user_id=member.id,member_role_ids={item.id for item in member.roles},role_member_count=len(role.members) if role else 0)
            if not decision.allowed:
                await self._deny(member,message,payload.emoji,config,mapping,decision.reason);return
            if decision.operation=="none":return
            if not role or role.is_default() or role.managed or not me or not me.guild_permissions.manage_roles or role>=me.top_role:
                await self._deny(member,message,payload.emoji,config,mapping,"BotがこのRoleを管理できません。");return
            try:
                if decision.operation=="remove":
                    await member.remove_roles(role,reason="Reaction Role removed");self.repository.deactivate_assignment(config["id"],mapping["id"],member.id)
                else:
                    async with self._role_locks[(guild.id,role.id)]:
                        if mapping.get("max_members") and role not in member.roles and len(role.members)>=mapping["max_members"]:
                            await self._deny(member,message,payload.emoji,config,mapping,"このRoleは人数上限に達しています。");return
                        await member.add_roles(role,reason="Reaction Role selected")
                    removed=[]
                    try:
                        for assignment in decision.conflicting_assignments:
                            old_config=self.repository.message(guild.id,int(assignment["message_config_id"]));old_role=guild.get_role(int(assignment["role_id"]))
                            if old_role:await member.remove_roles(old_role,reason="Reaction Role exclusive selection")
                            if old_config:
                                old_mapping=next((item for item in old_config["mappings"] if item["id"]==assignment["mapping_id"]),None)
                                old_channel=guild.get_channel(old_config["channel_id"])
                                if old_mapping and old_config.get("message_id") and isinstance(old_channel,(discord.TextChannel,discord.Thread)):
                                    try:old_message=await old_channel.fetch_message(old_config["message_id"]);await old_message.remove_reaction(old_mapping["emoji"],member)
                                    except discord.HTTPException:pass
                            self.repository.deactivate_assignment(int(assignment["message_config_id"]),int(assignment["mapping_id"]),member.id);removed.append(assignment)
                    except discord.HTTPException:
                        await member.remove_roles(role,reason="Reaction Role compensation");raise
                    expires_at=int(time.time())+config["temp_duration_seconds"] if config["behavior_type"]=="temp" else None
                    self.repository.activate_assignment(guild.id,config["id"],mapping["id"],member.id,role.id,expires_at,binding=config["behavior_type"]=="binding")
                    if config["behavior_type"]=="verify":
                        try:await message.remove_reaction(payload.emoji,member)
                        except discord.HTTPException:pass
                self.repository.audit(guild.id,config["id"],f"reaction_{event}","success",user_id=member.id,emoji_key=mapping["emoji_key"],role_id=role.id)
                await self._send_log(guild,config,"success",member.id,mapping)
            except discord.HTTPException as exc:
                self.repository.audit(guild.id,config["id"],f"reaction_{event}","failed",user_id=member.id,emoji_key=mapping["emoji_key"],role_id=role.id,reason=type(exc).__name__)
                await self._send_log(guild,config,"failed",member.id,mapping,type(exc).__name__)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self,payload:discord.RawReactionActionEvent)->None:await self._handle_reaction(payload,"add")
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self,payload:discord.RawReactionActionEvent)->None:await self._handle_reaction(payload,"remove")
    @commands.Cog.listener()
    async def on_raw_message_delete(self,payload:discord.RawMessageDeleteEvent)->None:
        if not payload.guild_id:return
        config=self.repository.message_by_discord_id(payload.guild_id,payload.message_id)
        if config:self.repository.delete_message(payload.guild_id,config["id"],recoverable=True)

    @tasks.loop(seconds=5)
    async def process_outbox(self)->None:
        await run_batch(self.repository.outbox_jobs, self.owner, self._process_outbox_item)

    async def _process_outbox_item(self, item: dict) -> Outcome:
        try:
            config=self.repository.message(int(item["guild_id"]),int(item["message_config_id"])) if item.get("message_config_id") else None
            guild=self.bot.get_guild(int(item["guild_id"])); channel_id=config["channel_id"] if config else item["payload"].get("channel_id");channel=guild.get_channel(int(channel_id)) if guild and channel_id else None
            if item["action"]=="delete":
                message_id=config.get("message_id") if config else item["payload"].get("message_id");source=config["source"] if config else item["payload"].get("source")
                if message_id and source=="bot" and isinstance(channel,(discord.TextChannel,discord.Thread)):
                    try:message=await channel.fetch_message(int(message_id));await message.delete()
                    except discord.NotFound:pass
                return Outcome()
            if not config or not isinstance(channel,(discord.TextChannel,discord.Thread)):raise RuntimeError("message_unavailable")
            if item["action"]=="move":
                target_channel=guild.get_channel(int(item["payload"].get("channel_id",0)))
                if not isinstance(target_channel,(discord.TextChannel,discord.Thread)):raise RuntimeError("move_channel_unavailable")
                target=await target_channel.fetch_message(int(item["payload"].get("message_id",0)))
                for mapping in config["mappings"]:await target.add_reaction(mapping["emoji"])
                old_channel=channel;old_message_id=config.get("message_id");old_source=config["source"]
                self.repository.move_message(guild.id,config["id"],target_channel.id,target.id,"bot" if self.bot.user and target.author.id==self.bot.user.id else "external",int(item["payload"].get("revision",config["revision"])))
                if old_source=="bot" and old_message_id:
                    try:old=await old_channel.fetch_message(old_message_id);await old.delete()
                    except discord.HTTPException:self.repository.audit(guild.id,config["id"],"move_cleanup","partial",reason="old_message_delete_failed")
                return Outcome()
            embed=discord.Embed(title=config["embed"]["title"] or None,description=config["embed"]["description"] or None,color=int(config["embed"]["color"].lstrip("#"),16))
            message=None
            if config.get("message_id"):
                try:message=await channel.fetch_message(config["message_id"])
                except discord.NotFound:pass
            if config["source"]=="bot":
                if message:
                    message=await message.edit(embed=embed,allowed_mentions=discord.AllowedMentions.none())
                else:
                    message=await channel.send(embed=embed,allowed_mentions=discord.AllowedMentions.none())
                    # Persist the Discord identity before adding reactions. If a
                    # later reaction fails, the retry repairs this message instead
                    # of publishing a new one every time the outbox is claimed.
                    self.repository.set_discord_message(config["id"],message.id,status="publishing")
                    config["message_id"]=message.id
            elif not message:raise RuntimeError("external_message_missing")
            for mapping in config["mappings"]:
                try:await message.add_reaction(mapping["emoji"])
                except discord.HTTPException:
                    if not item["payload"].get("foreign"):raise
            self.repository.set_discord_message(config["id"],message.id);return Outcome()
        except (discord.Forbidden,discord.NotFound,RuntimeError) as exc:
            if config:self.repository.set_delivery_status(config["id"],"failed",str(exc))
            return Outcome(str(exc), retry=False)
        except Exception as exc:
            if config:self.repository.set_delivery_status(config["id"],"pending",type(exc).__name__)
            return Outcome(type(exc).__name__, retry=True)

    @tasks.loop(seconds=15)
    async def process_schedules(self)->None:
        await run_batch(self.repository.schedule_jobs, self.owner, self._process_schedule_item, limit=100)

    async def _process_schedule_item(self, item: dict) -> Outcome:
        try:
            config=self.repository.message(int(item["guild_id"]),int(item["message_config_id"])) if item.get("message_config_id") else None;guild=self.bot.get_guild(int(item["guild_id"]))
            if item["kind"]=="self_destruct":
                if config and config["source"]=="bot":
                    guild_id=int(item["guild_id"])
                    self.repository.queue_action(guild_id,config["id"],"delete",{"channel_id":config["channel_id"],"message_id":config.get("message_id"),"source":config["source"]})
                    self.repository.delete_message(guild_id,config["id"],recoverable=False)
            elif item["kind"]=="temp_role" and config and guild:
                mapping=next((value for value in config["mappings"] if value["id"]==item["mapping_id"]),None);member=guild.get_member(int(item["user_id"]));role=guild.get_role(mapping["role_id"]) if mapping else None
                if member and role:await member.remove_roles(role,reason="Temporary Reaction Role expired")
                if mapping:self.repository.deactivate_assignment(config["id"],mapping["id"],int(item["user_id"]))
            return Outcome()
        except Exception as exc:return Outcome(type(exc).__name__, retry=True)

    @tasks.loop(hours=1)
    async def maintenance(self)->None:
        self.repository.maintain();cutoff=time.monotonic()-86400
        self._dm_recent={key:value for key,value in self._dm_recent.items() if value>=cutoff}


async def setup(bot:commands.Bot)->None:
    await bot.add_cog(ReactionRolesCog(bot))
