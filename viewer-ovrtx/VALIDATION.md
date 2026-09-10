# Validation — 2026-09-10

Status: implementation scaffold built; GPU first-frame gate NOT passed.

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
The next diagnostic is a minimal native runtime reproducer for the attach /
population boundary, followed by first-frame image validation.

No new firewall rules or public endpoints were provisioned. The existing
workbench frontend and its Kit dependencies were not modified. No customer CAD
assets or JLR reference documents were changed. Test servers are bounded and
are not a persistent production deployment.

## Repeat

```bash
python test_cli.py
timeout -k 5 120 bash run.sh --stage smoke.usda --frames 3
```

Set `VIEWER_PYTHON` if using an existing isolated runtime rather than `.venv`.
Do not retry indefinitely. Capture the last startup phase and resolve the native
runtime issue before provisioning public streaming or claiming readiness.
