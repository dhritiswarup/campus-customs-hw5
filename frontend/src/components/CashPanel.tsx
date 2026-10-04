import { useEffect, useRef, useState } from "react";
import { money, REQUEST_KIND, time } from "../lib/format";
import type { ApprovalRequest, Cash } from "../lib/types";
import { useAnimatedNumber } from "../lib/useAnimatedNumber";

export function CashPanel({ cash, ledger }: { cash: Cash | null; ledger: ApprovalRequest[] }) {
  const shown = useAnimatedNumber(cash?.balance ?? null);
  const prev = useRef<number | null>(null);
  const [delta, setDelta] = useState<{ amount: number; key: number } | null>(null);

  useEffect(() => {
    if (cash === null) return;
    if (prev.current !== null && cash.balance !== prev.current) {
      setDelta({ amount: cash.balance - prev.current, key: Date.now() });
    }
    prev.current = cash.balance;
  }, [cash]);

  const byTicket = new Map<string, ApprovalRequest[]>();
  for (const p of ledger.filter((l) => l.status === "paid")) {
    const k = p.ticket_id ? `Ticket ${p.ticket_id}` : "No ticket";
    byTicket.set(k, [...(byTicket.get(k) ?? []), p]);
  }

  return (
    <section className="panel cash">
      <header className="panel-head">
        <h2>Checking</h2>
        <span className="muted">as of {cash?.today ?? "—"}</span>
      </header>
      <div className={`balance ${delta ? "flash" : ""}`} key={delta?.key}>
        {shown === null ? "—" : money(shown)}
        {delta && (
          <span className={`delta ${delta.amount < 0 ? "down" : "up"}`}>
            {delta.amount < 0 ? "−" : "+"}
            {money(Math.abs(delta.amount), false)}
          </span>
        )}
      </div>
      {cash && (
        <div className="cash-sub">
          <div>
            <span className="muted">Pending approvals</span>
            <b>{money(cash.pending_total, false)}</b>
          </div>
          <div>
            <span className="muted">Left if all approved</span>
            <b className={cash.available_after_pending < 0 ? "neg" : ""}>{money(cash.available_after_pending, false)}</b>
          </div>
        </div>
      )}
      <div className="ledger">
        <h3>Ledger</h3>
        {byTicket.size === 0 && <div className="muted small">No payments yet. Approved payments land here.</div>}
        {[...byTicket.entries()].map(([ticket, rows]) => (
          <div key={ticket} className="ledger-group">
            <div className="ledger-ticket">{ticket}</div>
            {rows.map((r) => (
              <div key={r.id} className="ledger-row">
                <span>
                  {REQUEST_KIND[r.kind] ?? r.kind} · {r.payee}
                  <em>
                    approved by {r.decided_by} · {time(r.decided_at)}
                  </em>
                </span>
                <b className="neg">−{money(r.amount, false)}</b>
              </div>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
