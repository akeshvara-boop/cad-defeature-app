# CAD Defeature Review — Omniverse Kit extension

This extension loads a `cad_defeature_face_highlights` JSON manifest and renders
review-only RTX viewport overlays. It never edits the source CAD model.

## Run in Omniverse Kit

1. Start a Kit application that includes USD, viewport, and `omni.ui` support.
2. Add this repository's `exts` folder to Kit's extension search paths.
3. Enable **CAD Defeature Review** in the Extension Manager.
4. Open or import the matching CAD/USD model into the active USD stage.
5. Open **Window → CAD Defeature Review**.
6. Enter `data/reports/large-base-plate-highlights.json`, select **Load**, then
   select **Render overlays**.

## Colour legend

- Green: policy eligible, still requires user approval.
- Amber: insufficient confidence; no operation proposed.
- Red: detected but disallowed by current policy.

## Current binding mode

The manifest presently has transient OpenCascade `face_index` values, not stable
USD mesh-face mappings. The extension therefore creates transparent, non-editing
bounding-box overlay prims under `/World/CadDefeatureReview/Highlights`.
Selecting an entry selects that overlay and shows its full evidence JSON.

The next integration replaces boxes with `UsdGeomSubset` bindings after the CAD
importer emits stable USD prim paths and mesh face indices.
