# Validation — 2026-09-10

Status: native CAD first-frame gate PASSED on 2026-09-10. Browser delivery
remains a separate, unverified gate. Earlier failed probes are retained below
as historical evidence, not the current native-render result.

## Native startup diagnosis and correction

- Verified upstream OVRTX HEAD `e3ebb35a6024d070fe21125f3806d6152ed3c753`;
  the existing OVRTX/OVStage pins match its minimal example. Published package
  metadata agrees for OVRTX, OVStage, ovstream and Warp. NumPy 2.2.6 is retained
  deliberately from the upstream example. `uv pip check` passes.
- Two GDB snapshots placed the attachment caller in GPU Foundation/Carbonite
  waits while task workers executed NVIDIA shader and ray-tracing driver code.
  Changing worker stacks did not prove a fixed deadlock.
- An uninterrupted, bounded run produced a real CAD-derived 1280x720 BGRA
  frame after approximately eight minutes of cold compilation on four vCPUs.
  The earlier short deadlines were the native startup blocker.
- A warm-cache native-only repeat rendered three frames in approximately seven
  seconds. The PNG was visually inspected: the plate outline and holes appear.
- The first streaming attempt then exposed a separate lifecycle bug:
  `ovstream_create_server: unknown server type 0`. The application omitted
  `ovstream.initialize()` before server construction. Explicit initialization,
  shutdown and failure cleanup now follow upstream's example.
- Added `--render-only`, full RenderVar identity, phase duration diagnostics,
  and explicit mapped-frame release. Eleven local regression tests pass.
- Retested the corrected server on Brev: attachment took about 0.1 seconds,
  the first frame was available by 3.6 seconds, ovstream initialized and
  started successfully, three frames rendered, and cleanup exited with code
  zero without the prior active-mapping warning. This proves local server
  startup, not external video delivery (no client connected).
- No driver upgrade, firewall change or replacement of the running workbench
  was needed to establish native rendering. No claim of browser decoded video,
  CAD validity, successful defeaturing or CFD readiness is made.

Evidence on Brev: `/home/ubuntu/ovrtx-warmup-20260910T133234Z/` and
`/home/ubuntu/ovrtx-native-gdb-20260910T132602Z/` (not committed customer data).

## Historical short-deadline probes

| Check | Result |
|---|---|
| Standalone browser dependencies and Vite build | Passed |
| CPU-only CLI tests (help, missing stage, invalid port) | 3 passed |
| Python 3.12 isolated runtime installation on L40S | Passed |
| OVRTX, OVStage, ovstream, Warp imports | Passed |
| OVRTX renderer construction | Passed on repeat run |
| Attached stage / population | Stalled during bounded smoke tests |
| First converted BGRA frame | Not obtained |
| Browser decoded video / reconnect | Not tested; renderer gate blocks this |
| CAD export and workbench embedding | Not implemented in this milestone |

Installed runtime: OVRTX 0.5.0.377615, OVStage 0.2.0.377349,
ovstream 0.4.5, Warp 1.17.0, NumPy 2.2.6. GPU: NVIDIA L40S.
The browser client is independently locked to @nvidia/ov-web-rtc 6.7.0.

The initialization sequence was aligned with the pinned upstream minimal
example. Changing attachment order did not yet establish first-frame success.
No claim is made that this is a network problem or that replacing Kit fixes it.
Additional bounded diagnostics on 2026-09-10:

- Standalone OVRTX 0.5, without external OVStage attachment, loaded the sphere
  but stalled inside the first `step()`. A Python traceback identified the
  native bindings call; the probe timed out without a frame.
- An isolated comparison with OVRTX 0.4.1.364340 / OVStage 0.1.1.355824 stalled
  during renderer construction and emitted Carbonite tasking starvation
  warnings. This did not establish a working downgrade; application pins remain
  unchanged. Thread starvation is a diagnostic lead, not a proven root cause.
- Startup health now reports the initialization phase. The API reads startup
  HTTP 503 health bodies while keeping Connect disabled until rendering and
  public-route readiness are verified.

Next: resolve native runtime initialization and obtain a first-frame image
before testing browser transport. No successful rendered image is available.

No new firewall rules or public endpoints were provisioned. The existing
workbench frontend and its Kit dependencies were not modified. No customer CAD
assets or JLR reference documents were changed. Test servers are bounded and
are not a persistent production deployment.

## Repeat

### Feature branch Brev test — 2026-09-10

Tested code: `270a79b` on `feature/cad-review-viewer`, in a detached,
isolated worktree. The running application checkout was not switched.

- Found and fixed invalid single-line USD property declarations in the initial
  export. Added an OpenUSD parser regression test.
- 19 API/readiness/proxy tests, 3 preparation tests (including OpenUSD), and
  3 CLI tests passed on Linux: **25 passed**.
- A real CAD review candidate converted to 361 face IDs, 21,576 triangles and
  20,124 points. OpenUSD 26.8 parsed the result and validated mesh topology.
- Source SHA-256 remained unchanged; derived stage hash matched its manifest.
- Units of 0.001 metres per coordinate unit and Z-up were explicit diagnostic
  settings, not independently verified engineering metadata. The asset remains
  an unverified review candidate, not certified defeatured or CFD-ready CAD.
- CAD-derived USD render test used the pinned OVRTX runtime with a 60-second
  deadline and 5-second forced-stop grace. Readiness stayed HTTP 503 at
  `attaching_stage`, with zero rendered/submitted frames. The deadline killed
  the stalled process; no snapshot was produced.
- Existing API remained ready. No browser stream was attempted and no ports,
  firewall rules, renderer dependency pins or active services were changed.

The CAD preparation path passes; GPU render acceptance remains blocked.

```bash
python test_cli.py
timeout -k 5 120 bash run.sh --stage smoke.usda --frames 3
```

Set `VIEWER_PYTHON` if using an existing isolated runtime rather than `.venv`.
Do not retry indefinitely. Capture the last startup phase and resolve the native
runtime issue before provisioning public streaming or claiming readiness.
