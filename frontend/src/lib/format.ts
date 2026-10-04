import type { TicketStatus } from "./types";

export const money = (n: number, cents = true) =>
  n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: cents ? 2 : 0,
    maximumFractionDigits: cents ? 2 : 0,
  });

export const time = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" }) : "";

export const STATUS_LABEL: Record<TicketStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  waiting_on_approval: "Needs approval",
  waiting_on_vendor: "Waiting on vendor",
  resolved: "Resolved",
};

/** The Boss's saved status, except a ticket whose approvals are all decided reads "Ready to close". */
export function displayStatus(status: TicketStatus, pendingForTicket: number): { label: string; cls: string } {
  if (status === "waiting_on_approval" && pendingForTicket === 0) return { label: "Ready to close", cls: "status-ready" };
  return { label: STATUS_LABEL[status] ?? status, cls: `status-${status}` };
}

export const TICKET_TYPE: Record<string, string> = {
  customer_order: "Customer order",
  rent_notice: "Rent notice",
  price_override: "Discount request",
};

export const REQUEST_KIND: Record<string, string> = {
  invoice: "Vendor invoice",
  rent: "Rent payment",
  purchase_order: "Restock purchase",
};

/** Short, readable form of tool arguments for a chip: get_rent_due(lease_id=1). */
export function toolCall(tool: string, args: Record<string, unknown>): string {
  const skip = new Set(["agent", "author", "reason", "body", "note", "task"]);
  const bits = Object.entries(args ?? {})
    .filter(([k, v]) => !skip.has(k) && v !== null && v !== undefined)
    .map(([k, v]) => {
      const s = typeof v === "string" ? v : JSON.stringify(v);
      return `${k}=${s.length > 22 ? s.slice(0, 21) + "…" : s}`;
    });
  return `${tool}(${bits.join(", ")})`;
}

/** Did a tool result come back as a refusal / not-found? Returns the error text if so. */
export function toolError(content: unknown): string | null {
  if (content && typeof content === "object") {
    const c = content as Record<string, unknown>;
    if (c.ok === false || c.found === false) return String(c.error ?? "refused");
  }
  return null;
}
