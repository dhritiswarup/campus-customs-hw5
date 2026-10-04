"""Smoke test: launch the server from .mcp.json over stdio, call each tool for
its ticket, cross-check the values against SQLite, and write output/mcp_smoke.json.

Run:  .venv/Scripts/python.exe mcp_server/smoke_test.py
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from fastmcp import Client

HW5_DIR = Path(__file__).resolve().parent.parent
DB_PATH = HW5_DIR / "data" / "campus_customs_new.db"
OUT_PATH = HW5_DIR / "output" / "mcp_smoke.json"

CASES = [
    {
        "ticket": 101,
        "prompt": "Use the check_stock tool for ticket 101 (Tauhid Zaman wants 1 Classic Bulldog Tee, "
                  "CC-TEE-WHITE, size S) and see if the item is in stock.",
        "tool": "check_stock",
        "args": {"sku": "CC-TEE-WHITE", "size": "S", "qty_needed": 1},
    },
    {
        "ticket": 103,
        "prompt": "Use the check_stock tool for ticket 103 (Yale AI Club wants 20 Basic Hoodie Big Yale, "
                  "CC-HOOD-NAVY, size M) and see if the items are in stock.",
        "tool": "check_stock",
        "args": {"sku": "CC-HOOD-NAVY", "size": "M", "qty_needed": 20},
    },
    {
        "ticket": [101, 103],
        "prompt": "Use the get_vendor_status tool for tickets 101 and 103 to check whether the apparel "
                  "vendor can restock the tee and hoodies: lead time and any unpaid invoices.",
        "tool": "get_vendor_status",
        "args": {"vendor_id": 1},
    },
    {
        "ticket": 102,
        "prompt": "Use the get_rent_due tool for ticket 102 (rent notice from Elm City Properties, lease 1) "
                  "and see how much rent is due and when.",
        "tool": "get_rent_due",
        "args": {"lease_id": 1},
    },
]


def db_expected(conn: sqlite3.Connection, case: dict) -> dict:
    """Pull the raw DB values each tool output must match."""
    a = case["args"]
    if case["tool"] == "check_stock":
        qty, = conn.execute("SELECT qty FROM inventory WHERE sku=? AND size=?", (a["sku"], a["size"])).fetchone()
        cost, price = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku=?", (a["sku"],)).fetchone()
        return {"qty_on_hand": qty, "unit_cost": cost, "list_price": price}
    if case["tool"] == "get_vendor_status":
        lead, = conn.execute("SELECT lead_days FROM vendors WHERE id=?", (a["vendor_id"],)).fetchone()
        inv = conn.execute("SELECT id, amount, due_date FROM invoices WHERE vendor_id=? AND status='open'",
                           (a["vendor_id"],)).fetchall()
        return {"lead_days": lead, "open_invoices": [list(r) for r in inv]}
    if case["tool"] == "get_rent_due":
        rent, due = conn.execute("SELECT monthly_rent, next_due FROM leases WHERE id=?", (a["lease_id"],)).fetchone()
        bal, = conn.execute("SELECT SUM(balance) FROM cash_accounts").fetchone()
        return {"monthly_rent": rent, "next_due": due, "cash_balance": bal}
    raise ValueError(case["tool"])


def tool_actual(case: dict, out: dict) -> dict:
    """Extract the same fields from the tool output for comparison."""
    if case["tool"] == "check_stock":
        return {k: out[k] for k in ("qty_on_hand", "unit_cost", "list_price")}
    if case["tool"] == "get_vendor_status":
        v = out["vendors"][0]
        return {"lead_days": v["lead_days"],
                "open_invoices": [[i["invoice_id"], i["amount"], i["due_date"]] for i in v["open_invoices"]]}
    if case["tool"] == "get_rent_due":
        return {"monthly_rent": out["monthly_rent"], "next_due": out["next_due"],
                "cash_balance": sum(a["balance"] for a in out["cash_accounts"])}
    raise ValueError(case["tool"])


async def main() -> None:
    mcp_config = json.loads((HW5_DIR / ".mcp.json").read_text())
    server = mcp_config["mcpServers"]["campus-customs"]  # run the portable entry with this venv's python
    server["command"] = sys.executable
    server["args"] = [str(HW5_DIR / a) if a.endswith(".py") else a for a in server["args"]]
    conn = sqlite3.connect(DB_PATH)
    results = []
    async with Client(mcp_config) as client:
        tools = [t.name for t in await client.list_tools()]
        for case in CASES:
            res = await client.call_tool(case["tool"], case["args"])
            out = res.structured_content or json.loads(res.content[0].text)
            expected, actual = db_expected(conn, case), tool_actual(case, out)
            results.append({
                "ticket": case["ticket"],
                "prompt": case["prompt"],
                "tool": case["tool"],
                "arguments": case["args"],
                "tool_output": out,
                "db_check": {"expected_from_db": expected, "from_tool": actual, "matches_db": expected == actual},
            })
    conn.close()

    report = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "mcp_server": "campus-customs (stdio, launched from .mcp.json)",
        "database": "data/campus_customs_new.db",
        "tools_listed": tools,
        "all_match_db": all(r["db_check"]["matches_db"] for r in results),
        "tests": results,
    }
    OUT_PATH.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
