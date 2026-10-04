"""Append-only audit trail at output/audit_trail.json.

The file is one JSON array. Each new entry is written in place just before the
closing bracket, so earlier runs are never rewritten or wiped.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any

from config import AUDIT_CLIP_CHARS, AUDIT_PATH
from models import AuditEntry, RunState

_lock = threading.Lock()


def clip(value: Any, limit: int = AUDIT_CLIP_CHARS) -> Any:
    """Keep dicts/lists as JSON when small; otherwise cut to a clipped string."""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, default=str, ensure_ascii=False)
        return value if len(text) <= limit else f"{text[:limit]}... [+{len(text) - limit:,} chars]"
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= limit else f"{text[:limit]}... [+{len(text) - limit:,} chars]"


def _append_raw(line: str) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = line.encode("utf-8")
    with _lock:
        if not AUDIT_PATH.exists() or AUDIT_PATH.stat().st_size == 0:
            AUDIT_PATH.write_bytes(b"[\n" + payload + b"\n]\n")
            return
        with open(AUDIT_PATH, "rb+") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(size - 256, 0))
            tail = f.read()
            close = tail.rfind(b"]")
            if close == -1:
                raise ValueError(f"{AUDIT_PATH} is not a JSON array; refusing to overwrite it.")
            close_at = size - len(tail) + close
            empty = tail[:close].rstrip().endswith(b"[")
            f.seek(close_at)
            f.truncate()
            f.write((b"" if empty else b",\n") + payload + b"\n]\n")


def record(state: RunState, kind: str, **fields: Any) -> None:
    entry = AuditEntry(
        run_id=state.run_id,
        seq=state.next_seq(),
        logged_at=datetime.now().isoformat(timespec="milliseconds"),
        kind=kind,
        **fields,
    )
    _append_raw(json.dumps(entry.model_dump(), default=str, ensure_ascii=False))
