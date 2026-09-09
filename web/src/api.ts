import type { FrontendConfig, StreamHealth, WorkflowState } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const readOnly = (init?.method ?? "GET").toUpperCase() === "GET";
  const attempts = readOnly ? 3 : 1;
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(path, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
      });
      if (readOnly && [502, 503, 504].includes(response.status) && attempt < attempts - 1) {
        await response.body?.cancel();
        await new Promise((resolve) => window.setTimeout(resolve, 750 * (attempt + 1)));
        continue;
      }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof body.detail === "string" ? body.detail : response.statusText;
    throw new Error(`${path}: ${message || `Request failed with ${response.status}`}`);
  }
  return body as T;
    } catch (error) {
      lastError = error;
      // Only transport failures on reads may be replayed. Never retry writes.
      if (!(error instanceof TypeError) || attempt === attempts - 1) throw error;
      await new Promise((resolve) => window.setTimeout(resolve, 750 * (attempt + 1)));
    }
  }
  throw lastError;
}

export const api = {
  health: () => request<Record<string, unknown>>("/v1/healthz"),
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
