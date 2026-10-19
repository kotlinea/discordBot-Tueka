"""Live membership verification and durable draw/publication orchestration."""
from typing import Protocol
from discord_io import DiscordFailure
from jobs import LostLease, Outcome
from .models import eligible


class GiveawayPort(Protocol):
    async def member(self, guild: int, user: int) -> dict | None: ...
    async def reconcile(self, guild: int, channel: int, marker: str) -> int | None: ...
    async def send(self, plan: dict, marker: str) -> int: ...
    async def edit(self, plan: dict, message: int, marker: str) -> None: ...


class GiveawayService:
    def __init__(self, repository, port: GiveawayPort):
        self.repo, self.port = repository, port

    async def participate(self, guild, item, user, message, interaction, *, join):
        if not self.repo.settings.module_enabled(guild, 'giveaways'):
            raise PermissionError('giveaways_disabled')
        row = self.repo.item(guild, item)
        if row['status'] != 'open' or row['ends_at'] <= int(self.repo.clock()) or row['message_id'] != message:
            raise RuntimeError('campaign_not_accepting')
        if join:
            member = await self.port.member(guild, user)
            if not member or member.get('id') != user or not eligible(row['config'], member, guild, int(self.repo.clock())):
                raise PermissionError('participation_ineligible')
        return self.repo.enter(guild, item, user, message, interaction, join=join)

    async def draw(self, job):
        try:
            plan = self.repo.draw_plan(job)
            if plan['existing']:
                return Outcome()
            campaign = plan['campaign']
            candidates = []
            # Any transport/permission failure aborts the entire attempt. Never
            # publish a draw from a partially fetched eligibility snapshot.
            for user in plan['entrants']:
                member = await self.port.member(campaign['guild_id'], user)
                if member and member.get('id') == user and eligible(campaign['config'], member, campaign['guild_id'], int(self.repo.clock())):
                    candidates.append(user)
            self.repo.complete_draw(job, campaign['revision'], candidates)
            return Outcome()
        except LostLease:
            raise
        except DiscordFailure as failure:
            return Outcome(str(failure), retry=failure.retry)
        except PermissionError:
            return Outcome('Giveaways disabled', retry=True)
        except Exception as exc:
            return Outcome(f'Campaign draw failed ({type(exc).__name__})', retry=True)

    async def publish(self, job):
        try:
            plan = self.repo.publication_plan(job)
            campaign = plan['campaign']
            marker = f'Tueka campaign:{campaign["id"]}'
            action = self.repo.publication_begin(job)
            if action == 'send':
                try:
                    message = await self.port.send(plan, marker)
                except DiscordFailure as failure:
                    if not failure.partial:
                        self.repo.publication_not_sent(job)
                    raise
                self.repo.publication_receipt(job, message)
            elif action == 'recover':
                message = await self.port.reconcile(campaign['guild_id'], campaign['config']['channel_id'], marker)
                if message is None:
                    raise DiscordFailure('Campaign publication uncertain; receipt reconciliation required', partial=True)
                self.repo.publication_receipt(job, message)
                await self.port.edit(plan, message, marker)
            else:
                await self.port.edit(plan, campaign['message_id'], marker)
            self.repo.publication_settled(job, campaign['revision'])
            return Outcome()
        except LostLease:
            raise
        except DiscordFailure as failure:
            return Outcome(str(failure), retry=failure.retry)
        except PermissionError:
            return Outcome('Giveaways disabled', retry=True)
        except Exception as exc:
            return Outcome(f'Campaign publication failed ({type(exc).__name__})', retry=True)
