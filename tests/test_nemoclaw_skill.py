"""Tests for the NemoClaw skill contract.

The agent depends on two invariants: every outcome is a single JSON object with
a "status" field, and the safety guards cannot be bypassed. These tests assert
both without needing OpenCascade.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "nemoclaw" / "skills" / "cad-defeature" / "scripts" / "cad_agent.py"
SKILL_MD = SCRIPT.parents[1] / "SKILL.md"


def run_skill(*args: str) -> dict:
    """Invoke the skill script and assert it emitted parseable JSON."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip(), f"skill produced no stdout; stderr={result.stderr}"
    return json.loads(result.stdout)


def test_skill_md_has_required_frontmatter_name() -> None:
    """`nemoclaw skill install` rejects a SKILL.md without a name field."""
    text = SKILL_MD.read_text(encoding="utf-8")
    assert text.startswith("---"), "SKILL.md must open with YAML frontmatter"
    frontmatter = text.split("---")[1]
    assert "name: cad-defeature" in frontmatter
    assert "description:" in frontmatter


def test_skill_md_documents_the_human_approval_stop() -> None:
    """The agent must be told to stop, not to self-approve."""
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "needs_human_decision" in text
    assert "Never self-approve" in text or "never approve" in text.lower()


def test_missing_subcommand_is_not_a_traceback() -> None:
    """argparse errors are acceptable, but a crash must never reach the agent."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "args",
    [
        ("health", "--input", "does_not_exist.step"),
        ("verify", "--original", "a.brep", "--candidate", "b.brep"),
    ],
)
def test_errors_are_structured_json(args: tuple[str, ...]) -> None:
    """Every failure path returns {"status": "error", "message": ...}."""
    payload = run_skill(*args)
    assert payload["status"] == "error"
    assert payload["message"]
    assert "Traceback" not in payload["message"]
