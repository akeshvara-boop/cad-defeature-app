"""FastAPI entrypoint for the Kit-CAE CAD workflow control plane."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .runtime import NemoClawRuntimeError
from .workflows import WorkflowNotFound, WorkflowService


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


def _web_dist() -> Path:
    configured = os.getenv("CAD_UI_WEB_DIST")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "web" / "dist"


@application.get("/healthz")
def healthz() -> dict:
    return get_service().runner.readiness()


@application.get("/v1/config")
def frontend_config() -> dict:
    """Return non-secret deployment settings consumed by the web workbench."""
    return {
        "product": "Agentic CAD-to-Mesh Workbench",
        "api_version": application.version,
        "kit_stream": {
            "signaling_host": os.getenv("CAD_UI_KIT_SIGNALING_HOST", ""),
            "signaling_port": int(os.getenv("CAD_UI_KIT_SIGNALING_PORT", "49100")),
            "media_port": (
                int(os.environ["CAD_UI_KIT_MEDIA_PORT"])
                if os.getenv("CAD_UI_KIT_MEDIA_PORT")
                else None
            ),
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
