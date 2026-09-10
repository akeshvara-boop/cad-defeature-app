"""Fail-closed readiness for the isolated viewer, independent of Kit."""
import json
import os
from urllib.request import urlopen
from urllib.error import HTTPError

from fastapi import APIRouter

router = APIRouter()

@router.get("/v1/ovrtx/readiness")
def ovrtx_readiness(workflow_id: str = ''):
    result = {"ready": False, "host": None, "port": None,
              "reason": "OVRTX renderer is not ready. No connection will be attempted."}
    # Fixed loopback target: never probe a browser-supplied host or URL.
    try:
        try:
            response = urlopen("http://127.0.0.1:8081/healthz", timeout=1)
        except HTTPError as error:
            if error.code != 503:
                raise
            response = error
        with response:
            health = json.loads(response.read(16385))
        if isinstance(health, dict):
            phase = health.get("phase")
            if isinstance(phase, str) and phase in {"initializing", "creating_renderer", "creating_stage", "attaching_stage", "populating_stage", "first_frame", "starting_stream", "rendering", "loading_asset"}:
                result["phase"] = phase
                result["reason"] = f"OVRTX is not ready: {phase.replace('_', ' ')}. Connect remains disabled."
        if not isinstance(health, dict) or health.get("status") != "ready" or health.get("rendered_frames", 0) < 1:
            return result
        result.update(workflow_id=health.get('workflow_id'), asset_id=health.get('asset_id'),
                      rendered_frames=health.get('rendered_frames'), client_connected=health.get('client_connected'))
        if workflow_id and health.get('workflow_id') != workflow_id:
            result['reason'] = 'Load the selected workflow CAD output before connecting.'
            return result
    except (OSError, ValueError, TypeError):
        return result
    host = os.getenv("CAD_UI_OVRTX_SIGNALING_HOST", "").strip()
    try:
        port = int(os.getenv("CAD_UI_OVRTX_SIGNALING_PORT", "0"))
    except ValueError:
        port = 0
    verified = (os.getenv("CAD_UI_OVRTX_ROUTE_VERIFIED", "").lower() == "true" or
                os.getenv("CAD_UI_OVRTX_ROUTE_CONFIGURED", "").lower() == "true")
    if not verified or not host or any(c in host for c in "/<> \\\n\r") or not 1 <= port <= 65535:
        result["reason"] = "Renderer has frames, but its public signaling/media route is not verified."
        return result
    result.update(ready=True, host=host, port=port, reason="Renderer and configured route are ready for browser validation.")
    result.update(signaling_path='/ovrtx-stream', secure=True,
                  media_host=os.getenv('CAD_UI_OVRTX_MEDIA_HOST',''),
                  media_port=int(os.getenv('CAD_UI_OVRTX_MEDIA_PORT','48098')))
    return result
