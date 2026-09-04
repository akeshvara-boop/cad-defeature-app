# ADR-0001: Tolerance changes require recorded human approval

- **Status:** Accepted
- **Date:** 2026-09-04
- **Deciders:** Ambica Keshvara (product owner)
- **Applies to:** `cad_defeature.healing`, `cad_defeature.repair`, `heal` CLI command

## Context

The `large base plate.IGS` fixture cannot be turned into a valid solid at a
conservative tolerance. Observed behaviour, recorded in healing reports:

- sewing at `0.0001` mm leaves 3,422 free edges;
- sewing at `0.001` mm closes the shell (0 free edges) but produces exactly one
  invalid face (index 123), which invalidates its shell and the solid;
- a `ShapeFix` ladder up to `max_tolerance = 1.0` mm did not yield a model that
  survives the write/read validity round-trip.

Tolerance is therefore the pivotal engineering variable in this pipeline, and it
is not a purely technical choice:

1. A larger sewing or repair tolerance can silently move real geometry.
2. What counts as an acceptable deviation depends on the part, its material, its
   manufacturing intent, and the downstream simulation - none of which the agent
   can know.
3. Escalating tolerance automatically until something validates would let the
   pipeline "succeed" by deforming the customer's part. That directly
   contradicts the safety guarantee the agent exists to provide.

The agent must be able to *complete* work on imperfect real-world CAD, but it
must not be the party that decides how much geometric deviation is acceptable.

## Decision

**The agent will never escalate tolerance beyond a conservative automatic limit
on its own. Any tolerance above that limit requires explicit, recorded human
approval, supplied per run.**

Concretely:

1. `heal` accepts `--max-auto-tolerance` with a conservative default
   (`0.001` mm). Within this bound the agent proceeds unattended.
2. If no valid solid is achievable within that bound, the agent does **not**
   fail silently and does **not** loosen the tolerance. It stops and writes a
   `tolerance_decision_request.json` artifact containing:
   - the evidence per tolerance tried (free edges, degenerate shapes, invalid
     face/shell/solid counts, and the specific invalid face indices);
   - the smallest tolerance that would be required to progress;
   - the explicit geometric risk statement for that tolerance;
   - the exact command the reviewer must run to grant approval.
3. A human grants approval by re-running with:
   - `--approved-tolerance <value>` - the ceiling they authorise;
   - `--approved-by <name-or-email>` - who is accountable;
   - `--approval-note "<engineering justification>"`.
4. The granted tolerance, approver, note, and UTC timestamp are written into
   the healing report and into the resulting artifact set, so any downstream
   defeatured model is traceable to the human who authorised its tolerance.
5. Approval is **per run and per value**. It is not persisted, not inferred, and
   never reused implicitly by a later run.
6. All existing safety gates remain unconditional and are not waivable by
   approval: no gap filling, no invented surfaces, no overwriting of source
   models, and mandatory post-write validity re-validation.

## Consequences

### Positive

- The pipeline can complete on imperfect real-world CAD instead of dead-ending.
- The accountable engineering decision sits with a named human.
- Every tolerance concession is auditable after the fact, with the geometric
  evidence that motivated it attached.
- The agent's default behaviour stays conservative, so unattended runs cannot
  quietly deform parts.

### Negative

- Difficult models require a human round-trip, so healing is not always
  fully autonomous.
- Operators must understand what a tolerance value means; the decision request
  therefore has to state the risk in plain engineering terms, not just numbers.

### Rejected alternatives

- **Auto-escalate until valid.** Rejected: converts a safety tool into a silent
  deformation tool.
- **Hard-fail on any imperfect model.** Rejected: most production CAD, and
  especially IGES surface exports, would be permanently out of scope.
- **Persist a global tolerance setting.** Rejected: a value justified for one
  part would be applied invisibly to unrelated parts.

## Preferred remedy remains upstream

Human tolerance approval is a mitigation, not the ideal path. Where possible the
better fix is a **native closed-solid STEP AP242 or BREP export** from the source
CAD system, which avoids the surface-sewing problem entirely. The Verification
Agent should continue to flag any model that required an approved tolerance above
the automatic limit.
