#!/usr/bin/env bash
# Stage the CAD runtime wheels on the HOST so the sandbox can install them
# offline.
#
# WHY THIS EXISTS
# ---------------
# The OpenShell sandbox blocks outbound network access, so `pip install
# cadquery-ocp` cannot work from inside it. The two ways to fix that are:
#
#   1. Rebuild the sandbox image with the runtime baked in. This requires
#      extending NemoClaw's *full managed Dockerfile* for your exact release,
#      because `--from` replaces the managed runtime rather than layering on it.
#      Powerful, but it rebuilds the sandbox and destroys its state.
#
#   2. This script. Download the wheels on the host (where network is allowed),
#      upload them into the sandbox, and install with --no-index. No image
#      rebuild, no sandbox recreation, no policy change.
#
# Option 2 is preferred unless you specifically need a reproducible image.
#
# USAGE (host shell, e.g. ubuntu@brev-...):
#   ./nemoclaw/scripts/stage_cad_wheels.sh cad-to-mesh
#
set -euo pipefail

SANDBOX_NAME="${1:-}"
if [[ -z "$SANDBOX_NAME" ]]; then
    echo "usage: $0 <sandbox-name>" >&2
    echo "  e.g. $0 cad-to-mesh" >&2
    exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WHEELHOUSE="${REPO_ROOT}/.wheelhouse"
SANDBOX_WHEELHOUSE="/sandbox/wheelhouse"

# Pinned to match requirements-cad.txt exactly. A version drift between the
# sandbox and the reference cad-defeature image would mean the agent and the
# reference pipeline could disagree about the same geometry.
PACKAGES=(
    "cadquery-ocp==7.9.3.1.1"
    "cadquery==2.8.0"
    "numpy==2.5.2"
    "pyyaml>=6.0"
)

echo "==> Resolving the sandbox Python version"
# Wheels are ABI-specific, so they must be downloaded for the interpreter that
# will run them, not for the host's Python.
SANDBOX_PY="$(nemoclaw "$SANDBOX_NAME" exec -- python3 -c \
    'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null | tr -d '\r')"
if [[ -z "$SANDBOX_PY" ]]; then
    echo "ERROR: could not determine the sandbox Python version." >&2
    echo "  Check the sandbox is running: nemoclaw $SANDBOX_NAME status" >&2
    exit 1
fi
echo "    sandbox python: ${SANDBOX_PY}"

echo "==> Downloading wheels into ${WHEELHOUSE}"
mkdir -p "$WHEELHOUSE"
# --only-binary :all: fails loudly rather than fetching an sdist that would then
# need a compiler inside the sandbox.
python3 -m pip download \
    --only-binary ":all:" \
    --python-version "$SANDBOX_PY" \
    --platform manylinux2014_x86_64 \
    --dest "$WHEELHOUSE" \
    "${PACKAGES[@]}"

echo "==> Uploading wheelhouse into the sandbox at ${SANDBOX_WHEELHOUSE}"
nemoclaw "$SANDBOX_NAME" upload "$WHEELHOUSE" "$SANDBOX_WHEELHOUSE"

cat <<EOF

==> Wheels staged.

Next, inside the sandbox (nemoclaw $SANDBOX_NAME connect):

  python -m pip install --no-index --find-links ${SANDBOX_WHEELHOUSE} \\
      cadquery-ocp cadquery numpy pyyaml

  python -m pip install --no-build-isolation --no-index --no-deps \\
      /sandbox/cad-defeature-app

  python ~/.openclaw/skills/cad-defeature/scripts/cad_agent.py doctor

Both installs use --no-index, so neither makes a network call.
EOF
