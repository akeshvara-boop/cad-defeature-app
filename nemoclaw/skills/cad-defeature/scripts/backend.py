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


class BackendUnavailable(RuntimeError):
    """Raised when no execution path to the CAD pipeline exists."""


def _inprocess_available() -> bool:
    """True when the CAD package can be imported in this interpreter."""
    try:
        return importlib.util.find_spec("cad_defeature") is not None
    except (ImportError, ValueError):
        return False


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


def diagnose() -> dict[str, object]:
    """Report every backend's availability without selecting one.

    This is what the `doctor` subcommand surfaces. It exists because "the skill
    is installed" and "the skill can actually run" are different claims, and the
    gap between them is the most likely first failure in a fresh sandbox.
    """
    inprocess = _inprocess_available()
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

    remedy = None
    if selected is None:
        remedy = (
            "Neither backend is reachable. Either (a) install the pipeline into "
            "this sandbox so `import cad_defeature` works, or (b) expose a docker "
            "CLI with the cad-defeature:latest image built. OpenShell blocks "
            "docker socket access by default, so option (a) is usually correct "
            "for a hardened sandbox."
        )
    elif selected == "inprocess" and not inprocess:
        remedy = "CAD_DEFEATURE_BACKEND=inprocess was requested but cad_defeature is not importable."
    elif selected == "docker" and not docker_ok:
        remedy = f"CAD_DEFEATURE_BACKEND=docker was requested but: {docker_detail}"

    return {
        "requested_backend": requested,
        "selected_backend": selected,
        "backends": {
            "inprocess": {
                "available": inprocess,
                "detail": (
                    "cad_defeature is importable"
                    if inprocess
                    else "cad_defeature is not importable in this interpreter"
                ),
            },
            "docker": {"available": docker_ok, "detail": docker_detail},
        },
        "mount_root": os.environ.get("CAD_DEFEATURE_MOUNT", str(Path.cwd())),
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
