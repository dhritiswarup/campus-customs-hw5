"""Facilities: the lease, rent timing, and the rent payment request."""

from models import AgentSpec

SPEC = AgentSpec(
    name="facilities",
    title="Facilities",
    prompt_file="facilities.md",
    mcp_tools=(
        "get_ticket",
        "get_rent_due",
        "get_cash_position",
        "list_approval_requests",
        "request_payment",
        "draft_message",
        "add_ticket_note",
    ),
)
