"""Attach durable USD mesh-face bindings to review highlight manifests."""

from __future__ import annotations

import json
from pathlib import Path


def load_face_map(path: str | Path) -> dict[str, dict[str, object]]:
    """Load an importer-produced mapping of inventory face index to USD faces.

    Required input schema:
    {"schema_version":"1.0", "bindings":[
      {"face_index":64, "usd_prim_path":"/World/BasePlate/Mesh",
       "usd_face_indices":[12, 13]}
    ]}
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    bindings = data.get("bindings")
    if not isinstance(bindings, list):
        raise ValueError("USD face map must contain a bindings array.")
    result = {}
    for binding in bindings:
        required = {"face_index", "usd_prim_path", "usd_face_indices"}
        missing = required - binding.keys()
        if missing:
            raise ValueError(f"USD face binding missing: {', '.join(sorted(missing))}")
        result[str(binding["face_index"])] = binding
    return result


def attach_usd_bindings(manifest: dict[str, object], face_map: dict[str, dict[str, object]]) -> dict[str, object]:
    """Return a new manifest with exact USD bindings wherever supplied."""
    bound, fallback = 0, 0
    for highlight in manifest["highlights"]:
        binding = face_map.get(str(highlight["face_index"]))
        if binding:
            highlight["usd_binding"] = {
                "usd_prim_path": binding["usd_prim_path"],
                "usd_face_indices": binding["usd_face_indices"],
            }
            bound += 1
        else:
            fallback += 1
    manifest["usd_binding_summary"] = {
        "exact_face_bound": bound,
        "bounding_box_fallback": fallback,
        "binding_contract": "CAD importer must emit original inventory face_index to USD mesh-face indices.",
    }
    return manifest
