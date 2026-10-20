"""Fast, Discord-independent AutoMod rule evaluation."""
from __future__ import annotations

import re
import time
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import regex

from .models import RATE_TRIGGERS


URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>]+", re.IGNORECASE)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]{1,253})\]\((https?://[^\s)]+)\)", re.IGNORECASE)
INVITE_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:discord(?:app)?\.com/invite|discord\.(?:gg|io|me|li))/[A-Za-z0-9-]+", re.IGNORECASE)
EMOJI_RE = re.compile("[\U0001F1E6-\U0001FAFF\u2600-\u27BF]")
CUSTOM_EMOJI_RE = re.compile(r"<a?:[A-Za-z0-9_]{2,32}:\d+>")
MEDIA_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "webm", "mp4", "mov", "mp3", "wav", "flac", "pdf"}


@dataclass(slots=True)
class MessageContext:
    guild_id: int
    user_id: int
    channel_id: int
    content: str = ""
    category_id: int | None = None
    role_ids: set[int] = field(default_factory=set)
    mention_count: int = 0
    attachment_count: int = 0
    emoji_count: int = 0
    sticker_count: int = 0
    reaction_count: int = 0
    target_id: int | None = None
    actor_kind: str = "human"
    webhook_id: int | None = None
    event_type: str = "message_create"
    account_created_at: datetime | None = None
    joined_at: datetime | None = None
    now: float = field(default_factory=time.monotonic)

    @property
    def urls(self) -> list[str]:
        return URL_RE.findall(self.content)[:20]


@dataclass(slots=True)
class RuleMatch:
    rule: dict[str, Any]
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


UnsafeURLChecker = Callable[[list[str]], Awaitable[str | None]]


class AutoModEngine:
    def __init__(self, *, max_state_keys: int = 10000) -> None:
        self._state: dict[tuple[int, int, int], deque[tuple[float, str, int, int, int, int, int, bool]]] = defaultdict(deque)
        self._last_seen: dict[tuple[int, int, int], float] = {}
        self.max_state_keys = max_state_keys
        self._last_cleanup = 0.0

    @property
    def state_size(self) -> int:
        return len(self._state)

    def prune(self, now: float | None = None, *, max_age: int = 600) -> None:
        current = time.monotonic() if now is None else now
        stale = [key for key, seen in self._last_seen.items() if current - seen > max_age]
        if len(self._state) > self.max_state_keys:
            stale.extend(key for key, _ in sorted(self._last_seen.items(), key=lambda item: item[1])[:len(self._state) - self.max_state_keys])
        for key in set(stale):
            self._state.pop(key, None)
            self._last_seen.pop(key, None)
        self._last_cleanup = current

    @staticmethod
    def globally_exempt(context: MessageContext, settings: dict[str, Any]) -> bool:
        immune_channels = set(settings.get("immune_channel_ids", []))
        if (context.user_id in set(settings.get("immune_user_ids", [])) or context.channel_id in immune_channels
                or context.category_id in immune_channels):
            return True
        return bool(context.role_ids & set(settings.get("immune_role_ids", [])))

    @staticmethod
    def _eligible(context: MessageContext, rule: dict[str, Any]) -> bool:
        expected_event = rule.get("event_type", "message_create")
        if expected_event != context.event_type and not (context.event_type == "message_edit" and expected_event == "message_create" and rule.get("trigger_type") not in RATE_TRIGGERS):
            return False
        exemptions = rule.get("exemptions", {})
        if context.user_id in set(exemptions.get("user_ids", [])) or context.channel_id in set(exemptions.get("channel_ids", [])):
            return False
        if context.role_ids & set(exemptions.get("role_ids", [])):
            return False
        if context.category_id in set(exemptions.get("category_ids", [])):
            return False
        if context.actor_kind == "bot" and context.user_id in set(exemptions.get("bot_ids", [])):
            return False
        if context.actor_kind == "webhook" and context.webhook_id in set(exemptions.get("webhook_ids", [])):
            return False
        conditions = rule.get("conditions", {})
        if conditions.get("actor_kinds") and context.actor_kind not in conditions["actor_kinds"]:
            return False
        if conditions.get("user_ids") and context.user_id not in set(conditions["user_ids"]):
            return False
        explicitly_scoped = bool(conditions.get("channel_ids") and context.channel_id in set(conditions["channel_ids"]))
        if context.actor_kind == "bot" and context.user_id not in set(conditions.get("bot_ids", [])) and not explicitly_scoped:
            return False
        if context.actor_kind == "webhook" and context.webhook_id not in set(conditions.get("webhook_ids", [])) and not explicitly_scoped:
            return False
        if conditions.get("channel_ids") and context.channel_id not in set(conditions["channel_ids"]):
            return False
        if conditions.get("category_ids") and context.category_id not in set(conditions["category_ids"]):
            return False
        if conditions.get("required_role_ids") and not context.role_ids & set(conditions["required_role_ids"]):
            return False
        if context.role_ids & set(conditions.get("excluded_role_ids", [])):
            return False
        now = datetime.now(timezone.utc)
        minimum_account = int(conditions.get("minimum_account_age_days", 0))
        if minimum_account and (context.account_created_at is None or (now - context.account_created_at).total_seconds() < minimum_account * 86400):
            return False
        minimum_join = int(conditions.get("minimum_join_age_days", 0))
        if minimum_join and (context.joined_at is None or (now - context.joined_at).total_seconds() < minimum_join * 86400):
            return False
        return True

    @staticmethod
    def _host(url: str) -> str | None:
        try:
            value = url if "://" in url else f"https://{url}"
            host = (urlparse(value).hostname or "").rstrip(".").lower()
            return host.encode("idna").decode("ascii") if host else None
        except (ValueError, UnicodeError):
            return None

    @staticmethod
    def _domain_matches(host: str, domain: str) -> bool:
        try:
            normalized = domain.encode("idna").decode("ascii")
        except UnicodeError:
            normalized = domain
        return host == normalized or host.endswith("." + normalized)

    @staticmethod
    def _keyword_hit(content: str, keyword: str, mode: str) -> bool:
        lowered = unicodedata.normalize("NFKC", content).casefold()
        target = unicodedata.normalize("NFKC", keyword).casefold()
        if mode == "contains":
            return target in lowered
        if "*" in target:
            pattern = re.escape(target).replace(r"\*", ".*?")
            return re.search(pattern, lowered, re.IGNORECASE) is not None
        if any(ord(character) > 127 for character in target):
            return target in lowered
        return re.search(rf"(?<!\w){re.escape(target)}(?!\w)", lowered, re.IGNORECASE) is not None

    async def evaluate(self, context: MessageContext, rules: list[dict[str, Any]], *, edited: bool = False,
                       unsafe_url_checker: UnsafeURLChecker | None = None) -> list[RuleMatch]:
        if context.now - self._last_cleanup > 60 or len(self._state) > self.max_state_keys:
            self.prune(context.now)
        matches: list[RuleMatch] = []
        for rule in sorted(rules, key=lambda item: (int(item.get("priority", 100)), int(item.get("id", 0)))):
            if not rule.get("enabled", True) or not self._eligible(context, rule):
                continue
            trigger = rule["trigger_type"]
            if edited and trigger in RATE_TRIGGERS:
                continue
            match = await self._match(context, rule, unsafe_url_checker)
            if match:
                matches.append(match)
                if rule.get("stop_on_match"):
                    break
        return matches

    async def _match(self, context: MessageContext, rule: dict[str, Any], unsafe_url_checker: UnsafeURLChecker | None) -> RuleMatch | None:
        trigger, config, content = rule["trigger_type"], rule.get("trigger_config", {}), context.content
        if trigger == "keyword":
            if any(self._keyword_hit(content, item, "contains") for item in config.get("allow_list", [])):
                return None
            for keyword in config.get("keywords", []):
                if self._keyword_hit(content, keyword, config.get("match", "wildcard")):
                    return RuleMatch(rule, f"禁止キーワードを検知: {keyword}", {"keyword": keyword})
        elif trigger == "regex":
            for pattern in config.get("patterns", []):
                try:
                    found = regex.search(pattern, content[:4000], regex.IGNORECASE, timeout=0.02)
                except TimeoutError:
                    continue
                if found:
                    return RuleMatch(rule, "正規表現ルールに一致", {"pattern": pattern, "match": found.group(0)[:100]})
        elif trigger == "safe_browsing" and context.urls and unsafe_url_checker:
            unsafe = await unsafe_url_checker(context.urls[:5])
            if unsafe:
                return RuleMatch(rule, "危険なURLを検知", {"url": unsafe})
        elif trigger == "discord_invite" and INVITE_RE.search(content):
            return RuleMatch(rule, "Discord招待リンクを検知")
        elif trigger == "domain" and context.urls:
            hosts = [host for url in context.urls if (host := self._host(url))]
            domains = config.get("domains", [])
            for host in hosts:
                listed = any(self._domain_matches(host, domain) for domain in domains)
                if (config.get("mode") == "blacklist" and listed) or (config.get("mode") == "block_all_except" and not listed):
                    return RuleMatch(rule, f"許可されていないドメインを検知: {host}", {"domain": host})
        elif trigger == "phishing_link":
            for label, url in MARKDOWN_LINK_RE.findall(content):
                destination = self._host(url)
                claimed = self._host(label) if "." in label else None
                if claimed and destination and not self._domain_matches(destination, claimed):
                    return RuleMatch(rule, "表示先と実際のリンク先が異なるURLを検知", {"claimed": claimed, "destination": destination})
        elif trigger in RATE_TRIGGERS:
            subject_id = 0 if trigger in {"join_rate", "leave_rate", "new_account_ratio"} else context.user_id
            key = (context.guild_id, subject_id, int(rule.get("id", hash(rule["name"]) & 0x7FFFFFFF)))
            queue, window = self._state[key], int(config.get("window_seconds", 10))
            fresh = bool(context.account_created_at and (datetime.now(timezone.utc) - context.account_created_at).total_seconds() < int(config.get("account_age_days", 7)) * 86400)
            symbol_count = context.emoji_count or len(EMOJI_RE.findall(content)) + len(CUSTOM_EMOJI_RE.findall(content))
            queue.append((context.now, content.casefold().strip(), context.mention_count, len(context.urls), context.attachment_count, symbol_count + context.sticker_count, context.target_id or 0, fresh))
            self._last_seen[key] = context.now
            while queue and context.now - queue[0][0] > window:
                queue.popleft()
            limit = int(config.get("limit", 3))
            duplicate_count = sum(bool(content.strip()) and (item[1] == content.casefold().strip() or (int(config.get("similarity_percent", 100)) < 100 and SequenceMatcher(None, item[1], content.casefold().strip()).ratio() * 100 >= int(config["similarity_percent"]))) for item in queue)
            value = {
                "message_rate": len(queue),
                "duplicate": duplicate_count,
                "mention_rate": sum(item[2] for item in queue),
                "link_rate": sum(item[3] for item in queue),
                "attachment_rate": sum(item[4] for item in queue),
                "reaction_rate": len(queue),
                "reaction_burst": sum(item[6] == (context.target_id or 0) for item in queue),
                "join_rate": len(queue),
                "leave_rate": len(queue),
                "new_account_ratio": round(sum(item[7] for item in queue) * 100 / len(queue)) if len(queue) >= limit else 0,
                "emoji_sticker_rate": sum(item[5] for item in queue),
            }[trigger]
            matched = value >= (int(config.get("percentage", 70)) if trigger == "new_account_ratio" else limit)
            if trigger == "emoji_sticker_rate" and symbol_count >= int(config.get("per_message_limit", 12)):
                matched = True
                value = symbol_count
            if matched:
                labels = {"message_rate": "メッセージ連投", "duplicate": "重複・類似メッセージ", "mention_rate": "メンションスパム", "link_rate": "リンクスパム", "attachment_rate": "添付ファイルスパム", "reaction_rate": "リアクションスパム", "reaction_burst": "同一メッセージへのリアクション連打", "join_rate": "Join Raid", "leave_rate": "大量退出", "new_account_ratio": "新規アカウント比率の急増", "emoji_sticker_rate": "絵文字・スタンプスパム"}
                return RuleMatch(rule, labels[trigger], {"count": value, "window_seconds": window})
        elif trigger == "new_member_activity":
            if context.joined_at is not None:
                age_minutes = max(0, (datetime.now(timezone.utc) - context.joined_at).total_seconds() / 60)
                if age_minutes <= int(config.get("join_age_minutes", 10)):
                    return RuleMatch(rule, "参加直後のメッセージ行動", {"join_age_minutes": round(age_minutes, 1)})
        elif trigger == "caps":
            letters = [character for character in content if character.isalpha()]
            if len(letters) >= int(config.get("minimum_letters", 6)):
                percentage = round(sum(character.isupper() for character in letters) * 100 / len(letters))
                if percentage >= int(config.get("percentage", 70)):
                    return RuleMatch(rule, f"大文字率が上限を超過: {percentage}%", {"percentage": percentage})
        elif trigger == "media_only":
            paths = []
            for url in context.urls:
                try:
                    paths.append(urlparse(url if "://" in url else f"https://{url}").path)
                except (ValueError, UnicodeError):
                    continue
            media_link = any(path.rsplit(".", 1)[-1].lower() in MEDIA_EXTENSIONS for path in paths if "." in path)
            if context.attachment_count == 0 and not (config.get("allow_links", True) and media_link):
                return RuleMatch(rule, "メディア限定チャンネルへのテキスト投稿")
        elif trigger == "honeypot" and context.channel_id in set(config.get("channel_ids", [])):
            return RuleMatch(rule, "ハニーポットチャンネルへの投稿")
        return None
