"""Panel publication state and receipt recovery independent of Discord SDK."""
from typing import Protocol

from discord_io import DiscordFailure
from jobs import LostLease


class PanelPort(Protocol):
    async def find_panel_message(self, config: dict) -> int: ...
    async def publish_panel(self, config: dict, panels: list[dict], *, recover: bool) -> int: ...
    async def delete_panel_message(self, guild_id: int, channel_id: int, message_id: int) -> None: ...


class PanelDeliveryService:
    def __init__(self, repository, port: PanelPort):
        self.repository, self.port = repository, port

    async def deliver(self, config: dict) -> None:
        message_id = int(config.get('message_id') or 0)
        try:
            if config['status'].startswith('delete'):
                if config['status'] == 'delete_uncertain':
                    message_id = await self.port.find_panel_message(config)
                    config = {**config, 'status': 'delete'}
                    if not self.repository.mark_panel_published(config, message_id, finish=False):
                        raise LostLease('Panel ownership changed during delete recovery')
                if message_id:
                    await self.port.delete_panel_message(config['guild_id'], config['channel_id'], message_id)
                if config.get('previous_message_id'):
                    await self.port.delete_panel_message(config['guild_id'], config['previous_channel_id'], config['previous_message_id'])
                if not self.repository.mark_panel_published(config, 0, deleted=True):
                    raise LostLease('Panel ownership changed')
                return
            panels = [self.repository.panel(config['guild_id'], int(panel_id)) for panel_id in config['panel_ids']]
            panels = [panel for panel in panels if panel and panel.get('enabled')]
            if not panels:
                raise DiscordFailure('No enabled panels')
            message_id = await self.port.publish_panel(config, panels, recover=config['status'] == 'publishing')
            if not self.repository.mark_panel_published(config, message_id, finish=False):
                raise LostLease('Panel ownership changed after publication')
            if config.get('previous_channel_id') and config.get('previous_message_id'):
                await self.port.delete_panel_message(config['guild_id'], config['previous_channel_id'], config['previous_message_id'])
            if not self.repository.mark_panel_published(config, message_id):
                raise LostLease('Panel ownership changed after cleanup')
        except DiscordFailure as exc:
            # Only a definitely unsent initial publication may start a fresh send.
            # Unknown receipts and failures after saving a message ID keep recovery.
            if config['status'] == 'draft' and (exc.partial or message_id):
                config = {**config, 'status': 'publishing'}
            if not self.repository.mark_panel_published(config, message_id, str(exc), retry=exc.retry or exc.partial):
                raise LostLease('Panel ownership changed during failure handling') from exc
