#!/usr/bin/env bash
# Stage the CAD runtime wheels on the HOST so the sandbox can install them
# offline.
#
# The sandbox blocks egress. This script retrieves artifacts on the host, then
# uploads them. The sandbox install always uses --no-index.
#
# IMPORTANT: do NOT use one `pip download --platform` invocation for the whole
# dependency graph. cadquery-ocp uses `manylinux_2_31_x86_64`, but its VTK
# dependency uses `manylinux2014_x86_64.manylinux_2_17_x86_64`. pip treats the
# requested --platform tag as an exact compatibility target, not a glibc range;
# asking it to resolve both under either tag makes it report "from versions:
# none". We download each known binary artifact by its verified PyPI URL and let
# pip resolve the now-local wheelhouse offline.
#
# USAGE (host shell):
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
CADQUERY_VERSION="2.8.0"
VTK_VERSION="9.6.2"

# Artifact records are URL|filename|sha256. Keep the hashes next to the URLs:
# the host is trusted for egress but the download is still verified before it is
# copied into the isolated sandbox.
OCP_X86_URL="https://files.pythonhosted.org/packages/f1/16/0f3a1d0385d9144eb71416bffd421d57d10555c4caf2356e8cd858a5a3bc/cadquery_ocp-7.9.3.1.1-cp313-cp313-manylinux_2_31_x86_64.whl"
OCP_X86_SHA256="0e70ab790910b6d81080a6d0df26a0cd0f1fd08984c447585c74be9b6d58c6c8"
VTK_X86_URL=""
VTK_X86_SHA256=""

# aarch64 is deliberately not guessed: populate these only after independently
# verifying artifacts and hashes for the exact release.

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
    echo "ERROR: this wheelhouse manifest is intentionally pinned to Python 3.13." >&2
    echo "  Detected ${SANDBOX_PY}; do not guess compatible binary URLs." >&2
    echo "  Update the manifest from PyPI's JSON release metadata first." >&2
    exit 1
fi
if [[ "$SANDBOX_ARCH" != "x86_64" && "$SANDBOX_ARCH" != "amd64" ]]; then
    echo "ERROR: the verified wheelhouse manifest currently supports x86_64 only." >&2
    echo "  Detected ${SANDBOX_ARCH}; do not substitute artifacts without verification." >&2
    exit 1
fi

# Query the VTK release JSON on the HOST and select the exact cp313 Linux x86_64
# artifact. This avoids the incompatible OCP/VTK platform-tag intersection, yet
# avoids hard-coding a potentially stale CDN path. Require exactly one hit.
VTK_META="$(curl --fail --silent --show-error "https://pypi.org/pypi/vtk/${VTK_VERSION}/json")"
VTK_RECORD="$(python3 -c '
import json, sys
meta = json.load(sys.stdin)
matches = [item for item in meta["urls"] if item["filename"] == "vtk-9.6.2-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl"]
if len(matches) != 1:
    raise SystemExit(f"expected 1 VTK cp313 x86_64 wheel, found {len(matches)}")
item = matches[0]
print(item["url"] + "|" + item["digests"]["sha256"])
' <<< "$VTK_META")"
VTK_X86_URL="${VTK_RECORD%%|*}"
VTK_X86_SHA256="${VTK_RECORD##*|}"

mkdir -p "$WHEELHOUSE"
download_verified() {
    # Bash expands every assignment on a single `local` declaration before it
    # assigns any of them. Keep destination separate so nounset cannot see an
    # as-yet-unassigned `filename`.
    local url="$1"
    local filename="$2"
    local digest="$3"
    local destination="${WHEELHOUSE}/${filename}"
    echo "==> Downloading ${filename}"
    curl --fail --location --silent --show-error --output "$destination" "$url"
    echo "${digest}  ${destination}" | sha256sum --check --status
}

download_verified "$OCP_X86_URL" \
    "cadquery_ocp-${OCP_VERSION}-cp313-cp313-manylinux_2_31_x86_64.whl" \
    "$OCP_X86_SHA256"
download_verified "$VTK_X86_URL" \
    "vtk-${VTK_VERSION}-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl" \
    "$VTK_X86_SHA256"

# Download pure-Python packages and transitive pure dependencies to the local
# wheelhouse. No platform selection is needed after binary wheels are supplied.
echo "==> Resolving pure-Python dependencies into the local wheelhouse"
python3 -m pip download --only-binary ":all:" --dest "$WHEELHOUSE" \
    "cadquery==${CADQUERY_VERSION}" \
    "cadquery-ocp-proxy==${OCP_VERSION}" \
    "numpy==2.5.2" \
    "pyyaml>=6.0"

echo "==> Verifying the offline resolver before upload"
python3 -m pip download --no-index --find-links "$WHEELHOUSE" --only-binary ":all:" \
    --dest "${WHEELHOUSE}/.resolver-check" \
    "cadquery-ocp==${OCP_VERSION}" "cadquery==${CADQUERY_VERSION}"
rm -rf "${WHEELHOUSE}/.resolver-check"

echo "==> Wheels in ${WHEELHOUSE}:"
ls -1sh "$WHEELHOUSE"

echo "==> Uploading wheelhouse into the sandbox at ${SANDBOX_WHEELHOUSE}"
nemoclaw "$SANDBOX_NAME" upload "$WHEELHOUSE" "$SANDBOX_WHEELHOUSE"

cat <<EOF

==> Wheels staged and hash-verified.

Next, inside the sandbox (nemoclaw $SANDBOX_NAME connect):

  python -m pip install --no-index --find-links ${SANDBOX_WHEELHOUSE} \\
      cadquery-ocp cadquery numpy pyyaml

  python -m pip install --no-build-isolation --no-index --no-deps \\
      /sandbox/cad-defeature-app/cad-defeature-app

  python ~/.openclaw/skills/cad-defeature/scripts/cad_agent.py doctor

Both installs use --no-index, so neither makes a network call.
EOF
