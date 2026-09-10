CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER,
    author_id INTEGER NOT NULL,
    answers_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewer_id INTEGER,
    reviewed_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_suggestions_guild_created ON suggestions(guild_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_suggestions_message ON suggestions(guild_id, message_id) WHERE message_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS suggestion_votes (
    suggestion_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    value INTEGER NOT NULL CHECK(value IN (-1, 1)),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY(suggestion_id, user_id),
    FOREIGN KEY(suggestion_id) REFERENCES suggestions(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS suggestion_events (
    id INTEGER PRIMARY KEY,
    suggestion_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    actor_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL,
    FOREIGN KEY(suggestion_id) REFERENCES suggestions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_suggestion_events_guild_created ON suggestion_events(guild_id, created_at DESC);
