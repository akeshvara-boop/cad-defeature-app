from __future__ import annotations

from pathlib import Path

import pytest

from cad_defeature.api.workflows import WorkflowService, WorkflowStore


class FakeRunner:
    policy_path = "/sandbox/repo/policies/power_tools_delta.yaml"

    def __init__(self, source: Path):
        self.source = source
        self.calls = []
        self.approval_count = 0

    def validate_source(self, source_path):
        assert Path(source_path) == self.source
        return self.source

    def stage_source(self, source_path, workflow_id):
        return f"/sandbox/ui/input/{workflow_id}/model.igs"

    def invoke(self, action, arguments):
        self.calls.append((action, arguments))
        if action == "health":
            return {
                "status": "complete",
                "health": {"classification": "surface_or_wire_geometry", "route": "surface_safe_review"},
            }
        if action == "heal":
            return {
                "status": "needs_human_decision",
                "run_dir": "/sandbox/ui/runs/test/heal-1",
                "question": "Approve 0.01 mm?",
                "request": {"proposed_tolerance": 0.01},
            }
        if action == "approve":
            self.approval_count += 1
            if self.approval_count == 1:
                return {
                    "status": "needs_human_decision",
                    "run_dir": "/sandbox/ui/runs/test/heal-approved-1",
                    "question": "The prior approval was insufficient.",
                    "request": {"proposed_tolerance": 0.1},
                }
            return {
                "status": "complete",
                "run_dir": "/sandbox/ui/runs/test/heal-approved-2",
                "report": {"healed_model": "healed_solid.brep"},
            }
        if action == "defeature":
            return {
                "status": "complete",
                "run_dir": "/sandbox/ui/runs/test/agent-1",
                "report": {"artifacts": {"highlight_manifest": "highlight_manifest.json"}},
            }
        if action == "verify":
            return {"status": "complete", "verdict": "conditional_pass", "report": {}}
        raise AssertionError(action)

    def read_json(self, remote_path):
        return {
            "manifest_type": "cad_defeature_face_highlights",
            "model_path": "/sandbox/model.brep",
            "summary": {"highlight_count": 0, "by_status": {}},
            "highlights": [],
        }


def test_workflow_preserves_repeated_tolerance_decisions(tmp_path: Path) -> None:
    source = tmp_path / "part.igs"
    source.write_text("fixture", encoding="utf-8")
    runner = FakeRunner(source)
    service = WorkflowService(runner=runner, store=WorkflowStore(tmp_path / "state"))

    state = service.create(str(source))
    workflow_id = state["workflow_id"]
    state = service.heal(workflow_id)
    assert state["phase"] == "awaiting_tolerance_decision"
    assert state["tolerance_request"]["proposed_tolerance"] == 0.01

    state = service.approve(workflow_id, 0.01, "Engineer A", "Fixture review")
    assert state["phase"] == "awaiting_tolerance_decision"
    assert state["tolerance_request"]["proposed_tolerance"] == 0.1

    state = service.approve(workflow_id, 0.1, "Engineer A", "Separate higher-tolerance review")
    assert state["phase"] == "healing_complete"
    assert state["active_model"].endswith("/heal-approved-2/healed_solid.brep")


def test_analysis_exposes_highlight_manifest_and_verify_is_audited(tmp_path: Path) -> None:
    source = tmp_path / "part.igs"
    source.write_text("fixture", encoding="utf-8")
    runner = FakeRunner(source)
    service = WorkflowService(runner=runner, store=WorkflowStore(tmp_path / "state"))
    workflow_id = service.create(str(source))["workflow_id"]

    state = service.analyze(workflow_id)
    assert state["highlight_manifest"]["manifest_type"] == "cad_defeature_face_highlights"
    assert service.highlights(workflow_id)["highlights"] == []

    state = service.verify(workflow_id)
    assert state["phase"] == "verification_complete"
    assert state["verification"]["verdict"] == "conditional_pass"
    assert [event["action"] for event in state["events"]][-2:] == ["defeature", "verify"]


def test_approval_requires_the_exact_pending_request(tmp_path: Path) -> None:
    source = tmp_path / "part.igs"
    source.write_text("fixture", encoding="utf-8")
    service = WorkflowService(
        runner=FakeRunner(source), store=WorkflowStore(tmp_path / "state")
    )
    workflow_id = service.create(str(source))["workflow_id"]

    with pytest.raises(ValueError, match="no pending tolerance decision"):
        service.approve(workflow_id, 0.01, "Engineer A", "No request exists")

    service.heal(workflow_id)
    with pytest.raises(ValueError, match="must match the requested tolerance"):
        service.approve(workflow_id, 0.1, "Engineer A", "Too broad")


def test_store_rejects_path_like_workflow_ids(tmp_path: Path) -> None:
    store = WorkflowStore(tmp_path / "state")
    with pytest.raises(ValueError, match="12-character id"):
        store.load("../../outside")
