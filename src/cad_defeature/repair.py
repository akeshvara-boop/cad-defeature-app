"""Targeted OpenCascade ShapeFix repair for locally invalid geometry.

The repair is deliberately narrow: it corrects face/wire/shell defects that
OpenCascade itself reports as invalid.  It never deletes features, never fills
missing regions, and always reports before/after validity so a caller can
refuse the result.
"""
from __future__ import annotations

from cad_defeature.check import analyze_validity

# Escalating (precision, max_tolerance) pairs. Each step is still small relative
# to typical plate dimensions and every step used is recorded in the report.
DEFAULT_REPAIR_LADDER = (
    (0.001, 0.01),
    (0.001, 0.1),
    (0.01, 0.5),
    (0.05, 1.0),
)


def repair_shape(shape, ladder=DEFAULT_REPAIR_LADDER) -> dict[str, object]:
    """Run escalating ShapeFix passes and return the best shape plus an audit record."""
    from OCP.ShapeFix import ShapeFix_Shape

    before = analyze_validity(shape)
    passes: list[dict[str, object]] = []
    best_shape = shape
    best_result = before

    for precision, max_tolerance in ladder:
        fixer = ShapeFix_Shape(shape)
        fixer.SetPrecision(float(precision))
        fixer.SetMaxTolerance(float(max_tolerance))
        fixer.Perform()
        candidate = fixer.Shape()
        result = analyze_validity(candidate)
        passes.append(
            {
                "precision": precision,
                "max_tolerance": max_tolerance,
                "overall_valid": result["overall_valid"],
                "invalid_counts": result["invalid_counts"],
            }
        )
        if result["overall_valid"]:
            best_shape, best_result = candidate, result
            break
        if _score(result) < _score(best_result):
            best_shape, best_result = candidate, result

    return {
        "shape": best_shape,
        "record": {
            "operation": "shapefix_shape_ladder",
            "before": before,
            "after": best_result,
            "passes": passes,
            "repaired": bool(best_result["overall_valid"]) and not before["overall_valid"],
            "note": "ShapeFix corrects reported topological/tolerance defects only; no features were removed.",
        },
    }


def _score(result: dict[str, object]) -> tuple[int, int, int, int]:
    """Lower is better: fewer invalid faces first, then edges, shells, solids."""
    counts = result["invalid_counts"]
    return (counts["faces"], counts["edges"], counts["shells"], counts["solids"])
