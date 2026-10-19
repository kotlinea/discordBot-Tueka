ALTER TABLE insights_observers ADD COLUMN started_at BIGINT NOT NULL DEFAULT 0;
UPDATE insights_observers SET started_at=last_seen;
