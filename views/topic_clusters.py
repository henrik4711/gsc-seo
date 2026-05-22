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
        "Groups keywords into topics, shows page overlap and content gaps</p>",
        unsafe_allow_html=True
    )

    if "gsc_data" not in st.session_state:
        st.warning("Go to **1. Setup & Connect** and connect GSC first.")
        return

    df = st.session_state["gsc_data"]

    # ── Clustering method ─────────────────────────────────────────
    st.markdown(
        "<div style='background:#0d0d15; border:2px solid #5533ff; border-radius:8px; padding:1rem; margin-bottom:1rem;'>"
        "<div style='font-family:\"Syne\",sans-serif; font-size:1rem; font-weight:700; color:#c8b4ff; margin-bottom:0.5rem;'>"
        "Choose clustering method</div>"
        "<div style='font-size:0.85rem; color:#9b9bb8;'>"
        "<strong>AI Clustering (recommended)</strong> — Claude analyzes all keywords semantically and groups by topic + intent. "
        "40-80 meaningful clusters.<br>"
        "<strong>Algorithm Clustering</strong> — word-overlap grouping. Fast but creates 200-500 noisy clusters.</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Keyword input cap for AI clustering. Conservative default (500) so the
    # first build always completes even on slow API days; user can raise the
    # slider to pull in more long-tail keywords (= fewer unclustered pages)
    # at the cost of a longer wait. ai_generate_clusters streams the
    # response, so calls won't be killed by Railway's HTTP timeout no matter
    # how long the model takes.
    kw_cap = st.slider(
        "AI clustering — max keywords to send (higher = fewer unclustered pages, but slower + higher AI cost)",
        min_value=250, max_value=5000, value=500, step=250,
        help="The AI clusters the top N keywords by impressions. 500 (default) "
             "is the safe baseline and finishes in ~1 min. Raise to 1000-3000 "
             "for large sites with lots of long-tail queries — expect 2-8 min "
             "wait. Max 5000 (~15 min). Response is streamed, so it won't "
             "time out, but the AI cost scales with the number of keywords.",
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("Build AI Clusters (recommended)", type="primary", use_container_width=True):
            from config import get_anthropic_key, has_anthropic_key
            if not has_anthropic_key():
                st.warning("Add Anthropic API key in Setup")
            else:
                # Estimate wait: ~30s base + ~1s per 10 keywords. Tells user
                # what to expect so they don't think it's hung.
                _est_secs = max(60, int(30 + kw_cap / 10))
                _est_label = f"~{_est_secs // 60} min" if _est_secs >= 120 else f"~{_est_secs} sec"
                with st.spinner(f"AI analyzing {int(kw_cap)} keywords and building clusters... ({_est_label})"):
                    try:
                        from utils.ai_generator import get_client, ai_generate_clusters
                        client = get_client(get_anthropic_key())
                        site_context = st.session_state.get("site_context", "")
                        language = st.session_state.get("content_language", "Swedish")

                        # Prepare keyword data for AI
                        kw_data = df.groupby("query").agg(
                            impressions=("impressions", "sum"),
                            clicks=("clicks", "sum"),
                            pages=("page", lambda x: list(x.unique()[:3])),
                            avg_position=("position", "mean"),
                        ).sort_values("impressions", ascending=False).head(int(kw_cap))

                        keywords_for_ai = []
                        for kw, row in kw_data.iterrows():
                            keywords_for_ai.append({
                                "keyword": kw,
                                "impressions": int(row["impressions"]),
                                "clicks": int(row["clicks"]),
                                "pages": row["pages"],
                                "position": round(float(row["avg_position"]), 1),
                            })

                        result = ai_generate_clusters(client, keywords_for_ai, site_context, language)
                        st.session_state["topic_clusters"] = result

                        # Content gaps + roadmap
                        from utils.topic_clusters import identify_content_gaps, generate_content_roadmap
                        auth = st.session_state.get("page_authority")
                        gaps = identify_content_gaps(result["clusters"], auth)
                        st.session_state["content_gaps"] = gaps

                        roadmap = generate_content_roadmap(
                            clusters=result["clusters"],
                            page_topics=result["page_topics"],
                            gsc_data=df,
                            authority_data=auth,
                        )
                        st.session_state["content_roadmap"] = roadmap

                        from utils.persistence import save_key
                        save_key("topic_clusters")
                        save_key("content_gaps")
                        save_key("content_roadmap")

                        if result.get("ai_summary"):
                            st.success(result["ai_summary"])
                    except Exception as e:
                        st.error(f"Error: {e}")

    with col2:
        min_cluster = st.number_input("Min. queries per cluster", value=5, min_value=2, max_value=20)
        if st.button("Build Algorithm Clusters (fast)", use_container_width=True):
            with st.spinner("Analyzing keyword topics..."):
                from utils.topic_clusters import build_topic_clusters, identify_content_gaps, generate_content_roadmap
                result = build_topic_clusters(df, min_cluster_size=min_cluster)
                st.session_state["topic_clusters"] = result

                auth = st.session_state.get("page_authority")
                gaps = identify_content_gaps(result["clusters"], auth)
                st.session_state["content_gaps"] = gaps

                roadmap = generate_content_roadmap(
                    clusters=result["clusters"],
                    page_topics=result["page_topics"],
                    gsc_data=df,
                    authority_data=auth,
                )
                st.session_state["content_roadmap"] = roadmap

                from utils.persistence import save_key
                save_key("topic_clusters")
                save_key("content_gaps")
                save_key("content_roadmap")

    if "topic_clusters" not in st.session_state:
        st.info("Click 'Build Topic Clusters' to start")
        return

    result = st.session_state["topic_clusters"]
    clusters = result["clusters"]
    overlap = result["overlap_matrix"]
    gaps = st.session_state.get("content_gaps", [])

    if not clusters:
        st.warning("No clusters found. Try lowering the minimum queries.")
        return

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Topic Overview",
        "Page-Topic Map",
        "Content Gaps",
        "Page Overlap",
        "Content Roadmap",
    ])

    with tab1:
        _render_clusters(clusters)

    with tab2:
        _render_page_map(result["page_topics"])

    with tab3:
        _render_gaps(gaps)

    with tab4:
        _render_overlap(overlap)

    with tab5:
        _render_content_roadmap(result)


def _render_clusters(clusters):
    st.markdown("### All Topic Clusters")

    # Metrics
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Topics", len(clusters))
    with m2:
        total_queries = sum(c["query_count"] for c in clusters)
        st.metric("Queries in Clusters", total_queries)
    with m3:
        split_count = sum(1 for c in clusters if c["is_split"])
        st.metric("Split Topics", split_count)
    with m4:
        total_impr = sum(c["total_impressions"] for c in clusters)
        st.metric("Total Impressions", f"{total_impr:,}")

    # Cluster list — paginated
    TC_PER_PAGE = 15
    tc_total = len(clusters)
    tc_max_pg = max(1, (tc_total + TC_PER_PAGE - 1) // TC_PER_PAGE)
    tc_pg = st.number_input("Page", min_value=1, max_value=tc_max_pg, value=1, key="tc_cluster_page")
    tc_start = (tc_pg - 1) * TC_PER_PAGE
    visible_clusters = clusters[tc_start:tc_start + TC_PER_PAGE]
    st.markdown(f"**Showing {tc_start+1}-{min(tc_start+TC_PER_PAGE, tc_total)} of {tc_total} clusters**")

    for i, cluster in enumerate(visible_clusters):
        split_warn = " [SPLIT]" if cluster["is_split"] else ""
        color = "#ffaa33" if cluster["is_split"] else "#9b9bb8"

        with st.expander(
            f"{cluster['topic']}{split_warn} - "
            f"{cluster['query_count']} queries, {cluster['total_clicks']} clicks, "
            f"{cluster['page_count']} pages"
        ):
            st.markdown(f"**Core terms:** {', '.join(cluster['core_terms'])}")
            st.markdown(f"**Impressions:** {cluster['total_impressions']:,}")

            if cluster["is_split"]:
                st.markdown(
                    f"<div style='color:#ffaa33; font-weight:600;'>"
                    f"NOTE: Topic split across {cluster['page_count']} pages - possible cannibalization</div>",
                    unsafe_allow_html=True,
                )

            # Pages serving this topic
            st.markdown("**Pages:**")
            for p in cluster["pages"]:
                st.markdown(
                    f"- `{p['page']}` - {p['query_count']} queries, "
                    f"{p['total_clicks']} clicks, pos {p['avg_position']:.1f}"
                )

            # Queries in cluster
            st.markdown(f"**Queries:** {', '.join(cluster['queries'][:20])}")
            if len(cluster["queries"]) > 20:
                st.markdown(f"*...and {len(cluster['queries']) - 20} more*")


def _render_page_map(page_topics):
    st.markdown("### Page-Topic Map")
    st.markdown(
        "<p style='color:#9b9bb8;'>Which topics does each page cover?</p>",
        unsafe_allow_html=True,
    )

    if not page_topics:
        st.info("No topic data")
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
            "page": "Page",
            "topic_count": "Topics",
            "topics": "Topic Names",
            "total_clicks": "Total Clicks",
        }),
        use_container_width=True,
        hide_index=True,
    )


def _render_gaps(gaps):
    st.markdown("### Content Gaps")
    st.markdown(
        "<p style='color:#9b9bb8;'>Topics that are underserved or have issues</p>",
        unsafe_allow_html=True,
    )

    if not gaps:
        st.success("No content gaps identified")
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
    st.markdown("### Page Overlap")
    st.markdown(
        "<p style='color:#9b9bb8;'>"
        "Pages sharing topics should either be consolidated or differentiated</p>",
        unsafe_allow_html=True,
    )

    if not overlap:
        st.success("No page overlap found")
        return

    for pair in overlap[:20]:
        with st.expander(
            f"{pair['page_1'].split('/')[-2] or pair['page_1']} <-> "
            f"{pair['page_2'].split('/')[-2] or pair['page_2']} "
            f"({pair['shared_topics']} shared topics)"
        ):
            st.markdown(f"**Page 1:** `{pair['page_1']}`")
            st.markdown(f"**Page 2:** `{pair['page_2']}`")
            st.markdown(f"**Shared topics:** {', '.join(pair['topic_names'])}")

            # Show authority if available
            if "page_authority" in st.session_state:
                auth = st.session_state["page_authority"]
                for page in [pair["page_1"], pair["page_2"]]:
                    page_auth = auth[auth["page"].str.rstrip("/").str.lower() == page.rstrip("/").lower()]
                    if not page_auth.empty:
                        rd = page_auth.iloc[0].get("referring_domains", 0)
                        st.markdown(f"- `{page}`: **{rd}** referring domains")


def _render_content_roadmap(topic_result: dict):
    st.markdown("### Content Roadmap")
    st.markdown(
        "<p style='color:#9b9bb8;'>New articles needed to fill content gaps and strengthen topic clusters</p>",
        unsafe_allow_html=True,
    )

    if st.button("Generate Content Roadmap", type="primary"):
        with st.spinner("Analyzing content gaps and generating roadmap..."):
            from utils.topic_clusters import generate_content_roadmap

            gsc_data = st.session_state.get("gsc_data")
            auth_data = st.session_state.get("page_authority")

            roadmap = generate_content_roadmap(
                clusters=topic_result["clusters"],
                page_topics=topic_result["page_topics"],
                gsc_data=gsc_data,
                authority_data=auth_data,
            )
            st.session_state["content_roadmap"] = roadmap
            try:
                from utils.persistence import save_key as _sk
                _sk("content_roadmap")
            except Exception:
                pass

    if "content_roadmap" not in st.session_state:
        st.info("Click 'Generate Content Roadmap' to analyze gaps and suggest new articles")
        return

    roadmap = st.session_state["content_roadmap"]
    articles = roadmap.get("articles_needed", [])
    supporting = roadmap.get("supporting_content", [])

    # Summary metrics
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Articles Needed", roadmap.get("total_articles", 0))
    with m2:
        st.metric("Opportunity (impressions)", f"{roadmap.get('total_opportunity_impressions', 0):,}")
    with m3:
        st.metric("Clusters Needing Depth", roadmap.get("total_supporting_gaps", 0))

    # Tab: New Articles
    if articles:
        st.markdown("---")
        st.markdown(
            "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
            "text-transform:uppercase; letter-spacing:0.1em; margin:1rem 0 0.5rem;'>"
            "SUGGESTED NEW ARTICLES</div>",
            unsafe_allow_html=True,
        )

        for i, article in enumerate(articles[:10]):
            pri = article.get("priority", "medium").upper()
            pri_color = "#ff4455" if pri == "HIGH" else "#ffaa33" if pri == "MEDIUM" else "#6b6b8a"
            ct = article.get("content_type", "guide")
            ct_color = {"how-to": "#33dd88", "comparison": "#c8b4ff", "listicle": "#ffaa33",
                        "explainer": "#6b6baa", "guide": "#5533ff"}.get(ct, "#6b6b8a")

            with st.expander(
                f"{'[' + pri + ']':8s} {article['suggested_title'][:60]} "
                f"({article['estimated_impressions']:,} est. impressions)"
            ):
                # Article info
                st.markdown(
                    f"<div style='display:flex; gap:0.5rem; margin-bottom:0.5rem;'>"
                    f"<span style='background:{ct_color}22; border:1px solid {ct_color}; border-radius:4px; "
                    f"padding:2px 8px; font-size:0.7rem; color:{ct_color};'>{ct.upper()}</span>"
                    f"<span style='background:{pri_color}22; border:1px solid {pri_color}; border-radius:4px; "
                    f"padding:2px 8px; font-size:0.7rem; color:{pri_color};'>PRIORITY: {pri}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                st.markdown(f"**Cluster:** {article.get('cluster_topic', '?')}")
                st.markdown(f"**Subtopic:** {article.get('subtopic', '?')}")

                if article.get("supporting_page"):
                    st.markdown(f"**Supports:** `{article['supporting_page']}`")

                # Target keywords
                kws = article.get("target_keywords", [])
                if kws:
                    kw_badges = " ".join([
                        f"<span style='background:#0d0d15; border:1px solid #5533ff; border-radius:4px; "
                        f"padding:2px 6px; font-size:0.7rem; color:#c8b4ff; margin:2px; display:inline-block;'>{kw}</span>"
                        for kw in kws[:8]
                    ])
                    st.markdown(f"**Target keywords:**<br>{kw_badges}", unsafe_allow_html=True)

                # Internal linking plan
                linking_plan = article.get("internal_linking_plan", [])
                if linking_plan:
                    st.markdown(
                        "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                        "margin-top:0.5rem;'>INTERNAL LINKING PLAN:</div>",
                        unsafe_allow_html=True,
                    )
                    for lp in linking_plan:
                        direction = lp.get("direction", "")
                        from_page = lp["from"][:50]
                        to_page = lp["to"][:50]
                        anchor = lp.get("anchor", "")
                        st.markdown(
                            f"<div style='font-size:0.78rem; padding:2px 0;'>"
                            f"<span style='color:#6b6b8a;'>{direction}:</span> "
                            f"<code>{from_page}</code> -> <code>{to_page}</code><br>"
                            f"<span style='color:#6b6b8a;'>Anchor:</span> "
                            f"<span style='color:#33dd88;'>\"{anchor}\"</span></div>",
                            unsafe_allow_html=True,
                        )

    # Supporting content gaps
    if supporting:
        st.markdown("---")
        st.markdown(
            "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
            "text-transform:uppercase; letter-spacing:0.1em; margin:1rem 0 0.5rem;'>"
            "CLUSTERS NEEDING MORE DEPTH</div>",
            unsafe_allow_html=True,
        )

        for sc in supporting[:10]:
            info_badge = "<span style='color:#33dd88;'>Has guides</span>" if sc["has_informational"] else "<span style='color:#ff4455;'>No guides/blogs</span>"
            st.markdown(
                f"<div style='background:#0d0d15; border:1px solid #1e1e2e; border-radius:6px; "
                f"padding:0.7rem; margin-bottom:0.4rem;'>"
                f"<div style='font-weight:600; color:#e8e8f0;'>{sc['cluster_topic']}</div>"
                f"<div style='font-size:0.78rem; color:#6b6b8a; margin-top:0.3rem;'>"
                f"Pages: {sc['page_count']} | Queries: {sc['query_count']} | "
                f"Impressions: {sc['impressions']:,} | {info_badge}</div>"
                f"<div style='font-size:0.8rem; color:#c8b4ff; margin-top:0.3rem;'>"
                f"-> {sc['recommendation']}</div></div>",
                unsafe_allow_html=True,
            )

    if not articles and not supporting:
        st.success("No content gaps found - your topic coverage looks solid!")
