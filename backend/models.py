"""Data types shared by the Campus Customs agent team.

- AgentName / AgentSpec: who is on the team and which MCP tools each may use
- AgentReport / BossReport: the structured output each agent loop ends with
- TeamDeps / RunState: per-agent-run dependencies and the run-wide budget
- AuditEntry: one record appended to output/audit_trail.json
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
AGENT_NAMES: tuple[AgentName, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

TicketStatus = Literal["open", "in_progress", "waiting_on_approval", "waiting_on_vendor", "resolved"]


class AgentSpec(BaseModel):
    """Static definition of one agent: its prompt file and the MCP tools it may call."""

    name: AgentName
    title: str
    prompt_file: str
    mcp_tools: tuple[str, ...]
    output: Literal["agent_report", "boss_report"] = "agent_report"


# ---------------------------------------------------------------------------
# Structured outputs (the last step of every agent loop)
# ---------------------------------------------------------------------------


class AgentReport(BaseModel):
    """What a specialist hands back to whoever delegated to it."""

    summary: str = Field(description="One or two sentences with the key numbers.")
    ticket_ids: list[int] = Field(default_factory=list, description="Tickets this work was for.")
    facts: list[str] = Field(default_factory=list, description="Each fact used, with the tool it came from.")
    actions_taken: list[str] = Field(default_factory=list, description="Records created: request/PO/quote/draft IDs.")
    needs_human: list[str] = Field(default_factory=list, description="Decisions only a person can make.")
    blocked_by: list[str] = Field(default_factory=list, description="What stopped the work, if anything.")
    next_steps: list[str] = Field(default_factory=list, description="What should happen next and who does it.")


class TicketOutcome(BaseModel):
    ticket_id: int
    status: TicketStatus
    what_was_done: str
    agents: list[AgentName] = Field(default_factory=list)
    waiting_on: str = ""


class BossReport(BaseModel):
    """The Boss's end-of-run report to the human owner."""

    summary: str
    tickets: list[TicketOutcome] = Field(default_factory=list)
    approvals_needed: list[str] = Field(default_factory=list, description="Pending requests in recommended order.")
    cash_note: str = ""
    drafts_to_review: list[int] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------


@dataclass
class RunState:
    """Shared by every agent in one team run: IDs, budgets and running totals."""

    run_id: str
    max_depth: int
    max_delegations: int
    token_budget: int
    delegations: int = 0
    tokens_used: int = 0
    requests_used: int = 0
    seq: int = 0

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq


@dataclass
class TeamDeps:
    """Dependencies for one agent loop. chain = agents above this one, boss first."""

    agent: AgentName
    state: RunState
    toolsets: dict[str, Any]
    chain: list[AgentName] = field(default_factory=list)
    ticket_id: int | None = None

    @property
    def depth(self) -> int:
        return len(self.chain)


# ---------------------------------------------------------------------------
# API shapes (backend/main.py)
# ---------------------------------------------------------------------------

RunStatus = Literal["running", "done", "failed"]


class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=1, description="The human approving; agent names are refused.")


class RejectBody(BaseModel):
    rejected_by: str = Field(min_length=1)
    note: str = ""


class ResolveBody(BaseModel):
    resolved_by: str = Field(min_length=1)
    note: str = ""


class RunInfo(BaseModel):
    run_id: str
    ticket_id: int
    status: RunStatus
    started_at: str
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class AgentEvent(BaseModel):
    """One audit entry, flattened for the board: what an agent said and which tools it used."""

    run_id: str
    seq: int
    logged_at: str
    kind: str
    agent: str | None = None
    chain: list[str] = Field(default_factory=list)
    ticket_id: int | None = None
    summary: str = ""
    said: str | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    delegated_to: str | None = None
    report: dict[str, Any] | None = None  # agent_end: the agent's full structured report


class AuditEntry(BaseModel):
    """One line of output/audit_trail.json. kind tells you which fields are filled."""

    run_id: str
    seq: int
    logged_at: str
    kind: Literal["run_start", "agent_start", "agent_step", "delegation", "agent_end", "run_end"]
    agent: AgentName | None = None
    chain: list[AgentName] = Field(default_factory=list)
    depth: int = 0
    ticket_id: int | None = None
    step: int | None = None
    node: str | None = None
    summary: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)
