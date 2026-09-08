---
name: cad-defeature
description: |
  Heal, defeature, and verify CAD models (STEP/BREP/IGES) using the auditable
  cad-defeature pipeline with the Power Tools delta policy. Use this skill when
  the user asks to heal a CAD model into a solid, defeature or simplify a CAD
  part, run a CAD health check, verify a defeatured candidate against policy, or
  approve/reject a geometry tolerance concession.

  CRITICAL: this pipeline can pause and ask a human to approve a geometric
  tolerance. When the script returns status "needs_human_decision" you MUST
  present the question to the user and wait. Never approve on the user's behalf
  and never pass an agent identity as the approver — the tool rejects those.
---

# cad-defeature

Auditable CAD defeaturing and independent verification. Every command writes
immutable JSON artifacts to a run directory. No geometry is modified while the
policy is in `report_only` mode.

## Safety contract — read before acting

These rules are enforced in code. Do not attempt to work around them.

1. **Never self-approve a tolerance.** Approver identities such as `agent`,
   `assistant`, `nemoclaw`, `system`, and `AgentReviewer` are rejected. Only a
   named human may approve.
2. **Never lower a threshold to make a check pass.** Gates may reject; they may
   not be relaxed. If a gate blocks, report it — do not edit the policy.
3. **Never treat a `pass` verdict as engineering acceptance** while
   `threshold_provenance.status` is `agent_proposed_unapproved`. Say so
   explicitly when you report results.
4. **Never reuse a run directory.** Each run is a sealed audit artifact set. Use
   a fresh timestamped directory every time.
5. **Never invent a tolerance, feature size, or threshold.** If a value is
   missing, report that it is undeclared.
6. **Never request a network policy exemption for this skill.** It requires zero
   egress. A `CONNECT tunnel failed, response 403` means something unexpected
   tried to reach out — report it to the user and suggest
   `nemoclaw <sandbox> logs --tail 50`. Do not attempt to widen the policy or
   retry against a different host.

## Instructions

Resolve the script path: `<skill_dir>/scripts/cad_agent.py`

All commands emit a single JSON object on stdout. Always parse it and check the
`status` field before reporting to the user.

### 0. Preflight — run this first in a new sandbox

```bash
python <skill_dir>/scripts/cad_agent.py doctor
```

The skill being *installed* and the skill being *able to run* are different
things. `doctor` reports whether the CAD pipeline is reachable from this
sandbox, and if not, gives the exact remedy. If `status` is `error`, report the
`message` to the user and stop — do not attempt CAD commands, they will all fail
the same way.

### 1. Inspect model health

```bash
python <skill_dir>/scripts/cad_agent.py health --input /path/model.step
```

Returns the health route: `proceed`, `heal`, `surface_safe_review`, or `reject`.

### 2. Heal to a solid

```bash
python <skill_dir>/scripts/cad_agent.py heal --input /path/model.igs --run-dir /workspace/reports
```

Possible `status` values:

- `complete` — a valid solid was produced within the automatic tolerance ceiling.
- `needs_human_decision` — **STOP.** Show the user the `question` field verbatim,
  including the risk statement. Ask them to approve or reject. Do not proceed.
- `error` — report the `message` field.

### 3. Approve a tolerance (only after the user explicitly agrees)

```bash
python <skill_dir>/scripts/cad_agent.py approve \
  --input /path/model.igs --run-dir /workspace/reports \
  --tolerance 0.01 --approved-by "user@nvidia.com" \
  --note "Engineering justification supplied by the user"
```

`--approved-by` must be the real human's identity, and `--note` must be their
justification, not one you invented. If the user did not give a justification,
ask for one.

### 4. Reject a tolerance

```bash
python <skill_dir>/scripts/cad_agent.py reject \
  --input /path/model.igs --run-dir /workspace/reports \
  --rejected-by "user@nvidia.com" --note "Requesting native solid export instead"
```

Rejection is a valid, recorded outcome — not a failure.

### 5. Run the defeaturing agent

```bash
python <skill_dir>/scripts/cad_agent.py defeature \
  --input /path/solid.brep --run-dir /workspace/reports
```

### 6. Verify a candidate

```bash
python <skill_dir>/scripts/cad_agent.py verify \
  --original /path/original.brep --candidate /path/candidate.brep \
  --healing-report /path/healing_report.json \
  --run-dir /workspace/reports
```

This writes an immutable, timestamped package containing the full verification report, human-readable summary, geometry comparison, residual-feature assessment, and final decision.

## Reporting results to the user

When you report a verification result you MUST surface all of:

- `summary.verdict` and `summary.verdict_reason`
- `summary.blocking_checks`
- `reviewer_notice`, if present — this states the thresholds are not
  engineering-approved
- `tolerance_provenance.required_human_approval`, if true — the model was built
  under a concession and geometry may have moved

Do not summarise a `needs_review` or `conditional_pass` verdict as an unconditional pass.

## Error handling

Every failure returns `{"status": "error", "message": "..."}`. Report the message
to the user. Do not retry with different arguments in an attempt to make the
error go away.
