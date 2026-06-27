"""Framework-agnostic access to per-session application state.

Phase 0 of the Streamlit -> NiceGUI migration (see NICEGUI_MIGRATION_PLAN.md).
Business logic calls ``state()`` instead of ``st.session_state`` so it knows
NOTHING about which GUI framework is running.

Resolver model: ``bind()`` stores a *resolver* — a zero-arg callable that
returns the live store — NOT a captured store object. ``state()`` calls the
resolver on every access, so it always resolves through the framework's OWN
current-context machinery:

  * Streamlit:  ``bind(lambda: st.session_state)``  — identity store.
  * NiceGUI:    ``bind(lambda: app.storage.client)`` — resolves to the current
    client on every call, so it is correct in page builders AND event
    callbacks (separate async tasks).

WORKER THREADS (``scope``): NiceGUI's ``run.io_bound`` runs work in a thread
pool, and ``loop.run_in_executor`` does NOT copy contextvars — so
``app.storage.client`` is unreachable inside that thread. Before handing work
to a worker, the caller (see nicegui_app.components.run_job) snapshots the live
store in the main task and re-binds it for the worker via ``with scope(store)``.
The override is THREAD-LOCAL, so concurrent jobs from different clients never
clobber each other.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Callable, Iterator, MutableMapping, Union

Resolver = Callable[[], MutableMapping]

# Process-wide default resolver (set by bind at startup), or None until bound.
_resolver: Union[Resolver, None] = None

# Thread-local override, takes precedence when set (used by run_job in worker
# threads where the framework's own context is unavailable).
_local = threading.local()


def _coerce(store_or_resolver: Union[MutableMapping, Resolver]) -> Resolver:
    if callable(store_or_resolver):
        return store_or_resolver
    store = store_or_resolver
    return lambda: store


def bind(store_or_resolver: Union[MutableMapping, Resolver]) -> None:
    """Bind how to reach the active state store, process-wide.

    Pass a resolver callable (preferred) so the store is re-resolved on every
    access; or a plain MutableMapping (wrapped in a constant resolver) for
    simple/test cases. Call once at startup.
    """
    global _resolver
    _resolver = _coerce(store_or_resolver)


@contextmanager
def scope(store_or_resolver: Union[MutableMapping, Resolver]) -> Iterator[None]:
    """Temporarily override the store for the CURRENT THREAD only.

    Used to carry a snapshotted store into a worker thread (run_job), where the
    GUI framework's per-client context is not available. Thread-local, so it is
    safe under concurrent jobs.
    """
    resolver = _coerce(store_or_resolver)
    prev = getattr(_local, "resolver", None)
    _local.resolver = resolver
    try:
        yield
    finally:
        _local.resolver = prev


def is_bound() -> bool:
    """True if a backend is reachable in the current context."""
    return getattr(_local, "resolver", None) is not None or _resolver is not None


def state() -> MutableMapping:
    """Return the active state mapping. Drop-in for ``st.session_state``."""
    override = getattr(_local, "resolver", None)
    if override is not None:
        return override()
    if _resolver is None:
        raise RuntimeError(
            "app state backend not bound — call utils.state.bind(resolver) "
            "at startup (Streamlit: lambda: st.session_state; "
            "NiceGUI: lambda: app.storage.client)"
        )
    return _resolver()
