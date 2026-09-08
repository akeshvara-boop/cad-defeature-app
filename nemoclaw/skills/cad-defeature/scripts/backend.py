"""Execution backend resolution for the NemoClaw cad-defeature skill.

The skill script runs inside the NemoClaw/OpenShell sandbox, but the CAD
pipeline needs OpenCascade, which lives in the `cad-defeature:latest` image.
Those are not the same environment, so the skill must decide how to reach the
pipeline before it does anything else.

Two backends are supported:

    inprocess - `cad_defeature` is importable here. Used directly.
    docker    - shell out to the container image, mounting a shared workspace.

Resolution is explicit and reported to the agent rather than guessed at
silently, because a wrong guess produces a confusing ImportError deep inside a
CAD call rather than an actionable message.

Environment overrides:
    CAD_DEFEATURE_BACKEND   auto (default) | inprocess | docker
    CAD_DEFEATURE_IMAGE     container image, default cad-defeature:latest
    CAD_DEFEATURE_MOUNT     host directory shared with the container,
                            default the current working directory
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess

DEFAULT_IMAGE = "cad-defeature:latest"
CONTAINER_MOUNT = "/workspace"

# Where the repository may be reachable from inside the sandbox. Checked in
# order so the remedy can name a real path instead of a placeholder.
# The OpenShell sandbox roots its writable tree at /sandbox, not /workspace,
# so sandbox-native locations are searched first.
CANDIDATE_REPO_PATHS = (
    "/sandbox/cad-defeature-app",
    "/sandbox/workspace/cad-defeature-app",
    "/sandbox/workspace",
    "/sandbox",
    "/workspace/cad-defeature-app",
    "/workspace",
    "/home/ubuntu/cad-defeature-app",
    "/home/sandbox/cad-defeature-app",
    "/mnt/cad-defeature-app",
    "/app",
)

# Depth-limited scan roots used when none of the fixed paths hit. Kept shallow
# so a large mounted tree cannot turn preflight into a long filesystem walk.
SCAN_ROOTS = ("/sandbox", "/workspace", "/home")
SCAN_DEPTH = 3


class BackendUnavailable(RuntimeError):
    """Raised when no execution path to the CAD pipeline exists."""


def _inprocess_available() -> bool:
    """True when the CAD package can be imported in this interpreter."""
    try:
        return importlib.util.find_spec("cad_defeature") is not None
    except (ImportError, ValueError):
        return False


def _cad_runtime_available() -> tuple[bool, str]:
    """Check for OpenCascade, the binary runtime every CAD command needs.

    Importing cad_defeature succeeds without OCP because the package imports
    it lazily. Probing the spec here keeps the failure at preflight, where it
    is actionable, instead of mid-run inside a geometry call.
    """
    try:
        if importlib.util.find_spec("OCP") is not None:
            return True, "OpenCascade (OCP) runtime is importable"
    except (ImportError, ValueError):
        pass
    return False, (
        "OpenCascade (OCP) is not importable in this interpreter. The sandbox "
        "base Python is externally managed (PEP 668), so use the sandbox-local "
        "virtual environment created by the host-side staging script rather than "
        "installing system-wide or requesting egress:\n"
        "  ./nemoclaw/scripts/stage_cad_wheels.sh <sandbox-name>\n"
        "Then invoke this skill with:\n"
        "  /sandbox/.venvs/cad-defeature/bin/python "
        "~/.openclaw/skills/cad-defeature/scripts/cad_agent.py doctor"
    )


def _docker_available() -> tuple[bool, str]:
    """True when a working docker CLI can see the pipeline image."""
    binary = shutil.which("docker")
    if not binary:
        return False, "docker CLI is not on PATH in this sandbox"
    image = os.environ.get("CAD_DEFEATURE_IMAGE", DEFAULT_IMAGE)
    try:
        probe = subprocess.run(
            [binary, "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"docker CLI could not be executed: {exc}"
    if probe.returncode != 0:
        return False, (
            f"docker is available but image '{image}' was not found. "
            f"Build it with: docker build -t {image} ."
        )
    return True, f"docker backend ready using image '{image}'"


def _locate_repo() -> str | None:
    """Find the repo inside the sandbox so the remedy can be copy-pasteable.

    Identified by pyproject.toml plus the package directory, not by name
    alone, so an unrelated directory cannot be mistaken for the pipeline.
    """
    override = os.environ.get("CAD_DEFEATURE_REPO")
    candidates = (override, *CANDIDATE_REPO_PATHS) if override else CANDIDATE_REPO_PATHS
    for candidate in candidates:
        if candidate and _is_repo(Path(candidate)):
            return str(candidate)
    return _scan_for_repo()


def _is_repo(root: Path) -> bool:
    """Identify the pipeline by its contents, never by directory name."""
    try:
        return (root / "pyproject.toml").is_file() and (root / "src" / "cad_defeature").is_dir()
    except OSError:
        return False


def _scan_for_repo() -> str | None:
    """Shallow breadth-first scan of likely roots, depth-capped for speed."""
    for scan_root in SCAN_ROOTS:
        base = Path(scan_root)
        if not base.is_dir():
            continue
        frontier = [(base, 0)]
        while frontier:
            current, depth = frontier.pop(0)
            if _is_repo(current):
                return str(current)
            if depth >= SCAN_DEPTH:
                continue
            try:
                children = [child for child in current.iterdir() if child.is_dir()]
            except (OSError, PermissionError):
                continue
            for child in children:
                if child.name.startswith("."):
                    continue
                frontier.append((child, depth + 1))
    return None


def diagnose() -> dict[str, object]:
    """Report every backend's availability without selecting one.

    This is what the `doctor` subcommand surfaces. It exists because "the skill
    is installed" and "the skill can actually run" are different claims, and the
    gap between them is the most likely first failure in a fresh sandbox.
    """
    package_ok = _inprocess_available()
    cad_ok, cad_detail = _cad_runtime_available()
    # In-process execution requires BOTH the package and the CAD runtime.
    inprocess = package_ok and cad_ok
    docker_ok, docker_detail = _docker_available()
    requested = os.environ.get("CAD_DEFEATURE_BACKEND", "auto").strip().lower()

    if inprocess:
        selected = "inprocess"
    elif docker_ok:
        selected = "docker"
    else:
        selected = None

    if requested in {"inprocess", "docker"}:
        selected = requested

    repo = _locate_repo()
    remedy = None
    if package_ok and not cad_ok:
        # The package installed cleanly but the geometry runtime is absent.
        selected = None
        remedy = cad_detail
    elif selected is None:
        if repo:
            remedy = (
                "Install the pipeline into this sandbox from the local checkout "
                "(no network required):\n"
                f"  python -m pip install --no-build-isolation --no-index {repo}\n"
                "If pip reports missing build dependencies, add --no-deps: the "
                "OpenCascade runtime must already be present in the sandbox image. "
                "Do NOT request a network policy exemption to reach PyPI; this "
                "install needs no egress."
            )
        else:
            remedy = (
                "The cad-defeature repository is not visible inside this sandbox, so "
                "the pipeline cannot be installed. Copy it in from the HOST shell "
                "(this needs no sandbox egress):\n"
                "  nemoclaw <sandbox-name> upload ~/cad-defeature-app /sandbox/cad-defeature-app\n"
                "Or share the host directory live:\n"
                "  nemoclaw <sandbox-name> share mount /sandbox ~/.nemoclaw/mounts/<sandbox-name>\n"
                "Then re-run doctor. Searched: "
                + ", ".join(CANDIDATE_REPO_PATHS)
                + f" and scanned {', '.join(SCAN_ROOTS)} to depth {SCAN_DEPTH}."
                + " Set CAD_DEFEATURE_REPO if the checkout lives elsewhere."
            )
    elif selected == "inprocess" and not inprocess:
        remedy = (
            "CAD_DEFEATURE_BACKEND=inprocess was requested but "
            + (
                "cad_defeature is not importable."
                if not package_ok
                else cad_detail
            )
        )
    elif selected == "docker" and not docker_ok:
        remedy = f"CAD_DEFEATURE_BACKEND=docker was requested but: {docker_detail}"

    return {
        "requested_backend": requested,
        "selected_backend": selected,
        "backends": {
            "inprocess": {
                "available": inprocess,
                "detail": (
                    "cad_defeature and the OpenCascade runtime are both importable"
                    if inprocess
                    else "cad_defeature is not importable in this interpreter"
                    if not package_ok
                    else "cad_defeature is installed but the CAD runtime is missing"
                ),
                "package_importable": package_ok,
                "cad_runtime_importable": cad_ok,
                "cad_runtime_detail": cad_detail,
            },
            "docker": {"available": docker_ok, "detail": docker_detail},
        },
        "mount_root": os.environ.get("CAD_DEFEATURE_MOUNT", str(Path.cwd())),
        "repository_path": repo,
        "searched_paths": list(CANDIDATE_REPO_PATHS),
        "scan_roots": list(SCAN_ROOTS),
        "requires_network": False,
        "network_note": (
            "This skill performs no outbound network calls. CAD processing is local "
            "OpenCascade work and installation uses the local checkout. A CONNECT "
            "tunnel 403 while using this skill indicates an unexpected egress "
            "attempt - investigate it rather than widening the OpenShell policy."
        ),
        "usable": selected is not None and remedy is None,
        "remedy": remedy,
    }


def require_inprocess() -> None:
    """Guard used by commands that call the CAD package directly."""
    if _inprocess_available():
        return
    report = diagnose()
    if report["backends"]["docker"]["available"]:
        raise BackendUnavailable(
            "cad_defeature is not importable in this sandbox, but a docker "
            "backend is available. Run this command through the container, or "
            "install the pipeline into the sandbox. Run `doctor` for details."
        )
    raise BackendUnavailable(
        "The cad_defeature package is not importable and no docker fallback is "
        "available. Run `doctor` for the exact remedy."
    )
