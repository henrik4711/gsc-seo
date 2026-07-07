"""SEO flow control center — the understandable, resumable pipeline surface.

Renders utils/pipeline.py (the single source of truth for the flow) as
phases → steps with live status, per-step Run buttons and a "Run all
remaining" engine that picks up where you left off. All work reuses shared
utils logic via run_job (off the event loop); nothing is re-implemented here.
"""

from __future__ import annotations

from nicegui import ui

from utils import state
from utils import pipeline as P
from nicegui_app import components as c
from nicegui_app.layout import page_shell


def _store():
    return state.state()


def render() -> None:
    with page_shell("/flow"):
        c.page_header(
            "SEO flow",
            "Work top to bottom. The system remembers what's done and resumes — "
            "click Run all remaining, or run any step on its own.",
        )

        # ── overall progress + run-all ────────────────────────────
        run_bar = ui.linear_progress(value=0, show_value=False).classes("w-full")
        run_bar.visible = False
        status_line = ui.label().classes("text-sm text-gray-500")

        @ui.refreshable
        def flow_view() -> None:
            store = _store()
            runnable_left = P.remaining_runnable(store)
            done = sum(1 for s in P.STEPS if P.is_done(s, store))

            with ui.row().classes("w-full items-center justify-between"):
                ui.label(f"{done}/{len(P.STEPS)} steps done").classes("text-base font-semibold")
                ui.button(
                    f"Run all remaining ({len(runnable_left)})",
                    icon="play_arrow", on_click=_run_all,
                ).props("color=primary" + ("" if runnable_left else " disable"))

            for phase, steps in P.steps_by_phase():
                with ui.card().classes("w-full"):
                    ui.label(phase).classes("text-sm font-bold text-gray-600 uppercase tracking-wide")
                    for s in steps:
                        _step_row(s, store)

        def _step_row(s: P.Step, store) -> None:
            done = P.is_done(s, store)
            ready = P.is_ready(s)
            with ui.row().classes("w-full items-center gap-3 border-t py-2"):
                # status icon
                if done:
                    ui.icon("check_circle", color="positive").classes("text-xl")
                elif not ready:
                    ui.icon("lock_clock", color="grey").classes("text-xl")
                else:
                    ui.icon("radio_button_unchecked", color="grey").classes("text-xl")
                # title + description
                with ui.column().classes("gap-0 flex-1"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(s.title).classes("font-medium")
                        if s.optional:
                            ui.badge("optional").props("color=grey outline")
                        if done:
                            ui.label(f"· {P.step_count(s, store)}").classes("text-xs text-green-700")
                    ui.label(s.description).classes("text-xs text-gray-500")
                # action
                if s.kind == "data" and s.page:
                    ui.button("Open", icon="open_in_new",
                              on_click=lambda p=s.page: ui.navigate.to(p)).props("flat dense")
                elif s.run is not None:
                    ui.button("Run", icon="play_arrow",
                              on_click=lambda step=s: _run_one(step)).props("flat dense" + (" color=grey" if done else ""))
                else:
                    ui.badge("port pending").props("color=amber outline")

        async def _run_one(step: P.Step) -> None:
            try:
                await c.run_job(step.run, message=f"Running {step.title}…")
                c.notify_ok(f"{step.title} done")
            except Exception as e:  # shared logic raises clear ValueErrors
                c.notify_err(f"{step.title}: {e}")
            flow_view.refresh()

        async def _run_all() -> None:
            store = _store()
            steps = P.remaining_runnable(store)
            if not steps:
                c.notify_ok("Nothing to run — all set.")
                return
            run_bar.visible = True
            total = len(steps)
            for i, step in enumerate(steps):
                status_line.text = f"Step {i + 1}/{total} — {step.title}…"
                run_bar.value = i / total
                try:
                    await c.run_job(step.run, message=f"{step.title}…")
                except Exception as e:
                    run_bar.visible = False
                    status_line.text = ""
                    c.notify_err(f"Stopped at {step.title}: {e}")
                    flow_view.refresh()
                    return
                flow_view.refresh()
            run_bar.value = 1.0
            run_bar.visible = False
            status_line.text = ""
            c.notify_ok(f"Flow complete — ran {total} step(s).")

        flow_view()
