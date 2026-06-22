"""NiceGUI front-end — pilot / staging app.

Phase 0+pilot of the Streamlit -> NiceGUI migration (see
../NICEGUI_MIGRATION_PLAN.md). This app does NOT copy any business logic:
it REUSES the shared ``utils/`` package via the framework-agnostic
``utils.state`` accessor. The Streamlit app keeps running unchanged from
``app.py`` on ``main``; this lives on the ``nicegui-migration`` branch and
is ported to ``main`` only once it is at parity.

Folder is named ``nicegui_app`` (not ``nicegui``) on purpose: a top-level
``nicegui`` package would shadow the installed NiceGUI library.

Run locally:
    pip install -r nicegui_app/requirements.txt
    APP_PASSWORD=dev python -m nicegui_app.main
    # open http://localhost:8080

What this pilot proves:
  1. The NiceGUI app reuses real shared logic — ``get_storage_info()`` from
     utils.persistence — without going through Streamlit.
  2. The ``utils.state`` Store binds to a per-client backend, so logic that
     reads ``state()`` works under NiceGUI exactly as under Streamlit.
  3. Server-side persistent state needs no ``st.rerun`` — a counter updates
     a single label in place.
"""

from __future__ import annotations

import os
import sys

# Allow ``python nicegui_app/main.py`` as well as ``-m nicegui_app.main`` by
# ensuring the repo root (parent of this file's dir) is importable.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from nicegui import app, ui  # noqa: E402

from utils import state  # noqa: E402
from utils.persistence import get_storage_info  # noqa: E402

# Fail closed exactly like app.py: no APP_PASSWORD -> refuse to serve.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()


def _bind_client_store() -> None:
    """Bind utils.state to this client's per-connection storage.

    ``app.storage.client`` is a dict-like scoped to one browser connection —
    the NiceGUI analogue of Streamlit's per-session ``st.session_state``.
    """
    state.bind(app.storage.client)


def _render_dashboard() -> None:
    """The (tiny) pilot dashboard — all reused logic, zero Streamlit."""
    with ui.column().classes("w-full max-w-3xl mx-auto p-6 gap-4"):
        ui.label("SEO Platform — NiceGUI pilot").classes("text-2xl font-bold")
        ui.label(
            "This page reuses utils/ logic directly. No Streamlit, no rerun."
        ).classes("text-gray-500")

        # ── Proof 1+2: reuse real shared logic via the bound Store ──
        with ui.card().classes("w-full"):
            ui.label("Persisted data on /data volume").classes("font-semibold")
            info = get_storage_info()  # pure shared logic from utils.persistence
            if not info.get("available"):
                ui.label("No /data volume mounted (expected when running locally).")
            else:
                ui.label(f"Total: {info['total_mb']} MB")
                rows = [
                    {"key": k, "size_mb": v.get("size_mb"), "count": v.get("count", "")}
                    for k, v in info.get("files", {}).items()
                ]
                ui.table(
                    columns=[
                        {"name": "key", "label": "key", "field": "key", "align": "left"},
                        {"name": "size_mb", "label": "MB", "field": "size_mb"},
                        {"name": "count", "label": "count", "field": "count"},
                    ],
                    rows=rows,
                    row_key="key",
                ).classes("w-full")

        # ── Proof 3: persistent server-side state, no rerun ──
        with ui.card().classes("w-full"):
            ui.label("Server-side state demo (no st.rerun)").classes("font-semibold")
            store = state.state()
            store.setdefault("pilot_counter", 0)
            count_label = ui.label(f"counter = {store['pilot_counter']}")

            def _bump() -> None:
                store["pilot_counter"] += 1
                count_label.text = f"counter = {store['pilot_counter']}"  # in-place

            ui.button("Increment", on_click=_bump)


@ui.page("/")
def index() -> None:
    _bind_client_store()

    if not APP_PASSWORD:
        with ui.column().classes("w-full max-w-xl mx-auto p-6"):
            ui.label("🔒 Configuration error").classes("text-2xl font-bold")
            ui.label(
                "APP_PASSWORD env var is not set. The app refuses to serve "
                "without it. Set APP_PASSWORD=dev for local development."
            ).classes("text-red-600")
        return

    store = state.state()
    if store.get("authenticated"):
        _render_dashboard()
        return

    # ── Minimal login (per-client). Mirrors app.py's fail-closed gate. ──
    with ui.column().classes("w-full max-w-sm mx-auto p-6 gap-3"):
        ui.label("🔒 Sign in").classes("text-xl font-bold")
        pw = ui.input("Password", password=True, password_toggle_button=True)

        def _try_login() -> None:
            if pw.value == APP_PASSWORD:
                store["authenticated"] = True
                ui.navigate.reload()
            else:
                ui.notify("Wrong password", type="negative")

        pw.on("keydown.enter", lambda _: _try_login())
        ui.button("Sign in", on_click=_try_login)


def run() -> None:
    ui.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        title="SEO Platform (NiceGUI)",
        # storage_secret enables app.storage.client/user persistence.
        storage_secret=os.environ.get("NICEGUI_STORAGE_SECRET", "dev-pilot-secret"),
        reload=False,
        show=False,
    )


# NiceGUI requires ui.run() at module top level under __main__ / __mp_main__
# (it re-imports the module in a worker process).
if __name__ in {"__main__", "__mp_main__"}:
    run()
