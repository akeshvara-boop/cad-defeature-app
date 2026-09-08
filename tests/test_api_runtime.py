from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from cad_defeature.api.runtime import NemoClawRunner, extract_json_object


def completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


def test_extract_json_ignores_nemoclaw_banner_and_nested_objects() -> None:
    payload = {"status": "complete", "health": {"status": "kernel_inspected", "solids": 1}}
    output = "✓ Active gateway set to 'nemoclaw'\n" + json.dumps(payload, indent=2)
    assert extract_json_object(output) == payload


def test_runner_builds_argv_without_shell(tmp_path: Path) -> None:
    calls = []

    def fake(command, **kwargs):
        calls.append((command, kwargs))
        return completed(command, stdout='{"status":"complete"}')

    runner = NemoClawRunner(allowed_roots=[tmp_path], command_runner=fake)
    payload = runner.invoke("health", ["--input", "/sandbox/input/model.igs"])

    assert payload["status"] == "complete"
    command, kwargs = calls[0]
    assert command[:4] == ["nemoclaw", "cad-to-mesh", "exec", "--"]
    assert "bash" not in command
    assert "-lc" not in command
    assert kwargs["check"] is False


def test_runner_rejects_files_outside_allowed_root(tmp_path: Path) -> None:
    inside = tmp_path / "allowed"
    outside = tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    source = outside / "part.step"
    source.write_text("fixture", encoding="utf-8")
    runner = NemoClawRunner(allowed_roots=[inside])

    with pytest.raises(ValueError, match="outside CAD_UI_ALLOWED_ROOTS"):
        runner.validate_source(source)


def test_runner_rejects_unsupported_source_extension(tmp_path: Path) -> None:
    source = tmp_path / "part.fbx"
    source.write_text("fixture", encoding="utf-8")
    runner = NemoClawRunner(allowed_roots=[tmp_path])

    with pytest.raises(ValueError, match="Unsupported CAD extension"):
        runner.validate_source(source)
