"""Inventory: stock, shortfalls, vendor match / lead time, restock purchase orders."""

from models import AgentSpec

SPEC = AgentSpec(
    name="inventory",
    title="Inventory",
    prompt_file="inventory.md",
    mcp_tools=(
        "get_ticket",
        "check_stock",
        "list_inventory",
        "get_vendor_status",
        "get_cash_position",
        "create_purchase_order",
        "draft_message",
        "add_ticket_note",
    ),
)
