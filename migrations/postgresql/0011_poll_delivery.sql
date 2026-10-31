ALTER TABLE polls ADD COLUMN updated_at BIGINT NOT NULL DEFAULT 0;
ALTER TABLE polls ADD COLUMN thread_id BIGINT;
ALTER TABLE polls ADD COLUMN request_json JSONB;
ALTER TABLE polls ADD COLUMN display_checked_at BIGINT NOT NULL DEFAULT 0;
ALTER TABLE polls ADD COLUMN display_enabled BOOLEAN;
UPDATE polls SET config_json=config_json || '{"announce_winner":false,"pin_on_close":false,"create_thread":false,"remove_departed_votes":false}'::jsonb;
UPDATE polls SET config_json=config_json || '{"button_style":"secondary"}'::jsonb;
UPDATE polls SET updated_at=created_at;
CREATE TABLE poll_outbox (
    id BIGSERIAL PRIMARY KEY,
    poll_id BIGINT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    guild_id BIGINT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('publish','move','announce','pin','thread','archive','stop_old')),
    channel_id BIGINT NOT NULL,
    old_message_id BIGINT,
    old_channel_id BIGINT,
    generation BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    available_at BIGINT NOT NULL,
    created_at BIGINT NOT NULL,
    completed_at BIGINT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    lease_owner TEXT,
    lease_token TEXT,
    lease_until BIGINT,
    delivery_started INTEGER NOT NULL DEFAULT 0,
    discord_receipt_id BIGINT,
    UNIQUE(poll_id,action,generation)
);
CREATE INDEX poll_outbox_due ON poll_outbox(status,available_at);
CREATE TABLE poll_setting_events (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    actor_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    created_at BIGINT NOT NULL
);
CREATE INDEX poll_setting_events_guild ON poll_setting_events(guild_id,id);
