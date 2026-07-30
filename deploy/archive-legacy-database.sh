#!/usr/bin/env bash
# Root-run retirement of the legacy development-workspace SQLite database.
set -Eeuo pipefail
umask 027

SOURCE=/home/codexuser/churchill-data
LEGACY_DB="$SOURCE/churchill_bold.sqlite3"
DEV_DB="$SOURCE/data/churchill_dev.sqlite3"
PROD_DB=/var/lib/churchill/churchill_prod.sqlite3
ENV_FILE=/etc/churchill/production.env
BACKUP_DIR=/var/backups/churchill/legacy
EXPECTED_DATABASE_URL=sqlite:////var/lib/churchill/churchill_prod.sqlite3
EXPECTED_WORKING_DIRECTORY=/srv/churchill/current
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
ARCHIVE="$BACKUP_DIR/churchill_bold.sqlite3.$STAMP.bak"
HASH_FILE="$ARCHIVE.sha256"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[[ $EUID -eq 0 ]] || fail "Run this script as root."
[[ -f $LEGACY_DB ]] || fail "Legacy database not found: $LEGACY_DB"
[[ ! -e "$LEGACY_DB-wal" && ! -e "$LEGACY_DB-shm" && ! -e "$LEGACY_DB-journal" ]] ||
    fail "Legacy SQLite sidecar files exist; archive aborted to avoid an inconsistent backup."
[[ -f $DEV_DB ]] || fail "Development database not found: $DEV_DB"
[[ -f $PROD_DB ]] || fail "Production database not found: $PROD_DB"
[[ -r $ENV_FILE ]] || fail "Production environment is not readable: $ENV_FILE"
[[ -x $SOURCE/scripts/dev-test.sh ]] || fail "Development test wrapper is missing or not executable."
[[ ! -e $ARCHIVE && ! -e $HASH_FILE ]] || fail "Timestamped backup target already exists."

actual_database_url=$(
    sed -n 's/^DATABASE_URL=//p' "$ENV_FILE"
)
[[ $actual_database_url == "$EXPECTED_DATABASE_URL" ]] ||
    fail "$ENV_FILE does not contain the expected DATABASE_URL."

actual_working_directory=$(
    systemctl show churchill-web.service --property=WorkingDirectory --value
)
[[ $actual_working_directory == "$EXPECTED_WORKING_DIRECTORY" ]] ||
    fail "churchill-web.service does not use $EXPECTED_WORKING_DIRECTORY."
systemctl is-active --quiet churchill-web.service ||
    fail "churchill-web.service is not active."

dev_database_url=$(
    runuser -u codexuser -- bash -c \
        '. /home/codexuser/churchill-data/scripts/dev-env.sh; printf "%s" "$DATABASE_URL"'
)
[[ $dev_database_url == "sqlite:///$DEV_DB" ]] ||
    fail "Development scripts do not select $DEV_DB."

open_fds=()
for fd in /proc/[0-9]*/fd/*; do
    target=$(readlink "$fd" 2>/dev/null) || continue
    if [[ $target == "$LEGACY_DB" || $target == "$LEGACY_DB (deleted)" ]]; then
        open_fds+=("$fd -> $target")
    fi
done
if ((${#open_fds[@]})); then
    printf 'Legacy database is open:\n%s\n' "${open_fds[@]}" >&2
    exit 1
fi

install -d -o root -g root -m 0750 "$BACKUP_DIR"
legacy_hash=$(sha256sum "$LEGACY_DB" | awk '{print $1}')
mv -- "$LEGACY_DB" "$ARCHIVE"
printf '%s  %s\n' "$legacy_hash" "$(basename "$ARCHIVE")" >"$HASH_FILE"
chmod 0640 "$ARCHIVE" "$HASH_FILE"
chown root:root "$ARCHIVE" "$HASH_FILE"

(
    cd "$BACKUP_DIR"
    sha256sum --check "$(basename "$HASH_FILE")"
)

curl --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null
echo "Production /health: HTTP 200"
curl --fail --silent --show-error http://127.0.0.1:8000/ >/dev/null
echo "Production /: HTTP 200"

runuser -u codexuser -- "$SOURCE/scripts/dev-test.sh"

[[ ! -e $LEGACY_DB ]] || fail "Legacy database was recreated: $LEGACY_DB"

echo "Legacy database archived successfully."
echo "Backup: $ARCHIVE"
echo "SHA-256 record: $HASH_FILE"
echo "churchill-tunnel.service was not modified or restarted."
