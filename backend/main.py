"""Campus Customs backend API for the React dashboard.

Run from backend/:  uvicorn main:app --reload --port 8000   ->  http://localhost:8000
Interactive docs:   http://localhost:8000/docs

Shop data goes through the campus-customs MCP server (one long-lived stdio
session), the same server the agents use. The only route that changes cash
is POST /api/approvals/{id}/approve, which a human triggers by clicking Approve.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import Client

from agents import run_team
from agents.loop import new_run_id, ticket_task
from config import AUDIT_PATH, ORIGINAL_DB, WORKING_DB, mcp_client_config
from models import AgentEvent, ApproveBody, RejectBody, ResolveBody, RunInfo

RUNS: dict[str, RunInfo] = {}
_tasks: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with Client(mcp_client_config()) as client:
        app.state.mcp = client
        yield
        for task in _tasks.values():
            task.cancel()


app = FastAPI(title="Campus Customs API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[  # the Vite dev page (http by default; https if you enable it)
        "http://localhost:5173", "http://127.0.0.1:5173",
        "https://localhost:5173", "https://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def mcp(tool: str, **args: Any) -> dict[str, Any]:
    """Call one campus-customs MCP tool and return its JSON result."""
    res = await app.state.mcp.call_tool(tool, args, raise_on_error=False)
    if res.is_error:
        raise HTTPException(502, f"MCP tool {tool} failed: {res.content[0].text if res.content else ''}")
    return res.structured_content or json.loads(res.content[0].text)


def _active_run() -> RunInfo | None:
    return next((r for r in RUNS.values() if r.status == "running"), None)


# ---------------------------------------------------------------------------
# Tickets and agent runs
# ---------------------------------------------------------------------------


@app.get("/api/tickets")
async def list_tickets() -> dict[str, Any]:
    """Every ticket on the board with its status and an is_open flag."""
    return await mcp("list_tickets")


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: int) -> dict[str, Any]:
    """One ticket with linked rows and the drafts, quotes, POs and approval requests on it."""
    out = await mcp("get_ticket", ticket_id=ticket_id)
    if not out.get("found"):
        raise HTTPException(404, out.get("error"))
    return out


@app.post("/api/tickets/{ticket_id}/resolve")
async def resolve(ticket_id: int, body: ResolveBody) -> dict[str, Any]:
    """Human clicked Mark resolved: close the ticket (refused while it has pending approvals)."""
    if (busy := _active_run()) and busy.ticket_id == ticket_id:
        raise HTTPException(409, f"Run {busy.run_id} is still working this ticket.")
    out = await mcp("resolve_ticket", ticket_id=ticket_id, resolved_by=body.resolved_by, note=body.note)
    if not out.get("ok"):
        raise HTTPException(409, out.get("error"))
    return out


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int) -> RunInfo:
    """Start the agent team on one ticket in the background; poll /api/runs/{run_id} and /api/events."""
    if not (await mcp("get_ticket", ticket_id=ticket_id)).get("found"):
        raise HTTPException(404, f"No ticket with id={ticket_id}.")
    if busy := _active_run():
        raise HTTPException(409, f"Run {busy.run_id} on ticket {busy.ticket_id} is still running.")

    info = RunInfo(run_id=new_run_id(), ticket_id=ticket_id, status="running",
                   started_at=datetime.now().isoformat(timespec="seconds"))
    RUNS[info.run_id] = info

    async def work() -> None:
        try:
            result = await run_team(ticket_task(ticket_id), ticket_id=ticket_id, run_id=info.run_id)
            info.result = result
            info.status = "done" if result.get("ok") else "failed"
            info.error = None if result.get("ok") else result["report"].get("error")
        except Exception as exc:  # keep the API up even if a run crashes
            info.status, info.error = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            info.finished_at = datetime.now().isoformat(timespec="seconds")
            _tasks.pop(info.run_id, None)

    _tasks[info.run_id] = asyncio.create_task(work())
    return info


@app.get("/api/runs")
async def list_runs() -> list[RunInfo]:
    """Runs started since the server came up, newest first."""
    return sorted(RUNS.values(), key=lambda r: r.started_at, reverse=True)


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> RunInfo:
    """Status of one run; result holds the Boss's report when done."""
    if run_id not in RUNS:
        raise HTTPException(404, f"No run {run_id} in this server session.")
    return RUNS[run_id]


# ---------------------------------------------------------------------------
# Agent events (from the append-only audit trail)
# ---------------------------------------------------------------------------


def _read_audit() -> list[dict[str, Any]]:
    if not AUDIT_PATH.exists():
        return []
    for _ in range(3):  # a write may be in flight; it always leaves valid JSON within a moment
        try:
            return json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return []


def _event(e: dict[str, Any]) -> AgentEvent | None:
    d = e.get("detail") or {}
    ev = AgentEvent(**{k: e.get(k) for k in ("run_id", "seq", "logged_at", "kind", "agent", "ticket_id", "summary")},
                    chain=e.get("chain") or [])
    if e["kind"] == "agent_step":
        if e.get("node") == "model_response":
            parts = d.get("parts", [])
            ev.said = "\n".join(p["content"] for p in parts if p["kind"] == "text") or None
            ev.tools = [{"tool": p["tool"], "args": p["args"]} for p in parts
                        if p["kind"] == "tool_call" and p["tool"] != "final_result"]
            if not ev.said and not ev.tools:
                return None  # only the final_result call; agent_end carries the report
        elif e.get("node") == "model_request":
            ev.tool_results = [{"tool": p["tool"], "content": p["content"]} for p in d.get("parts", [])
                               if p["kind"] == "tool_return" and p["tool"] != "final_result"]
            if not ev.tool_results:
                return None
        else:
            return None  # user_prompt / end nodes add nothing for the board
    elif e["kind"] == "delegation":
        ev.delegated_to = d.get("to")
        ev.said = d.get("task")
    elif e["kind"] == "agent_start":
        ev.said = d.get("task")
    elif e["kind"] == "agent_end":
        report = d.get("report") or {}
        ev.said = report.get("summary") or report.get("error")
        ev.report = report or None
    return ev


@app.get("/api/events")
async def events(
    run_id: str | None = None,
    ticket_id: int | None = None,
    after_seq: int = Query(0, description="With run_id: only events after this seq (for polling)."),
    limit: int = Query(100, ge=1, le=1000),
) -> list[AgentEvent]:
    """Recent agent events, oldest first: what each agent said and which tools it called."""
    entries = _read_audit()
    if run_id:
        entries = [e for e in entries if e["run_id"] == run_id and e["seq"] > after_seq]
    if ticket_id is not None:
        runs = {e["run_id"] for e in entries if e["kind"] == "run_start" and e.get("ticket_id") == ticket_id}
        entries = [e for e in entries if e["run_id"] in runs]
    out = [ev for e in entries if (ev := _event(e))]
    return out[-limit:]


# ---------------------------------------------------------------------------
# Approvals and cash (the human side)
# ---------------------------------------------------------------------------


@app.get("/api/approvals")
async def approvals(status: str | None = "pending") -> dict[str, Any]:
    """Payment / purchase requests the agents prepared (pending by default; status=all for every one)."""
    return await mcp("list_approval_requests", status=None if status == "all" else status)


@app.post("/api/approvals/{request_id}/approve")
async def approve(request_id: int, body: ApproveBody) -> dict[str, Any]:
    """Human clicked Approve: pay the request from checking. The only route that changes cash."""
    if busy := _active_run():
        raise HTTPException(409, f"Wait for run {busy.run_id} to finish before approving payments.")
    out = await mcp("approve_request", request_id=request_id, approved_by=body.approved_by)
    if not out.get("ok"):
        raise HTTPException(409, out.get("error"))
    return out


@app.post("/api/approvals/{request_id}/reject")
async def reject(request_id: int, body: RejectBody) -> dict[str, Any]:
    """Human clicked Reject: decline the request; no money moves."""
    out = await mcp("reject_request", request_id=request_id, rejected_by=body.rejected_by, note=body.note)
    if not out.get("ok"):
        raise HTTPException(409, out.get("error"))
    return out


@app.get("/api/cash")
async def cash() -> dict[str, Any]:
    """Current checking balance from cash_accounts, plus what is pending against it."""
    pos = await mcp("get_cash_position")
    checking = next((a for a in pos["cash_accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(404, "No checking account in cash_accounts.")
    return {
        "account": "checking",
        "balance": checking["balance"],
        "as_of": checking["date"],
        "today": pos["today"],
        "pending_total": pos["pending_total"],
        "available_after_pending": pos["available_after_pending"],
    }


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


@app.post("/api/reset")
async def reset() -> dict[str, Any]:
    """Copy the original campus_customs.db over the working copy for a fresh run.

    Clears agent work (requests, POs, quotes, drafts, notes) and restores cash and tickets.
    The audit trail is append-only and is kept.
    """
    if busy := _active_run():
        raise HTTPException(409, f"Run {busy.run_id} is still running; reset after it finishes.")
    try:
        shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    except OSError as exc:
        raise HTTPException(500, f"Reset failed: {exc}") from exc
    RUNS.clear()
    tickets = await mcp("list_tickets")
    return {"ok": True, "database": WORKING_DB.name, "restored_from": ORIGINAL_DB.name,
            "cash": await cash(), "tickets": [{"id": t["id"], "status": t["status"]} for t in tickets["tickets"]]}


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "database": WORKING_DB.name, "audit_trail": AUDIT_PATH.name, "active_run": _active_run()}
