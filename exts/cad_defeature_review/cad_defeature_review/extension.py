"""Omniverse Kit extension entry point for CAD defeature review."""

from __future__ import annotations

import json

import omni.ext
import omni.ui as ui

from .highlight_controller import HighlightController
from .manifest_loader import ManifestLoader


class CadDefeatureReviewExtension(omni.ext.IExt):
    """Dockable manifest loader, overlay renderer, and candidate inspector."""

    def on_startup(self, ext_id):
        self._loader = ManifestLoader()
        self._controller = HighlightController()
        self._manifest = None
        self._selected = None
        self._path_model = ui.SimpleStringModel("")
        self._filter_model = ui.SimpleStringModel("all")
        self._window = ui.Window("CAD Defeature Review", width=500, height=680)
        with self._window.frame:
            self._build_ui()

    def on_shutdown(self):
        self._controller.clear()
        self._window = None

    def _build_ui(self):
        with ui.VStack(spacing=8, height=0):
            ui.Label("CAD Defeature Review", style={"font_size": 20})
            ui.Label("Load a generated highlight manifest after opening the corresponding CAD/USD model.", word_wrap=True)
            with ui.HStack(height=26):
                ui.StringField(self._path_model)
                ui.Button("Load", width=70, clicked_fn=self._load_manifest)
            with ui.HStack(height=26):
                ui.Button("Render overlays", clicked_fn=self._render)
                ui.Button("Clear", clicked_fn=self._clear)
                ui.ComboBox(0, "all", "eligible", "review_required", "policy_ineligible", model=self._filter_model)
            self._summary = ui.Label("No manifest loaded.", word_wrap=True)
            ui.Separator()
            with ui.ScrollingFrame(height=360):
                self._list = ui.VStack(spacing=4)
            ui.Separator()
            ui.Label("Candidate details")
            self._details = ui.StringField(multiline=True, height=170, read_only=True)

    def _load_manifest(self):
        try:
            self._manifest = self._loader.load(self._path_model.get_value_as_string())
            summary = self._manifest["summary"]
            self._summary.text = f"Loaded {summary['highlight_count']} highlights: {summary['by_status']}"
            self._rebuild_list()
        except Exception as exc:
            self._summary.text = f"Load error: {exc}"

    def _render(self):
        if not self._manifest:
            self._summary.text = "Load a manifest first."
            return
        try:
            self._controller.clear()
            self._controller.render(self._filtered_highlights())
            self._summary.text = "Overlays rendered. Select a list item to inspect its evidence."
        except Exception as exc:
            self._summary.text = f"Render error: {exc}"

    def _clear(self):
        self._controller.clear()
        self._summary.text = "Review overlays cleared."

    def _filtered_highlights(self):
        status = self._filter_model.get_value_as_string()
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
