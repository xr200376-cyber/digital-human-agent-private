#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-/etc/aivo-commercial/aivo-commercial.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "env file not found" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

BACKUP_ROOT="${COMMERCIAL_BACKUP_ROOT:-/var/backups/aivo-commercial}"
STAMP="$(date -u +%Y%m%d%H%M%S)"
DEST="$BACKUP_ROOT/$STAMP"
mkdir -p "$DEST"

pg_dump -Fc "$COMMERCIAL_DATABASE_URL" > "$DEST/commercial.pgcustom"

if [[ -n "${STORAGE_DIR:-}" && -d "$STORAGE_DIR/commercial_center/releases" ]]; then
  tar -C "$STORAGE_DIR/commercial_center" -czf "$DEST/releases.tar.gz" releases
fi

find "$BACKUP_ROOT" -maxdepth 1 -type d -mtime +14 -name '20*' -exec rm -rf {} +
echo "backup completed: $STAMP"
