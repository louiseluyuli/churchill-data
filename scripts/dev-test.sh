#!/usr/bin/env bash
set -euo pipefail
. /home/codexuser/churchill-data/scripts/dev-env.sh
test_database=$(mktemp /tmp/churchill-tests.XXXXXX.sqlite3)
trap 'rm -f "$test_database"' EXIT
export DATABASE_URL="sqlite:///$test_database"
exec .venv/bin/pytest -q "$@"
