CREATE TABLE IF NOT EXISTS resource_leases (
    namespace TEXT NOT NULL,
    resource_key TEXT NOT NULL,
    token TEXT NOT NULL,
    lease_until INTEGER NOT NULL,
    PRIMARY KEY(namespace, resource_key)
);
