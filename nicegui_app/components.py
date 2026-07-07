"""Shared NiceGUI UI helpers — the Streamlit→NiceGUI idiom cheat-sheet.

Pattern adopted from the production NiceGUI app in wp-system
(wp_publisher/nicegui/components.py). Every view imports these instead of
repeating raw ``ui.*`` calls, so the port stays consistent and the Streamlit
idioms have one obvious translation.

Cheat-sheet (Streamlit -> here):
    st.success/error/warning/info  -> banner(kind, msg)   (persistent inline)
                                   -> notify_ok / notify_err  (transient toast)
    st.spinner + slow call         -> await run_job(fn, ...)  (off event loop)
    st.table(list[dict])           -> simple_table(rows)
    st.rerun()                     -> some_refreshable.refresh()  (targeted)
    st.header/subheader            -> page_header / subheader
"""

from __future__ import annotations

from typing import Callable, Optional

from nicegui import app, run, ui

from utils import state


async def run_job(fn: Callable, *args, message: str = "Working…", **kwargs):
    """Run a blocking function OFF the event loop with a spinner notification.

    Critical under NiceGUI: a synchronous AI/scrape/IO call run directly in an
    async handler freezes the whole server for every connected client. This
    wraps it in ``run.io_bound`` (a worker thread) and shows a spinner that is
    dismissed when the work finishes. Returns the function's result.

    Why the scope() dance: our shared logic reads ``state()`` internally, but a
    worker thread has no access to ``app.storage.client`` (NiceGUI's per-client
    context isn't copied into the thread pool). So we snapshot the live store
    HERE on the main task and re-bind it inside the worker via state.scope(),
    which is thread-local and therefore concurrency-safe.

    Usage:
        result = await run_job(generate_ai_fixes_for_page, page, message="AI…")
    """
    store = app.storage.client  # snapshot on the main task, where it's reachable

    def _job():
        with state.scope(store):
            return fn(*args, **kwargs)

    note = ui.notification(message, spinner=True, timeout=None, close_button=False)
    try:
        return await run.io_bound(_job)
    finally:
        note.dismiss()


def notify_ok(msg: str) -> None:
    """Transient success toast (replaces a fleeting st.success)."""
    ui.notify(msg, type="positive")


def notify_err(msg: str) -> None:
    """Transient error toast (replaces a fleeting st.error)."""
    ui.notify(msg, type="negative")


# Dark-theme banners: tinted border + faint fill, readable on #0d0d15.
_BANNER_STYLE = {
    "success": ("✅", "#33dd88"),
    "error":   ("🔴", "#ff4455"),
    "warning": ("🟡", "#ffaa33"),
    "info":    ("🔵", "#5bb4d4"),
}


def banner(kind: str, msg: str) -> None:
    """Persistent inline alert box (replaces st.success/error/warning/info)."""
    icon, color = _BANNER_STYLE.get(kind, _BANNER_STYLE["info"])
    with ui.row().classes("w-full items-center gap-2 p-3 rounded border").style(
        f"border-color:{color}55; background:{color}14; color:#e8e8f0"
    ):
        ui.label(icon)
        ui.label(msg).classes("text-sm")


def page_header(title: str, subtitle: str = "") -> None:
    """Page title + optional subtitle (replaces st.header/st.caption)."""
    ui.label(title).classes("text-2xl font-bold")
    if subtitle:
        ui.label(subtitle).classes("text-gray-500 text-sm")


def subheader(title: str) -> None:
    ui.label(title).classes("text-lg font-semibold mt-2")


def caption(text: str) -> None:
    ui.label(text).classes("text-gray-500 text-sm")


def simple_table(rows: list[dict], columns: Optional[list[str]] = None):
    """Render a list[dict] as a table (replaces st.table / st.dataframe).

    Returns the ui.table element (or None if empty) so callers can keep a
    handle for later .refresh()/binding.
    """
    if not rows:
        caption("—")
        return None
    cols = columns or list(rows[0].keys())
    return ui.table(
        columns=[{"name": c, "label": c, "field": c, "align": "left"} for c in cols],
        rows=rows,
        row_key=cols[0],
    ).classes("w-full").props("flat dense")
