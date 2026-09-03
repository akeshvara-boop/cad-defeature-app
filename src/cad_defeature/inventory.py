"""Read-only geometric feature inventory for Power Tools policy proposals."""

from __future__ import annotations


def inventory_features(shape, policy: dict[str, object]) -> dict[str, object]:
    """Classify supported face surfaces without modifying or exporting CAD."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_SurfaceOfRevolution, GeomAbs_Torus
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
    from OCP.TopoDS import TopoDS

    adjacency = _face_adjacency(shape, TopAbs_EDGE, TopAbs_FACE, TopExp, TopTools_IndexedDataMapOfShapeListOfShape)
    candidates, type_counts, unclassified = [], {}, []
    explorer, index = TopExp_Explorer(shape, TopAbs_FACE), 0
    while explorer.More():
        index += 1
        face = TopoDS.Face_s(explorer.Current())
        adaptor = BRepAdaptor_Surface(face)
        surface_type = adaptor.GetType()
        type_counts[str(surface_type)] = type_counts.get(str(surface_type), 0) + 1
        candidate = None
        if surface_type == GeomAbs_Cylinder:
            candidate = _candidate(index, "cylindrical_surface", "through_hole", adaptor.Cylinder().Radius(), policy, face, Bnd_Box, BRepBndLib)
        elif surface_type == GeomAbs_Cone:
            candidate = _candidate(index, "conical_surface", "chamfer", adaptor.Cone().RefRadius(), policy, face, Bnd_Box, BRepBndLib)
        elif surface_type == GeomAbs_Torus:
            candidate = _candidate(index, "toroidal_surface", "external_fillet", adaptor.Torus().MinorRadius(), policy, face, Bnd_Box, BRepBndLib)
        elif surface_type == GeomAbs_SurfaceOfRevolution:
            fact = _revolution_fact(index, face, adaptor, Bnd_Box, BRepBndLib)
            if fact["basis_curve_base_type"] == "Geom_Circle" and fact["basis_curve_radius"] is not None:
                candidate = _candidate(index, "revolution_of_circle", "external_fillet", fact["basis_curve_radius"], policy, face, Bnd_Box, BRepBndLib, fact)
            elif fact["basis_curve_base_type"] == "Geom_Line":
                candidate = _line_revolution_candidate(index, face, fact, adjacency[index], policy, Bnd_Box, BRepBndLib)
                if candidate is None:
                    unclassified.append(fact)
            else:
                fact["adjacent_face_count"] = adjacency[index]
                fact["topology_classification"] = "unclassified"
                unclassified.append(fact)
        if candidate:
            candidates.append(candidate)
        explorer.Next()

    eligible = [item for item in candidates if item["policy_eligible"]]
    return {
        "performed_read_only": True,
        "policy_name": policy["policy"]["name"],
        "policy_version": policy["policy"]["version"],
        "face_surface_type_counts": type_counts,
        "candidate_count": len(candidates),
        "eligible_candidate_count": len(eligible),
        "unclassified_revolution_count": len(unclassified),
        "unclassified_revolutions": unclassified,
        "candidates": candidates,
    }


def _face_adjacency(shape, edge_type, face_type, top_exp, map_type):
    """Build local adjacency from OpenCascade's native edge→ancestor-face map."""
    ancestor_map = map_type()
    top_exp.MapShapesAndAncestors_s(shape, edge_type, face_type, ancestor_map)
    faces = []
    explorer = __import__("OCP.TopExp", fromlist=["TopExp_Explorer"]).TopExp_Explorer(shape, face_type)
    while explorer.More():
        faces.append(explorer.Current())
        explorer.Next()
    face_indices = {hash(face): index for index, face in enumerate(faces, start=1)}
    neighbours = {index: set() for index in range(1, len(faces) + 1)}
    for edge_index in range(1, ancestor_map.Extent() + 1):
        owners = [face_indices[hash(owner)] for owner in ancestor_map.FindFromIndex(edge_index) if hash(owner) in face_indices]
        for owner in owners:
            neighbours[owner].update(set(owners) - {owner})
    return {index: len(owner_neighbours) for index, owner_neighbours in neighbours.items()}


def _revolution_fact(index, face, adaptor, box_type, bndlib):
    surface = adaptor.Surface().Surface()
    curve = _unwrap_trimmed_curve(surface.BasisCurve())
    axis = surface.Axis().Direction()
    return {
        "face_index": index,
        "basis_curve_base_type": curve.DynamicType().Name(),
        "basis_curve_radius": curve.Radius() if hasattr(curve, "Radius") else None,
        "axis_direction": {"x": axis.X(), "y": axis.Y(), "z": axis.Z()},
        "face_bounding_box": _bounding_box(face, box_type, bndlib),
        "note": "Unclassified revolution requires topology-aware confirmation before any operation.",
    }


def _unwrap_trimmed_curve(curve):
    while hasattr(curve, "BasisCurve"):
        next_curve = curve.BasisCurve()
        if next_curve.DynamicType().Name() == curve.DynamicType().Name():
            break
        curve = next_curve
    return curve


def _line_revolution_candidate(index, face, fact, adjacent_face_count, policy, box_type, bndlib):
    box, axis = fact["face_bounding_box"], fact["axis_direction"]
    radial_span = max(box["xmax"] - box["xmin"], box["ymax"] - box["ymin"]) / 2
    axial_span = box["zmax"] - box["zmin"]
    fact.update({"adjacent_face_count": adjacent_face_count, "estimated_radius": radial_span, "axial_span": axial_span})
    # Do not promote an incomplete topology result to a removable candidate.
    fact["topology_classification"] = "topology_map_pending_face_owner_extraction"
    return None


def _candidate(index, surface_kind, feature_class, radius, policy, face, box_type, bndlib, extra=None):
    rule = policy["candidate_feature_classes"][feature_class]
    dimension_name = "diameter" if feature_class == "through_hole" else "radius_or_size"
    value = radius * 2 if feature_class == "through_hole" else radius
    maximum = rule.get("max_diameter", rule.get("max_radius", rule.get("max_size")))
    enabled = bool(rule.get("enabled"))
    result = {
        "candidate_id": f"face-{index:04d}", "face_index": index, "surface_kind": surface_kind,
        "proposed_feature_class": feature_class, "dimensions": {dimension_name: value, "surface_radius": radius},
        "face_bounding_box": _bounding_box(face, box_type, bndlib),
        "policy_eligible": enabled and maximum is not None and value <= maximum,
        "approval_required": bool(rule.get("approval_required", True)), "confidence": "surface_only",
        "eligibility_reason": f"enabled={enabled}, {dimension_name}={value:.6g}, limit={maximum}",
        "note": "Classification is a proposal; topology-aware confirmation is required before removal.",
    }
    if extra:
        result["revolution_analysis"] = extra
    return result


def _bounding_box(shape, box_type, bndlib):
    box = box_type()
    bndlib.Add_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return {"xmin": xmin, "ymin": ymin, "zmin": zmin, "xmax": xmax, "ymax": ymax, "zmax": zmax}
