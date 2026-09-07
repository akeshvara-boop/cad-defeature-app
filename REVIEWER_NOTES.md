# NOTE TO REVIEWERS AND BUILDERS — READ BEFORE TRUSTING ANY OUTPUT

**Status: the thresholds in this project are NOT engineering-approved.**

This file exists because the pipeline is capable of producing confident-looking
JSON reports with verdicts like `pass`. Anyone reading those reports — a human
reviewer, a downstream agent, or a future maintainer — must understand what has
and has not been ratified by an engineer.

## 1. Provisional thresholds (agent-proposed, NOT approved)

The numeric gates in `policies/power_tools_delta.yaml` were proposed by the
assistant that built this pipeline. They are placeholders chosen to be
conservative. **No engineer who owns the Power Tools delta workflow has signed
off on them.**

| Gate | Current value | Provenance |
|---|---|---|
| `max_bounding_box_delta` | 0.0 mm | Agent-proposed placeholder |
| `max_volume_delta_percent` | 1.0 % | Agent-proposed placeholder |
| `require_valid_solid` | true | Agent-proposed, low risk |
| `require_closed_shell` | true | Agent-proposed, low risk |
| `allow_non_manifold_edges` | false | Agent-proposed, low risk |
| Healing automatic ceiling | 0.001 mm | Empirical: value that closed this fixture's shell |
| Healing gap tolerance reference | 0.01 mm | Sourced from NVIDIA Autonomous Aerospace SRS default |

Until an owner ratifies these, a `pass` verdict means only
*"passed the assistant's proposed limits"* — not *"acceptable for engineering
use"*.

## 2. Volume delta is the wrong primary gate

`max_volume_delta_percent` is the weakest gate in this policy and should not be
the primary control. NVIDIA's own CAD-to-Mesh A2A requirements define geometry
verification in terms of reported quantities — open/free edges, non-manifold
entities, gaps, overlaps, sliver faces, short edges, **minimum feature size**,
closed region count and volume, and **protected-feature retention** — with
volume/area deltas as *one reported item among many*.

The correct primary control is **minimum feature size**: declare the smallest
feature that must survive defeaturing, and treat volume delta as reported
evidence rather than the acceptance test. A single volume percentage cannot
distinguish "removed 200 fastener holes" from "removed a coolant channel".

## 3. Thresholds are per use-case, not global

`power_tools_delta.yaml` currently has one flat set of gates. The A2A
requirements define **separate policies per use case** (aerodynamics vs battery
thermal) with different protected features. A plate with coolant channels needs
protected-feature retention far more than it needs a volume cap.

Do not reuse this policy across use cases without re-deriving its gates.

## 4. The current test fixture carries tolerance debt

The `large base plate.IGS` fixture could not be healed into a valid solid within
the conservative automatic ceiling. It was only buildable under a **human
tolerance concession of 0.5 mm** — 500× the automatic ceiling — recorded in the
healing report with the approver's identity.

Consequences:

- Geometry in that healed solid may have moved by up to 0.5 mm anywhere.
- The approval note reads "Test approval on non-production fixture".
- **Treat that model as a pipeline test fixture, not as a representation of the
  part.** Any geometric result derived from it is provisional.

The preferred remedy is a **native closed-solid STEP AP242 or Parasolid export**
of the part, which removes the tolerance concession entirely. Per the A2A
requirements, STL must never be the authoritative CAD hand-off.

## 5. Rules the agent must never relax

These follow NVIDIA's A2A ownership model, where the Meshing Agent explicitly
"must not own: lowering acceptance thresholds" and the Geometry Verification
Agent "must not own: repairing the geometry it verifies".

- The agent **never** escalates tolerance beyond the automatic ceiling on its
  own; a human must approve, with an accountable identity and a justification
  (see `docs/decisions/ADR-0001-tolerance-human-approval.md`).
- The agent **never** self-approves. Agent identities are rejected outright.
- The Verification Agent **never** repairs what it verifies.
- Gates may **reject**; they may not lower their own thresholds.
- Missing gates are an **error**, never a default. Verification refuses to run
  rather than assume a limit nobody approved.
- No gap filling and no invented surfaces, at any tolerance.
- Source models are never overwritten; run directories are immutable.

## 6. What a reviewer must check before accepting a report

1. Read `summary.verdict_reason` and `summary.blocking_checks` — not just
   `verdict`.
2. Check `tolerance_provenance`. If `required_human_approval` is true, the model
   was built under a concession; read the approver and the note.
3. Confirm no check is silently `not_assessed`. An unassessed gate is not a
   passed gate.
4. Confirm the policy version and mode. While `mode: report_only`, **no geometry
   is modified** — a report is a classification, not a change.

## 7. Open questions requiring an engineering owner

- What is the real minimum feature size that must survive defeaturing?
- What volume delta, if any, is acceptable — and per use case?
- Should `max_bounding_box_delta` be exact zero, or allow numerical noise
  (kernel operations can perturb the envelope by ~1e-9 mm)?
- Which feature classes are protected for this part family?
- Who is the accountable owner able to ratify these thresholds?

Until these are answered by a named owner, this pipeline should be regarded as
**structurally sound but not qualified for production geometry decisions**.
