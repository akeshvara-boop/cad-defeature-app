# Product Roadmap — CAD Defeaturing & Verification Agent Platform

## Vision

Build a GPU-enabled CAD-processing application that uses the **NemoClaw framework** to orchestrate two specialized agents:

1. **CAD Defeaturing Agent** — simplifies a CAD model using the Power Tools delta policy and performs post-processing CAD checks.
2. **Verification Agent** — independently verifies that the defeatured result meets the policy and is geometrically suitable for downstream CAE use.

The application presents the original model, defeatured output, geometry differences, and agent-generated reports in **NVIDIA Kit CAE**.

## Product outcomes

- A repeatable, traceable CAD defeaturing workflow.
- Independent verification rather than relying on the defeaturing agent's own assessment.
- Visual evidence of removed or retained geometry in Kit CAE.
- Versioned CAD artifacts and machine-readable reports for each run.

## Current baseline

- The application runs in the `cad-defeature-demo` Brev environment.
- Docker image: `cad-defeature:latest`.
- IGES model upload and kernel inspection are working.
- The OpenCascade compatibility issue was corrected in source:

  ```python
  TopoDS.Shell(shell_explorer.Current())
  ```

  replacing `TopoDS.Shell_s(...)`.

- The test model (`large base plate.IGS`) was inspected successfully:
  - 361 faces
  - 5,050 edges
  - 10,100 vertices
  - 0 detected shells
  - 0 detected solids

### Status update (2026-09-07)

The healing blocker described above is **resolved, with a recorded caveat**.

- The IGES model could not be sewn into a valid solid within the conservative
  automatic tolerance ceiling of 0.001 mm.
- It was healed successfully only under a **human-approved tolerance concession
  of 0.5 mm** (500x the automatic ceiling), recorded in `healing_report.json`
  with the approver's identity and justification.
- The approval note reads "Test approval on non-production fixture". Treat the
  resulting solid as a **pipeline test fixture, not a faithful representation of
  the part**: geometry may have moved by up to 0.5 mm.

The human-in-the-loop tolerance gate is specified in
`docs/decisions/ADR-0001-tolerance-human-approval.md` and enforced in code.

**Acquiring a native closed-solid STEP AP242 or BREP export remains the highest
priority action**, because it removes the tolerance debt entirely rather than
managing it.

### Threshold ratification status

The numeric acceptance gates in `policies/power_tools_delta.yaml` are
**agent-proposed and unratified**. `threshold_provenance.pending_owner` is the
placeholder `AgentReviewer`, which the code explicitly refuses to accept as an
approver. Until a named engineer ratifies them, a `pass` verdict carries no
engineering authority. See `REVIEWER_NOTES.md`.

---

## Target architecture

```text
CAD input (STEP / BREP / IGES)
            |
            v
CAD health assessment and format classification
            |
            v
NemoClaw orchestrator
   |-------------------------------|
   v                               v
CAD Defeaturing Agent        Verification Agent
- Power Tools delta policy   - Independent CAD validation
- Feature identification     - Original/output comparison
- Incremental removal        - Residual-feature detection
- CAD check                  - Pass / conditional pass / fail
   |                               |
   |-------------------------------|
            v
Versioned CAD artifacts and reports
            |
            v
NVIDIA Kit CAE visualization
Original | Defeatured | Delta | Findings | Reports
```

---

## Phase 0 — Foundation and reproducibility

### Objective
Establish a stable, reproducible runtime for the application and its agent framework.

### Scope
- Confirm NemoClaw package availability in the Docker image and project dependencies.
- Add and pin NemoClaw dependencies if absent.
- Define the agent input, output, logging, and handoff contracts.
- Commit the OpenCascade `TopoDS.Shell` compatibility correction.
- Document Brev upload, image build, and run workflows.

### Deliverables
- Reproducible Docker build containing all required runtime dependencies.
- NemoClaw orchestration skeleton.
- Environment and operational guide.
- Sample STEP, BREP, and IGES input set.

### Exit criteria
A sample model can be inspected and passed through a minimal NemoClaw-managed pipeline.

---

## Phase 1 — CAD ingestion and health assessment

### Objective
Classify input geometry and determine whether it is safe to process.

### Scope
- Support and classify `.step`, `.stp`, `.brep`, `.iges`, and `.igs` inputs as appropriate.
- Inspect topology: vertices, edges, faces, shells, solids, and validity.
- Detect closed solids, open shells, surface-only geometry, and invalid/incomplete inputs.
- Assess healing options such as sewing, gap detection, invalid-face detection, and solid reconstruction.
- Produce a standardized Input CAD Health Report.

### Deliverables
- `inspect` and `cad-check` commands with JSON output.
- Input CAD Health Report schema.
- Explicit routing rules: proceed, heal, surface-safe processing, or reject.

### Exit criteria
Every input receives a documented health classification before agent execution.

---

## Phase 2 — CAD Defeaturing Agent

### Objective
Create a simplified CAD artifact while preserving required geometry and traceability.

### Agent responsibilities
- Receive source model, CAD Health Report, and policy thresholds.
- Apply the Power Tools delta policy.
- Identify candidate removable features, including small holes, fillets, chamfers, cosmetic geometry, small protrusions, pockets, ribs, and cut-outs.
- Remove features incrementally and maintain a complete decision log.
- Perform a post-defeaturing CAD check.

### Outputs
```text
output/
├── defeatured_model.step
├── defeatured_model.brep
├── defeaturing_report.json
├── cad_check_after_defeaturing.json
└── removal_manifest.json
```

### Report content
- Policy version and thresholds.
- Removed features, retained features, and rationale.
- Before/after topology statistics.
- CAD validity state, warnings, and processing duration.

### Exit criteria
The agent produces a defeatured artifact and evidence of each material change.

---

## Phase 3 — Verification Agent

### Objective
Independently verify geometry health and policy compliance of the defeatured output.

### Agent responsibilities
- Receive original model, defeatured model, Defeaturing Agent report, and removal manifest.
- Run an independent CAD health/topology validation.
- Compare source and result topology and geometry.
- Detect residual features that violate the policy.
- Return a decision: **pass**, **conditional pass**, **fail**, or **needs review**.

### Outputs
```text
verification/
├── verification_report.json
├── verification_summary.md
├── geometry_comparison.json
├── residual_features.json
└── final_decision.json
```

### Acceptance criteria
- No prohibited feature class remains above policy threshold.
- Output passes the agreed CAD validity checks.
- Output is suitable for the intended CAE workflow.
- Exceptions and retained features are explicitly documented.

### Exit criteria
Verification is evidence-based and independent of the defeaturing decision process.

---

## Phase 4 — Kit CAE visualization and report experience

### Objective
Enable engineers to visually validate model changes and agent findings.

### Visualization views
1. Original CAD model.
2. Defeatured CAD model.
3. Delta comparison view highlighting removed/changed geometry.
4. CAD health overlays for open, invalid, or healed regions.
5. Verification overlays for residual feature candidates and final decision.

### Report experience
- Input format and model metadata.
- Before/after topology metrics.
- Applied policy and thresholds.
- Feature removal manifest and rationale.
- CAD-check results, warnings, and verification decision.
- Exportable JSON, Markdown, and PDF reports.

### Exit criteria
Users can understand the geometry changes and agent decisions without reviewing raw logs.

---

## Phase 5 — End-to-end evaluation and hardening

### Objective
Validate reliability across representative CAD inputs and package a demonstrable workflow.

### Scope
- Test valid solid STEP/BREP models and IGES surface models.
- Include representative holes, fillets, chamfers, pockets, ribs, and small detail.
- Measure processing success rate, CAD validity success rate, feature reduction, verification pass rate, and manual-review rate.
- Tune policy thresholds and agent rules based on failures.
- Package deployment instructions for the Brev/GPU environment.

### Final demonstration
1. Upload CAD input to Brev.
2. Run CAD health assessment.
3. Execute the NemoClaw CAD Defeaturing Agent.
4. Execute the NemoClaw Verification Agent.
5. Review original/output/delta geometry in Kit CAE.
6. Export the final verification report.

---

## Immediate next steps

Status legend: DONE / PARTIAL / BLOCKED / OPEN.

1. **DONE** - Integrate NemoClaw. Delivered as an OpenClaw agent skill under
   `nemoclaw/skills/cad-defeature/`, not as a pip dependency: NemoClaw is an
   installer-driven OpenShell runtime that hosts the agent, so the pipeline is
   exposed *to* it rather than importing it. See `nemoclaw/README.md`.
2. **DONE** - Commit the OpenCascade `TopoDS.Shell` compatibility correction.
3. **DONE** - CAD Health Report generation, including the no-solid route
   (`classify_health` covers proceed / heal / surface_safe_review / reject).
4. **PARTIAL** - Power Tools delta policy defined, but its numeric thresholds are
   unratified placeholders and `min_feature_size` is undeclared.
5. **PARTIAL** - Agent contracts and artifact schemas exist for defeaturing,
   healing and verification. Four Phase 3 artifacts are still missing:
   `verification_summary.md`, `geometry_comparison.json`,
   `residual_features.json`, `final_decision.json`. `conditional pass` is not
   yet implemented.
6. **BLOCKED (external)** - Add a closed-solid STEP AP242 or BREP model to the
   test corpus. Requires a native export from the source CAD system; cannot be
   produced by healing the existing IGES file.

### Ordered plan

| # | Action | Blocked on | Unblocks |
|---|---|---|---|
| 1 | Install NemoClaw on the Brev host and install the skill into the sandbox | `nvapi-*` key | Phase 0 exit |
| 2 | Obtain a native closed-solid export | Source CAD system access | Phases 2 and 5 |
| 3 | Ratify `min_feature_size` and the acceptance deltas | Named engineering owner | Policy leaving report_only |
| 4 | Implement the four missing Phase 3 artifacts + `conditional pass` | Nothing | Phase 3 exit |
| 5 | Backfill tests for tolerance gate, gates and provenance; fill empty `test_cli.py` | Nothing | Phase 5 |

Actions 4 and 5 need no external input and can proceed immediately. Actions 1-3
are genuinely blocked on inputs that only a human can supply.
