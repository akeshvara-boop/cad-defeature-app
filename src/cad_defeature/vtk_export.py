"""OpenCascade-to-VTK review export with stable inventory face-index cell data."""

from __future__ import annotations

from pathlib import Path

from cad_defeature.model import read_shape


def export_review_mesh(input_path: str | Path, output_path: str | Path) -> dict[str, object]:
    """Tessellate CAD read-only and write a VTK PolyData review mesh.

    Every generated triangle receives an ``occ_face_index`` cell-data value. The
    index uses the same TopExp_Explorer face ordering as ``inventory_features``;
    it is therefore safe to join a highlight manifest generated from the same
    source model and inventory run.
    """
    from vtkmodules.vtkCommonCore import vtkIntArray, vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
    from vtkmodules.vtkIOXML import vtkXMLPolyDataWriter

    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location

    source = Path(input_path)
    target = Path(output_path)
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite existing VTK mesh: {target}")
    if not source.is_file():
        raise FileNotFoundError(f"CAD input was not found: {source}")

    shape = read_shape(source)
    # Deflection is relative to model units. It is deliberately conservative for
    # engineering review rather than downstream simulation meshing.
    BRepMesh_IncrementalMesh(shape, 0.1, False, 0.5, True).Perform()

    points = vtkPoints()
    polygons = vtkCellArray()
    face_ids = vtkIntArray()
    face_ids.SetName("occ_face_index")
    point_cache: dict[tuple[float, float, float], int] = {}
    face_count = triangle_count = 0

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face_count += 1
        face = TopoDS.Face(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        # OCP 7.8+ returns Poly_Triangulation directly; no IsNull() handle API.
        if triangulation is not None and triangulation.NbTriangles() > 0:
            transform = location.Transformation()
            nodes = triangulation.Nodes()
            triangles = triangulation.Triangles()
            for triangle_index in range(1, triangulation.NbTriangles() + 1):
                triangle = triangles.Value(triangle_index)
                node_indices = triangle.Get()
                polygons.InsertNextCell(3)
                for node_index in node_indices:
                    point = nodes.Value(node_index).Transformed(transform)
                    key = (round(point.X(), 12), round(point.Y(), 12), round(point.Z(), 12))
                    vtk_id = point_cache.get(key)
                    if vtk_id is None:
                        vtk_id = points.InsertNextPoint(point.X(), point.Y(), point.Z())
                        point_cache[key] = vtk_id
                    polygons.InsertCellPoint(vtk_id)
                face_ids.InsertNextValue(face_count)
                triangle_count += 1
        explorer.Next()

    polydata = vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetPolys(polygons)
    polydata.GetCellData().AddArray(face_ids)
    polydata.GetCellData().SetScalars(face_ids)
    target.parent.mkdir(parents=True, exist_ok=True)
    writer = vtkXMLPolyDataWriter()
    writer.SetFileName(str(target))
    writer.SetInputData(polydata)
    if writer.Write() != 1:
        raise RuntimeError(f"VTK could not write review mesh: {target}")

    return {
        "status": "vtk_review_mesh_written",
        "input_path": str(source),
        "output_path": str(target),
        "face_index_contract": "occ_face_index matches inventory face_index for the same source model.",
        "faces_seen": face_count,
        "triangles_written": triangle_count,
        "points_written": points.GetNumberOfPoints(),
    }
