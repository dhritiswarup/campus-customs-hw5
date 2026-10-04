import { useState } from "react";
import { agentMeta } from "../lib/agents";
import { money, REQUEST_KIND } from "../lib/format";
import type { ApprovalRequest } from "../lib/types";

interface Props {
  request: ApprovalRequest;
  balance: number | null;
  locked: string | null; // reason the buttons are disabled, if any
  onApprove: (r: ApprovalRequest) => Promise<void>;
  onReject: (r: ApprovalRequest) => Promise<void>;
}

export function ApprovalCard({ request: r, balance, locked, onApprove, onReject }: Props) {
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const who = agentMeta(r.requested_by);
  const after = balance === null ? null : balance - r.amount;
  const overdraw = after !== null && after < 0;

  async function act(kind: "approve" | "reject") {
    setBusy(kind);
    try {
      await (kind === "approve" ? onApprove(r) : onReject(r));
    } finally {
      setBusy(null);
    }
  }

  return (
    <article className="approval">
      <div className="approval-flag">Your approval needed</div>
      <div className="approval-kind">
        {REQUEST_KIND[r.kind] ?? r.kind} · request #{r.id}
        {r.ticket_id ? ` · ticket ${r.ticket_id}` : ""}
      </div>
      <div className="approval-amount">{money(r.amount)}</div>
      <div className="approval-payee">to {r.payee}</div>
      <p className="approval-reason">{r.reason}</p>
      <div className="approval-meta">
        <span className="who" style={{ color: who.color }}>
          Requested by {who.label}
        </span>
        {after !== null && (
          <span className={overdraw ? "overdraw" : ""}>
            Checking after: {money(after)}
            {overdraw && " — would overdraw"}
          </span>
        )}
      </div>
      <div className="approval-actions">
        <button className="btn btn-approve" disabled={!!busy || !!locked || overdraw} onClick={() => act("approve")}>
          {busy === "approve" ? "Paying…" : `Approve ${money(r.amount, false)}`}
        </button>
        <button className="btn btn-reject" disabled={!!busy || !!locked} onClick={() => act("reject")}>
          {busy === "reject" ? "Rejecting…" : "Reject"}
        </button>
      </div>
      {locked && <div className="approval-locked">{locked}</div>}
    </article>
  );
}
