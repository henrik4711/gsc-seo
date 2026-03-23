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
        st.warning("Go to **1. Setup & Connect** and connect GSC first.")
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
        if st.button("Analyze Cannibalization", type="primary", use_container_width=True):
            with st.spinner("Finding keyword conflicts..."):
                from utils.cannibalization import (
                    detect_cannibalization,
                    get_page_cannibalization_summary,
                    get_cannibalization_clusters,
                )
                cannibal_df = detect_cannibalization(df, min_impressions=min_impressions)
                st.session_state["cannibalization"] = cannibal_df
                st.session_state["cannibal_page_summary"] = get_page_cannibalization_summary(cannibal_df)
                st.session_state["cannibal_clusters"] = get_cannibalization_clusters(cannibal_df)

                from utils.persistence import save_key
                save_key("cannibalization")

    if "cannibalization" not in st.session_state:
        st.info("Click 'Analyze Cannibalization' to start")
        return

    cannibal_df = st.session_state["cannibalization"]
    if cannibal_df.empty:
        st.success("No cannibalization found!")
        return

    # Apply severity filter
    filtered = cannibal_df[cannibal_df["severity"].isin(severity_filter)]

    # ── Overview metrics ───────────────────────────────────────
    st.markdown("### Overview")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Cannibalized Keywords", len(cannibal_df))
    with m2:
        st.metric("Severe", len(cannibal_df[cannibal_df["severity"] == "severe"]))
    with m3:
        total_lost = cannibal_df["lost_clicks_estimate"].sum()
        st.metric("Est. Lost Clicks", f"{total_lost:,}")
    with m4:
        affected_pages = set()
        for details in cannibal_df["pages_detail"]:
            for p in details:
                affected_pages.add(p["page"])
        st.metric("Pages Involved", len(affected_pages))

    # ── Page-level summary ─────────────────────────────────────
    st.markdown("### Pages with Most Conflicts")
    page_summary = st.session_state.get("cannibal_page_summary", pd.DataFrame())
    if not page_summary.empty:
        display_cols = ["page", "cannibal_queries", "severe_count", "is_winner_count",
                        "is_loser_count", "total_lost_clicks", "win_rate"]
        st.dataframe(
            page_summary[display_cols].rename(columns={
                "page": "Page",
                "cannibal_queries": "Conflicts",
                "severe_count": "Severe",
                "is_winner_count": "Winner",
                "is_loser_count": "Loser",
                "total_lost_clicks": "Lost Clicks",
                "win_rate": "Win Rate %",
            }),
            use_container_width=True,
            hide_index=True,
        )

    # ── Page pair clusters ─────────────────────────────────────
    clusters = st.session_state.get("cannibal_clusters", [])
    if clusters:
        st.markdown("### Page Pairs with Most Overlap")
        st.markdown(
            "<p style='color:#9b9bb8;'>These page pairs share the most keywords and should be consolidated</p>",
            unsafe_allow_html=True
        )
        for i, cluster in enumerate(clusters[:10]):
            with st.expander(
                f"{cluster['page_1'].split('/')[-2]} vs {cluster['page_2'].split('/')[-2]} "
                f"({cluster['shared_queries']} shared keywords, ~{cluster['total_lost_clicks']} lost clicks)"
            ):
                st.markdown(f"**Page 1:** `{cluster['page_1']}`")
                st.markdown(f"**Page 2:** `{cluster['page_2']}`")
                st.markdown(f"**Shared keywords:** {', '.join(cluster['query_examples'][:15])}")

                # Show authority data + merge recommendation
                if "page_authority" in st.session_state:
                    auth = st.session_state["page_authority"]
                    page_scores = {}
                    for page in [cluster["page_1"], cluster["page_2"]]:
                        from utils.ui_helpers import normalize_url as _nu
                        page_auth = auth[auth["page"].apply(_nu) == _nu(page)]
                        rd = 0
                        risk = "Unknown"
                        if not page_auth.empty:
                            rd = int(page_auth.iloc[0].get("referring_domains", 0))
                            risk = page_auth.iloc[0].get("change_risk", "Unknown")
                        page_scores[page] = {"rd": rd, "risk": risk}
                        risk_color = "#ff4455" if risk == "HIGH" else "#ffaa33" if risk == "MEDIUM" else "#33dd88"
                        st.markdown(f"`{page}`: **{rd}** referring domains — <span style='color:{risk_color}'>{risk} risk</span>", unsafe_allow_html=True)

                    # Recommend which page to keep
                    p1, p2 = cluster["page_1"], cluster["page_2"]
                    s1 = page_scores.get(p1, {})
                    s2 = page_scores.get(p2, {})
                    keep = p1 if s1.get("rd", 0) >= s2.get("rd", 0) else p2
                    redirect = p2 if keep == p1 else p1
                    st.markdown(
                        f"<div style='background:#0d0d15; border-left:3px solid #5533ff; padding:0.8rem; margin-top:0.5rem; border-radius:0 6px 6px 0;'>"
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#5533ff; margin-bottom:0.3rem;'>MERGE RECOMMENDATION</div>"
                        f"<div style='font-size:0.85rem; color:#c8b4ff;'>"
                        f"<strong>KEEP:</strong> {keep} ({s1.get('rd', 0) if keep == p1 else s2.get('rd', 0)} backlinks)<br>"
                        f"<strong>REDIRECT:</strong> {redirect} → {keep} (301 redirect)<br>"
                        f"<strong>Steps:</strong> 1) Copy unique content from {redirect.split('/')[-2]} to {keep.split('/')[-2]} "
                        f"2) Set up 301 redirect 3) Update internal links pointing to old URL"
                        f"</div></div>",
                        unsafe_allow_html=True,
                    )

    # ── Detailed keyword list ──────────────────────────────────
    st.markdown("### All Cannibalized Keywords")

    for _, row in filtered.head(50).iterrows():
        severity_color = {"severe": "#ff4455", "moderate": "#ffaa33", "mild": "#6b6b8a"}
        color = severity_color.get(row["severity"], "#6b6b8a")

        with st.expander(
            f"[{row['severity'].upper()}] \"{row['query']}\" - "
            f"{row['page_count']} pages, ~{row['lost_clicks_estimate']} lost clicks"
        ):
            st.markdown(
                f"<span style='color:{color}; font-weight:600;'>{row['severity'].upper()}</span> | "
                f"Position spread: {row['position_spread']} | "
                f"Total impressions: {row['total_impressions']:,}",
                unsafe_allow_html=True,
            )

            st.markdown(f"**Recommended winner:** `{row['recommended_winner']}`")
            if row.get("merge_action"):
                st.info(row["merge_action"])

            # Show each competing page
            for p in row["pages_detail"]:
                is_winner = p["page"] == row["recommended_winner"]
                icon = ">>>" if is_winner else "   "
                rd_info = f" | **{p.get('referring_domains', 0)} backlinks**" if p.get("referring_domains") else ""
                st.markdown(
                    f"`{icon}` **Pos {p['position']}** | CTR {p['ctr']}% | "
                    f"{p['clicks']} clicks | {p['impressions']} impr | `{p['page']}`"
                )
