CREATE TABLE insights_observers (
    guild_id BIGINT PRIMARY KEY,
    owner TEXT NOT NULL,
    revision INTEGER NOT NULL,
    last_seen BIGINT NOT NULL
);
CREATE TABLE insights_daily (
    guild_id BIGINT NOT NULL,
    day TEXT NOT NULL,
    messages BIGINT NOT NULL DEFAULT 0 CHECK(messages >= 0),
    joins BIGINT NOT NULL DEFAULT 0 CHECK(joins >= 0),
    leaves BIGINT NOT NULL DEFAULT 0 CHECK(leaves >= 0),
    voice_seconds BIGINT NOT NULL DEFAULT 0 CHECK(voice_seconds >= 0),
    observed_seconds INTEGER NOT NULL DEFAULT 0 CHECK(observed_seconds BETWEEN 0 AND 86400),
    first_observed BIGINT NOT NULL,
    last_observed BIGINT NOT NULL,
    expires_at BIGINT NOT NULL,
    PRIMARY KEY(guild_id,day)
);
CREATE INDEX insights_daily_expiry ON insights_daily(expires_at);
CREATE TABLE insights_seen (
    guild_id BIGINT NOT NULL,
    event_key TEXT NOT NULL,
    observed_at BIGINT NOT NULL,
    expires_at BIGINT NOT NULL,
    PRIMARY KEY(guild_id,event_key)
);
CREATE INDEX insights_seen_expiry ON insights_seen(expires_at);
CREATE TABLE insights_voice (
    guild_id BIGINT NOT NULL REFERENCES insights_observers(guild_id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    last_seen BIGINT NOT NULL,
    PRIMARY KEY(guild_id,user_id)
);
