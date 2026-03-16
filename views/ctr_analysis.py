"""
CTR Analysis page
Identifies pages/queries where CTR underperforms expected for their position
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px


def render():
    st.markdown("## 📊 CTR Gap Analysis")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:2rem;'>Find pages where click-through rate underperforms relative to organic position</p>",
        unsafe_allow_html=True
    )

    if "gsc_data" not in st.session_state:
        st.warning("Go to **1. Setup & Connect** and connect GSC first.")
        return

    df = st.session_state["gsc_data"].copy()

    # ── Filters ───────────────────────────────────────────────────
    with st.expander("🎛️ Filters", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            gap_threshold = st.slider(
                "CTR Gap Threshold (%)",
                min_value=-80, max_value=-5, value=-25,
                help="Only show queries this % below expected CTR"
            )
        with col2:
            min_impressions = st.number_input("Min. impressions", min_value=0, value=10)
        with col3:
            pos_max = st.number_input("Max. position", min_value=1, max_value=100, value=20)
        with col4:
            min_lost = st.number_input("Min. lost clicks", min_value=0, value=0)

    # Apply filters
    filtered = df[
        (df["ctr_gap_pct"] <= gap_threshold) &
        (df["impressions"] >= min_impressions) &
        (df["position"] <= pos_max) &
        (df["lost_clicks_estimate"] >= min_lost)
    ].copy()

    # ── Overview Metrics ──────────────────────────────────────────
    total_lost = filtered["lost_clicks_estimate"].sum()
    pages_affected = filtered["page"].nunique()
    queries_affected = len(filtered)
    avg_gap = filtered["ctr_gap_pct"].mean() if len(filtered) > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Lost Clicks/mo (est.)", f"{total_lost:,}", delta=None, help="Estimated based on impressions × gap")
    with m2:
        st.metric("Pages Affected", f"{pages_affected:,}")
    with m3:
        st.metric("Queries with Gap", f"{queries_affected:,}")
    with m4:
        st.metric("Avg. CTR Gap", f"{avg_gap:.1f}%")

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["📋 QUERY LEVEL", "🌐 PAGE LEVEL", "📈 VISUALIZATION"])

    with tab1:
        if filtered.empty:
            st.info("No queries meet the filter criteria. Try adjusting the filters.")
        else:
            display_df = filtered[[
                "page", "query", "position_rounded", "ctr", "expected_ctr",
                "ctr_gap_pct", "impressions", "clicks", "lost_clicks_estimate"
            ]].copy()

            display_df.columns = [
                "Page", "Keyword", "Position", "Actual CTR", "Expected CTR",
                "Gap %", "Impressions", "Clicks", "Lost Clicks"
            ]

            display_df["Actual CTR"] = (display_df["Actual CTR"] * 100).round(2).astype(str) + "%"
            display_df["Expected CTR"] = (display_df["Expected CTR"] * 100).round(2).astype(str) + "%"
            display_df["Gap %"] = display_df["Gap %"].round(1).astype(str) + "%"

            # Color-code by gap severity
            st.dataframe(
                display_df,
                use_container_width=True,
                height=450,
                column_config={
                    "Page": st.column_config.TextColumn(width="large"),
                    "Keyword": st.column_config.TextColumn(width="medium"),
                    "Lost Clicks": st.column_config.NumberColumn(format="%d 🔴"),
                }
            )

            # Export
            csv = filtered.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download CTR Gap Report (CSV)",
                csv, "ctr_gaps.csv", "text/csv"
            )

            # Save to session for next steps
            st.session_state["ctr_gaps"] = filtered

    with tab2:
        # Aggregate by page
        page_summary = filtered.groupby("page").agg(
            total_lost_clicks=("lost_clicks_estimate", "sum"),
            avg_position=("position", "mean"),
            avg_ctr=("ctr", "mean"),
            avg_expected_ctr=("expected_ctr", "mean"),
            avg_gap=("ctr_gap_pct", "mean"),
            query_count=("query", "count"),
            top_queries=("query", lambda x: ", ".join(x.head(3).tolist()))
        ).reset_index().sort_values("total_lost_clicks", ascending=False)

        if page_summary.empty:
            st.info("No pages to show.")
        else:
            page_summary["avg_position"] = page_summary["avg_position"].round(1)
            page_summary["avg_ctr"] = (page_summary["avg_ctr"] * 100).round(2).astype(str) + "%"
            page_summary["avg_gap"] = page_summary["avg_gap"].round(1).astype(str) + "%"

            st.dataframe(
                page_summary.rename(columns={
                    "page": "Page",
                    "total_lost_clicks": "Lost Clicks",
                    "avg_position": "Avg. Pos.",
                    "avg_ctr": "Avg. CTR",
                    "avg_gap": "Avg. Gap",
                    "query_count": "Keywords",
                    "top_queries": "Top Keywords"
                }),
                use_container_width=True,
                height=400
            )

            # Pages with audit buttons
            st.markdown("#### Add Pages to Audit Queue")
            if "audit_queue" not in st.session_state:
                st.session_state["audit_queue"] = []

            top_pages = page_summary.head(10)["page"].tolist()
            selected_pages = st.multiselect(
                "Select pages for analysis",
                top_pages,
                default=top_pages[:3],
                help="These pages will be sent to Page Auditor"
            )

            if st.button("📋 Add to Audit Queue", type="primary"):
                st.session_state["audit_queue"] = selected_pages
                st.session_state["ctr_gaps"] = filtered
                st.success(f"✅ {len(selected_pages)} pages added to audit queue. Go to Page Auditor →")

    with tab3:
        if filtered.empty:
            st.info("No data to visualize.")
        else:
            col_l, col_r = st.columns(2)

            with col_l:
                # Scatter: Position vs CTR Gap
                fig_scatter = go.Figure()

                # Benchmark line
                positions = list(range(1, 21))
                from utils.gsc_client import get_expected_ctr
                benchmarks = [get_expected_ctr(p) * 100 for p in positions]

                fig_scatter.add_trace(go.Scatter(
                    x=positions, y=benchmarks,
                    mode="lines", name="Benchmark CTR",
                    line=dict(color="#5533ff", width=2, dash="dash"),
                    hovertemplate="Position %{x}: %{y:.1f}% expected<extra></extra>"
                ))

                # Actual data points
                plot_df = filtered.groupby("page").agg(
                    ctr=("ctr", "mean"),
                    position=("position", "mean"),
                    lost=("lost_clicks_estimate", "sum")
                ).reset_index()

                fig_scatter.add_trace(go.Scatter(
                    x=plot_df["position"],
                    y=plot_df["ctr"] * 100,
                    mode="markers",
                    name="Your Pages",
                    marker=dict(
                        size=plot_df["lost"].apply(lambda x: min(max(6, x/5), 20)),
                        color="#ff4455",
                        opacity=0.7,
                    ),
                    text=plot_df["page"].apply(lambda x: x.replace("https://", "")[-40:]),
                    hovertemplate="<b>%{text}</b><br>Position: %{x:.1f}<br>CTR: %{y:.2f}%<extra></extra>"
                ))

                fig_scatter.update_layout(
                    title="Position vs. CTR (Red dots = below benchmark)",
                    paper_bgcolor="#0a0a0f",
                    plot_bgcolor="#12121f",
                    font=dict(color="#e8e8f0", family="IBM Plex Mono"),
                    xaxis=dict(title="Position", gridcolor="#1e1e2e", color="#6b6b8a"),
                    yaxis=dict(title="CTR %", gridcolor="#1e1e2e", color="#6b6b8a"),
                    showlegend=True,
                    legend=dict(bgcolor="#0f0f1a", bordercolor="#1e1e2e"),
                    height=380,
                )
                st.plotly_chart(fig_scatter, use_container_width=True)

            with col_r:
                # Top 15 pages by lost clicks
                top_lost = (
                    filtered.groupby("page")["lost_clicks_estimate"]
                    .sum()
                    .sort_values(ascending=True)
                    .tail(15)
                )
                short_labels = top_lost.index.map(lambda x: "/" + "/".join(x.rstrip("/").split("/")[-2:]))

                fig_bar = go.Figure(go.Bar(
                    x=top_lost.values,
                    y=short_labels,
                    orientation="h",
                    marker=dict(
                        color=top_lost.values,
                        colorscale=[[0, "#2a1a33"], [1, "#ff4455"]],
                    ),
                    hovertemplate="%{y}<br>Lost Clicks: %{x:,}<extra></extra>"
                ))

                fig_bar.update_layout(
                    title="Top 15 Pages - Lost Clicks",
                    paper_bgcolor="#0a0a0f",
                    plot_bgcolor="#12121f",
                    font=dict(color="#e8e8f0", family="IBM Plex Mono"),
                    xaxis=dict(title="Estimated Lost Clicks", gridcolor="#1e1e2e", color="#6b6b8a"),
                    yaxis=dict(color="#6b6b8a"),
                    height=380,
                    margin=dict(l=120),
                )
                st.plotly_chart(fig_bar, use_container_width=True)
