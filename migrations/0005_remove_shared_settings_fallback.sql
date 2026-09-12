-- Preserve values currently exposed by V2 before removing runtime fallback.
-- Canonical helper schemas allow application to an empty database as well.
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY, management_channel_id INTEGER,
    welcome_channel_id INTEGER, default_role_id INTEGER
);
CREATE TABLE IF NOT EXISTS guild_modules (
    guild_id INTEGER NOT NULL, module_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)), settings_json TEXT NOT NULL DEFAULT '{}',
    revision INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (guild_id, module_id)
);
CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- Missing module rows previously exposed disabled candidates with revision zero.
INSERT OR IGNORE INTO guild_modules(guild_id,module_id,enabled,settings_json,revision)
SELECT guild_id,'welcome',0,json_object('welcome_channel_id',welcome_channel_id),0 FROM guild_settings;
INSERT OR IGNORE INTO guild_modules(guild_id,module_id,enabled,settings_json,revision)
SELECT guild_id,'autorole',0,json_object('default_role_id',default_role_id),0 FROM guild_settings;
INSERT OR IGNORE INTO guild_modules(guild_id,module_id,enabled,settings_json,revision)
SELECT guild_id,'leveling',0,json_object('text_notification_channel_id',management_channel_id),0 FROM guild_settings;

-- An explicit JSON null overrides the shared value and must remain null.
UPDATE guild_modules SET settings_json=json_set(settings_json,'$.text_notification_channel_id',
    (SELECT management_channel_id FROM guild_settings WHERE guild_id=guild_modules.guild_id))
WHERE module_id='leveling' AND json_type(settings_json,'$.text_notification_channel_id') IS NULL;

-- Only existing audit rows without any category toggle used message-only logging.
UPDATE guild_modules SET settings_json=json_set(settings_json,'$.log_message',json('true'))
WHERE module_id='audit_log' AND json_extract(settings_json,'$.management_channel_id')
    AND json_type(settings_json,'$.log_message') IS NULL
    AND json_type(settings_json,'$.log_voice') IS NULL
    AND json_type(settings_json,'$.log_channel') IS NULL
    AND json_type(settings_json,'$.log_member') IS NULL
    AND json_type(settings_json,'$.log_role') IS NULL
    AND json_type(settings_json,'$.log_server') IS NULL;
INSERT OR IGNORE INTO guild_modules(guild_id,module_id,enabled,settings_json,revision)
SELECT guild_id,'audit_log',0,json_object('management_channel_id',management_channel_id),0 FROM guild_settings;

DROP TABLE guild_settings;
DELETE FROM app_metadata WHERE key='json_migration_v1';
