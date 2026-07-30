#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
. "$script_dir/dev-env.sh"
exec "$DEV_ROOT/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port "${DEV_PORT:-8001}"
