import json
from pathlib import Path

import pytest

import cad_defeature.verification as verification
from cad_defeature.verification_artifacts import ARTIFACT_NAMES, write_verification_package


def _inspection(non_manifold_edges: int = 0, min_edge_length: float = 2.0) -> dict:
    return {
        "status": "kernel_inspected",
        "shape_is_valid": True,
        "topology": {"solids": 1, "shells": 1, "faces": 8, "edges": 12, "vertices": 8},
        "connectivity": {
            "non_manifold_edges": non_manifold_edges,
            "min_edge_length": min_edge_length,
        },
        "solid_construction": {
            "solid_is_valid": True,
            "free_edges_after_sewing": 0,
            "bounding_box": {
                "xmin": 0.0, "ymin": 0.0, "zmin": 0.0,
                "xmax": 2.0, "ymax": 2.0, "zmax": 2.0,
            },
            "volume": 8.0,
        },
    }


def _policy(approved: bool = True, min_feature_size: float | None = 1.0) -> dict:
    provenance = {
        "status": "engineer_approved" if approved else "agent_proposed_unapproved",
        "approved_by": "engineer@example.com" if approved else None,
        "approved_at_utc": "2026-09-08T00:00:00+00:00" if approved else None,
        "pending_owner": None if approved else "AgentReviewer",
    }
    return {
        "policy": {"name": "test", "version": "1", "mode": "report_only"},
        "input_requirements": {},
        "protected_geometry": {},
        "candidate_feature_classes": {},
        "verification_gates": {
            "require_valid_solid": True,
            "require_closed_shell": True,
            "allow_non_manifold_edges": False,
            "max_bounding_box_delta": 0.0,
            "bounding_box_numerical_noise": 1e-6,
            "max_volume_delta_percent": 1.0,
            "min_feature_size": min_feature_size,
        },
        "audit_requirements": {},
        "threshold_provenance": provenance,
        "use_case": {"name": "test"},
    }


def _run_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    approved: bool = True,
    min_feature_size: float | None = 1.0,
    non_manifold_edges: int = 0,
) -> dict:
    original = tmp_path / "original.brep"
    candidate = tmp_path / "candidate.brep"
    original.write_bytes(b"original")
    candidate.write_bytes(b"candidate")
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(json.dumps(_policy(approved, min_feature_size)), encoding="utf-8")
    healing_path = tmp_path / "healing.json"
    healing_path.write_text(
        json.dumps({"decision": "healed", "tolerance_approval": None}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        verification,
        "inspect_model",
        lambda _path: _inspection(non_manifold_edges=non_manifold_edges),
    )
    monkeypatch.setattr(
        verification,
        "_residual_feature_check",
        lambda _candidate, _policy: {
            "name": "residual_features",
            "status": "pass",
            "observed": {
                "candidate_count": 0,
                "eligible_residual_count": 0,
                "unclassified_count": 0,
                "residuals": [],
                "unclassified": [],
            },
        },
    )
    return verification.verify_models(
        original, candidate, policy_path, healing_report_path=healing_path
    )


def test_all_assessed_approved_checks_pass(monkeypatch, tmp_path) -> None:
    report = _run_report(monkeypatch, tmp_path)
    assert report["summary"]["verdict"] == "pass"
    assert report["summary"]["blocking_checks"] == []
    assert report["summary"]["review_checks"] == []


def test_review_condition_produces_conditional_pass(monkeypatch, tmp_path) -> None:
    report = _run_report(monkeypatch, tmp_path, approved=False)
    assert report["summary"]["verdict"] == "conditional_pass"
    assert report["summary"]["blocking_checks"] == []
    assert "threshold_provenance" in report["summary"]["review_checks"]


def test_unassessed_gate_requires_review(monkeypatch, tmp_path) -> None:
    report = _run_report(monkeypatch, tmp_path, min_feature_size=None)
    assert report["summary"]["verdict"] == "needs_review"
    assert "min_feature_size" in report["summary"]["blocking_checks"]


def test_non_manifold_connectivity_key_is_enforced(monkeypatch, tmp_path) -> None:
    report = _run_report(monkeypatch, tmp_path, non_manifold_edges=2)
    check = next(item for item in report["checks"] if item["name"] == "non_manifold_edges")
    assert check["observed"] == 2
    assert check["status"] == "fail"
    assert report["summary"]["verdict"] == "fail"


def test_verification_package_contains_all_phase_three_artifacts(monkeypatch, tmp_path) -> None:
    report = _run_report(monkeypatch, tmp_path)
    output = tmp_path / "verification"
    package = write_verification_package(report, output)
    assert set(path.name for path in output.iterdir()) == set(ARTIFACT_NAMES.values())
    assert Path(package["artifacts"]["final_decision"]).is_file()
    decision = json.loads((output / "final_decision.json").read_text(encoding="utf-8"))
    assert decision["verdict"] == "pass"
    assert decision["ready_for_downstream"] is True
    with pytest.raises(FileExistsError):
        write_verification_package(report, output)
