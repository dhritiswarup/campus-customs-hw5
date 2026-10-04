import { AGENT_ORDER, agentMeta } from "./agents";
import type { AgentEvent, AgentName, AgentReport } from "./types";

export type LiveState = "idle" | "thinking" | "tool" | "done" | "error";

export interface AgentLive {
  state: LiveState;
  detail: string; // tool name, delegate target, or last line
  calls: number; // tool calls this run
}

/** Replay a run's events into each agent's current status. */
export function deriveLive(events: AgentEvent[], running: boolean): Record<AgentName, AgentLive> {
  const live = Object.fromEntries(
    AGENT_ORDER.map((a) => [a, { state: "idle", detail: "", calls: 0 } as AgentLive]),
  ) as Record<AgentName, AgentLive>;

  for (const e of events) {
    const a = e.agent;
    if (!a || !live[a]) continue;
    const s = live[a];
    if (e.kind === "agent_start") {
      s.state = "thinking";
      s.detail = "reading the task";
    } else if (e.kind === "delegation") {
      s.state = "tool";
      s.detail = `delegate → ${agentMeta(e.delegated_to).label}`;
      s.calls += 1;
    } else if (e.kind === "agent_step" && e.tools.length) {
      s.state = "tool";
      s.detail = e.tools.map((t) => t.tool).join(", ");
      s.calls += e.tools.length;
    } else if (e.kind === "agent_step" && e.tool_results.length) {
      s.state = "thinking";
      s.detail = "reading tool results";
    } else if (e.kind === "agent_end") {
      const failed = e.report ? !e.report.ok : e.summary.includes("FAILED");
      s.state = failed ? "error" : "done";
      s.detail = failed ? "hit an error" : "reported back";
    }
  }
  if (!running) {
    for (const a of AGENT_ORDER) {
      if (live[a].state === "thinking" || live[a].state === "tool") live[a] = { ...live[a], state: "done" };
    }
  }
  return live;
}

/** Events belonging to the most recent run in a list. */
export function latestRun(events: AgentEvent[]): AgentEvent[] {
  const starts = events.filter((e) => e.kind === "run_start");
  if (!starts.length) return [];
  const last = starts[starts.length - 1].run_id;
  return events.filter((e) => e.run_id === last);
}

export interface AgentSummary {
  agent: AgentName;
  report: AgentReport;
  at: string;
}

/** Each agent's report(s) from a run, Boss last. */
export function summaries(events: AgentEvent[]): AgentSummary[] {
  const out = events
    .filter((e) => e.kind === "agent_end" && e.agent && e.report)
    .map((e) => ({ agent: e.agent as AgentName, report: e.report as AgentReport, at: e.logged_at }));
  return [...out.filter((s) => s.agent !== "boss"), ...out.filter((s) => s.agent === "boss")];
}
