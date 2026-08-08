"""One-time import of legacy data/<guild_id>.json files into SQLite."""
from config import Settings
from storage import GuildStorage


if __name__ == "__main__":
    settings = Settings.from_env()
    count = GuildStorage(settings.database_path).migrate_json(settings.data_dir)
    print(f"Migrated {count} guild JSON file(s).")
