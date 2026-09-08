"""Interactive Kit-CAE workbench for the agentic CAD preparation workflow."""

from __future__ import annotations

import asyncio
import json

import omni.ext
import omni.ui as ui

from .api_client import WorkflowApiClient
from .highlight_controller import HighlightController
from .manifest_loader import ManifestLoader


NVIDIA_GREEN = 0xFF76B900
TEXT_MUTED = 0xFFAAAAAA
TEXT_WARNING = 0xFF4FB6FF


class CadDefeatureReviewExtension(omni.ext.IExt):
    """Dockable workflow controls plus manifest-driven USD review overlays."""

    def on_startup(self, ext_id):
        self._loader = ManifestLoader()
        self._controller = HighlightController()
        self._manifest = None
        self._workflow = None
        self._selected = None
        self._task = None

        self._api_url_model = ui.SimpleStringModel("http://127.0.0.1:8000")
        self._source_model = ui.SimpleStringModel("")
        self._workflow_id_model = ui.SimpleStringModel("")
        self._max_auto_model = ui.SimpleFloatModel(0.001)
        self._tolerance_model = ui.SimpleFloatModel(0.01)
        self._identity_model = ui.SimpleStringModel("")
        self._note_model = ui.SimpleStringModel("")
        self._path_model = ui.SimpleStringModel("")
        self._stage_path_model = ui.SimpleStringModel("")

        self._window = ui.Window("Agentic CAD-to-Mesh Workbench", width=560, height=900)
        with self._window.frame:
            self._build_ui()

    def on_shutdown(self):
        if self._task and not self._task.done():
            self._task.cancel()
        self._controller.clear()
        self._window = None

    def _build_ui(self):
        with ui.ScrollingFrame():
            with ui.VStack(spacing=10, height=0):
                ui.Label("AGENTIC CAD-TO-MESH", style={"font_size": 22, "color": NVIDIA_GREEN})
                ui.Label(
                    "NemoClaw orchestration · OpenShell execution · Kit-CAE review",
                    style={"color": TEXT_MUTED},
                )
                self._status = ui.Label("Ready. Connect to the host API to begin.", word_wrap=True)

                with ui.CollapsableFrame("1  CONNECT + INGEST", collapsed=False):
                    with ui.VStack(spacing=6, height=0):
                        ui.Label("Host API")
                        with ui.HStack(height=26):
                            ui.StringField(self._api_url_model)
                            ui.Button("Check", width=78, clicked_fn=self._check_api)
                        ui.Label("CAD path on Brev host (.step/.stp/.brep/.iges/.igs)")
                        ui.StringField(self._source_model, height=26)
                        ui.Button("Start workflow + health assessment", height=30, clicked_fn=self._start)
                        with ui.HStack(height=26):
                            ui.StringField(self._workflow_id_model)
                            ui.Button("Refresh", width=78, clicked_fn=self._refresh)

                with ui.CollapsableFrame("2  HEAL + HUMAN DECISION", collapsed=False):
                    with ui.VStack(spacing=6, height=0):
                        ui.Label("Automatic tolerance ceiling (mm)")
                        ui.FloatField(self._max_auto_model, height=25)
                        ui.Button("Run conservative healing", height=30, clicked_fn=self._heal)
                        self._decision = ui.Label("No tolerance decision requested.", word_wrap=True)
                        with ui.HStack(height=25):
                            ui.Label("Proposed / approved tolerance (mm)", width=250)
                            ui.FloatField(self._tolerance_model)
                        ui.Label("Accountable engineer")
                        ui.StringField(self._identity_model, height=25)
                        ui.Label("Engineering justification")
                        ui.StringField(self._note_model, multiline=True, height=54)
                        with ui.HStack(height=30):
                            ui.Button("Approve once", clicked_fn=self._approve)
                            ui.Button("Reject", clicked_fn=self._reject)

                with ui.CollapsableFrame("3  ANALYSE + VERIFY", collapsed=False):
                    with ui.VStack(spacing=6, height=0):
                        ui.Label(
                            "Feature analysis is report-only; it does not modify CAD geometry.",
                            style={"color": TEXT_MUTED},
                            word_wrap=True,
                        )
                        with ui.HStack(height=30):
                            ui.Button("Analyse features", clicked_fn=self._analyze)
                            ui.Button("Independent verify", clicked_fn=self._verify)
                        ui.Label(
                            "CFD mesh handoff: NOT IMPLEMENTED — no solver-quality volume mesh is produced.",
                            style={"color": TEXT_WARNING},
                            word_wrap=True,
                        )

                with ui.CollapsableFrame("4  KIT-CAE FINDINGS", collapsed=False):
                    with ui.VStack(spacing=6, height=0):
                        ui.Label(
                            "Open the matching CAD-derived USD/CAE model in Kit-CAE, then render findings.",
                            word_wrap=True,
                        )
                        with ui.HStack(height=26):
                            ui.StringField(self._stage_path_model)
                            ui.Button("Open USD", width=88, clicked_fn=self._open_stage)
                        ui.Button("Load findings from workflow", height=30, clicked_fn=self._load_workflow_manifest)
                        ui.Label("Or load a local highlight_manifest.json")
                        with ui.HStack(height=26):
                            ui.StringField(self._path_model)
                            ui.Button("Load", width=70, clicked_fn=self._load_manifest)
                        with ui.HStack(height=26):
                            ui.Button("Render overlays", clicked_fn=self._render)
                            ui.Button("Clear", clicked_fn=self._clear)
                            self._filter_combo = ui.ComboBox(
                                0, "all", "eligible", "review_required", "policy_ineligible"
                            )
                        self._summary = ui.Label("No manifest loaded.", word_wrap=True)
                        with ui.ScrollingFrame(height=240):
                            self._list = ui.VStack(spacing=4)
                        ui.Label("Selected finding")
                        self._details = ui.StringField(multiline=True, height=140, read_only=True)

                with ui.CollapsableFrame("AUDIT STATE", collapsed=True):
                    with ui.VStack(height=0):
                        self._workflow_details = ui.StringField(multiline=True, height=260, read_only=True)

    def _client(self):
        return WorkflowApiClient(self._api_url_model.get_value_as_string().strip())

    def _workflow_id(self):
        value = self._workflow_id_model.get_value_as_string().strip()
        if not value:
            raise ValueError("Start a workflow or enter a workflow id first.")
        return value

    def _check_api(self):
        self._dispatch("Checking host API…", self._client().health, self._show_result)

    def _start(self):
        source = self._source_model.get_value_as_string().strip()
        if not source:
            self._status.text = "Enter the CAD path on the Brev host."
            return
        self._dispatch("Staging CAD and running health assessment…", lambda: self._client().start(source))

    def _refresh(self):
        try:
            workflow_id = self._workflow_id()
        except ValueError as exc:
            self._status.text = str(exc)
            return
        self._dispatch("Refreshing workflow…", lambda: self._client().get(workflow_id))

    def _heal(self):
        self._workflow_action(
            "Running conservative healing…",
            lambda client, workflow_id: client.heal(workflow_id, self._max_auto_model.get_value_as_float()),
        )

    def _approve(self):
        identity = self._identity_model.get_value_as_string().strip()
        note = self._note_model.get_value_as_string().strip()
        if not identity or not note:
            self._status.text = "Approval requires an accountable engineer and justification."
            return
        self._workflow_action(
            "Applying this run-scoped human approval…",
            lambda client, workflow_id: client.approve(
                workflow_id,
                self._tolerance_model.get_value_as_float(),
                identity,
                note,
                self._max_auto_model.get_value_as_float(),
            ),
        )

    def _reject(self):
        identity = self._identity_model.get_value_as_string().strip()
        note = self._note_model.get_value_as_string().strip()
        if not identity or not note:
            self._status.text = "Rejection requires an accountable engineer and note."
            return
        self._workflow_action(
            "Recording tolerance rejection…",
            lambda client, workflow_id: client.reject(workflow_id, identity, note),
        )

    def _analyze(self):
        self._workflow_action(
            "Running report-only feature analysis…",
            lambda client, workflow_id: client.analyze(workflow_id),
        )

    def _verify(self):
        self._workflow_action(
            "Running independent verification…",
            lambda client, workflow_id: client.verify(workflow_id),
        )

    def _load_workflow_manifest(self):
        try:
            workflow_id = self._workflow_id()
        except ValueError as exc:
            self._status.text = str(exc)
            return
        self._dispatch(
            "Loading workflow findings…",
            lambda: self._client().highlights(workflow_id),
            self._apply_manifest,
        )

    def _open_stage(self):
        path = self._stage_path_model.get_value_as_string().strip()
        if not path.lower().endswith((".usd", ".usda", ".usdc")):
            self._status.text = "Enter a CAD-derived .usd, .usda or .usdc stage path."
            return
        try:
            import omni.usd

            opened = omni.usd.get_context().open_stage(path)
            self._status.text = (
                "USD stage opened in Kit-CAE."
                if opened is not False
                else "Kit-CAE could not open the USD stage."
            )
        except Exception as exc:
            self._status.text = f"USD open failed: {exc}"

    def _workflow_action(self, message, operation):
        try:
            workflow_id = self._workflow_id()
            client = self._client()
        except ValueError as exc:
            self._status.text = str(exc)
            return
        self._dispatch(message, lambda: operation(client, workflow_id))

    def _dispatch(self, message, operation, success=None):
        if self._task and not self._task.done():
            self._status.text = "A workflow operation is already running."
            return
        self._status.text = message
        self._task = asyncio.ensure_future(self._run_async(operation, success or self._apply_workflow))

    async def _run_async(self, operation, success):
        try:
            result = await asyncio.to_thread(operation)
            success(result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._status.text = f"Operation failed: {exc}"

    def _apply_workflow(self, state):
        self._workflow = state
        if state.get("workflow_id"):
            self._workflow_id_model.set_value(state["workflow_id"])
        phase = state.get("phase", "unknown")
        status = state.get("status", "unknown")
        self._status.text = f"{phase.replace('_', ' ').title()} · {status}"
        request = state.get("tolerance_request") or {}
        if request:
            proposed = request.get("proposed_tolerance")
            if isinstance(proposed, (int, float)):
                self._tolerance_model.set_value(float(proposed))
            self._decision.text = (
                (state.get("healing") or {}).get("question")
                or f"Human decision required for tolerance {proposed} mm."
            )
        else:
            self._decision.text = "No tolerance decision requested."
        self._workflow_details.model.set_value(json.dumps(state, indent=2))

    def _show_result(self, result):
        self._status.text = json.dumps(result, sort_keys=True)

    def _load_manifest(self):
        try:
            self._apply_manifest(self._loader.load(self._path_model.get_value_as_string()))
        except Exception as exc:
            self._summary.text = f"Load error: {exc}"

    def _apply_manifest(self, manifest):
        self._manifest = self._loader.validate(manifest)
        summary = self._manifest["summary"]
        self._summary.text = f"Loaded {summary['highlight_count']} findings: {summary['by_status']}"
        self._rebuild_list()
        self._status.text = "Findings loaded. Render them on the active Kit-CAE USD stage."

    def _render(self):
        if not self._manifest:
            self._summary.text = "Load a manifest first."
            return
        try:
            self._controller.clear()
            self._controller.render(self._filtered_highlights())
            self._summary.text = "Overlays rendered in the active Kit-CAE viewport."
        except Exception as exc:
            self._summary.text = f"Render error: {exc}"

    def _clear(self):
        self._controller.clear()
        self._summary.text = "Review overlays cleared."

    def _filter_status(self):
        return self._filter_combo.model.get_item_value_model().get_value_as_string()

    def _filtered_highlights(self):
        status = self._filter_status()
        highlights = self._manifest["highlights"]
        return highlights if status == "all" else [item for item in highlights if item["status"] == status]

    def _rebuild_list(self):
        self._list.clear()
        with self._list:
            for item in self._filtered_highlights():
                ui.Button(
                    f"{item['highlight_id']}  |  {item['status']}  |  {item['label']}",
                    height=25,
                    clicked_fn=lambda value=item: self._select(value),
                )

    def _select(self, item):
        self._selected = item
        self._controller.select(item["highlight_id"])
        self._details.model.set_value(json.dumps(item, indent=2))
