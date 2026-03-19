"""
Cluster Health Check — AI evaluates entire topic clusters
Checks: hub-spoke linking, keyword distribution, content gaps, cannibalization
"""

import streamlit as st
import json
from urllib.parse import urlparse
from config import get_anthropic_key, has_anthropic_key


def _build_cluster_data(cluster, audit_results, topic_clusters, gsc_data, sf_link_map=None):
    """Gather all data for a single cluster for AI evaluation."""
    pages = cluster.get("pages", [])
    if not pages:
        return None

    # Index audit results by URL
    audit_by_url = {r["url"]: r for r in audit_results}

    # Determine hub page (most impressions, or shallowest URL)
    page_urls = [p["page"] for p in pages]
    hub_url = ""
    hub_depth = 999
    for pu in page_urls:
        depth = len(urlparse(pu).path.strip("/").split("/"))
        if depth < hub_depth:
            hub_depth = depth
            hub_url = pu

    hub_audit = audit_by_url.get(hub_url, {})
    hub_content = (hub_audit.get("body_text") or hub_audit.get("intro_text") or "")[:500]

    # Build spoke data
    spokes = []
    spoke_keywords = {}
    for p in pages:
        purl = p["page"]
        if purl == hub_url:
            continue
        pa = audit_by_url.get(purl, {})
        spokes.append({
            "url": purl,
            "title": (pa.get("title") or "")[:80],
            "h1": (pa.get("h1") or "")[:80],
            "word_count": pa.get("word_count", 0),
            "page_type": pa.get("page_type", "unknown"),
            "impressions": p.get("total_impressions", pa.get("impressions", 0)),
            "clicks": p.get("total_clicks", pa.get("clicks", 0)),
            "meta_score": pa.get("meta_score"),
            "content_score": pa.get("content_score"),
        })
        spoke_keywords[purl] = pa.get("target_keywords", [])[:8]

    # Build link map within cluster
    cluster_urls = set(page_urls)

    def _get_outlinks(url):
        """Get internal links from a page (from audit data or SF link map)."""
        links = set()
        pa = audit_by_url.get(url, {})
        il = pa.get("internal_links", [])
        if isinstance(il, list):
            for l in il:
                u = l.get("url", "")
                if u.startswith("/"):
                    domain = urlparse(url).netloc
                    u = f"https://{domain}{u}"
                links.add(u.rstrip("/").lower())
        if sf_link_map:
            for sl in sf_link_map.get("links_from", {}).get(url, []):
                links.add(sl.get("target", "").rstrip("/").lower())
        return links

    hub_outlinks = _get_outlinks(hub_url)

    # Hub → Spoke links
    hub_to_spoke = []
    for s in spokes:
        if s["url"].rstrip("/").lower() in hub_outlinks:
            hub_to_spoke.append(s["url"])

    # Spoke → Hub links
    spoke_to_hub = []
    for s in spokes:
        spoke_links = _get_outlinks(s["url"])
        if hub_url.rstrip("/").lower() in spoke_links:
            spoke_to_hub.append(s["url"])

    # Horizontal links (spoke ↔ spoke)
    horizontal = []
    spoke_urls = [s["url"] for s in spokes]
    for s in spokes:
        s_links = _get_outlinks(s["url"])
        for other in spoke_urls:
            if other != s["url"] and other.rstrip("/").lower() in s_links:
                horizontal.append({"from": s["url"], "to": other})

    # Cannibalization within cluster
    cannibalized = []
    if gsc_data is not None and not gsc_data.empty:
        cluster_gsc = gsc_data[gsc_data["page"].isin(cluster_urls)]
        if not cluster_gsc.empty:
            kw_pages = cluster_gsc.groupby("query")["page"].apply(list).to_dict()
            for kw, kw_pages_list in kw_pages.items():
                if len(set(kw_pages_list)) > 1:
                    cannibalized.append({
                        "keyword": kw,
                        "pages": list(set(kw_pages_list))[:3],
                    })
            cannibalized.sort(key=lambda x: -len(x["pages"]))
            cannibalized = cannibalized[:15]

    return {
        "topic": cluster.get("topic", ""),
        "core_terms": cluster.get("core_terms", []),
        "query_count": cluster.get("query_count", 0),
        "total_impressions": cluster.get("total_impressions", 0),
        "total_clicks": cluster.get("total_clicks", 0),
        "hub_url": hub_url,
        "hub_title": (hub_audit.get("title") or "")[:80],
        "hub_h1": (hub_audit.get("h1") or "")[:80],
        "hub_word_count": hub_audit.get("word_count", 0),
        "hub_outlinks": len(hub_outlinks),
        "hub_content": hub_content,
        "hub_keywords": hub_audit.get("target_keywords", [])[:10],
        "spokes": spokes,
        "spoke_keywords": spoke_keywords,
        "hub_to_spoke_links": hub_to_spoke,
        "spoke_to_hub_links": spoke_to_hub,
        "horizontal_links": horizontal,
        "cannibalized_keywords": cannibalized,
    }


def render():
    st.markdown("## Cluster Health Check")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1.5rem;'>"
        "AI evaluates each topic cluster as a whole: hub-spoke linking, keyword distribution, "
        "content gaps, and cannibalization. This is what Google looks at for topical authority.</p>",
        unsafe_allow_html=True,
    )

    if not has_anthropic_key():
        st.warning("Add Anthropic API key in **1. Setup**")
        return

    tc = st.session_state.get("topic_clusters")
    if not tc:
        st.warning("Run **5. Topic Clusters** first")
        return

    audit_results = st.session_state.get("audit_results", [])
    if not audit_results:
        st.warning("Run **6. Page Auditor** (bulk audit) first — cluster health needs page data")
        return

    gsc_data = st.session_state.get("gsc_data")
    sf_link_map = st.session_state.get("sf_link_map")
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")
    clusters = tc.get("clusters", [])

    # Sort by impressions
    clusters_sorted = sorted(clusters, key=lambda c: -c.get("total_impressions", 0))

    # ── Summary ───────────────────────────────────────────────────
    evaluated = sum(1 for c in clusters_sorted if f"_cluster_health_{hash(c.get('topic','')) & 0xFFFFFF}" in st.session_state)

    # Build site URL list for AI
    all_site_urls = sorted(set(r["url"] for r in audit_results if r.get("url")))
    if gsc_data is not None and hasattr(gsc_data, "page"):
        all_site_urls = sorted(set(all_site_urls + gsc_data["page"].unique().tolist()))

    c1, c2, c3 = st.columns(3)
    c1.metric("Topic clusters", len(clusters_sorted))
    c2.metric("Evaluated", evaluated)
    c3.metric("Total impressions", f"{sum(c.get('total_impressions', 0) for c in clusters_sorted):,}")

    st.markdown("---")

    # ── Bulk evaluate button ──────────────────────────────────────
    col_gen, col_info = st.columns([1, 2])
    with col_gen:
        gen_top = st.button("Evaluate top 5 clusters", type="primary")
    with col_info:
        st.markdown(
            "<span style='font-size:0.75rem; color:#6b6b8a;'>"
            "~30 seconds per cluster. Results cached.</span>",
            unsafe_allow_html=True,
        )

    if gen_top:
        from utils.ai_generator import get_client, evaluate_cluster_health
        client = get_client(get_anthropic_key())

        with st.status("Evaluating clusters...", expanded=True) as status:
            progress = st.progress(0)
            log = st.empty()

            for i, cluster in enumerate(clusters_sorted[:5]):
                topic = cluster.get("topic", f"Cluster {i}")
                health_key = f"_cluster_health_{hash(topic) & 0xFFFFFF}"

                if health_key in st.session_state:
                    log.write(f"[{i+1}/5] {topic} — cached")
                    progress.progress((i + 1) / 5)
                    continue

                log.write(f"[{i+1}/5] Evaluating: {topic}...")
                try:
                    cd = _build_cluster_data(cluster, audit_results, tc, gsc_data, sf_link_map)
                    if cd:
                        result = evaluate_cluster_health(client, cd, site_context, language, all_site_urls)
                        st.session_state[health_key] = result
                except Exception as e:
                    st.session_state[health_key] = {"error": str(e), "health_score": 0}
                progress.progress((i + 1) / 5)

            status.update(label="Evaluation complete", state="complete", expanded=False)
        st.rerun()

    # ── Cluster cards ─────────────────────────────────────────────
    ITEMS_PER_PAGE = 10
    total_items = len(clusters_sorted)
    max_pg = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    pg = st.number_input("Page", min_value=1, max_value=max_pg, value=1, key="cluster_health_page")
    start_i = (pg - 1) * ITEMS_PER_PAGE
    visible = clusters_sorted[start_i:start_i + ITEMS_PER_PAGE]

    for cluster in visible:
        topic = cluster.get("topic", "?")
        health_key = f"_cluster_health_{hash(topic) & 0xFFFFFF}"
        has_eval = health_key in st.session_state
        impr = cluster.get("total_impressions", 0)
        pages_count = cluster.get("page_count", len(cluster.get("pages", [])))
        queries = cluster.get("query_count", 0)

        # Health score badge
        if has_eval:
            health = st.session_state[health_key]
            score = health.get("health_score", 0)
            score_color = "#33dd88" if score >= 70 else "#ffaa33" if score >= 40 else "#ff4455"
            badge = f"<span style='font-size:1.2rem; font-weight:800; color:{score_color};'>{score}/100</span>"
        else:
            badge = "<span style='font-size:0.7rem; color:#6b6b8a;'>NOT EVALUATED</span>"

        st.markdown(
            f"<div style='background:#12121f; border:1px solid #2a2a40; border-radius:6px; padding:1rem; margin-bottom:0.3rem;'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
            f"<div>"
            f"<div style='font-size:1rem; color:#e8e8f0; font-weight:600;'>{topic}</div>"
            f"<div style='font-size:0.72rem; color:#6b6b8a;'>"
            f"{pages_count} pages · {queries} queries · {impr:,} impressions</div>"
            f"</div>"
            f"{badge}"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        with st.expander(f"Health check: {topic}", expanded=False):
            if not has_eval:
                if st.button(f"Evaluate this cluster", key=f"btn_eval_{hash(topic) & 0xFFFFFF}", type="primary"):
                    with st.spinner(f"AI evaluating {topic}..."):
                        try:
                            from utils.ai_generator import get_client, evaluate_cluster_health
                            client = get_client(get_anthropic_key())
                            cd = _build_cluster_data(cluster, audit_results, tc, gsc_data, sf_link_map)
                            if cd:
                                result = evaluate_cluster_health(client, cd, site_context, language, all_site_urls)
                                st.session_state[health_key] = result
                                st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
            else:
                health = st.session_state[health_key]

                if health.get("error"):
                    st.error(f"Evaluation failed: {health['error']}")
                    if st.button("Retry", key=f"btn_retry_cl_{hash(topic) & 0xFFFFFF}"):
                        del st.session_state[health_key]
                        st.rerun()
                    continue

                score = health.get("health_score", 0)
                score_color = "#33dd88" if score >= 70 else "#ffaa33" if score >= 40 else "#ff4455"

                # Summary
                st.markdown(
                    f"<div style='background:#0d0d15; border:2px solid {score_color}; border-radius:8px; padding:1rem; margin-bottom:1rem;'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
                    f"<div style='font-size:0.9rem; color:#e8e8f0;'>{health.get('health_summary', '')}</div>"
                    f"<div style='font-size:2.5rem; font-weight:800; color:{score_color};'>{score}</div>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # Sections
                sections = [
                    ("Hub/Pillar Page", "hub_assessment", "#c8b4ff"),
                    ("Vertical Linking (Hub ↔ Spoke)", "vertical_linking", "#5533ff"),
                    ("Horizontal Linking (Spoke ↔ Spoke)", "horizontal_linking", "#ffaa33"),
                    ("Keyword Distribution", "keyword_issues", "#33dd88"),
                    ("Content Gaps", "content_gaps", "#ff4455"),
                ]

                for section_title, section_key, color in sections:
                    section = health.get(section_key, {})
                    if not section:
                        continue

                    issues = section.get("issues", []) + section.get("hub_to_spoke_missing", []) + section.get("spoke_to_hub_missing", [])
                    missing_conns = section.get("missing_connections", [])
                    misplaced = section.get("misplaced_keywords", [])
                    cannib = section.get("cannibalization", [])
                    missing_subs = section.get("missing_subtopics", [])
                    thin = section.get("thin_pages", [])
                    fixes = section.get("fixes", [])

                    has_problems = bool(issues or missing_conns or misplaced or cannib or missing_subs or thin or fixes)

                    if has_problems:
                        with st.expander(f"{section_title}", expanded=True):
                            # Issues
                            for issue in issues[:5]:
                                if isinstance(issue, str):
                                    st.markdown(f"<div style='color:#ff4455; font-size:0.85rem;'>✗ {issue}</div>", unsafe_allow_html=True)
                                elif isinstance(issue, dict):
                                    st.markdown(f"<div style='color:#ff4455; font-size:0.85rem;'>✗ {issue}</div>", unsafe_allow_html=True)

                            # Missing connections
                            for mc in missing_conns[:5]:
                                st.markdown(
                                    f"<div style='font-size:0.82rem; color:#e8e8f0; padding:2px 0;'>"
                                    f"`{mc.get('from','')}` → `{mc.get('to','')}` — {mc.get('why','')}</div>",
                                    unsafe_allow_html=True,
                                )

                            # Misplaced keywords
                            for mk in misplaced[:5]:
                                st.markdown(
                                    f"<div style='font-size:0.82rem; color:#ffaa33; padding:2px 0;'>"
                                    f"**{mk.get('keyword','')}** is on `{mk.get('current_page','')}` but should be on `{mk.get('should_be_on','')}` — {mk.get('reason','')}</div>",
                                    unsafe_allow_html=True,
                                )

                            # Cannibalization
                            for cn in cannib[:5]:
                                pages_str = ", ".join(f"`{p}`" for p in cn.get("pages", []))
                                st.markdown(
                                    f"<div style='font-size:0.82rem; color:#ff4455; padding:2px 0;'>"
                                    f"**{cn.get('keyword','')}** on multiple pages: {pages_str} — {cn.get('fix','')}</div>",
                                    unsafe_allow_html=True,
                                )

                            # Missing subtopics
                            for ms in missing_subs[:5]:
                                st.markdown(f"<div style='font-size:0.82rem; color:#c8b4ff; padding:2px 0;'>+ Create new page for: **{ms}**</div>", unsafe_allow_html=True)

                            # Thin pages
                            for tp in thin[:5]:
                                st.markdown(
                                    f"<div style='font-size:0.82rem; color:#ffaa33; padding:2px 0;'>"
                                    f"`{tp.get('url','')}` — {tp.get('word_count',0)} words (target: {tp.get('target',1500)})</div>",
                                    unsafe_allow_html=True,
                                )

                            # Fixes
                            if fixes:
                                st.markdown("**What to do:**")
                                for i, fix in enumerate(fixes, 1):
                                    st.markdown(
                                        f"<div style='background:#0d0d15; border-left:3px solid {color}; padding:0.4rem 0.8rem; "
                                        f"border-radius:0 4px 4px 0; margin-bottom:0.3rem;'>"
                                        f"<span style='color:{color}; font-weight:700;'>{i}.</span> "
                                        f"<span style='color:#e8e8f0; font-size:0.85rem;'>{fix}</span></div>",
                                        unsafe_allow_html=True,
                                    )

                # Priority actions
                actions = health.get("priority_actions", [])
                if actions:
                    st.markdown("#### Priority Actions")
                    for a in actions[:10]:
                        impact = a.get("impact", "medium")
                        impact_color = {"high": "#ff4455", "medium": "#ffaa33", "low": "#33dd88"}.get(impact, "#6b6b8a")
                        st.markdown(
                            f"<div style='background:#12121f; border-left:3px solid {impact_color}; padding:0.5rem 0.8rem; "
                            f"border-radius:0 4px 4px 0; margin-bottom:0.4rem;'>"
                            f"<span style='color:{impact_color}; font-size:0.65rem; text-transform:uppercase;'>{impact}</span> "
                            f"<span style='color:#e8e8f0; font-size:0.85rem;'>{a.get('action','')}</span>"
                            f"<span style='color:#6b6b8a; font-size:0.72rem; margin-left:0.5rem;'>"
                            f"{a.get('page','')} · ~{a.get('time_minutes',0)} min</span></div>",
                            unsafe_allow_html=True,
                        )

                # Regenerate
                if st.button("Regenerate evaluation", key=f"btn_regen_cl_{hash(topic) & 0xFFFFFF}"):
                    del st.session_state[health_key]
                    st.rerun()
