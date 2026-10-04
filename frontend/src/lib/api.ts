import type { AgentEvent, ApprovalRequest, Cash, Health, RunInfo, TicketsResponse } from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(`Can't reach the backend at ${API_BASE}.`);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(typeof body.detail === "string" ? body.detail : `${res.status} ${res.statusText}`);
  return body as T;
}

const post = <T>(path: string, data?: unknown) =>
  call<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

export const api = {
  health: () => call<Health>("/api/health"),
  tickets: () => call<TicketsResponse>("/api/tickets"),
  runTicket: (id: number) => post<RunInfo>(`/api/tickets/${id}/run`),
  resolveTicket: (id: number, resolved_by: string) => post(`/api/tickets/${id}/resolve`, { resolved_by }),
  run: (runId: string) => call<RunInfo>(`/api/runs/${runId}`),
  eventsForRun: (runId: string, afterSeq = 0) =>
    call<AgentEvent[]>(`/api/events?run_id=${runId}&after_seq=${afterSeq}&limit=1000`),
  eventsForTicket: (ticketId: number) => call<AgentEvent[]>(`/api/events?ticket_id=${ticketId}&limit=1000`),
  approvals: (status: "pending" | "all" = "pending") =>
    call<{ requests: ApprovalRequest[] }>(`/api/approvals?status=${status}`).then((r) => r.requests),
  approve: (id: number, approved_by: string) => post(`/api/approvals/${id}/approve`, { approved_by }),
  reject: (id: number, rejected_by: string, note = "") => post(`/api/approvals/${id}/reject`, { rejected_by, note }),
  cash: () => call<Cash>("/api/cash"),
  reset: () => post("/api/reset"),
};
