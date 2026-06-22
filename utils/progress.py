"""Framework-agnostic progress + transient UI for long-running logic.

Phase 0/3 of the Streamlit -> NiceGUI migration (see
NICEGUI_MIGRATION_PLAN.md). Runner/analysis functions take a ``Progress``
object instead of calling ``st.spinner`` / ``st.progress`` / ``st.error``
directly. The default ``NULL`` instance is a no-op, so logic runs unchanged
outside any GUI (tests, scripts, cron).

  * Streamlit: ``default_progress()`` returns a Progress that wraps
    st.spinner / st.error — but ONLY when called inside a live Streamlit
    script run, so behaviour is identical to the old inline st.* calls.
  * NiceGUI / FastAPI / tests: ``default_progress()`` returns NULL (no
    spinner, no warnings). A NiceGUI caller can pass its own Progress.

The protocol is intentionally tiny — extend only when a real call site
needs it.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional


class Progress:
    """No-op progress sink. Subclass per framework to render real UI."""

    @contextmanager
    def spinner(self, msg: str) -> Iterator[None]:
        """Context manager shown while a slow block runs. No-op by default."""
        yield

    def step(self, msg: str, pct: Optional[float] = None) -> None:
        """Report incremental progress. ``pct`` in 0.0..1.0 when known."""

    def error(self, msg: str) -> None:
        """Surface a user-facing error message."""

    def done(self, msg: str = "") -> None:
        """Signal completion."""


# Shared no-op default — logic signature: ``progress: Progress = NULL``.
NULL = Progress()


def _in_streamlit_context() -> bool:
    """True only inside a live Streamlit script run.

    Lets default_progress() stay silent under NiceGUI/FastAPI/tests instead
    of emitting "missing ScriptRunContext" warnings from stray st.* calls.
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        # suppress_warning=True: don't log "missing ScriptRunContext" when
        # we're legitimately outside Streamlit (NiceGUI / FastAPI / tests).
        return get_script_run_ctx(suppress_warning=True) is not None
    except Exception:
        return False


class _StreamlitProgress(Progress):
    """Progress backed by Streamlit widgets. Used only inside a live run."""

    @contextmanager
    def spinner(self, msg: str) -> Iterator[None]:
        import streamlit as st
        with st.spinner(msg):
            yield

    def error(self, msg: str) -> None:
        import streamlit as st
        st.error(msg)


def default_progress() -> Progress:
    """Return the right Progress for the current runtime.

    Streamlit-backed inside a live Streamlit run (preserving the old inline
    st.spinner / st.error behaviour with no caller changes); NULL otherwise.
    """
    return _StreamlitProgress() if _in_streamlit_context() else NULL
