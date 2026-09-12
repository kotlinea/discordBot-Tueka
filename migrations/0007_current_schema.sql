-- Complete current V2 schema. Runtime constructors no longer own DDL.

-- Existing current tables and data remain in place; preceding migrations handle removals.

CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS dashboard_preferences (
                    user_id INTEGER PRIMARY KEY,
                    locale TEXT NOT NULL DEFAULT 'ja' CHECK(locale IN ('ja','en')),
                    appearance TEXT NOT NULL DEFAULT 'precision' CHECK(appearance IN ('precision','community','atmosphere')),
                    color_scheme TEXT NOT NULL DEFAULT 'system' CHECK(color_scheme IN ('system','light','dark')),
                    navigation_collapsed INTEGER NOT NULL DEFAULT 0 CHECK(navigation_collapsed IN (0,1)),
                    revision INTEGER NOT NULL DEFAULT 1,
                    updated_at INTEGER NOT NULL
                );

CREATE TABLE IF NOT EXISTS dashboard_sessions (
                    session_id TEXT PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );

CREATE TABLE IF NOT EXISTS guild_modules (
    guild_id INTEGER NOT NULL, module_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)), settings_json TEXT NOT NULL DEFAULT '{}',
    revision INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (guild_id, module_id)
);

CREATE TABLE IF NOT EXISTS guild_users (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
                    PRIMARY KEY (guild_id, user_id)
                );

CREATE TABLE IF NOT EXISTS guild_voice_users (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
                    PRIMARY KEY (guild_id, user_id)
                );

CREATE TABLE IF NOT EXISTS moderation_action_requests (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    target_user_id INTEGER,
                    channel_id INTEGER,
                    action TEXT NOT NULL,
                    reason TEXT,
                    options_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at INTEGER NOT NULL,
                    completed_at INTEGER,
                    result_json TEXT,
                    dedupe_key TEXT NOT NULL UNIQUE
                );

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

CREATE TABLE IF NOT EXISTS moderation_cases (id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, moderator_id INTEGER, action TEXT NOT NULL, reason TEXT, expires_at INTEGER, dm_sent INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, source TEXT NOT NULL DEFAULT 'manual', points INTEGER NOT NULL DEFAULT 0, revoked_at INTEGER, moderation_event_id INTEGER, moderation_rule_id INTEGER);

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

CREATE TABLE IF NOT EXISTS moderation_lockdown_snapshots (
                    lockdown_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    before_json TEXT NOT NULL,
                    applied_json TEXT NOT NULL,
                    restore_status TEXT NOT NULL DEFAULT 'pending',
                    PRIMARY KEY(lockdown_id,channel_id,role_id),
                    FOREIGN KEY(lockdown_id) REFERENCES moderation_lockdowns(id) ON DELETE CASCADE
                );

CREATE TABLE IF NOT EXISTS moderation_lockdowns (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    source_event_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'active',
                    reason TEXT,
                    started_by INTEGER,
                    started_at INTEGER NOT NULL,
                    unlock_at INTEGER,
                    completed_at INTEGER,
                    last_error TEXT
                );

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

CREATE TABLE IF NOT EXISTS moderation_raid_state (
                    guild_id INTEGER PRIMARY KEY,
                    active INTEGER NOT NULL DEFAULT 0,
                    started_at INTEGER,
                    last_signal_at INTEGER,
                    source_rule_id INTEGER,
                    lockdown_id INTEGER
                );

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

CREATE TABLE IF NOT EXISTS oauth_states (
                    state TEXT PRIMARY KEY,
                    expires_at INTEGER NOT NULL
                );

CREATE TABLE IF NOT EXISTS poll_votes (message_id INTEGER NOT NULL, user_id INTEGER NOT NULL, option_index INTEGER NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY (message_id,user_id), FOREIGN KEY(message_id) REFERENCES polls(message_id) ON DELETE CASCADE);

CREATE TABLE IF NOT EXISTS polls (message_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, creator_id INTEGER NOT NULL, question TEXT NOT NULL, options_json TEXT NOT NULL, image_url TEXT, closes_at INTEGER, status TEXT NOT NULL DEFAULT 'open', created_at INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS reaction_role_access_roles (
                message_config_id INTEGER NOT NULL, role_id INTEGER NOT NULL, policy TEXT NOT NULL CHECK(policy IN ('whitelist','blacklist')),
                PRIMARY KEY(message_config_id,role_id), FOREIGN KEY(message_config_id) REFERENCES reaction_role_messages_v2(id) ON DELETE CASCADE
            );

CREATE TABLE IF NOT EXISTS reaction_role_assignments (
                message_config_id INTEGER NOT NULL, mapping_id INTEGER NOT NULL, user_id INTEGER NOT NULL, role_id INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'active', expires_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                PRIMARY KEY(message_config_id,mapping_id,user_id), FOREIGN KEY(message_config_id) REFERENCES reaction_role_messages_v2(id) ON DELETE CASCADE,
                FOREIGN KEY(mapping_id) REFERENCES reaction_role_mappings_v2(id) ON DELETE CASCADE
            );

CREATE TABLE IF NOT EXISTS reaction_role_binding_receipts (
                message_config_id INTEGER NOT NULL, user_id INTEGER NOT NULL, mapping_id INTEGER NOT NULL, created_at INTEGER NOT NULL,
                PRIMARY KEY(message_config_id,user_id), FOREIGN KEY(message_config_id) REFERENCES reaction_role_messages_v2(id) ON DELETE CASCADE,
                FOREIGN KEY(mapping_id) REFERENCES reaction_role_mappings_v2(id) ON DELETE CASCADE
            );

CREATE TABLE IF NOT EXISTS reaction_role_events (
                id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, message_config_id INTEGER, user_id INTEGER, actor_id INTEGER,
                emoji_key TEXT, role_id INTEGER, event_type TEXT NOT NULL, result TEXT NOT NULL, reason TEXT,
                details_json TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL
            );

CREATE TABLE IF NOT EXISTS reaction_role_link_groups (
                id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, name TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );

CREATE TABLE IF NOT EXISTS reaction_role_mappings_v2 (
                id INTEGER PRIMARY KEY, message_config_id INTEGER NOT NULL, emoji_key TEXT NOT NULL, emoji_display TEXT NOT NULL,
                emoji_id INTEGER, emoji_name TEXT, animated INTEGER NOT NULL DEFAULT 0, role_id INTEGER NOT NULL,
                max_members INTEGER, position INTEGER NOT NULL, UNIQUE(message_config_id,emoji_key),
                UNIQUE(message_config_id,role_id), FOREIGN KEY(message_config_id) REFERENCES reaction_role_messages_v2(id) ON DELETE CASCADE
            );

CREATE TABLE IF NOT EXISTS reaction_role_messages_v2 (
                id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, message_id INTEGER,
                name TEXT NOT NULL, source TEXT NOT NULL CHECK(source IN ('bot','external')),
                behavior_type TEXT NOT NULL, locked INTEGER NOT NULL DEFAULT 0 CHECK(locked IN (0,1)),
                access_policy TEXT NOT NULL DEFAULT 'blacklist' CHECK(access_policy IN ('whitelist','blacklist')),
                selection_limit INTEGER, temp_duration_seconds INTEGER, self_destruct_at INTEGER,
                embed_json TEXT NOT NULL DEFAULT '{}', link_group_id INTEGER, enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
                status TEXT NOT NULL DEFAULT 'pending', last_error TEXT, revision INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                UNIQUE(guild_id,message_id), FOREIGN KEY(link_group_id) REFERENCES reaction_role_link_groups(id) ON DELETE SET NULL
            );

CREATE TABLE IF NOT EXISTS reaction_role_outbox (
                id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, message_config_id INTEGER, action TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'pending', lease_owner TEXT, lease_until INTEGER,
                attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at INTEGER NOT NULL DEFAULT 0, last_error TEXT, created_at INTEGER NOT NULL
            );

CREATE TABLE IF NOT EXISTS reaction_role_recovery (
                guild_id INTEGER NOT NULL, deleted_message_id INTEGER NOT NULL, snapshot_json TEXT NOT NULL,
                created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, PRIMARY KEY(guild_id,deleted_message_id)
            );

CREATE TABLE IF NOT EXISTS reaction_role_schedules (
                id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, message_config_id INTEGER, mapping_id INTEGER, user_id INTEGER,
                kind TEXT NOT NULL, due_at INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'pending', lease_owner TEXT, lease_until INTEGER,
                attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, created_at INTEGER NOT NULL,
                UNIQUE(kind,message_config_id,mapping_id,user_id,due_at)
            );

CREATE TABLE IF NOT EXISTS reaction_role_settings (
                guild_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
                log_channel_id INTEGER, denial_dm INTEGER NOT NULL DEFAULT 1 CHECK(denial_dm IN (0,1)),
                denial_dm_cooldown_seconds INTEGER NOT NULL DEFAULT 300, audit_retention_days INTEGER NOT NULL DEFAULT 90,
                revision INTEGER NOT NULL DEFAULT 1, updated_at INTEGER NOT NULL
            );

CREATE TABLE IF NOT EXISTS safe_browsing_cache (url_hash TEXT PRIMARY KEY, unsafe INTEGER NOT NULL, expires_at INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS scheduled_moderation_actions (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    due_at INTEGER NOT NULL,
                    reason TEXT,
                    case_id INTEGER,
                    completed_at INTEGER,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                );

CREATE TABLE IF NOT EXISTS social_connections (id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, provider TEXT NOT NULL, account_id TEXT NOT NULL, account_name TEXT NOT NULL, access_token_encrypted TEXT NOT NULL, refresh_token_encrypted TEXT, expires_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, UNIQUE(guild_id, provider, account_id));

CREATE TABLE IF NOT EXISTS social_deliveries (id INTEGER PRIMARY KEY, subscription_id INTEGER NOT NULL, event_key TEXT NOT NULL, discord_channel_id INTEGER NOT NULL, discord_message_id INTEGER, state TEXT NOT NULL DEFAULT 'sent', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at INTEGER NOT NULL DEFAULT 0, last_error TEXT, UNIQUE(subscription_id, event_key));

CREATE TABLE IF NOT EXISTS social_events (id INTEGER PRIMARY KEY, provider TEXT NOT NULL, event_key TEXT NOT NULL UNIQUE, account_id TEXT NOT NULL, payload_json TEXT NOT NULL, received_at INTEGER NOT NULL, processed_at INTEGER, event_type TEXT NOT NULL DEFAULT 'post', external_event_id TEXT, occurred_at INTEGER, status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, available_at INTEGER NOT NULL DEFAULT 0, lease_owner TEXT, lease_until INTEGER, last_error TEXT);

CREATE TABLE IF NOT EXISTS social_live_messages (subscription_id INTEGER NOT NULL, provider TEXT NOT NULL, account_id TEXT NOT NULL, discord_channel_id INTEGER NOT NULL, discord_message_id INTEGER NOT NULL, PRIMARY KEY(subscription_id, provider, account_id));

CREATE TABLE IF NOT EXISTS social_oauth_states (state TEXT PRIMARY KEY, guild_id INTEGER NOT NULL, provider TEXT NOT NULL, expires_at INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS "social_subscriptions" (id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, provider TEXT NOT NULL, account_id TEXT NOT NULL, account_name TEXT NOT NULL, channel_id INTEGER NOT NULL, role_id INTEGER, events_json TEXT NOT NULL DEFAULT '[]', enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)), created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, target_id INTEGER, event_channels_json TEXT NOT NULL DEFAULT '{}', templates_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'pending', last_error TEXT, revision INTEGER NOT NULL DEFAULT 1, UNIQUE(guild_id, provider, account_id));

CREATE TABLE IF NOT EXISTS social_targets (
                    id INTEGER PRIMARY KEY,
                    provider TEXT NOT NULL,
                    account_key TEXT NOT NULL,
                    external_id TEXT,
                    handle TEXT,
                    display_name TEXT,
                    avatar_url TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    cursor_json TEXT NOT NULL DEFAULT '{}',
                    last_error TEXT,
                    last_checked_at INTEGER,
                    next_check_at INTEGER NOT NULL DEFAULT 0,
                    lease_owner TEXT,
                    lease_until INTEGER,
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(provider,account_key)
                );

CREATE TABLE IF NOT EXISTS social_worker_state (
                    worker_name TEXT PRIMARY KEY,
                    heartbeat_at INTEGER NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
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

CREATE TABLE IF NOT EXISTS suggestion_votes (
    suggestion_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    value INTEGER NOT NULL CHECK(value IN (-1, 1)),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY(suggestion_id, user_id),
    FOREIGN KEY(suggestion_id) REFERENCES suggestions(id) ON DELETE CASCADE
);

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

CREATE TABLE IF NOT EXISTS temporary_voice_channels (channel_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, owner_id INTEGER NOT NULL, created_at INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS ticket_attachments (
                    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, discord_attachment_id INTEGER NOT NULL,
                    filename TEXT NOT NULL, content_type TEXT, byte_size INTEGER NOT NULL, backend TEXT NOT NULL,
                    object_key TEXT NOT NULL, content_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ready', created_at INTEGER NOT NULL,
                    UNIQUE(ticket_id,discord_attachment_id)
                );

CREATE TABLE IF NOT EXISTS ticket_audit_events (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, ticket_id INTEGER, actor_id INTEGER, event_type TEXT NOT NULL,
                    detail_json TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL
                );

CREATE TABLE IF NOT EXISTS ticket_blacklist (
                    guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, reason TEXT, created_by INTEGER, created_at INTEGER NOT NULL,
                    PRIMARY KEY(guild_id,user_id)
                );

CREATE TABLE IF NOT EXISTS ticket_close_requests (
                    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, requested_by INTEGER NOT NULL, reason TEXT, status TEXT NOT NULL DEFAULT 'pending',
                    expires_at INTEGER NOT NULL, resolved_by INTEGER, resolved_at INTEGER, created_at INTEGER NOT NULL
                );

CREATE TABLE IF NOT EXISTS ticket_counters (guild_id INTEGER PRIMARY KEY, next_number INTEGER NOT NULL DEFAULT 1);

CREATE TABLE IF NOT EXISTS ticket_feedback (
                    ticket_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, rating INTEGER NOT NULL, comment_encrypted TEXT,
                    form_id INTEGER, answers_encrypted_json TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL
                );

CREATE TABLE IF NOT EXISTS ticket_forms (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, name TEXT NOT NULL, title TEXT NOT NULL,
                    fields_json TEXT NOT NULL DEFAULT '[]', revision INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                    UNIQUE(guild_id,name)
                );

CREATE TABLE IF NOT EXISTS ticket_guild_settings (
                    guild_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, open_limit INTEGER NOT NULL DEFAULT 1,
                    language TEXT NOT NULL DEFAULT 'ja', log_channel_id INTEGER, transcript_channel_id INTEGER,
                    transcript_retention_days INTEGER NOT NULL DEFAULT 365, close_dm INTEGER NOT NULL DEFAULT 1,
                    default_auto_close_json TEXT NOT NULL DEFAULT '{}', revision INTEGER NOT NULL DEFAULT 1, updated_at INTEGER NOT NULL
                );

CREATE TABLE IF NOT EXISTS ticket_messages (
                    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, discord_message_id INTEGER, author_id INTEGER, author_name TEXT,
                    kind TEXT NOT NULL DEFAULT 'message', encrypted_content TEXT, metadata_json TEXT NOT NULL DEFAULT '{}',
                    edited_at INTEGER, deleted_at INTEGER, created_at INTEGER NOT NULL, UNIQUE(ticket_id,discord_message_id)
                );

CREATE TABLE IF NOT EXISTS ticket_on_call (
                    guild_id INTEGER NOT NULL, team_id INTEGER NOT NULL, user_id INTEGER NOT NULL, enabled_at INTEGER NOT NULL,
                    PRIMARY KEY(guild_id,team_id,user_id)
                );

CREATE TABLE IF NOT EXISTS ticket_orphans (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, ticket_id INTEGER, container_id INTEGER NOT NULL,
                    resource_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', reason TEXT,
                    created_at INTEGER NOT NULL, recovered_at INTEGER, UNIQUE(guild_id,container_id)
                );

CREATE TABLE IF NOT EXISTS ticket_outbox (
                    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, action TEXT NOT NULL, actor_id INTEGER NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                    available_at INTEGER NOT NULL, lease_owner TEXT, lease_until INTEGER, last_error TEXT, created_at INTEGER NOT NULL, completed_at INTEGER
                );

CREATE TABLE IF NOT EXISTS ticket_panel_messages (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, name TEXT NOT NULL, channel_id INTEGER NOT NULL, message_id INTEGER,
                    title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '#5865F2',
                    panel_ids_json TEXT NOT NULL DEFAULT '[]', config_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'draft', last_error TEXT,
                    lease_owner TEXT, lease_until INTEGER, revision INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, previous_channel_id INTEGER, previous_message_id INTEGER, UNIQUE(guild_id,name)
                );

CREATE TABLE IF NOT EXISTS ticket_panels (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                    mode TEXT NOT NULL, form_id INTEGER, team_id INTEGER, category_id INTEGER, thread_parent_channel_id INTEGER,
                    staff_notification_channel_id INTEGER, config_json TEXT NOT NULL DEFAULT '{}', enabled INTEGER NOT NULL DEFAULT 1,
                    revision INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, archived_at INTEGER, UNIQUE(guild_id,name)
                );

CREATE TABLE IF NOT EXISTS ticket_participants (
                    ticket_id INTEGER NOT NULL, subject_type TEXT NOT NULL, subject_id INTEGER NOT NULL, access TEXT NOT NULL DEFAULT 'member',
                    added_by INTEGER, created_at INTEGER NOT NULL, PRIMARY KEY(ticket_id,subject_type,subject_id)
                );

CREATE TABLE IF NOT EXISTS ticket_schedules (
                    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, kind TEXT NOT NULL, due_at INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
                    created_at INTEGER NOT NULL, completed_at INTEGER, UNIQUE(ticket_id,kind)
                );

CREATE TABLE IF NOT EXISTS ticket_staff_teams (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, name TEXT NOT NULL, role_ids_json TEXT NOT NULL DEFAULT '[]',
                    user_ids_json TEXT NOT NULL DEFAULT '[]', admin_user_ids_json TEXT NOT NULL DEFAULT '[]', notification_channel_id INTEGER,
                    enabled INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                    UNIQUE(guild_id,name)
                );

CREATE TABLE IF NOT EXISTS ticket_tags (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, name TEXT NOT NULL, content TEXT NOT NULL,
                    created_by INTEGER, revision INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                    UNIQUE(guild_id,name)
                );

CREATE TABLE IF NOT EXISTS ticket_transcripts (
                    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, version INTEGER NOT NULL DEFAULT 1, backend TEXT NOT NULL,
                    object_key TEXT NOT NULL, content_hash TEXT NOT NULL, byte_size INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'ready',
                    last_error TEXT, expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL, UNIQUE(ticket_id,version)
                );

CREATE TABLE IF NOT EXISTS tickets_v2 (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, ticket_number INTEGER NOT NULL, panel_id INTEGER, opener_id INTEGER NOT NULL,
                    interaction_id TEXT, mode TEXT NOT NULL, discord_container_id INTEGER, parent_channel_id INTEGER, status TEXT NOT NULL DEFAULT 'creating',
                    claimed_by INTEGER, close_reason TEXT, closed_by INTEGER, form_answers_json TEXT NOT NULL DEFAULT '{}',
                    auto_close_excluded INTEGER NOT NULL DEFAULT 0, last_user_message_at INTEGER, last_message_at INTEGER,
                    notes_thread_id INTEGER, closing_at INTEGER, awaiting_return_category_id INTEGER, created_at INTEGER NOT NULL, opened_at INTEGER, closed_at INTEGER, deleted_at INTEGER, revision INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(guild_id,ticket_number), UNIQUE(interaction_id)
                );

CREATE TABLE IF NOT EXISTS trust_events (id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, category TEXT NOT NULL, weight INTEGER NOT NULL, reason TEXT, created_at INTEGER NOT NULL);

-- tueka: add-column-if-missing
ALTER TABLE polls ADD COLUMN image_url TEXT;

-- tueka: add-column-if-missing
ALTER TABLE moderation_cases ADD COLUMN moderation_event_id INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE moderation_cases ADD COLUMN moderation_rule_id INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE moderation_cases ADD COLUMN source TEXT NOT NULL DEFAULT 'manual';

-- tueka: add-column-if-missing
ALTER TABLE moderation_cases ADD COLUMN points INTEGER NOT NULL DEFAULT 0;

-- tueka: add-column-if-missing
ALTER TABLE moderation_cases ADD COLUMN revoked_at INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE moderation_points ADD COLUMN moderation_rule_id INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE moderation_points ADD COLUMN moderation_event_id INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE guild_modules ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;

-- tueka: add-column-if-missing
ALTER TABLE social_subscriptions ADD COLUMN target_id INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE social_subscriptions ADD COLUMN event_channels_json TEXT NOT NULL DEFAULT '{}';

-- tueka: add-column-if-missing
ALTER TABLE social_subscriptions ADD COLUMN templates_json TEXT NOT NULL DEFAULT '{}';

-- tueka: add-column-if-missing
ALTER TABLE social_subscriptions ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';

-- tueka: add-column-if-missing
ALTER TABLE social_subscriptions ADD COLUMN last_error TEXT;

-- tueka: add-column-if-missing
ALTER TABLE social_subscriptions ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;

-- tueka: add-column-if-missing
ALTER TABLE social_events ADD COLUMN event_type TEXT NOT NULL DEFAULT 'post';

-- tueka: add-column-if-missing
ALTER TABLE social_events ADD COLUMN external_event_id TEXT;

-- tueka: add-column-if-missing
ALTER TABLE social_events ADD COLUMN occurred_at INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE social_events ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';

-- tueka: add-column-if-missing
ALTER TABLE social_events ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;

-- tueka: add-column-if-missing
ALTER TABLE social_events ADD COLUMN available_at INTEGER NOT NULL DEFAULT 0;

-- tueka: add-column-if-missing
ALTER TABLE social_events ADD COLUMN lease_owner TEXT;

-- tueka: add-column-if-missing
ALTER TABLE social_events ADD COLUMN lease_until INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE social_events ADD COLUMN last_error TEXT;

-- tueka: add-column-if-missing
ALTER TABLE social_deliveries ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;

-- tueka: add-column-if-missing
ALTER TABLE social_deliveries ADD COLUMN next_attempt_at INTEGER NOT NULL DEFAULT 0;

-- tueka: add-column-if-missing
ALTER TABLE social_deliveries ADD COLUMN last_error TEXT;

-- tueka: add-column-if-missing
ALTER TABLE reaction_role_messages_v2 ADD COLUMN access_policy TEXT NOT NULL DEFAULT 'blacklist';

-- tueka: add-column-if-missing
ALTER TABLE tickets_v2 ADD COLUMN notes_thread_id INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE tickets_v2 ADD COLUMN closing_at INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE tickets_v2 ADD COLUMN awaiting_return_category_id INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE ticket_panel_messages ADD COLUMN lease_owner TEXT;

-- tueka: add-column-if-missing
ALTER TABLE ticket_panel_messages ADD COLUMN lease_until INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE ticket_panel_messages ADD COLUMN config_json TEXT NOT NULL DEFAULT '{}';

-- tueka: add-column-if-missing
ALTER TABLE ticket_panel_messages ADD COLUMN previous_channel_id INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE ticket_panel_messages ADD COLUMN previous_message_id INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE ticket_panels ADD COLUMN archived_at INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE ticket_feedback ADD COLUMN form_id INTEGER;

-- tueka: add-column-if-missing
ALTER TABLE ticket_feedback ADD COLUMN answers_encrypted_json TEXT NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_moderation_action_requests_pending ON moderation_action_requests(status,created_at);

CREATE INDEX IF NOT EXISTS idx_moderation_events_expiry ON moderation_events(evidence_expires_at);

CREATE INDEX IF NOT EXISTS idx_moderation_events_guild_created ON moderation_events(guild_id,created_at DESC);

CREATE INDEX IF NOT EXISTS idx_moderation_events_target ON moderation_events(guild_id,target_user_id,created_at DESC);

CREATE INDEX IF NOT EXISTS idx_moderation_lockdowns_active ON moderation_lockdowns(guild_id,status,unlock_at);

CREATE INDEX IF NOT EXISTS idx_moderation_points_active ON moderation_points(guild_id, user_id, expires_at, revoked_at);

CREATE INDEX IF NOT EXISTS idx_moderation_rules_guild ON moderation_rules(guild_id,family,enabled,priority,id);

CREATE INDEX IF NOT EXISTS idx_rr_assignments_due ON reaction_role_assignments(state,expires_at);

CREATE INDEX IF NOT EXISTS idx_rr_events_expiry ON reaction_role_events(expires_at);

CREATE INDEX IF NOT EXISTS idx_rr_events_guild ON reaction_role_events(guild_id,created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rr_messages_guild ON reaction_role_messages_v2(guild_id,enabled,id);

CREATE INDEX IF NOT EXISTS idx_rr_outbox_due ON reaction_role_outbox(state,next_attempt_at,lease_until);

CREATE INDEX IF NOT EXISTS idx_rr_schedules_due ON reaction_role_schedules(state,due_at,lease_until);

CREATE INDEX IF NOT EXISTS idx_scheduled_moderation_due ON scheduled_moderation_actions(completed_at, due_at);

CREATE INDEX IF NOT EXISTS idx_social_targets_due ON social_targets(status,next_check_at,lease_until);

CREATE INDEX IF NOT EXISTS idx_suggestion_events_guild_created ON suggestion_events(guild_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_suggestions_guild_created ON suggestions(guild_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_suggestions_message ON suggestions(guild_id, message_id) WHERE message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ticket_messages_cursor ON ticket_messages(ticket_id,id);

CREATE INDEX IF NOT EXISTS idx_ticket_outbox_due ON ticket_outbox(status,available_at,lease_until);

CREATE INDEX IF NOT EXISTS idx_ticket_schedules_due ON ticket_schedules(status,due_at);

CREATE INDEX IF NOT EXISTS idx_tickets_v2_container ON tickets_v2(discord_container_id);

CREATE INDEX IF NOT EXISTS idx_tickets_v2_guild_status ON tickets_v2(guild_id,status,created_at);
