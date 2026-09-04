"""Read-only in-memory solid-construction diagnostics."""

from __future__ import annotations


def diagnose_solid_construction(shape, tolerance: float = 0.001) -> dict[str, object]:
    """Attempt to build a solid from a sewn shell, without writing any file."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    sewing = BRepBuilderAPI_Sewing(tolerance)
    face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
    input_faces = 0
    while face_explorer.More():
        sewing.Add(face_explorer.Current())
        input_faces += 1
        face_explorer.Next()
    sewing.Perform()
    sewn_shape = sewing.SewedShape()

    shell_explorer = TopExp_Explorer(sewn_shape, TopAbs_SHELL)
    if not shell_explorer.More():
        return {
            "performed_in_memory": True,
            "tolerance": tolerance,
            "input_faces_added": input_faces,
            "status": "no_shell_produced",
            "solid_conversion_candidate": False,
        }

    shell = TopoDS.Shell(shell_explorer.Current())
    maker = BRepBuilderAPI_MakeSolid(shell)
    if not maker.IsDone():
        return {
            "performed_in_memory": True,
            "tolerance": tolerance,
            "input_faces_added": input_faces,
            "status": "solid_construction_failed",
            "solid_conversion_candidate": False,
        }

    solid = maker.Solid()
    valid = BRepCheck_Analyzer(solid).IsValid()
    volume = _volume(solid, BRepGProp, GProp_GProps)
    bounding_box = _bounding_box(solid, Bnd_Box, BRepBndLib)
    return {
        "performed_in_memory": True,
        "tolerance": tolerance,
        "input_faces_added": input_faces,
        "status": "solid_constructed" if valid else "solid_invalid",
        "solid_conversion_candidate": valid,
        "solid_is_null": solid.IsNull(),
        "solid_is_valid": valid,
        "volume": volume,
        "bounding_box": bounding_box,
        "free_edges_after_sewing": sewing.NbFreeEdges(),
        "degenerated_shapes_after_sewing": sewing.NbDegeneratedShapes(),
    }


def _volume(solid, brep_gprop, props_type) -> float:
    properties = props_type()
    brep_gprop.VolumeProperties_s(solid, properties)
    return properties.Mass()


def _bounding_box(solid, box_type, brep_bndlib) -> dict[str, float]:
    box = box_type()
    brep_bndlib.Add_s(solid, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return {
        "xmin": xmin,
        "ymin": ymin,
        "zmin": zmin,
        "xmax": xmax,
        "ymax": ymax,
        "zmax": zmax,
        "x_length": xmax - xmin,
        "y_length": ymax - ymin,
        "z_length": zmax - zmin,
    }
