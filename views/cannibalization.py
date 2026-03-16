"""
Cannibalization detection view.
Shows keyword conflicts between pages and recommends consolidation.
"""

import streamlit as st
import pandas as pd


def render():
    st.markdown("## Cannibalization Detector")
    st.markdown(
        "<p style='color:#9b9bb8; margin-bottom:2rem;'>"
        "Find keywords where multiple pages compete against each other</p>",
        unsafe_allow_html=True
    )

    if "gsc_data" not in st.session_state:
        st.warning("Gaa til **1. Setup & Connect** og forbind GSC foerst.")
        return

    df = st.session_state["gsc_data"]

    # Controls
    col1, col2, col3 = st.columns(3)
    with col1:
        min_impressions = st.number_input("Min. impressions", value=10, min_value=1)
    with col2:
        severity_filter = st.multiselect(
            "Severity", ["severe", "moderate", "mild"],
            default=["severe", "moderate"]
        )
    with col3:
        if st.button("Analyser kannibalisering", type="primary", use_container_width=True):
            with st.spinner("Finder keyword-konflikter..."):
                from utils.cannibalization import (
                    detect_cannibalization,
                    get_page_cannibalization_summary,
                    get_cannibalization_clusters,
                )
                cannibal_df = detect_cannibalization(df, min_impressions=min_impressions)
                st.session_state["cannibalization"] = cannibal_df
                st.session_state["cannibal_page_summary"] = get_page_cannibalization_summary(cannibal_df)
                st.session_state["cannibal_clusters"] = get_cannibalization_clusters(cannibal_df)

    if "cannibalization" not in st.session_state:
        st.info("Klik 'Analyser kannibalisering' for at starte")
        return

    cannibal_df = st.session_state["cannibalization"]
    if cannibal_df.empty:
        st.success("Ingen kannibalisering fundet!")
        return

    # Apply severity filter
    filtered = cannibal_df[cannibal_df["severity"].isin(severity_filter)]

    # ── Overview metrics ───────────────────────────────────────
    st.markdown("### Oversigt")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Kannibaliserede keywords", len(cannibal_df))
    with m2:
        st.metric("Severe", len(cannibal_df[cannibal_df["severity"] == "severe"]))
    with m3:
        total_lost = cannibal_df["lost_clicks_estimate"].sum()
        st.metric("Estimerede tabte klik", f"{total_lost:,}")
    with m4:
        affected_pages = set()
        for details in cannibal_df["pages_detail"]:
            for p in details:
                affected_pages.add(p["page"])
        st.metric("Sider involveret", len(affected_pages))

    # ── Page-level summary ─────────────────────────────────────
    st.markdown("### Sider med flest konflikter")
    page_summary = st.session_state.get("cannibal_page_summary", pd.DataFrame())
    if not page_summary.empty:
        display_cols = ["page", "cannibal_queries", "severe_count", "is_winner_count",
                        "is_loser_count", "total_lost_clicks", "win_rate"]
        st.dataframe(
            page_summary[display_cols].rename(columns={
                "page": "Side",
                "cannibal_queries": "Konflikter",
                "severe_count": "Severe",
                "is_winner_count": "Vinder",
                "is_loser_count": "Taber",
                "total_lost_clicks": "Tabte klik",
                "win_rate": "Win rate %",
            }),
            use_container_width=True,
            hide_index=True,
        )

    # ── Page pair clusters ─────────────────────────────────────
    clusters = st.session_state.get("cannibal_clusters", [])
    if clusters:
        st.markdown("### Side-par med mest overlap")
        st.markdown(
            "<p style='color:#9b9bb8;'>Disse side-par deler flest keywords og boer konsolideres</p>",
            unsafe_allow_html=True
        )
        for i, cluster in enumerate(clusters[:10]):
            with st.expander(
                f"{cluster['page_1'].split('/')[-2]} vs {cluster['page_2'].split('/')[-2]} "
                f"({cluster['shared_queries']} faelles keywords, ~{cluster['total_lost_clicks']} tabte klik)"
            ):
                st.markdown(f"**Side 1:** `{cluster['page_1']}`")
                st.markdown(f"**Side 2:** `{cluster['page_2']}`")
                st.markdown(f"**Faelles keywords:** {', '.join(cluster['query_examples'][:15])}")

                # Show authority data if available
                if "page_authority" in st.session_state:
                    auth = st.session_state["page_authority"]
                    for page in [cluster["page_1"], cluster["page_2"]]:
                        page_auth = auth[auth["page"].str.rstrip("/").str.lower() == page.rstrip("/").lower()]
                        if not page_auth.empty:
                            rd = page_auth.iloc[0].get("referring_domains", 0)
                            risk = page_auth.iloc[0].get("change_risk", "Ukendt")
                            st.markdown(f"`{page}`: **{rd}** referring domains - {risk}")

    # ── Detailed keyword list ──────────────────────────────────
    st.markdown("### Alle kannibaliserede keywords")

    for _, row in filtered.head(50).iterrows():
        severity_color = {"severe": "#ff4455", "moderate": "#ffaa33", "mild": "#6b6b8a"}
        color = severity_color.get(row["severity"], "#6b6b8a")

        with st.expander(
            f"[{row['severity'].upper()}] \"{row['query']}\" - "
            f"{row['page_count']} sider, ~{row['lost_clicks_estimate']} tabte klik"
        ):
            st.markdown(
                f"<span style='color:{color}; font-weight:600;'>{row['severity'].upper()}</span> | "
                f"Position spread: {row['position_spread']} | "
                f"Total impressions: {row['total_impressions']:,}",
                unsafe_allow_html=True,
            )

            st.markdown(f"**Anbefalet vinder:** `{row['recommended_winner']}`")

            # Show each competing page
            for p in row["pages_detail"]:
                is_winner = p["page"] == row["recommended_winner"]
                icon = ">>>" if is_winner else "   "
                st.markdown(
                    f"`{icon}` **Pos {p['position']}** | CTR {p['ctr']}% | "
                    f"{p['clicks']} klik | {p['impressions']} impr | `{p['page']}`"
                )
