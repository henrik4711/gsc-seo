"""
Topic Clusters view.
Groups keywords into topics, maps to pages, identifies content gaps.
"""

import streamlit as st
import pandas as pd


def render():
    st.markdown("## Topic Clusters")
    st.markdown(
        "<p style='color:#9b9bb8; margin-bottom:2rem;'>"
        "Grupperer keywords i topics, viser side-overlap og content gaps</p>",
        unsafe_allow_html=True
    )

    if "gsc_data" not in st.session_state:
        st.warning("Hent GSC data forst (Setup & Connect)")
        return

    df = st.session_state["gsc_data"]

    col1, col2 = st.columns([1, 1])
    with col1:
        min_cluster = st.number_input("Min. queries per cluster", value=2, min_value=2, max_value=10)
    with col2:
        if st.button("Byg Topic Clusters", type="primary", use_container_width=True):
            with st.spinner("Analyserer keyword-topics..."):
                from utils.topic_clusters import build_topic_clusters, identify_content_gaps
                result = build_topic_clusters(df, min_cluster_size=min_cluster)
                st.session_state["topic_clusters"] = result

                # Content gaps
                auth = st.session_state.get("page_authority")
                gaps = identify_content_gaps(result["clusters"], auth)
                st.session_state["content_gaps"] = gaps

    if "topic_clusters" not in st.session_state:
        st.info("Klik 'Byg Topic Clusters' for at starte")
        return

    result = st.session_state["topic_clusters"]
    clusters = result["clusters"]
    overlap = result["overlap_matrix"]
    gaps = st.session_state.get("content_gaps", [])

    if not clusters:
        st.warning("Ingen clusters fundet. Proev at saenke minimum queries.")
        return

    tab1, tab2, tab3, tab4 = st.tabs([
        "Topic Oversigt",
        "Side-Topic Map",
        "Content Gaps",
        "Side Overlap",
    ])

    with tab1:
        _render_clusters(clusters)

    with tab2:
        _render_page_map(result["page_topics"])

    with tab3:
        _render_gaps(gaps)

    with tab4:
        _render_overlap(overlap)


def _render_clusters(clusters):
    st.markdown("### Alle Topic Clusters")

    # Metrics
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Topics", len(clusters))
    with m2:
        total_queries = sum(c["query_count"] for c in clusters)
        st.metric("Queries i clusters", total_queries)
    with m3:
        split_count = sum(1 for c in clusters if c["is_split"])
        st.metric("Split topics", split_count)
    with m4:
        total_impr = sum(c["total_impressions"] for c in clusters)
        st.metric("Total impressions", f"{total_impr:,}")

    # Cluster list
    for i, cluster in enumerate(clusters[:30]):
        split_warn = " [SPLIT]" if cluster["is_split"] else ""
        color = "#ffaa33" if cluster["is_split"] else "#9b9bb8"

        with st.expander(
            f"{cluster['topic']}{split_warn} - "
            f"{cluster['query_count']} queries, {cluster['total_clicks']} klik, "
            f"{cluster['page_count']} sider"
        ):
            st.markdown(f"**Core terms:** {', '.join(cluster['core_terms'])}")
            st.markdown(f"**Impressions:** {cluster['total_impressions']:,}")

            if cluster["is_split"]:
                st.markdown(
                    f"<div style='color:#ffaa33; font-weight:600;'>"
                    f"OBS: Topic fordelt paa {cluster['page_count']} sider - mulig kannibalisering</div>",
                    unsafe_allow_html=True,
                )

            # Pages serving this topic
            st.markdown("**Sider:**")
            for p in cluster["pages"]:
                st.markdown(
                    f"- `{p['page']}` - {p['query_count']} queries, "
                    f"{p['total_clicks']} klik, pos {p['avg_position']:.1f}"
                )

            # Queries in cluster
            st.markdown(f"**Queries:** {', '.join(cluster['queries'][:20])}")
            if len(cluster["queries"]) > 20:
                st.markdown(f"*...og {len(cluster['queries']) - 20} mere*")


def _render_page_map(page_topics):
    st.markdown("### Side-Topic Map")
    st.markdown(
        "<p style='color:#9b9bb8;'>Hvilke topics daekker hver side?</p>",
        unsafe_allow_html=True,
    )

    if not page_topics:
        st.info("Ingen topic data")
        return

    # Build summary table
    records = []
    for page, topics in page_topics.items():
        records.append({
            "page": page,
            "topic_count": len(topics),
            "topics": ", ".join([t["topic"] for t in topics[:5]]),
            "total_clicks": sum(t["clicks"] for t in topics),
        })

    page_df = pd.DataFrame(records).sort_values("topic_count", ascending=False)

    st.dataframe(
        page_df.rename(columns={
            "page": "Side",
            "topic_count": "Topics",
            "topics": "Topic navne",
            "total_clicks": "Total klik",
        }),
        use_container_width=True,
        hide_index=True,
    )


def _render_gaps(gaps):
    st.markdown("### Content Gaps")
    st.markdown(
        "<p style='color:#9b9bb8;'>Topics der er underserved eller har problemer</p>",
        unsafe_allow_html=True,
    )

    if not gaps:
        st.success("Ingen content gaps identificeret")
        return

    high = [g for g in gaps if g["priority"] == "high"]
    medium = [g for g in gaps if g["priority"] == "medium"]

    if high:
        st.markdown(
            "<div style='color:#ff4455; font-weight:600; margin-bottom:0.5rem;'>"
            f"HIGH PRIORITY ({len(high)})</div>",
            unsafe_allow_html=True,
        )
        for gap in high:
            with st.expander(f"{gap['topic']} - {gap['impressions']:,} impressions"):
                for issue in gap["issues"]:
                    st.markdown(f"- {issue}")

    if medium:
        st.markdown(
            "<div style='color:#ffaa33; font-weight:600; margin-top:1rem; margin-bottom:0.5rem;'>"
            f"MEDIUM PRIORITY ({len(medium)})</div>",
            unsafe_allow_html=True,
        )
        for gap in medium:
            with st.expander(f"{gap['topic']} - {gap['impressions']:,} impressions"):
                for issue in gap["issues"]:
                    st.markdown(f"- {issue}")


def _render_overlap(overlap):
    st.markdown("### Side Overlap")
    st.markdown(
        "<p style='color:#9b9bb8;'>"
        "Sider der deler topics boer enten konsolideres eller tydeliggoeres</p>",
        unsafe_allow_html=True,
    )

    if not overlap:
        st.success("Ingen side-overlap fundet")
        return

    for pair in overlap[:20]:
        with st.expander(
            f"{pair['page_1'].split('/')[-2] or pair['page_1']} <-> "
            f"{pair['page_2'].split('/')[-2] or pair['page_2']} "
            f"({pair['shared_topics']} faelles topics)"
        ):
            st.markdown(f"**Side 1:** `{pair['page_1']}`")
            st.markdown(f"**Side 2:** `{pair['page_2']}`")
            st.markdown(f"**Faelles topics:** {', '.join(pair['topic_names'])}")

            # Show authority if available
            if "page_authority" in st.session_state:
                auth = st.session_state["page_authority"]
                for page in [pair["page_1"], pair["page_2"]]:
                    page_auth = auth[auth["page"].str.rstrip("/").str.lower() == page.rstrip("/").lower()]
                    if not page_auth.empty:
                        rd = page_auth.iloc[0].get("referring_domains", 0)
                        st.markdown(f"- `{page}`: **{rd}** referring domains")
