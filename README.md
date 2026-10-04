# Campus Customs Multi-Agent Operations (HW5)

A five-agent team (**Boss, Inventory, Accounting, Facilities, Customer Service**) that runs a small Yale apparel shop's ticket board. The agents reach the shop's SQLite database only through an **MCP server**, a **FastAPI** backend runs them, and a **React** board lets a human watch them work and approve every payment.

```text
React board (frontend/, :5173) ──HTTP──▶ FastAPI (backend/main.py, :8000)
                                             ├─▶ agent team (PydanticAI, gpt-6-luna via Portkey)
                                             └─▶ MCP client ──stdio──▶ MCP server (mcp_server/server.py)
                                                                          └─▶ data/campus_customs_new.db
```

- **Model:** `gpt-6-luna` through Portkey for every agent (`backend/config.py`).
- **Databases:** `data/campus_customs.db` is the **original** and is never modified. `data/campus_customs_new.db` is the **working copy** the app reads and writes. Both are committed. The working copy is the state after the Problem 9 run: all 3 tickets resolved, checking $152.
- **Full documentation:** [`output/harness.md`](output/harness.md) covers tables, MCP tools, agents, API routes, the dashboard, and safety. [`output/design.md`](output/design.md) covers the board design.

## Layout

```text
hw5/
├── AI_prompts.md            prompts used to build each problem
├── requirements.txt         Python dependencies
├── .env.example             copy to .env and add PORTKEY_API_KEY
├── .mcp.json                registers the campus-customs MCP server (stdio)
├── data/                    campus_customs.db (original) + campus_customs_new.db (working copy)
├── mcp_server/              server.py (19 tools), smoke_test.py, README.md
├── backend/                 main.py (FastAPI), models.py, config.py, audit.py, run_team.py,
│   ├── agents/              boss / inventory / accounting / facilities / customer_service + loop.py
│   └── prompts/             one prompt file per agent
├── frontend/                React + Vite + TypeScript board
└── output/                  harness.md, design.md, mcp_smoke.json, desk_tickets.html,
                             resolved_tickets.json, resolved_board.html, audit_trail.json, github_url.txt
```

## Setup (once)

Requires Python 3.11+ and Node 18+.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cd frontend && npm install && cd ..

cp .env.example .env          # Windows: copy .env.example .env
# then edit .env and set PORTKEY_API_KEY
```

The real `.env` is in `.gitignore` and is never committed.

## 1. Copy the original DB to the working copy (clean run)

Whenever you want a clean shop (3 open tickets, $3,400 in checking, no agent work), copy the original over the working copy:

```bash
# macOS / Linux / Git Bash
cp data/campus_customs.db data/campus_customs_new.db
# Windows PowerShell
Copy-Item data\campus_customs.db data\campus_customs_new.db -Force
```

Stop the backend before copying the file by hand. While the backend is running, use the board's **Reset shop** button or `POST /api/reset` (step 5) instead. Either way, `output/audit_trail.json` is kept, because it is append-only.

## 2. Start the MCP server

The MCP server (`mcp_server/server.py`) talks to `data/campus_customs_new.db`.

- **With the app:** you don't need a separate terminal. The backend launches the server over stdio from `.mcp.json` when it starts, and again for each agent run.
- **On its own** (from the repo root, venv active), to run or test it directly:

  ```bash
  python mcp_server/server.py          # waits for an MCP client on stdio
  python mcp_server/smoke_test.py      # calls the Problem 3 tools and checks them against SQLite
  ```

  Claude Code and other MCP clients opened in the repo root pick it up from `.mcp.json`.

## 3. Start the FastAPI backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The backend is at `http://localhost:8000`, with interactive docs at `/docs`. Main routes:
- `GET /api/tickets`
- `POST /api/tickets/{id}/run`
- `GET /api/events`
- `POST /api/approvals/{id}/approve`
- `GET /api/cash`
- `POST /api/reset`

All of them are listed in `output/harness.md`. Note that `--reload` restarts the server when a `.py` file changes, which stops any agent run in progress.

## 4. Start the React board

In a second terminal:

```bash
cd frontend
npm run dev
```

This opens `http://localhost:5173`. The board calls the backend at `VITE_API_BASE`, which defaults to `http://localhost:8000`. To change it, add `VITE_API_BASE=...` to `frontend/.env`. Type your name in **Approving as** before approving anything.

## 5. Reset the DB before a full three-ticket run

Start every full run from the original data:

1. Click **Reset shop** on the board, or run `curl -X POST http://localhost:8000/api/reset`. Checking goes back to **$3,400.00** and tickets 101, 102 and 103 reopen.
2. For each ticket, click **Run team ▸** and watch the agents in the feed.
3. Approve or reject the payment cards on the right. Approving is the only thing that moves cash.
4. If a ticket needs more work after an approval (for example, ordering the tee once invoice 501 is paid), click **Run team ▸** again. Use **Mark resolved ✓** when the team has done everything the shop can do.

Each run appends to `output/audit_trail.json`. The expected-vs-actual results and the cash breakdown from our run are in `output/desk_tickets.html`.

**Command-line alternative** (no board): `cd backend && python run_team.py --task "..."` runs the Boss once, and `--db <copy.db>` points it at a scratch copy.

## Safety

- Agents can only *request* payments. Paying is a human-only action on the board, and it refuses any payment that would make cash negative.
- Customer and vendor messages are saved as drafts and never sent.
- Each agent sees only the MCP tools for its job, and run limits cap delegations, model calls and tokens.

Details are in the Safety section of `output/harness.md`.
