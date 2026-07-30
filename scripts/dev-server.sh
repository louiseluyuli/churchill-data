#!/usr/bin/env bash
set -euo pipefail
. /home/codexuser/churchill-data/scripts/dev-env.sh
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${DEV_PORT:-8001}"
