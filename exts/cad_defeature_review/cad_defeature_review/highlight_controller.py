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
        UsdShade.MaterialBindingAPI(cube).Bind(material)
