"""Baseline audit-report creation for CAD inspection results."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def build_baseline_report(input_path: str | Path, inspection: dict[str, object]) -> dict[str, object]:
    """Create a serialisable, read-only baseline report from inspection facts."""
    path = Path(input_path)
    stat = path.stat()
    return {
        "report_type": "cad_defeature_baseline",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "tool": {
            "name": "cad-defeature",
            "version": _package_version(),
        },
        "input": {
            "path": str(path),
            "filename": path.name,
            "source_format": inspection.get("source_format"),
            "size_bytes": stat.st_size,
            "sha256": _sha256(path),
        },
        "baseline": {
            "import": {
                "shape_kind": inspection.get("shape_kind"),
                "shape_is_valid": inspection.get("shape_is_valid"),
                "topology": inspection.get("topology"),
            },
            "connectivity": inspection.get("connectivity"),
            "sewing": inspection.get("sewing"),
            "solid": inspection.get("solid_construction"),
        },
    }


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_version() -> str:
    try:
        return version("cad-defeature")
    except PackageNotFoundError:
        return "development"
