-- Schema-only fixture from the pre-removal database; contains no user rows.
CREATE TABLE guild_users (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
                    warn INTEGER NOT NULL DEFAULT 0 CHECK (warn >= 0),
                    PRIMARY KEY (guild_id, user_id)
                );
CREATE TABLE moderation_cases (id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, moderator_id INTEGER, action TEXT NOT NULL, reason TEXT, expires_at INTEGER, dm_sent INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, automod_event_id INTEGER, rule_id INTEGER, source TEXT NOT NULL DEFAULT 'manual', points INTEGER NOT NULL DEFAULT 0, revoked_at INTEGER, moderation_event_id INTEGER, moderation_rule_id INTEGER);
CREATE TABLE moderation_points (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    points INTEGER NOT NULL CHECK(points > 0),
                    reason TEXT,
                    rule_id INTEGER,
                    automod_event_id INTEGER,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER,
                    revoked_at INTEGER, moderation_rule_id INTEGER, moderation_event_id INTEGER,
                    FOREIGN KEY(rule_id) REFERENCES automod_rules(id) ON DELETE SET NULL,
                    FOREIGN KEY(automod_event_id) REFERENCES automod_events(id) ON DELETE SET NULL
                );
CREATE TABLE moderation_rules (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    family TEXT NOT NULL CHECK(family IN ('automod','anti_spam','anti_raid','infraction')),
                    event_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
                    mode TEXT NOT NULL DEFAULT 'enforce' CHECK(mode IN ('monitor','enforce')),
                    priority INTEGER NOT NULL DEFAULT 100,
                    stop_on_match INTEGER NOT NULL DEFAULT 0 CHECK(stop_on_match IN (0,1)),
                    trigger_type TEXT NOT NULL,
                    trigger_config_json TEXT NOT NULL DEFAULT '{}',
                    conditions_json TEXT NOT NULL DEFAULT '{}',
                    exemptions_json TEXT NOT NULL DEFAULT '{}',
                    actions_json TEXT NOT NULL DEFAULT '[]',
                    revision INTEGER NOT NULL DEFAULT 1,
                    legacy_rule_id INTEGER UNIQUE,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
CREATE TABLE moderation_events (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    rule_id INTEGER,
                    family TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    actor_id INTEGER,
                    actor_kind TEXT NOT NULL DEFAULT 'human',
                    target_user_id INTEGER,
                    channel_id INTEGER,
                    target_id INTEGER,
                    reason TEXT NOT NULL,
                    evidence_text TEXT,
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    mode TEXT NOT NULL DEFAULT 'enforce',
                    case_id INTEGER,
                    created_at INTEGER NOT NULL,
                    evidence_expires_at INTEGER,
                    dedupe_key TEXT,
                    UNIQUE(guild_id,dedupe_key),
                    FOREIGN KEY(rule_id) REFERENCES moderation_rules(id) ON DELETE SET NULL
                );
CREATE TABLE moderation_action_results (
                    id INTEGER PRIMARY KEY,
                    event_id INTEGER NOT NULL,
                    sequence INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    case_id INTEGER,
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL,
                    UNIQUE(event_id,sequence),
                    FOREIGN KEY(event_id) REFERENCES moderation_events(id) ON DELETE CASCADE
                );
CREATE TABLE automod_rules (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
                    mode TEXT NOT NULL DEFAULT 'enforce' CHECK(mode IN ('monitor','enforce')),
                    priority INTEGER NOT NULL DEFAULT 100,
                    stop_on_match INTEGER NOT NULL DEFAULT 0 CHECK(stop_on_match IN (0,1)),
                    trigger_type TEXT NOT NULL,
                    trigger_config_json TEXT NOT NULL DEFAULT '{}',
                    conditions_json TEXT NOT NULL DEFAULT '{}',
                    exemptions_json TEXT NOT NULL DEFAULT '{}',
                    actions_json TEXT NOT NULL DEFAULT '[]',
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
CREATE TABLE automod_events (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    rule_id INTEGER,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER,
                    trigger_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    evidence_text TEXT,
                    attachments_json TEXT NOT NULL DEFAULT '[]',
                    action_results_json TEXT NOT NULL DEFAULT '[]',
                    mode TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    evidence_expires_at INTEGER,
                    FOREIGN KEY(rule_id) REFERENCES automod_rules(id) ON DELETE SET NULL
                );
CREATE TABLE automod_migrations (guild_id INTEGER PRIMARY KEY, version INTEGER NOT NULL, migrated_at INTEGER NOT NULL);
CREATE TABLE moderation_migrations (guild_id INTEGER PRIMARY KEY,version INTEGER NOT NULL,migrated_at INTEGER NOT NULL);
CREATE INDEX idx_moderation_points_active ON moderation_points(guild_id, user_id, expires_at, revoked_at);
CREATE INDEX idx_moderation_rules_guild ON moderation_rules(guild_id,family,enabled,priority,id);
CREATE INDEX idx_moderation_events_guild_created ON moderation_events(guild_id,created_at DESC);
CREATE INDEX idx_moderation_events_target ON moderation_events(guild_id,target_user_id,created_at DESC);
CREATE INDEX idx_moderation_events_expiry ON moderation_events(evidence_expires_at);
