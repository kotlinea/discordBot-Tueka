"""Application-scoped repository and service composition."""
from __future__ import annotations
from dashboard.repository import DashboardRepository
from guild_settings import GuildSettingsRepository
from typing import Any
from social import SocialRepository
from moderation import ModerationRepository
from ticketing import TicketRepository, TicketService, TranscriptStorage
from reaction_roles import ReactionRoleRepository, ReactionRoleService
from suggestions import SuggestionRepository
from applications.repository import ApplicationRepository
from appeals.repository import AppealRepository
from scheduling.repository import ScheduleRepository
from dataclasses import dataclass, field
from features.defaults import SettingsAccess

@dataclass(frozen=True)
class ApiContext:
    discord: Any
    settings: Any | None
    social_repository: SocialRepository
    moderation_repository: ModerationRepository
    dashboard_repository: DashboardRepository
    guild_settings_repository: GuildSettingsRepository
    ticket_repository: TicketRepository | None
    ticket_transcripts: TranscriptStorage | None
    ticket_service: TicketService | None
    reaction_role_repository: ReactionRoleRepository | None
    reaction_role_service: ReactionRoleService | None
    suggestion_repository: SuggestionRepository
    application_repository: ApplicationRepository
    appeal_repository: AppealRepository
    schedule_repository: ScheduleRepository
    feature_settings: dict[str, SettingsAccess] = field(default_factory=dict)

def create_context(database_url: str, discord: Any, settings: Any | None=None) -> ApiContext:
    social_repository = SocialRepository(database_url)
    moderation_repository = ModerationRepository(database_url)
    dashboard_repository = DashboardRepository(database_url)
    guild_settings_repository = GuildSettingsRepository(database_url)
    ticket_repository = TicketRepository(settings.database_url) if settings is not None else None
    ticket_transcripts = TranscriptStorage(settings.data_dir / 'ticket-transcripts', settings.ticket_encryption_key, s3={'endpoint_url': settings.ticket_s3_endpoint_url, 'region': settings.ticket_s3_region, 'bucket': settings.ticket_s3_bucket, 'access_key_id': settings.ticket_s3_access_key_id, 'secret_access_key': settings.ticket_s3_secret_access_key, 'prefix': settings.ticket_s3_prefix}) if settings is not None else None
    ticket_service = TicketService(ticket_repository, ticket_transcripts) if ticket_repository and ticket_transcripts else None
    reaction_role_repository = ReactionRoleRepository(settings.database_url) if settings is not None else None
    reaction_role_service = ReactionRoleService(reaction_role_repository, max_mappings=settings.reaction_role_max_mappings_per_message) if reaction_role_repository and settings else None
    suggestion_repository = SuggestionRepository(database_url)
    context = ApiContext(discord=discord, settings=settings, social_repository=social_repository, moderation_repository=moderation_repository, dashboard_repository=dashboard_repository, guild_settings_repository=guild_settings_repository, ticket_repository=ticket_repository, ticket_transcripts=ticket_transcripts, ticket_service=ticket_service, reaction_role_repository=reaction_role_repository, reaction_role_service=reaction_role_service, suggestion_repository=suggestion_repository, application_repository=ApplicationRepository(database_url), appeal_repository=AppealRepository(database_url), schedule_repository=ScheduleRepository(database_url))

    from .settings import create_settings_access
    context.feature_settings.update(create_settings_access(context))
    return context
