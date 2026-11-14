"""Seed datasets, versions and source metadata from the current committed catalog.

Run from services/api: uv run python ../../database/seeds/seed_catalog.py
Apply Postgres migrations first. Uses the same idempotent upsert as API startup.
"""

from gridstorm_api.catalog import NetworkCatalog
from gridstorm_api.config import Settings
from gridstorm_api.db.session import Database
from gridstorm_api.sync import sync_catalog


def main() -> None:
    settings = Settings.from_env()
    catalog = NetworkCatalog(settings.networks_dir)
    entries = catalog.entries()
    if catalog.errors or not entries:
        raise RuntimeError(f"catalog is empty or invalid: {catalog.errors}")
    db = Database(settings.resolved_database_url)
    try:
        with db.session() as session:
            versions = sync_catalog(session, catalog)
        print(f"seeded {len(versions)} network dataset(s): {', '.join(sorted(versions))}")
    finally:
        db.dispose()


if __name__ == "__main__":
    main()
