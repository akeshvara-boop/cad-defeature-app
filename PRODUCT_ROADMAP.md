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

The current model is therefore readable but is presently classified as surface/wire-style geometry rather than a closed solid. CAD healing or a surface-safe workflow must be addressed before robust solid defeaturing.

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

1. Confirm and integrate NemoClaw into the Docker image and dependency configuration.
2. Commit the OpenCascade compatibility correction.
3. Implement CAD Health Report generation, including explicit handling for models with no detected solids.
4. Define the first Power Tools delta policy: feature classes, thresholds, exclusions, and acceptance criteria.
5. Implement NemoClaw agent contracts and artifact schemas.
6. Add at least one closed-solid STEP or BREP model to the test corpus for the first end-to-end workflow.
