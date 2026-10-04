import { AGENT_ORDER, AGENTS } from "../lib/agents";
import type { AgentLive } from "../lib/derive";
import type { AgentName } from "../lib/types";

const STATE_LABEL = { idle: "Idle", thinking: "Thinking", tool: "Using tool", done: "Done", error: "Error" };

export function AgentRoster({ live }: { live: Record<AgentName, AgentLive> }) {
  return (
    <div className="roster">
      {AGENT_ORDER.map((name) => {
        const a = AGENTS[name];
        const s = live[name];
        const Icon = a.icon;
        return (
          <div key={name} className={`agent-card state-${s.state}`} style={{ "--agent": a.color } as React.CSSProperties}>
            <div className="agent-avatar">
              <Icon size={22} />
              <span className="agent-ring" />
            </div>
            <div className="agent-text">
              <div className="agent-name">{a.label}</div>
              <div className="agent-role">{a.role}</div>
            </div>
            <div className="agent-status">
              <span className="dot" />
              <span>{STATE_LABEL[s.state]}</span>
            </div>
            <div className="agent-detail mono" title={s.detail}>
              {s.state === "idle" ? "—" : s.detail}
            </div>
          </div>
        );
      })}
    </div>
  );
}
