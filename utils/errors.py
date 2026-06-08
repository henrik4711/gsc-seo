"""
Central runtime error reporting.

Why this exists: the codebase has a long tail of `except Exception: pass`
and `except Exception as e: print(...)` patterns. Both are invisible to
the operator — print() goes to Railway logs which the operator can't
see from Streamlit, and bare pass loses the error entirely. We've spent
a dozen debugging cycles tracking bugs that would have been obvious if
the error was surfaced in the UI.

This module gives EVERY exception handler one single function to call
that:
  1. Always prints the error to stderr (for Railway logs)
  2. Appends to a session-state error list (if Streamlit context is live)
  3. Pops a Streamlit toast (immediate visibility)

The session-state list is rendered by app.py at the top of every page,
so operators see accumulated errors regardless of which view they're on.

## Usage

    from utils.errors import report_error

    try:
        risky_thing()
    except Exception as e:
        report_error(
            stage="bundled_unpack",
            key="sf_inlinks",
            error=e,
            severity="error",
        )

`stage` and `key` are free-form strings that identify what went wrong
in a way the operator will recognize. Stage is the high-level operation;
key is the specific item.

## Non-Streamlit contexts

api.py (FastAPI) has no Streamlit context. report_error detects this
via try/except around `import streamlit` and falls back to stderr only.
No Streamlit dependency is required at import time.
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone


# Cap on accumulated errors per session to prevent memory blow-up on
# long-running services where something fails repeatedly.
MAX_ERRORS_IN_SESSION = 50


def report_error(stage: str,
                  key: str = "",
                  error: BaseException | None = None,
                  message: str = "",
                  severity: str = "error") -> None:
    """Surface a runtime error to the operator.

    Args:
        stage:    high-level operation (e.g. 'bundled_unpack', 'save_ai_cache')
        key:      specific item affected (e.g. 'sf_inlinks', filename)
        error:    the caught exception, if any. Provides class + traceback.
        message:  optional human text. If empty, str(error) is used.
        severity: 'error' | 'warning' | 'info'. Controls toast styling.

    The function NEVER raises — error reporting must not become the source
    of further errors. Best-effort surfacing only.
    """
    err_class = type(error).__name__ if error is not None else ""
    msg_text = message or (str(error) if error is not None else "(no message)")
    tb_text = ""
    if error is not None:
        try:
            tb_text = traceback.format_exc()
        except Exception:
            tb_text = ""

    entry = {
        "ts":          datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage":       stage,
        "key":         key,
        "severity":    severity,
        "error_class": err_class,
        "message":     msg_text,
        "traceback":   tb_text,
    }

    # 1. Always emit to stderr for Railway logs
    try:
        line = f"[{severity}] {stage} :: {key or '-'} :: {err_class}: {msg_text}"
        print(line, file=sys.stderr, flush=True)
        if tb_text and severity == "error":
            print(tb_text, file=sys.stderr, flush=True)
    except Exception:
        pass  # stderr broken (rare); nothing useful to do

    # 2. Surface in Streamlit context if available
    try:
        import streamlit as st
        try:
            errors_list = st.session_state.setdefault("_system_errors", [])
            errors_list.append(entry)
            # Cap at MAX_ERRORS_IN_SESSION — drop oldest
            if len(errors_list) > MAX_ERRORS_IN_SESSION:
                del errors_list[:len(errors_list) - MAX_ERRORS_IN_SESSION]
        except Exception:
            # No active script context (e.g. import time)
            pass
        # 3. Pop a toast for immediate visibility
        try:
            icon_map = {"error": "🔴", "warning": "🟡", "info": "🔵"}
            icon = icon_map.get(severity, "🔴")
            toast_msg = f"{stage}: {err_class or msg_text[:80]}"
            st.toast(toast_msg, icon=icon)
        except Exception:
            pass
    except Exception:
        # Not running under Streamlit (e.g. FastAPI in api.py) —
        # stderr already done above
        pass


def get_recent_errors() -> list[dict]:
    """Return the accumulated error entries for this Streamlit session.

    Empty list when running outside Streamlit (e.g. FastAPI in api.py)
    or when no errors have been reported yet.
    """
    try:
        import streamlit as st
        return list(st.session_state.get("_system_errors", []))
    except Exception:
        return []


def clear_errors() -> None:
    """Drop all accumulated errors from this session. Bound to a UI
    dismiss button so the operator can clear the panel after acting on
    the errors."""
    try:
        import streamlit as st
        st.session_state.pop("_system_errors", None)
    except Exception:
        pass


def render_errors_panel() -> None:
    """Render the accumulated errors panel at the top of any view.

    Called from app.py near the page header so errors are visible
    regardless of which view the operator is on. Renders only when
    at least one error has been reported in this session — no panel
    when everything is clean.
    """
    errors = get_recent_errors()
    if not errors:
        return
    try:
        import streamlit as st
    except Exception:
        return

    error_count = sum(1 for e in errors if e.get("severity") == "error")
    warn_count = sum(1 for e in errors if e.get("severity") == "warning")
    info_count = sum(1 for e in errors if e.get("severity") == "info")

    summary_parts = []
    if error_count:
        summary_parts.append(f"{error_count} error(s)")
    if warn_count:
        summary_parts.append(f"{warn_count} warning(s)")
    if info_count:
        summary_parts.append(f"{info_count} info")
    summary = " · ".join(summary_parts) or f"{len(errors)} message(s)"

    with st.expander(f"⚠ System messages ({summary}) — click to inspect",
                       expanded=False):
        # Newest first
        for entry in reversed(errors):
            sev = entry.get("severity", "error")
            stage = entry.get("stage", "?")
            key = entry.get("key", "")
            err_class = entry.get("error_class", "")
            msg = entry.get("message", "")
            ts = entry.get("ts", "")
            tb = entry.get("traceback", "")

            header = f"**{stage}**"
            if key:
                header += f" / `{key}`"
            header += f" — `{err_class}`" if err_class else ""
            header += f"  _{ts}_"

            if sev == "error":
                box = st.error
            elif sev == "warning":
                box = st.warning
            else:
                box = st.info

            box(f"{header}\n\n{msg}")

            if tb:
                st.markdown("**traceback**")
                with st.container():
                    st.code(tb, language="python")

        if st.button("Dismiss all system messages", key="btn_clear_system_errors"):
            clear_errors()
            try:
                st.rerun()
            except Exception:
                pass
