"""Framework-agnostic access to per-session application state.

Phase 0 of the Streamlit -> NiceGUI migration (see NICEGUI_MIGRATION_PLAN.md).
Business logic calls ``state()`` instead of ``st.session_state`` so it knows
NOTHING about which GUI framework is running.

Resolver model (revised after studying the NiceGUI app in wp-system):
``bind()`` stores a *resolver* — a zero-arg callable that returns the live
store — NOT a captured store object. ``state()`` calls the resolver on every
access, so it always resolves through the framework's OWN current-context
machinery:

  * Streamlit:  ``bind(lambda: st.session_state)``  — the proxy resolves to
    the running session, so it's the identity store (behaviour unchanged).
  * NiceGUI:    ``bind(lambda: app.storage.client)`` — resolves to the
    current client on every call, so it is correct inside page builders AND
    inside event callbacks / background tasks, which run in separate async
    task contexts. (Binding a captured object once would be stale there —
    that was the latent bug this revision fixes.)

A plain MutableMapping may still be passed (``bind({})`` in tests); it is
wrapped in a constant resolver. A module-level global is enough — no
ContextVar — because the resolver itself is context-aware.
"""

from __future__ import annotations

from typing import Callable, MutableMapping, Union

# A zero-arg callable returning the live store, or None until bound.
_resolver: Union[Callable[[], MutableMapping], None] = None


def bind(store_or_resolver: Union[MutableMapping, Callable[[], MutableMapping]]) -> None:
    """Bind how to reach the active state store.

    Pass a resolver callable (preferred) so the store is re-resolved on every
    access; or a plain MutableMapping (wrapped in a constant resolver) for
    simple/test cases. Call once at startup.
    """
    global _resolver
    if callable(store_or_resolver):
        _resolver = store_or_resolver
    else:
        _store = store_or_resolver
        _resolver = lambda: _store


def is_bound() -> bool:
    """True if a backend has been bound."""
    return _resolver is not None


def state() -> MutableMapping:
    """Return the active state mapping. Drop-in for ``st.session_state``."""
    if _resolver is None:
        raise RuntimeError(
            "app state backend not bound — call utils.state.bind(resolver) "
            "at startup (Streamlit: lambda: st.session_state; "
            "NiceGUI: lambda: app.storage.client)"
        )
    return _resolver()
