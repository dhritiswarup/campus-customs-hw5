import { displayStatus, TICKET_TYPE } from "../lib/format";
import type { ApprovalRequest, RunInfo, Ticket } from "../lib/types";

interface Props {
  tickets: Ticket[];
  selected: number | null;
  activeRun: RunInfo | null;
  pending: ApprovalRequest[];
  onSelect: (id: number) => void;
  onRun: (id: number) => void;
}

function detail(t: Ticket): string {
  if (t.sku) return `${t.qty} × ${t.sku} · ${t.size}`;
  if (t.lease_id) return `Lease #${t.lease_id}`;
  return t.notes ?? "";
}

export function TicketList({ tickets, selected, activeRun, pending, onSelect, onRun }: Props) {
  return (
    <section className="panel tickets">
      <header className="panel-head">
        <h2>Tickets</h2>
        <span className="muted">{tickets.filter((t) => t.is_open).length} open</span>
      </header>
      <ul>
        {tickets.length === 0 && [1, 2, 3].map((i) => <li key={i} className="skeleton" aria-hidden />)}
        {tickets.map((t) => {
          const running = activeRun?.status === "running" && activeRun.ticket_id === t.id;
          const waiting = pending.filter((p) => p.ticket_id === t.id).length;
          return (
            <li
              key={t.id}
              className={`ticket ${selected === t.id ? "is-selected" : ""} ${running ? "is-running" : ""} ${
                t.status === "resolved" ? "is-resolved" : ""
              }`}
              onClick={() => onSelect(t.id)}
            >
              <div className="ticket-top">
                <span className="ticket-id">{t.id}</span>
                <span className={`pill ${displayStatus(t.status, waiting).cls}`}>{displayStatus(t.status, waiting).label}</span>
              </div>
              <div className="ticket-type">{TICKET_TYPE[t.type] ?? t.type}</div>
              <div className="ticket-who">{t.requester}</div>
              <div className="ticket-what">{t.subject}</div>
              <div className="ticket-detail mono">{detail(t)}</div>
              <div className="ticket-foot">
                {waiting > 0 && <span className="needs">{waiting} awaiting you</span>}
                {t.status === "resolved" ? (
                  <div className="stamp">Resolved</div>
                ) : (
                <button
                  className="btn btn-run"
                  disabled={activeRun?.status === "running"}
                  onClick={(ev) => {
                    ev.stopPropagation();
                    onRun(t.id);
                  }}
                >
                  {running ? (
                    <>
                      <span className="spinner" /> Team working…
                    </>
                  ) : (
                    "Run team ▸"
                  )}
                </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
