#!/usr/bin/env bash
# Stage the OpenCascade (OCP) wheel on the HOST for offline sandbox install.
#
# The cad-defeature pipeline uses OCP directly (see src/cad_defeature/*); it
# does NOT import CadQuery. CadQuery and VTK are therefore intentionally absent
# here: adding them pulls a desktop/visualisation dependency graph that is not
# needed for local STEP/BREP processing and has incompatible cross-platform
# wheel tags. OCP is self-contained for the APIs this pipeline calls.
#
# The sandbox blocks egress. This script downloads the one required binary on
# the host, validates its SHA-256, and uploads it. The sandbox installation uses
# --no-index --no-deps, so it cannot make a network request.
#
# Usage (host shell):
#   ./nemoclaw/scripts/stage_cad_wheels.sh cad-to-mesh
set -euo pipefail

SANDBOX_NAME="${1:-}"
if [[ -z "$SANDBOX_NAME" ]]; then
    echo "usage: $0 <sandbox-name>" >&2
    exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WHEELHOUSE="${REPO_ROOT}/.wheelhouse"
SANDBOX_WHEELHOUSE="/sandbox/wheelhouse"
OCP_VERSION="7.9.3.1.1"
OCP_X86_FILENAME="cadquery_ocp-7.9.3.1.1-cp313-cp313-manylinux_2_31_x86_64.whl"
OCP_X86_URL="https://files.pythonhosted.org/packages/f1/16/0f3a1d0385d9144eb71416bffd421d57d10555c4caf2356e8cd858a5a3bc/${OCP_X86_FILENAME}"
OCP_X86_SHA256="0e70ab790910b6d81080a6d0df26a0cd0f1fd08984c447585c74be9b6d58c6c8"

echo "==> Inspecting the sandbox interpreter and architecture"
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

if [[ "$SANDBOX_PY" != "3.13" ]]; then
    echo "ERROR: this verified wheel manifest is pinned to Python 3.13." >&2
    echo "  Detected ${SANDBOX_PY}; do not guess a binary artifact URL." >&2
    exit 1
fi
if [[ "$SANDBOX_ARCH" != "x86_64" && "$SANDBOX_ARCH" != "amd64" ]]; then
    echo "ERROR: this verified wheel manifest supports x86_64 only." >&2
    echo "  Detected ${SANDBOX_ARCH}; do not substitute artifacts without verification." >&2
    exit 1
fi

mkdir -p "$WHEELHOUSE"
DESTINATION="${WHEELHOUSE}/${OCP_X86_FILENAME}"
echo "==> Downloading ${OCP_X86_FILENAME}"
curl --fail --location --silent --show-error --output "$DESTINATION" "$OCP_X86_URL"
echo "${OCP_X86_SHA256}  ${DESTINATION}" | sha256sum --check --status

# Validate the wheel's Python tag and archive integrity before crossing the
# sandbox boundary. No dependency resolution is needed or desired.
python3 -c '
import sys, zipfile
wheel = sys.argv[1]
with zipfile.ZipFile(wheel) as archive:
    assert any(name.endswith(".dist-info/METADATA") for name in archive.namelist())
print("    wheel archive OK")
' "$DESTINATION"

echo "==> Wheel in ${WHEELHOUSE}:"
ls -1sh "$DESTINATION"

echo "==> Uploading wheelhouse into the sandbox at ${SANDBOX_WHEELHOUSE}"
nemoclaw "$SANDBOX_NAME" upload "$WHEELHOUSE" "$SANDBOX_WHEELHOUSE"

cat <<EOF

==> OCP wheel staged and hash-verified.

Next, inside the sandbox (nemoclaw $SANDBOX_NAME connect):

  python -m pip install --no-index --no-deps --find-links ${SANDBOX_WHEELHOUSE} \\
      cadquery-ocp==${OCP_VERSION}

  python -c "import OCP; print('OpenCascade runtime OK')"

  python -m pip install --no-build-isolation --no-index --no-deps \\
      /sandbox/cad-defeature-app/cad-defeature-app

  python ~/.openclaw/skills/cad-defeature/scripts/cad_agent.py doctor

Every install uses --no-index, so neither makes a network call.
EOF
