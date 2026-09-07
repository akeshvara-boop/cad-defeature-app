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


def test_doctor_always_reports_both_backends() -> None:
    """Preflight must be actionable whether or not the pipeline is reachable."""
    payload = run_skill("doctor")
    diagnosis = payload["diagnosis"]
    assert set(diagnosis["backends"]) == {"inprocess", "docker"}
    for backend in diagnosis["backends"].values():
        assert isinstance(backend["available"], bool)
        assert backend["detail"]
    # An unusable environment must always carry a remedy, never a bare failure.
    if not diagnosis["usable"]:
        assert payload["status"] == "error"
        assert diagnosis["remedy"]
        assert payload["message"] == diagnosis["remedy"]


def test_doctor_declares_the_skill_needs_no_egress() -> None:
    """A restricted-egress sandbox must not push the agent toward a policy change."""
    payload = run_skill("doctor")
    diagnosis = payload["diagnosis"]
    assert diagnosis["requires_network"] is False
    assert "403" in diagnosis["network_note"] or "egress" in diagnosis["network_note"]
    remedy = diagnosis.get("remedy") or ""
    # The offline install path must never send the agent to PyPI.
    if "pip install" in remedy:
        assert "--no-index" in remedy


def test_skill_md_forbids_requesting_network_exemptions() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "Never request a network policy exemption" in text


def test_skill_md_tells_agent_to_run_doctor_first() -> None:
    """A fresh sandbox fails confusingly unless preflight is documented."""
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "doctor" in text
    assert "Preflight" in text or "preflight" in text
