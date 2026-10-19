ALTER TABLE suggestions ADD COLUMN review_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE suggestions ADD COLUMN discussion_thread_id BIGINT;
ALTER TABLE suggestions ADD COLUMN implemented_at BIGINT;
