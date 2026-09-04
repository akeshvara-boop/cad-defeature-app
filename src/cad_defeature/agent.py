"""Conservative CAD Defeaturing Agent orchestration and artifact contracts.

This first agent implementation is intentionally dry-run only.  The active
Power Tools delta policy is report_only, so it creates an auditable removal
plan but never modifies the source CAD artifact.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import json

from cad_defeature.highlights import build_highlight_manifest
from cad_defeature.inspect import inspect_model
from cad_defeature.inventory import inventory_features
from cad_defeature.model import read_defeaturing_solid
from cad_defeature.policy import load_policy, policy_summary


def classify_health(inspection: dict[str, object]) -> dict[str, object]:
    """Turn kernel facts into a safe processing route for the agent."""
    topology = inspection.get("topology", {})
    if inspection.get("status") != "kernel_inspected":
        return {
            "classification": "reject",
            "route": "reject",
            "reason": inspection.get("diagnostic", inspection.get("status", "input could not be inspected")),
        }
    if not inspection.get("shape_is_valid"):
        return {"classification": "invalid", "route": "heal", "reason": "OpenCascade validity check failed."}
    if topology.get("solids", 0) > 0:
        return {"classification": "closed_solid", "route": "proceed", "reason": "At least one solid was detected."}
    if topology.get("shells", 0) > 0:
        return {"classification": "open_or_sheet_shell", "route": "heal", "reason": "Shell geometry has no detected solid."}
    return {
        "classification": "surface_or_wire_geometry",
        "route": "surface_safe_review",
        "reason": "No closed solid was detected; do not perform solid defeaturing.",
    }


def run_defeaturing_agent(input_path: str | Path, policy_path: str | Path, output_dir: str | Path) -> dict[str, object]:
    """Run the policy-driven planning stage and write versioned agent artifacts."""
    source = Path(input_path)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to write into a non-empty agent output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)

    policy = load_policy(policy_path)
    inspection = inspect_model(source)
    health = classify_health(inspection)
    health_report = {
        "report_type": "input_cad_health_report",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_model": str(source),
        "inspection": inspection,
        "health": health,
    }
    _write(output / "input_cad_health_report.json", health_report)

    report: dict[str, object] = {
        "report_type": "defeaturing_agent_report",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "agent": {"name": "cad_defeaturing_agent", "mode": "dry_run"},
        "source_model": str(source),
        "policy": policy_summary(policy),
        "health_route": health,
        "removed_features": [],
        "retained_features": [],
        "warnings": [],
        "artifacts": {"input_health_report": "input_cad_health_report.json"},
    }
    removal_manifest = {
        "manifest_type": "cad_defeature_removal_manifest",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_model": str(source),
        "policy": policy_summary(policy),
        "mode": "dry_run",
        "operations": [],
    }

    if health["route"] != "proceed":
        report["decision"] = "needs_healing_or_surface_safe_review"
        report["warnings"].append(health["reason"])
        report["artifacts"]["removal_manifest"] = "removal_manifest.json"
    else:
        inventory = inventory_features(read_defeaturing_solid(source), policy)
        _write(output / "feature_inventory.json", inventory)
        highlights = build_highlight_manifest(inventory, source)
        _write(output / "highlight_manifest.json", highlights)
        for candidate in inventory.get("candidates", []):
            target = report["retained_features"]
            target.append({
                "candidate_id": candidate["candidate_id"],
                "face_index": candidate["face_index"],
                "feature_class": candidate["proposed_feature_class"],
                "reason": "Policy is report_only; no geometry changes are permitted.",
            })
        report["decision"] = "dry_run_complete"
        report["warnings"].append("No defeatured CAD was created because the policy mode is report_only.")
        report["artifacts"].update({
            "feature_inventory": "feature_inventory.json",
            "highlight_manifest": "highlight_manifest.json",
            "removal_manifest": "removal_manifest.json",
        })

    _write(output / "removal_manifest.json", removal_manifest)
    cad_check = {
        "report_type": "cad_check_after_defeaturing",
        "schema_version": "1.0",
        "mode": "dry_run",
        "validity": "not_applicable_no_geometry_change",
        "source_health_route": health,
    }
    _write(output / "cad_check_after_defeaturing.json", cad_check)
    report["artifacts"]["cad_check"] = "cad_check_after_defeaturing.json"
    _write(output / "defeaturing_report.json", report)
    return report


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
