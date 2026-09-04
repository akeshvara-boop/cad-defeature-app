"""Independent, report-only verification for CAD defeaturing runs."""

from __future__ import annotations

from datetime import UTC, datetime
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

    gates = policy["verification_gates"]
    checks = [
        _kernel_import_check(original_inspection, candidate_inspection),
        _validity_check(candidate_inspection, bool(gates["require_valid_solid"])),
        _closure_check(candidate_inspection, bool(gates["require_closed_shell"])),
        _non_manifold_check(candidate_inspection, bool(gates["allow_non_manifold_edges"])),
        _bounding_box_check(original_inspection, candidate_inspection, float(gates["max_bounding_box_delta"])),
        _volume_check(original_inspection, candidate_inspection, float(gates["max_volume_delta_percent"])),
    ]
    failed = [check for check in checks if check["status"] == "fail"]
    pending = [check for check in checks if check["status"] == "not_assessed"]
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
