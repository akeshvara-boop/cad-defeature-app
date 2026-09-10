"""Read-only CAD to visual-review USD worker; run outside the OVRTX process.

Requires OpenCascade (OCP). The tessellation is NOT a CFD volume mesh.
Units and asset status must be supplied explicitly; source files are never edited.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def stage_text(points, triangles, face_ids, meters_per_unit, up_axis):
    if not math.isfinite(meters_per_unit) or meters_per_unit <= 0:
        raise ValueError("meters-per-unit must be finite and positive")
    if up_axis not in ("Y", "Z"):
        raise ValueError("up-axis must be Y or Z")
    if not points or not triangles or len(triangles) != len(face_ids):
        raise ValueError("Nonempty triangles and matching CAD face IDs are required")
    if any(len(p) != 3 or not all(math.isfinite(x) for x in p) for p in points):
        raise ValueError("Nonfinite or malformed CAD coordinates")
    if any(len(t) != 3 or any(i < 0 or i >= len(points) for i in t) for t in triangles):
        raise ValueError("Invalid triangle indices")
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    center = [(a + b) / 2 for a, b in zip(lo, hi)]
    radius = math.sqrt(sum((b - a) ** 2 for a, b in zip(lo, hi))) / 2
    if radius <= 0:
        raise ValueError("CAD bounds are degenerate")
    # Fit bounding sphere inside vertical 20.25mm aperture at 35mm focal length.
    distance = 1.15 * radius / math.sin(math.atan(20.25 / 70))
    eye = (center[0], center[1], center[2] + distance)
    fmt = lambda p: '(' + ', '.join(format(x, '.12g') for x in p) + ')'
    near = max(radius * 0.001, 1e-8)
    far = distance + radius * 4
    return f'''#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = {meters_per_unit:.12g}
    upAxis = "{up_axis}"
)
def Xform "World" {{
    def Mesh "CAD" {{
        uniform token subdivisionScheme = "none"
        uniform token orientation = "rightHanded"
        bool doubleSided = true
        point3f[] points = [{', '.join(fmt(p) for p in points)}]
        int[] faceVertexCounts = [{', '.join('3' for _ in triangles)}]
        int[] faceVertexIndices = [{', '.join(str(i) for t in triangles for i in t)}]
        int[] primvars:occ_face_index = [{', '.join(map(str, face_ids))}] (
            interpolation = "uniform"
        )
        float3[] extent = [{fmt(lo)}, {fmt(hi)}]
        color3f[] primvars:displayColor = [(0.55, 0.65, 0.7)]
    }}
    def DomeLight "ViewerLight" {{
        float inputs:intensity = 1000
    }}
    def Camera "Camera" {{
        float focalLength = 35
        float horizontalAperture = 36
        float verticalAperture = 20.25
        float2 clippingRange = ({near:.12g}, {far:.12g})
        double3 xformOp:translate = {fmt(eye)}
        uniform token[] xformOpOrder = ["xformOp:translate"]
    }}
}}
def Scope "Render" {{
    def RenderProduct "Camera" {{
        rel camera = </World/Camera>
        uniform int2 resolution = (1280, 720)
        rel orderedVars = [</Render/LdrColor>]
    }}
    def RenderVar "LdrColor" {{
        uniform string sourceName = "LdrColor"
    }}
    def RenderSettings "Settings" {{
        rel products = [</Render/Camera>]
    }}
}}
'''


def tessellate(source, deflection):
    from cad_defeature.model import read_shape
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location
    shape = read_shape(source)
    mesh = BRepMesh_IncrementalMesh(shape, deflection, False, 0.5, True)
    mesh.Perform()
    if not mesh.IsDone():
        raise RuntimeError("CAD tessellation did not complete")
    points, triangles, ids, missing = [], [], [], []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_id = 0
    while explorer.More():
        face_id += 1
        face = TopoDS.Face(explorer.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None or tri.NbTriangles() == 0:
            missing.append(face_id)
        else:
            offset = len(points)
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i).Transformed(loc.Transformation())
                points.append((p.X(), p.Y(), p.Z()))
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = (offset + n - 1 for n in tri.Triangle(i).Get())
                if face.Orientation() == TopAbs_REVERSED:
                    b, c = c, b
                triangles.append((a, b, c))
                ids.append(face_id)
        explorer.Next()
    if missing:
        raise RuntimeError(f"Incomplete visual asset: faces without triangles: {missing}")
    return points, triangles, ids


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True, help='Must not exist')
    p.add_argument('--meters-per-unit', type=float, required=True)
    p.add_argument('--up-axis', choices=['Y', 'Z'], required=True)
    p.add_argument('--deflection', type=float, default=0.1, help='Visual tessellation tolerance in source units')
    args = p.parse_args()
    if not args.input.is_file():
        p.error('CAD input does not exist')
    if args.output_dir.exists():
        p.error('Refusing to overwrite an existing output directory')
    if not all(math.isfinite(v) and v > 0 for v in (args.deflection, args.meters_per_unit)):
        p.error('Deflection and meters-per-unit must be finite and positive')
    before = hashlib.sha256(args.input.read_bytes()).hexdigest()
    points, triangles, ids = tessellate(args.input, args.deflection)
    usd = stage_text(points, triangles, ids, args.meters_per_unit, args.up_axis)
    if hashlib.sha256(args.input.read_bytes()).hexdigest() != before:
        raise RuntimeError('Source changed during preparation; output rejected')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / 'review.usda').open('x', encoding='utf-8', newline='\n') as f:
        f.write(usd)
    manifest = dict(schema_version='1.0', status='prepared_not_render_verified',
                    asset_role='unverified_review_candidate', source_name=args.input.name,
                    source_sha256=before, stage='review.usda',
                    stage_sha256=hashlib.sha256(usd.encode()).hexdigest(),
                    meters_per_unit=args.meters_per_unit, up_axis=args.up_axis,
                    deflection=args.deflection, triangles=len(triangles),
                    cad_faces=len(set(ids)), source_modified=False, cfd_ready=False,
                    note='Visual tessellation only. No claim of successful defeaturing or CAD validity.')
    with (args.output_dir / 'review-manifest.json').open('x', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
