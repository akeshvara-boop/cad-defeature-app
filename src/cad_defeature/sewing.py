"""In-memory OpenCascade surface-sewing diagnostics.

This module never writes a CAD file. It is intentionally limited to reporting
what a sewing pass could reconstruct from imported faces.
"""

from __future__ import annotations


def diagnose_sewing(shape, tolerance: float = 0.001) -> dict[str, object]:
    """Sew all faces in *shape* in memory and return validation facts."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    sewing = BRepBuilderAPI_Sewing(tolerance)
    faces = list(_shapes_of_type(shape, TopExp_Explorer, TopAbs_FACE))
    for face in faces:
        sewing.Add(face)
    sewing.Perform()
    sewn_shape = sewing.SewedShape()

    topology = {
        "solids": _count(sewn_shape, TopExp_Explorer, TopAbs_SOLID),
        "shells": _count(sewn_shape, TopExp_Explorer, TopAbs_SHELL),
        "faces": _count(sewn_shape, TopExp_Explorer, TopAbs_FACE),
        "edges": _count(sewn_shape, TopExp_Explorer, TopAbs_EDGE),
    }
    return {
        "performed_in_memory": True,
        "tolerance": tolerance,
        "input_faces_added": len(faces),
        "sewn_shape_is_null": sewn_shape.IsNull(),
        "sewn_shape_is_valid": BRepCheck_Analyzer(sewn_shape).IsValid(),
        "free_edges_after_sewing": sewing.NbFreeEdges(),
        "multiple_edges_after_sewing": sewing.NbMultipleEdges(),
        "degenerated_shapes": sewing.NbDegeneratedShapes(),
        "topology": topology,
        "solid_conversion_candidate": topology["shells"] > 0 and sewing.NbFreeEdges() == 0,
    }


def _shapes_of_type(shape, explorer_type, shape_type):
    explorer = explorer_type(shape, shape_type)
    while explorer.More():
        yield explorer.Current()
        explorer.Next()


def _count(shape, explorer_type, shape_type) -> int:
    return sum(1 for _ in _shapes_of_type(shape, explorer_type, shape_type))
