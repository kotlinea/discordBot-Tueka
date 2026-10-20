-- Answer-free evidence supports the current cooldown, including later increases.
CREATE TABLE application_cooldowns (
    guild_id BIGINT NOT NULL,
    form_id BIGINT NOT NULL REFERENCES application_forms(id) ON DELETE CASCADE,
    author_id BIGINT NOT NULL,
    submitted_at BIGINT NOT NULL,
    PRIMARY KEY(guild_id, form_id, author_id)
);
CREATE INDEX application_cooldowns_submitted ON application_cooldowns(submitted_at);
INSERT INTO application_cooldowns(guild_id,form_id,author_id,submitted_at)
SELECT guild_id,form_id,author_id,MAX(created_at)
FROM applications
WHERE created_at > EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT - 2592000
GROUP BY guild_id,form_id,author_id;
