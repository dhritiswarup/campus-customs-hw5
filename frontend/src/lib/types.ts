// Shapes returned by the FastAPI backend (backend/main.py).

export type AgentName = "boss" | "inventory" | "accounting" | "facilities" | "customer_service";

export type TicketStatus = "open" | "in_progress" | "waiting_on_approval" | "waiting_on_vendor" | "resolved";

export interface Ticket {
  id: number;
  type: string;
  requester: string;
  subject: string;
  sku: string | null;
  size: string | null;
  qty: number | null;
  lease_id: number | null;
  invoice_id: number | null;
  status: TicketStatus;
  notes: string | null;
  created_at: string;
  is_open: boolean;
}

export interface TicketsResponse {
  today: string;
  tickets: Ticket[];
}

export interface ApprovalRequest {
  id: number;
  kind: "invoice" | "rent" | "purchase_order";
  ref_id: number;
  ticket_id: number | null;
  amount: number;
  payee: string;
  reason: string;
  requested_by: AgentName;
  status: "pending" | "paid" | "rejected";
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  payment_id: number | null;
}

export interface Cash {
  account: string;
  balance: number;
  as_of: string;
  today: string;
  pending_total: number;
  available_after_pending: number;
}

export interface AgentReport {
  ok: boolean;
  agent: AgentName;
  summary?: string;
  error?: string;
  facts?: string[];
  actions_taken?: string[];
  needs_human?: string[];
  blocked_by?: string[];
  next_steps?: string[];
  // Boss report
  tickets?: { ticket_id: number; status: TicketStatus; what_was_done: string; agents: AgentName[]; waiting_on: string }[];
  approvals_needed?: string[];
  cash_note?: string;
  drafts_to_review?: number[];
  risks?: string[];
}

export interface AgentEvent {
  run_id: string;
  seq: number;
  logged_at: string;
  kind: "run_start" | "agent_start" | "agent_step" | "delegation" | "agent_end" | "run_end";
  agent: AgentName | null;
  chain: AgentName[];
  ticket_id: number | null;
  summary: string;
  said: string | null;
  tools: { tool: string; args: Record<string, unknown> }[];
  tool_results: { tool: string; content: unknown }[];
  delegated_to: AgentName | null;
  report: AgentReport | null;
}

export interface RunInfo {
  run_id: string;
  ticket_id: number;
  status: "running" | "done" | "failed";
  started_at: string;
  finished_at: string | null;
  result: { ok: boolean; delegations: number; tokens_used: number; model_requests: number; report: AgentReport } | null;
  error: string | null;
}

export interface Health {
  ok: boolean;
  database: string;
  active_run: RunInfo | null;
}
