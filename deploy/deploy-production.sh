#!/usr/bin/env bash
# Root-run initial migration and repeatable production promotion.
set -Eeuo pipefail
umask 027

SOURCE=/home/codexuser/churchill-data
RELEASES=/srv/churchill/releases
CURRENT=/srv/churchill/current
PROD_DB=/var/lib/churchill/churchill_prod.sqlite3
DEV_DB="$SOURCE/data/churchill_dev.sqlite3"
BACKUPS=/var/backups/churchill
ENV_FILE=/etc/churchill/production.env
UNIT_FILE=/etc/systemd/system/churchill-web.service
LIVE_SOURCE="$SOURCE/churchill_bold.sqlite3"
MODE=deploy
ALLOW_DIRTY=0
REBUILD_DATABASE=0
PUBLIC_URL=${CHURCHILL_PUBLIC_URL:-}
SMOKE_PORT=8765
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
RELEASE="$RELEASES/$TIMESTAMP"
ROLLBACK_DIR=
PREVIOUS_RELEASE=
DB_REPLACED=0
SWITCHED=0
CONFIG_INSTALLED=0
SMOKE_PID=

usage() {
    echo "Usage: $0 [--initial] [--allow-dirty] [--rebuild-database] [--public-url URL]"
}

while (($#)); do
    case "$1" in
        --initial) MODE=initial ;;
        --allow-dirty) ALLOW_DIRTY=1 ;;
        --rebuild-database) REBUILD_DATABASE=1 ;;
        --public-url) shift; PUBLIC_URL=${1:?missing URL} ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
    shift
done

[[ $EUID -eq 0 ]] || { echo "Run this script as root." >&2; exit 1; }
[[ -d "$SOURCE/.git" && -f "$SOURCE/requirements.txt" ]] || {
    echo "Development source not found at $SOURCE." >&2; exit 1;
}
[[ $PUBLIC_URL =~ ^https://[a-z0-9-]+\.trycloudflare\.com/?$ ]] || {
    echo "Pass the existing Quick Tunnel URL with --public-url." >&2; exit 1;
}
PUBLIC_URL=${PUBLIC_URL%/}

cleanup() {
    if [[ -n ${SMOKE_PID:-} ]]; then
        kill "$SMOKE_PID" 2>/dev/null || true
        wait "$SMOKE_PID" 2>/dev/null || true
    fi
}

rollback() {
    result=$?
    trap - ERR
    cleanup
    if [[ $SWITCHED -eq 1 || $CONFIG_INSTALLED -eq 1 || $DB_REPLACED -eq 1 ]]; then
        echo "Deployment failed; restoring previous production state." >&2
        if [[ -n $PREVIOUS_RELEASE ]]; then
            ln -sfn "$PREVIOUS_RELEASE" "$CURRENT.rollback"
            mv -Tf "$CURRENT.rollback" "$CURRENT"
        elif [[ $SWITCHED -eq 1 && -L $CURRENT ]]; then
            rm -f "$CURRENT"
        fi
        if [[ -f "$ROLLBACK_DIR/churchill-web.service" ]]; then
            install -o root -g root -m 0644 "$ROLLBACK_DIR/churchill-web.service" "$UNIT_FILE"
        fi
        if [[ -f "$ROLLBACK_DIR/production.env" ]]; then
            install -o root -g churchill -m 0640 "$ROLLBACK_DIR/production.env" "$ENV_FILE"
        elif [[ $CONFIG_INSTALLED -eq 1 ]]; then
            rm -f "$ENV_FILE"
        fi
        if [[ $DB_REPLACED -eq 1 && -f "$ROLLBACK_DIR/production.sqlite3" ]]; then
            install -o churchill -g churchill -m 0640 "$ROLLBACK_DIR/production.sqlite3" "$PROD_DB"
        fi
        if [[ $SWITCHED -eq 1 ]]; then
            systemctl daemon-reload
            systemctl restart churchill-web.service
        fi
    fi
    exit "$result"
}
trap rollback ERR
trap cleanup EXIT

dirty=$(git -C "$SOURCE" status --short)
if [[ $MODE != initial && -n $dirty && $ALLOW_DIRTY -ne 1 ]]; then
    echo "Refusing a dirty working tree; commit it or pass --allow-dirty explicitly." >&2
    exit 1
fi

# Tests always use a disposable development-only database.
TEST_DB=$(mktemp /tmp/churchill-deploy-tests.XXXXXX.sqlite3)
trap 'rm -f "$TEST_DB"; cleanup' EXIT
runuser -u codexuser -- env DATABASE_URL="sqlite:///$TEST_DB" \
    "$SOURCE/.venv/bin/pytest" -q "$SOURCE/tests"
rm -f "$TEST_DB"

if ! id churchill >/dev/null 2>&1; then
    useradd --system --home-dir /nonexistent --no-create-home \
        --shell /usr/sbin/nologin churchill
fi
install -d -o root -g root -m 0755 /srv/churchill "$RELEASES"
install -d -o churchill -g churchill -m 0750 /var/lib/churchill
install -d -o root -g churchill -m 0750 /etc/churchill
install -d -o root -g root -m 0750 "$BACKUPS"
install -d -o root -g root -m 0755 "$RELEASE"
ROLLBACK_DIR=$(mktemp -d "$BACKUPS/rollback-$TIMESTAMP.XXXXXX")

if [[ -L $CURRENT ]]; then
    PREVIOUS_RELEASE=$(readlink -f "$CURRENT")
fi
if [[ -f $UNIT_FILE ]]; then
    cp -a "$UNIT_FILE" "$ROLLBACK_DIR/churchill-web.service"
fi
if [[ -f $ENV_FILE ]]; then
    cp -a "$ENV_FILE" "$ROLLBACK_DIR/production.env"
fi

if [[ $MODE == initial ]]; then
    [[ -f $LIVE_SOURCE ]] || { echo "Live source database missing: $LIVE_SOURCE" >&2; exit 1; }
    "$SOURCE/.venv/bin/python" "$SOURCE/deploy/sqlite_backup.py" \
        "$LIVE_SOURCE" "$BACKUPS/pre-migration-$TIMESTAMP.sqlite3"
    if [[ ! -f $PROD_DB ]]; then
        "$SOURCE/.venv/bin/python" "$SOURCE/deploy/sqlite_backup.py" "$LIVE_SOURCE" "$PROD_DB"
    fi
    chown churchill:churchill "$PROD_DB"
    chmod 0640 "$PROD_DB"
    install -d -o codexuser -g codexuser -m 0750 "$SOURCE/data"
    "$SOURCE/.venv/bin/python" "$SOURCE/deploy/sqlite_backup.py" "$PROD_DB" "$DEV_DB"
    chown codexuser:codexuser "$DEV_DB"
    chmod 0640 "$DEV_DB"
elif [[ ! -f $PROD_DB ]]; then
    echo "Production database missing: $PROD_DB" >&2
    exit 1
else
    "$SOURCE/.venv/bin/python" "$SOURCE/deploy/sqlite_backup.py" \
        "$PROD_DB" "$BACKUPS/pre-deploy-$TIMESTAMP.sqlite3"
fi

if [[ $MODE == initial ]]; then
    "$SOURCE/.venv/bin/python" "$SOURCE/deploy/validate_database.py" \
        "$PROD_DB" --baseline "$SOURCE/deploy/baseline-counts.txt"
else
    "$SOURCE/.venv/bin/python" "$SOURCE/deploy/validate_database.py" "$PROD_DB"
fi

# Archive the validated working tree, including untracked application files.
tar -C "$SOURCE" -cf - \
    --exclude=.git --exclude=.venv --exclude=venv --exclude=env \
    --exclude=data --exclude=downloads --exclude=tests --exclude='*.sqlite' \
    --exclude='*.sqlite3' --exclude='*.db' --exclude='__pycache__' \
    --exclude=.pytest_cache --exclude=.mypy_cache --exclude=.ruff_cache \
    --exclude='*.pyc' --exclude='.env' --exclude='.env.*' \
    --exclude=backups --exclude='release-manifest.json' . |
    tar -C "$RELEASE" -xf -
"$SOURCE/.venv/bin/python" "$SOURCE/deploy/create_manifest.py" \
    "$SOURCE" "$RELEASE" "$TIMESTAMP"

python3 -m venv "$RELEASE/.venv"
"$RELEASE/.venv/bin/python" -m pip install --disable-pip-version-check \
    --requirement "$RELEASE/requirements.txt"

if [[ $REBUILD_DATABASE -eq 1 ]]; then
    CANDIDATE_DB="$ROLLBACK_DIR/candidate.sqlite3"
    REBUILD_BASELINE="$ROLLBACK_DIR/pre-rebuild-counts.txt"
    "$RELEASE/.venv/bin/python" "$RELEASE/deploy/validate_database.py" \
        "$PROD_DB" --write-baseline "$REBUILD_BASELINE"
    "$RELEASE/.venv/bin/python" "$RELEASE/deploy/sqlite_backup.py" "$PROD_DB" "$CANDIDATE_DB"
    env DATABASE_URL="sqlite:///$CANDIDATE_DB" \
        "$RELEASE/.venv/bin/python" -m app.loader rebuild
    "$RELEASE/.venv/bin/python" "$RELEASE/deploy/validate_database.py" \
        "$CANDIDATE_DB" --baseline "$REBUILD_BASELINE"
    "$SOURCE/.venv/bin/python" "$SOURCE/deploy/sqlite_backup.py" \
        "$PROD_DB" "$ROLLBACK_DIR/production.sqlite3"
    install -o churchill -g churchill -m 0640 "$CANDIDATE_DB" "$PROD_DB.new"
    mv -f "$PROD_DB.new" "$PROD_DB"
    DB_REPLACED=1
fi

chown -R root:churchill "$RELEASE"
chmod -R a-w "$RELEASE"
find "$RELEASE" -type d -exec chmod 0755 {} +
find "$RELEASE" -type f -exec chmod 0644 {} +
find "$RELEASE/.venv/bin" -type f -exec chmod 0755 {} +

install -o root -g churchill -m 0640 "$RELEASE/deploy/production.env.example" "$ENV_FILE"
install -o root -g root -m 0644 "$RELEASE/deploy/churchill-web.service" "$UNIT_FILE"
CONFIG_INSTALLED=1

# Candidate smoke test uses the production identity and database on a separate port.
runuser -u churchill -- env DATABASE_URL="sqlite:////var/lib/churchill/churchill_prod.sqlite3" \
    "$RELEASE/.venv/bin/uvicorn" app.main:app --app-dir "$RELEASE" \
    --host 127.0.0.1 --port "$SMOKE_PORT" >"$ROLLBACK_DIR/smoke.log" 2>&1 &
SMOKE_PID=$!
for _ in $(seq 1 30); do
    curl -fsS "http://127.0.0.1:$SMOKE_PORT/health" >/dev/null && break
    sleep 1
done
mapfile -t SMOKE_PATHS < <(
    "$RELEASE/.venv/bin/python" "$RELEASE/deploy/smoke_paths.py" "$PROD_DB"
)
for path in "${SMOKE_PATHS[@]}"; do
    curl -fsS "http://127.0.0.1:$SMOKE_PORT$path" >/dev/null
done
kill "$SMOKE_PID"; wait "$SMOKE_PID" || true; SMOKE_PID=

ln -sfn "$RELEASE" "$CURRENT.new"
mv -Tf "$CURRENT.new" "$CURRENT"
SWITCHED=1
systemctl daemon-reload
systemctl restart churchill-web.service

for _ in $(seq 1 30); do
    curl -fsS http://127.0.0.1:8000/health >/dev/null && break
    sleep 1
done
curl -fsS http://127.0.0.1:8000/health >/dev/null
for path in "${SMOKE_PATHS[@]}"; do
    curl -fsS "http://127.0.0.1:8000$path" >/dev/null
done
for _ in $(seq 1 20); do
    curl -fsS "$PUBLIC_URL/" >/dev/null && break
    sleep 1
done
curl -fsS "$PUBLIC_URL/" >/dev/null
systemctl is-active --quiet churchill-tunnel.service

trap - ERR
echo "Deployment complete: $RELEASE"
echo "The tunnel service was neither modified nor restarted."
