"""NemoClaw tool surface for the human-in-the-loop tolerance decision.

Exposes healing as a conversational interaction rather than a CLI flag
(docs/decisions/ADR-0001). The agent calls ``heal_model``; when a tolerance
concession is needed it returns a structured ``needs_human_decision`` payload
that NemoClaw renders to the reviewer. The reviewer's answer comes back through
``approve_tolerance`` or ``reject_tolerance``.

Design rules enforced here:
- The agent never self-approves. ``approved_by`` must be a human identity and
  must not be the agent itself.
- Approval is scoped to one run directory and one source model. It cannot be
  replayed against a different model.
- Rejection is a first-class, recorded outcome, not an error.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from cad_defeature.healing import heal_to_solid
from cad_defeature.tolerance_gate import (
    APPROVAL_FILENAME,
    DEFAULT_MAX_AUTO_TOLERANCE,
    ToleranceApprovalRequired,
    risk_statement,
    write_json,
)

AGENT_IDENTITIES = {"agent", "cad-defeature", "nemoclaw", "assistant", "system"}


def heal_model(
    input_path: str,
    output_dir: str,
    max_auto_tolerance: float = DEFAULT_MAX_AUTO_TOLERANCE,
) -> dict[str, object]:
    """Heal a CAD model, pausing for human input if tolerance must be raised."""
    try:
        report = heal_to_solid(input_path, output_dir, max_auto_tolerance=max_auto_tolerance)
    except ToleranceApprovalRequired as pause:
        return {
            "status": "needs_human_decision",
            "run_dir": str(output_dir),
            "question": _question_text(pause.request),
            "request": pause.request,
            "respond_with": ["approve_tolerance", "reject_tolerance"],
        }
    return {"status": "complete", "run_dir": str(output_dir), "report": report}


def approve_tolerance(
    input_path: str,
    output_dir: str,
    approved_tolerance: float,
    approved_by: str,
    approval_note: str,
    max_auto_tolerance: float = DEFAULT_MAX_AUTO_TOLERANCE,
) -> dict[str, object]:
    """Resume healing under a recorded human tolerance approval.

    ``output_dir`` must be a NEW directory: the approved run is a distinct,
    separately auditable artifact set from the run that requested the decision.
    """
    _reject_agent_identity(approved_by)
    if not approval_note or not approval_note.strip():
        raise ValueError("An engineering justification is required to approve a tolerance.")

    approval = {
        "approved_tolerance": float(approved_tolerance),
        "approved_by": approved_by,
        "approval_note": approval_note,
    }
    report = heal_to_solid(
        input_path,
        output_dir,
        max_auto_tolerance=max_auto_tolerance,
        approval=approval,
    )
    write_json(
        Path(output_dir) / APPROVAL_FILENAME,
        {
            "report_type": "tolerance_approval",
            "schema_version": "1.0",
            "source_model": str(input_path),
            "granted_at_utc": datetime.now(UTC).isoformat(),
            "risk_acknowledged": risk_statement(float(approved_tolerance)),
            "scope": "single_run",
            **approval,
        },
    )
    return {"status": "complete", "run_dir": str(output_dir), "report": report}


def reject_tolerance(
    input_path: str,
    output_dir: str,
    rejected_by: str,
    rejection_note: str,
) -> dict[str, object]:
    """Record that a human declined the tolerance concession."""
    _reject_agent_identity(rejected_by)
    record = {
        "report_type": "tolerance_rejection",
        "schema_version": "1.0",
        "source_model": str(input_path),
        "rejected_by": rejected_by,
        "rejection_note": rejection_note,
        "rejected_at_utc": datetime.now(UTC).isoformat(),
        "consequence": "Healing stops. No model was produced and the source model is unchanged.",
        "recommended_next_step": (
            "Obtain a native closed-solid STEP AP242 or BREP export of this part from the "
            "source CAD system, which removes the need for any tolerance concession."
        ),
    }
    write_json(Path(output_dir) / "tolerance_rejection.json", record)
    return {"status": "rejected", "run_dir": str(output_dir), "record": record}


def _question_text(request: dict[str, object]) -> str:
    """Plain-language question for the reviewer, not a raw JSON dump."""
    proposed = request.get("proposed_tolerance")
    faces = request.get("blocking_faces") or []
    return (
        f"Healing cannot produce a valid solid within the automatic tolerance ceiling of "
        f"{request.get('max_auto_tolerance')} mm. The smallest tolerance that would allow "
        f"progress is {proposed} mm. Blocking face indices: {faces or 'none recorded'}.\n\n"
        f"{risk_statement(proposed) if proposed else ''}\n\n"
        "Approve this tolerance (with a justification), or reject it and request a native "
        "closed-solid export instead?"
    )


def _reject_agent_identity(identity: str) -> None:
    if not identity or not identity.strip():
        raise ValueError("An accountable human identity is required.")
    if identity.strip().lower() in AGENT_IDENTITIES:
        raise ValueError(
            "Tolerance decisions cannot be made by the agent. Supply the responsible human."
        )
