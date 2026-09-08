"""Persistent, auditable workflow service for the Kit-CAE UI."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import threading
from typing import Any
from uuid import uuid4

from .runtime import NemoClawRunner


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowNotFound(KeyError):
    """Raised when a workflow id has no persisted state."""


class WorkflowStore:
    """JSON state store; geometry and engineering evidence stay in OpenShell."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(
            root or os.getenv("CAD_UI_STATE_DIR", "~/.cad-defeature-ui/workflows")
        ).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, state: dict[str, Any]) -> None:
        target = self._path(state["workflow_id"])
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(target)

    def load(self, workflow_id: str) -> dict[str, Any]:
        target = self._path(workflow_id)
        if not target.exists():
            raise WorkflowNotFound(workflow_id)
        return json.loads(target.read_text(encoding="utf-8"))

    def list(self) -> list[dict[str, Any]]:
        states = [json.loads(path.read_text(encoding="utf-8")) for path in self.root.glob("*.json")]
        return sorted(states, key=lambda item: item.get("updated_at", ""), reverse=True)

    def _path(self, workflow_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", workflow_id):
            raise ValueError("Workflow id must be the 12-character id issued by this service.")
        return self.root / f"{workflow_id}.json"


class WorkflowService:
    """Coordinate health, healing, review, analysis and verification steps."""

    def __init__(self, runner: NemoClawRunner | None = None, store: WorkflowStore | None = None) -> None:
        self.runner = runner or NemoClawRunner()
        self.store = store or WorkflowStore()
        self._lock = threading.RLock()

    def create(self, source_path: str) -> dict[str, Any]:
        with self._lock:
            workflow_id = uuid4().hex[:12]
            source = self.runner.validate_source(source_path)
            remote_source = self.runner.stage_source(source, workflow_id)
            state: dict[str, Any] = {
                "workflow_id": workflow_id,
                "created_at": _now(),
                "updated_at": _now(),
                "phase": "ingested",
                "status": "running",
                "host_source": str(source),
                "source_model": remote_source,
                "active_model": remote_source,
                "sandbox_run_root": f"/sandbox/ui/runs/{workflow_id}",
                "events": [],
                "cfd_mesh_handoff": {
                    "status": "not_implemented",
                    "message": (
                        "Current pipeline produces CAD health, healing, read-only feature analysis "
                        "and verification evidence. It does not yet produce a solver-quality CFD mesh."
                    ),
                },
            }
            self._record(state, "ingest", {"status": "complete", "source_model": remote_source})
            result = self.runner.invoke("health", ["--input", remote_source])
            state["health"] = result
            state["phase"] = "health_assessed"
            state["status"] = result.get("status", "unknown")
            self._record(state, "health", result)
            self.store.save(state)
            return deepcopy(state)

    def get(self, workflow_id: str) -> dict[str, Any]:
        return self.store.load(workflow_id)

    def list(self) -> list[dict[str, Any]]:
        return self.store.list()

    def heal(self, workflow_id: str, max_auto_tolerance: float = 0.001) -> dict[str, Any]:
        return self._execute(
            workflow_id,
            "heal",
            [
                "--input",
                self._source(workflow_id),
                "--run-dir",
                self._run_root(workflow_id),
                "--max-auto-tolerance",
                str(max_auto_tolerance),
            ],
            self._apply_healing,
        )

    def approve(
        self,
        workflow_id: str,
        tolerance: float,
        approved_by: str,
        note: str,
        max_auto_tolerance: float = 0.001,
    ) -> dict[str, Any]:
        state = self.store.load(workflow_id)
        request = state.get("tolerance_request") or {}
        proposed = request.get("proposed_tolerance")
        if state.get("phase") != "awaiting_tolerance_decision" or proposed is None:
            raise ValueError("This workflow has no pending tolerance decision to approve.")
        if abs(float(tolerance) - float(proposed)) > 1e-12:
            raise ValueError(
                f"Approval must match the requested tolerance of {proposed} mm; "
                "a larger value requires its own decision request."
            )
        return self._execute(
            workflow_id,
            "approve",
            [
                "--input",
                self._source(workflow_id),
                "--run-dir",
                self._run_root(workflow_id),
                "--tolerance",
                str(tolerance),
                "--approved-by",
                approved_by,
                "--note",
                note,
                "--max-auto-tolerance",
                str(max_auto_tolerance),
            ],
            self._apply_healing,
        )

    def reject(self, workflow_id: str, rejected_by: str, note: str) -> dict[str, Any]:
        state = self.store.load(workflow_id)
        if state.get("phase") != "awaiting_tolerance_decision":
            raise ValueError("This workflow has no pending tolerance decision to reject.")
        if not rejected_by.strip() or not note.strip():
            raise ValueError("Rejection requires an accountable engineer and note.")

        def apply(state: dict[str, Any], result: dict[str, Any]) -> None:
            state["phase"] = "tolerance_rejected"
            state["status"] = result.get("status", "rejected")
            state["tolerance_decision"] = result

        return self._execute(
            workflow_id,
            "reject",
            [
                "--input",
                self._source(workflow_id),
                "--run-dir",
                self._run_root(workflow_id),
                "--rejected-by",
                rejected_by,
                "--note",
                note,
            ],
            apply,
        )

    def analyze(self, workflow_id: str) -> dict[str, Any]:
        state = self.store.load(workflow_id)

        def apply(current: dict[str, Any], result: dict[str, Any]) -> None:
            current["analysis"] = result
            current["phase"] = "feature_analysis_complete"
            current["status"] = result.get("status", "unknown")
            run_dir = result.get("run_dir")
            artifacts = (result.get("report") or {}).get("artifacts") or {}
            if run_dir and artifacts.get("highlight_manifest"):
                manifest_path = str(PurePosixPath(run_dir) / artifacts["highlight_manifest"])
                current["highlight_manifest_path"] = manifest_path
                current["highlight_manifest"] = self.runner.read_json(manifest_path)

        return self._execute(
            workflow_id,
            "defeature",
            [
                "--input",
                state["active_model"],
                "--run-dir",
                state["sandbox_run_root"],
                "--policy",
                self.runner.policy_path,
            ],
            apply,
        )

    def verify(self, workflow_id: str) -> dict[str, Any]:
        state = self.store.load(workflow_id)
        arguments = [
            "--original",
            state["source_model"],
            "--candidate",
            state["active_model"],
            "--policy",
            self.runner.policy_path,
            "--run-dir",
            state["sandbox_run_root"],
        ]
        if state.get("healing_report_path"):
            arguments.extend(["--healing-report", state["healing_report_path"]])

        def apply(current: dict[str, Any], result: dict[str, Any]) -> None:
            current["verification"] = result
            current["phase"] = "verification_complete"
            current["status"] = result.get("status", "unknown")

        return self._execute(workflow_id, "verify", arguments, apply)

    def highlights(self, workflow_id: str) -> dict[str, Any]:
        state = self.store.load(workflow_id)
        manifest = state.get("highlight_manifest")
        if not manifest:
            raise ValueError("No highlight manifest exists. Run feature analysis first.")
        return manifest

    def _execute(self, workflow_id: str, action: str, arguments: list[str], apply) -> dict[str, Any]:
        with self._lock:
            state = self.store.load(workflow_id)
            result = self.runner.invoke(action, arguments)
            apply(state, result)
            self._record(state, action, result)
            self.store.save(state)
            return deepcopy(state)

    def _apply_healing(self, state: dict[str, Any], result: dict[str, Any]) -> None:
        state["healing"] = result
        state["status"] = result.get("status", "unknown")
        state["phase"] = (
            "awaiting_tolerance_decision"
            if result.get("status") == "needs_human_decision"
            else "healing_complete"
        )
        state["tolerance_request"] = result.get("request")
        run_dir = result.get("run_dir")
        report = result.get("report") or {}
        if run_dir:
            state["last_healing_run_dir"] = run_dir
            state["healing_report_path"] = str(PurePosixPath(run_dir) / "healing_report.json")
        if result.get("status") == "complete" and report.get("healed_model") and run_dir:
            state["active_model"] = str(PurePosixPath(run_dir) / report["healed_model"])

    def _source(self, workflow_id: str) -> str:
        return self.store.load(workflow_id)["source_model"]

    def _run_root(self, workflow_id: str) -> str:
        return self.store.load(workflow_id)["sandbox_run_root"]

    @staticmethod
    def _record(state: dict[str, Any], action: str, result: dict[str, Any]) -> None:
        state["updated_at"] = _now()
        state.setdefault("events", []).append(
            {
                "at": state["updated_at"],
                "action": action,
                "status": result.get("status", "unknown"),
                "run_dir": result.get("run_dir"),
            }
        )
