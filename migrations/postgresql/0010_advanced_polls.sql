-- Preserve published messages while giving drafts an identity before publication.
ALTER TABLE polls ADD COLUMN id BIGSERIAL UNIQUE;
ALTER TABLE poll_votes DROP CONSTRAINT poll_votes_message_id_fkey;
ALTER TABLE polls DROP CONSTRAINT polls_pkey;
ALTER TABLE polls ALTER COLUMN message_id DROP NOT NULL;
ALTER TABLE polls ADD PRIMARY KEY(id);
ALTER TABLE polls ADD UNIQUE(message_id);
ALTER TABLE polls ADD COLUMN description TEXT NOT NULL DEFAULT '';
ALTER TABLE polls ADD COLUMN config_json JSONB NOT NULL DEFAULT '{}';
ALTER TABLE polls ADD COLUMN revision BIGINT NOT NULL DEFAULT 1;
ALTER TABLE polls ADD COLUMN ever_voted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE polls ADD COLUMN published_at BIGINT;
ALTER TABLE polls ADD COLUMN scheduled_at BIGINT;
ALTER TABLE polls ADD COLUMN duration_seconds BIGINT;
ALTER TABLE polls ADD COLUMN closed_at BIGINT;
ALTER TABLE polls ADD COLUMN request_key TEXT;
ALTER TABLE polls ADD UNIQUE(guild_id,request_key);
ALTER TABLE polls ADD CONSTRAINT polls_status CHECK(status IN ('draft','scheduled','publishing','open','closed','deleted','cancelled'));
UPDATE polls SET published_at=created_at,closed_at=CASE WHEN status='closed' THEN COALESCE(closes_at,created_at) END,
    config_json=jsonb_build_object('question',question,'description','','options',options_json::jsonb,
    'emojis',(SELECT jsonb_agg(''::text) FROM jsonb_array_elements(options_json::jsonb)),
    'max_choices',1,'mode','anonymous','ui','buttons','image_url',image_url,'color',5793266,
    'allowed_roles','[]'::jsonb,'denied_roles','[]'::jsonb,'denied_users','[]'::jsonb,'max_participants',NULL,
    'visibility','{"open":{"counts":"everyone","ranking":"everyone","total":"everyone","participants":"hidden","ballots":"hidden"},"closed":{"counts":"everyone","ranking":"everyone","total":"everyone","participants":"hidden","ballots":"hidden"}}'::jsonb);
CREATE TABLE poll_ballots (
    poll_id BIGINT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    choices JSONB NOT NULL CHECK(jsonb_typeof(choices)='array' AND jsonb_array_length(choices) BETWEEN 1 AND 20),
    weight INTEGER NOT NULL CHECK(weight BETWEEN 1 AND 100),
    updated_at BIGINT NOT NULL,
    PRIMARY KEY(poll_id,user_id)
);
INSERT INTO poll_ballots SELECT p.id,v.user_id,jsonb_build_array(v.option_index),1,v.created_at
    FROM poll_votes v JOIN polls p ON p.message_id=v.message_id;
UPDATE polls SET ever_voted=TRUE WHERE id IN (SELECT poll_id FROM poll_ballots);
DROP TABLE poll_votes;
CREATE INDEX polls_due ON polls(status,closes_at);
CREATE INDEX polls_guild ON polls(guild_id,id);
CREATE TABLE poll_events (
    id BIGSERIAL PRIMARY KEY,
    poll_id BIGINT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    actor_id BIGINT,
    event_type TEXT NOT NULL,
    created_at BIGINT NOT NULL
);
