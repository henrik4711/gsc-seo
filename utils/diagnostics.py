"""
Single source of truth for diagnostic logging across ALL pipeline
steps and AI calls.

Every function that does meaningful work calls log_run(...) with
its inputs, outputs, timing, errors. Logs are persisted as JSON
files on the mounted volume so they survive crashes and restarts.

A single download button in the UI grabs the entire diagnostic
log so you can see EXACTLY what happened on any run.

Usage:
    from utils.diagnostics import log_run, log_event, get_logs

    # As a context manager — automatic timing + error capture
    with log_run("Step 7: AI Quality Check") as run:
        run.input("audit_results count", len(audit))
        run.input("eligible pages", len(eligible))
        result = do_work()
        run.output("checked", len(result))
        run.output("avg score", sum(...)/len(result))

    # Or one-off events
    log_event("scrape page", url=url, success=True, words=812)
"""

import json
import os
import time
import traceback
from datetime import datetime
from contextlib import contextmanager

DIAGNOSTICS_DIR = "/data/diagnostics"
MAX_LOG_FILES = 200  # rotate when exceeded
MAX_FIELD_LEN = 5000  # truncate huge values


def _ensure_dir():
    try:
        os.makedirs(DIAGNOSTICS_DIR, exist_ok=True)
        return True
    except Exception:
        return False


def _truncate(v):
    """Trim large values so a single log entry doesn't blow up disk."""
    if isinstance(v, str):
        return v[:MAX_FIELD_LEN] + ("...[truncated]" if len(v) > MAX_FIELD_LEN else "")
    if isinstance(v, (list, tuple)):
        if len(v) > 100:
            return [_truncate(x) for x in list(v)[:100]] + [f"...[+{len(v)-100} more]"]
        return [_truncate(x) for x in v]
    if isinstance(v, dict):
        if len(v) > 50:
            keys = list(v.keys())[:50]
            out = {k: _truncate(v[k]) for k in keys}
            out["__more_keys__"] = len(v) - 50
            return out
        return {k: _truncate(val) for k, val in v.items()}
    return v


def _file_for_today():
    return os.path.join(DIAGNOSTICS_DIR, f"diag_{datetime.now().strftime('%Y%m%d')}.jsonl")


def _append(entry: dict):
    """Append one JSON-line entry to today's log file."""
    if not _ensure_dir():
        return
    try:
        path = _file_for_today()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        print(f"[diagnostics] write failed: {e}")


class _RunContext:
    """One logged run — captures inputs, outputs, timing, errors."""
    def __init__(self, name):
        self.name = name
        self.t0 = time.time()
        self.inputs = {}
        self.outputs = {}
        self.events = []
        self.error = None

    def input(self, key, value):
        self.inputs[key] = _truncate(value)

    def output(self, key, value):
        self.outputs[key] = _truncate(value)

    def event(self, message, **fields):
        self.events.append({
            "t": round(time.time() - self.t0, 3),
            "msg": message,
            **{k: _truncate(v) for k, v in fields.items()},
        })


@contextmanager
def log_run(name: str):
    """
    Context manager around a logical run. Captures elapsed time,
    inputs, outputs, and any exception.
    """
    ctx = _RunContext(name)
    try:
        yield ctx
    except Exception as e:
        ctx.error = {
            "type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc()[:5000],
        }
        # Re-raise so callers still see it
        _flush(ctx)
        raise
    else:
        _flush(ctx)


def _flush(ctx: _RunContext):
    duration = round(time.time() - ctx.t0, 3)
    _append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "name": ctx.name,
        "duration_sec": duration,
        "inputs": ctx.inputs,
        "outputs": ctx.outputs,
        "events": ctx.events,
        "error": ctx.error,
    })


def log_event(name: str, **fields):
    """One-off log entry — no run/duration tracking."""
    _append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "name": name,
        "fields": {k: _truncate(v) for k, v in fields.items()},
    })


def get_logs(limit: int = 1000, name_filter: str = None, errors_only: bool = False) -> list:
    """Read back recent log entries from disk. Newest first."""
    if not os.path.isdir(DIAGNOSTICS_DIR):
        return []
    entries = []
    files = sorted([f for f in os.listdir(DIAGNOSTICS_DIR) if f.startswith("diag_") and f.endswith(".jsonl")])
    # Read newest files first
    for fname in reversed(files):
        path = os.path.join(DIAGNOSTICS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in reversed(f.readlines()):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    if name_filter and name_filter.lower() not in (e.get("name", "") or "").lower():
                        continue
                    if errors_only and not e.get("error"):
                        continue
                    entries.append(e)
                    if len(entries) >= limit:
                        return entries
        except Exception:
            continue
    return entries


def get_summary() -> dict:
    """Aggregate counts: runs per step, errors per step, total time."""
    entries = get_logs(limit=10000)
    by_name = {}
    errors_by_name = {}
    total_seconds = 0
    for e in entries:
        n = e.get("name", "unknown")
        by_name[n] = by_name.get(n, 0) + 1
        total_seconds += e.get("duration_sec", 0) or 0
        if e.get("error"):
            errors_by_name[n] = errors_by_name.get(n, 0) + 1
    return {
        "total_entries": len(entries),
        "by_name": dict(sorted(by_name.items(), key=lambda x: -x[1])),
        "errors_by_name": errors_by_name,
        "total_seconds": round(total_seconds, 1),
    }


def export_all_as_json() -> str:
    """Bundle ALL diagnostic files into one JSON blob for download."""
    if not os.path.isdir(DIAGNOSTICS_DIR):
        return json.dumps({"entries": [], "summary": get_summary()})
    entries = get_logs(limit=100000)
    return json.dumps({
        "exported_at": datetime.now().isoformat(),
        "summary": get_summary(),
        "entries": entries,
    }, ensure_ascii=False, indent=1, default=str)


def clear_logs() -> int:
    """Delete all diagnostic files. Returns count of files removed."""
    if not os.path.isdir(DIAGNOSTICS_DIR):
        return 0
    n = 0
    for f in os.listdir(DIAGNOSTICS_DIR):
        try:
            os.remove(os.path.join(DIAGNOSTICS_DIR, f))
            n += 1
        except Exception:
            pass
    return n
