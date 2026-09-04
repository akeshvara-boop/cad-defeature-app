"""Conservative, auditable surface sewing and solid reconstruction.

Healing runs unattended only within a conservative tolerance ceiling. When a
larger tolerance is required it stops and emits a decision request for a human,
per docs/decisions/ADR-0001.
"""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from cad_defeature.check import analyze_validity
from cad_defeature.model import read_shape
from cad_defeature.repair import repair_shape
from cad_defeature.tolerance_gate import (
    DECISION_REQUEST_FILENAME,
    DEFAULT_MAX_AUTO_TOLERANCE,
    ToleranceApprovalRequired,
    build_decision_request,
    validate_approval,
    write_json,
)

DEFAULT_TOLERANCES = (0.0001, 0.001, 0.01, 0.1, 0.5, 1.0)


def heal_to_solid(
    input_path: str | Path,
    output_dir: str | Path,
    tolerances=DEFAULT_TOLERANCES,
    max_auto_tolerance: float = DEFAULT_MAX_AUTO_TOLERANCE,
    approval: dict[str, object] | None = None,
) -> dict[str, object]:
    """Export a BREP only when sewing existing faces yields a valid solid.

    The operation never fills gaps or creates geometry: it joins source faces
    within a recorded tolerance, optionally applies a reported-defect ShapeFix
    pass, and only accepts a result that is still valid after the file is
    written and read back from disk.

    Tolerances above ``max_auto_tolerance`` are attempted only when ``approval``
    carries a valid human grant; otherwise ``ToleranceApprovalRequired`` is
    raised with the evidence a reviewer needs.
    """
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    source, destination = Path(input_path), Path(output_dir)
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Refusing to write into non-empty output directory: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    approval_record = None
    ceiling = float(max_auto_tolerance)
    if approval:
        # The approved value must clear the automatic ceiling to mean anything.
        approval_record = validate_approval(approval, float(max_auto_tolerance), float(max_auto_tolerance))
        ceiling = approval_record["approved_tolerance"]

    shape = read_shape(source)
    attempts: list[dict[str, object]] = []
    deferred: list[float] = []

    for tolerance in tolerances:
        if float(tolerance) > ceiling:
            deferred.append(float(tolerance))
            continue

        sewing = BRepBuilderAPI_Sewing(float(tolerance))
        faces = TopExp_Explorer(shape, TopAbs_FACE)
        count = 0
        while faces.More():
            sewing.Add(faces.Current())
            count += 1
            faces.Next()
        sewing.Perform()
        sewn = sewing.SewedShape()
        attempt: dict[str, object] = {
            "tolerance": tolerance,
            "faces_added": count,
            "free_edges": sewing.NbFreeEdges(),
            "multiple_edges": sewing.NbMultipleEdges(),
            "degenerated_shapes": sewing.NbDegeneratedShapes(),
            "status": "not_closed",
            "within_auto_ceiling": float(tolerance) <= float(max_auto_tolerance),
        }
        shells = TopExp_Explorer(sewn, TopAbs_SHELL)
        if sewing.NbFreeEdges() != 0 or not shells.More():
            attempts.append(attempt)
            continue

        maker = BRepBuilderAPI_MakeSolid(TopoDS.Shell(shells.Current()))
        if not maker.IsDone() or maker.Solid().IsNull():
            attempt["status"] = "solid_construction_failed"
            attempts.append(attempt)
            continue

        solid = maker.Solid()
        attempt["validity_before_repair"] = analyze_validity(solid)
        if not attempt["validity_before_repair"]["overall_valid"]:
            repair = repair_shape(solid, max_tolerance_limit=ceiling)
            attempt["repair"] = repair["record"]
            solid = repair["shape"]
        if not analyze_validity(solid)["overall_valid"]:
            attempt["status"] = "constructed_solid_invalid"
            attempts.append(attempt)
            continue

        output_model = destination / "healed_solid.brep"
        BRepTools.Write_s(solid, str(output_model))
        roundtrip = analyze_validity(read_shape(output_model))
        attempt["validity_after_write_read"] = roundtrip
        if not roundtrip["overall_valid"]:
            output_model.unlink()
            attempt["status"] = "write_read_roundtrip_invalid"
            attempts.append(attempt)
            continue

        attempt["status"] = "valid_solid_exported"
        attempts.append(attempt)
        return _finish(
            source, destination, attempts, "healed_solid_created", output_model.name, approval_record
        )

    if deferred:
        request = build_decision_request(source, attempts, float(max_auto_tolerance), min(deferred))
        write_json(destination / DECISION_REQUEST_FILENAME, request)
        _finish(source, destination, attempts, "tolerance_approval_required", None, approval_record)
        raise ToleranceApprovalRequired(request)

    return _finish(
        source, destination, attempts, "healing_failed_needs_source_repair", None, approval_record
    )


def _finish(
    source: Path,
    output: Path,
    attempts: list[dict[str, object]],
    decision: str,
    model: str | None,
    approval_record: dict[str, object] | None,
) -> dict[str, object]:
    report = {
        "report_type": "cad_healing_report",
        "schema_version": "1.2",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_model": str(source),
        "decision": decision,
        "healed_model": model,
        "tolerance_approval": approval_record,
        "safety_note": (
            "No gaps were filled and no surfaces were invented. Output is accepted only if it "
            "is still valid after being written and read back. Tolerances above the automatic "
            "ceiling are used only under a recorded human approval."
        ),
        "attempts": attempts,
    }
    (output / "healing_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report
