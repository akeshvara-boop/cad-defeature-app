// Install before the streaming SDK. Only state/counts are retained, never SDP
// credentials, cookies or local candidate addresses.
const peers = new Set<RTCPeerConnection>();
let lastError = "none";
let created = 0;
const NativePeer = window.RTCPeerConnection;
if (NativePeer) {
  window.RTCPeerConnection = new Proxy(NativePeer, {
    construct(target, args) {
      const peer = Reflect.construct(target, args) as RTCPeerConnection;
      peers.add(peer);
      created += 1;
      peer.addEventListener("icecandidateerror", (event) => {
        const error = event as RTCPeerConnectionIceErrorEvent;
        lastError = `${error.errorCode}: ${error.errorText}`;
      });
      peer.addEventListener("connectionstatechange", () => {
        if (peer.connectionState === "closed") peers.delete(peer);
      });
      return peer;
    }
  });
}

export async function iceSummary(): Promise<string> {
  const active = [...peers].filter((p) => p.signalingState !== "closed");
  const peer = active[active.length - 1];
  if (!peer) return `ICE: no peer · created ${created} · last error ${lastError}`;
  let received = 0;
  let pair = "none";
  let remote = "none";
  try {
    const stats = await peer.getStats();
    stats.forEach((entry) => {
      if (entry.type === "remote-candidate") {
        remote = `${entry.address ?? entry.ip ?? "hidden"}:${entry.port ?? "?"}/${entry.protocol ?? "?"}`;
      }
      if (entry.type === "candidate-pair" && (entry.nominated || entry.selected)) {
        pair = `${entry.state}`;
        received += Number(entry.bytesReceived ?? 0);
      }
    });
  } catch { /* Peer may close while stats are being collected. */ }
  return `ICE: ${peer.iceConnectionState} · signaling ${peer.signalingState} · peers ${active.length} (created ${created}) · pair ${pair} · remote ${remote} · received ${received} bytes · error ${lastError}`;
}
