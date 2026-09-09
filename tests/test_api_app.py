from __future__ import annotations

from fastapi.responses import RedirectResponse

from cad_defeature.api.app import (
    application,
    frontend_config,
    kit_stream_healthz,
    root,
)


def test_openapi_exposes_frontend_configuration() -> None:
    schema = application.openapi()
    assert "/v1/config" in schema["paths"]
    assert "/v1/stream/healthz" in schema["paths"]
    assert schema["info"]["title"] == "Agentic CAD-to-Mesh Workbench API"


def test_frontend_config_reports_capability_boundaries(monkeypatch) -> None:
    monkeypatch.setenv("CAD_UI_KIT_SIGNALING_HOST", "kit.example.test")
    monkeypatch.setenv("CAD_UI_KIT_SIGNALING_PORT", "49101")
    monkeypatch.setenv("CAD_UI_KIT_SIGNALING_SECURE", "true")
    monkeypatch.setenv("CAD_UI_KIT_MEDIA_PORT", "47999")

    config = frontend_config()

    assert config["kit_stream"] == {
        "client": "kit-app-streaming",
        "signaling_host": "kit.example.test",
        "signaling_port": 49101,
        "signaling_secure": True,
        "signaling_path": "",
        "media_port": 47999,
        "configuration_warnings": [],
    }
    assert config["capabilities"]["feature_analysis"] == "report_only"
    assert config["capabilities"]["cfd_mesh_handoff"] == "not_implemented"


def test_frontend_config_rejects_placeholder_host(monkeypatch) -> None:
    monkeypatch.setenv("CAD_UI_KIT_SIGNALING_HOST", "<BREV_PUBLIC_STREAM_HOST>")

    stream = frontend_config()["kit_stream"]

    assert stream["signaling_host"] == ""
    assert "unresolved placeholder" in stream["configuration_warnings"][0]


def test_stream_health_reports_ready_listener(monkeypatch) -> None:
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    observed = {}

    def connect(address, timeout):
        observed.update(address=address, timeout=timeout)
        return Connection()

    monkeypatch.setattr("cad_defeature.api.app.socket.create_connection", connect)
    monkeypatch.setenv("CAD_UI_KIT_PROBE_HOST", "127.0.0.1")
    monkeypatch.setenv("CAD_UI_KIT_PROBE_PORT", "49100")

    result = kit_stream_healthz()

    assert result["status"] == "ready"
    assert result["boundary"] == "kit_listener"
    assert observed["address"] == ("127.0.0.1", 49100)


def test_root_explains_how_to_build_missing_ui(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CAD_UI_WEB_DIST", str(tmp_path / "missing"))
    response = root()

    assert response["status"] == "ui_not_built"
    assert response["api_docs"] == "/docs"


def test_root_redirects_to_built_ui(monkeypatch, tmp_path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    monkeypatch.setenv("CAD_UI_WEB_DIST", str(dist))

    response = root()

    assert isinstance(response, RedirectResponse)
    assert response.headers["location"] == "/ui/"
