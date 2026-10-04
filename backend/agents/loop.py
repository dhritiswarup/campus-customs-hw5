"""Agent loops, delegation, and audit tracing for the Campus Customs team.

- run_team(task): opens ONE stdio session to the campus-customs MCP server,
  gives each agent a filtered view of its tools, and runs the Boss.
- delegate(to_agent, task): a tool every agent has. It runs another agent's
  loop and returns that agent's structured report, so any agent can hand
  work to any other (full connectivity), within depth / count / token limits.
- Every loop node (prompt -> model request -> model response / tool calls ->
  tool results -> end) is appended to output/audit_trail.json.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from functools import lru_cache
from typing import Any

from fastmcp import Client
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import (
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.usage import UsageLimits

import audit
from audit import clip
from config import (
    AGENT_REQUEST_LIMIT,
    AGENT_TOKEN_LIMIT,
    AGENT_TOOL_CALL_LIMIT,
    MAX_DELEGATION_DEPTH,
    MAX_DELEGATIONS_PER_RUN,
    MODEL_NAME,
    RUN_TIMEOUT_S,
    RUN_TOKEN_BUDGET,
    WORKING_DB,
    build_model,
    load_prompt,
    mcp_client_config,
)
from models import AGENT_NAMES, AgentName, AgentReport, BossReport, RunState, TeamDeps

from . import TEAM

DEFAULT_TASK = (
    "Work every open ticket on the board. Plan across all tickets together (shared blockers, "
    "tight cash), delegate each piece to the right agent, set each ticket's status, and give me "
    "your report with the approvals I need to make."
)


# ---------------------------------------------------------------------------
# Delegation tool (shared by every agent)
# ---------------------------------------------------------------------------


async def delegate(
    ctx: RunContext[TeamDeps], to_agent: AgentName, task: str, ticket_id: int | None = None
) -> dict[str, Any]:
    """Hand a piece of work to another Campus Customs agent and wait for its report.

    Args:
        to_agent: boss, inventory, accounting, facilities or customer_service.
        task: A complete, self-contained instruction: ticket ID, the exact SKU/size/qty
            or invoice/lease ID, what to do, any limits, and what to report back.
            The other agent cannot see your conversation.
        ticket_id: The ticket this work is for, if any.
    """
    d = ctx.deps
    s = d.state
    refusal = None
    if to_agent == d.agent:
        refusal = "You cannot delegate to yourself; do the work with your own tools."
    elif to_agent in d.chain:
        refusal = f"{to_agent} is already waiting on you in this chain ({' > '.join(d.chain + [d.agent])}); report back instead."
    elif d.depth + 1 > MAX_DELEGATION_DEPTH:
        refusal = f"Delegation depth limit ({MAX_DELEGATION_DEPTH}) reached; finish with what you have."
    elif s.delegations >= MAX_DELEGATIONS_PER_RUN:
        refusal = f"Run delegation limit ({MAX_DELEGATIONS_PER_RUN}) reached; finish with what you have."
    elif s.tokens_used >= RUN_TOKEN_BUDGET:
        refusal = f"Run token budget ({RUN_TOKEN_BUDGET:,}) used up; finish with what you have."

    audit.record(
        s, "delegation", agent=d.agent, chain=d.chain, depth=d.depth, ticket_id=ticket_id,
        summary=f"{d.agent} -> {to_agent}" + (f" REFUSED: {refusal}" if refusal else ""),
        detail={"from": d.agent, "to": to_agent, "task": task, "tool_call_id": ctx.tool_call_id,
                "refused": refusal, "delegation_no": None if refusal else s.delegations + 1},
    )
    if refusal:
        return {"ok": False, "agent": to_agent, "error": refusal}

    s.delegations += 1
    return await run_agent(to_agent, task, s, d.toolsets, chain=d.chain + [d.agent], ticket_id=ticket_id)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _agent(name: AgentName) -> Agent[TeamDeps, Any]:
    spec = TEAM[name]
    return Agent(
        build_model(),
        name=name,
        deps_type=TeamDeps,
        output_type=BossReport if spec.output == "boss_report" else AgentReport,
        tools=[Tool(delegate, takes_ctx=True)],
        retries=2,
    )


def _instructions(deps: TeamDeps) -> str:
    spec = TEAM[deps.agent]
    s = deps.state
    others = [a for a in AGENT_NAMES if a != deps.agent and a not in deps.chain]
    chain = " > ".join(deps.chain + [deps.agent])
    return (
        load_prompt(spec.prompt_file)
        + "\n\n## This run\n"
        + f"- You are `{deps.agent}`. Pass `agent=\"{deps.agent}\"` (or author) to every tool that asks who you are.\n"
        + f"- Delegation chain: {chain}. You may delegate to: {', '.join(others) or 'nobody (report back)'}.\n"
        + f"- Delegations left this run: {MAX_DELEGATIONS_PER_RUN - s.delegations}. "
        + f"Depth left: {MAX_DELEGATION_DEPTH - deps.depth}. "
        + f"Model calls allowed in your loop: {AGENT_REQUEST_LIMIT}.\n"
        + (f"- Ticket in focus: {deps.ticket_id}.\n" if deps.ticket_id is not None else "")
    )


def _usage(u: Any) -> dict[str, int]:
    keys = ("requests", "tool_calls", "input_tokens", "output_tokens")
    return {k: int(getattr(u, k, 0) or 0) for k in keys}


async def run_agent(
    name: AgentName,
    task: str,
    state: RunState,
    toolsets: dict[str, Any],
    chain: list[AgentName] | None = None,
    ticket_id: int | None = None,
) -> dict[str, Any]:
    """Run one agent loop to completion and return its report as a dict (never raises)."""
    spec = TEAM[name]
    deps = TeamDeps(agent=name, state=state, toolsets=toolsets, chain=chain or [], ticket_id=ticket_id)
    who = {"agent": name, "chain": deps.chain, "depth": deps.depth, "ticket_id": ticket_id}
    prompt_text = load_prompt(spec.prompt_file)
    instructions = _instructions(deps)
    token_cap = max(min(AGENT_TOKEN_LIMIT, RUN_TOKEN_BUDGET - state.tokens_used), 1)

    audit.record(
        state, "agent_start", **who, summary=f"{name} starts: {task[:160]}",
        detail={
            "task": task, "model": MODEL_NAME, "prompt_file": f"backend/prompts/{spec.prompt_file}",
            "prompt_sha256": hashlib.sha256(prompt_text.encode()).hexdigest()[:16],
            "run_context": instructions[len(prompt_text):].strip(), "mcp_tools": list(spec.mcp_tools),
            "limits": {"request_limit": AGENT_REQUEST_LIMIT, "tool_calls_limit": AGENT_TOOL_CALL_LIMIT,
                       "total_tokens_limit": token_cap},
        },
    )

    step = 0

    def log_step(node: str, summary: str, **detail: Any) -> None:
        nonlocal step
        step += 1
        audit.record(state, "agent_step", **who, step=step, node=node, summary=summary, detail=detail)

    usage: dict[str, int] = {}
    try:
        async with _agent(name).iter(
            task,
            deps=deps,
            instructions=instructions,
            toolsets=[toolsets[name]],
            usage_limits=UsageLimits(
                request_limit=AGENT_REQUEST_LIMIT,
                tool_calls_limit=AGENT_TOOL_CALL_LIMIT,
                total_tokens_limit=token_cap,
            ),
        ) as run:
            async for node in run:
                if Agent.is_user_prompt_node(node):
                    log_step("user_prompt", "receives task", prompt=clip(task))
                elif Agent.is_model_request_node(node):
                    parts = _request_parts(node.request.parts)
                    log_step("model_request", _request_summary(parts), parts=parts)
                elif Agent.is_call_tools_node(node):
                    resp = node.model_response
                    parts = _response_parts(resp.parts)
                    calls = [p for p in parts if p["kind"] == "tool_call"]
                    log_step(
                        "model_response",
                        "calls " + ", ".join(c["tool"] for c in calls) if calls else "writes its answer",
                        model=resp.model_name, parts=parts, usage=_usage(resp.usage),
                    )
                elif Agent.is_end_node(node):
                    log_step("end", "loop complete")
            output = run.result.output
            usage = _usage(run.usage() if callable(run.usage) else run.usage)
        report = {"ok": True, "agent": name, **output.model_dump()}
    except Exception as exc:  # report to the caller instead of crashing the team
        report = {"ok": False, "agent": name, "error": f"{type(exc).__name__}: {exc}"}

    state.tokens_used += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    state.requests_used += usage.get("requests", 0)
    audit.record(
        state, "agent_end", **who,
        summary=f"{name} {'finished' if report['ok'] else 'FAILED'}: "
        + str(report.get("summary") or report.get("error", ""))[:200],
        detail={"report": report, "usage": usage, "run_tokens_used": state.tokens_used},
    )
    return report


def new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


def ticket_task(ticket_id: int) -> str:
    return (
        f"Work ticket {ticket_id} only. Read it with get_ticket, check the cash position (other tickets "
        f"may already have pending requests against the same cash), delegate only to the agents this "
        f"ticket needs, set its status, and give me your report with any approvals I need to make."
    )


async def run_team(
    task: str = DEFAULT_TASK,
    db_path: str | None = None,
    ticket_id: int | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """One team run: connect to MCP, run the Boss, return its report plus run totals.

    ticket_id focuses the Boss on one ticket; run_id lets a caller (the API) know the ID up front.
    """
    state = RunState(
        run_id=run_id or new_run_id(),
        max_depth=MAX_DELEGATION_DEPTH,
        max_delegations=MAX_DELEGATIONS_PER_RUN,
        token_budget=RUN_TOKEN_BUDGET,
    )
    mcp = MCPToolset(Client(mcp_client_config(db_path)), id="campus-customs")
    audit.record(
        state, "run_start", ticket_id=ticket_id, summary=task[:200],
        detail={"task": task, "model": MODEL_NAME, "database": str(db_path or WORKING_DB),
                "limits": {"max_delegation_depth": MAX_DELEGATION_DEPTH,
                           "max_delegations": MAX_DELEGATIONS_PER_RUN, "run_token_budget": RUN_TOKEN_BUDGET}},
    )
    async with mcp:  # one MCP server process shared by every agent in this run
        toolsets = {
            name: mcp.filtered(lambda _ctx, tool, allowed=frozenset(spec.mcp_tools): tool.name in allowed)
            for name, spec in TEAM.items()
        }
        try:
            async with asyncio.timeout(RUN_TIMEOUT_S):
                report = await run_agent("boss", task, state, toolsets, ticket_id=ticket_id)
        except TimeoutError:
            report = {"ok": False, "agent": "boss", "error": f"Run stopped at the {RUN_TIMEOUT_S}s wall-clock limit."}
    totals = {"ok": report["ok"], "delegations": state.delegations, "tokens_used": state.tokens_used, "model_requests": state.requests_used}
    audit.record(state, "run_end", agent="boss", ticket_id=ticket_id, summary="run complete" if report["ok"] else "run failed", detail=totals)
    return {"run_id": state.run_id, **totals, "report": report}


# ---------------------------------------------------------------------------
# Message-part helpers for the audit trail
# ---------------------------------------------------------------------------


def _request_parts(parts: list[Any]) -> list[dict[str, Any]]:
    out = []
    for p in parts:
        if isinstance(p, ToolReturnPart):
            out.append({"kind": "tool_return", "tool": p.tool_name, "tool_call_id": p.tool_call_id, "content": clip(p.content)})
        elif isinstance(p, RetryPromptPart):
            out.append({"kind": "retry", "tool": p.tool_name, "content": clip(p.content)})
        elif isinstance(p, UserPromptPart):
            out.append({"kind": "user_prompt", "content": clip(p.content)})
        elif isinstance(p, SystemPromptPart):
            out.append({"kind": "system_prompt", "content": clip(p.content, 300)})
        else:
            out.append({"kind": type(p).__name__})
    return out


def _response_parts(parts: list[Any]) -> list[dict[str, Any]]:
    out = []
    for p in parts:
        if isinstance(p, ToolCallPart):
            out.append({"kind": "tool_call", "tool": p.tool_name, "tool_call_id": p.tool_call_id, "args": p.args_as_dict()})
        elif isinstance(p, TextPart):
            out.append({"kind": "text", "content": clip(p.content)})
        elif isinstance(p, ThinkingPart):
            out.append({"kind": "thinking", "content": clip(p.content or "(hidden reasoning)", 1500)})
        else:
            out.append({"kind": type(p).__name__})
    return out


def _request_summary(parts: list[dict[str, Any]]) -> str:
    returns = [p["tool"] for p in parts if p["kind"] == "tool_return"]
    if returns:
        return "sends tool results to the model: " + ", ".join(returns)
    if any(p["kind"] == "retry" for p in parts):
        return "asks the model to retry"
    return "sends the task to the model"
