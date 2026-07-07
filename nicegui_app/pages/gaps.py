"""Keyword gaps — the payoff of the competitor data.

"Here are the searches your competitors rank for and you don't", prioritized
by volume, plus the topic clusters that are pure opportunity (mostly gap
keywords, no existing mshop page → candidates for NEW content).

Reuses utils/keyword_universe.keyword_gaps and the is_opportunity tags that
utils/clustering already wrote onto the clusters — no new logic here.
"""

from __future__ import annotations

from nicegui import ui

from utils import state
from utils.keyword_universe import keyword_gaps, universe_summary, UNIVERSE_KEY
from nicegui_app import components as c
from nicegui_app.layout import page_shell


def _opportunity_clusters():
    tc = state.state().get("topic_clusters") or {}
    clusters = tc.get("clusters", []) if isinstance(tc, dict) else []
    opp = [cl for cl in clusters if cl.get("is_opportunity")]
    return sorted(opp, key=lambda cl: cl.get("gap_volume", 0), reverse=True)


def render() -> None:
    with page_shell("/gaps"):
        c.page_header(
            "Keyword gaps",
            "Searches competitors rank for and you don't — your content "
            "opportunities, biggest search volume first.",
        )

        uni = state.state().get(UNIVERSE_KEY)
        s = universe_summary(uni)
        if not s["gaps"]:
            c.banner("info", "No gaps yet. Import competitor keywords on the "
                             "Keyword universe page first.")
            ui.button("Open Keyword universe", icon="travel_explore",
                      on_click=lambda: ui.navigate.to("/keywords")).props("color=primary")
            return

        with ui.row().classes("w-full gap-3 flex-wrap"):
            for label, value in [
                ("Gap keywords", f"{s['gaps']:,}"),
                ("Total gap volume", f"{s['total_volume']:,}"),
                ("Competitors analyzed", s["competitors"]),
            ]:
                with ui.card().classes("flex-1 min-w-[150px] items-center py-3"):
                    ui.label(str(value)).classes("text-2xl font-bold text-primary")
                    ui.label(label).classes("text-xs text-gray-500 text-center")

        # ── opportunity clusters (need clusters built) ────────────
        opp = _opportunity_clusters()
        with ui.card().classes("w-full"):
            c.subheader("New-content opportunities (whole topics you're missing)")
            if not opp:
                c.caption("Build topic clusters (SEO flow → Build topic clusters) "
                          "to group these gaps into content ideas.")
            else:
                for cl in opp[:30]:
                    with ui.row().classes("w-full items-center justify-between border-t py-2"):
                        with ui.column().classes("gap-0 flex-1"):
                            ui.label(cl.get("topic", "—")).classes("font-medium")
                            kws = ", ".join((cl.get("gap_keywords") or [])[:8])
                            ui.label(kws).classes("text-xs text-gray-500")
                        ui.badge(f"{cl.get('gap_volume', 0):,} vol").props("color=primary")

        # ── full prioritized gap list ────────────────────────────
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                c.subheader("All gap keywords")
                min_vol = ui.number("Min volume", value=0, min=0, step=50).props("dense").classes("w-32")

            table_holder = ui.column().classes("w-full")

            def _render_table() -> None:
                table_holder.clear()
                gaps = keyword_gaps(uni, min_volume=int(min_vol.value or 0))
                with table_holder:
                    if gaps is None or gaps.empty:
                        c.caption("No gaps at this volume threshold.")
                        return
                    rows = [{
                        "keyword": r["keyword"],
                        "volume": int(r["volume"]),
                        "kd": int(r["keyword_difficulty"]),
                        "competitors": ", ".join(r["competitors"]),
                        "best_pos": r["best_competitor_position"] or "",
                    } for _, r in gaps.head(300).iterrows()]
                    ui.table(
                        columns=[
                            {"name": "keyword", "label": "Keyword", "field": "keyword", "align": "left", "sortable": True},
                            {"name": "volume", "label": "Volume", "field": "volume", "sortable": True},
                            {"name": "kd", "label": "KD", "field": "kd", "sortable": True},
                            {"name": "competitors", "label": "Ranks for it", "field": "competitors", "align": "left"},
                            {"name": "best_pos", "label": "Best pos", "field": "best_pos", "sortable": True},
                        ],
                        rows=rows, row_key="keyword", pagination=25,
                    ).classes("w-full").props("flat dense")
                    ui.button("Download all as CSV", icon="download",
                              on_click=lambda: ui.download(
                                  gaps[["keyword", "volume", "keyword_difficulty",
                                        "n_competitors", "best_competitor_position"]]
                                  .to_csv(index=False).encode("utf-8"),
                                  "keyword_gaps.csv")).props("flat dense")
                    if len(gaps) > 300:
                        c.caption(f"Showing top 300 of {len(gaps):,}. Download CSV for all.")

            min_vol.on("change", lambda _: _render_table())
            _render_table()
