"""The shared queues and their domain-specific storage columns."""
from .repository import QueueSpec

QUEUE_SPECS = {spec.table: spec for spec in (
    QueueSpec('giveaway_outbox'),
    QueueSpec('giveaway_draw_jobs'),
    QueueSpec('starboard_outbox'),
    QueueSpec('starboard_refresh_jobs'),
    QueueSpec('scheduled_post_outbox'),
    QueueSpec('appeal_outbox'),
    QueueSpec('ticket_outbox'),
    QueueSpec('ticket_schedules', due='due_at'),
    QueueSpec('reaction_role_outbox', state='state', due='next_attempt_at', done='done'),
    QueueSpec('reaction_role_schedules', state='state', due='due_at', done='done'),
    QueueSpec('moderation_action_requests', result='result_json'),
    QueueSpec('scheduled_moderation_actions', due='due_at', created=None),
    QueueSpec('social_events', completed='processed_at', created='received_at'),
    QueueSpec('suggestion_outbox'),
)}
