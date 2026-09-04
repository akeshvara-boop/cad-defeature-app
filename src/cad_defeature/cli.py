"""Command-line interface for CAD defeaturing."""

from __future__ import annotations

import argparse
import json

from pathlib import Path

from cad_defeature.agent import run_defeaturing_agent
from cad_defeature.audit import build_baseline_report
from cad_defeature.inspect import inspect_model
from cad_defeature.highlights import build_highlight_manifest, load_inventory
from cad_defeature.inventory import inventory_features
from cad_defeature.model import read_defeaturing_solid
from cad_defeature.policy import load_policy, policy_summary
from cad_defeature.usd_bindings import attach_usd_bindings, load_face_map
from cad_defeature.verification import verify_models
from cad_defeature.vtk_export import export_review_mesh
from cad_defeature.trame_review import serve_review


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

    highlights_parser = subcommands.add_parser(
        "highlights", help="Create a viewer-neutral face-highlight manifest from an inventory report."
    )
    highlights_parser.add_argument("--inventory", required=True, help="Path to an existing feature inventory JSON report.")
    highlights_parser.add_argument("--model", required=True, help="Original CAD model path recorded by the manifest.")
    highlights_parser.add_argument("--output", required=True, help="New JSON manifest path; existing files are never overwritten.")

    bind_parser = subcommands.add_parser(
        "bind-usd", help="Attach importer-provided USD mesh-face bindings to a highlight manifest."
    )
    bind_parser.add_argument("--manifest", required=True, help="Existing highlight manifest JSON path.")
    bind_parser.add_argument("--face-map", required=True, help="Importer-produced OpenCascade-face to USD-face mapping JSON path.")
    bind_parser.add_argument("--output", required=True, help="New bound manifest path; existing files are never overwritten.")

    verify_parser = subcommands.add_parser(
        "verify", help="Independently verify a defeatured CAD candidate without modifying either model."
    )
    verify_parser.add_argument("--original", required=True, help="Path to the original CAD model.")
    verify_parser.add_argument("--candidate", required=True, help="Path to the defeatured CAD candidate.")
    verify_parser.add_argument("--policy", required=True, help="Path to the Power Tools delta policy YAML file.")
    verify_parser.add_argument("--output", help="Optional new JSON verification report path; existing files are never overwritten.")

    vtk_parser = subcommands.add_parser(
        "export-vtk", help="Tessellate CAD into a VTK review mesh with stable OpenCascade face-index cell data."
    )
    vtk_parser.add_argument("input", help="Path to a STEP/STP/IGES/IGS CAD model.")
    vtk_parser.add_argument("--output", required=True, help="New .vtp review mesh path; existing files are never overwritten.")

    review_parser = subcommands.add_parser(
        "review-vtk", help="Serve the VTK/Trame highlight review application."
    )
    review_parser.add_argument("--mesh", required=True, help="Path to a .vtp mesh from export-vtk.")
    review_parser.add_argument("--manifest", required=True, help="Path to a highlight manifest from highlights or bind-usd.")
    review_parser.add_argument("--port", type=int, default=8080, help="Web server port (default: 8080).")

    agent_parser = subcommands.add_parser("agent", help="Run the CAD Defeaturing Agent in safe dry-run mode.")
    agent_parser.add_argument("input", help="Path to the original CAD model.")
    agent_parser.add_argument("--policy", required=True, help="Path to the Power Tools delta policy YAML file.")
    agent_parser.add_argument("--output-dir", required=True, help="New, empty directory for versioned agent artifacts.")
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
    elif args.command == "highlights":
        output = Path(args.output)
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite existing highlight manifest: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        manifest = build_highlight_manifest(load_inventory(args.inventory), args.model)
        output.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({"status": "highlight_manifest_written", "report_path": str(output), "summary": manifest["summary"]}, indent=2))
    elif args.command == "bind-usd":
        output = Path(args.output)
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite existing bound manifest: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        manifest = load_inventory(args.manifest)
        bound_manifest = attach_usd_bindings(manifest, load_face_map(args.face_map))
        output.write_text(json.dumps(bound_manifest, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({"status": "usd_bindings_attached", "report_path": str(output), "summary": bound_manifest["usd_binding_summary"]}, indent=2))
    elif args.command == "verify":
        report = verify_models(args.original, args.candidate, args.policy)
        if args.output:
            output = Path(args.output)
            if output.exists():
                raise FileExistsError(f"Refusing to overwrite existing verification report: {output}")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "export-vtk":
        print(json.dumps(export_review_mesh(args.input, args.output), indent=2, sort_keys=True))
    elif args.command == "review-vtk":
        serve_review(args.mesh, args.manifest, args.port)
    elif args.command == "agent":
        report = run_defeaturing_agent(args.input, args.policy, args.output_dir)
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
