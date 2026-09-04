"""Browser-based VTK/Trame viewer for validating CAD defeature findings."""
from __future__ import annotations

import json
from pathlib import Path

STATUS_COPY = {
    "eligible": "Green — proposed for defeaturing; approval is still required.",
    "review_required": "Amber — uncertain classification; retain until reviewed.",
    "policy_ineligible": "Red — detected but retained by the active policy.",
}


def load_manifest(path: str | Path) -> dict[str, object]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("manifest_type") != "cad_defeature_face_highlights":
        raise ValueError("Expected a cad_defeature_face_highlights manifest.")
    return manifest


def serve_review(mesh_path: str | Path, manifest_path: str | Path, port: int = 8080) -> None:
    """Show original CAD geometry and selectable defeature candidates."""
    from trame.app import get_server
    from trame.ui.vuetify3 import SinglePageLayout
    from trame.widgets import html, vtk, vuetify3
    from vtkmodules.vtkFiltersCore import vtkThreshold
    from vtkmodules.vtkIOXML import vtkXMLPolyDataReader
    from vtkmodules.vtkRenderingCore import vtkActor, vtkDataSetMapper, vtkPolyDataMapper, vtkRenderer, vtkRenderWindow

    mesh = Path(mesh_path)
    manifest = load_manifest(manifest_path)
    reader = vtkXMLPolyDataReader()
    reader.SetFileName(str(mesh))
    reader.Update()
    dataset = reader.GetOutput()
    if dataset.GetCellData().GetArray("occ_face_index") is None:
        raise ValueError("VTK review mesh does not contain occ_face_index cell data.")

    renderer = vtkRenderer()
    renderer.SetBackground(0.08, 0.09, 0.11)
    render_window = vtkRenderWindow()
    render_window.AddRenderer(renderer)
    base_mapper = vtkPolyDataMapper()
    base_mapper.SetInputData(dataset)
    base_actor = vtkActor()
    base_actor.SetMapper(base_mapper)
    base_actor.GetProperty().SetColor(0.68, 0.70, 0.74)
    base_actor.GetProperty().SetOpacity(0.85)
    renderer.AddActor(base_actor)

    highlights = manifest["highlights"]
    actors = {}
    for item in highlights:
        actor = _highlight_actor(dataset, item, vtkThreshold, vtkDataSetMapper, vtkActor)
        if actor:
            renderer.AddActor(actor)
            actors[item["highlight_id"]] = actor
    renderer.ResetCamera()
    render_window.Render()

    server = get_server("cad_defeature_review")
    state, ctrl = server.state, server.controller
    state.trame__title = "CAD Defeature Review"
    state.visible_statuses = ["eligible"]
    state.visible_highlights = []
    state.selected_highlight = None
    state.selected_name = "Select a finding to identify its matching face on the original CAD."

    def refresh() -> None:
        selected_statuses = set(state.visible_statuses or [])
        visible = []
        for item in highlights:
            is_visible = item["status"] in selected_statuses
            actor = actors.get(item["highlight_id"])
            if actor:
                actor.SetVisibility(is_visible)
            if is_visible:
                visible.append(item)
        state.visible_highlights = visible

    @state.change("visible_statuses")
    def update_visibility(**_):
        refresh()
        if hasattr(ctrl, "view_update"):
            ctrl.view_update()

    @state.change("selected_highlight")
    def select_highlight(**_):
        item = next((entry for entry in highlights if entry["highlight_id"] == state.selected_highlight), None)
        for identifier, actor in actors.items():
            actor.GetProperty().SetLineWidth(5 if identifier == state.selected_highlight else 1)
        if item:
            state.selected_name = f"Original CAD face {item['face_index']}: {item['label']}"
        else:
            state.selected_name = "Select a finding to identify its matching face on the original CAD."
        if hasattr(ctrl, "view_update"):
            ctrl.view_update()

    refresh()
    statuses = sorted({item["status"] for item in highlights})
    with SinglePageLayout(server) as layout:
        layout.title.set_text("CAD Defeature Review")
        with layout.toolbar:
            vuetify3.VToolbarTitle("CAD Defeature Review — original geometry and proposed changes")
        with layout.content:
            with vuetify3.VContainer(fluid=True, classes="fill-height"):
                with vuetify3.VRow(classes="fill-height"):
                    with vuetify3.VCol(cols=8, classes="fill-height"):
                        html.P("Original CAD mesh: grey. Highlight overlays: green = remove candidate; amber/red = retain or review.")
                        view = vtk.VtkLocalView(render_window)
                        ctrl.view_update = view.update
                        view.reset_camera()
                    with vuetify3.VCol(cols=4):
                        html.H3("Defeature filters")
                        vuetify3.VChipGroup(v_model=("visible_statuses", ["eligible"]), multiple=True, column=True, children=[vuetify3.VChip(f"{status}: {STATUS_COPY[status]}", value=status) for status in statuses])
                        html.H3("Select a CAD finding")
                        html.P("Only findings enabled by the filters are listed.")
                        vuetify3.VList(items=("visible_highlights",), item_title="label", item_value="highlight_id", v_model=("selected_highlight", None), selectable=True)
                        html.H3("Original CAD identification")
                        html.P("{{ selected_name }}")
    server.start(host="0.0.0.0", port=port, open_browser=False)


def _highlight_actor(dataset, item, vtk_threshold, vtk_mapper, vtk_actor):
    threshold = vtk_threshold()
    threshold.SetInputData(dataset)
    threshold.SetInputArrayToProcess(0, 0, 0, 1, "occ_face_index")
    threshold.SetLowerThreshold(item["face_index"])
    threshold.SetUpperThreshold(item["face_index"])
    threshold.SetThresholdFunction(vtk_threshold.THRESHOLD_BETWEEN)
    threshold.Update()
    if threshold.GetOutput().GetNumberOfCells() == 0:
        return None
    mapper = vtk_mapper()
    mapper.SetInputConnection(threshold.GetOutputPort())
    actor = vtk_actor()
    actor.SetMapper(mapper)
    red, green, blue = (int(item["color"][index:index + 2], 16) / 255 for index in (1, 3, 5))
    actor.GetProperty().SetColor(red, green, blue)
    actor.GetProperty().SetOpacity(item.get("opacity", 0.6))
    actor.GetProperty().SetEdgeVisibility(True)
    return actor
