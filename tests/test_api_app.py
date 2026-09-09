from __future__ import annotations

from fastapi.responses import RedirectResponse

from cad_defeature.api.app import application, frontend_config, root


def test_openapi_exposes_frontend_configuration() -> None:
    schema = application.openapi()
    assert "/v1/config" in schema["paths"]
    assert schema["info"]["title"] == "Agentic CAD-to-Mesh Workbench API"


def test_frontend_config_reports_capability_boundaries(monkeypatch) -> None:
    monkeypatch.setenv("CAD_UI_KIT_SIGNALING_HOST", "kit.example.test")
    monkeypatch.setenv("CAD_UI_KIT_SIGNALING_PORT", "49101")
    monkeypatch.setenv("CAD_UI_KIT_MEDIA_PORT", "47999")

    config = frontend_config()

    assert config["kit_stream"] == {
        "signaling_host": "kit.example.test",
        "signaling_port": 49101,
        "media_port": 47999,
    }
    assert config["capabilities"]["feature_analysis"] == "report_only"
    assert config["capabilities"]["cfd_mesh_handoff"] == "not_implemented"


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
