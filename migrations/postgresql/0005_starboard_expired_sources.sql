-- Retain only the source identity after content, receipts and history expire.
-- The marker ends with its Board and cannot reconstruct already-purged IDs.
CREATE TABLE starboard_expired_sources (
    board_id BIGINT NOT NULL REFERENCES starboards(id) ON DELETE CASCADE,
    source_message_id BIGINT NOT NULL,
    PRIMARY KEY(board_id,source_message_id)
);
