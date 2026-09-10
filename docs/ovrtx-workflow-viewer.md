# Workflow-scoped OVRTX review

The workbench's central review panel embeds `/ovrtx/` with the selected workflow
ID. Geometry renders on Brev using OVStage and OVRTX. The browser displays
ovstream video; it does not render CAD locally.

## Operator flow

1. Select a workflow with a successfully recorded healed CAD output.
2. Confirm the source units and up axis in the viewer. Do not guess these values.
3. Select **Load CAD output**. The API copies only that workflow's recorded output
   into an isolated review directory and prepares USD in the separate CAD worker.
4. Wait for **Selected CAD output rendered**, then select **Connect once**.
5. Switching workflow or output replaces the iframe and disconnects its session.
   Each new iframe requires an explicit load, so an earlier output cannot be
   silently reused, even within the same workflow.

Healed geometry is not necessarily defeatured, independently verified, or
CFD-ready. Failed healing and input-only workflows are deliberately blocked.
Original CAD and workflow approval records are not modified by viewing.

## Deployment configuration

The host API needs `CAD_UI_WEB_DIST`, `CAD_UI_OVRTX_DIST`,
`CAD_UI_PUBLIC_ORIGIN`, `CAD_UI_REVIEW_ROOT`, and `CAD_UI_REVIEW_PYTHON`.
Set `CAD_UI_VIEWER_TOKEN` to the same private random token in the API and native
viewer. Store it outside the repository with user-only permissions. The viewer
also needs the same `CAD_UI_REVIEW_ROOT`.

Configure `CAD_UI_OVRTX_SIGNALING_HOST` and `CAD_UI_OVRTX_SIGNALING_PORT` for the
public TLS proxy, plus `CAD_UI_OVRTX_MEDIA_HOST` and `CAD_UI_OVRTX_MEDIA_PORT`
for the existing public UDP mapping. `CAD_UI_OVRTX_ROUTE_CONFIGURED=true`
allows browser testing; it is **not** evidence of decoded video.

The browser signaling path is `/ovrtx-stream/sign_in`; the API bridges to the
fixed loopback endpoint `ws://127.0.0.1:49200/sign_in`. Native health and asset
loading use loopback port 8081. Asset loading requires the shared token.
Signaling checks the browser origin and matching rendered workflow/asset IDs.

For the existing Brev mapping, public UDP 15865 maps to host UDP 49100;
start the standalone server with `--media-port 49100`. Do not run Kit or another
renderer on that host UDP port. Public signaling remains on the HTTPS proxy,
not the UDP endpoint.

Use the tested renderer environment separately from the CAD worker: OVRTX
0.5.0.377615, OVStage 0.2.0.377349, ovstream 0.4.5, Warp 1.17.0 and Python 3.12.
The embedded client uses `@nvidia/ov-web-rtc` 6.7.0. Keep dependency lockfiles.

## Validation evidence, 2026-09-10

- Both frontend production builds completed.
- 24 focused backend tests and 13 standalone viewer tests passed.
- Deployed API, workbench and embedded client returned HTTP 200.
- Native OVRTX rendered frames and successfully switched to an isolated CAD
  review fixture without restarting the renderer.
- Failed healing returned HTTP 409; a foreign origin returned HTTP 403.
- A different workflow could not connect to the fixture's asset.
- The local OVRTX WebSocket proxy upgrade succeeded.

The fixture was not recorded as a customer workflow or shown as its output.
Public gateway UDP delivery and actual browser decoded frames still require
an authenticated browser test with a successful workflow output. Native frames,
HTTP readiness and a WebSocket upgrade alone do not establish this.

## Signaling handoff fix and controlled media validation

The client intentionally closes its initial signaling WebSocket with code 4001
and opens a replacement using `reconnect=1`. The old bridge discarded the
disconnect code, closing the upstream with 1000. Native logs consequently showed
`mayReconnect: 0` followed by
`NVST_DISCONN_PEER_TRANSPORT_TERMINATED_ON_SIGNALING`. This ended an otherwise
established session. Preserve valid close codes and reasons in both directions;
do not transmit reserved synthetic codes (1005/1006).

An isolated animated CUDA test pattern reproduced the same failure without
OVRTX, OVStage or CAD processing. Native logs showed DTLS and NVENC initialization
succeeding before signaling teardown. After the proxy fix, a controlled Chrome
CAD test decoded 582 video frames at 30 FPS, with an ICE candidate pair in
`succeeded`, DTLS connected, and zero reported lost video packets. The native
handoff then logged `mayReconnect: 1`.

This test used loopback SSH-tunneled signaling and the existing public Brev UDP
media gateway. It proves external media delivery from Brev to the test laptop,
but does not independently validate the authenticated public HTTPS/Pomerium
signaling route. A normal-browser workbench test remains the final acceptance
step. No firewall, driver or TURN changes were made.

The viewer now owns a dedicated AppStreamer instance and provides a downloadable
connection report with SDK lifecycle, ICE, DTLS and video statistics. Reports do
not intentionally collect SDP or data-channel content; review diagnostics before
sharing externally. Native INFO-level diagnostic logs may contain session
metadata and must remain in a private operator directory.
