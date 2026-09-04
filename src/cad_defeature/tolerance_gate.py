"""Human-in-the-loop tolerance gate (see docs/decisions/ADR-0001).

The agent heals unattended only within a conservative automatic tolerance
ceiling. Above that ceiling it must stop, emit a decision request describing the
geometric risk in plain terms, and wait for a NemoClaw approval grant carrying an
accountable human identity.

Nothing here loosens any other safety rule: approval raises the tolerance
ceiling and nothing else.
"""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

DEFAULT_MAX_AUTO_TOLERANCE = 0.001
DECISION_REQUEST_FILENAME = "tolerance_decision_request.json"
APPROVAL_FILENAME = "tolerance_approval.json"

# Hard stop. Even an approved human cannot exceed this via the agent; beyond it
# the correct action is a native solid export, not a looser tolerance.
ABSOLUTE_TOLERANCE_CEILING = 1.0


class ToleranceApprovalRequired(Exception):
    """Raised when healing needs a tolerance above the automatic ceiling."""

    def __init__(self, request: dict[str, object]) -> None:
        super().__init__(
            "Tolerance above the automatic ceiling is required. "
            "A human must approve the proposed tolerance before healing can continue."
        )
        self.request = request


def risk_statement(tolerance: float) -> str:
    """Describe, in engineering terms, what a tolerance concession permits."""
    return (
        f"Sewing and repair may join or adjust geometry across gaps of up to {tolerance} mm. "
        f"Any real feature, gap, or surface mismatch smaller than {tolerance} mm may be "
        "closed or moved by that amount. Approve only if a deviation of this size is "
        "acceptable for this part's fit, function, and downstream simulation."
    )


def build_decision_request(
    source_model: str | Path,
    attempts: list[dict[str, object]],
    max_auto_tolerance: float,
    proposed_tolerance: float | None,
) -> dict[str, object]:
    """Assemble the evidence a human needs in order to rule on tolerance."""
    blocking_faces: list[int] = []
    for attempt in attempts:
        validity = attempt.get("validity_before_repair") or {}
        examples = validity.get("invalid_examples") or {}
        for face_index in examples.get("faces", []):
            if face_index not in blocking_faces:
                blocking_faces.append(face_index)

    return {
        "report_type": "tolerance_decision_request",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_model": str(source_model),
        "decision_required": "approve_or_reject_tolerance",
        "max_auto_tolerance": max_auto_tolerance,
        "proposed_tolerance": proposed_tolerance,
        "absolute_ceiling": ABSOLUTE_TOLERANCE_CEILING,
        "blocking_faces": blocking_faces,
        "evidence": [
            {
                "tolerance": attempt.get("tolerance"),
                "status": attempt.get("status"),
                "free_edges": attempt.get("free_edges"),
                "degenerated_shapes": attempt.get("degenerated_shapes"),
                "invalid_counts": (attempt.get("validity_before_repair") or {}).get("invalid_counts"),
            }
            for attempt in attempts
        ],
        "risk_if_approved": risk_statement(proposed_tolerance) if proposed_tolerance else None,
        "recommended_alternative": (
            "Prefer a native closed-solid STEP AP242 or BREP export from the source CAD "
            "system. That removes the surface-sewing problem entirely and needs no "
            "tolerance concession."
        ),
        "how_to_approve": {
            "nemoclaw_tool": "approve_tolerance",
            "required_fields": ["approved_tolerance", "approved_by", "approval_note"],
            "note": "Approval applies to this run only and is never reused implicitly.",
        },
    }


def validate_approval(
    approval: dict[str, object] | None,
    proposed_tolerance: float,
    max_auto_tolerance: float,
) -> dict[str, object]:
    """Return a normalised approval record, or raise if it is not usable."""
    if not approval:
        raise ValueError("No tolerance approval was supplied.")
    for field in ("approved_tolerance", "approved_by", "approval_note"):
        if not approval.get(field):
            raise ValueError(f"Tolerance approval is missing required field: {field}")

    approved = float(approval["approved_tolerance"])
    if approved > ABSOLUTE_TOLERANCE_CEILING:
        raise ValueError(
            f"Approved tolerance {approved} exceeds the absolute ceiling "
            f"{ABSOLUTE_TOLERANCE_CEILING}. Obtain a native solid export instead."
        )
    if approved < proposed_tolerance:
        raise ValueError(
            f"Approved tolerance {approved} is below the {proposed_tolerance} required "
            "to progress, so healing would still fail. Approve the required value or reject."
        )
    return {
        "approved_tolerance": approved,
        "approved_by": str(approval["approved_by"]),
        "approval_note": str(approval["approval_note"]),
        "max_auto_tolerance": max_auto_tolerance,
        "granted_at_utc": datetime.now(UTC).isoformat(),
        "risk_acknowledged": risk_statement(approved),
        "scope": "single_run",
    }


def write_json(path: str | Path, payload: dict[str, object]) -> Path:
    """Write an audit artifact deterministically."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target
