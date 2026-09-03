"""Read-only baseline inspection for CAD input files.

This module intentionally performs no geometry changes.  It validates that an
input has a supported CAD interchange extension and records file-level facts
that remain useful before a geometry kernel is selected.
"""

from __future__ import annotations

from pathlib import Path

SUPPORTED_SUFFIXES = {".step", ".stp", ".brep", ".brp"}


def inspect_model(input_path: str | Path) -> dict[str, object]:
    """Return file-level baseline metadata for a CAD input file.

    The function does not parse or modify the model. Topology counts and BREP
    validation will be added after selecting an OpenCascade-compatible binding.
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
    if exists:
        result["size_bytes"] = path.stat().st_size
    return result
