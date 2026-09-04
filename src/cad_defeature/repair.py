"""Targeted OpenCascade ShapeFix repair for locally invalid geometry.

The repair is deliberately narrow: it corrects face/wire/shell defects that
OpenCascade itself reports as invalid.  It never deletes features, never fills
missing regions, and always reports before/after validity so a caller can
refuse the result.
"""
from __future__ import annotations

from cad_defeature.check import analyze_validity

DEFAULT_PRECISION = 0.001
DEFAULT_MAX_TOLERANCE = 0.01


def repair_shape(shape, precision: float = DEFAULT_PRECISION, max_tolerance: float = DEFAULT_MAX_TOLERANCE) -> dict[str, object]:
    """Run ShapeFix on *shape* and return the fixed shape plus an audit record."""
    from OCP.ShapeFix import ShapeFix_Shape

    before = analyze_validity(shape)
    fixer = ShapeFix_Shape(shape)
    fixer.SetPrecision(float(precision))
    fixer.SetMaxTolerance(float(max_tolerance))
    fixer.Perform()
    fixed = fixer.Shape()
    after = analyze_validity(fixed)
    return {
        "shape": fixed,
        "record": {
            "operation": "shapefix_shape",
            "precision": precision,
            "max_tolerance": max_tolerance,
            "before": before,
            "after": after,
            "repaired": bool(after["overall_valid"]) and not before["overall_valid"],
            "note": "ShapeFix corrects reported topological/tolerance defects only; no features were removed.",
        },
    }
