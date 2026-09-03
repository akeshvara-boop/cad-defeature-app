"""Create read-only visualization manifests from feature inventory reports."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


COLOURS = {
    "eligible": "#22c55e",
    "review_required": "#f59e0b",
    "policy_ineligible": "#ef4444",
}


def build_highlight_manifest(inventory: dict[str, object], model_path: str | Path) -> dict[str, object]:
    """Convert candidates into viewer-neutral, face-index highlight records."""
    highlights = []
    for candidate in inventory.get("candidates", []):
        status = _status(candidate)
        highlights.append(_highlight(candidate, status))

    for revolution in inventory.get("unclassified_revolutions", []):
        highlights.append({
            "highlight_id": f"face-{revolution['face_index']:04d}",
            "face_index": revolution["face_index"],
            "color": COLOURS["review_required"],
            "opacity": 0.45,
            "status": "review_required",
            "label": "Unclassified surface of revolution — no operation proposed",
            "details": revolution,
        })

    counts = {key: 0 for key in COLOURS}
    for item in highlights:
        counts[item["status"]] += 1
    return {
        "manifest_type": "cad_defeature_face_highlights",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "model_path": str(model_path),
        "policy": {
            "name": inventory["policy_name"],
            "version": inventory["policy_version"],
        },
        "rendering": {
            "face_reference": "face_index_from_same_inventory_run",
            "default_opacity": 0.55,
            "legend": {
                "eligible": {"color": COLOURS["eligible"], "meaning": "Policy eligible; approval still required"},
                "review_required": {"color": COLOURS["review_required"], "meaning": "Unclassified or confidence insufficient"},
                "policy_ineligible": {"color": COLOURS["policy_ineligible"], "meaning": "Detected but disallowed by policy"},
            },
        },
        "summary": {"highlight_count": len(highlights), "by_status": counts},
        "highlights": highlights,
    }


def _status(candidate: dict[str, object]) -> str:
    if candidate["policy_eligible"]:
        return "eligible"
    return "policy_ineligible"


def _highlight(candidate: dict[str, object], status: str) -> dict[str, object]:
    feature = candidate["proposed_feature_class"].replace("_", " ")
    return {
        "highlight_id": candidate["candidate_id"],
        "face_index": candidate["face_index"],
        "color": COLOURS[status],
        "opacity": 0.65 if status == "policy_ineligible" else 0.55,
        "status": status,
        "label": f"Possible {feature} — {status.replace('_', ' ')}",
        "details": candidate,
    }


def load_inventory(path: str | Path) -> dict[str, object]:
    """Load an inventory report and minimally validate its intended schema."""
    import json

    report_path = Path(path)
    data = json.loads(report_path.read_text(encoding="utf-8"))
    required = {"policy_name", "policy_version", "candidates", "unclassified_revolutions"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Inventory report is missing: {', '.join(sorted(missing))}")
    return data
