#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
. "$script_dir/dev-env.sh"
[[ $EUID -ne 0 ]] || {
    echo "Development tests must not run as root." >&2
    exit 1
}
exec "$DEV_ROOT/.venv/bin/pytest" -q "$@"
