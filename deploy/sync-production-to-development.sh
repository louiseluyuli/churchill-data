#!/usr/bin/env bash
# Root-run, one-way consistent production snapshot into development.
set -Eeuo pipefail
umask 027

SOURCE=/home/codexuser/churchill-data
PROD_DB=/var/lib/churchill/churchill_prod.sqlite3
DEV_DB="$SOURCE/data/churchill_dev.sqlite3"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

[[ $EUID -eq 0 ]] || { echo "Run this script as root." >&2; exit 1; }
[[ -f $PROD_DB ]] || { echo "Production database not found." >&2; exit 1; }
install -d -o codexuser -g codexuser -m 0750 "$SOURCE/data" "$SOURCE/data/backups"
if [[ -f $DEV_DB ]]; then
    "$SOURCE/.venv/bin/python" "$SOURCE/deploy/sqlite_backup.py" \
        "$DEV_DB" "$SOURCE/data/backups/churchill_dev-$STAMP.sqlite3"
    chown codexuser:codexuser "$SOURCE/data/backups/churchill_dev-$STAMP.sqlite3"
    chmod 0640 "$SOURCE/data/backups/churchill_dev-$STAMP.sqlite3"
fi
temporary="$SOURCE/data/.churchill_dev-$STAMP.sqlite3"
"$SOURCE/.venv/bin/python" "$SOURCE/deploy/sqlite_backup.py" "$PROD_DB" "$temporary"
chown codexuser:codexuser "$temporary"
chmod 0640 "$temporary"
mv -f "$temporary" "$DEV_DB"
echo "Development mirror synchronized from a consistent production snapshot."
