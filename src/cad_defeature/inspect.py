"""Read-only baseline and OpenCascade topology inspection for CAD input files."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_SUFFIXES = {".step", ".stp", ".brep", ".brp", ".iges", ".igs"}


def inspect_model(input_path: str | Path) -> dict[str, object]:
    """Return file-level metadata and, when possible, geometry facts.

    The input model is never modified.  Kernel import errors are returned as
    structured diagnostics so callers can distinguish file-level validation
    from geometry parsing failures.
    """
    path = Path(input_path)
    suffix = path.suffix.lower()
    exists = path.is_file()
    result: dict[str, object] = {
        "input_path": str(path),
        "exists": exists,
        "suffix": suffix,
        "supported_format": suffix in SUPPORTED_SUFFIXES,
        "status": "ready_for_kernel_inspection" if exists else "input_not_found",
    }
    if not exists:
        return result

    result["size_bytes"] = path.stat().st_size
    if suffix not in SUPPORTED_SUFFIXES:
        result["status"] = "unsupported_format"
        return result

    try:
        result.update(_inspect_topology(path, suffix))
    except ImportError:
        result["status"] = "kernel_unavailable"
        result["diagnostic"] = "Install cadquery-ocp in the active environment."
    except ValueError as error:
        result["status"] = "kernel_import_failed"
        result["diagnostic"] = str(error)
    return result


def _inspect_topology(path: Path, suffix: str) -> dict[str, object]:
    """Load one CAD file with OpenCascade and report read-only topology facts."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepTools import BRepTools
    from OCP.IGESControl import IGESControl_Reader
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_VERTEX

    if suffix in {".igs", ".iges"}:
        reader = IGESControl_Reader()
        transfer_label = "iges"
    elif suffix in {".step", ".stp"}:
        reader = STEPControl_Reader()
        transfer_label = "step"
    else:
        shape = _read_brep(path, BRep_Builder, BRepTools)
        transfer_label = "brep"
        return _shape_facts(shape, transfer_label, BRepCheck_Analyzer, TopExp_Explorer,
                            TopAbs_SOLID, TopAbs_SHELL, TopAbs_FACE, TopAbs_EDGE,
                            TopAbs_VERTEX, TopAbs_COMPOUND, TopAbs_COMPSOLID)

    read_status = reader.ReadFile(str(path))
    if read_status != IFSelect_RetDone:
        raise ValueError(f"OpenCascade could not read the {transfer_label.upper()} file.")
    transferred = reader.TransferRoots()
    if transferred < 1:
        raise ValueError(f"OpenCascade found no transferable roots in the {transfer_label.upper()} file.")
    shape = reader.OneShape()
    return _shape_facts(shape, transfer_label, BRepCheck_Analyzer, TopExp_Explorer,
                        TopAbs_SOLID, TopAbs_SHELL, TopAbs_FACE, TopAbs_EDGE,
                        TopAbs_VERTEX, TopAbs_COMPOUND, TopAbs_COMPSOLID)


def _read_brep(path: Path, builder_type, brep_tools):
    from OCP.TopoDS import TopoDS_Shape

    shape = TopoDS_Shape()
    builder = builder_type()
    if not brep_tools.Read_s(shape, str(path), builder):
        raise ValueError("OpenCascade could not read the BREP file.")
    return shape


def _shape_facts(shape, source_format, analyzer_type, explorer_type, *shape_types) -> dict[str, object]:
    solid, shell, face, edge, vertex, compound, compsolid = shape_types
    counts = {
        "solids": _count(shape, explorer_type, solid),
        "shells": _count(shape, explorer_type, shell),
        "faces": _count(shape, explorer_type, face),
        "edges": _count(shape, explorer_type, edge),
        "vertices": _count(shape, explorer_type, vertex),
    }
    analyzer = analyzer_type(shape)
    from cad_defeature.connectivity import analyze_connectivity
    from cad_defeature.sewing import diagnose_sewing
    from cad_defeature.solid import diagnose_solid_construction

    return {
        "status": "kernel_inspected",
        "source_format": source_format,
        "shape_is_null": shape.IsNull(),
        "shape_is_valid": analyzer.IsValid(),
        "shape_kind": _shape_kind(shape.ShapeType(), solid, compound, compsolid),
        "topology": counts,
        "connectivity": analyze_connectivity(shape),
        "sewing": diagnose_sewing(shape),
        "solid_construction": diagnose_solid_construction(shape),
    }


def _count(shape, explorer_type, shape_type) -> int:
    explorer = explorer_type(shape, shape_type)
    count = 0
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def _shape_kind(shape_type, solid, compound, compsolid) -> str:
    if shape_type == solid:
        return "solid"
    if shape_type == compound:
        return "compound"
    if shape_type == compsolid:
        return "compsolid"
    return "other"
