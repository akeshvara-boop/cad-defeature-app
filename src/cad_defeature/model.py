"""Read and prepare CAD source files in memory without writing output."""

from __future__ import annotations

from pathlib import Path


def read_shape(input_path: str | Path):
    """Read a supported CAD file and return its OpenCascade import shape."""
    path = Path(input_path)
    suffix = path.suffix.lower()
    if suffix in {".igs", ".iges"}:
        from OCP.IGESControl import IGESControl_Reader

        reader = IGESControl_Reader()
        if reader.ReadFile(str(path)) != 1:
            raise ValueError(f"OpenCascade could not read IGES file: {path}")
        reader.TransferRoots()
        return reader.OneShape()
    if suffix in {".step", ".stp"}:
        from OCP.STEPControl import STEPControl_Reader

        reader = STEPControl_Reader()
        if reader.ReadFile(str(path)) != 1:
            raise ValueError(f"OpenCascade could not read STEP file: {path}")
        reader.TransferRoots()
        return reader.OneShape()
    raise ValueError(f"Feature inventory does not support format: {suffix}")


def read_defeaturing_solid(input_path: str | Path, tolerance: float = 0.001):
    """Read, sew, and construct a valid solid solely in memory for analysis."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    imported = read_shape(input_path)
    sewing = BRepBuilderAPI_Sewing(tolerance)
    faces = TopExp_Explorer(imported, TopAbs_FACE)
    while faces.More():
        sewing.Add(faces.Current())
        faces.Next()
    sewing.Perform()
    if sewing.NbFreeEdges() != 0:
        raise ValueError("Cannot inventory an open sewn shell.")
    shells = TopExp_Explorer(sewing.SewedShape(), TopAbs_SHELL)
    if not shells.More():
        raise ValueError("Sewing produced no shell for feature inventory.")
    solid = BRepBuilderAPI_MakeSolid(TopoDS.Shell(shells.Current())).Solid()
    if solid.IsNull() or not BRepCheck_Analyzer(solid).IsValid():
        raise ValueError("Sewn result could not be validated as a solid.")
    return solid
