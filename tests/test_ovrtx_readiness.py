import importlib
import io
import json

module = importlib.import_module("cad_defeature.api.ovrtx_readiness")

def health(monkeypatch, value):
    monkeypatch.setattr(module, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(value).encode()))
    monkeypatch.setenv("CAD_UI_OVRTX_SIGNALING_HOST", "viewer.example.test")
    monkeypatch.setenv("CAD_UI_OVRTX_SIGNALING_PORT", "443")
    monkeypatch.setenv("CAD_UI_OVRTX_ROUTE_VERIFIED", "true")

def test_offline_is_closed(monkeypatch):
    def offline(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(module, "urlopen", offline)
    assert module.ovrtx_readiness()["ready"] is False

def test_no_frames_is_closed(monkeypatch):
    health(monkeypatch, {"status": "ready", "rendered_frames": 0})
    assert module.ovrtx_readiness()["ready"] is False

def test_unverified_route_is_closed(monkeypatch):
    health(monkeypatch, {"status": "ready", "rendered_frames": 3})
    monkeypatch.delenv("CAD_UI_OVRTX_ROUTE_VERIFIED")
    assert module.ovrtx_readiness()["host"] is None

def test_verified_ready_route(monkeypatch):
    health(monkeypatch, {"status": "ready", "rendered_frames": 3})
    assert module.ovrtx_readiness()["ready"] is True
    assert module.ovrtx_readiness()["port"] == 443

def test_malformed_health_is_closed(monkeypatch):
    health(monkeypatch, [])
    assert module.ovrtx_readiness()["ready"] is False

def test_url_in_host_is_closed(monkeypatch):
    health(monkeypatch, {"status": "ready", "rendered_frames": 3})
    monkeypatch.setenv("CAD_UI_OVRTX_SIGNALING_HOST", "https://viewer.example.test/path")
    assert module.ovrtx_readiness()["ready"] is False

def test_startup_503_explains_phase(monkeypatch):
    from urllib.error import HTTPError
    def starting(*a, **k):
        payload = io.BytesIO(b'{"status":"starting","phase":"attaching_stage","rendered_frames":0}')
        raise HTTPError("http://127.0.0.1:8081/healthz", 503, "starting", {}, payload)
    monkeypatch.setattr(module, "urlopen", starting)
    result = module.ovrtx_readiness()
    assert result["ready"] is False
    assert result["phase"] == "attaching_stage"
    assert "attaching stage" in result["reason"]

def test_malformed_phase_stays_closed(monkeypatch):
    health(monkeypatch, {"status": "starting", "phase": [], "rendered_frames": 0})
    assert module.ovrtx_readiness()["ready"] is False
