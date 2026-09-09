"""FastAPI entrypoint for the Kit-CAE CAD workflow control plane."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
import socket
from time import monotonic

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .runtime import NemoClawRuntimeError
from .workflows import WorkflowNotFound, WorkflowService
from .stream_proxy import router as stream_router


class StartWorkflowRequest(BaseModel):
    source_path: str


class HealRequest(BaseModel):
    max_auto_tolerance: float = Field(default=0.001, gt=0)


class ApprovalRequest(BaseModel):
    tolerance: float = Field(gt=0)
    approved_by: str = Field(min_length=1)
    note: str = Field(min_length=1)
    max_auto_tolerance: float = Field(default=0.001, gt=0)


class RejectionRequest(BaseModel):
    rejected_by: str = Field(min_length=1)
    note: str = Field(min_length=1)


@lru_cache(maxsize=1)
def get_service() -> WorkflowService:
    return WorkflowService()


application = FastAPI(
    title="Agentic CAD-to-Mesh Workbench API",
    version="0.1.0",
    description=(
        "Host-side control plane for NemoClaw CAD health, healing, read-only feature "
        "analysis, verification and Kit-CAE review. CFD meshing is not yet implemented."
    ),
)


application.include_router(stream_router)


def _stream_host() -> tuple[str, list[str]]:
    """Return a real host value and never leak README placeholders to the UI."""
    raw = os.getenv("CAD_UI_KIT_SIGNALING_HOST", "").strip()
    unresolved = (
        not raw
        or raw.startswith("<")
        or raw.endswith(">")
        or "BREV_PUBLIC" in raw.upper()
        or "PUBLIC_STREAM_HOST" in raw.upper()
    )
    if unresolved:
        warnings = []
        if raw:
            warnings.append(
                "CAD_UI_KIT_SIGNALING_HOST contains an unresolved placeholder; "
                "enter the Brev stream endpoint before connecting."
            )
        return "", warnings
    return raw, []


def _port_from_env(name: str, default: int | None) -> int | None:
    value = os.getenv(name)
    if not value:
        return default
    try:
        port = int(value)
    except ValueError:
        return default
    return port if 1 <= port <= 65535 else default


def _bool_from_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _web_dist() -> Path:
    configured = os.getenv("CAD_UI_WEB_DIST")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "web" / "dist"


@application.get("/healthz")
@application.get("/v1/healthz")
def healthz() -> dict:
    return get_service().runner.readiness()


@application.get("/v1/stream/healthz")
def kit_stream_healthz() -> dict:
    """Probe the Kit signaling listener from the API host.

    This proves process/listener readiness only. Browser reachability, TLS and
    WebRTC media negotiation are deliberately reported as separate boundaries.
    """
    host = os.getenv("CAD_UI_KIT_PROBE_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = _port_from_env("CAD_UI_KIT_PROBE_PORT", 49100) or 49100
    started = monotonic()
    try:
        with socket.create_connection((host, port), timeout=1.5):
            pass
    except OSError as exc:
        return {
            "status": "offline",
            "probe_host": host,
            "signaling_port": port,
            "latency_ms": round((monotonic() - started) * 1000, 1),
            "detail": str(exc),
            "boundary": "kit_listener",
        }
    return {
        "status": "ready",
        "probe_host": host,
        "signaling_port": port,
        "latency_ms": round((monotonic() - started) * 1000, 1),
        "detail": "Kit signaling listener accepted a TCP connection from the API host.",
        "boundary": "kit_listener",
    }


@application.get("/v1/config")
def frontend_config() -> dict:
    """Return non-secret deployment settings consumed by the web workbench."""
    signaling_host, warnings = _stream_host()
    return {
        "product": "Agentic CAD-to-Mesh Workbench",
        "api_version": application.version,
        "kit_stream": {
            "client": "kit-app-streaming",
            "signaling_host": signaling_host,
            "signaling_port": _port_from_env("CAD_UI_KIT_SIGNALING_PORT", 49100),
            "signaling_secure": _bool_from_env("CAD_UI_KIT_SIGNALING_SECURE"),
            "signaling_path": "/kit-stream" if os.getenv("CAD_UI_PUBLIC_ORIGIN") else "",
            "media_port": _port_from_env("CAD_UI_KIT_MEDIA_PORT", None),
            "configuration_warnings": warnings,
        },
        "capabilities": {
            "cad_health": "available",
            "healing": "available",
            "human_tolerance_gate": "required_when_requested",
            "feature_analysis": "report_only",
            "independent_verification": "available",
            "kit_cae_review": "available",
            "cfd_mesh_handoff": "not_implemented",
        },
    }


@application.get("/v1/workflows")
def list_workflows() -> list[dict]:
    return get_service().list()


@application.post("/v1/workflows")
def start_workflow(request: StartWorkflowRequest) -> dict:
    return _call(get_service().create, request.source_path)


@application.get("/v1/workflows/{workflow_id}")
def get_workflow(workflow_id: str) -> dict:
    return _call(get_service().get, workflow_id)


@application.post("/v1/workflows/{workflow_id}/heal")
def heal(workflow_id: str, request: HealRequest) -> dict:
    return _call(get_service().heal, workflow_id, request.max_auto_tolerance)


@application.post("/v1/workflows/{workflow_id}/approve")
def approve(workflow_id: str, request: ApprovalRequest) -> dict:
    return _call(
        get_service().approve,
        workflow_id,
        request.tolerance,
        request.approved_by,
        request.note,
        request.max_auto_tolerance,
    )


@application.post("/v1/workflows/{workflow_id}/reject")
def reject(workflow_id: str, request: RejectionRequest) -> dict:
    return _call(get_service().reject, workflow_id, request.rejected_by, request.note)


@application.post("/v1/workflows/{workflow_id}/analyze")
def analyze(workflow_id: str) -> dict:
    return _call(get_service().analyze, workflow_id)


@application.post("/v1/workflows/{workflow_id}/verify")
def verify(workflow_id: str) -> dict:
    return _call(get_service().verify, workflow_id)


@application.get("/v1/workflows/{workflow_id}/highlights")
def highlights(workflow_id: str) -> dict:
    return _call(get_service().highlights, workflow_id)


def _call(operation, *args):
    try:
        return operation(*args)
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {exc.args[0]}") from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NemoClawRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@application.get("/", include_in_schema=False)
def root():
    """Open the product UI when it has been built; otherwise point to setup docs."""
    if _web_dist().is_dir():
        return RedirectResponse(url="/ui/")
    return {
        "status": "ui_not_built",
        "message": "Build the web client with: cd web && npm install && npm run build",
        "api_docs": "/docs",
    }


if _web_dist().is_dir():
    application.mount("/ui", StaticFiles(directory=_web_dist(), html=True), name="ui")
