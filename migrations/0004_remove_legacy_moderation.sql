-- Preserve current rows while removing V1 columns and their foreign keys.

-- Child tables are copied and dropped before parents so ON DELETE cannot erase links.

CREATE TABLE IF NOT EXISTS guild_users (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
                    PRIMARY KEY (guild_id, user_id)
                );

CREATE TABLE _p1_copy_guild_users AS SELECT "guild_id","user_id","xp" FROM guild_users;

CREATE TABLE IF NOT EXISTS moderation_cases (id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, moderator_id INTEGER, action TEXT NOT NULL, reason TEXT, expires_at INTEGER, dm_sent INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, source TEXT NOT NULL DEFAULT 'manual', points INTEGER NOT NULL DEFAULT 0, revoked_at INTEGER, moderation_event_id INTEGER, moderation_rule_id INTEGER);

CREATE TABLE _p1_copy_moderation_cases AS SELECT "id","guild_id","user_id","moderator_id","action","reason","expires_at","dm_sent","created_at","source","points","revoked_at","moderation_event_id","moderation_rule_id" FROM moderation_cases;

CREATE TABLE IF NOT EXISTS moderation_points (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    points INTEGER NOT NULL CHECK(points > 0),
                    reason TEXT,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER,
                    revoked_at INTEGER, moderation_rule_id INTEGER, moderation_event_id INTEGER
                );

CREATE TABLE _p1_copy_moderation_points AS SELECT "id","guild_id","user_id","points","reason","created_at","expires_at","revoked_at","moderation_rule_id","moderation_event_id" FROM moderation_points;

CREATE TABLE IF NOT EXISTS moderation_rules (
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
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

CREATE TABLE _p1_copy_moderation_rules AS SELECT "id","guild_id","family","event_type","name","enabled","mode","priority","stop_on_match","trigger_type","trigger_config_json","conditions_json","exemptions_json","actions_json","revision","created_at","updated_at" FROM moderation_rules;

CREATE TABLE IF NOT EXISTS moderation_events (
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

CREATE TABLE _p1_copy_moderation_events AS SELECT "id","guild_id","rule_id","family","event_type","source","actor_id","actor_kind","target_user_id","channel_id","target_id","reason","evidence_text","evidence_json","mode","case_id","created_at","evidence_expires_at","dedupe_key" FROM moderation_events;

CREATE TABLE IF NOT EXISTS moderation_action_results (
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

CREATE TABLE _p1_copy_moderation_action_results AS SELECT "id","event_id","sequence","action_type","status","case_id","detail_json","created_at" FROM moderation_action_results;

DROP TABLE moderation_action_results;

DROP TABLE moderation_events;

DROP TABLE moderation_rules;

DROP TABLE moderation_points;

DROP TABLE moderation_cases;

DROP TABLE guild_users;

CREATE TABLE guild_users (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
                    PRIMARY KEY (guild_id, user_id)
                );

INSERT INTO guild_users SELECT * FROM _p1_copy_guild_users;

DROP TABLE _p1_copy_guild_users;

CREATE TABLE moderation_cases (id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, moderator_id INTEGER, action TEXT NOT NULL, reason TEXT, expires_at INTEGER, dm_sent INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, source TEXT NOT NULL DEFAULT 'manual', points INTEGER NOT NULL DEFAULT 0, revoked_at INTEGER, moderation_event_id INTEGER, moderation_rule_id INTEGER);

INSERT INTO moderation_cases SELECT * FROM _p1_copy_moderation_cases;

DROP TABLE _p1_copy_moderation_cases;

CREATE TABLE moderation_points (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    points INTEGER NOT NULL CHECK(points > 0),
                    reason TEXT,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER,
                    revoked_at INTEGER, moderation_rule_id INTEGER, moderation_event_id INTEGER
                );

INSERT INTO moderation_points SELECT * FROM _p1_copy_moderation_points;

DROP TABLE _p1_copy_moderation_points;

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
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

INSERT INTO moderation_rules SELECT * FROM _p1_copy_moderation_rules;

DROP TABLE _p1_copy_moderation_rules;

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

INSERT INTO moderation_events SELECT * FROM _p1_copy_moderation_events;

DROP TABLE _p1_copy_moderation_events;

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

INSERT INTO moderation_action_results SELECT * FROM _p1_copy_moderation_action_results;

DROP TABLE _p1_copy_moderation_action_results;

CREATE INDEX idx_moderation_points_active ON moderation_points(guild_id, user_id, expires_at, revoked_at);

CREATE INDEX idx_moderation_rules_guild ON moderation_rules(guild_id,family,enabled,priority,id);

CREATE INDEX idx_moderation_events_guild_created ON moderation_events(guild_id,created_at DESC);

CREATE INDEX idx_moderation_events_target ON moderation_events(guild_id,target_user_id,created_at DESC);

CREATE INDEX idx_moderation_events_expiry ON moderation_events(evidence_expires_at);

DROP TABLE IF EXISTS automod_events;

DROP TABLE IF EXISTS automod_rules;

DROP TABLE IF EXISTS automod_migrations;

DROP TABLE IF EXISTS moderation_migrations;
