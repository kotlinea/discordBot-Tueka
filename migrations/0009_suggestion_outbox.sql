CREATE TABLE suggestion_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suggestion_id INTEGER NOT NULL REFERENCES suggestions(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    available_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    completed_at INTEGER,
    attempts INTEGER NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_token TEXT,
    lease_until INTEGER,
    last_error TEXT,
    delivery_started INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_suggestion_outbox_claim ON suggestion_outbox(status, available_at, lease_until, id);
CREATE INDEX idx_suggestion_outbox_retention ON suggestion_outbox(status, completed_at);
INSERT INTO suggestion_outbox(suggestion_id,action,payload_json,available_at,created_at)
    SELECT id,'publish','{"recover":true}',CAST(strftime('%s','now') AS INTEGER),CAST(strftime('%s','now') AS INTEGER)
    FROM suggestions WHERE message_id IS NULL AND status IN ('pending','reviewing');
