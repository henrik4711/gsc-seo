"""Keyword universe — import competitor Ahrefs keywords + see the gap list.

Reuses ALL logic from utils/keyword_universe.py (goal #5). This module only
renders; it never parses, filters or aggregates keywords itself.

The story the screen tells (goal #2):
    Your own GSC only shows keywords you already rank for. Upload each
    competitor's Ahrefs 'Organic keywords' export → we strip their brand
    terms → union everything into one universe → the gap list is what they
    rank for and you don't.
"""

from __future__ import annotations

import io

from nicegui import ui

from utils import state
from utils.keyword_universe import (
    add_competitor, remove_competitor, universe_summary, keyword_gaps,
    brand_from_domain, UNIVERSE_KEY, COMPETITOR_META_KEY,
)
from nicegui_app import components as c
from nicegui_app.layout import page_shell


def _universe():
    return state.state().get(UNIVERSE_KEY)


def _meta():
    return state.state().get(COMPETITOR_META_KEY) or []


def render() -> None:
    with page_shell("/keywords"):
        c.page_header(
            "Keyword universe",
            "GSC alone only shows what you already rank for. Add competitors "
            "to see everything — with their brand terms stripped out.",
        )

        # ── live summary tiles ────────────────────────────────────
        @ui.refreshable
        def summary_tiles() -> None:
            s = universe_summary(_universe())
            tiles = [
                ("Keywords total", s["total"], "text-primary"),
                ("You rank", s["own"], "text-green-700"),
                ("Gaps (they rank, you don't)", s["gaps"], "text-amber-700"),
                ("Competitors", s["competitors"], "text-blue-700"),
                ("Total search volume", f"{s['total_volume']:,}", "text-primary"),
            ]
            with ui.row().classes("w-full gap-3 flex-wrap"):
                for label, value, color in tiles:
                    with ui.card().classes("flex-1 min-w-[150px] items-center py-3"):
                        ui.label(str(value)).classes(f"text-2xl font-bold {color}")
                        ui.label(label).classes("text-xs text-gray-500 text-center")

        # ── uploaded competitors list ─────────────────────────────
        @ui.refreshable
        def competitor_list() -> None:
            meta = _meta()
            if not meta:
                c.banner("info", "No competitors uploaded yet. Add one below.")
                return
            with ui.card().classes("w-full"):
                c.subheader("Uploaded competitors")
                for m in meta:
                    with ui.row().classes("w-full items-center justify-between border-b py-1"):
                        brands = ", ".join(m.get("brand_terms") or []) or "—"
                        ui.label(f"{m['domain']}").classes("font-medium")
                        ui.label(f"{m.get('count', 0):,} keywords · brand stripped: {brands}") \
                            .classes("text-xs text-gray-500 flex-1 ml-3")
                        ui.button(icon="delete", on_click=lambda d=m["domain"]: _remove(d)) \
                            .props("flat dense color=negative")

        async def _remove(domain: str) -> None:
            await c.run_job(remove_competitor, domain, message=f"Removing {domain}…")
            c.notify_ok(f"Removed {domain}")
            summary_tiles.refresh()
            competitor_list.refresh()
            gap_table.refresh()

        # ── gap opportunity table ─────────────────────────────────
        @ui.refreshable
        def gap_table() -> None:
            uni = _universe()
            gaps = keyword_gaps(uni, min_volume=0)
            with ui.card().classes("w-full"):
                with ui.row().classes("w-full items-center justify-between"):
                    c.subheader("Gap opportunities — keywords competitors rank for, you don't")
                    if gaps is not None and not gaps.empty:
                        ui.button("Download CSV", icon="download",
                                  on_click=lambda: _download_gaps(gaps)).props("flat dense")
                if gaps is None or gaps.empty:
                    c.caption("No gaps yet — upload a competitor to populate this list.")
                    return
                rows = [{
                    "keyword": r["keyword"],
                    "volume": int(r["volume"]),
                    "kd": int(r["keyword_difficulty"]),
                    "competitors": ", ".join(r["competitors"]),
                    "best_pos": r["best_competitor_position"] or "",
                } for _, r in gaps.head(200).iterrows()]
                ui.table(
                    columns=[
                        {"name": "keyword", "label": "Keyword", "field": "keyword", "align": "left", "sortable": True},
                        {"name": "volume", "label": "Volume", "field": "volume", "sortable": True},
                        {"name": "kd", "label": "KD", "field": "kd", "sortable": True},
                        {"name": "competitors", "label": "Ranks for it", "field": "competitors", "align": "left"},
                        {"name": "best_pos", "label": "Best pos", "field": "best_pos", "sortable": True},
                    ],
                    rows=rows, row_key="keyword", pagination=20,
                ).classes("w-full").props("flat dense")
                if len(gaps) > 200:
                    c.caption(f"Showing top 200 of {len(gaps):,} gaps by volume. Download CSV for all.")

        def _download_gaps(gaps) -> None:
            csv = gaps[[
                "keyword", "volume", "keyword_difficulty", "n_competitors",
                "best_competitor_position",
            ]].to_csv(index=False)
            ui.download(csv.encode("utf-8"), "keyword_gaps.csv")

        # ── upload form ───────────────────────────────────────────
        with ui.card().classes("w-full"):
            c.subheader("Add a competitor")
            c.caption(
                "Ahrefs → Organic keywords → Export (CSV). Enter the "
                "competitor's domain and the brand word(s) to strip out "
                "(e.g. 'sinful' — you'll never rank for their brand)."
            )
            with ui.row().classes("w-full gap-3 items-end flex-wrap"):
                domain_in = ui.input("Competitor domain", placeholder="sinful.dk") \
                    .classes("flex-1 min-w-[180px]")
                brand_in = ui.input("Brand terms to strip (comma separated)",
                                    placeholder="sinful") \
                    .classes("flex-1 min-w-[180px]")

            # Pre-fill brand from domain when the operator leaves the field
            # empty — one less thing to type, still editable.
            def _prefill() -> None:
                if not brand_in.value.strip() and domain_in.value.strip():
                    b = brand_from_domain(domain_in.value)
                    if b:
                        brand_in.value = b
            domain_in.on("blur", lambda _: _prefill())

            async def _on_upload(e) -> None:
                domain = (domain_in.value or "").strip().lower()
                if not domain:
                    c.notify_err("Enter the competitor domain first, then upload.")
                    return
                brand_terms = [t.strip() for t in (brand_in.value or "").split(",") if t.strip()]
                data = e.content.read()

                added, _ = await c.run_job(
                    add_competitor, data, domain, brand_terms,
                    message=f"Importing {e.name} for {domain}…",
                )
                if added == 0:
                    c.notify_err(f"Could not parse {e.name} — is it an Ahrefs 'Organic keywords' CSV?")
                    return
                c.notify_ok(f"Imported {added:,} keywords for {domain} (brand stripped)")
                summary_tiles.refresh()
                competitor_list.refresh()
                gap_table.refresh()
                upload.reset()

            upload = ui.upload(
                label="Upload Ahrefs Organic keywords CSV",
                on_upload=_on_upload, auto_upload=True, max_files=1,
            ).classes("w-full").props("accept=.csv,.tsv,.txt")

        summary_tiles()
        competitor_list()
        gap_table()
