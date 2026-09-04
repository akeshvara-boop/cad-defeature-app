"""Temporary browser-based VTK/Trame viewer for highlight-manifest validation."""

from __future__ import annotations

import json
from pathlib import Path


def load_manifest(path: str | Path) -> dict[str, object]:
    """Load and minimally validate a CAD defeature highlight manifest."""
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("manifest_type") != "cad_defeature_face_highlights":
        raise ValueError("Expected a cad_defeature_face_highlights manifest.")
    if not isinstance(manifest.get("highlights"), list):
        raise ValueError("Highlight manifest must contain a highlights array.")
    return manifest


def serve_review(mesh_path: str | Path, manifest_path: str | Path, port: int = 8080) -> None:
    """Serve interactive VTK geometry with manifest-controlled face colouring."""
    from trame.app import get_server
    from trame.ui.vuetify3 import SinglePageLayout
    from trame.widgets import html, vtk, vuetify3
    from vtkmodules.vtkFiltersCore import vtkThreshold
    from vtkmodules.vtkIOXML import vtkXMLPolyDataReader
    from vtkmodules.vtkRenderingCore import vtkActor, vtkDataSetMapper, vtkPolyDataMapper, vtkRenderer, vtkRenderWindow

    mesh = Path(mesh_path)
    manifest = load_manifest(manifest_path)
    if not mesh.is_file():
        raise FileNotFoundError(f"VTK review mesh was not found: {mesh}")

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
    base_actor.GetProperty().SetOpacity(0.22)
    renderer.AddActor(base_actor)

    actors = {}
    statuses = {item["status"] for item in manifest["highlights"]}
    for item in manifest["highlights"]:
        actor = _highlight_actor(dataset, item, vtkThreshold, vtkDataSetMapper, vtkActor)
        if actor:
            renderer.AddActor(actor)
            actors[item["highlight_id"]] = actor

    renderer.ResetCamera()
    server = get_server("cad_defeature_review")
    state, ctrl = server.state, server.controller
    state.trame__title = "CAD Defeature Review"
    state.visible_statuses = list(statuses)
    state.highlights = manifest["highlights"]
    state.selected_highlight = None

    @state.change("visible_statuses")
    def update_visibility(**_):
        selected = set(state.visible_statuses or [])
        for item in manifest["highlights"]:
            actor = actors.get(item["highlight_id"])
            if actor:
                actor.SetVisibility(item["status"] in selected)
        ctrl.view_update()

    @state.change("selected_highlight")
    def select_highlight(**_):
        for identifier, actor in actors.items():
            actor.GetProperty().SetLineWidth(4 if identifier == state.selected_highlight else 1)
        ctrl.view_update()

    with SinglePageLayout(server) as layout:
        layout.title.set_text("CAD Defeature Review")
        with layout.toolbar:
            vuetify3.VToolbarTitle("CAD Defeature Review — VTK prototype")
        with layout.content:
            with vuetify3.VContainer(fluid=True, classes="fill-height"):
                with vuetify3.VRow(classes="fill-height"):
                    with vuetify3.VCol(cols=8, classes="fill-height"):
                        view = vtk.VtkLocalView(render_window)
                        ctrl.view_update = view.update
                        view.reset_camera()
                    with vuetify3.VCol(cols=4):
                        html.P("Manifest-to-geometry proof: occ_face_index cell data matches inventory face_index.")
                        vuetify3.VChipGroup(v_model=("visible_statuses", []), multiple=True, column=True, children=[vuetify3.VChip(status, value=status) for status in sorted(statuses)])
                        html.H3("Highlights")
                        vuetify3.VList(items=("highlights",), item_title="label", item_value="highlight_id", v_model=("selected_highlight", None), selectable=True)
                        html.Pre("{{ JSON.stringify(highlights.find(x => x.highlight_id === selected_highlight), null, 2) }}")
    server.start(port=port, open_browser=False)


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
