"""Converge known highlight receipts with current source state; never blind resend."""
from typing import Protocol
import asyncio
from discord_io import DiscordFailure, settle_external
from jobs import Outcome,LostLease
from .models import eligible


class HighlightAdapter(Protocol):
    async def source(self,guild:int,channel:int,message:int,emoji:str,allow_private:bool=False)->tuple[dict,int]: ...
    async def reconcile(self,guild:int,channel:int,marker:str)->int|None: ...
    async def send(self,guild:int,channel:int,source:dict,score:int,emoji:str,marker:str)->int: ...
    async def edit(self,guild:int,channel:int,message:int,source:dict,score:int,emoji:str,marker:str)->None: ...
    async def delete(self,guild:int,channel:int,message:int,marker:str)->None: ...


class HighlightDelivery:
    def __init__(self,repository,adapter:HighlightAdapter):
        self.repo,self.adapter=repository,adapter
        # The Cog shares this lock for raw events and source deletion, so a later
        # fetch cannot be overwritten by an earlier concurrent SDK response.
        self.source_lock=asyncio.Lock()

    @staticmethod
    def marker(publication,entry):return f'Tueka highlight:{publication}:{entry}'

    _external = staticmethod(settle_external)

    async def _receipt(self,job,publication,entry):
        if publication['message_id']:return publication['message_id']
        if not publication['delivery_started']:return None
        marker=self.marker(publication['id'],entry['id'])
        receipt=await self.adapter.reconcile(entry['guild_id'],publication['target_channel_id'],marker)
        if receipt is None:raise DiscordFailure('Highlight delivery is uncertain; receipt reconciliation required',partial=True)
        self.repo.publication_receipt(job,publication['id'],receipt)
        return receipt

    async def handle(self,job):
        entry=None;external_started=False;settled=False;cancelled=False
        try:
            plan=self.repo.delivery_plan(job);entry=plan['entry'];config=plan['config']
            if config['enabled'] and not plan['source'].get('deleted') and eligible(config,plan['source']):
                async with self.source_lock:
                    try:
                        source,score=await self.adapter.source(entry['guild_id'],entry['source_channel_id'],entry['source_message_id'],config['emoji'],entry['source_channel_id'] in config['source_channel_ids'])
                    except DiscordFailure as failure:
                        if not failure.missing:raise
                        self.repo.delete_source(entry['guild_id'],entry['source_channel_id'],[entry['source_message_id']])
                    else:
                        self.repo.observe(entry['guild_id'],entry['board_id'],plan['board_revision'],source,score)
                plan=self.repo.delivery_plan(job);entry=plan['entry'];config=plan['config']
            retained=None
            for publication in plan['publications']:
                receipt=await self._receipt(job,publication,entry)
                target=publication['target_channel_id']
                if plan['desired'] and target==config['target_channel_id'] and receipt:
                    try:
                        external_started=True
                        await self._external(self.adapter.edit(entry['guild_id'],target,receipt,plan['source'],entry['score'],config['emoji'],self.marker(publication['id'],entry['id'])))
                    except DiscordFailure as failure:
                        if not failure.missing:raise
                        self.repo.publication_removed(job,publication['id'])
                    else:retained=receipt
                else:
                    if receipt:
                        try:
                            external_started=True
                            await self._external(self.adapter.delete(entry['guild_id'],target,receipt,self.marker(publication['id'],entry['id'])))
                        except DiscordFailure as failure:
                            if not failure.missing:raise
                    self.repo.publication_removed(job,publication['id'])
            if plan['desired'] and retained is None:
                publication,action=self.repo.publication_begin(job,config['target_channel_id'])
                if action=='recover':
                    retained=await self._receipt(job,{**publication,'delivery_started':1},entry)
                    external_started=True
                    await self._external(self.adapter.edit(entry['guild_id'],config['target_channel_id'],retained,plan['source'],entry['score'],config['emoji'],self.marker(publication['id'],entry['id'])))
                elif action=='edit':
                    raise LostLease('A second highlight delivery raced this worker')
                else:
                    try:
                        external_started=True
                        receipt=await self._external(self.adapter.send(entry['guild_id'],config['target_channel_id'],plan['source'],entry['score'],config['emoji'],self.marker(publication['id'],entry['id'])))
                    except DiscordFailure as failure:
                        if not failure.partial:self.repo.publication_not_sent(job,publication['id'])
                        raise
                    self.repo.publication_receipt(job,publication['id'],receipt)
            self.repo.delivery_settled(job,entry['revision'])
            settled=True
            return Outcome()
        except asyncio.CancelledError:
            cancelled=True
            raise
        except DiscordFailure as failure:return Outcome(str(failure),retry=failure.retry)
        except PermissionError:return Outcome('Starboard is disabled',retry=True)
        except LostLease:raise
        except Exception as exc:return Outcome(f'Highlight processing failed ({type(exc).__name__})',retry=True)
        finally:
            if external_started and not settled:
                self.repo.delivery_repair(entry['guild_id'],entry['id'],job,cancelled=cancelled)
