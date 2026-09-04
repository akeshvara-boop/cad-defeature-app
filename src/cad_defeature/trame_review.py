"""Browser-based VTK/Trame viewer for validating CAD defeature findings."""

from __future__ import annotations

import json
from pathlib import Path


STATUS_COPY = {
    "eligible": "Green: proposed for defeaturing; human approval is still required.",
    "review_required": "Amber: uncertain classification; retain it until reviewed.",
    "policy_ineligible": "Red: detected, but the active policy says to retain it.",
}


def load_manifest(path: str | Path) -> dict[str, object]:
    """Load and minimally validate a CAD defeature highlight manifest."""
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("manifest_type") != "cad_defeature_face_highlights":
        raise ValueError("Expected a cad_defeature_face_highlights manifest.")
    if not isinstance(manifest.get("highlights"), list):
        raise ValueError("Highlight manifest must contain a highlights array.")
    return manifest


def serve_review(mesh_path: str | Path, manifest_path: str | Path, port: int = 8080) -> None:
    """Serve original geometry with selectable, named defeature findings."""
    from trame.app import get_server
    from trame.ui.vuetify3 import SinglePageLayout
    from trame.widgets import html, vtk, vuetify3
    from vtkmodules.vtkFiltersCore import vtkThreshold
    from vtkmodules.vtkIOXML import vtkXMLPolyDataReader
    from vtkmodules.vtkRenderingCore import (
        vtkActor,
        vtkBillboardTextActor3D,
        vtkDataSetMapper,
        vtkPolyDataMapper,
        vtkRenderer,
        vtkRenderWindow,
    )

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
    base_actor.GetProperty().SetOpacity(0.62)
    renderer.AddActor(base_actor)

    actors = {}
    highlights = manifest["highlights"]
    statuses = sorted({item["status"] for item in highlights})
    for item in highlights:
        actor = _highlight_actor(dataset, item, vtkThreshold, vtkDataSetMapper, vtkActor)
        if actor:
            renderer.AddActor(actor)
            actors[item["highlight_id"]] = actor

    label_actor = vtkBillboardTextActor3D()
    label_actor.GetTextProperty().SetColor(1.0, 1.0, 1.0)
    label_actor.GetTextProperty().SetFontSize(18)
    label_actor.GetTextProperty().SetBold(True)
    label_actor.SetVisibility(False)
    renderer.AddActor(label_actor)
    renderer.ResetCamera()

    server = get_server("cad_defeature_review")
    state, ctrl = server.state, server.controller
    state.trame__title = "CAD Defeature Review"
    state.visible_statuses = ["eligible"]
    state.highlights = highlights
    state.selected_highlight = None
    state.selected_details = "Select a finding to show its name directly on the original CAD geometry."
    state.status_guide = [
        {"status": status.replace("_", " "), "meaning": STATUS_COPY.get(status, "")}
        for status in statuses
    ]

    def apply_visibility() -> None:
        selected = set(state.visible_statuses or [])
        for item in highlights:
            actor = actors.get(item["highlight_id"])
            if actor:
                actor.SetVisibility(item["status"] in selected)

    @state.change("visible_statuses")
    def update_visibility(**_):
        apply_visibility()
        ctrl.view_update()

    @state.change("selected_highlight")
    def select_highlight(**_):
        selected_item = next(
            (item for item in highlights if item["highlight_id"] == state.selected_highlight),
            None,
        )
        for identifier, actor in actors.items():
            actor.GetProperty().SetLineWidth(5 if identifier == state.selected_highlight else 1)
        if selected_item:
            _set_label(label_actor, selected_item)
            state.selected_details = json.dumps(selected_item, indent=2)
        else:
            label_actor.SetVisibility(False)
            state.selected_details = "Select a finding to show its name directly on the original CAD geometry."
        ctrl.view_update()

    apply_visibility()
    with SinglePageLayout(server) as layout:
        layout.title.set_text("CAD Defeature Review")
        with layout.toolbar:
            vuetify3.VToolbarTitle("CAD Defeature Review — original geometry and proposed changes")
        with layout.content:
            with vuetify3.VContainer(fluid=True, classes="fill-height"):
                with vuetify3.VRow(classes="fill-height"):
                    with vuetify3.VCol(cols=8, classes="fill-height"):
                        html.P("Grey is the original CAD mesh. Select a finding to place its name on the matching face.")
                        view = vtk.VtkLocalView(render_window)
                        ctrl.view_update = view.update
                        view.reset_camera()
                    with vuetify3.VCol(cols=4):
                        html.H3("Defeature review")
                        html.P("Start with green candidates. Turn on amber or red only when you want to inspect retained or uncertain geometry.")
                        vuetify3.VChipGroup(
                            v_model=("visible_statuses", ["eligible"]),
                            multiple=True,
                            column=True,
                            children=[
                                vuetify3.VChip(status.replace("_", " "), value=status)
                                for status in statuses
                            ],
                        )
                        vuetify3.VTable(
                            children=[
                                html.Tbody(
                                    children=[
                                        html.Tr(children=[html.Td(item["status"]), html.Td(item["meaning"])])
                                        for item in state.status_guide
                                    ]
                                )
                            ]
                        )
                        html.H3("Findings on original CAD")
                        vuetify3.VList(
                            items=("highlights",),
                            item_title="label",
                            item_value="highlight_id",
                            v_model=("selected_highlight", None),
                            selectable=True,
                        )
                        html.H3("Selected finding")
                        html.Pre("{{ selected_details }}")
    server.start(host="0.0.0.0", port=port, open_browser=False)


def _set_label(label_actor, item: dict[str, object]) -> None:
    """Put a concise finding name at the centre of the matching CAD face."""
    bbox = item.get("details", {}).get("face_bounding_box", {})
    if not bbox:
        label_actor.SetVisibility(False)
        return
    x = (bbox["xmin"] + bbox["xmax"]) / 2
    y = (bbox["ymin"] + bbox["ymax"]) / 2
    z = (bbox["zmin"] + bbox["zmax"]) / 2
    label_actor.SetInput(f"{item['highlight_id']}\n{item['label']}")
    label_actor.SetPosition(x, y, z)
    label_actor.SetVisibility(True)


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
