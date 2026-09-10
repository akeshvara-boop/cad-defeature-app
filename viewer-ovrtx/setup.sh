#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
: "${PYTHON:=python3.12}"
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt --index-url https://pypi.nvidia.com --extra-index-url https://pypi.org/simple
.venv/bin/python -c 'import ovrtx, ovstage, ovstream, warp; print("Viewer imports OK")'
.venv/bin/python -m pip freeze > runtime-resolved.txt
npm --prefix client ci
npm --prefix client run build
