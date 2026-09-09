# Brev HTTPS signaling

The browser uses the existing authenticated Secure Link for both the portal and
Kit signaling. The SDK's `signalingPath` is `/kit-stream`; its WebSocket request
to `/kit-stream/sign_in` is bridged to `ws://127.0.0.1:49100/sign_in`.
Brev terminates TLS. No second public TCP listener is needed.

Set these variables before launching Uvicorn:

```bash
export CAD_UI_PUBLIC_ORIGIN=https://8000-27deyu6ui.gobrev.dev
export CAD_UI_KIT_SIGNALING_HOST=8000-27deyu6ui.gobrev.dev
export CAD_UI_KIT_SIGNALING_PORT=443
export CAD_UI_KIT_SIGNALING_SECURE=true
export NEMOCLAW_BINARY=/home/ubuntu/.local/bin/nemoclaw
```

The bridge is disabled without `CAD_UI_PUBLIC_ORIGIN` and rejects mismatched
browser origins. The upstream is fixed to local Kit. Browser cookies and
authorization headers aren't forwarded. Origin checks do not replace access
control: retain Brev authentication and restrict direct network access to the API.

The portal health check uses `/v1/healthz` to avoid proxy-reserved `/healthz`.
The stream listener check is `/v1/stream/healthz`.

Media remains a separate UDP/ICE path. A hostname must not be supplied as an
SDK `mediaServer` IP override. The server must advertise a reachable candidate;
verify ICE connection and decoded video frames before declaring the viewer ready.
An HTTPS login redirect or a successful WebSocket handshake alone is insufficient.
