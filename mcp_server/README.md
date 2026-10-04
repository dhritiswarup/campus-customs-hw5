# Campus Customs MCP Server

This is the only way the Campus Customs agent team (Boss, Inventory, Accounting, Facilities, Customer Service) gets at shop data. Every agent calls these tools instead of writing SQL. Built with [FastMCP](https://gofastmcp.com).

**Database:** `data/campus_customs_new.db`, the working copy. The original `data/campus_customs.db` is never touched. To reset, copy the original over the working copy. For tests, set `CAMPUS_CUSTOMS_DB` to point the server at a scratch copy.

**Rules:**
- Tools only return what's in the database. If a row is missing, they return `"found": false` (or `"ok": false`) with an error and never a guessed value.
- "Today" comes from `desk.date_today`, not the computer clock.
- No tool sends anything. Messages are saved as drafts.
- Agents can only *request* payments. Money moves only through `approve_request`, which is for humans and refuses any payment that would push cash negative.

## Tools (19)

### Read

| Tool | Reads | Returns |
|---|---|---|
| `check_stock(sku, size, qty_needed=1)` | `inventory`, `pricing` | Stock on hand, shortfall vs. the order, location, unit cost, list price |
| `list_inventory(sku=None)` | `inventory`, `pricing` | Every size of a SKU (or all stock) with qty, cost, price |
| `get_vendor_status(vendor_id=None)` | `vendors`, `invoices`, `desk` | Specialty, lead days, open invoices with days overdue, `can_ship` (false while any invoice is unpaid) |
| `get_rent_due(lease_id)` | `leases`, `desk`, `cash_accounts` | Rent, due date, days until due, whether cash covers it |
| `list_open_tickets()` | `tickets`, `desk` | Every non-resolved ticket, oldest first |
| `list_tickets()` | `tickets`, `desk` | Every ticket, open or resolved, with `is_open` (for the dashboard) |
| `get_ticket(ticket_id)` | `tickets` + linked `inventory`/`pricing`, `invoices`/`vendors`, `leases`; `ticket_log`, `drafts`, `quotes`, `purchase_orders`, `approval_requests` | One ticket with its linked rows and all work done on it |
| `get_cash_position()` | `cash_accounts`, `approval_requests`, `payments` | Cash on hand, pending requests and total, `available_after_pending`, recent payments |
| `list_approval_requests(status="pending")` | `approval_requests` | The approval queue (pending / paid / rejected / all) |
| `preview_discount(sku, qty, discount_pct)` | `pricing` | Unit price, margin, total, `above_cost`, max discount that stays above cost; saves nothing |

### Write (agents; nothing here pays or sends)

| Tool | Reads → Writes | Does |
|---|---|---|
| `add_ticket_note(ticket_id, agent, note)` | → `ticket_log` | Work note on a ticket |
| `set_ticket_status(ticket_id, status, agent, note)` | `tickets`, `approval_requests` → `tickets`, `ticket_log` | Changes status; refuses `resolved` while an approval is pending |
| `draft_message(ticket_id, recipient_type, recipient, subject, body, author)` | → `drafts` | Saves a customer/vendor/landlord draft; never sends |
| `create_quote(ticket_id, sku, size, qty, discount_pct, agent)` | `pricing` → `quotes` | Saves a draft quote; refuses price ≤ unit cost |
| `request_payment(kind, ref_id, amount, reason, agent, ticket_id=None)` | `invoices`, `vendors`, `leases`, `cash_accounts` → `approval_requests` | Pending request for an invoice or rent; exact amount, no duplicates, not above cash |
| `create_purchase_order(vendor_id, sku, size, qty, agent, ticket_id=None)` | `vendors`, `invoices`, `inventory`, `pricing`, `desk`, `cash_accounts` → `purchase_orders`, `approval_requests` | Restock PO and its pending payment; refuses if the vendor has an open invoice or the cost exceeds cash |

### Human only (filtered out of every agent's toolset)

| Tool | Reads → Writes | Does |
|---|---|---|
| `approve_request(request_id, approved_by)` | `approval_requests`, `cash_accounts`, `purchase_orders`, `invoices`, `desk` → `payments`, `cash_accounts`, `approval_requests`, `invoices` / `leases` / `purchase_orders` | Pays from checking. Refuses agent names and negative balances, then marks the invoice paid, advances `leases.next_due` one month, or places the PO with `expected_arrival` |
| `reject_request(request_id, rejected_by, note="")` | → `approval_requests`, `purchase_orders` | Declines; no money moves |
| `resolve_ticket(ticket_id, resolved_by, note="")` | `approval_requests` → `tickets`, `ticket_log` | Closes a ticket from the dashboard; refuses agent names and tickets with pending approvals |

**Work tables** (`approval_requests`, `purchase_orders`, `quotes`, `drafts`, `ticket_log`) are created with `CREATE TABLE IF NOT EXISTS` in the working copy the first time a tool connects.

## Run

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe mcp_server/server.py
```

**Connect:** `.mcp.json` in the repo root registers the server as `campus-customs` (stdio: `python mcp_server/server.py`, run from the repo root with the venv active). MCP clients such as Claude Code load it from there. The agent backend (`backend/config.py`) launches the server from this same entry, filling in the venv's Python and the absolute script path so it works from any folder.

**Smoke test:** `.venv/Scripts/python.exe mcp_server/smoke_test.py` starts the server from `.mcp.json`, calls the three Problem 3 tools for their tickets, checks every value against SQLite, and writes `output/mcp_smoke.json`.
