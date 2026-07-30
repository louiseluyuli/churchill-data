#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
. "$script_dir/dev-env.sh"
exec "$DEV_ROOT/.venv/bin/python" -m app.loader fetch --evidence-limit 100 --candidate-cap 30000 "$@"
