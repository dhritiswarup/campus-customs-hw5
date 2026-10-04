import { useEffect, useRef, useState } from "react";
import { agentMeta } from "../lib/agents";
import { time, toolCall, toolError } from "../lib/format";
import type { AgentEvent } from "../lib/types";

function Avatar({ agent }: { agent: string | null }) {
  const a = agentMeta(agent);
  const Icon = a.icon;
  return (
    <span className="avatar" style={{ "--agent": a.color } as React.CSSProperties} title={a.label}>
      <Icon size={16} />
    </span>
  );
}

/** Speech bubble; long raw model text collapses to a few lines until clicked. */
function Bubble({ text, className = "" }: { text: string | null; className?: string }) {
  const long = (text ?? "").length > 360;
  const [open, setOpen] = useState(false);
  return (
    <>
      <div className={`bubble ${className} ${long && !open ? "clamped" : ""}`} onClick={() => long && setOpen(!open)}>
        {text}
      </div>
      {long && (
        <button className="bubble-more" onClick={() => setOpen(!open)}>
          {open ? "Show less" : "Show full message"}
        </button>
      )}
    </>
  );
}

function Row({ e }: { e: AgentEvent }) {
  const a = agentMeta(e.agent);
  const style = { "--agent": a.color } as React.CSSProperties;

  if (e.kind === "run_start") {
    return <div className="feed-divider">Team run started · {time(e.logged_at)}</div>;
  }
  if (e.kind === "run_end") {
    return <div className="feed-divider end">Run complete · {time(e.logged_at)}</div>;
  }
  if (e.kind === "agent_start") {
    if (e.chain.length) return null; // the delegation bubble already shows the task
    return (
      <div className="feed-row" style={style}>
        <Avatar agent={e.agent} />
        <div className="feed-body">
          <div className="feed-meta">
            <b>{a.label}</b> picks up the ticket <span>{time(e.logged_at)}</span>
          </div>
        </div>
      </div>
    );
  }
  if (e.kind === "delegation") {
    const to = agentMeta(e.delegated_to);
    const refused = e.summary.includes("REFUSED");
    return (
      <div className="feed-row" style={style}>
        <Avatar agent={e.agent} />
        <div className="feed-body">
          <div className="feed-meta">
            <b>{a.label}</b> → <b style={{ color: to.color }}>{to.label}</b> <span>{time(e.logged_at)}</span>
          </div>
          <Bubble text={e.said} className={refused ? "bubble-refused" : ""} />
          {refused && <div className="chip chip-err mono">{e.summary.split("REFUSED: ")[1]}</div>}
        </div>
      </div>
    );
  }
  if (e.kind === "agent_end") {
    return (
      <div className="feed-row" style={style}>
        <Avatar agent={e.agent} />
        <div className="feed-body">
          <div className="feed-meta">
            <b>{a.label}</b> reports back <span>{time(e.logged_at)}</span>
          </div>
          <Bubble text={e.said} className={`bubble-report ${e.report && !e.report.ok ? "bubble-refused" : ""}`} />
        </div>
      </div>
    );
  }
  // agent_step: speech, tool calls, or tool results
  return (
    <div className="feed-row compact" style={style}>
      <Avatar agent={e.agent} />
      <div className="feed-body">
        {e.said && <Bubble text={e.said} />}
        {e.tools.length > 0 && (
          <div className="chips">
            {e.tools.map((t, i) => (
              <span key={i} className="chip mono" title={JSON.stringify(t.args, null, 2)}>
                {toolCall(t.tool, t.args)}
              </span>
            ))}
          </div>
        )}
        {e.tool_results.length > 0 && (
          <div className="chips">
            {e.tool_results.map((r, i) => {
              const err = toolError(r.content);
              return (
                <span key={i} className={`chip chip-result mono ${err ? "chip-err" : ""}`} title={JSON.stringify(r.content, null, 2)}>
                  {err ? `✗ ${r.tool}: ${err}` : `✓ ${r.tool}`}
                </span>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export function Feed({ events, running, empty }: { events: AgentEvent[]; running: boolean; empty: string }) {
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [events.length]);

  return (
    <div
      className="feed"
      ref={box}
      onScroll={(ev) => {
        const el = ev.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      }}
    >
      {events.length === 0 && <div className="feed-empty">{empty}</div>}
      {events.map((e) => (
        <Row key={`${e.run_id}-${e.seq}`} e={e} />
      ))}
      {running && (
        <div className="typing">
          <span />
          <span />
          <span />
        </div>
      )}
    </div>
  );
}
