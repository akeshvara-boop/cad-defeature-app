# Isolated OVRTX remote viewer — first-frame proof

This is a parallel experiment, not a replacement for the Kit-CAE workbench.
Its first milestone is a prepared USD stage -> OVStage -> OVRTX -> app-owned
CUDA BGRA8 buffer -> ovstream -> browser video. No browser-side 3D rendering.

## Setup and bounded renderer test

Use Python 3.12 on the Brev GPU host. Run `bash setup.sh`, then:

```bash
bash run.sh --stage smoke.usda --frames 3
```

The log must include `FIRST_BGRA_FRAME_READY 1280x720`. An import or listening
socket alone is not success. For the ongoing render service, omit `--frames`.
Initial shader compilation may take several minutes.

Separate defaults: HTTP/UI/health 127.0.0.1:8081, signaling TCP 49200,
media UDP 48098. These are local allocations, NOT publicly exposed endpoints.
No existing Kit port, gateway mapping, API process or firewall is changed.
Readiness at `/healthz` distinguishes rendered frames from submitted frames;
only the browser can confirm decoded video. Keep logs private.

## Browser route is a separate deployment gate

Use the standalone `@nvidia/ov-web-rtc` client, not the existing Kit client.
Before exposing the viewer, provision an authenticated TLS/WSS endpoint and a
matching media route (direct ingress or supported ICE/TURN). The existing Kit
gateway port translation is NOT automatically valid for this standalone client.
Do not copy the Kit `mediaServer`, `mediaPort`, or `/kit-stream` overrides.
The isolated client accepts a signaling host and port, uses one guarded session,
and declares live only after a decoded frame. It is not yet embedded into the
main workbench and cannot bypass browser mixed-content restrictions.

## Asset handoff and next milestones

`--stage /approved/path/model.usdc --product /Render/Camera` accepts a prepared
USD with camera/render product/LdrColor wiring. Source files remain unchanged.
The included sphere fixture provides a non-customer first-frame test.

Not implemented in this first milestone: CAD tessellation/USD export adapter,
automatic camera fitting, interactive camera updates, selection, workflow-ID
asset resolution, production session authorization, or workbench embedding.
Native input forwarding in the client does not imply server camera controls.
Do not label geometry CFD-ready: this viewer does not create solver meshes.

Next: prove GPU frames, establish one external browser session, then add
non-destructive asset composition/camera fitting and workbench controls.

Runtime pair is pinned to the current official OVRTX minimal example. Python
installation records the remaining resolved versions in an ignored file.
Browser dependencies are locked separately from the workbench.
