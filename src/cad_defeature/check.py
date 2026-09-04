"""Actionable OpenCascade validity diagnostics.

BRepCheck_Analyzer only answers "valid or not". These helpers report *which*
sub-shapes fail so healing and agent decisions can be evidence-based.
"""
from __future__ import annotations


def analyze_validity(shape, max_examples: int = 10) -> dict[str, object]:
    """Return overall validity plus counts and examples of invalid sub-shapes."""
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    analyzer = BRepCheck_Analyzer(shape)
    result: dict[str, object] = {
        "overall_valid": analyzer.IsValid(),
        "invalid_counts": {},
        "invalid_examples": {},
    }
    for label, shape_type in (
        ("solids", TopAbs_SOLID),
        ("shells", TopAbs_SHELL),
        ("faces", TopAbs_FACE),
        ("edges", TopAbs_EDGE),
    ):
        invalid_indices = []
        explorer = TopExp_Explorer(shape, shape_type)
        index = 0
        while explorer.More():
            if not analyzer.IsValid(explorer.Current()):
                invalid_indices.append(index)
            index += 1
            explorer.Next()
        result["invalid_counts"][label] = len(invalid_indices)
        result["invalid_examples"][label] = invalid_indices[:max_examples]
    return result
