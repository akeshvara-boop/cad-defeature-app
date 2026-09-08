import pytest

from cad_defeature.cli import build_parser


def test_verify_accepts_complete_package_output_dir() -> None:
    args = build_parser().parse_args(
        [
            "verify",
            "--original",
            "original.brep",
            "--candidate",
            "candidate.brep",
            "--policy",
            "policy.yaml",
            "--output-dir",
            "verification-run",
        ]
    )
    assert args.output_dir == "verification-run"
    assert args.output is None


def test_verify_rejects_two_output_modes() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "verify",
                "--original", "original.brep",
                "--candidate", "candidate.brep",
                "--policy", "policy.yaml",
                "--output", "report.json",
                "--output-dir", "verification-run",
            ]
        )
