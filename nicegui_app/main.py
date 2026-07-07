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
  1. Reuse — the dashboard calls real shared logic (get_storage_info) with no
     Streamlit involved.
  2. State resolver — state() is bound ONCE to ``lambda: app.storage.client``
     and re-resolved on every access, so it is correct inside the page builder
     AND inside event callbacks (which run in separate async tasks). The
     counter handler calls state() fresh to prove it.
  3. Off-loop work — slow calls go through ``run_job`` (run.io_bound + spinner)
     so the event loop never freezes for other clients.
  4. No rerun — the counter updates one label in place.
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
from nicegui_app import components as c  # noqa: E402
from nicegui_app.layout import page_shell  # noqa: E402

# Fail closed exactly like app.py: no APP_PASSWORD -> refuse to serve.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()

# Bind ONCE at import: a resolver, not a captured object. app.storage.client
# resolves to the current client on every state() call, so it is valid in page
# builders, event callbacks and background tasks alike. (The lambda is only
# *called* later, inside a client context, so referencing app.storage.client
# here at import time is safe.)
state.bind(lambda: app.storage.client)


async def _render_dashboard() -> None:
    """The (tiny) pilot dashboard — all reused logic, zero Streamlit."""
    with page_shell("/"):
        c.page_header(
            "SEO Platform — NiceGUI",
            "Reuses utils/ logic directly. No Streamlit, no rerun.",
        )

        # ── Proof 1+3: reuse shared logic, loaded off the event loop ──
        with ui.card().classes("w-full"):
            c.subheader("Persisted data on /data volume")
            info = await c.run_job(get_storage_info, message="Loading storage info…")
            if not info.get("available"):
                c.banner("info", "No /data volume mounted (expected locally).")
            else:
                c.caption(f"Total: {info['total_mb']} MB")
                c.simple_table([
                    {"key": k, "size_mb": v.get("size_mb"), "count": v.get("count", "")}
                    for k, v in info.get("files", {}).items()
                ])

        # ── Proof 2+4: state() resolved fresh in a callback, no rerun ──
        with ui.card().classes("w-full"):
            c.subheader("Server-side state demo (no st.rerun)")
            current = state.state().get("pilot_counter", 0)
            count_label = ui.label(f"counter = {current}")

            def _bump() -> None:
                s = state.state()  # resolved FRESH in this event-callback task
                s["pilot_counter"] = s.get("pilot_counter", 0) + 1
                count_label.text = f"counter = {s['pilot_counter']}"  # in-place

            ui.button("Increment", on_click=_bump)


def _ensure_loaded() -> None:
    """Rehydrate the per-client store from the /data volume once per session.

    Makes the whole app resumable (goal #4): a redeploy / reconnect reloads
    GSC data, the keyword universe, competitor uploads, audit results, etc.
    from disk into app.storage.client. No-op locally (no /data volume) and
    guarded so it runs only once per client connection.
    """
    s = app.storage.client
    if s.get("_loaded_from_disk"):
        return
    try:
        from utils.persistence import load_all
        load_all()
    except Exception as e:  # never block the page on a load hiccup
        print(f"[nicegui] load_all failed: {e}")
    s["_loaded_from_disk"] = True


def _guard() -> bool:
    """Fail-closed auth gate shared by every page. Returns True if usable."""
    if not APP_PASSWORD:
        with ui.column().classes("w-full max-w-xl mx-auto p-6"):
            c.page_header("🔒 Configuration error")
            c.banner(
                "error",
                "APP_PASSWORD env var is not set. The app refuses to serve "
                "without it. Set APP_PASSWORD=dev for local development.",
            )
        return False

    # Auth lives in app.storage.user (signed per-browser cookie), NOT
    # app.storage.client: the latter is wiped on ui.navigate.reload(), which
    # would create a login loop. app.storage.user survives the reload.
    if app.storage.user.get("authenticated"):
        _ensure_loaded()
        return True

    # ── Minimal login (per-client). Mirrors app.py's fail-closed gate. ──
    with ui.column().classes("w-full max-w-sm mx-auto p-6 gap-3"):
        c.page_header("🔒 Sign in")
        pw = ui.input("Password", password=True, password_toggle_button=True)

        def _try_login() -> None:
            if pw.value == APP_PASSWORD:
                app.storage.user["authenticated"] = True
                ui.navigate.reload()
            else:
                c.notify_err("Wrong password")

        pw.on("keydown.enter", lambda _: _try_login())
        ui.button("Sign in", on_click=_try_login)
    return False


@ui.page("/")
async def index() -> None:
    if _guard():
        await _render_dashboard()


@ui.page("/flow")
async def flow_page() -> None:
    if _guard():
        from nicegui_app.pages import flow
        flow.render()


@ui.page("/keywords")
async def keywords_page() -> None:
    if _guard():
        from nicegui_app.pages import keywords
        keywords.render()


@ui.page("/gaps")
async def gaps_page() -> None:
    if _guard():
        from nicegui_app.pages import gaps
        gaps.render()


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
