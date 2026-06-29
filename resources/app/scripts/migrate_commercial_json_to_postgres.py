from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.commercial_center import CommercialCenterStore, PostgresCommercialCenterStore
from app.settings import Settings
from app.utils.files import read_json


def load_commercial_payload(storage_dir: Path) -> dict[str, Any]:
    data_path = storage_dir / "commercial_center" / "data.json"
    if not data_path.exists():
        return CommercialCenterStore(Settings(storage_dir=storage_dir))._default_data()
    loaded = read_json(data_path)
    if not isinstance(loaded, dict):
        return CommercialCenterStore(Settings(storage_dir=storage_dir))._default_data()
    default = CommercialCenterStore(Settings(storage_dir=storage_dir))._default_data()
    for key, value in default.items():
        loaded.setdefault(key, value)
    return loaded


def build_migration_summary(storage_dir: Path) -> dict[str, Any]:
    data_path = storage_dir / "commercial_center" / "data.json"
    payload = load_commercial_payload(storage_dir)
    return {
        "source_found": data_path.exists(),
        "customers": len(payload.get("customers", {})),
        "licenses": len(payload.get("licenses", {})),
        "activations": len(payload.get("activations", {})),
        "releases": len(payload.get("releases", {})),
        "audit_logs": len(payload.get("audit_logs", [])),
        "target_tables": list(PostgresCommercialCenterStore.tables),
    }


def migrate_to_postgres(storage_dir: Path, database_url: str, *, dry_run: bool = False) -> dict[str, Any]:
    summary = build_migration_summary(storage_dir)
    if dry_run:
        return {**summary, "migrated": False, "dry_run": True}
    source_store = CommercialCenterStore(Settings(storage_dir=storage_dir))
    backup = source_store.run_backup()
    payload = load_commercial_payload(storage_dir)
    target = PostgresCommercialCenterStore(
        Settings(
            storage_dir=storage_dir,
            commercial_repository_backend="postgres",
            commercial_database_url=database_url,
        )
    )
    target._save(payload)
    return {
        **summary,
        "migrated": True,
        "dry_run": False,
        "backup_status": backup["backup"]["status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate commercial JSON storage to PostgreSQL.")
    parser.add_argument("--storage-dir", default="storage", help="Aivo storage directory.")
    parser.add_argument("--database-url", default="", help="PostgreSQL connection URL.")
    parser.add_argument("--dry-run", action="store_true", help="Only print migration summary.")
    args = parser.parse_args()

    storage_dir = Path(args.storage_dir)
    if not args.dry_run and not args.database_url:
        raise SystemExit("--database-url is required unless --dry-run is used")
    result = migrate_to_postgres(storage_dir, args.database_url, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
