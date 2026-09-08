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
        _bounding_box_check(
            original_inspection,
            candidate_inspection,
            float(gates["max_bounding_box_delta"]),
            float(gates.get("bounding_box_numerical_noise") or 0.0),
        ),
        _volume_check(original_inspection, candidate_inspection, float(gates["max_volume_delta_percent"])),
        _tolerance_provenance_check(healing_report_path),
        _min_feature_size_check(candidate_inspection, gates.get("min_feature_size")),
        _threshold_provenance_check(policy),
        _residual_feature_check(candidate, policy),
    ]
    failed = [check for check in checks if check["status"] == "fail"]
    needs_review = [check for check in checks if check["status"] == "needs_review"]
    not_assessed = [check for check in checks if check["status"] == "not_assessed"]
    if failed:
        verdict = "fail"
    elif not_assessed:
        verdict = "needs_review"
    elif needs_review:
        verdict = "conditional_pass"
    else:
        verdict = "pass"

    return {
        "report_type": "cad_defeature_verification",
        "schema_version": "1.1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "performed_read_only": True,
        "policy": {
            "name": policy["policy"]["name"],
            "version": policy["policy"]["version"],
            "mode": policy["policy"]["mode"],
        },
        "original": _model_record(original, original_inspection),
        "candidate": _model_record(candidate, candidate_inspection),
        "threshold_provenance": policy.get("threshold_provenance"),
        "use_case": policy.get("use_case"),
        "reviewer_notice": _reviewer_notice(policy),
        "tolerance_provenance": _load_provenance(healing_report_path),
        "checks": checks,
        "summary": {
            "passed": len([check for check in checks if check["status"] == "pass"]),
            "failed": len(failed),
            "needs_review": len(needs_review),
            "not_assessed": len(not_assessed),
            "verdict": verdict,
            "blocking_checks": [check["name"] for check in failed + not_assessed],
            "review_checks": [check["name"] for check in needs_review],
            "verdict_reason": _verdict_reason(failed, needs_review, not_assessed),
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
    # The connectivity report contract uses ``non_manifold_edges``. Retain the
    # earlier key as a compatibility fallback for already-generated fixtures.
    count = connectivity.get("non_manifold_edges", connectivity.get("non_manifold_edge_count"))
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


def _bounding_box_check(
    original: dict[str, object],
    candidate: dict[str, object],
    maximum: float,
    numerical_noise: float = 0.0,
) -> dict[str, object]:
    original_box = _box(original)
    candidate_box = _box(candidate)
    if not original_box or not candidate_box:
        return {"name": "bounding_box_delta", "status": "not_assessed", "maximum": maximum}
    delta = max(abs(original_box[key] - candidate_box[key]) for key in original_box)
    effective = maximum + numerical_noise
    return {
        "name": "bounding_box_delta",
        "status": "pass" if delta <= effective else "fail",
        "observed": delta,
        "maximum": maximum,
        "numerical_noise_allowance": numerical_noise,
        "effective_limit": effective,
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


def _residual_feature_check(candidate: Path, policy: dict[str, object]) -> dict[str, object]:
    """Independently inventory policy-eligible features left in the candidate.

    This is deliberately a verification-time inventory. It does not trust the
    Defeaturing Agent's removal manifest or its claimed outcome.
    """
    try:
        from cad_defeature.inventory import inventory_features
        from cad_defeature.model import read_defeaturing_solid

        inventory = inventory_features(read_defeaturing_solid(candidate), policy)
    except (ImportError, ValueError) as error:
        return {
            "name": "residual_features",
            "status": "not_assessed",
            "observed": None,
            "requirement": (
                "Independent residual-feature inventory could not be completed: "
                f"{error}"
            ),
        }

    residuals = [
        item for item in inventory.get("candidates", []) if item.get("policy_eligible")
    ]
    unclassified = list(inventory.get("unclassified_revolutions", []))
    if residuals:
        status = "fail"
        requirement = "No policy-eligible removable feature may remain in the candidate."
    elif unclassified:
        status = "needs_review"
        requirement = (
            "Unclassified surfaces remain and require topology-aware confirmation before "
            "the candidate can receive an unconditional pass."
        )
    else:
        status = "pass"
        requirement = "No policy-eligible removable feature remains in the candidate."

    return {
        "name": "residual_features",
        "status": status,
        "observed": {
            "candidate_count": inventory.get("candidate_count", 0),
            "eligible_residual_count": len(residuals),
            "unclassified_count": len(unclassified),
            "residuals": residuals,
            "unclassified": unclassified,
        },
        "requirement": requirement,
        "performed_read_only": True,
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


def _verdict_reason(
    failed: list[dict[str, object]],
    needs_review: list[dict[str, object]],
    not_assessed: list[dict[str, object]],
) -> str:
    """State plainly why the verdict is what it is, naming the checks involved."""
    if failed:
        return (
            "Failed policy gate(s): "
            + ", ".join(check["name"] for check in failed)
        )
    parts: list[str] = []
    if needs_review:
        parts.append(
            "Human review required for: "
            + ", ".join(check["name"] for check in needs_review)
        )
    if not_assessed:
        parts.append(
            "Could not be assessed (insufficient input or geometry data): "
            + ", ".join(check["name"] for check in not_assessed)
        )
    if parts:
        return " ".join(parts)
    return "All policy gates passed and every check was assessable."


REVIEWER_NOTICE_UNAPPROVED = (
    "THRESHOLDS NOT ENGINEERING-APPROVED. The numeric gates in this policy are agent-proposed placeholders. A pass verdict means only that the candidate met the assistant's proposed limits, NOT that it is acceptable for engineering use. See REVIEWER_NOTES.md and ratify the thresholds with a named owner before relying on this report."
)


# Placeholder identities that look like an owner but carry no accountability.
# Ratification by any of these is rejected outright.
PLACEHOLDER_OWNERS = {
    "agentreviewer",
    "agent",
    "assistant",
    "nemoclaw",
    "system",
    "tbd",
    "unassigned",
    "none",
}


def _is_real_owner(identity: object) -> bool:
    """True only for a named human; placeholders never confer approval."""
    if not isinstance(identity, str) or not identity.strip():
        return False
    return identity.strip().lower() not in PLACEHOLDER_OWNERS


def _reviewer_notice(policy: dict[str, object]) -> str | None:
    """Surface an unmissable warning while thresholds remain unratified."""
    provenance = policy.get("threshold_provenance") or {}
    if provenance.get("status") == "engineer_approved" and _is_real_owner(
        provenance.get("approved_by")
    ):
        return None
    pending = provenance.get("pending_owner")
    if pending and not _is_real_owner(pending):
        return (
            REVIEWER_NOTICE_UNAPPROVED
            + f" Threshold ownership is currently a placeholder ({pending}); no accountable engineering owner has been assigned."
        )
    return REVIEWER_NOTICE_UNAPPROVED


def _threshold_provenance_check(policy: dict[str, object]) -> dict[str, object]:
    """Treat unratified thresholds as an explicit review item, not silence."""
    provenance = policy.get("threshold_provenance") or {}
    approved_by = provenance.get("approved_by")
    pending_owner = provenance.get("pending_owner")
    if provenance.get("status") == "engineer_approved" and _is_real_owner(approved_by):
        return {
            "name": "threshold_provenance",
            "status": "pass",
            "observed": {"approved_by": approved_by, "approved_at_utc": provenance.get("approved_at_utc")},
        }
    if approved_by and not _is_real_owner(approved_by):
        return {
            "name": "threshold_provenance",
            "status": "fail",
            "observed": {"approved_by": approved_by},
            "requirement": (
                "Thresholds were marked approved by a placeholder identity. Approval requires a named, accountable human owner."
            ),
        }
    return {
        "name": "threshold_provenance",
        "status": "needs_review",
        "observed": {
            "status": provenance.get("status"),
            "approved_by": approved_by,
            "pending_owner": pending_owner,
            "pending_owner_is_placeholder": bool(
                pending_owner and not _is_real_owner(pending_owner)
            ),
        },
        "requirement": (
            "The numeric gates used to judge this model have not been ratified by a named "
            "engineering owner, so a pass verdict carries no engineering authority."
        ),
    }


def _min_feature_size_check(
    inspection: dict[str, object], minimum: float | None
) -> dict[str, object]:
    """Primary defeaturing control: the smallest feature that must survive.

    Per NVIDIA CAD-to-Mesh A2A geometry verification, minimum feature size is a
    required reported quantity. Volume delta alone cannot distinguish removing
    fastener holes from removing a coolant channel.
    """
    if minimum is None:
        return {
            "name": "min_feature_size",
            "status": "not_assessed",
            "observed": None,
            "minimum": None,
            "requirement": (
                "No engineer has declared the smallest feature that must survive "
                "defeaturing. Set verification_gates.min_feature_size in the policy; "
                "this gate is not defaulted because guessing it would permit silent "
                "loss of a physics-critical feature."
            ),
        }
    connectivity = inspection.get("connectivity") or {}
    observed = connectivity.get("min_edge_length")
    if observed is None:
        return {
            "name": "min_feature_size",
            "status": "not_assessed",
            "observed": None,
            "minimum": minimum,
            "requirement": (
                "Inspection did not report a minimum edge length for this model, so the "
                "declared minimum feature size could not be enforced."
            ),
        }
    return {
        "name": "min_feature_size",
        "status": "pass" if float(observed) >= float(minimum) else "fail",
        "observed": float(observed),
        "minimum": float(minimum),
    }
