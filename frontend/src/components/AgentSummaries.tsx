import { agentMeta } from "../lib/agents";
import type { AgentSummary } from "../lib/derive";

export function AgentSummaries({ items }: { items: AgentSummary[] }) {
  if (!items.length) {
    return <div className="muted small">When the team finishes, each agent's short report shows up here.</div>;
  }
  return (
    <div className="summaries">
      {items.map((s, i) => {
        const a = agentMeta(s.agent);
        const Icon = a.icon;
        const r = s.report;
        const done = r.actions_taken ?? [];
        const human = r.needs_human ?? (r.approvals_needed ?? []);
        return (
          <article key={i} className="summary" style={{ "--agent": a.color } as React.CSSProperties}>
            <header>
              <span className="avatar">
                <Icon size={15} />
              </span>
              <b>{a.label}</b>
              {!r.ok && <span className="pill status-error">error</span>}
            </header>
            <p>{r.summary ?? r.error}</p>
            {done.length > 0 && (
              <ul>
                {done.slice(0, 4).map((d, j) => (
                  <li key={j}>{d}</li>
                ))}
              </ul>
            )}
            {human.length > 0 && (
              <div className="summary-human">
                <span>Needs you:</span> {human.slice(0, 2).join(" · ")}
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
