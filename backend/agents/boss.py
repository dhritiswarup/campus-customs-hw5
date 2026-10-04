"""Boss: owns the ticket board, plans across tickets, delegates, sets ticket status."""

from models import AgentSpec

SPEC = AgentSpec(
    name="boss",
    title="Boss",
    prompt_file="boss.md",
    output="boss_report",
    mcp_tools=(
        "list_open_tickets",
        "get_ticket",
        "get_cash_position",
        "list_approval_requests",
        "set_ticket_status",
        "add_ticket_note",
    ),
)
