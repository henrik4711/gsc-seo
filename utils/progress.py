"""Framework-agnostic progress reporting for long-running logic.

Phase 0 of the Streamlit -> NiceGUI migration (see
NICEGUI_MIGRATION_PLAN.md). Runner/analysis functions take a ``Progress``
object instead of calling ``st.spinner`` / ``st.progress`` / ``st.toast``
directly. The default ``NULL`` instance is a no-op, so logic runs unchanged
outside any GUI (tests, scripts, cron).

  * Streamlit wraps st.progress / st.status / st.toast in a Progress.
  * NiceGUI wraps ui.linear_progress / ui.notification in a Progress.

The protocol is intentionally tiny — extend only when a real call site
needs it.
"""

from __future__ import annotations

from typing import Optional


class Progress:
    """No-op progress sink. Subclass per framework to render real UI."""

    def step(self, msg: str, pct: Optional[float] = None) -> None:
        """Report incremental progress. ``pct`` in 0.0..1.0 when known."""

    def done(self, msg: str = "") -> None:
        """Signal completion."""


# Shared no-op default — logic signature: ``progress: Progress = NULL``.
NULL = Progress()
