"""USD overlay creation and viewport selection support for manifest highlights."""

from __future__ import annotations


class HighlightController:
    """Create transparent bounding-box overlays when exact USD face subsets are unavailable."""

    OVERLAY_ROOT = "/World/CadDefeatureReview/Highlights"

    def __init__(self):
        self._overlay_paths = {}

    def clear(self):
        import omni.usd

        stage = omni.usd.get_context().get_stage()
        if stage:
            stage.RemovePrim(self.OVERLAY_ROOT)
        self._overlay_paths.clear()

    def render(self, highlights: list[dict]):
        """Create viewer-only USD box overlays from manifest face bounding boxes."""
        import omni.usd
        from pxr import Gf, UsdGeom, UsdShade

        stage = omni.usd.get_context().get_stage()
        if not stage:
            raise RuntimeError("No USD stage is open. Open/import the CAD model first.")
        UsdGeom.Xform.Define(stage, self.OVERLAY_ROOT)
        for item in highlights:
            if item.get("usd_binding"):
                self._render_face_subset(stage, item)
                continue
            bounds = item["details"]["face_bounding_box"]
            overlay_path = f"{self.OVERLAY_ROOT}/{item['highlight_id']}"
            cube = UsdGeom.Cube.Define(stage, overlay_path)
            cube.CreateSizeAttr(1.0)
            size = Gf.Vec3d(
                bounds["xmax"] - bounds["xmin"],
                bounds["ymax"] - bounds["ymin"],
                bounds["zmax"] - bounds["zmin"],
            )
            centre = Gf.Vec3d(
                (bounds["xmin"] + bounds["xmax"]) / 2,
                (bounds["ymin"] + bounds["ymax"]) / 2,
                (bounds["zmin"] + bounds["zmax"]) / 2,
            )
            cube.AddScaleOp().Set(size)
            cube.AddTranslateOp().Set(centre)
            self._bind_material(stage, cube, item["color"], item["opacity"])
            cube.GetPrim().SetCustomDataByKey("cad_defeature", item)
            self._overlay_paths[item["highlight_id"]] = overlay_path

    def _render_face_subset(self, stage, item):
        """Bind a preview material to exact imported USD mesh face indices."""
        from pxr import UsdGeom

        binding = item["usd_binding"]
        mesh = stage.GetPrimAtPath(binding["usd_prim_path"])
        if not mesh.IsValid() or not mesh.IsA(UsdGeom.Mesh):
            raise RuntimeError(f"USD mesh was not found: {binding['usd_prim_path']}")
        subset_path = f"{mesh.GetPath()}/CadDefeature_{item['highlight_id']}"
        subset = UsdGeom.Subset.CreateGeomSubset(
            UsdGeom.Mesh(mesh), subset_path.name, UsdGeom.Tokens.face, binding["usd_face_indices"]
        )
        self._bind_material(stage, subset, item["color"], item["opacity"])
        subset.GetPrim().SetCustomDataByKey("cad_defeature", item)
        self._overlay_paths[item["highlight_id"]] = str(subset.GetPath())

    def select(self, highlight_id: str):
        import omni.usd

        path = self._overlay_paths.get(highlight_id)
        if path:
            omni.usd.get_context().get_selection().set_selected_prim_paths([path], True)

    @staticmethod
    def _bind_material(stage, cube, html_colour: str, opacity: float):
        from pxr import Gf, UsdShade

        material_path = f"{cube.GetPath()}_Material"
        material = UsdShade.Material.Define(stage, material_path)
        shader = UsdShade.Shader.Define(stage, f"{material_path}/PreviewSurface")
        shader.CreateIdAttr("UsdPreviewSurface")
        red, green, blue = (int(html_colour[index:index + 2], 16) / 255 for index in (1, 3, 5))
        shader.CreateInput("diffuseColor", UsdShade.Tokens.color3f).Set(Gf.Vec3f(red, green, blue))
        shader.CreateInput("opacity", UsdShade.Tokens.float).Set(opacity)
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI(cube.GetPrim()).Bind(material)
