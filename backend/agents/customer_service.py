"""Customer Service: honest customer-facing draft replies built from tool facts."""

from models import AgentSpec

SPEC = AgentSpec(
    name="customer_service",
    title="Customer Service",
    prompt_file="customer_service.md",
    mcp_tools=(
        "get_ticket",
        "check_stock",
        "list_inventory",
        "get_vendor_status",
        "draft_message",
        "add_ticket_note",
    ),
)
