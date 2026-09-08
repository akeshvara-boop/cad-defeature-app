# Kit-CAE interactive workbench

## Delivered architecture

```text
Kit-CAE extension (GPU visualization and engineer controls)
                    |
                    | HTTP on the Brev host
                    v
cad_defeature.api.app (workflow state and audit control)
                    |
                    | fixed argv commands; no shell interpolation
                    v
NemoClaw host CLI -> OpenShell sandbox -> cad_agent.py
                    |
         +----------+-----------+----------------+
         |                      |                |
      health/heal       report-only analysis   verify
         |                      |                |
         +---------- immutable evidence --------+
                                |
                                v
                    Kit-CAE USD finding overlays
```

The split is intentional. Kit-CAE has its own Python/Kit runtime, while the CAD
kernel currently runs in the OpenShell Python 3.13 environment. The host API
keeps these environments isolated and preserves the existing human tolerance
gate.

## Current product boundary

The workbench performs:

- controlled CAD staging into the `cad-to-mesh` sandbox;
- input health assessment;
- conservative surface sewing and solid reconstruction;
- one-run human approval or rejection of tolerance concessions;
- report-only feature inventory and review highlights;
- independent verification and immutable evidence packages;
- review overlays in the active Kit-CAE USD viewport.

It does **not** yet create a solver-quality CFD surface or volume mesh. The UI
shows that handoff as `NOT IMPLEMENTED` so CAD review evidence cannot be
mistaken for a Star-CCM+ ready mesh.

## Start the API on Brev

Run this on the Brev host, not inside the NemoClaw sandbox:

```bash
cd ~/cad-defeature-app
python3 -m venv .venv-ui
.venv-ui/bin/python -m pip install -e '.[api]'

export CAD_UI_SANDBOX=cad-to-mesh
export CAD_UI_ALLOWED_ROOTS="$HOME"
.venv-ui/bin/uvicorn cad_defeature.api.app:application \
  --host 127.0.0.1 --port 8000
```

The API expects the already validated sandbox layout:

```text
/sandbox/.venvs/cad-defeature/bin/python
/sandbox/.openclaw/skills/cad-defeature/scripts/cad_agent.py
/sandbox/cad-defeature-app/cad-defeature-app/src
/sandbox/cad-sysroot/...
```

Override these with `CAD_UI_SANDBOX_PYTHON`, `CAD_UI_AGENT_SCRIPT`,
`CAD_UI_PYTHONPATH`, or `CAD_UI_LD_LIBRARY_PATH` only when the sandbox layout
really differs.

Test the host control plane:

```bash
curl http://127.0.0.1:8000/healthz
```

## Load the extension in Kit-CAE

Build and launch the NVIDIA Kit-CAE application on the same GPU host:

```bash
git clone https://github.com/NVIDIA-Omniverse/kit-cae.git
cd kit-cae
./repo.sh build -r
./repo.sh launch -n omni.cae.kit
```

In **Window > Extensions**, add this repository's `exts` directory to the
extension search paths and enable **Agentic CAD-to-Mesh Workbench**. The
extension depends on `omni.cae.bundle`, so it is intentionally targeted at a
Kit-CAE application.

## Engineer flow

1. Enter `http://127.0.0.1:8000` and select **Check**.
2. Enter the CAD path as seen by the Brev host, for example
   `/home/ubuntu/cad-defeature-app/data/input/large base plate.IGS`.
3. Select **Start workflow + health assessment**.
4. If required, run **conservative healing**.
5. When the workflow pauses, review the stated tolerance and risk. Supply a
   named engineer and justification, then approve once or reject. A higher
   subsequent request is a new decision and is never implicitly approved.
6. Run feature analysis and independent verification.
7. Enter the corresponding CAD-derived `.usd`, `.usda` or `.usdc` stage path,
   select **Open USD**, load workflow findings, and render the overlays.

Workflow state is stored under `~/.cad-defeature-ui/workflows`; engineering
artifacts remain in immutable `/sandbox/ui/runs/<workflow-id>/...` directories.

## Next implementation slice: CFD mesh handoff

The next product increment needs a meshing adapter contract with these gates:

1. geometry selected from a verified closed-solid candidate;
2. use-case policy (external aero or battery coolant) and protected faces;
3. named boundary-condition groups and stable CAD-to-mesh provenance;
4. Star-CCM+ or Neural Concept mesher job submission;
5. surface checks: watertightness, orientation, intersections and feature-edge
   capture;
6. volume checks: cell validity, skewness/non-orthogonality, prism layers,
   y-plus target and local refinement;
7. independent mesh verdict before a solver case can be created.
