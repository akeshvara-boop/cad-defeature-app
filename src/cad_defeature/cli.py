"""Command-line interface for CAD defeaturing."""

from __future__ import annotations

import argparse
import json

from cad_defeature.inspect import inspect_model


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
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    if args.command == "inspect":
        print(json.dumps(inspect_model(args.input), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
