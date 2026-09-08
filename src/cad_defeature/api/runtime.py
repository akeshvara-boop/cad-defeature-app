"""Safe host-to-NemoClaw command adapter.

The API runs on the Brev host. CAD kernels stay in the OpenShell sandbox and
Kit-CAE stays in its own Kit runtime; this adapter is the narrow boundary
between them. Commands are always argv lists and never pass user text through
a shell.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
from typing import Any


SUPPORTED_CAD_EXTENSIONS = {".step", ".stp", ".brep", ".brp", ".iges", ".igs"}
DEFAULT_LIBRARY_PATH = (
    "/sandbox/cad-sysroot/usr/lib/x86_64-linux-gnu:"
    "/sandbox/cad-sysroot/lib/x86_64-linux-gnu:"
    "/sandbox/cad-sysroot/usr/lib:/sandbox/cad-sysroot/lib"
)


class NemoClawRuntimeError(RuntimeError):
    """Raised when the host CLI or sandbox command contract fails."""


def extract_json_object(output: str) -> dict[str, Any]:
    """Return the last JSON object in output containing CLI banner text."""
    decoder = json.JSONDecoder()
    candidates: list[tuple[int, dict[str, Any]]] = []
    for index, character in enumerate(output):
        if character != "{":
            continue
        try:
            value, end = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append((end, value))
    if not candidates:
        tail = output[-1000:].strip()
        raise NemoClawRuntimeError(f"NemoClaw returned no JSON object. Output tail: {tail}")
    # Nested objects also decode successfully when scanning from every opening
    # brace. The complete agent payload has the longest decoded span.
    return max(candidates, key=lambda item: item[0])[1]


class NemoClawRunner:
    """Stage CAD data and invoke the structured cad-defeature skill."""

    def __init__(
        self,
        sandbox: str | None = None,
        binary: str | None = None,
        allowed_roots: Sequence[str | Path] | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.sandbox = sandbox or os.getenv("CAD_UI_SANDBOX", "cad-to-mesh")
        self.binary = binary or os.getenv("NEMOCLAW_BINARY", "nemoclaw")
        self._run_command = command_runner or subprocess.run
        configured_roots = allowed_roots or self._configured_roots()
        self.allowed_roots = tuple(Path(root).expanduser().resolve() for root in configured_roots)
        self.python = os.getenv(
            "CAD_UI_SANDBOX_PYTHON", "/sandbox/.venvs/cad-defeature/bin/python"
        )
        self.agent_script = os.getenv(
            "CAD_UI_AGENT_SCRIPT",
            "/sandbox/.openclaw/skills/cad-defeature/scripts/cad_agent.py",
        )
        self.python_path = os.getenv(
            "CAD_UI_PYTHONPATH", "/sandbox/cad-defeature-app/cad-defeature-app/src"
        )
        self.library_path = os.getenv("CAD_UI_LD_LIBRARY_PATH", DEFAULT_LIBRARY_PATH)
        self.policy_path = os.getenv(
            "CAD_UI_POLICY_PATH",
            "/sandbox/cad-defeature-app/cad-defeature-app/policies/power_tools_delta.yaml",
        )

    @staticmethod
    def _configured_roots() -> tuple[Path, ...]:
        value = os.getenv("CAD_UI_ALLOWED_ROOTS")
        if value:
            return tuple(Path(item) for item in value.split(os.pathsep) if item.strip())
        return (Path.home(),)

    def readiness(self) -> dict[str, Any]:
        executable = shutil.which(self.binary)
        return {
            "status": "ready" if executable else "not_ready",
            "nemoclaw_executable": executable,
            "sandbox": self.sandbox,
            "allowed_roots": [str(path) for path in self.allowed_roots],
        }

    def validate_source(self, source_path: str | Path) -> Path:
        source = Path(source_path).expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"CAD source is not a file: {source}")
        if source.suffix.lower() not in SUPPORTED_CAD_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_CAD_EXTENSIONS))
            raise ValueError(f"Unsupported CAD extension {source.suffix!r}; expected {supported}")
        if not any(source == root or root in source.parents for root in self.allowed_roots):
            raise ValueError(
                f"CAD source is outside CAD_UI_ALLOWED_ROOTS: {source}. "
                f"Allowed roots: {', '.join(map(str, self.allowed_roots))}"
            )
        return source

    def stage_source(self, source_path: str | Path, workflow_id: str) -> str:
        source = self.validate_source(source_path)
        remote_dir = PurePosixPath("/sandbox/ui/input") / workflow_id
        remote_path = remote_dir / f"model{source.suffix.lower()}"
        self._host_command(
            [self.binary, self.sandbox, "exec", "--", "mkdir", "-p", str(remote_dir)]
        )
        self._host_command(
            [self.binary, self.sandbox, "upload", str(source), str(remote_path)],
            timeout=600,
        )
        return str(remote_path)

    def invoke(self, action: str, arguments: Sequence[str], timeout: int = 900) -> dict[str, Any]:
        command = [
            self.binary,
            self.sandbox,
            "exec",
            "--",
            "env",
            f"LD_LIBRARY_PATH={self.library_path}",
            f"PYTHONPATH={self.python_path}",
            self.python,
            self.agent_script,
            action,
            *map(str, arguments),
        ]
        result = self._run_command(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
        payload = extract_json_object(combined)
        if result.returncode and payload.get("status") not in {
            "error",
            "rejected",
            "needs_human_decision",
        }:
            raise NemoClawRuntimeError(
                f"NemoClaw exited {result.returncode}: {combined[-1000:].strip()}"
            )
        return payload

    def read_json(self, remote_path: str) -> dict[str, Any]:
        result = self._host_command(
            [self.binary, self.sandbox, "exec", "--", "cat", remote_path]
        )
        return extract_json_object(result.stdout)

    def _host_command(
        self, command: Sequence[str], timeout: int = 120
    ) -> subprocess.CompletedProcess[str]:
        result = self._run_command(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout or "unknown command failure").strip()
            raise NemoClawRuntimeError(detail[-2000:])
        return result
