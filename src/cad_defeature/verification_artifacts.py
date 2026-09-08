"""Immutable Phase 3 artifact package for independent CAD verification."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path


ARTIFACT_NAMES = {
    "verification_report": "verification_report.json",
    "verification_summary": "verification_summary.md",
    "geometry_comparison": "geometry_comparison.json",
    "residual_features": "residual_features.json",
    "final_decision": "final_decision.json",
}


def write_verification_package(
    report: dict[str, object], output_dir: str | Path
) -> dict[str, object]:
    """Write one complete verification package into a new or empty directory."""
    output = Path(output_dir)
    if output.exists() and not output.is_dir():
        raise FileExistsError(f"Verification output is not a directory: {output}")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            f"Refusing to write into a non-empty verification directory: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)

    packaged_report = deepcopy(report)
    packaged_report["artifacts"] = dict(ARTIFACT_NAMES)
    geometry = build_geometry_comparison(packaged_report)
    residual = build_residual_features(packaged_report)
    decision = build_final_decision(packaged_report)
    summary = render_verification_summary(packaged_report)

    _write_json(output / ARTIFACT_NAMES["verification_report"], packaged_report)
    _write_text(output / ARTIFACT_NAMES["verification_summary"], summary)
    _write_json(output / ARTIFACT_NAMES["geometry_comparison"], geometry)
    _write_json(output / ARTIFACT_NAMES["residual_features"], residual)
    _write_json(output / ARTIFACT_NAMES["final_decision"], decision)

    # Expose the package contract to callers without changing the verification
    # facts from which the files were derived.
    report["artifacts"] = dict(ARTIFACT_NAMES)
    return {
        "output_dir": str(output),
        "artifacts": {
            name: str(output / filename) for name, filename in ARTIFACT_NAMES.items()
        },
    }


def build_geometry_comparison(report: dict[str, object]) -> dict[str, object]:
    """Create a compact before/after topology and metric comparison."""
    original = report.get("original") or {}
    candidate = report.get("candidate") or {}
    original_inspection = original.get("inspection") or {}
    candidate_inspection = candidate.get("inspection") or {}
    original_topology = original_inspection.get("topology") or {}
    candidate_topology = candidate_inspection.get("topology") or {}
    keys = sorted(set(original_topology) | set(candidate_topology))
    topology_delta = {
        key: _numeric_delta(original_topology.get(key), candidate_topology.get(key))
        for key in keys
    }
    relevant_checks = {
        check.get("name"): check
        for check in report.get("checks", [])
        if check.get("name") in {
            "kernel_import",
            "valid_solid",
            "closed_shell",
            "non_manifold_edges",
            "bounding_box_delta",
            "volume_delta_percent",
            "min_feature_size",
        }
    }
    return {
        "report_type": "cad_defeature_geometry_comparison",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "performed_read_only": True,
        "original": {
            "path": original.get("path"),
            "sha256": original.get("sha256"),
            "topology": original_topology,
            "solid": original_inspection.get("solid_construction"),
        },
        "candidate": {
            "path": candidate.get("path"),
            "sha256": candidate.get("sha256"),
            "topology": candidate_topology,
            "solid": candidate_inspection.get("solid_construction"),
        },
        "topology_delta": topology_delta,
        "verification_checks": relevant_checks,
    }


def build_residual_features(report: dict[str, object]) -> dict[str, object]:
    """Extract the independent residual-feature result as a standalone artifact."""
    check = next(
        (item for item in report.get("checks", []) if item.get("name") == "residual_features"),
        None,
    )
    return {
        "report_type": "cad_defeature_residual_features",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "performed_read_only": True,
        "candidate": {
            "path": (report.get("candidate") or {}).get("path"),
            "sha256": (report.get("candidate") or {}).get("sha256"),
        },
        "assessment": check
        or {
            "name": "residual_features",
            "status": "not_assessed",
            "observed": None,
            "requirement": "The verification report did not contain a residual-feature check.",
        },
    }


def build_final_decision(report: dict[str, object]) -> dict[str, object]:
    """Create the machine-readable handoff decision for downstream agents."""
    summary = report.get("summary") or {}
    verdict = summary.get("verdict")
    return {
        "report_type": "cad_defeature_final_decision",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "verdict": verdict,
        "verdict_reason": summary.get("verdict_reason"),
        "blocking_checks": summary.get("blocking_checks", []),
        "review_checks": summary.get("review_checks", []),
        "ready_for_downstream": verdict == "pass",
        "engineering_authority": report.get("reviewer_notice") is None,
        "reviewer_notice": report.get("reviewer_notice"),
        "tolerance_provenance": report.get("tolerance_provenance"),
        "policy": report.get("policy"),
        "artifacts": report.get("artifacts", ARTIFACT_NAMES),
    }


def render_verification_summary(report: dict[str, object]) -> str:
    """Render a concise review document without hiding incomplete evidence."""
    summary = report.get("summary") or {}
    lines = [
        "# CAD Defeaturing Verification Summary",
        "",
        f"- Verdict: **{summary.get('verdict', 'unknown')}**",
        f"- Reason: {summary.get('verdict_reason', 'No reason recorded.')}",
        f"- Original: {(report.get('original') or {}).get('path')}",
        f"- Candidate: {(report.get('candidate') or {}).get('path')}",
        f"- Blocking checks: {_display(summary.get('blocking_checks'))}",
        f"- Review conditions: {_display(summary.get('review_checks'))}",
        "",
        "## Checks",
        "",
        "| Check | Status |",
        "|---|---|",
    ]
    lines.extend(
        f"| {check.get('name')} | {check.get('status')} |"
        for check in report.get("checks", [])
    )
    notice = report.get("reviewer_notice")
    if notice:
        lines.extend(["", "## Reviewer notice", "", str(notice)])
    return "\n".join(lines) + "\n"


def _numeric_delta(original: object, candidate: object) -> int | float | None:
    if isinstance(original, (int, float)) and isinstance(candidate, (int, float)):
        return candidate - original
    return None


def _display(items: object) -> str:
    if isinstance(items, list) and items:
        return ", ".join(str(item) for item in items)
    return "none"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_text(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite verification artifact: {path}")
    path.write_text(content, encoding="utf-8")
