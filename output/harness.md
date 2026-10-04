# Campus Customs Multi-Agent Harness

This file describes the data, tools, agents, routes, dashboard, and guardrails behind Campus Customs Multi-Agent Operations.

- **Original database:** `data/campus_customs.db`. Read-only reference; never modified. Copy it over the working file (or `POST /api/reset`) to reset.
- **Working database:** `data/campus_customs_new.db`. The MCP server reads and writes this copy, and the agents and backend reach it only through MCP.
- **Model:** `gpt-6-luna` through Portkey for every agent.

**Contents:** [Database tables](#database-tables) · [The 3 tickets](#the-3-open-tickets-and-how-they-link) · [MCP tools](#mcp-tools-all-19-after-problem-8) · [Agent team](#agent-team-problem-5) · [Backend routes](#backend-routes-problem-7) · [Dashboard](#dashboard-problem-8) · [Audit trail](#audit-trail) · [Problem 9 run](#problem-9-run-resolving-the-three-tickets) · [Safety](#safety)

```text
React board (frontend/, :5173) ──HTTP──▶ FastAPI (backend/main.py, :8000)
                                             │  routes: tickets · run · events · approvals · cash · reset
                                             ├─▶ agent team (backend/agents/, PydanticAI, gpt-6-luna via Portkey)
                                             │      Boss ⇄ Inventory ⇄ Accounting ⇄ Facilities ⇄ Customer Service
                                             │      each agent: filtered MCP toolset + delegate()
                                             └─▶ MCP client ──stdio──▶ campus-customs MCP server (mcp_server/server.py)
                                                                          └─▶ data/campus_customs_new.db
every agent loop step ─▶ output/audit_trail.json (append-only)
```

## Database tables

The 10 original tables are below. The MCP server also adds 5 work tables to the working copy only (`approval_requests`, `purchase_orders`, `quotes`, `drafts`, `ticket_log`), which are described under [Work tables](#work-tables-added-to-the-working-copy).

### `desk`
Fields: `date_today`, `notes`

Holds the shop's "today" (`2026-08-31`), which agents must use, rather than the real clock, to decide what is due or overdue.

### `tickets`
Fields: `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at`

The work queue on the board: Boss reads each ticket's `type` and its link columns (`sku`/`size`/`qty`, `lease_id`, `invoice_id`) to decide which agent handles it.

### `inventory`
Fields: `sku`, `name`, `size`, `qty`, `location` (primary key: `sku` + `size`)

Inventory agent checks on-hand stock by SKU and size here to spot shortfalls before an order is promised.

### `pricing`
Fields: `sku`, `unit_cost`, `list_price`

Accounting uses cost vs. list price to compute margins and set a floor for any discount, and to price restock purchase orders.

### `vendors`
Fields: `id`, `name`, `specialty`, `lead_days`

Inventory matches a SKU to the vendor whose `specialty` fits and uses `lead_days` to give customers an honest restock date.

### `invoices`
Fields: `id`, `vendor_id` → `vendors.id`, `amount`, `due_date`, `status`, `description`

Shows what the shop owes each vendor; an `open` invoice blocks that vendor from shipping new product until it's paid.

### `leases`
Fields: `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`

Facilities uses this to know rent amount and due date for the shop space.

### `cash_accounts`
Fields: `name`, `balance`, `date`

The only source of money (`checking` = $3,400). The pay tool must check this balance and refuse any payment that would make it go negative.

### `payments`
Fields: `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`

The ledger of money that actually went out (empty at start). Every row must carry the human approver in `approved_by`, and `kind` + `ref_id` point back to the invoice or lease that was paid.

## The 3 open tickets and how they link

Today is **2026-08-31**. Cash on hand is **$3,400**.

| Ticket | Type | Links to | What it really requires |
|---|---|---|---|
| **101**: Tauhid Zaman, 1 Bulldog tee, size S | `customer_order` | `inventory` (`CC-TEE-WHITE`/S → **qty 0**), `invoice_id` **501** → `invoices` → vendor 1 Bulldog Print Co (apparel, 5-day lead) | Out of stock. Invoice 501 ($840, due 2026-08-28) is **open and overdue**, so Bulldog Print won't ship until it's paid with human approval. Then a restock PO and a customer message saying the tee arrives in about 5 days. |
| **102**: Elm City Properties, rent due | `rent_notice` | `lease_id` **1** → `leases` (Chapel Street shop, $2,400, due **2026-09-02**) | Pay $2,400 rent with human approval before 9/2; record it in `payments`, reduce `cash_accounts`, and advance `leases.next_due`. |
| **103**: Yale AI Club, 20 hoodies size M, bulk discount | `price_override` | `inventory` (`CC-HOOD-NAVY`/M → **qty 8**), `pricing` (cost $22, list $58), apparel vendor = Bulldog Print (same open invoice 501) | Short by 12. Accounting must set a discount that keeps margin above $22 cost; restocking 12 units (12 × $22 = $264) also depends on invoice 501 being paid. Customer Service drafts the quote. |

### Cross-ticket constraints
- Tickets **101 and 103 both depend on invoice 501.** Paying it once unblocks both restocks.
- **Cash is tight:** $840 (invoice) + $2,400 (rent) = $3,240, which leaves **$160**. That isn't enough for a $264 hoodie restock PO, so Boss has to set priorities, and the pay tool must refuse anything that would go negative.
- Nothing in the data brings money in, so cash only goes down.
- Customer and vendor messages are drafts on the board only and are never sent.

## MCP tools for the three tickets (Problem 3)

All agents reach the database only through the FastMCP server in `mcp_server/server.py`, which uses `data/campus_customs_new.db`. The three tools below are read-only. They return `"found": false` instead of guessing when a row is missing, and they use `desk.date_today` as "today."

### 1. `check_stock(sku, size, qty_needed=1)`
- **Reads:** `inventory` (qty, location), `pricing` (unit_cost, list_price)
- **Unlocks:** **101** and **103**
- **Why it fits:** Ticket 101 asks for 1 `CC-TEE-WHITE` in size S and ticket 103 asks for 20 `CC-HOOD-NAVY` in size M. This tool returns the exact shortfall for that SKU and size (101: 0 on hand, short 1; 103: 8 on hand, short 12) plus cost and list price, so Inventory knows how much to restock and Accounting can set a discount for the AI Club's 20 hoodies without dropping below the $22 unit cost.

### 2. `get_vendor_status(vendor_id=None)`
- **Reads:** `vendors` (specialty, lead_days), `invoices` (open status, amount, due_date), `desk` (date_today)
- **Unlocks:** **101** and **103**
- **Why it fits:** Both tickets need an apparel restock from Bulldog Print Co, which has open invoice 501 ($840, 3 days overdue). This tool returns `can_ship = false` plus the 5-day lead time, so the agents know invoice 501 must be paid (with human approval) before any tee or hoodie PO, and they can give each customer an honest arrival date.

### 3. `get_rent_due(lease_id)`
- **Reads:** `leases` (monthly_rent, next_due, landlord), `desk` (date_today), `cash_accounts` (balance)
- **Unlocks:** **102**
- **Why it fits:** Ticket 102 links to `lease_id` 1. This tool confirms that $2,400 is due to Elm City Properties on 2026-09-02, which is 2 days from shop-today, and that the $3,400 in checking covers it. Facilities can then send a correctly sized payment request for human approval before the due date.

### Connection and smoke test
- `.mcp.json` registers the server as `campus-customs` and runs `.venv/Scripts/python.exe mcp_server/server.py` over stdio.
- `mcp_server/smoke_test.py` starts the server from `.mcp.json` with a real MCP client and calls each tool for its ticket:
  - `check_stock` for tickets 101 and 103
  - `get_vendor_status` for vendor 1 (tickets 101 and 103)
  - `get_rent_due` for lease 1 (ticket 102)
- It then checks each output against direct SQLite queries. The results are in `output/mcp_smoke.json`, and every test has `matches_db: true`.

## Agent team (Problem 5)

The team is built with PydanticAI in `backend/`. Every agent runs on **`gpt-6-luna` through Portkey** (`PORTKEY_API_KEY` from `.env`, set in `backend/config.py`). Each agent has its own prompt in `backend/prompts/<agent>.md`. Data types (`AgentSpec`, `AgentReport`, `BossReport`, `TeamDeps`, `RunState`, `AuditEntry`) live in `backend/models.py`.

| Agent | File / prompt | Owns | MCP tools it may call |
|---|---|---|---|
| **Boss** | `agents/boss.py`, `prompts/boss.md` | The board: triage, cross-ticket priorities (shared blockers, tight cash), delegation, ticket status, final report to the human | `list_open_tickets`, `get_ticket`, `get_cash_position`, `list_approval_requests`, `set_ticket_status`, `add_ticket_note` |
| **Inventory** | `agents/inventory.py`, `prompts/inventory.md` | Stock and shortfalls, vendor match by specialty, lead time and `can_ship`, restock POs | `get_ticket`, `check_stock`, `list_inventory`, `get_vendor_status`, `get_cash_position`, `create_purchase_order`, `draft_message`, `add_ticket_note` |
| **Accounting** | `agents/accounting.py`, `prompts/accounting.md` | Cash position, vendor-invoice payment requests, margins and discount quotes | `get_ticket`, `check_stock`, `get_vendor_status`, `get_cash_position`, `list_approval_requests`, `preview_discount`, `create_quote`, `request_payment`, `draft_message`, `add_ticket_note` |
| **Facilities** | `agents/facilities.py`, `prompts/facilities.md` | Lease, rent timing, rent payment request, landlord drafts | `get_ticket`, `get_rent_due`, `get_cash_position`, `list_approval_requests`, `request_payment`, `draft_message`, `add_ticket_note` |
| **Customer Service** | `agents/customer_service.py`, `prompts/customer_service.md` | Honest customer replies (drafts only) built from tool facts and saved quotes/POs | `get_ticket`, `check_stock`, `list_inventory`, `get_vendor_status`, `draft_message`, `add_ticket_note` |

**Full connectivity.** Every agent also has a `delegate(to_agent, task, ticket_id)` tool that runs any other agent's loop and returns its structured report (`AgentReport`, or `BossReport` from the Boss). There is no fixed hierarchy: Customer Service can ask Accounting for a quote, Inventory can ask Accounting about cash, and so on.

**Agent loop.** `backend/agents/loop.py` runs each agent with `Agent.iter()`: task → model request → model response (tool calls) → tool results → ... → structured output. `run_team()` opens **one** stdio session to the MCP server, using the `.mcp.json` entry, and hands each agent a *filtered* view with only its own tools. Shop facts therefore come only from MCP. There is no second tool layer.

**Run:** `.venv/Scripts/python.exe backend/run_team.py` (add `--db <copy.db>` to work on a scratch copy).

## MCP tools (all 19, after Problem 8)

R = reads, W = writes. The new work tables (`approval_requests`, `purchase_orders`, `quotes`, `drafts`, `ticket_log`) are created only in the working copy, the first time the server connects.

| Tool | Added | Tables | Used by | What it does |
|---|---|---|---|---|
| `check_stock` | P3 | R `inventory`, `pricing` | Inventory, Accounting, Customer Service | On-hand qty, shortfall, location, cost and list price for one SKU/size |
| `get_vendor_status` | P3 | R `vendors`, `invoices`, `desk` | Inventory, Accounting, Customer Service | Lead days, open invoices (days overdue), `can_ship` |
| `get_rent_due` | P3 | R `leases`, `desk`, `cash_accounts` | Facilities | Rent, due date, days until due, whether cash covers it |
| `list_open_tickets` | P5 | R `tickets`, `desk` | Boss | The work queue (all non-resolved tickets) and shop date |
| `list_tickets` | P7 | R `tickets`, `desk` | Dashboard API (`GET /api/tickets`) | Every ticket, open or resolved, with an `is_open` flag |
| `get_ticket` | P5 | R `tickets`, `inventory`, `pricing`, `invoices`, `vendors`, `leases`, `ticket_log`, `drafts`, `quotes`, `purchase_orders`, `approval_requests` | All | One ticket, its linked rows, and all work done on it so far (prevents repeat work) |
| `list_inventory` | P5 | R `inventory`, `pricing` | Inventory, Customer Service | All sizes of a SKU (or all stock), so customers can be offered sizes that are on hand |
| `get_cash_position` | P5 | R `cash_accounts`, `approval_requests`, `payments` | Boss, Inventory, Accounting, Facilities | Cash on hand, pending total, `available_after_pending`, recent payments |
| `list_approval_requests` | P5 | R `approval_requests` | Boss, Accounting, Facilities | The human approval queue (stops duplicate requests) |
| `preview_discount` | P5 | R `pricing` | Accounting | Price, margin, and total for a discount %, plus the max % that stays above cost (saves nothing) |
| `create_quote` | P5 | R `pricing`; W `quotes` | Accounting | Saves a draft quote; **refuses any price at or below unit cost** |
| `request_payment` | P5 | R `invoices`, `vendors`, `leases`, `cash_accounts`; W `approval_requests` | Accounting (invoices), Facilities (rent) | Files a **pending** request for a human; exact amount only, no duplicates, no amount above cash; **does not pay** |
| `create_purchase_order` | P5 | R `vendors`, `invoices`, `inventory`, `pricing`, `desk`, `cash_accounts`; W `purchase_orders`, `approval_requests` | Inventory | Restock PO plus pending payment request; **refuses if the vendor has an open invoice** or cost exceeds cash |
| `draft_message` | P5 | W `drafts` | All specialists | Saves a customer/vendor/landlord message as a draft; **never sends** |
| `add_ticket_note` | P5 | W `ticket_log` | All | Work note on a ticket |
| `set_ticket_status` | P5 | W `tickets`, `ticket_log` | Boss | Moves status (`open`, `in_progress`, `waiting_on_approval`, `waiting_on_vendor`, `resolved`); refuses `resolved` while an approval is pending |
| `approve_request` | P5 | R `desk`, `approval_requests`, `purchase_orders`, `invoices`; W `payments`, `cash_accounts`, `approval_requests`, plus `invoices`/`leases`/`purchase_orders` | **Human only** | The only tool that moves money. Rejects agent names as approver, **refuses a negative balance**, and re-checks that the vendor can ship. Then marks the invoice paid, moves the lease to next month, or places the PO with an ETA |
| `reject_request` | P5 | W `approval_requests`, `purchase_orders` | **Human only** | Declines a request; no money moves |
| `resolve_ticket` | P8 | R `approval_requests`; W `tickets`, `ticket_log` | **Human only** (dashboard "Mark resolved") | Closes a ticket; refuses agent names and tickets with pending approvals |

`approve_request`, `reject_request` and `resolve_ticket` are on the server for the human dashboard. No agent spec lists them, `backend/agents/__init__.py` asserts that, and the per-agent filter means the model never sees them.

### Work tables added to the working copy

| Table | Fields | Why |
|---|---|---|
| `approval_requests` | `id`, `kind` (invoice/rent/purchase_order), `ref_id`, `ticket_id`, `amount`, `payee`, `reason`, `requested_by`, `status` (pending/paid/rejected), `created_at`, `decided_by`, `decided_at`, `decision_note`, `payment_id` | The human approval queue; links every payment back to the agent that asked and the human who approved |
| `purchase_orders` | `id`, `vendor_id`, `sku`, `size`, `qty`, `unit_cost`, `total`, `ticket_id`, `status`, `created_by`, `created_at`, `expected_arrival` | Restock orders; ETA is set only when paid (shop date + `lead_days`) |
| `quotes` | `id`, `ticket_id`, `sku`, `size`, `qty`, `list_price`, `unit_price`, `discount_pct`, `unit_cost`, `margin_per_unit`, `total`, `created_by`, `status`, `created_at` | Discount quotes Customer Service can cite exactly |
| `drafts` | `id`, `ticket_id`, `recipient_type`, `recipient`, `subject`, `body`, `author`, `status`, `created_at` | Outgoing messages waiting for a human to send |
| `ticket_log` | `id`, `ticket_id`, `agent`, `note`, `status_from`, `status_to`, `logged_at` | Per-ticket history of who did what |

## Backend routes (Problem 7)

`backend/main.py` (FastAPI). Start it from `backend/` with `uvicorn main:app --reload --port 8000` → `http://localhost:8000` (docs at `/docs`). Every shop read and write goes through one long-lived MCP session to the same `campus-customs` server the agents use.

- `GET /api/tickets`: the three tickets with `status` and `is_open` (open vs. resolved).
- `GET /api/tickets/{ticket_id}`: one ticket with its linked rows, drafts, quotes, POs and approval requests.
- `POST /api/tickets/{ticket_id}/run`: starts the agent team on that ticket in the background and returns a `run_id` (202). Returns 409 if a run is already going.
- `POST /api/tickets/{ticket_id}/resolve` (body `{"resolved_by": "<human name>"}`): the human clicked Mark resolved, so the ticket is closed. Refused while it has pending approvals. (Added in Problem 8.)
- `GET /api/runs` · `GET /api/runs/{run_id}`: run status (`running`/`done`/`failed`) and, when done, the Boss's report.
- `GET /api/events?run_id=&ticket_id=&after_seq=&limit=`: recent agent events from `audit_trail.json`, showing what each agent said, the tools it called (with arguments), tool results, and delegations, so the board can refresh.
- `GET /api/approvals?status=pending|paid|rejected|all`: payment and purchase requests the agents prepared.
- `POST /api/approvals/{request_id}/approve` (body `{"approved_by": "<human name>"}`): the human clicked Approve, so the request is paid from checking. **The only route that changes cash.** It refuses agent names, negative balances, and approvals during a run.
- `POST /api/approvals/{request_id}/reject` (body `{"rejected_by": "...", "note": "..."}`): declines a request, and no money moves.
- `GET /api/cash`: the current checking balance from `cash_accounts`, plus pending total and available after pending.
- `POST /api/reset`: copies the original `campus_customs.db` over `campus_customs_new.db` for a fresh run. The audit trail is kept, and the route refuses during a run.
- `GET /api/health`: server is up, which DB and audit file it uses, and any active run.

## Dashboard (Problem 8)

`frontend/` (React + Vite + TypeScript, Yale Blue and white). Run `npm run dev` there, which serves `http://localhost:5173` and calls the backend at `VITE_API_BASE` in `frontend/.env` (`http://localhost:8000`). The backend's CORS allows `http(s)://localhost:5173` and `http(s)://127.0.0.1:5173`. `?ticket=101` opens the board on a ticket. Design choices are in `output/design.md`.

| Board area | What it shows | Routes it calls |
|---|---|---|
| Tickets (left) | The 3 tickets, status pill (Open / In progress / Needs approval / Ready to close / Waiting on vendor / Resolved), **Run team ▸**, and a RESOLVED stamp | `GET /api/tickets`, `POST /api/tickets/{id}/run` |
| Checking (left) | Large animated balance that ticks down after a payment, pending total, left-if-all-approved, ledger of paid requests grouped per ticket | `GET /api/cash`, `GET /api/approvals?status=all` |
| Agent roster (center) | 5 agents, each with its own color, icon, role label, and live status (idle / thinking / using tool / done / error) | `GET /api/events?run_id=` polled every 1.2 s |
| Feed (center) | Chat bubbles for speech, delegations and reports; monospace chips for tool calls and results; red chips for refusals | `GET /api/events`, `GET /api/runs/{id}` |
| Approvals (right) | Bold card: amount, payee, reason, requesting agent, checking-after preview, **Approve / Reject** (locked during a run) | `GET /api/approvals`, `POST /api/approvals/{id}/approve` · `/reject` |
| What each agent did (right) | Each agent's report summary, actions, and "needs you" | `GET /api/events` (agent reports) |
| Header | "Approving as" name, **Reset shop**, **Mark resolved ✓** on the stage | `POST /api/reset`, `POST /api/tickets/{id}/resolve` |

The board is sized for laptops. From 1201px wide up, it's one screen tall and the columns scroll inside themselves, and on wide monitors it's capped at 1480px and centered.

## Audit trail

Each run appends entries to `output/audit_trail.json`, one JSON array that is never wiped. `backend/audit.py` writes each new entry just before the closing `]`. Each entry has `run_id`, `seq`, `logged_at`, `kind`, `agent`, `chain` (who delegated to whom), `depth`, `ticket_id`, `step`, `node`, `summary`, and `detail`:

- `run_start` / `run_end`: the task, model, database, limits, and totals (delegations, tokens, model requests).
- `agent_start`: the task given, the model, the prompt file and its SHA-256, the run context, the allowed MCP tools, and the limits.
- `agent_step`: one per loop node. `model_request` records the tool results sent back. `model_response` records tool names, arguments, call IDs, text, reasoning summary, and token usage. `end` marks the end of the loop.
- `delegation`: from → to, the full task, and whether it was refused and why.
- `agent_end`: the full structured report (or error), the agent's usage, and running run tokens.

Long tool results are clipped at 4,000 characters.

## Problem 9 run: resolving the three tickets

The working DB was reset (`POST /api/reset`), giving **starting checking $3,400.00**. Each ticket was then run from the board until resolved, with a human approving every payment on the board. The full itemization is in `output/desk_tickets.html` (Cash tab) and `output/resolved_tickets.json`, and screenshots are in `output/resolved_board.html`.

| Ticket | Runs | Delegations | Human approvals | Cash change | Closed by |
|---|---|---|---|---|---|
| 101 tee | 3 | Accounting, Customer Service · Inventory, Customer Service · Customer Service | #1 invoice 501 **$840**, #2 PO #1 (1 tee) **$8** | **−$848.00** | Human (Boss left `waiting_on_vendor`, ETA 2026-09-05) |
| 102 rent | 2 | Facilities · (none) | #3 rent lease 1 **$2,400** | **−$2,400.00** | Boss (`resolved` after seeing payment #3) |
| 103 hoodies | 1 | Accounting, Customer Service | none | **$0.00** (quote #1: 20% off, $46.40 × 20 = $928; $264 restock unaffordable) | Human |

**Ending checking: $3,400.00 − $848.00 − $2,400.00 − $0.00 = $152.00**, which matches `cash_accounts.checking` in the working DB. Run totals: 6 team runs, 8 delegations, 65 model calls, and 236,262 tokens, all appended to `output/audit_trail.json`.

## Safety

### Guardrails for real customers and real money
- **A human approves every payment.** Agents can only file requests. The one paying tool is outside every agent's toolset, refuses agent names as approver, and records `approved_by` on every `payments` row. A real business would also add sign-in for approvers, two-person approval above a dollar threshold, and a daily payment cap.
- **No overdrafts, no overpayment.** Payments that would push cash below zero are refused at pay time, and requests must exactly match what is owed. Duplicate requests are blocked, and `available_after_pending` warns before the queue exceeds cash.
- **Nothing is sent automatically.** Customer, vendor, and landlord messages are drafts only. Prompts forbid exposing internal matters (unpaid bills, cash) to customers. A real shop would add a human review step and a block-list check before anything goes out.
- **Facts only from the database.** Tools return "not found" instead of guessing. Prompts require every number to come from a tool, and Customer Service may quote only saved quotes and PO dates.
- **Business rules enforced in code, not just prompts.** Price never at or below cost, no PO to a vendor with an open invoice, no resolving a ticket with pending approvals, and shop date from `desk`. A real business would add a cap on discount size and a margin floor set by the owner.
- **Least privilege.** Each agent sees only the MCP tools for its job, and only the Boss changes ticket status. The three human-only tools (`approve_request`, `reject_request`, `resolve_ticket`) are reachable only through the dashboard routes.
- **The board enforces it too.** Every approval, rejection and manual resolve needs a named human ("Approving as"). Approvals and reset lock while a run is in progress, so cash can't change under an agent mid-decision. Approve is disabled when the payment would overdraw the account.
- **Audit and reset.** Every model call, tool call, and delegation is in the append-only audit trail. The original DB stays untouched for resets. In production, also protect PII in logs and keep the key in a secrets manager (the key is never logged here).

### Limits that keep token use in check (`backend/config.py`)
| Limit | Value |
|---|---|
| Delegation depth (boss → A → B → C) | 3 |
| Delegations per run (whole team) | 12 |
| No self-delegation, no delegating back up the chain | enforced in `delegate` |
| Model calls per agent loop | 14 |
| Tool calls per agent loop | 30 |
| Tokens per agent loop | 200,000 |
| Tokens per run (whole team; each new loop gets only what is left) | 600,000 |
| One model call timeout / retries | 60 s / 4 |
| Wall clock per run | 900 s |
| Audit text per field | 4,000 chars |

When a limit is hit, the agent gets a clear refusal or error and reports what it finished, rather than crashing the run. Prompts also tell agents to read `get_ticket` first so they do not repeat work, to give each delegation one complete task, and not to retry a refused action the same way.
