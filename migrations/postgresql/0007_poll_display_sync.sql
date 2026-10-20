-- Existing polls need one reconciliation, including already closed results.
ALTER TABLE polls ADD COLUMN display_revision BIGINT NOT NULL DEFAULT 1;
ALTER TABLE polls ADD COLUMN synced_revision BIGINT NOT NULL DEFAULT 0;
CREATE INDEX polls_pending_display ON polls(message_id)
    WHERE display_revision <> synced_revision;
