-- tueka: add-column-if-missing
ALTER TABLE ticket_outbox ADD COLUMN lease_token TEXT;
-- tueka: add-column-if-missing
ALTER TABLE ticket_schedules ADD COLUMN lease_owner TEXT;
-- tueka: add-column-if-missing
ALTER TABLE ticket_schedules ADD COLUMN lease_until INTEGER;
-- tueka: add-column-if-missing
ALTER TABLE ticket_schedules ADD COLUMN lease_token TEXT;
-- tueka: add-column-if-missing
ALTER TABLE reaction_role_outbox ADD COLUMN completed_at INTEGER;
-- tueka: add-column-if-missing
ALTER TABLE reaction_role_outbox ADD COLUMN lease_token TEXT;
-- tueka: add-column-if-missing
ALTER TABLE reaction_role_schedules ADD COLUMN completed_at INTEGER;
-- tueka: add-column-if-missing
ALTER TABLE reaction_role_schedules ADD COLUMN lease_token TEXT;
-- tueka: add-column-if-missing
ALTER TABLE social_events ADD COLUMN lease_token TEXT;
-- tueka: add-column-if-missing
ALTER TABLE moderation_action_requests ADD COLUMN lease_owner TEXT;
-- tueka: add-column-if-missing
ALTER TABLE moderation_action_requests ADD COLUMN lease_until INTEGER;
-- tueka: add-column-if-missing
ALTER TABLE moderation_action_requests ADD COLUMN available_at INTEGER NOT NULL DEFAULT 0;
-- tueka: add-column-if-missing
ALTER TABLE moderation_action_requests ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
-- tueka: add-column-if-missing
ALTER TABLE moderation_action_requests ADD COLUMN last_error TEXT;
-- tueka: add-column-if-missing
ALTER TABLE moderation_action_requests ADD COLUMN lease_token TEXT;
-- tueka: add-column-if-missing
ALTER TABLE scheduled_moderation_actions ADD COLUMN lease_owner TEXT;
-- tueka: add-column-if-missing
ALTER TABLE scheduled_moderation_actions ADD COLUMN lease_until INTEGER;
-- tueka: add-column-if-missing
ALTER TABLE scheduled_moderation_actions ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';
-- tueka: add-column-if-missing
ALTER TABLE scheduled_moderation_actions ADD COLUMN lease_token TEXT;
UPDATE scheduled_moderation_actions SET status='completed' WHERE completed_at IS NOT NULL;
UPDATE reaction_role_outbox SET completed_at=CAST(strftime('%s','now') AS INTEGER) WHERE state IN ('done','failed') AND completed_at IS NULL;
UPDATE reaction_role_schedules SET completed_at=CAST(strftime('%s','now') AS INTEGER) WHERE state IN ('done','failed') AND completed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_ticket_outbox_job_claim ON ticket_outbox(status,available_at,lease_until);
CREATE INDEX IF NOT EXISTS idx_ticket_outbox_job_retention ON ticket_outbox(status,completed_at);
CREATE INDEX IF NOT EXISTS idx_ticket_schedules_job_claim ON ticket_schedules(status,due_at,lease_until);
CREATE INDEX IF NOT EXISTS idx_ticket_schedules_job_retention ON ticket_schedules(status,completed_at);
CREATE INDEX IF NOT EXISTS idx_reaction_role_outbox_job_claim ON reaction_role_outbox(state,next_attempt_at,lease_until);
CREATE INDEX IF NOT EXISTS idx_reaction_role_outbox_job_retention ON reaction_role_outbox(state,completed_at);
CREATE INDEX IF NOT EXISTS idx_reaction_role_schedules_job_claim ON reaction_role_schedules(state,due_at,lease_until);
CREATE INDEX IF NOT EXISTS idx_reaction_role_schedules_job_retention ON reaction_role_schedules(state,completed_at);
CREATE INDEX IF NOT EXISTS idx_social_events_job_claim ON social_events(status,available_at,lease_until);
CREATE INDEX IF NOT EXISTS idx_social_events_job_retention ON social_events(status,processed_at);
CREATE INDEX IF NOT EXISTS idx_moderation_action_requests_job_claim ON moderation_action_requests(status,available_at,lease_until);
CREATE INDEX IF NOT EXISTS idx_moderation_action_requests_job_retention ON moderation_action_requests(status,completed_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_moderation_actions_job_claim ON scheduled_moderation_actions(status,due_at,lease_until);
CREATE INDEX IF NOT EXISTS idx_scheduled_moderation_actions_job_retention ON scheduled_moderation_actions(status,completed_at);
