#!/usr/bin/env bash
# Source this file from development-only commands.
set -euo pipefail

DEV_ROOT=/home/codexuser/churchill-data
DEV_DATABASE="$DEV_ROOT/data/churchill_dev.sqlite3"
mkdir -p "$DEV_ROOT/data"
export DATABASE_URL="sqlite:///$DEV_DATABASE"
cd "$DEV_ROOT"
