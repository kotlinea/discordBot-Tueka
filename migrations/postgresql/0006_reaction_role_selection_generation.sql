CREATE SEQUENCE reaction_role_selection_generation;
ALTER TABLE reaction_role_assignments ADD COLUMN generation BIGINT NOT NULL DEFAULT nextval('reaction_role_selection_generation');
ALTER TABLE reaction_role_schedules ADD COLUMN selection_generation BIGINT;
ALTER TABLE reaction_role_schedules ADD COLUMN cleanup_only BOOLEAN NOT NULL DEFAULT false;

UPDATE reaction_role_schedules s SET selection_generation=a.generation
    FROM reaction_role_assignments a WHERE s.message_config_id=a.message_config_id
    AND s.mapping_id=a.mapping_id AND s.user_id=a.user_id AND s.scheduled_for=a.expires_at;

-- Old superseded attached jobs still have evidence for assignment-only cleanup.
UPDATE reaction_role_schedules SET cleanup_only=true,state='pending',completed_at=NULL,
    lease_owner=NULL,lease_token=NULL,lease_until=NULL
    WHERE kind='temp_role' AND state='done' AND last_error='Superseded by a newer Reaction Role selection'
    AND selection_generation IS NOT NULL;

-- Detached jobs from before this migration have no provable selection identity.
UPDATE reaction_role_schedules SET state='failed',
    last_error='Selection generation unavailable; reconciliation required',
    completed_at=COALESCE(completed_at,created_at),lease_owner=NULL,lease_token=NULL,lease_until=NULL
    WHERE kind='temp_role' AND state IN ('pending','retry','processing') AND selection_generation IS NULL;

UPDATE reaction_role_outbox SET state='failed',last_error='Cleanup selection generation unavailable; reconciliation required',
    completed_at=COALESCE(completed_at,created_at),lease_owner=NULL,lease_token=NULL,lease_until=NULL
    WHERE action='clear_selection' AND state IN ('pending','retry','processing')
    AND (payload_json::jsonb ->> 'selection_generation') IS NULL;
