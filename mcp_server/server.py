"""Campus Customs MCP server.

Every agent on the Campus Customs team (Boss, Inventory, Accounting,
Facilities, Customer Service) reaches the shop database only through the
tools in this server. The tools read and write the working copy
data/campus_customs_new.db and never touch the original campus_customs.db.

Rules every tool follows:
- Only report what is in the database. Missing rows come back as an
  explicit "not found" error, never a guessed value.
- "Today" is desk.date_today, not the computer clock.
- No tool sends anything. Customer / vendor / landlord messages are saved
  as drafts on the board only.
- Agents can only *request* payments. Money moves only through
  approve_request, which a human calls (the agent backend never exposes it),
  and it refuses any payment that would push cash below zero.

Run (stdio):  python mcp_server/server.py
"""

from __future__ import annotations

import calendar
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from fastmcp import FastMCP

HW5_DIR = Path(__file__).resolve().parent.parent
# CAMPUS_CUSTOMS_DB lets tests point the server at a scratch copy.
DB_PATH = Path(os.getenv("CAMPUS_CUSTOMS_DB") or HW5_DIR / "data" / "campus_customs_new.db")

mcp = FastMCP("campus-customs")

AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service"}
TICKET_STATUSES = ("open", "in_progress", "waiting_on_approval", "waiting_on_vendor", "resolved")
DRAFT_RECIPIENTS = ("customer", "vendor", "landlord")

# Work tables the agents write to. Created in the working copy only.
_WORK_TABLES = """
CREATE TABLE IF NOT EXISTS approval_requests (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,             -- invoice | rent | purchase_order
    ref_id INTEGER NOT NULL,        -- invoices.id | leases.id | purchase_orders.id
    ticket_id INTEGER,
    amount REAL NOT NULL,
    payee TEXT NOT NULL,
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL,           -- pending | paid | rejected
    created_at TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    decision_note TEXT,
    payment_id INTEGER
);
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY,
    vendor_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    size TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_cost REAL NOT NULL,
    total REAL NOT NULL,
    ticket_id INTEGER,
    status TEXT NOT NULL,           -- awaiting_payment_approval | placed | rejected
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expected_arrival TEXT
);
CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER,
    sku TEXT NOT NULL,
    size TEXT NOT NULL,
    qty INTEGER NOT NULL,
    list_price REAL NOT NULL,
    unit_price REAL NOT NULL,
    discount_pct REAL NOT NULL,
    unit_cost REAL NOT NULL,
    margin_per_unit REAL NOT NULL,
    total REAL NOT NULL,
    created_by TEXT NOT NULL,
    status TEXT NOT NULL,           -- draft (never sent by an agent)
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER,
    recipient_type TEXT NOT NULL,   -- customer | vendor | landlord
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    author TEXT NOT NULL,
    status TEXT NOT NULL,           -- draft (never sent by an agent)
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ticket_log (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    agent TEXT NOT NULL,
    note TEXT NOT NULL,
    status_from TEXT,
    status_to TEXT,
    logged_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Working database not found at {DB_PATH}. "
            "Copy data/campus_customs.db to data/campus_customs_new.db first."
        )
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_WORK_TABLES)
    return conn


def _shop_today(conn: sqlite3.Connection) -> date:
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    if row is None:
        raise ValueError("desk table has no date_today row.")
    return date.fromisoformat(row["date_today"])


def _now() -> str:
    """Wall-clock timestamp for record-keeping only (business dates use desk.date_today)."""
    return datetime.now().isoformat(timespec="seconds")


def _cash_balance(conn: sqlite3.Connection, account: str = "checking") -> float | None:
    row = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    return row["balance"] if row else None


def _pending_total(conn: sqlite3.Connection) -> float:
    return conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM approval_requests WHERE status = 'pending'"
    ).fetchone()[0]


def _open_invoices(conn: sqlite3.Connection, vendor_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, amount, due_date, status, description FROM invoices "
        "WHERE vendor_id = ? AND status = 'open' ORDER BY due_date",
        (vendor_id,),
    ).fetchall()


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _require_agent(name: str) -> str | None:
    if name not in AGENT_NAMES:
        return f"Unknown agent {name!r}. Use one of: {', '.join(sorted(AGENT_NAMES))}."
    return None


def _ticket_exists(conn: sqlite3.Connection, ticket_id: int | None) -> bool:
    if ticket_id is None:
        return True
    return conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is not None


# --------------------------------------------------------------------------
# Read tools
# --------------------------------------------------------------------------


def check_stock(sku: str, size: str, qty_needed: int = 1) -> dict:
    """Check on-hand stock for one SKU and size, and whether it covers an order.

    Reads inventory (qty, location) and pricing (unit_cost, list_price).
    Returns qty_on_hand, shortfall (units still needed), and the unit cost /
    list price so Accounting can price a restock or a discount.
    """
    with _connect() as conn:
        item = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory "
            "WHERE sku = ? AND size = ?",
            (sku, size),
        ).fetchone()
        if item is None:
            return {"found": False, "error": f"No inventory row for sku={sku!r}, size={size!r}."}
        price = conn.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()

    shortfall = max(qty_needed - item["qty"], 0)
    return {
        "found": True,
        "sku": item["sku"],
        "name": item["name"],
        "size": item["size"],
        "location": item["location"],
        "qty_on_hand": item["qty"],
        "qty_needed": qty_needed,
        "can_fill_from_stock": shortfall == 0,
        "shortfall": shortfall,
        "unit_cost": price["unit_cost"] if price else None,
        "list_price": price["list_price"] if price else None,
    }


def list_inventory(sku: str | None = None) -> dict:
    """List every inventory row (all SKUs and sizes) with stock, cost and list price.

    Reads inventory and pricing. Pass sku to see all sizes of one product,
    for example to tell a customer which other sizes are on the shelf.
    """
    with _connect() as conn:
        sql = (
            "SELECT i.sku, i.name, i.size, i.qty, i.location, p.unit_cost, p.list_price "
            "FROM inventory i LEFT JOIN pricing p ON p.sku = i.sku"
        )
        rows = (
            conn.execute(sql + " WHERE i.sku = ? ORDER BY i.size", (sku,)).fetchall()
            if sku
            else conn.execute(sql + " ORDER BY i.sku, i.size").fetchall()
        )
    if not rows:
        return {"found": False, "error": f"No inventory rows for sku={sku!r}."}
    return {"found": True, "items": [dict(r) for r in rows]}


def get_vendor_status(vendor_id: int | None = None) -> dict:
    """List vendors with lead times and any open (unpaid) invoices.

    Reads vendors, invoices, and desk.date_today. A vendor with an open
    invoice is marked can_ship = False, because vendors will not ship new
    product while they have an unpaid invoice. Pass vendor_id for one vendor,
    or omit it to see every vendor so the agent can pick by specialty.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        if vendor_id is None:
            vendors = conn.execute(
                "SELECT id, name, specialty, lead_days FROM vendors ORDER BY id"
            ).fetchall()
        else:
            vendors = conn.execute(
                "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?",
                (vendor_id,),
            ).fetchall()
            if not vendors:
                return {"found": False, "error": f"No vendor with id={vendor_id}."}

        result = []
        for v in vendors:
            open_invoices = [
                {
                    "invoice_id": inv["id"],
                    "amount": inv["amount"],
                    "due_date": inv["due_date"],
                    "days_overdue": max((today - date.fromisoformat(inv["due_date"])).days, 0),
                    "description": inv["description"],
                }
                for inv in _open_invoices(conn, v["id"])
            ]
            result.append(
                {
                    "vendor_id": v["id"],
                    "name": v["name"],
                    "specialty": v["specialty"],
                    "lead_days": v["lead_days"],
                    "open_invoices": open_invoices,
                    "open_balance": sum(i["amount"] for i in open_invoices),
                    "can_ship": not open_invoices,
                }
            )

    return {"found": True, "today": today.isoformat(), "vendors": result}


def get_rent_due(lease_id: int) -> dict:
    """Report the rent owed on a lease, days until due, and whether cash covers it.

    Reads leases, desk.date_today, and cash_accounts. Does not pay anything;
    payments need human approval through a separate tool.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        lease = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes "
            "FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        if lease is None:
            return {"found": False, "error": f"No lease with id={lease_id}."}
        accounts = conn.execute(
            "SELECT name, balance, date FROM cash_accounts ORDER BY name"
        ).fetchall()

    days_until_due = (date.fromisoformat(lease["next_due"]) - today).days
    total_cash = sum(a["balance"] for a in accounts)
    return {
        "found": True,
        "today": today.isoformat(),
        "lease_id": lease["id"],
        "space_name": lease["space_name"],
        "landlord": lease["landlord"],
        "monthly_rent": lease["monthly_rent"],
        "next_due": lease["next_due"],
        "days_until_due": days_until_due,
        "is_overdue": days_until_due < 0,
        "notes": lease["notes"],
        "cash_accounts": [dict(a) for a in accounts],
        "cash_covers_rent": total_cash >= lease["monthly_rent"],
        "cash_after_rent": total_cash - lease["monthly_rent"],
    }


def list_open_tickets() -> dict:
    """List every ticket on the board that is not resolved, oldest first.

    Reads tickets and desk.date_today. This is the Boss's work queue: each
    row carries the ticket type and its link columns (sku/size/qty,
    lease_id, invoice_id) that say which agent should pick it up.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        rows = conn.execute(
            "SELECT * FROM tickets WHERE status != 'resolved' ORDER BY created_at"
        ).fetchall()
    return {"found": True, "today": today.isoformat(), "tickets": [dict(r) for r in rows]}


def list_tickets() -> dict:
    """List every ticket on the board, open or resolved, with an is_open flag.

    Reads tickets and desk.date_today. Used by the human dashboard to show the
    whole board; agents work from list_open_tickets.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        rows = conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
    return {
        "found": True,
        "today": today.isoformat(),
        "tickets": [{**dict(r), "is_open": r["status"] != "resolved"} for r in rows],
    }


def get_ticket(ticket_id: int) -> dict:
    """Get one ticket with everything linked to it and all work done on it so far.

    Reads tickets plus the linked inventory/pricing (sku+size), invoices and
    vendors (invoice_id), and leases (lease_id), then the ticket's
    ticket_log notes, drafts, quotes, purchase_orders and approval_requests.
    Call this first so you do not repeat work another agent already did.
    """
    with _connect() as conn:
        t = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"found": False, "error": f"No ticket with id={ticket_id}."}
        linked: dict = {}
        if t["sku"] and t["size"]:
            item = conn.execute(
                "SELECT i.sku, i.name, i.size, i.qty AS qty_on_hand, i.location, p.unit_cost, p.list_price "
                "FROM inventory i LEFT JOIN pricing p ON p.sku = i.sku WHERE i.sku = ? AND i.size = ?",
                (t["sku"], t["size"]),
            ).fetchone()
            linked["inventory"] = dict(item) if item else {"found": False, "error": "No matching inventory row."}
        if t["invoice_id"] is not None:
            inv = conn.execute(
                "SELECT i.id, i.amount, i.due_date, i.status, i.description, v.id AS vendor_id, "
                "v.name AS vendor_name, v.lead_days FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
                "WHERE i.id = ?",
                (t["invoice_id"],),
            ).fetchone()
            linked["invoice"] = dict(inv) if inv else {"found": False, "error": "No matching invoice."}
        if t["lease_id"] is not None:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (t["lease_id"],)).fetchone()
            linked["lease"] = dict(lease) if lease else {"found": False, "error": "No matching lease."}

        def rows(table: str) -> list[dict]:
            return [dict(r) for r in conn.execute(f"SELECT * FROM {table} WHERE ticket_id = ? ORDER BY id", (ticket_id,))]

        return {
            "found": True,
            "today": _shop_today(conn).isoformat(),
            "ticket": dict(t),
            "linked": linked,
            "log": rows("ticket_log"),
            "drafts": rows("drafts"),
            "quotes": rows("quotes"),
            "purchase_orders": rows("purchase_orders"),
            "approval_requests": rows("approval_requests"),
        }


def get_cash_position() -> dict:
    """Show cash on hand, money already committed to pending approvals, and recent payments.

    Reads cash_accounts, approval_requests (status pending) and payments.
    available_after_pending is what would be left if a human approved every
    pending request; use it to decide what the shop can still afford.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        accounts = [dict(a) for a in conn.execute("SELECT name, balance, date FROM cash_accounts ORDER BY name")]
        pending = [
            dict(r)
            for r in conn.execute(
                "SELECT id, kind, ref_id, ticket_id, amount, payee, requested_by FROM approval_requests "
                "WHERE status = 'pending' ORDER BY id"
            )
        ]
        payments = [dict(r) for r in conn.execute("SELECT * FROM payments ORDER BY id DESC LIMIT 10")]
    cash = sum(a["balance"] for a in accounts)
    committed = sum(p["amount"] for p in pending)
    return {
        "found": True,
        "today": today.isoformat(),
        "cash_accounts": accounts,
        "cash_on_hand": cash,
        "pending_requests": pending,
        "pending_total": committed,
        "available_after_pending": cash - committed,
        "recent_payments": payments,
    }


def list_approval_requests(status: str | None = "pending") -> dict:
    """List payment approval requests waiting for (or already given) a human decision.

    Reads approval_requests. status can be pending, paid, rejected, or None for all.
    """
    with _connect() as conn:
        if status:
            rows = conn.execute("SELECT * FROM approval_requests WHERE status = ? ORDER BY id", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM approval_requests ORDER BY id").fetchall()
    return {"found": True, "requests": [dict(r) for r in rows]}


def preview_discount(sku: str, qty: int, discount_pct: float) -> dict:
    """Work out the price, margin and total for a discount without saving anything.

    Reads pricing. discount_pct is off list price (10 means 10%). Reports
    above_cost = False if the discounted price would be at or below unit cost,
    which the shop never allows.
    """
    with _connect() as conn:
        p = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if p is None:
        return {"found": False, "error": f"No pricing row for sku={sku!r}."}
    if qty <= 0 or not 0 <= discount_pct < 100:
        return {"found": False, "error": "qty must be > 0 and discount_pct between 0 and 100."}
    unit_price = round(p["list_price"] * (1 - discount_pct / 100), 2)
    margin = round(unit_price - p["unit_cost"], 2)
    return {
        "found": True,
        "sku": sku,
        "qty": qty,
        "list_price": p["list_price"],
        "unit_cost": p["unit_cost"],
        "discount_pct": discount_pct,
        "unit_price": unit_price,
        "margin_per_unit": margin,
        "margin_pct_of_price": round(margin / unit_price * 100, 1) if unit_price else None,
        "total": round(unit_price * qty, 2),
        "total_margin": round(margin * qty, 2),
        "above_cost": unit_price > p["unit_cost"],
        "max_discount_pct_above_cost": round((1 - p["unit_cost"] / p["list_price"]) * 100, 2),
    }


# --------------------------------------------------------------------------
# Write tools for agents (nothing here moves money or sends a message)
# --------------------------------------------------------------------------


def add_ticket_note(ticket_id: int, agent: str, note: str) -> dict:
    """Add a work note to a ticket's log so the team and the human can see progress.

    Writes ticket_log. agent is your own agent name.
    """
    if err := _require_agent(agent):
        return {"ok": False, "error": err}
    with _connect() as conn:
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket with id={ticket_id}."}
        cur = conn.execute(
            "INSERT INTO ticket_log (ticket_id, agent, note, logged_at) VALUES (?, ?, ?, ?)",
            (ticket_id, agent, note, _now()),
        )
    return {"ok": True, "log_id": cur.lastrowid}


def set_ticket_status(ticket_id: int, status: str, agent: str, note: str) -> dict:
    """Move a ticket to a new status and log why. Only the Boss should call this.

    Writes tickets.status and ticket_log. status is one of open, in_progress,
    waiting_on_approval, waiting_on_vendor, resolved. A ticket cannot be
    resolved while it still has a pending approval request.
    """
    if err := _require_agent(agent):
        return {"ok": False, "error": err}
    if status not in TICKET_STATUSES:
        return {"ok": False, "error": f"status must be one of {TICKET_STATUSES}."}
    with _connect() as conn:
        t = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"ok": False, "error": f"No ticket with id={ticket_id}."}
        if status == "resolved":
            pending = conn.execute(
                "SELECT COUNT(*) FROM approval_requests WHERE ticket_id = ? AND status = 'pending'", (ticket_id,)
            ).fetchone()[0]
            if pending:
                return {"ok": False, "error": f"Ticket {ticket_id} still has {pending} pending approval request(s)."}
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        conn.execute(
            "INSERT INTO ticket_log (ticket_id, agent, note, status_from, status_to, logged_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ticket_id, agent, note, t["status"], status, _now()),
        )
    return {"ok": True, "ticket_id": ticket_id, "status_from": t["status"], "status_to": status}


def draft_message(
    ticket_id: int, recipient_type: str, recipient: str, subject: str, body: str, author: str
) -> dict:
    """Save a message to a customer, vendor or landlord as a DRAFT on the board. Never sends it.

    Writes drafts. recipient_type is customer, vendor or landlord. A human
    reads and sends drafts; agents never email customers or call vendors.
    """
    if err := _require_agent(author):
        return {"ok": False, "error": err}
    if recipient_type not in DRAFT_RECIPIENTS:
        return {"ok": False, "error": f"recipient_type must be one of {DRAFT_RECIPIENTS}."}
    with _connect() as conn:
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket with id={ticket_id}."}
        cur = conn.execute(
            "INSERT INTO drafts (ticket_id, recipient_type, recipient, subject, body, author, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'draft', ?)",
            (ticket_id, recipient_type, recipient, subject, body, author, _now()),
        )
    return {"ok": True, "draft_id": cur.lastrowid, "status": "draft", "sent": False}


def create_quote(ticket_id: int, sku: str, size: str, qty: int, discount_pct: float, agent: str) -> dict:
    """Save a discounted price quote for a ticket. Refuses any price at or below unit cost.

    Reads pricing; writes quotes. The quote stays a draft; Customer Service
    puts it in a draft message for a human to send.
    """
    if err := _require_agent(agent):
        return {"ok": False, "error": err}
    preview = preview_discount(sku, qty, discount_pct)
    if not preview.get("found"):
        return {"ok": False, "error": preview["error"]}
    if not preview["above_cost"]:
        return {
            "ok": False,
            "error": f"Refused: ${preview['unit_price']} is not above unit cost ${preview['unit_cost']}. "
            f"Max discount that stays above cost is just under {preview['max_discount_pct_above_cost']}%.",
        }
    with _connect() as conn:
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket with id={ticket_id}."}
        cur = conn.execute(
            "INSERT INTO quotes (ticket_id, sku, size, qty, list_price, unit_price, discount_pct, unit_cost, "
            "margin_per_unit, total, created_by, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?)",
            (
                ticket_id, sku, size, qty, preview["list_price"], preview["unit_price"], discount_pct,
                preview["unit_cost"], preview["margin_per_unit"], preview["total"], agent, _now(),
            ),
        )
    return {"ok": True, "quote_id": cur.lastrowid, **{k: preview[k] for k in ("unit_price", "margin_per_unit", "total", "total_margin")}}


def request_payment(kind: str, ref_id: int, amount: float, reason: str, agent: str, ticket_id: int | None = None) -> dict:
    """Ask a human to approve paying an open vendor invoice or a lease's rent. Does NOT pay.

    Reads invoices / leases, cash_accounts and approval_requests; writes
    approval_requests (status pending). kind is invoice (ref_id = invoices.id)
    or rent (ref_id = leases.id). amount must equal the amount owed. Refuses
    duplicates, amounts above cash on hand, and anything already paid.
    Purchase-order payments are requested by create_purchase_order instead.
    """
    if err := _require_agent(agent):
        return {"ok": False, "error": err}
    if kind not in ("invoice", "rent"):
        return {"ok": False, "error": "kind must be 'invoice' or 'rent' (POs use create_purchase_order)."}
    with _connect() as conn:
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket with id={ticket_id}."}
        if kind == "invoice":
            row = conn.execute(
                "SELECT i.amount, i.status, v.name FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
                (ref_id,),
            ).fetchone()
            if row is None:
                return {"ok": False, "error": f"No invoice with id={ref_id}."}
            if row["status"] != "open":
                return {"ok": False, "error": f"Invoice {ref_id} is {row['status']}, not open."}
            owed, payee = row["amount"], row["name"]
        else:
            row = conn.execute("SELECT monthly_rent, landlord FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if row is None:
                return {"ok": False, "error": f"No lease with id={ref_id}."}
            owed, payee = row["monthly_rent"], row["landlord"]
        if round(amount, 2) != round(owed, 2):
            return {"ok": False, "error": f"Amount ${amount} does not match the ${owed} owed."}
        dup = conn.execute(
            "SELECT id FROM approval_requests WHERE kind = ? AND ref_id = ? AND status = 'pending'", (kind, ref_id)
        ).fetchone()
        if dup:
            return {"ok": False, "error": f"Approval request {dup['id']} is already pending for this {kind}."}
        cash = _cash_balance(conn) or 0.0
        if amount > cash:
            return {"ok": False, "error": f"Refused: ${amount} is more than the ${cash} in checking."}
        committed = _pending_total(conn)
        cur = conn.execute(
            "INSERT INTO approval_requests (kind, ref_id, ticket_id, amount, payee, reason, requested_by, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (kind, ref_id, ticket_id, amount, payee, reason, agent, _now()),
        )
    left = cash - committed - amount
    return {
        "ok": True,
        "request_id": cur.lastrowid,
        "status": "pending",
        "paid": False,
        "payee": payee,
        "amount": amount,
        "cash_on_hand": cash,
        "available_if_all_pending_approved": left,
        "warning": None if left >= 0 else "Pending requests now exceed cash; a human must choose which to approve.",
    }


def create_purchase_order(vendor_id: int, sku: str, size: str, qty: int, agent: str, ticket_id: int | None = None) -> dict:
    """Create a restock purchase order and ask a human to approve paying for it.

    Reads vendors, invoices, inventory, pricing, desk and cash_accounts;
    writes purchase_orders (awaiting_payment_approval) and approval_requests.
    Refuses if the vendor has an open invoice (vendors will not ship while
    unpaid) or the cost is more than cash on hand. The PO is only placed,
    with expected_arrival = today + lead_days, after a human approves it.
    """
    if err := _require_agent(agent):
        return {"ok": False, "error": err}
    if qty <= 0:
        return {"ok": False, "error": "qty must be > 0."}
    with _connect() as conn:
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket with id={ticket_id}."}
        v = conn.execute("SELECT id, name, lead_days FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if v is None:
            return {"ok": False, "error": f"No vendor with id={vendor_id}."}
        blocking = _open_invoices(conn, vendor_id)
        if blocking:
            ids = ", ".join(str(i["id"]) for i in blocking)
            return {"ok": False, "error": f"Refused: {v['name']} has open invoice(s) {ids} and will not ship until paid."}
        if conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone() is None:
            return {"ok": False, "error": f"No inventory row for sku={sku!r}, size={size!r}."}
        p = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if p is None:
            return {"ok": False, "error": f"No pricing row for sku={sku!r}."}
        total = round(p["unit_cost"] * qty, 2)
        cash = _cash_balance(conn) or 0.0
        if total > cash:
            return {"ok": False, "error": f"Refused: PO total ${total} is more than the ${cash} in checking."}
        committed = _pending_total(conn)
        po = conn.execute(
            "INSERT INTO purchase_orders (vendor_id, sku, size, qty, unit_cost, total, ticket_id, status, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'awaiting_payment_approval', ?, ?)",
            (vendor_id, sku, size, qty, p["unit_cost"], total, ticket_id, agent, _now()),
        ).lastrowid
        req = conn.execute(
            "INSERT INTO approval_requests (kind, ref_id, ticket_id, amount, payee, reason, requested_by, status, created_at) "
            "VALUES ('purchase_order', ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (po, ticket_id, total, v["name"], f"Restock {qty} x {sku} {size}", agent, _now()),
        ).lastrowid
        eta = (_shop_today(conn) + timedelta(days=v["lead_days"])).isoformat()
    left = cash - committed - total
    return {
        "ok": True,
        "po_id": po,
        "request_id": req,
        "total": total,
        "status": "awaiting_payment_approval",
        "expected_arrival_if_approved_today": eta,
        "available_if_all_pending_approved": left,
        "warning": None if left >= 0 else "Pending requests now exceed cash; a human must choose which to approve.",
    }


# --------------------------------------------------------------------------
# Human-only tools (the agent backend filters these out)
# --------------------------------------------------------------------------


def approve_request(request_id: int, approved_by: str) -> dict:
    """HUMAN ONLY. Approve a pending request and make the payment from checking.

    Writes payments, cash_accounts, approval_requests and, by kind, invoices
    (status paid), leases (next_due + 1 month) or purchase_orders (placed,
    expected_arrival). Refuses agent names as approver and any payment that
    would make the balance negative.
    """
    if not approved_by.strip() or approved_by.strip().lower() in AGENT_NAMES:
        return {"ok": False, "error": "approved_by must be a human's name, not an agent."}
    with _connect() as conn:
        today = _shop_today(conn)
        r = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,)).fetchone()
        if r is None:
            return {"ok": False, "error": f"No approval request with id={request_id}."}
        if r["status"] != "pending":
            return {"ok": False, "error": f"Request {request_id} is {r['status']}, not pending."}
        cash = _cash_balance(conn)
        if cash is None or cash - r["amount"] < 0:
            return {"ok": False, "error": f"Refused: paying ${r['amount']} would make checking (${cash}) negative."}
        if r["kind"] == "purchase_order":
            po = conn.execute("SELECT vendor_id FROM purchase_orders WHERE id = ?", (r["ref_id"],)).fetchone()
            if _open_invoices(conn, po["vendor_id"]):
                return {"ok": False, "error": "Refused: vendor still has an open invoice and will not ship."}
        pay_id = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, 'checking', ?, ?)",
            (r["kind"], r["ref_id"], r["amount"], today.isoformat(), approved_by),
        ).lastrowid
        conn.execute("UPDATE cash_accounts SET balance = balance - ?, date = ? WHERE name = 'checking'", (r["amount"], today.isoformat()))
        effect: dict = {}
        if r["kind"] == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (r["ref_id"],))
            effect = {"invoice_id": r["ref_id"], "invoice_status": "paid"}
        elif r["kind"] == "rent":
            lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (r["ref_id"],)).fetchone()
            nxt = _add_months(date.fromisoformat(lease["next_due"]), 1).isoformat()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (nxt, r["ref_id"]))
            effect = {"lease_id": r["ref_id"], "next_due": nxt}
        else:
            lead = conn.execute(
                "SELECT v.lead_days FROM purchase_orders p JOIN vendors v ON v.id = p.vendor_id WHERE p.id = ?",
                (r["ref_id"],),
            ).fetchone()["lead_days"]
            eta = (today + timedelta(days=lead)).isoformat()
            conn.execute("UPDATE purchase_orders SET status = 'placed', expected_arrival = ? WHERE id = ?", (eta, r["ref_id"]))
            effect = {"po_id": r["ref_id"], "po_status": "placed", "expected_arrival": eta}
        conn.execute(
            "UPDATE approval_requests SET status = 'paid', decided_by = ?, decided_at = ?, payment_id = ? WHERE id = ?",
            (approved_by, _now(), pay_id, request_id),
        )
        balance = _cash_balance(conn)
    return {"ok": True, "request_id": request_id, "payment_id": pay_id, "amount": r["amount"], "cash_after": balance, **effect}


def reject_request(request_id: int, rejected_by: str, note: str = "") -> dict:
    """HUMAN ONLY. Reject a pending payment request; no money moves.

    Writes approval_requests and, for a purchase order, purchase_orders (rejected).
    """
    if not rejected_by.strip() or rejected_by.strip().lower() in AGENT_NAMES:
        return {"ok": False, "error": "rejected_by must be a human's name, not an agent."}
    with _connect() as conn:
        r = conn.execute("SELECT kind, ref_id, status FROM approval_requests WHERE id = ?", (request_id,)).fetchone()
        if r is None:
            return {"ok": False, "error": f"No approval request with id={request_id}."}
        if r["status"] != "pending":
            return {"ok": False, "error": f"Request {request_id} is {r['status']}, not pending."}
        conn.execute(
            "UPDATE approval_requests SET status = 'rejected', decided_by = ?, decided_at = ?, decision_note = ? WHERE id = ?",
            (rejected_by, _now(), note, request_id),
        )
        if r["kind"] == "purchase_order":
            conn.execute("UPDATE purchase_orders SET status = 'rejected' WHERE id = ?", (r["ref_id"],))
    return {"ok": True, "request_id": request_id, "status": "rejected"}


def resolve_ticket(ticket_id: int, resolved_by: str, note: str = "") -> dict:
    """HUMAN ONLY. Mark a ticket resolved from the dashboard after reviewing the team's work.

    Writes tickets.status and ticket_log. Refuses agent names and any ticket
    that still has a pending approval request.
    """
    if not resolved_by.strip() or resolved_by.strip().lower() in AGENT_NAMES:
        return {"ok": False, "error": "resolved_by must be a human's name, not an agent."}
    with _connect() as conn:
        t = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"ok": False, "error": f"No ticket with id={ticket_id}."}
        pending = conn.execute(
            "SELECT COUNT(*) FROM approval_requests WHERE ticket_id = ? AND status = 'pending'", (ticket_id,)
        ).fetchone()[0]
        if pending:
            return {"ok": False, "error": f"Ticket {ticket_id} still has {pending} pending approval request(s)."}
        conn.execute("UPDATE tickets SET status = 'resolved' WHERE id = ?", (ticket_id,))
        conn.execute(
            "INSERT INTO ticket_log (ticket_id, agent, note, status_from, status_to, logged_at) VALUES (?, ?, ?, ?, 'resolved', ?)",
            (ticket_id, f"human:{resolved_by.strip()}", note or "Marked resolved from the dashboard.", t["status"], _now()),
        )
    return {"ok": True, "ticket_id": ticket_id, "status_from": t["status"], "status_to": "resolved"}


HUMAN_ONLY_TOOLS = {"approve_request", "reject_request", "resolve_ticket"}

for _tool in (
    check_stock,
    list_inventory,
    get_vendor_status,
    get_rent_due,
    list_open_tickets,
    list_tickets,
    get_ticket,
    get_cash_position,
    list_approval_requests,
    preview_discount,
    add_ticket_note,
    set_ticket_status,
    draft_message,
    create_quote,
    request_payment,
    create_purchase_order,
    approve_request,
    reject_request,
    resolve_ticket,
):
    mcp.tool(_tool)


if __name__ == "__main__":
    mcp.run(show_banner=False)
