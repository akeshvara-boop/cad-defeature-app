# CAD Defeaturing Application

Source-of-truth repository for an auditable STEP/BREP CAD defeaturing pipeline.

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
