"""The Campus Customs agent team. Every agent can delegate to every other agent."""

from models import AgentName, AgentSpec

from . import accounting, boss, customer_service, facilities, inventory

TEAM: dict[AgentName, AgentSpec] = {
    m.SPEC.name: m.SPEC for m in (boss, inventory, accounting, facilities, customer_service)
}

# Tools on the MCP server that only a human may call. No agent spec may list them.
HUMAN_ONLY_TOOLS = frozenset({"approve_request", "reject_request", "resolve_ticket"})

for _spec in TEAM.values():
    assert not HUMAN_ONLY_TOOLS & set(_spec.mcp_tools), f"{_spec.name} lists a human-only tool"

from .loop import run_agent, run_team  # noqa: E402

__all__ = ["TEAM", "HUMAN_ONLY_TOOLS", "run_agent", "run_team"]
