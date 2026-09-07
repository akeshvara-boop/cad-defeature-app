# NemoClaw integration

This directory holds the NemoClaw/OpenClaw agent skill that exposes the
`cad-defeature` pipeline to a sandboxed agent.

## What NemoClaw actually is (and what it is not)

NemoClaw is **not a Python library** and is deliberately not added to
`requirements-cad.txt` or `environment.yml`. Per the
[NemoClaw Developer Guide](https://docs.nvidia.com/nemoclaw/latest/get-started/quickstart.html),
NemoClaw is an installer-driven runtime: it packages the OpenClaw agent harness
inside the NVIDIA **OpenShell** zero-trust sandbox, with kernel-level policy
enforcement (Landlock for filesystem, seccomp for syscalls) and an out-of-process
credential gateway.

That means the integration model is inverted from a normal dependency:

- NemoClaw is installed on the **host**, not inside this image.
- The agent runs in a NemoClaw-managed sandbox.
- This pipeline is exposed to that agent as an **agent skill**.

Adding a `nemoclaw` pip requirement would be wrong and would not work.

## Architecture

```text
Host (Brev instance / DGX)
  └── NemoClaw installer  -> OpenShell gateway + sandbox
        └── OpenClaw agent (Nemotron)
              └── skill: cad-defeature   <-- this directory
                    └── scripts/cad_agent.py
                          └── cad_defeature package (this repo)
```

## Prerequisites

- An `nvapi-*` API key from
  [build.nvidia.com/settings/api-keys](https://build.nvidia.com/settings/api-keys).
  **`sk-*` keys from inference.nvidia.com will not work with NemoClaw.**
- 4+ vCPU, 16 GB RAM, 40 GB free disk. A GPU is only required for local
  inference or Kit CAE visualisation, not for the agent itself.

## Install NemoClaw on the host

```bash
curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash
```

The wizard creates the OpenShell gateway, builds the sandbox image, wires
inference, and applies a starter network policy. If `nemoclaw` is not found
afterwards, run `source ~/.bashrc`.

## Install this skill into the sandbox

```bash
nemoclaw <sandbox-name> skill install ./nemoclaw/skills/cad-defeature/
```

The command validates the `SKILL.md` frontmatter (a `name` field is required)
and uploads the directory into the agent's skill path. Re-running it updates the
skill in place and preserves chat history.

## Network policy note

OpenShell blocks egress by default and logs denials. This skill performs **no
network calls** — all CAD processing is local OpenCascade work — so it needs no
policy exemptions. If you see a denial while using it, something unexpected is
reaching out; investigate rather than widening the policy.

## Safety rules the skill enforces

These are enforced in code (`cad_defeature.tolerance_gate`,
`cad_defeature.verification`), not merely described in the SKILL.md, because an
agent can be talked out of a prompt instruction but not out of a raised
exception:

| Rule | Enforcement |
|---|---|
| Agent cannot approve its own tolerance concession | `AGENT_IDENTITIES` rejection in `nemoclaw_tools` |
| Placeholder owners cannot ratify thresholds | `PLACEHOLDER_OWNERS` rejection in `verification` |
| Missing policy gates are an error, never a default | `_resolve_gates` raises |
| Run directories are immutable | `FileExistsError` on non-empty output |
| Tolerance never escalates past what was approved | `max_tolerance_limit` on the ShapeFix ladder |

This aligns with NVIDIA's agent guidance that autonomous agents "must not write
to an official source of truth without human approval".

## Local test without a sandbox

The skill script is a plain CLI and returns structured JSON, so it can be
exercised directly:

```bash
python nemoclaw/skills/cad-defeature/scripts/cad_agent.py health --input data/input/model.step
```

Every outcome — including errors — is a single JSON object with a `status`
field, so the agent never has to parse a traceback.
