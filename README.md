# CAD Defeaturing Application

Source-of-truth repository for an auditable STEP/BREP CAD defeaturing pipeline.

> ### Read REVIEWER_NOTES.md before trusting any report
>
> The numeric acceptance thresholds in `policies/power_tools_delta.yaml` are
> **agent-proposed placeholders and are not engineering-approved**. A `pass`
> is only possible after those thresholds are ratified. Until then, technically
> complete evidence can produce `conditional_pass`, while missing evidence
> produces `needs_review`; neither means "acceptable for engineering use". The
> policy is `mode: report_only`, so no geometry is modified. Reviewers must read
> [`REVIEWER_NOTES.md`](REVIEWER_NOTES.md) before relying on any output.

## Container runtime

The Docker image packages the Python/OpenCascade/CadQuery runtime used by the
`cad-defeature` CLI. It is intentionally separate from Kit-CAE: Kit-CAE has a
large, platform-specific Kit SDK build and should be cloned and built on the
target GPU host.

### Build

```bash
docker build -t cad-defeature:latest .
```

### Run

Place source models in `data/input/`. Generated artifacts are written to
`data/output/` or `reports/` through bind mounts.

```bash
# Show CLI usage
docker run --rm cad-defeature:latest --help

# Inspect an IGES, STEP, or BREP model
docker run --rm \
  -v "$PWD/data/input:/workspace/input:ro" \
  cad-defeature:latest \
  inspect /workspace/input/model.igs

# Write a read-only baseline report
docker run --rm \
  -v "$PWD/data/input:/workspace/input:ro" \
  -v "$PWD/reports:/workspace/reports" \
  cad-defeature:latest \
  baseline /workspace/input/model.igs \
  --output /workspace/reports/model-baseline.json

# Produce a policy-driven feature inventory
docker run --rm \
  -v "$PWD/data/input:/workspace/input:ro" \
  -v "$PWD/data/output:/workspace/output" \
  cad-defeature:latest \
  inventory /workspace/input/model.igs \
  --policy /app/policies/power_tools_delta.yaml \
  --output /workspace/output/model-inventory.json
```

A complete independent verification run can be written as an immutable Phase 3
package:

```bash
cad-defeature verify --original /workspace/input/original.brep \
  --candidate /workspace/input/candidate.brep \
  --policy /app/policies/power_tools_delta.yaml \
  --healing-report /workspace/reports/healing_report.json \
  --output-dir /workspace/reports/verification-run
```

The CLI refuses to overwrite report/manifest paths. Use a new output filename
for each run, or intentionally remove an obsolete local output beforehand.

### Docker Compose

```bash
docker compose run --rm cad-defeature --help
```

The current core pipeline is CPU/OpenCascade based. For future GPU-backed VTK
or rendering functionality inside this container, install NVIDIA Container
Toolkit on the target host and uncomment `gpus: all` in `docker-compose.yml`.

## Target-host setup

```bash
git clone https://github.com/akeshvara-boop/cad-defeature-app.git
cd cad-defeature-app
docker build -t cad-defeature:latest .
```

For Kit-CAE, clone and build it separately on the Linux GPU host:

```bash
git clone https://github.com/NVIDIA-Omniverse/kit-cae.git
cd kit-cae
./repo.sh build -r
```

## Interactive Kit-CAE workbench

The `cad_defeature_review` extension is now an interactive Kit-CAE control and
review surface. A host-side FastAPI service stages CAD into the `cad-to-mesh`
NemoClaw sandbox, invokes the structured agent actions, persists workflow state,
and returns findings to Kit-CAE without blocking the render thread.

```bash
python3 -m pip install -e '.[api]'
uvicorn cad_defeature.api.app:application --host 127.0.0.1 --port 8000
```

Full setup and product boundaries are documented in
[`docs/kit-cae-workbench.md`](docs/kit-cae-workbench.md). The current UI does
not claim to generate a CFD-ready mesh; that downstream adapter and its mesh
quality gates remain the next implementation slice.

## NVIDIA-style web workbench

The customer-facing React portal is under `web/`. It presents the real workflow
state, agent event timeline, human tolerance gate, verification evidence and an
embedded Kit-CAE WebRTC viewport. The FastAPI service serves a production build
at `/ui/`, so one Brev Secure Link can expose both the experience and API.

```bash
cd web
npm install
npm run build

cd ..
export CAD_UI_KIT_SIGNALING_HOST="<BREV_PUBLIC_STREAM_HOST>"
export CAD_UI_KIT_SIGNALING_PORT=49100
uvicorn cad_defeature.api.app:application --host 0.0.0.0 --port 8000
```

Open the port-8000 Brev Secure Link root; it redirects to `/ui/`. For frontend
development, `npm run dev` serves `/ui/` on port 5173 and proxies `/healthz`
and `/v1` to the host API on `127.0.0.1:8000`.

The WebRTC stream remains a separate transport. Kit must log that its primary
stream server started and listen on TCP 49100 before the viewport can connect.
