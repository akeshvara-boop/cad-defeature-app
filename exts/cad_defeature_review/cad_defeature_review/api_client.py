"""Small standard-library client for the host workflow API.

Kit extensions should not need a second HTTP dependency. Calls are made from
``asyncio.to_thread`` by the extension so the Kit render thread stays free.
"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class WorkflowApiError(RuntimeError):
    """A user-facing API or transport error."""


class WorkflowApiClient:
    def __init__(self, base_url: str, timeout: int = 900) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict:
        return self._request("GET", "/healthz")

    def start(self, source_path: str) -> dict:
        return self._request("POST", "/v1/workflows", {"source_path": source_path})

    def get(self, workflow_id: str) -> dict:
        return self._request("GET", self._workflow_path(workflow_id))

    def heal(self, workflow_id: str, max_auto_tolerance: float) -> dict:
        return self._request(
            "POST", f"{self._workflow_path(workflow_id)}/heal", {"max_auto_tolerance": max_auto_tolerance}
        )

    def approve(self, workflow_id: str, tolerance: float, approved_by: str, note: str, max_auto_tolerance: float) -> dict:
        return self._request(
            "POST",
            f"{self._workflow_path(workflow_id)}/approve",
            {
                "tolerance": tolerance,
                "approved_by": approved_by,
                "note": note,
                "max_auto_tolerance": max_auto_tolerance,
            },
        )

    def reject(self, workflow_id: str, rejected_by: str, note: str) -> dict:
        return self._request(
            "POST", f"{self._workflow_path(workflow_id)}/reject", {"rejected_by": rejected_by, "note": note}
        )

    def analyze(self, workflow_id: str) -> dict:
        return self._request("POST", f"{self._workflow_path(workflow_id)}/analyze")

    def verify(self, workflow_id: str) -> dict:
        return self._request("POST", f"{self._workflow_path(workflow_id)}/verify")

    def highlights(self, workflow_id: str) -> dict:
        return self._request("GET", f"{self._workflow_path(workflow_id)}/highlights")

    @staticmethod
    def _workflow_path(workflow_id: str) -> str:
        return f"/v1/workflows/{quote(workflow_id, safe='')}"

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(detail).get("detail", detail)
            except json.JSONDecodeError:
                pass
            raise WorkflowApiError(f"API {exc.code}: {detail}") from exc
        except URLError as exc:
            raise WorkflowApiError(f"Cannot reach {self.base_url}: {exc.reason}") from exc
