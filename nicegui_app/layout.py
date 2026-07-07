"""Shared page shell — one navigation + chrome used by every page.

Goal #2 (understandable, consistent flow) and #5 (no duplicated code) both
live here: a page calls ``with page_shell("/keywords"):`` and gets the same
header, left navigation and centered content column as every other page. To
add a page, add one entry to ``NAV`` and one ``@ui.page`` route in main.py.
"""

from __future__ import annotations

from contextlib import contextmanager

from nicegui import ui

# The flow, top to bottom, in the order the operator works through it. New
# steps get inserted here as they are ported — this list is the single
# source of truth for the navigation.
NAV = [
    ("/", "Dashboard", "dashboard"),
    ("/flow", "SEO flow", "account_tree"),
    ("/keywords", "Keyword universe", "travel_explore"),
    ("/gaps", "Keyword gaps", "lightbulb"),
]


@contextmanager
def page_shell(active_path: str):
    """Header + left nav + centered content column. Yields the content column."""
    from nicegui_app import theme
    theme.apply()

    with ui.header().classes("items-center justify-between px-4 py-2"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("insights").classes("text-2xl").style(f"color:{theme.PRIMARY}")
            ui.label("SEO Platform").classes("text-lg font-bold")
        ui.label("mshop").classes("text-xs opacity-60")

    with ui.left_drawer(bordered=True).props("width=230").classes("gap-1 p-2"):
        for path, label, icon in NAV:
            active = path == active_path
            btn = (
                ui.button(label, icon=icon, on_click=lambda p=path: ui.navigate.to(p))
                .props(f"flat no-caps{' color=primary' if active else ' color=grey-6'}")
                .classes("w-full justify-start")
            )
            if active:
                btn.style(f"background:{theme.PRIMARY}22; font-weight:600")

    content = ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-4")
    with content:
        yield content
