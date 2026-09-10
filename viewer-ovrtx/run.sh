#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export OVRTX_SKIP_USD_CHECK=1
exec .venv/bin/python -u server.py "$@"
