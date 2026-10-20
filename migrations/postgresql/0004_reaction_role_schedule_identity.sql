-- Domain deadlines remain immutable when Queue retry changes due_at.
-- Renaming also moves the existing selection uniqueness constraint onto the
-- immutable deadline, so retry timestamps cannot collide with another job.
ALTER TABLE reaction_role_schedules RENAME COLUMN due_at TO scheduled_for;
ALTER TABLE reaction_role_schedules ADD COLUMN due_at BIGINT;
UPDATE reaction_role_schedules SET due_at=scheduled_for;
ALTER TABLE reaction_role_schedules ALTER COLUMN due_at SET NOT NULL;
ALTER TABLE reaction_role_schedules ALTER COLUMN scheduled_for DROP NOT NULL;
CREATE INDEX idx_rr_schedule_retry_claim ON reaction_role_schedules(state,due_at,lease_until);
UPDATE reaction_role_schedules SET scheduled_for=NULL
    WHERE NOT ((state='pending' AND attempts=0) OR (state='processing' AND attempts=1));

-- Existing retries have lost their original deadline. Do not adopt a newer
-- configuration/assignment deadline as evidence for an older job.
UPDATE reaction_role_schedules SET state='failed',
    last_error='Original schedule time unavailable; reconciliation required',
    completed_at=COALESCE(completed_at,created_at),lease_owner=NULL,lease_token=NULL,lease_until=NULL
    WHERE scheduled_for IS NULL AND state IN ('pending','retry','processing');

UPDATE reaction_role_schedules s SET role_id=m.role_id FROM reaction_role_mappings_v2 m
    WHERE s.kind='temp_role' AND s.role_id IS NULL AND s.mapping_id=m.id;

-- IDs record selection order, rather than sorting by the deadline's length.
UPDATE reaction_role_schedules old SET state='done',
    last_error='Superseded by a newer Reaction Role selection',
    completed_at=COALESCE(old.completed_at,old.created_at),lease_owner=NULL,lease_token=NULL,lease_until=NULL
    WHERE old.kind='temp_role' AND old.state IN ('pending','retry','processing') AND old.role_id IS NOT NULL
    AND EXISTS (SELECT 1 FROM reaction_role_schedules newer
        WHERE newer.kind='temp_role' AND newer.guild_id=old.guild_id AND newer.user_id=old.user_id
        AND newer.role_id=old.role_id AND newer.id>old.id);
