"""Independent, report-only verification for CAD defeaturing runs."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from cad_defeature.audit import _sha256
from cad_defeature.inspect import inspect_model
from cad_defeature.policy import load_policy


class VerificationError(ValueError):
    """Raised when a verification input is incomplete or inconsistent."""


def verify_models(
    original_path: str | Path,
    candidate_path: str | Path,
    policy_path: str | Path,
    healing_report_path: str | Path | None = None,
) -> dict[str, object]:
    """Compare two CAD models against policy gates without modifying either file."""
    original = Path(original_path)
    candidate = Path(candidate_path)
    policy = load_policy(policy_path)
    original_inspection = inspect_model(original)
    candidate_inspection = inspect_model(candidate)

    if not original.is_file() or not candidate.is_file():
        missing = [str(path) for path in (original, candidate) if not path.is_file()]
        raise VerificationError(f"Verification input file was not found: {', '.join(missing)}")

    gates = _resolve_gates(policy)
    checks = [
        _kernel_import_check(original_inspection, candidate_inspection),
        _validity_check(candidate_inspection, bool(gates["require_valid_solid"])),
        _closure_check(candidate_inspection, bool(gates["require_closed_shell"])),
        _non_manifold_check(candidate_inspection, bool(gates["allow_non_manifold_edges"])),
        _bounding_box_check(original_inspection, candidate_inspection, float(gates["max_bounding_box_delta"])),
        _volume_check(original_inspection, candidate_inspection, float(gates["max_volume_delta_percent"])),
        _tolerance_provenance_check(healing_report_path),
    ]
    failed = [check for check in checks if check["status"] == "fail"]
    pending = [
        check for check in checks if check["status"] in ("not_assessed", "needs_review")
    ]
    verdict = "pass" if not failed and not pending else "fail" if failed else "needs_review"

    return {
        "report_type": "cad_defeature_verification",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "performed_read_only": True,
        "policy": {
            "name": policy["policy"]["name"],
            "version": policy["policy"]["version"],
            "mode": policy["policy"]["mode"],
        },
        "original": _model_record(original, original_inspection),
        "candidate": _model_record(candidate, candidate_inspection),
        "tolerance_provenance": _load_provenance(healing_report_path),
        "checks": checks,
        "summary": {
            "passed": len([check for check in checks if check["status"] == "pass"]),
            "failed": len(failed),
            "not_assessed": len(pending),
            "verdict": verdict,
        },
    }


def _model_record(path: Path, inspection: dict[str, object]) -> dict[str, object]:
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "inspection": inspection,
    }


def _kernel_import_check(original: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    statuses = {"original": original.get("status"), "candidate": candidate.get("status")}
    passed = all(status == "kernel_inspected" for status in statuses.values())
    return {
        "name": "kernel_import",
        "status": "pass" if passed else "fail",
        "observed": statuses,
        "requirement": "Both models must be kernel_inspected.",
    }


def _validity_check(inspection: dict[str, object], required: bool) -> dict[str, object]:
    solid = inspection.get("solid_construction") or {}
    observed = solid.get("solid_is_valid", inspection.get("shape_is_valid"))
    return {
        "name": "valid_solid",
        "status": "pass" if not required or observed is True else "fail",
        "observed": observed,
        "required": required,
    }


def _closure_check(inspection: dict[str, object], required: bool) -> dict[str, object]:
    solid = inspection.get("solid_construction") or {}
    free_edges = solid.get("free_edges_after_sewing")
    observed = free_edges == 0 if free_edges is not None else inspection.get("topology", {}).get("shells", 0) > 0
    return {
        "name": "closed_shell",
        "status": "pass" if not required or observed else "fail",
        "observed": observed,
        "free_edges_after_sewing": free_edges,
        "required": required,
    }


def _non_manifold_check(inspection: dict[str, object], allowed: bool) -> dict[str, object]:
    connectivity = inspection.get("connectivity") or {}
    count = connectivity.get("non_manifold_edge_count")
    if count is None:
        return {
            "name": "non_manifold_edges",
            "status": "not_assessed",
            "observed": None,
            "allowed": allowed,
        }
    return {
        "name": "non_manifold_edges",
        "status": "pass" if allowed or count == 0 else "fail",
        "observed": count,
        "allowed": allowed,
    }


def _bounding_box_check(original: dict[str, object], candidate: dict[str, object], maximum: float) -> dict[str, object]:
    original_box = _box(original)
    candidate_box = _box(candidate)
    if not original_box or not candidate_box:
        return {"name": "bounding_box_delta", "status": "not_assessed", "maximum": maximum}
    delta = max(abs(original_box[key] - candidate_box[key]) for key in original_box)
    return {
        "name": "bounding_box_delta",
        "status": "pass" if delta <= maximum else "fail",
        "observed": delta,
        "maximum": maximum,
    }


def _volume_check(original: dict[str, object], candidate: dict[str, object], maximum_percent: float) -> dict[str, object]:
    original_volume = _volume(original)
    candidate_volume = _volume(candidate)
    if original_volume in (None, 0) or candidate_volume is None:
        return {"name": "volume_delta_percent", "status": "not_assessed", "maximum": maximum_percent}
    delta = abs(candidate_volume - original_volume) / abs(original_volume) * 100
    return {
        "name": "volume_delta_percent",
        "status": "pass" if delta <= maximum_percent else "fail",
        "observed": delta,
        "maximum": maximum_percent,
    }


def _box(inspection: dict[str, object]) -> dict[str, float] | None:
    solid = inspection.get("solid_construction") or {}
    box = solid.get("bounding_box")
    return box if isinstance(box, dict) else None


def _volume(inspection: dict[str, object]) -> float | None:
    solid = inspection.get("solid_construction") or {}
    value = solid.get("volume")
    return float(value) if isinstance(value, int | float) else None


def _load_provenance(healing_report_path: str | Path | None) -> dict[str, object] | None:
    """Read the healing report so verification can see how the candidate was built."""
    if not healing_report_path:
        return None
    path = Path(healing_report_path)
    if not path.is_file():
        raise VerificationError(f"Healing report was not found: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    approval = report.get("tolerance_approval")
    return {
        "healing_report": str(path),
        "decision": report.get("decision"),
        "source_model": report.get("source_model"),
        "tolerance_approval": approval,
        "required_human_approval": approval is not None,
    }


def _tolerance_provenance_check(healing_report_path: str | Path | None) -> dict[str, object]:
    """Flag candidates built under a human tolerance concession.

    Per docs/decisions/ADR-0001 this is reported, never silently accepted: a
    model healed above the automatic ceiling carries geometric risk that a
    reviewer must weigh alongside the numeric gates.
    """
    provenance = _load_provenance(healing_report_path)
    if provenance is None:
        return {
            "name": "tolerance_provenance",
            "status": "not_assessed",
            "observed": None,
            "requirement": "Pass --healing-report to audit how the candidate solid was produced.",
        }
    approval = provenance.get("tolerance_approval")
    if not approval:
        return {
            "name": "tolerance_provenance",
            "status": "pass",
            "observed": "healed_within_automatic_tolerance_ceiling",
        }
    return {
        "name": "tolerance_provenance",
        "status": "needs_review",
        "observed": {
            "approved_tolerance": approval.get("approved_tolerance"),
            "max_auto_tolerance": approval.get("max_auto_tolerance"),
            "approved_by": approval.get("approved_by"),
            "approval_note": approval.get("approval_note"),
        },
        "requirement": (
            "This candidate was only buildable under a human tolerance concession above the "
            "automatic ceiling. Geometry may have moved by up to the approved tolerance, so a "
            "reviewer must confirm that deviation is acceptable for this part."
        ),
    }


REQUIRED_GATES = {
    "require_valid_solid": bool,
    "require_closed_shell": bool,
    "allow_non_manifold_edges": bool,
    "max_bounding_box_delta": float,
    "max_volume_delta_percent": float,
}


def _resolve_gates(policy: dict[str, object]) -> dict[str, object]:
    """Return the verification gates, refusing to guess at missing thresholds.

    A missing gate is a policy authoring error, not something to default.
    Silently substituting a threshold would mean the report claims a check was
    enforced against a limit nobody approved.
    """
    gates = policy.get("verification_gates")
    if not isinstance(gates, dict):
        raise VerificationError(
            "Policy is missing a verification_gates section, so no gate can be enforced."
        )
    missing = [name for name in REQUIRED_GATES if name not in gates]
    if missing:
        raise VerificationError(
            "Policy verification_gates is missing required gate(s): "
            + ", ".join(sorted(missing))
            + ". Add explicit values to the policy file; verification will not assume "
            + "a threshold that no human approved. Gates present: "
            + ", ".join(sorted(gates))
        )
    return gates
