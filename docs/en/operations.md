# Operations

Run the Discord Bot, Dashboard, and Social Worker as separate services sharing one PostgreSQL database. Keep the database, transcripts, backups, `.env`, and encryption keys outside the public web root.

Back up before upgrades. Stop the services, update dependencies, run migrations, rebuild the dashboard and documentation, then restart and verify OAuth, commands, saves, worker heartbeat, and deliveries.

Swagger UI is available at `/api/docs`; public product documentation is served at `/docs/`.
