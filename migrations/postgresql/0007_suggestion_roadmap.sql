ALTER TABLE suggestions ADD COLUMN category TEXT NOT NULL DEFAULT '';
ALTER TABLE suggestions ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE suggestions ADD COLUMN merged_into BIGINT REFERENCES suggestions(id) ON DELETE SET NULL;
-- Existing suggestions retain their original lifetime; only new submissions receive expiry.
ALTER TABLE suggestions ADD COLUMN expires_at BIGINT;
CREATE INDEX suggestions_merge_target ON suggestions(guild_id,merged_into);
CREATE INDEX suggestions_expiry ON suggestions(expires_at);
CREATE INDEX suggestions_tags ON suggestions USING GIN ((tags_json::jsonb));
-- A canonical zero overrides an old source vote without deleting the original vote.
ALTER TABLE suggestion_votes DROP CONSTRAINT suggestion_votes_value_check;
ALTER TABLE suggestion_votes ADD CONSTRAINT suggestion_votes_value_check CHECK(value IN (-1,0,1));
