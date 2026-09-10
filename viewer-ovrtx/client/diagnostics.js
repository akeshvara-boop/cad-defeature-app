// Observe peer state without collecting SDP, credentials, or data-channel content.
const events = [], peers = new Map();
let nextPeer = 0;
export function record(kind, value) {
  const clean = JSON.parse(JSON.stringify(value ?? null, (key, item) =>
    /token|credential|password|sdp|authorization|cookie/i.test(key) ? '[redacted]' : item));
  events.push({time:new Date().toISOString(),kind,value:clean});
  if (events.length > 300) events.shift();
  console.info('[OVRTX diagnostic]', kind, clean);
}
const NativePeer = window.RTCPeerConnection;
if (NativePeer) window.RTCPeerConnection = class extends NativePeer {
  constructor(...args) {
    super(...args);
    const id = ++nextPeer;
    peers.set(id,{peer:this,stats:{}});
    if (peers.size > 8) {
      const closed = [...peers].find(([,p])=>p.peer.connectionState === 'closed');
      if (closed) peers.delete(closed[0]);
    }
    record('peer-created',{id});
    for (const name of ['iceconnectionstatechange','connectionstatechange','signalingstatechange'])
      this.addEventListener(name,()=>record(name,{id,ice:this.iceConnectionState,connection:this.connectionState,signaling:this.signalingState}));
    this.addEventListener('icecandidateerror',e=>record('ice-error',{id,code:e.errorCode,text:e.errorText}));
  }
};
export function report() {
  const video=document.getElementById('remote-video');
  return {createdPeers:nextPeer,events,peers:[...peers].map(([id,p])=>({id,ice:p.peer.iceConnectionState,connection:p.peer.connectionState,...p.stats})),
    video:video?{time:video.currentTime,readyState:video.readyState,width:video.videoWidth,height:video.videoHeight,frames:video.getVideoPlaybackQuality?.().totalVideoFrames}:null};
}
let sampling = false;
setInterval(async()=>{
  if(sampling)return;
  sampling=true;
  try {
    for(const p of peers.values()) {
      if(p.peer.connectionState==='closed')continue;
      const stats=await p.peer.getStats();
      const sample={};
      stats.forEach(s=>{
        if(s.type==='transport')sample.dtls=s.dtlsState;
        if(s.type==='candidate-pair' && (s.nominated || s.selected))sample.pair={state:s.state,bytesReceived:s.bytesReceived,bytesSent:s.bytesSent,rtt:s.currentRoundTripTime};
        if(s.type==='inbound-rtp' && (s.kind==='video'||s.mediaType==='video'))sample.video={bytes:s.bytesReceived,packets:s.packetsReceived,lost:s.packetsLost,decoded:s.framesDecoded,received:s.framesReceived,fps:s.framesPerSecond,codecId:s.codecId};
      });
      p.stats=sample;
    }
    const target=document.getElementById('diagnostics');
    if(target)target.textContent=JSON.stringify(report().peers)+' · decoded '+(report().video?.frames??0);
  }catch(e){record('stats-error',String(e));}finally{sampling=false;}
},1000);
window.ovrtxDiagnosticReport=report;
