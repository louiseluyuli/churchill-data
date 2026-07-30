#!/usr/bin/env bash
# Source this file from development-only commands.
set -euo pipefail

DEV_SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
DEV_ROOT=$(cd -- "$DEV_SCRIPT_DIR/.." && pwd -P)
DEV_DATABASE="$DEV_ROOT/data/churchill_dev.sqlite3"
mkdir -p "$DEV_ROOT/data"
export DATABASE_URL="sqlite:///$DEV_DATABASE"
cd "$DEV_ROOT"
