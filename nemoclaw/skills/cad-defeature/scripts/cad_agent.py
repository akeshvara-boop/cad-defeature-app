#!/usr/bin/env python3
"""NemoClaw skill entrypoint for the cad-defeature pipeline.

Contract with the agent: every invocation prints exactly one JSON object on
stdout and exits 0 for a handled outcome, 1 for an error. The agent parses the
"status" field and never has to interpret free-form text or tracebacks.

Statuses:
    complete              - work finished, "report" holds the artifact
    needs_human_decision  - STOP; a human must rule on a tolerance concession
    rejected              - a human declined the concession (a valid outcome)
    error                 - "message" explains what went wrong

Safety note: this script deliberately exposes no way to lower a policy
threshold, and no way for a non-human identity to approve a tolerance. Those
guards live in cad_defeature.tolerance_gate and cad_defeature.verification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend import BackendUnavailable, diagnose, require_inprocess  # noqa: E402


def _emit(payload: dict, exit_code: int = 0) -> None:
    """Print one JSON object and exit. The only output path in this script."""
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    raise SystemExit(exit_code)


def _fail(message: str, **extra: object) -> None:
    _emit({"status": "error", "message": message, **extra}, exit_code=1)


def _fresh_run_dir(base: str, prefix: str) -> Path:
    """Run directories are immutable, so always allocate a new timestamped one."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    target = Path(base) / f"{prefix}-{stamp}"
    if target.exists():
        _fail(f"Run directory already exists, refusing to reuse it: {target}")
    return target


def _approval_pause_payload(run_dir: Path, request: dict) -> dict:
    """Preserve a higher-tolerance request as a handled workflow pause."""
    return {
        "status": "needs_human_decision",
        "run_dir": str(run_dir),
        "question": (
            "The approved tolerance was insufficient to produce a valid solid. "
            "Review the new request and make a separate human decision."
        ),
        "request": request,
        "respond_with": ["approve_tolerance", "reject_tolerance"],
        "agent_instruction": (
            "STOP. Do not reuse the prior approval or approve the higher tolerance "
            "on the user's behalf."
        ),
    }


def cmd_doctor(args: argparse.Namespace) -> None:
    """Report whether the skill can actually reach the CAD pipeline."""
    report = diagnose()
    _emit(
        {
            "status": "complete" if report["usable"] else "error",
            "message": (
                "Skill can reach the CAD pipeline."
                if report["usable"]
                else report["remedy"]
            ),
            "diagnosis": report,
        },
            exit_code=0 if report["usable"] else 1,
    )


def cmd_health(args: argparse.Namespace) -> None:
    require_inprocess()
    from cad_defeature.agent import classify_health
    from cad_defeature.inspect import inspect_model

    inspection = inspect_model(args.input)
    health = classify_health(inspection)
    if health.get("route") == "reject":
        _fail(
            str(health.get("reason", "CAD health inspection rejected the input.")),
            source_model=args.input,
            health=health,
            inspection=inspection,
        )
    _emit(
        {
            "status": "complete",
            "source_model": args.input,
            "health": health,
            "inspection": inspection,
        }
    )


def cmd_heal(args: argparse.Namespace) -> None:
    require_inprocess()
    from cad_defeature.nemoclaw_tools import heal_model

    run_dir = _fresh_run_dir(args.run_dir, "heal")
    result = heal_model(args.input, str(run_dir), max_auto_tolerance=args.max_auto_tolerance)
    if result.get("status") == "needs_human_decision":
        result["agent_instruction"] = (
            "STOP. Present the 'question' field to the user verbatim, including the "
            "risk statement. Wait for the user to approve or reject. Do not approve "
            "on their behalf and do not pass an agent identity as the approver."
        )
    _emit(result)


def cmd_approve(args: argparse.Namespace) -> None:
    require_inprocess()
    from cad_defeature.nemoclaw_tools import approve_tolerance
    from cad_defeature.tolerance_gate import ToleranceApprovalRequired

    run_dir = _fresh_run_dir(args.run_dir, "heal-approved")
    try:
        result = approve_tolerance(
            args.input,
            str(run_dir),
            approved_tolerance=args.tolerance,
            approved_by=args.approved_by,
            approval_note=args.note,
            max_auto_tolerance=args.max_auto_tolerance,
        )
    except ToleranceApprovalRequired as pause:
        result = _approval_pause_payload(run_dir, pause.request)
    _emit(result)


def cmd_reject(args: argparse.Namespace) -> None:
    require_inprocess()
    from cad_defeature.nemoclaw_tools import reject_tolerance

    run_dir = _fresh_run_dir(args.run_dir, "heal-rejected")
    run_dir.mkdir(parents=True, exist_ok=True)
    _emit(
        reject_tolerance(
            args.input,
            str(run_dir),
            rejected_by=args.rejected_by,
            rejection_note=args.note,
        )
    )


def cmd_defeature(args: argparse.Namespace) -> None:
    require_inprocess()
    from cad_defeature.agent import run_defeaturing_agent

    run_dir = _fresh_run_dir(args.run_dir, "agent")
    report = run_defeaturing_agent(args.input, args.policy, str(run_dir))
    _emit({"status": "complete", "run_dir": str(run_dir), "report": report})


def cmd_verify(args: argparse.Namespace) -> None:
    require_inprocess()
    from cad_defeature.verification import verify_models
    from cad_defeature.verification_artifacts import write_verification_package

    report = verify_models(
        args.original,
        args.candidate,
        args.policy,
        args.healing_report,
    )
    run_dir = None
    if args.run_dir:
        run_dir = _fresh_run_dir(args.run_dir, "verification")
        write_verification_package(report, run_dir)
    summary = report.get("summary", {})
    _emit(
        {
            "status": "complete",
            "verdict": summary.get("verdict"),
            "verdict_reason": summary.get("verdict_reason"),
            "blocking_checks": summary.get("blocking_checks"),
            "review_checks": summary.get("review_checks"),
            "reviewer_notice": report.get("reviewer_notice"),
            "run_dir": str(run_dir) if run_dir else None,
            "artifacts": report.get("artifacts"),
            "agent_instruction": (
                "Report verdict, verdict_reason, blocking_checks, review_checks and "
                "reviewer_notice to the user. Do not describe a needs_review or "
                "conditional_pass verdict as an unconditional pass."
            ),
            "report": report,
        }
    )


DEFAULT_POLICY = "/app/policies/power_tools_delta.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cad_agent", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser(
        "doctor", help="Check that the skill can reach the CAD pipeline. Run this first."
    )
    doctor.set_defaults(func=cmd_doctor)

    health = sub.add_parser("health", help="Classify CAD input health.")
    health.add_argument("--input", required=True)
    health.set_defaults(func=cmd_health)

    heal = sub.add_parser("heal", help="Heal a model to a valid solid.")
    heal.add_argument("--input", required=True)
    heal.add_argument("--run-dir", required=True, help="Parent directory; a timestamped subdirectory is created.")
    heal.add_argument("--max-auto-tolerance", type=float, default=0.001)
    heal.set_defaults(func=cmd_heal)

    approve = sub.add_parser("approve", help="Resume healing under a human tolerance approval.")
    approve.add_argument("--input", required=True)
    approve.add_argument("--run-dir", required=True)
    approve.add_argument("--tolerance", type=float, required=True)
    approve.add_argument("--approved-by", required=True, help="Named human. Agent identities are rejected.")
    approve.add_argument("--note", required=True, help="The human's engineering justification.")
    approve.add_argument("--max-auto-tolerance", type=float, default=0.001)
    approve.set_defaults(func=cmd_approve)

    reject = sub.add_parser("reject", help="Record a human rejection of the tolerance concession.")
    reject.add_argument("--input", required=True)
    reject.add_argument("--run-dir", required=True)
    reject.add_argument("--rejected-by", required=True)
    reject.add_argument("--note", required=True)
    reject.set_defaults(func=cmd_reject)

    defeature = sub.add_parser("defeature", help="Run the defeaturing agent.")
    defeature.add_argument("--input", required=True)
    defeature.add_argument("--run-dir", required=True)
    defeature.add_argument("--policy", default=DEFAULT_POLICY)
    defeature.set_defaults(func=cmd_defeature)

    verify = sub.add_parser("verify", help="Independently verify a candidate.")
    verify.add_argument("--original", required=True)
    verify.add_argument("--candidate", required=True)
    verify.add_argument("--policy", default=DEFAULT_POLICY)
    verify.add_argument("--healing-report", default=None)
    verify.add_argument("--run-dir", default=None, help="Parent directory for an immutable verification package.")
    verify.set_defaults(func=cmd_verify)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except SystemExit:
        raise
    except BackendUnavailable as exc:
        _fail(str(exc), diagnosis=diagnose())
    except ImportError as exc:
        _fail(
            "The cad_defeature package is not importable in this sandbox. "
            f"Install the pipeline before running this skill. Detail: {exc}"
        )
    except FileNotFoundError as exc:
        _fail(str(exc))
    except FileExistsError as exc:
        _fail(str(exc))
    except ValueError as exc:
        _fail(str(exc))
    except Exception as exc:  # noqa: BLE001 - the agent contract needs JSON, never a traceback
        _fail(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
