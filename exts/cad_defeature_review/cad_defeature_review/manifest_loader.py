"""Read a generated CAD-defeature highlight manifest."""

from __future__ import annotations

import json
from pathlib import Path


class ManifestLoader:
    """Load and validate viewer-neutral face-highlight manifests."""

    REQUIRED = {"manifest_type", "model_path", "summary", "highlights"}

    def load(self, path: str) -> dict:
        manifest_path = Path(path)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        missing = self.REQUIRED - data.keys()
        if missing:
            raise ValueError(f"Manifest missing required fields: {', '.join(sorted(missing))}")
        if data["manifest_type"] != "cad_defeature_face_highlights":
            raise ValueError("Unsupported manifest type.")
        data["_manifest_path"] = str(manifest_path)
        return data
