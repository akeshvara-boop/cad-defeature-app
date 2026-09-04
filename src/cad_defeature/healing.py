"""Conservative, auditable surface sewing and solid reconstruction."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from cad_defeature.check import analyze_validity
from cad_defeature.model import read_shape
from cad_defeature.repair import repair_shape

DEFAULT_TOLERANCES = (0.0001, 0.001, 0.01, 0.1)


def heal_to_solid(input_path: str | Path, output_dir: str | Path, tolerances=DEFAULT_TOLERANCES) -> dict[str, object]:
    """Export a BREP only when sewing existing faces yields a valid solid.

    The operation never fills gaps or creates geometry: it joins source faces
    within a recorded tolerance, optionally applies a reported-defect ShapeFix
    pass, and only accepts a result that is still valid after the file is
    written and read back from disk.
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
    shape = read_shape(source)
    attempts = []

    for tolerance in tolerances:
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
            repair = repair_shape(solid)
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
        return _finish(source, destination, attempts, "healed_solid_created", output_model.name)
    return _finish(source, destination, attempts, "healing_failed_needs_source_repair", None)


def _finish(source: Path, output: Path, attempts: list[dict[str, object]], decision: str, model: str | None) -> dict[str, object]:
    report = {
        "report_type": "cad_healing_report",
        "schema_version": "1.1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_model": str(source),
        "decision": decision,
        "healed_model": model,
        "safety_note": "No gaps were filled and no surfaces were invented. Output is accepted only if it is still valid after being written and read back.",
        "attempts": attempts,
    }
    (output / "healing_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
