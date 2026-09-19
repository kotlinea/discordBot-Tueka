CREATE TABLE runtime_heartbeats (
    service TEXT NOT NULL CHECK(service IN ('bot','dashboard','social-worker')),
    instance_id TEXT NOT NULL,
    observed_at DOUBLE PRECISION NOT NULL,
    ready BOOLEAN NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY(service, instance_id)
);
CREATE INDEX runtime_heartbeats_observed_idx ON runtime_heartbeats(observed_at);
