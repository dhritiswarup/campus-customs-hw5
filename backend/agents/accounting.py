"""Accounting: cash, vendor-invoice payment requests, pricing and discount quotes."""

from models import AgentSpec

SPEC = AgentSpec(
    name="accounting",
    title="Accounting",
    prompt_file="accounting.md",
    mcp_tools=(
        "get_ticket",
        "check_stock",
        "get_vendor_status",
        "get_cash_position",
        "list_approval_requests",
        "preview_discount",
        "create_quote",
        "request_payment",
        "draft_message",
        "add_ticket_note",
    ),
)
