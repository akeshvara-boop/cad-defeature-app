"""Command-line interface for CAD defeaturing."""

from __future__ import annotations

import argparse
import json

from pathlib import Path

from cad_defeature.audit import build_baseline_report
from cad_defeature.inspect import inspect_model
from cad_defeature.inventory import inventory_features
from cad_defeature.model import read_defeaturing_solid
from cad_defeature.policy import load_policy, policy_summary


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(prog="cad-defeature")
    subcommands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subcommands.add_parser(
        "inspect", help="Record read-only baseline metadata for a CAD input."
    )
    inspect_parser.add_argument(
        "input", help="Path to a STEP/STP/BREP/BRP/IGES/IGS file."
    )

    baseline_parser = subcommands.add_parser(
        "baseline", help="Create a read-only JSON baseline audit report."
    )
    baseline_parser.add_argument(
        "input", help="Path to a STEP/STP/BREP/BRP/IGES/IGS file."
    )
    baseline_parser.add_argument(
        "--output", required=True, help="New JSON report path; existing files are never overwritten."
    )

    policy_parser = subcommands.add_parser(
        "policy", help="Validate and display a defeaturing delta policy."
    )
    policy_parser.add_argument("input", help="Path to the Power Tools delta policy YAML file.")

    inventory_parser = subcommands.add_parser(
        "inventory", help="Create a read-only analytic-surface feature inventory."
    )
    inventory_parser.add_argument("input", help="Path to a supported CAD input file.")
    inventory_parser.add_argument("--policy", required=True, help="Path to the Power Tools delta policy YAML file.")
    inventory_parser.add_argument("--output", help="Optional new JSON output path; existing files are never overwritten.")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    if args.command == "inspect":
        print(json.dumps(inspect_model(args.input), indent=2, sort_keys=True))
    elif args.command == "baseline":
        output = Path(args.output)
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite existing baseline report: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        report = build_baseline_report(args.input, inspect_model(args.input))
        output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({"status": "baseline_written", "report_path": str(output)}, indent=2))
    elif args.command == "policy":
        print(json.dumps(policy_summary(load_policy(args.input)), indent=2, sort_keys=True))
    elif args.command == "inventory":
        report = inventory_features(read_defeaturing_solid(args.input), load_policy(args.policy))
        if args.output:
            output = Path(args.output)
            if output.exists():
                raise FileExistsError(f"Refusing to overwrite existing inventory report: {output}")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
