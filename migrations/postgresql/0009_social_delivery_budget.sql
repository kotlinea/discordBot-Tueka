ALTER TABLE social_deliveries
    ADD COLUMN dispatch_accounted_attempts BIGINT NOT NULL DEFAULT 0;

-- Attempts made before this checkpoint existed are not new dispatch progress.
UPDATE social_deliveries SET dispatch_accounted_attempts=attempts;
