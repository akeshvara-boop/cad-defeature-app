#!/usr/bin/env bash
# Stage the CAD runtime wheels on the HOST so the sandbox can install them
# offline.
#
# WHY THIS EXISTS
# ---------------
# The OpenShell sandbox blocks outbound network access, so `pip install
# cadquery-ocp` cannot work from inside it. This script downloads the wheels on
# the host (where network is allowed and reviewable), uploads them into the
# sandbox, and lets pip install with --no-index. No image rebuild, no sandbox
# recreation, no network policy change.
#
# PLATFORM TAG NOTE
# -----------------
# cadquery-ocp publishes Linux wheels tagged `manylinux_2_31_x86_64` (and
# `manylinux_2_28_x86_64` for 8.x). pip's --platform match is EXACT, not
# "greater-or-equal", so asking for `manylinux2014_x86_64` finds nothing and
# reports the confusing "from versions: none". We therefore try the real tags
# in order, newest glibc first.
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

# Pinned to match requirements-cad.txt so the sandbox and the reference
# cad-defeature image cannot disagree about the same geometry.
PACKAGES=(
    "cadquery-ocp==7.9.3.1.1"
    "cadquery==2.8.0"
    "numpy==2.5.2"
    "pyyaml>=6.0"
)

echo "==> Inspecting the sandbox interpreter and architecture"
# Wheels are ABI- and arch-specific, so resolve against the interpreter that
# will actually run them rather than the host's Python.
SANDBOX_INFO="$(nemoclaw "$SANDBOX_NAME" exec -- python3 -c \
    'import platform,sys; print(f"{sys.version_info.major}.{sys.version_info.minor} {platform.machine()}")' \
    2>/dev/null | tr -d '\r' | tail -n 1)"
if [[ -z "$SANDBOX_INFO" ]]; then
    echo "ERROR: could not query the sandbox interpreter." >&2
    echo "  Check the sandbox is running: nemoclaw $SANDBOX_NAME status" >&2
    exit 1
fi
SANDBOX_PY="${SANDBOX_INFO%% *}"
SANDBOX_ARCH="${SANDBOX_INFO##* }"
echo "    python ${SANDBOX_PY}, arch ${SANDBOX_ARCH}"

case "$SANDBOX_ARCH" in
    x86_64|amd64) ARCH_TAG="x86_64" ;;
    aarch64|arm64) ARCH_TAG="aarch64" ;;
    *)
        echo "ERROR: unsupported sandbox architecture '${SANDBOX_ARCH}'." >&2
        echo "  cadquery-ocp publishes wheels for x86_64 and aarch64 only." >&2
        exit 1
        ;;
esac

# Newest glibc floor first. The first tag that resolves wins.
PLATFORM_TAGS=(
    "manylinux_2_31_${ARCH_TAG}"
    "manylinux_2_28_${ARCH_TAG}"
    "manylinux_2_35_${ARCH_TAG}"
    "manylinux2014_${ARCH_TAG}"
)

mkdir -p "$WHEELHOUSE"
DOWNLOADED=""
for tag in "${PLATFORM_TAGS[@]}"; do
    echo "==> Trying platform tag ${tag}"
    if python3 -m pip download \
        --only-binary ":all:" \
        --python-version "$SANDBOX_PY" \
        --platform "$tag" \
        --dest "$WHEELHOUSE" \
        "${PACKAGES[@]}"; then
        DOWNLOADED="$tag"
        break
    fi
    echo "    no match for ${tag}, trying next tag"
done

if [[ -z "$DOWNLOADED" ]]; then
    echo "ERROR: no wheels matched any known platform tag." >&2
    echo "  Tried: ${PLATFORM_TAGS[*]}" >&2
    echo "  Confirm the sandbox interpreter is supported: cadquery-ocp 7.9.3.1.1" >&2
    echo "  publishes cp310-cp314 wheels only." >&2
    exit 1
fi

echo "==> Resolved with platform tag ${DOWNLOADED}"
echo "==> Wheels in ${WHEELHOUSE}:"
ls -1sh "$WHEELHOUSE"

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
