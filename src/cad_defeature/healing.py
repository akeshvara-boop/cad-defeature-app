"""Conservative, auditable surface sewing and solid reconstruction."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from cad_defeature.model import read_shape

DEFAULT_TOLERANCES = (0.0001, 0.001, 0.01, 0.1)


def heal_to_solid(input_path: str | Path, output_dir: str | Path, tolerances=DEFAULT_TOLERANCES) -> dict[str, object]:
    """Export a BREP only when sewing existing faces yields a valid solid.

    The operation never fills gaps or creates geometry: it joins source faces
    within a recorded tolerance and rejects any result with remaining free edges.
    """
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.BRepCheck import BRepCheck_Analyzer
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
        attempt = {
            "tolerance": tolerance,
            "faces_added": count,
            "free_edges": sewing.NbFreeEdges(),
            "multiple_edges": sewing.NbMultipleEdges(),
            "degenerated_shapes": sewing.NbDegeneratedShapes(),
            "status": "not_closed",
        }
        shells = TopExp_Explorer(sewn, TopAbs_SHELL)
        if sewing.NbFreeEdges() == 0 and shells.More():
            maker = BRepBuilderAPI_MakeSolid(TopoDS.Shell(shells.Current()))
            if maker.IsDone() and not maker.Solid().IsNull() and BRepCheck_Analyzer(maker.Solid()).IsValid():
                output_model = destination / "healed_solid.brep"
                BRepTools.Write_s(maker.Solid(), str(output_model))
                attempt["status"] = "valid_solid_exported"
                attempts.append(attempt)
                return _finish(source, destination, attempts, "healed_solid_created", output_model.name)
            attempt["status"] = "constructed_solid_invalid"
        attempts.append(attempt)
    return _finish(source, destination, attempts, "healing_failed_needs_source_repair", None)


def _finish(source: Path, output: Path, attempts: list[dict[str, object]], decision: str, model: str | None) -> dict[str, object]:
    report = {
        "report_type": "cad_healing_report",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_model": str(source),
        "decision": decision,
        "healed_model": model,
        "safety_note": "No gaps were filled and no surfaces were invented. Output is written only after valid closed-solid construction.",
        "attempts": attempts,
    }
    (output / "healing_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
