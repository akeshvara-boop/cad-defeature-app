#!/usr/bin/env bash
# Stage and install the OpenCascade (OCP) runtime in a NemoClaw sandbox.
#
# The CAD pipeline imports OCP directly; it does not import CadQuery or VTK.
# We deliberately stage only the OCP wheel. That keeps the dependency boundary
# small and avoids mixing incompatible manylinux tags from visualisation extras.
#
# The sandbox blocks egress. This script performs every fetch on the HOST,
# verifies the artifact, uploads it, and (by default) installs it into a
# sandbox-local virtual environment. It never needs a network-policy exception.
#
# Usage (host shell):
#   ./nemoclaw/scripts/stage_cad_wheels.sh cad-to-mesh
#   ./nemoclaw/scripts/stage_cad_wheels.sh cad-to-mesh --stage-only
set -euo pipefail

SANDBOX_NAME="${1:-}"
MODE="${2:---install}"
if [[ -z "$SANDBOX_NAME" || ( "$MODE" != "--install" && "$MODE" != "--stage-only" ) ]]; then
    echo "usage: $0 <sandbox-name> [--install|--stage-only]" >&2
    exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WHEELHOUSE="${REPO_ROOT}/.wheelhouse"
SANDBOX_WHEELHOUSE="/sandbox/wheelhouse"
SANDBOX_REPO="/sandbox/cad-defeature-app/cad-defeature-app"
# /sandbox is the declared writable sandbox mount. `nemoclaw exec` may run under
# a gateway identity that cannot write /home/sandbox even when an interactive
# shell presents it as HOME, so never create managed state below that home.
VENV="/sandbox/.venvs/cad-defeature"
OCP_VERSION="7.9.3.1.1"
OCP_FILENAME="cadquery_ocp-7.9.3.1.1-cp313-cp313-manylinux_2_31_x86_64.whl"
OCP_URL="https://files.pythonhosted.org/packages/f1/16/0f3a1d0385d9144eb71416bffd421d57d10555c4caf2356e8cd858a5a3bc/${OCP_FILENAME}"
OCP_SHA256="0e70ab790910b6d81080a6d0df26a0cd0f1fd08984c447585c74be9b6d58c6c8"

sandbox_exec() {
    nemoclaw "$SANDBOX_NAME" exec -- bash -lc "$1"
}

echo "==> Inspecting the sandbox interpreter and architecture"
SANDBOX_INFO="$(sandbox_exec 'python3 -c "import platform,sys; print(f\"{sys.version_info.major}.{sys.version_info.minor} {platform.machine()}\")"' 2>/dev/null | tr -d '\r' | tail -n 1)"
if [[ -z "$SANDBOX_INFO" ]]; then
    echo "ERROR: could not query the sandbox interpreter." >&2
    echo "  Check the sandbox is running: nemoclaw $SANDBOX_NAME status" >&2
    exit 1
fi
SANDBOX_PY="${SANDBOX_INFO%% *}"
SANDBOX_ARCH="${SANDBOX_INFO##* }"
echo "    python ${SANDBOX_PY}, arch ${SANDBOX_ARCH}"

if [[ "$SANDBOX_PY" != "3.13" ]]; then
    echo "ERROR: this verified manifest is pinned to Python 3.13; detected ${SANDBOX_PY}." >&2
    exit 1
fi
if [[ "$SANDBOX_ARCH" != "x86_64" && "$SANDBOX_ARCH" != "amd64" ]]; then
    echo "ERROR: this verified manifest supports x86_64 only; detected ${SANDBOX_ARCH}." >&2
    exit 1
fi

mkdir -p "$WHEELHOUSE"
DESTINATION="${WHEELHOUSE}/${OCP_FILENAME}"
echo "==> Downloading ${OCP_FILENAME} on the host"
curl --fail --location --silent --show-error --output "$DESTINATION" "$OCP_URL"
echo "${OCP_SHA256}  ${DESTINATION}" | sha256sum --check --status
python3 -c '
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    assert any(name.endswith(".dist-info/METADATA") for name in archive.namelist())
print("    wheel archive OK")
' "$DESTINATION"

# Directory uploads preserve the source basename. The previous implementation
# uploaded `.wheelhouse` to `/sandbox/wheelhouse`, which placed the wheel at
# `/sandbox/wheelhouse/.wheelhouse/<wheel>`. pip searched the parent directory
# and correctly found no candidates. Upload the wheel file to its exact target.
SANDBOX_WHEEL="${SANDBOX_WHEELHOUSE}/${OCP_FILENAME}"
echo "==> Uploading verified wheel into the sandbox at ${SANDBOX_WHEEL}"
nemoclaw "$SANDBOX_NAME" upload "$DESTINATION" "$SANDBOX_WHEEL"

echo "==> Confirming the uploaded artifact is visible inside the sandbox"
sandbox_exec "test -f '${SANDBOX_WHEEL}' && python3 -c \"import zipfile; zipfile.ZipFile('${SANDBOX_WHEEL}').testzip() is None or exit(1); print('    sandbox wheel archive OK')\""

if [[ "$MODE" == "--stage-only" ]]; then
    cat <<EOF

==> Wheel staged only.

Inside the sandbox, create/activate a virtual environment first. The base Python
is externally managed (PEP 668), so pip correctly refuses system-wide installs:

  python -m venv /sandbox/.venvs/cad-defeature
  source /sandbox/.venvs/cad-defeature/bin/activate
  python -m pip install --no-index --no-deps --find-links ${SANDBOX_WHEELHOUSE} cadquery-ocp==${OCP_VERSION}
EOF
    exit 0
fi

# PEP 668 means pip must not write to the externally-managed base interpreter.
# The venv boundary is intentional. The commands run non-interactively from the
# host so the validated interpreter is exactly the one that receives the wheel.
echo "==> Creating/reusing sandbox-local virtual environment: ${VENV}"
sandbox_exec "python3 -m venv '${VENV}'"
echo "==> Installing OCP offline into the virtual environment"
sandbox_exec "'${VENV}/bin/python' -m pip install --no-index --no-deps --find-links '${SANDBOX_WHEELHOUSE}' 'cadquery-ocp==${OCP_VERSION}'"
echo "==> Verifying the sandbox runtime"
sandbox_exec "'${VENV}/bin/python' -c \"import OCP; print('OpenCascade runtime OK:', OCP.__file__)\""

# The project has no runtime dependencies declared, but setuptools is a build
# dependency. Install only if the venv needs it; use the project's source-tree
# fallback below rather than hiding a missing offline build wheel.
if sandbox_exec "test -d '${SANDBOX_REPO}'"; then
    echo "==> Installing local cad-defeature package into the virtual environment"
    if ! sandbox_exec "'${VENV}/bin/python' -m pip install --no-build-isolation --no-index --no-deps '${SANDBOX_REPO}'"; then
        cat <<EOF >&2
ERROR: OCP installed, but the local project install failed.
The likely cause is that the fresh venv has an older setuptools than pyproject.toml
requires (>=68). This is a separate offline build-tool issue; do not enable egress.
Run the doctor using PYTHONPATH as a temporary, dependency-free fallback:
  PYTHONPATH=${SANDBOX_REPO}/src ${VENV}/bin/python ~/.openclaw/skills/cad-defeature/scripts/cad_agent.py doctor
EOF
        exit 1
    fi
    sandbox_exec "'${VENV}/bin/python' -c \"import cad_defeature; print('cad_defeature OK:', cad_defeature.__file__)\""
else
    cat <<EOF >&2
WARNING: OCP installed, but the repository was not found at ${SANDBOX_REPO}.
Upload the host checkout first, then rerun this command:
  nemoclaw ${SANDBOX_NAME} upload ${REPO_ROOT} /sandbox/cad-defeature-app
EOF
    exit 1
fi

cat <<EOF

==> Sandbox CAD environment is ready.

Use this interpreter for every skill invocation (a normal sandbox shell does not
auto-activate the venv):

  ${VENV}/bin/python ~/.openclaw/skills/cad-defeature/scripts/cad_agent.py doctor

Or interactively:

  source /sandbox/.venvs/cad-defeature/bin/activate
  python ~/.openclaw/skills/cad-defeature/scripts/cad_agent.py doctor
EOF
