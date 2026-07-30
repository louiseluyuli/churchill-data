#!/usr/bin/env bash
# Forward all deployment options, including --skip-public-check.
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repository_root=$(cd -- "$script_dir/.." && pwd -P)
exec "$repository_root/deploy/deploy-production.sh" "$@"
