#!/usr/bin/env bash
set -euo pipefail
. /home/codexuser/churchill-data/scripts/dev-env.sh
exec .venv/bin/python -m app.loader fetch --evidence-limit 100 --candidate-cap 30000 "$@"
