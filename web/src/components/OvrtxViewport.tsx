export function OvrtxViewport({ workflowId, output }: { workflowId?: string; output?: string }) {
  return <div className="panel" style={{ overflow: "hidden", minHeight: 580 }}>
    <div className="section-heading" style={{ padding: 16 }}>
      <div><span className="eyebrow">OUTPUT · OVRTX</span><h2>CAD visual review</h2></div>
      <span className="pill muted">Not CFD validation</span>
    </div>
    {workflowId ? <iframe key={`${workflowId}:${output || ""}`} title="OVRTX selected workflow viewer"
      src={`/ovrtx/?workflow_id=${encodeURIComponent(workflowId)}`}
      allow="autoplay; fullscreen" style={{ width: "100%", height: 620, border: 0 }} />
      : <p style={{ padding: 24 }}>Select a workflow to review its CAD output.</p>}
  </div>;
}
