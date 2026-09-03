"""Read-only geometric feature inventory for Power Tools policy proposals."""

from __future__ import annotations

from pathlib import Path


def inventory_features(shape, policy: dict[str, object]) -> dict[str, object]:
    """Classify analytic face surfaces and report policy eligibility.

    The inventory does not modify, heal, or export the CAD shape. A cylindrical
    surface is reported as a candidate only; determining hole versus boss is a
    later topology-aware planning step.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Torus
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    candidates = []
    surface_type_counts = {}
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_index = 0
    while explorer.More():
        face_index += 1
        face = TopoDS.Face_s(explorer.Current())
        adaptor = BRepAdaptor_Surface(face)
        surface_type = adaptor.GetType()
        surface_type_counts[str(surface_type)] = surface_type_counts.get(str(surface_type), 0) + 1
        candidate = _candidate_for_surface(
            face_index, face, adaptor, surface_type, policy,
            GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Torus, Bnd_Box, BRepBndLib,
        )
        if candidate is not None:
            candidates.append(candidate)
        explorer.Next()

    eligible = [item for item in candidates if item["policy_eligible"]]
    return {
        "performed_read_only": True,
        "policy_name": policy["policy"]["name"],
        "policy_version": policy["policy"]["version"],
        "face_surface_type_counts": surface_type_counts,
        "candidate_count": len(candidates),
        "eligible_candidate_count": len(eligible),
        "candidates": candidates,
    }


def _candidate_for_surface(index, face, adaptor, surface_type, policy, cylinder, cone, torus, box_type, bndlib):
    if surface_type == cylinder:
        radius = adaptor.Cylinder().Radius()
        return _candidate(index, "cylindrical_surface", "through_hole", radius, policy, face, box_type, bndlib)
    if surface_type == cone:
        radius = adaptor.Cone().RefRadius()
        return _candidate(index, "conical_surface", "chamfer", radius, policy, face, box_type, bndlib)
    if surface_type == torus:
        radius = adaptor.Torus().MinorRadius()
        return _candidate(index, "toroidal_surface", "external_fillet", radius, policy, face, box_type, bndlib)
    return None


def _candidate(index, surface_kind, feature_class, radius, policy, face, box_type, bndlib):
    rules = policy["candidate_feature_classes"]
    rule = rules[feature_class]
    dimension_name = "diameter" if feature_class == "through_hole" else "radius_or_size"
    value = radius * 2 if feature_class == "through_hole" else radius
    maximum = rule.get("max_diameter", rule.get("max_radius", rule.get("max_size")))
    enabled = bool(rule.get("enabled"))
    eligible = enabled and maximum is not None and value <= maximum
    return {
        "candidate_id": f"face-{index:04d}",
        "face_index": index,
        "surface_kind": surface_kind,
        "proposed_feature_class": feature_class,
        "dimensions": {dimension_name: value, "surface_radius": radius},
        "face_bounding_box": _bounding_box(face, box_type, bndlib),
        "policy_eligible": eligible,
        "approval_required": bool(rule.get("approval_required", True)),
        "eligibility_reason": (
            f"enabled and {dimension_name} {value:.6g} is within limit {maximum:.6g}"
            if eligible else f"not eligible: enabled={enabled}, {dimension_name}={value:.6g}, limit={maximum}"
        ),
        "confidence": "surface_only",
        "note": "Classification is a proposal; topology-aware hole/boss confirmation is required before removal.",
    }


def _bounding_box(shape, box_type, bndlib):
    box = box_type()
    bndlib.Add_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return {"xmin": xmin, "ymin": ymin, "zmin": zmin, "xmax": xmax, "ymax": ymax, "zmax": zmax}
