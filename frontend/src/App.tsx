import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgentRoster } from "./components/AgentRoster";
import { AgentSummaries } from "./components/AgentSummaries";
import { ApprovalCard } from "./components/ApprovalCard";
import { CashPanel } from "./components/CashPanel";
import { Feed } from "./components/Feed";
import { TicketList } from "./components/TicketList";
import { API_BASE, api } from "./lib/api";
import { deriveLive, latestRun, summaries } from "./lib/derive";
import { displayStatus, money, TICKET_TYPE } from "./lib/format";
import type { AgentEvent, ApprovalRequest, Cash, RunInfo, Ticket } from "./lib/types";

const POLL_RUN_MS = 1200;
const POLL_IDLE_MS = 6000;

type Toast = { text: string; tone: "ok" | "err" | "info"; key: number };

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [today, setToday] = useState("");
  const [cash, setCash] = useState<Cash | null>(null);
  const [pending, setPending] = useState<ApprovalRequest[]>([]);
  const [ledger, setLedger] = useState<ApprovalRequest[]>([]);
  // ?ticket=101 opens the board on that ticket (handy for links and screenshots).
  const [selected, setSelected] = useState<number | null>(() => {
    const t = Number(new URLSearchParams(location.search).get("ticket"));
    return Number.isInteger(t) && t > 0 ? t : null;
  });
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [activeRun, setActiveRun] = useState<RunInfo | null>(null);
  const [offline, setOffline] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [approver, setApprover] = useState(() => localStorage.getItem("cc-approver") ?? "");
  const lastSeq = useRef(0);

  const running = activeRun?.status === "running";
  const say = (text: string, tone: Toast["tone"] = "info") => setToast({ text, tone, key: Date.now() });

  const refresh = useCallback(async () => {
    try {
      const [t, c, p, l] = await Promise.all([api.tickets(), api.cash(), api.approvals("pending"), api.approvals("all")]);
      setTickets(t.tickets);
      setToday(t.today);
      setCash(c);
      setPending(p);
      setLedger(l);
      setOffline(null);
      setSelected((s) => s ?? t.tickets[0]?.id ?? null);
    } catch (e) {
      setOffline((e as Error).message);
    }
  }, []);

  const loadTicketEvents = useCallback(async (id: number) => {
    try {
      setEvents(latestRun(await api.eventsForTicket(id)));
    } catch {
      /* offline banner covers it */
    }
  }, []);

  // First load: board data, and pick up a run that is already going.
  useEffect(() => {
    refresh();
    api
      .health()
      .then((h) => {
        if (h.active_run) {
          lastSeq.current = 0;
          setEvents([]);
          setActiveRun(h.active_run);
          setSelected(h.active_run.ticket_id);
        }
      })
      .catch(() => {});
  }, [refresh]);

  // Idle refresh keeps cash / approvals honest if something changes elsewhere.
  useEffect(() => {
    if (running) return;
    const id = setInterval(refresh, POLL_IDLE_MS);
    return () => clearInterval(id);
  }, [running, refresh]);

  // Show the latest run for whichever ticket is selected.
  useEffect(() => {
    if (selected === null) return;
    if (running && activeRun?.ticket_id === selected) return;
    loadTicketEvents(selected);
  }, [selected, running, activeRun?.ticket_id, loadTicketEvents]);

  // Live polling while the team works.
  useEffect(() => {
    if (!running || !activeRun) return;
    let stop = false;
    const tick = async () => {
      try {
        const fresh = await api.eventsForRun(activeRun.run_id, lastSeq.current);
        if (fresh.length) {
          lastSeq.current = fresh[fresh.length - 1].seq;
          if (activeRun.ticket_id === selected) setEvents((prev) => [...prev, ...fresh]);
        }
        const info = await api.run(activeRun.run_id);
        if (info.status !== "running" && !stop) {
          setActiveRun(info);
          await refresh();
          await loadTicketEvents(info.ticket_id);
          say(
            info.status === "done"
              ? `Team finished ticket ${info.ticket_id} · ${info.result?.delegations ?? 0} delegations`
              : `Run on ticket ${info.ticket_id} stopped: ${info.error ?? "error"}`,
            info.status === "done" ? "ok" : "err",
          );
        }
      } catch (e) {
        setOffline((e as Error).message);
      }
    };
    tick();
    const id = setInterval(tick, POLL_RUN_MS);
    return () => {
      stop = true;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, activeRun?.run_id]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 4200);
    return () => clearTimeout(id);
  }, [toast]);

  async function startRun(id: number) {
    try {
      const info = await api.runTicket(id);
      lastSeq.current = 0;
      setSelected(id);
      setEvents([]);
      setActiveRun(info);
      say(`Boss is picking up ticket ${id}…`);
    } catch (e) {
      say((e as Error).message, "err");
    }
  }

  function needName(): string | null {
    const name = approver.trim();
    if (!name) {
      say("Type your name in “Approving as” first.", "err");
      return null;
    }
    return name;
  }

  async function approve(r: ApprovalRequest) {
    const name = needName();
    if (!name) return;
    try {
      await api.approve(r.id, name);
      say(`Paid ${money(r.amount)} to ${r.payee}`, "ok");
      await refresh();
    } catch (e) {
      say((e as Error).message, "err");
    }
  }

  async function reject(r: ApprovalRequest) {
    const name = needName();
    if (!name) return;
    try {
      await api.reject(r.id, name);
      say(`Rejected request #${r.id}`, "info");
      await refresh();
    } catch (e) {
      say((e as Error).message, "err");
    }
  }

  async function resolve(id: number) {
    const name = needName();
    if (!name) return;
    try {
      await api.resolveTicket(id, name);
      say(`Ticket ${id} resolved`, "ok");
      await refresh();
    } catch (e) {
      say((e as Error).message, "err");
    }
  }

  async function reset() {
    if (!confirm("Reset the shop database to the original values? Agent work, approvals and payments are cleared (the audit trail is kept).")) return;
    try {
      await api.reset();
      setActiveRun(null);
      setEvents([]);
      await refresh();
      say("Database reset to the original values", "info");
    } catch (e) {
      say((e as Error).message, "err");
    }
  }

  const ticket = tickets.find((t) => t.id === selected) ?? null;
  const showingLive = running && activeRun?.ticket_id === selected;
  const live = useMemo(() => deriveLive(events, showingLive), [events, showingLive]);
  const reports = useMemo(() => summaries(events), [events]);
  const ticketPending = pending.filter((p) => p.ticket_id === selected);
  const otherPending = pending.filter((p) => p.ticket_id !== selected);
  const lastResult = activeRun && activeRun.ticket_id === selected && !running ? activeRun.result : null;

  return (
    <div className="app">
      <div className="glow" aria-hidden />
      <header className="topbar">
        <div className="brand">
          <span className="mark">cc</span>
          <div>
            <h1>
              Campus Customs <em>Desk</em>
            </h1>
            <div className="muted small">Five agents, one shop, you hold the checkbook · shop date {today || "—"}</div>
          </div>
        </div>
        <div className="top-actions">
          <label className="approver">
            <span>Approving as</span>
            <input
              value={approver}
              placeholder="your name"
              onChange={(e) => {
                setApprover(e.target.value);
                localStorage.setItem("cc-approver", e.target.value);
              }}
            />
          </label>
          <button className="btn btn-ghost" onClick={reset} disabled={running}>
            Reset shop
          </button>
        </div>
      </header>

      {offline && tickets.length > 0 && (
        <div className="offline">
          {offline} Start it from <code>backend/</code> with <code>uvicorn main:app --reload --port 8000</code> ({API_BASE}).
        </div>
      )}

      <main className="grid">
        <aside className="col-left">
          <TicketList
            tickets={tickets}
            selected={selected}
            activeRun={activeRun}
            pending={pending}
            onSelect={setSelected}
            onRun={startRun}
          />
          <CashPanel cash={cash} ledger={ledger} />
        </aside>

        <section className="col-center panel">
          {offline && tickets.length === 0 ? (
            <div className="stage-offline">
              <h2>The desk is waiting for its backend</h2>
              <p className="muted">
                The board couldn't reach {API_BASE}. Start the FastAPI server in a second terminal and this page
                fills in by itself.
              </p>
              <code>cd backend{"\n"}../.venv/Scripts/uvicorn.exe main:app --reload --port 8000</code>
            </div>
          ) : (
          <>
          {ticket ? (
            <header className="stage-head">
              <div>
                <div className="eyebrow">
                  Ticket {ticket.id} · {TICKET_TYPE[ticket.type] ?? ticket.type}
                </div>
                <h2>
                  {ticket.requester} <span className="muted">— {ticket.subject}</span>
                </h2>
                <div className="muted small">{ticket.notes}</div>
              </div>
              <div className="stage-actions">
                <span className={`pill big ${displayStatus(ticket.status, ticketPending.length).cls}`}>
                  {displayStatus(ticket.status, ticketPending.length).label}
                </span>
                {ticket.status !== "resolved" && !showingLive && ticketPending.length === 0 && events.length > 0 && (
                  <button className="btn btn-ghost" onClick={() => resolve(ticket.id)}>
                    Mark resolved ✓
                  </button>
                )}
              </div>
            </header>
          ) : (
            <header className="stage-head">
              <h2>Pick a ticket</h2>
            </header>
          )}

          <AgentRoster live={live} />

          {lastResult && (
            <div className="run-stats mono">
              {lastResult.delegations} delegations · {lastResult.model_requests} model calls ·{" "}
              {lastResult.tokens_used.toLocaleString()} tokens
            </div>
          )}

          <Feed
            events={events}
            running={showingLive}
            empty={
              running && !showingLive
                ? `The team is busy on ticket ${activeRun?.ticket_id}.`
                : "No run yet for this ticket. Press “Run team ▸” to put the agents on it."
            }
          />
          </>
          )}
        </section>

        <aside className="col-right">
          <section className="panel">
            <header className="panel-head">
              <h2>Approvals</h2>
              <span className="muted">{pending.length} waiting</span>
            </header>
            {pending.length === 0 && <div className="muted small">Nothing to approve. Agents only ask — you decide.</div>}
            {[...ticketPending, ...otherPending].map((r) => (
              <ApprovalCard
                key={r.id}
                request={r}
                balance={cash?.balance ?? null}
                locked={running ? "Approvals unlock when the current run finishes." : null}
                onApprove={approve}
                onReject={reject}
              />
            ))}
          </section>
          <section className="panel">
            <header className="panel-head">
              <h2>What each agent did</h2>
              <span className="muted">{ticket ? `ticket ${ticket.id}` : ""}</span>
            </header>
            <AgentSummaries items={reports} />
          </section>
        </aside>
      </main>

      {toast && (
        <div className={`toast toast-${toast.tone}`} key={toast.key}>
          {toast.text}
        </div>
      )}
    </div>
  );
}
