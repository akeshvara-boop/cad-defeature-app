# Agentic CAD-to-Mesh Workbench — NVIDIA Kit-CAE extension

The extension now provides an interactive operator surface for CAD health,
healing, explicit tolerance decisions, report-only feature analysis and
independent verification through the host workflow API. It retains the
manifest-driven USD overlay review experience described below.

Start the API first:

```bash
uvicorn cad_defeature.api.app:application --host 127.0.0.1 --port 8000
```

See [`docs/kit-cae-workbench.md`](../../docs/kit-cae-workbench.md) for the Brev,
NemoClaw and Kit-CAE deployment sequence.

This extension loads a `cad_defeature_face_highlights` JSON manifest and renders
review-only RTX viewport overlays. It never edits the source CAD model.

## Run in Omniverse Kit

1. Start a Kit application that includes USD, viewport, and `omni.ui` support.
2. Add this repository's `exts` folder to Kit's extension search paths.
3. Enable **Agentic CAD-to-Mesh Workbench** in the Extension Manager.
4. Open or import the matching CAD/USD model into the active USD stage.
5. The dockable **Agentic CAD-to-Mesh Workbench** window opens when enabled.
6. Enter `data/reports/large-base-plate-highlights.json`, select **Load**, then
   select **Render overlays**.

## Colour legend

- Green: policy eligible, still requires user approval.
- Amber: insufficient confidence; no operation proposed.
- Red: detected but disallowed by current policy.

## Binding modes

The extension supports two rendering modes:

1. **Exact face highlighting** — a bound manifest includes `usd_binding` with a
   USD mesh prim path plus mesh face indices. The extension creates a
   `UsdGeomSubset` and binds the transparent review material directly to those
   faces.
2. **Bounding-box fallback** — an unbound manifest creates transparent,
   non-editing overlay boxes under `/World/CadDefeatureReview/Highlights`.

Create a bound manifest only from an importer-produced face map. The importer
must establish and retain the mapping from the inventory-run OpenCascade
`face_index` to USD mesh-face indices; never infer it from bounds alone.

```powershell
python -m cad_defeature.cli bind-usd `
  --manifest data\reports\large-base-plate-highlights.json `
  --face-map data\import\large-base-plate-usd-face-map.json `
  --output data\reports\large-base-plate-highlights-bound.json
```
