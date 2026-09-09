import { useEffect, useMemo, useState } from "react";

import { api } from "./api";
import { StreamViewport } from "./components/StreamViewport";
import type { FrontendConfig, JsonRecord, WorkflowEvent, WorkflowState } from "./types";

type Tab = "experience" | "report" | "blueprint";

const DEFAULT_SOURCE = "/home/ubuntu/cad-defeature-app/data/input/large base plate.IGS";

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

function pathValue(root: unknown, ...path: string[]): unknown {
  let current = root;
  for (const key of path) {
    current = record(current)[key];
  }
  return current;
}

function display(value: unknown, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value).replace(/_/g, " ");
}

function eventStatus(events: WorkflowEvent[] = [], actions: string[]): string {
  const event = [...events].reverse().find((item) => actions.includes(item.action));
  return event?.status ?? "pending";
}

function statusTone(status: string): string {
  const value = status.toLowerCase();
  if (["complete", "ready", "pass"].includes(value)) return "success";
  if (["conditional_pass", "needs_human_decision", "needs_review"].includes(value)) return "review";
  if (["error", "failed", "fail", "rejected"].includes(value)) return "danger";
  if (["running", "connecting"].includes(value)) return "active";
  return "muted";
}

function Metric({ label, value, suffix }: { label: string; value: unknown; suffix?: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{display(value)}{value !== null && value !== undefined && suffix ? suffix : ""}</strong>
    </div>
  );
}

function StatusPill({ value }: { value: string }) {
  return <span className={`pill ${statusTone(value)}`}>{display(value)}</span>;
}

export default function App() {
  const [tab, setTab] = useState<Tab>("experience");
  const [config, setConfig] = useState<FrontendConfig | null>(null);
  const [apiState, setApiState] = useState("checking");
  const [workflows, setWorkflows] = useState<WorkflowState[]>([]);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [sourcePath, setSourcePath] = useState(DEFAULT_SOURCE);
  const [maxAutoTolerance, setMaxAutoTolerance] = useState(0.001);
  const [engineer, setEngineer] = useState("");
  const [decisionNote, setDecisionNote] = useState("");
  const [signalingHost, setSignalingHost] = useState("");
  const [signalingPort, setSignalingPort] = useState(49100);
  const [signalingSecure, setSignalingSecure] = useState(false);
  const [mediaPort, setMediaPort] = useState<number | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.config(), api.health(), api.workflows()])
      .then(([deployment, health, recent]) => {
        const query = new URLSearchParams(window.location.search);
        const queryHost = query.get("server")?.trim();
        const queryPort = Number(query.get("signalingPort"));
        const querySecure = query.get("secure");
        setConfig(deployment);
        setApiState(String(health.status ?? "unknown"));
        setSignalingHost(queryHost || deployment.kit_stream.signaling_host);
        setSignalingPort(
          Number.isInteger(queryPort) && queryPort > 0
            ? queryPort
            : deployment.kit_stream.signaling_port
        );
        setSignalingSecure(
          querySecure === null
            ? deployment.kit_stream.signaling_secure
            : ["1", "true", "yes"].includes(querySecure.toLowerCase())
        );
        setMediaPort(deployment.kit_stream.media_port);
        setWorkflows(recent);
        if (recent.length) setWorkflow(recent[0]);
      })
      .catch((reason) => {
        setApiState("not ready");
        setError(reason instanceof Error ? reason.message : "Unable to reach the workflow API.");
      });
  }, []);

  const proposedTolerance = Number(pathValue(workflow?.tolerance_request, "proposed_tolerance"));
  const needsDecision = workflow?.phase === "awaiting_tolerance_decision";
  const topology = record(pathValue(workflow?.health, "inspection", "topology"));
  const healthClassification = pathValue(workflow?.health, "health", "classification");
  const healthRoute = pathValue(workflow?.health, "health", "route");
  const verificationVerdict = pathValue(workflow?.verification, "verdict");

  const steps = useMemo(() => [
    { label: "Ingest CAD", agent: "CAD Intake Agent", status: eventStatus(workflow?.events, ["ingest"]) },
    { label: "Assess health", agent: "CAD Health Agent", status: eventStatus(workflow?.events, ["health"]) },
    { label: "Heal geometry", agent: "Healing Agent", status: needsDecision ? "needs_human_decision" : eventStatus(workflow?.events, ["approve", "heal"]) },
    { label: "Analyse features", agent: "Defeaturing Agent", status: eventStatus(workflow?.events, ["defeature"]) },
    { label: "Verify independently", agent: "Verification Agent", status: eventStatus(workflow?.events, ["verify"]) },
    { label: "Generate CFD mesh", agent: "Mesh Agent", status: "not_implemented" }
  ], [needsDecision, workflow?.events]);

  async function run(label: string, operation: () => Promise<WorkflowState>) {
    setBusy(label);
    setError("");
    try {
      const next = await operation();
      setWorkflow(next);
      setWorkflows((current) => [next, ...current.filter((item) => item.workflow_id !== next.workflow_id)]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Workflow operation failed.");
    } finally {
      setBusy("");
    }
  }

  function requireWorkflow(): WorkflowState {
    if (!workflow) throw new Error("Start or select a workflow first.");
    return workflow;
  }

  function execute(label: string, operation: (current: WorkflowState) => Promise<WorkflowState>) {
    let current: WorkflowState;
    try {
      current = requireWorkflow();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Select a workflow first.");
      return;
    }
    void run(label, () => operation(current));
  }

  function submitApproval(approved: boolean) {
    if (!workflow || !needsDecision) return;
    if (!engineer.trim() || !decisionNote.trim()) {
      setError("A named accountable engineer and engineering justification are required.");
      return;
    }
    if (approved) {
      void run("Recording approval", () => api.approve(
        workflow.workflow_id,
        proposedTolerance,
        engineer,
        decisionNote,
        maxAutoTolerance
      ));
    } else {
      void run("Recording rejection", () => api.reject(
        workflow.workflow_id,
        engineer,
        decisionNote
      ));
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">NVIDIA</span>
          <span className="product-name">Agentic CAD-to-Mesh Workbench</span>
          <span className="version">v{config?.api_version ?? "0.1.0"}</span>
        </div>
        <nav className="tabs" aria-label="Workbench views">
          {(["experience", "report", "blueprint"] as Tab[]).map((item) => (
            <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>
              {item === "experience" ? "Experience" : item === "report" ? "Workflow Report" : "Blueprint"}
            </button>
          ))}
        </nav>
        <div className="system-state">
          <span className={`status-dot status-${apiState === "ready" ? "connected" : "error"}`} />
          API {display(apiState)}
        </div>
      </header>

      <div className="notice">
        <strong>Engineering assurance:</strong> AI-generated recommendations require verification. Human tolerance decisions are recorded per run and never reused implicitly.
      </div>

      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <button onClick={() => setError("")} aria-label="Dismiss error">×</button>
        </div>
      )}

      {tab === "experience" && (
        <main className="experience-grid">
          <aside className="workflow-panel panel">
            <div className="section-heading">
              <div>
                <span className="eyebrow">INPUT</span>
                <h2>Workflow</h2>
              </div>
              {workflow && <StatusPill value={workflow.status} />}
            </div>

            <label>
              CAD path on Brev
              <input value={sourcePath} onChange={(event) => setSourcePath(event.target.value)} />
            </label>
            <button
              className="button primary full"
              disabled={Boolean(busy) || !sourcePath.trim()}
              onClick={() => void run("Starting workflow", () => api.start(sourcePath.trim()))}
            >
              {busy === "Starting workflow" ? "Inspecting CAD…" : "Start workflow + health check"}
            </button>

            <div className="workflow-history">
              <span className="field-label">Recent runs</span>
              <select
                value={workflow?.workflow_id ?? ""}
                onChange={(event) => {
                  const selected = workflows.find((item) => item.workflow_id === event.target.value);
                  if (selected) setWorkflow(selected);
                }}
              >
                <option value="">No workflow selected</option>
                {workflows.map((item) => (
                  <option key={item.workflow_id} value={item.workflow_id}>
                    {item.workflow_id} · {display(item.phase)}
                  </option>
                ))}
              </select>
            </div>

            <div className="step-list">
              {steps.map((step, index) => (
                <div className={`step ${statusTone(step.status)}`} key={step.label}>
                  <div className="step-index">{index + 1}</div>
                  <div>
                    <strong>{step.label}</strong>
                    <span>{step.agent}</span>
                  </div>
                  <StatusPill value={step.status} />
                </div>
              ))}
            </div>

            <div className="action-stack">
              <label>
                Automatic tolerance ceiling (mm)
                <input
                  type="number"
                  min="0.000001"
                  step="0.001"
                  value={maxAutoTolerance}
                  onChange={(event) => setMaxAutoTolerance(Number(event.target.value))}
                />
              </label>
              <button
                className="button secondary full"
                disabled={!workflow || Boolean(busy)}
                onClick={() => execute("Healing geometry", (current) => api.heal(current.workflow_id, maxAutoTolerance))}
              >
                Run conservative healing
              </button>
              <div className="button-row">
                <button
                  className="button secondary"
                  disabled={!workflow || Boolean(busy)}
                  onClick={() => execute("Analysing features", (current) => api.analyze(current.workflow_id))}
                >
                  Analyse features
                </button>
                <button
                  className="button secondary"
                  disabled={!workflow || Boolean(busy)}
                  onClick={() => execute("Verifying candidate", (current) => api.verify(current.workflow_id))}
                >
                  Verify
                </button>
              </div>
            </div>
          </aside>

          <section className="visual-column">
            <div className="stream-settings panel">
              <div>
                <span className="eyebrow">OUTPUT</span>
                <h2>Engineering review</h2>
              </div>
              <label>
                Kit signalling host
                <input
                  placeholder="e.g. global.prd.ga.run.brev.nvidia.com"
                  value={signalingHost}
                  onChange={(event) => setSignalingHost(event.target.value)}
                />
              </label>
              <label className="port-field">
                Port
                <input
                  type="number"
                  value={signalingPort}
                  onChange={(event) => setSignalingPort(Number(event.target.value))}
                />
              </label>
              <label className="transport-field">
                Transport
                <select
                  value={signalingSecure ? "wss" : "ws"}
                  onChange={(event) => setSignalingSecure(event.target.value === "wss")}
                >
                  <option value="ws">Direct WS</option>
                  <option value="wss">TLS proxy WSS</option>
                </select>
              </label>
            </div>
            <StreamViewport
              host={signalingHost}
              signalingPort={signalingPort}
              secure={signalingSecure}
              mediaPort={mediaPort}
              signalingPath={config?.kit_stream.signaling_path}
              configurationWarnings={config?.kit_stream.configuration_warnings}
            />

            <div className="metrics-grid">
              <Metric label="Faces" value={topology.faces} />
              <Metric label="Edges" value={topology.edges} />
              <Metric label="Shells" value={topology.shells} />
              <Metric label="Solids" value={topology.solids} />
              <Metric label="Health route" value={healthRoute} />
              <Metric label="Verification" value={verificationVerdict} />
            </div>
          </section>

          <aside className="insight-column">
            <section className="panel agent-panel">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">ORCHESTRATION</span>
                  <h2>Agent activity</h2>
                </div>
                {busy && <span className="working-indicator">{busy}…</span>}
              </div>
              <div className="tool-chain">
                <span>NemoClaw</span><i>→</i><span>OpenShell</span><i>→</i><span>OpenCascade</span><i>→</i><span>Kit-CAE</span>
              </div>
              <div className="event-list">
                {(workflow?.events ?? []).length === 0 && <p className="empty">No agent events yet.</p>}
                {[...(workflow?.events ?? [])].reverse().map((event, index) => (
                  <div className="event" key={`${event.at}-${event.action}-${index}`}>
                    <span className={`event-node ${statusTone(event.status)}`} />
                    <div>
                      <strong>{display(event.action)}</strong>
                      <span>{new Date(event.at).toLocaleString()}</span>
                    </div>
                    <StatusPill value={event.status} />
                  </div>
                ))}
              </div>
            </section>

            <section className={`panel decision-panel ${needsDecision ? "attention" : ""}`}>
              <div className="section-heading">
                <div>
                  <span className="eyebrow">HUMAN GATE</span>
                  <h2>Tolerance decision</h2>
                </div>
                <StatusPill value={needsDecision ? "needs review" : "not requested"} />
              </div>
              {needsDecision ? (
                <>
                  <div className="decision-callout">
                    Requested tolerance <strong>{proposedTolerance} mm</strong>
                    <p>{display(pathValue(workflow?.healing, "question"), "Review the geometric risk before deciding.")}</p>
                  </div>
                  <label>
                    Accountable engineer
                    <input value={engineer} onChange={(event) => setEngineer(event.target.value)} />
                  </label>
                  <label>
                    Engineering justification
                    <textarea value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)} rows={3} />
                  </label>
                  <div className="button-row">
                    <button className="button primary" disabled={Boolean(busy)} onClick={() => submitApproval(true)}>
                      Approve once
                    </button>
                    <button className="button danger" disabled={Boolean(busy)} onClick={() => submitApproval(false)}>
                      Reject
                    </button>
                  </div>
                </>
              ) : (
                <p className="empty">The workflow has no pending tolerance concession.</p>
              )}
            </section>

            <section className="panel readiness-panel">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">READINESS</span>
                  <h2>CFD handoff</h2>
                </div>
                <StatusPill value="gated" />
              </div>
              <div className="readiness-score"><span>CAD evidence</span><strong>{workflow ? "Available" : "Pending"}</strong></div>
              <div className="readiness-score"><span>Health classification</span><strong>{display(healthClassification)}</strong></div>
              <div className="readiness-score"><span>Solver-quality mesh</span><strong>Not implemented</strong></div>
              <p className="boundary-note">
                Volume cells, boundary layers, BC mapping and solver-import validation are required before this can be marked CFD-ready.
              </p>
            </section>
          </aside>
        </main>
      )}

      {tab === "report" && (
        <main className="report-view">
          <section className="report-hero panel">
            <div>
              <span className="eyebrow">WORKFLOW REPORT</span>
              <h1>{workflow ? `Run ${workflow.workflow_id}` : "No workflow selected"}</h1>
              <p>{workflow?.host_source ?? "Start or select a workflow from the Experience tab."}</p>
            </div>
            {workflow && <StatusPill value={display(verificationVerdict, workflow.status)} />}
          </section>
          <section className="report-cards">
            <div className="panel report-card"><span>Phase</span><strong>{display(workflow?.phase)}</strong></div>
            <div className="panel report-card"><span>Health</span><strong>{display(healthClassification)}</strong></div>
            <div className="panel report-card"><span>Active model</span><strong className="path-text">{workflow?.active_model ?? "—"}</strong></div>
            <div className="panel report-card"><span>CFD mesh</span><strong>Not implemented</strong></div>
          </section>
          <section className="panel evidence-panel">
            <h2>Immutable workflow state</h2>
            <pre>{workflow ? JSON.stringify(workflow, null, 2) : "No evidence loaded."}</pre>
          </section>
        </main>
      )}

      {tab === "blueprint" && (
        <main className="blueprint-view panel">
          <span className="eyebrow">REFERENCE ARCHITECTURE</span>
          <h1>Agentic CAD preparation and verification</h1>
          <p className="blueprint-intro">An auditable control plane connects engineering intent, isolated CAD tools and GPU visualization.</p>
          <div className="blueprint-flow">
            <div className="blueprint-node user"><span>01</span><strong>CAE engineer</strong><small>CAD path, intent and decisions</small></div>
            <i>→</i>
            <div className="blueprint-node orchestrator"><span>02</span><strong>NemoClaw orchestrator</strong><small>Policy, routing and audit</small></div>
            <i>→</i>
            <div className="blueprint-node tools"><span>03</span><strong>OpenShell tools</strong><small>OCP health, healing and analysis</small></div>
            <i>→</i>
            <div className="blueprint-node verify"><span>04</span><strong>Independent verification</strong><small>Evidence-based verdict</small></div>
            <i>→</i>
            <div className="blueprint-node output"><span>05</span><strong>Kit-CAE</strong><small>WebRTC visualization and review</small></div>
          </div>
          <div className="blueprint-layers">
            <div><strong>Experience</strong><span>React portal · engineer controls · reports</span></div>
            <div><strong>Control plane</strong><span>FastAPI · workflow state · approval gate</span></div>
            <div><strong>Agent runtime</strong><span>NemoClaw · OpenShell · structured tools</span></div>
            <div><strong>Engineering tools</strong><span>OpenCascade · OpenUSD · Kit-CAE</span></div>
            <div className="future"><strong>Next gated layer</strong><span>Mesher adapter · BC mapping · CFD quality verification</span></div>
          </div>
        </main>
      )}
    </div>
  );
}
