import json

from cad_defeature.agent import classify_health


def test_surface_geometry_routes_to_safe_review() -> None:
    result = classify_health({
        "status": "kernel_inspected",
        "shape_is_valid": True,
        "topology": {"solids": 0, "shells": 0},
    })
    assert result["route"] == "surface_safe_review"


def test_solid_geometry_can_proceed() -> None:
    result = classify_health({
        "status": "kernel_inspected",
        "shape_is_valid": True,
        "topology": {"solids": 1, "shells": 1},
    })
    assert result["route"] == "proceed"
