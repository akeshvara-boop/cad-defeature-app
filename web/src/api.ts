import type { FrontendConfig, StreamHealth, WorkflowState } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof body.detail === "string" ? body.detail : response.statusText;
    throw new Error(message || `Request failed with ${response.status}`);
  }
  return body as T;
}

export const api = {
  health: () => request<Record<string, unknown>>("/healthz"),
  config: () => request<FrontendConfig>("/v1/config"),
  streamHealth: () => request<StreamHealth>("/v1/stream/healthz"),
  workflows: () => request<WorkflowState[]>("/v1/workflows"),
  workflow: (id: string) => request<WorkflowState>(`/v1/workflows/${id}`),
  start: (sourcePath: string) =>
    request<WorkflowState>("/v1/workflows", {
      method: "POST",
      body: JSON.stringify({ source_path: sourcePath })
    }),
  heal: (id: string, maxAutoTolerance: number) =>
    request<WorkflowState>(`/v1/workflows/${id}/heal`, {
      method: "POST",
      body: JSON.stringify({ max_auto_tolerance: maxAutoTolerance })
    }),
  approve: (
    id: string,
    tolerance: number,
    approvedBy: string,
    note: string,
    maxAutoTolerance: number
  ) =>
    request<WorkflowState>(`/v1/workflows/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({
        tolerance,
        approved_by: approvedBy,
        note,
        max_auto_tolerance: maxAutoTolerance
      })
    }),
  reject: (id: string, rejectedBy: string, note: string) =>
    request<WorkflowState>(`/v1/workflows/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ rejected_by: rejectedBy, note })
    }),
  analyze: (id: string) =>
    request<WorkflowState>(`/v1/workflows/${id}/analyze`, { method: "POST" }),
  verify: (id: string) =>
    request<WorkflowState>(`/v1/workflows/${id}/verify`, { method: "POST" })
};
