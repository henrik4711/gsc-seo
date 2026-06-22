"""Framework-agnostic access to per-session application state.

This is Phase 0 of the Streamlit -> NiceGUI migration (see
NICEGUI_MIGRATION_PLAN.md). Business logic calls ``state()`` instead of
``st.session_state`` so it knows NOTHING about which GUI framework is
running.

  * Streamlit binds ``st.session_state`` (already a MutableMapping) once
    per script-run -> behaviour is bit-for-bit identical to before.
  * NiceGUI binds a per-client dict (e.g. a slot in ``app.storage``) once
    per client connection.

A ``ContextVar`` (not a plain module global) backs the active store so the
SAME accessor keeps working when NiceGUI runs many clients concurrently in
one process. In Streamlit each session runs in its own ScriptRunner thread
and gets its own context, so per-run ``bind()`` is correctly isolated too.
"""

from __future__ import annotations

import contextvars
from typing import MutableMapping

# No default value: an unbound access is a programming error we want to
# surface loudly rather than silently operate on a throwaway dict.
_active: contextvars.ContextVar = contextvars.ContextVar("app_state")


def bind(store: MutableMapping) -> None:
    """Bind the active state backend for the current context.

    Call once at app startup (Streamlit) or per client connection
    (NiceGUI). ``store`` must be a MutableMapping — the logic only ever
    uses ``in`` / ``[]`` / ``.get`` / ``.keys`` / ``.pop``.
    """
    _active.set(store)


def is_bound() -> bool:
    """True if a backend is bound in the current context."""
    try:
        _active.get()
        return True
    except LookupError:
        return False


def state() -> MutableMapping:
    """Return the active state mapping. Drop-in for ``st.session_state``."""
    try:
        return _active.get()
    except LookupError as exc:
        raise RuntimeError(
            "app state backend not bound — call utils.state.bind(store) "
            "at startup (Streamlit) or per client connection (NiceGUI)"
        ) from exc
