"""Read and validate the version-controlled defeaturing delta policy."""

from __future__ import annotations

import json
from pathlib import Path


REQUIRED_SECTIONS = {
    "policy",
    "input_requirements",
    "protected_geometry",
    "candidate_feature_classes",
    "verification_gates",
    "audit_requirements",
}


def load_policy(path: str | Path) -> dict[str, object]:
    """Load a JSON-compatible YAML policy without adding a YAML dependency.

    The repository policy uses YAML syntax. If PyYAML is installed it is used;
    otherwise callers receive an actionable dependency error.
    """
    policy_path = Path(path)
    if not policy_path.is_file():
        raise FileNotFoundError(f"Policy file was not found: {policy_path}")
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("Policy loading requires PyYAML. Install it with: python -m pip install pyyaml") from exc

    data = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Policy root must be a mapping.")
    missing = REQUIRED_SECTIONS - data.keys()
    if missing:
        raise ValueError(f"Policy is missing required sections: {', '.join(sorted(missing))}")
    if data["policy"].get("mode") != "report_only":
        raise ValueError("Only report_only policy mode is supported at this stage.")
    return data


def policy_summary(policy: dict[str, object]) -> dict[str, object]:
    """Return a concise, serialisable summary for auditing and CLI output."""
    metadata = policy["policy"]
    candidates = policy["candidate_feature_classes"]
    enabled = sorted(name for name, rule in candidates.items() if rule.get("enabled"))
    return {
        "name": metadata["name"],
        "version": metadata["version"],
        "mode": metadata["mode"],
        "enabled_candidate_feature_classes": enabled,
        "verification_gates": policy["verification_gates"],
    }
