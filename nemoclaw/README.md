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

## Verify the skill can actually run

Installing a skill uploads files; it does not prove the skill can reach the CAD
pipeline. The sandbox is a different environment from the `cad-defeature:latest`
image, so `import cad_defeature` may not resolve there.

Run the preflight first:

```bash
python ~/.openclaw/skills/cad-defeature/scripts/cad_agent.py doctor
```

Or simply ask the agent: *"run the cad-defeature doctor check"*.

A `usable: false` result names the remedy. The two supported backends are:

| Backend | When it applies | How to enable |
|---|---|---|
| `inprocess` | `cad_defeature` importable in the sandbox | `pip install /path/to/cad-defeature-app` inside the sandbox |
| `docker` | sandbox can reach a docker CLI + built image | `docker build -t cad-defeature:latest .` on the host |

**OpenShell blocks docker socket access by default**, so for a hardened sandbox
the in-process install is normally the correct path. Do not widen the network or
socket policy just to make the docker backend reachable.

Override detection with `CAD_DEFEATURE_BACKEND=inprocess|docker` if needed.

## Network policy note

**OpenShell blocks outbound network access by default.** Blocked requests fail
with `CONNECT tunnel failed, response 403`. Inspect which rule denied a request:

```bash
nemoclaw <sandbox-name> logs --tail 50
```

This skill is **designed to need no egress at all**:

| Operation | Network required |
|---|---|
| CAD healing, defeaturing, verification | No — local OpenCascade |
| Policy loading | No — local YAML |
| Installing the pipeline into the sandbox | No — `pip install --no-index` from the local checkout |
| Skill install / update | No — `nemoclaw skill install` runs host-side |

Consequently: **a `CONNECT tunnel 403` while using this skill is a signal, not an
obstacle.** It means something attempted unexpected egress. Investigate it with
`nemoclaw <name> logs` rather than widening the policy.

Do **not** request a network exemption to reach PyPI for this install. If pip
tries to reach the network, the wrong install command was used — see the
offline install form below.

## Offline install into the sandbox

`doctor` prints the exact command with the discovered repo path. It looks like:

```bash
python -m pip install --no-build-isolation --no-index /workspace/cad-defeature-app
```

`--no-index` guarantees pip never attempts egress. If pip complains about build
dependencies, add `--no-deps` — the OpenCascade runtime must already be present
in the sandbox image, since it cannot be fetched under this policy.

If the repo is not visible inside the sandbox, `doctor` lists the paths it
searched. Mount or copy the checkout to one of them, or set
`CAD_DEFEATURE_REPO=/actual/path`.

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
