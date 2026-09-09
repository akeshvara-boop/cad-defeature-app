# Brev UDP gateway media override

Client 5.18.2 supports `mediaServer` and `mediaPort` independently of
the WSS signaling endpoint. Its implementation rewrites remote ICE candidate
address/port using these values. This is a client override, not a Kit bind change.

For the cad-defeature-demo gateway mapping observed on 2026-09-09:

```bash
export CAD_UI_KIT_MEDIA_HOST=global.prd.ga.run.brev.nvidia.com
export CAD_UI_KIT_MEDIA_PORT=15865
```

Set these on the host API process and restart that process. Rebuild the web
frontend after updating the source. Leave Kit's internal UDP port at 49100,
and retain the authenticated WSS bridge on port 443 with `/kit-stream`.
These mapping values are deployment-specific and may change if recreated.

The API exposes the override in `/v1/config`. The viewer shows it as
`Media override`, and supplies both values to the streaming client.
Without an override, the original Kit ICE candidate remains in use.

Verification requires a fresh browser connection: check that the remote ICE
candidate uses gateway port 15865, then confirm a selected pair, increasing
received bytes, and decoded frames. Capture UDP 49100 on the instance while
connecting to verify gateway delivery. TCP listener readiness does not prove
media reachability. Hostname resolution, gateway UDP forwarding, and return-path
compatibility still require the live browser test; do not mark streaming ready
based on configuration or build tests alone.
