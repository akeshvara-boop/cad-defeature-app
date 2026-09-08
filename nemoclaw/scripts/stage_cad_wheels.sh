#!/usr/bin/env bash
# Stage and install the OpenCascade (OCP) runtime in a NemoClaw sandbox.
#
# The CAD pipeline imports OCP directly; it does not import the CadQuery Python
# API. However, cadquery-ocp links against VTK's Python wrapping library, so
# both pinned binary wheels are required at runtime. This script downloads them
# on the HOST, verifies them, uploads each wheel to a pip-visible sandbox path,
# and installs them into a sandbox-local virtual environment without egress.
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
VENV="/sandbox/.venvs/cad-defeature"
OCP_VERSION="7.9.3.1.1"
VTK_VERSION="9.6.2"
OCP_FILENAME="cadquery_ocp-7.9.3.1.1-cp313-cp313-manylinux_2_31_x86_64.whl"
OCP_URL="https://files.pythonhosted.org/packages/f1/16/0f3a1d0385d9144eb71416bffd421d57d10555c4caf2356e8cd858a5a3bc/${OCP_FILENAME}"
OCP_SHA256="0e70ab790910b6d81080a6d0df26a0cd0f1fd08984c447585c74be9b6d58c6c8"
VTK_FILENAME="vtk-9.6.2-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl"
VTK_URL="https://files.pythonhosted.org/packages/bd/75/4a1fe360256b99779d534b2387d0efa70952167d53d716f60ff39d62994d/${VTK_FILENAME}"
VTK_SHA256="fb85c7fbad59209a08e428479defbdf96f974a9f39d4212960fb1a24a919613c"
PYYAML_VERSION="6.0.3"
PYYAML_FILENAME="pyyaml-6.0.3-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl"
PYYAML_SHA256="0f29edc409a6392443abf94b9cf89ce99889a1dd5376d94316ae5145dfedd5d6"

sandbox_exec() {
    nemoclaw "$SANDBOX_NAME" exec -- bash -lc "$1"
}

download_verified() {
    local filename="$1"
    local url="$2"
    local digest="$3"
    local destination="${WHEELHOUSE}/${filename}"

    echo "==> Downloading ${filename} on the host"
    curl --fail --location --silent --show-error --output "$destination" "$url"
    echo "${digest}  ${destination}" | sha256sum --check --status
    python3 -c '
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    assert any(name.endswith(".dist-info/METADATA") for name in archive.namelist())
print("    wheel archive OK")
' "$destination"
}

download_pyyaml_verified() {
    local destination="${WHEELHOUSE}/${PYYAML_FILENAME}"

    echo "==> Downloading ${PYYAML_FILENAME} on the host"
    python3 -m pip download \
        --only-binary=:all: \
        --no-deps \
        --platform manylinux2014_x86_64 \
        --python-version 313 \
        --implementation cp \
        --abi cp313 \
        --dest "$WHEELHOUSE" \
        "PyYAML==${PYYAML_VERSION}"
    echo "${PYYAML_SHA256}  ${destination}" | sha256sum --check --status
    python3 -c '
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    assert any(name.endswith(".dist-info/METADATA") for name in archive.namelist())
print("    wheel archive OK")
' "$destination"
}

upload_and_verify() {
    local filename="$1"
    local source="${WHEELHOUSE}/${filename}"
    local target="${SANDBOX_WHEELHOUSE}/${filename}"

    # Directory uploads preserve their basename. Upload each file to its exact
    # destination so --find-links searches the directory that contains wheels.
    echo "==> Uploading verified wheel into the sandbox at ${target}"
    nemoclaw "$SANDBOX_NAME" upload "$source" "$target"
    echo "==> Confirming the uploaded artifact is visible inside the sandbox"
    sandbox_exec "test -f '${target}' && python3 -c \"import zipfile; zipfile.ZipFile('${target}').testzip() is None or exit(1); print('    sandbox wheel archive OK')\""
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
download_verified "$VTK_FILENAME" "$VTK_URL" "$VTK_SHA256"
download_verified "$OCP_FILENAME" "$OCP_URL" "$OCP_SHA256"
download_pyyaml_verified
upload_and_verify "$VTK_FILENAME"
upload_and_verify "$OCP_FILENAME"
upload_and_verify "$PYYAML_FILENAME"

if [[ "$MODE" == "--stage-only" ]]; then
    cat <<EOF

==> Wheels staged only.

The base Python is externally managed (PEP 668), so install into a sandbox-local
venv; this remains entirely offline:

  python -m venv ${VENV}
  ${VENV}/bin/python -m pip install --no-index --no-deps --find-links ${SANDBOX_WHEELHOUSE} PyYAML==${PYYAML_VERSION} vtk==${VTK_VERSION} cadquery-ocp==${OCP_VERSION}
EOF
    exit 0
fi

echo "==> Creating/reusing sandbox-local virtual environment: ${VENV}"
sandbox_exec "python3 -m venv '${VENV}'"
echo "==> Installing PyYAML, VTK and OCP offline into the virtual environment"
sandbox_exec "'${VENV}/bin/python' -m pip install --no-index --no-deps --find-links '${SANDBOX_WHEELHOUSE}' 'PyYAML==${PYYAML_VERSION}' 'vtk==${VTK_VERSION}' 'cadquery-ocp==${OCP_VERSION}'"
echo "==> Verifying the linked sandbox CAD runtime"
sandbox_exec "'${VENV}/bin/python' -c \"import yaml; import vtkmodules; import OCP; print('Policy, VTK and OpenCascade runtimes OK:', OCP.__file__)\""

if sandbox_exec "test -d '${SANDBOX_REPO}'"; then
    echo "==> Installing local cad-defeature package into the virtual environment"
    if ! sandbox_exec "'${VENV}/bin/python' -m pip install --no-build-isolation --no-index --no-deps '${SANDBOX_REPO}'"; then
        cat <<EOF >&2
ERROR: VTK/OCP installed, but the local project install failed.
A likely cause is that the fresh venv has an older setuptools than pyproject.toml
requires (>=68). This is a separate offline build-tool issue; do not enable egress.
Temporary dependency-free fallback:
  PYTHONPATH=${SANDBOX_REPO}/src ${VENV}/bin/python ~/.openclaw/skills/cad-defeature/scripts/cad_agent.py doctor
EOF
        exit 1
    fi
    sandbox_exec "'${VENV}/bin/python' -c \"import cad_defeature; print('cad_defeature OK:', cad_defeature.__file__)\""
else
    cat <<EOF >&2
WARNING: VTK/OCP installed, but the repository was not found at ${SANDBOX_REPO}.
Upload the host checkout first, then rerun this command:
  nemoclaw ${SANDBOX_NAME} upload ${REPO_ROOT} /sandbox/cad-defeature-app
EOF
    exit 1
fi

cat <<EOF

==> Sandbox CAD environment is ready.

Use this interpreter for every skill invocation:

  ${VENV}/bin/python ~/.openclaw/skills/cad-defeature/scripts/cad_agent.py doctor
EOF
