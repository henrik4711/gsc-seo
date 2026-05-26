"""
Cluster Health Check — AI evaluates entire topic clusters
Checks: hub-spoke linking, keyword distribution, content gaps, cannibalization
"""

import streamlit as st
from utils.url_helpers import url_segments as _url_segments
import json
from urllib.parse import urlparse
from config import get_anthropic_key, has_anthropic_key
from utils.ui_helpers import stable_hash


def _build_cluster_data(cluster, audit_results, topic_clusters, gsc_data, sf_link_map=None):
    """Gather all data for a single cluster for AI evaluation."""
    from utils.page_profile import build_page_profile
    from utils.ui_helpers import normalize_url as _nu

    pages = cluster.get("pages", [])
    if not pages:
        return None

    # Determine hub page (most impressions, or shallowest URL).
    # DEFENSIVE: skip any cluster entry where 'page' is not a string —
    # legacy / corrupted topic_clusters.json could carry dict-shaped
    # 'page' values that crash `set(page_urls)` below with
    # "unhashable type: 'dict'" and kill the whole cluster evaluation.
    page_urls = [
        p["page"] for p in pages
        if isinstance(p, dict) and isinstance(p.get("page"), str) and p["page"]
    ]
    if not page_urls:
        return None
    hub_url = ""
    hub_depth = 999
    for pu in page_urls:
        depth = len(_url_segments(pu))
        if depth < hub_depth:
            hub_depth = depth
            hub_url = pu

    hub_profile = build_page_profile(hub_url)
    hub_content = (hub_profile["body_text"] or hub_profile["intro_text"] or "")[:500]
    # DEFENSIVE: same isinstance guard on link entries — page_profile
    # *should* always produce {"url": str, "anchor": str}, but persisted
    # legacy data may not, and a single bad row would crash the entire
    # cluster eval. Skip malformed entries instead.
    hub_outlink_targets = {
        _nu(l["url"]) for l in hub_profile["internal_links_out"]
        if isinstance(l, dict) and isinstance(l.get("url"), str)
    }

    # Build spoke data. Iterate over the pre-filtered page_urls list
    # (built above with the isinstance guard) so we never feed a
    # malformed `page` value into build_page_profile or set ops below.
    spokes = []
    spoke_keywords = {}
    spoke_profiles = {}  # cache profiles for link checks
    hub_norm = _nu(hub_url)
    for purl in page_urls:
        if _nu(purl) == hub_norm:
            continue
        profile = build_page_profile(purl)
        spoke_profiles[purl] = profile
        # Carry forward the matching p-dict (for impressions/clicks)
        p = next(
            (x for x in pages
             if isinstance(x, dict) and x.get("page") == purl),
            {}
        )
        spokes.append({
            "url": purl,
            "title": profile["title"][:80],
            "h1": profile["h1"][:80],
            "word_count": profile["word_count"],
            "page_type": profile["page_type"],
            "impressions": profile["total_impressions"] or p.get("total_impressions", 0),
            "clicks": profile["total_clicks"] or p.get("total_clicks", 0),
            "meta_score": profile["content_audit"].get("meta_score"),
            "content_score": profile["content_audit"].get("content_score"),
        })
        spoke_keywords[purl] = profile["content_audit"].get("target_keywords", [])[:8]

    # Build link map within cluster
    cluster_urls = set(page_urls)

    # Hub → Spoke links
    hub_to_spoke = []
    for s in spokes:
        if _nu(s["url"]) in hub_outlink_targets:
            hub_to_spoke.append(s["url"])

    # Spoke → Hub links (same defensive guard — bad rows skipped)
    spoke_to_hub = []
    for s in spokes:
        sp = spoke_profiles[s["url"]]
        spoke_outlink_targets = {
            _nu(l["url"]) for l in sp["internal_links_out"]
            if isinstance(l, dict) and isinstance(l.get("url"), str)
        }
        if _nu(hub_url) in spoke_outlink_targets:
            spoke_to_hub.append(s["url"])

    # Horizontal links (spoke ↔ spoke)
    horizontal = []
    spoke_urls = [s["url"] for s in spokes]
    for s in spokes:
        sp = spoke_profiles[s["url"]]
        s_targets = {
            _nu(l["url"]) for l in sp["internal_links_out"]
            if isinstance(l, dict) and isinstance(l.get("url"), str)
        }
        for other in spoke_urls:
            if other != s["url"] and _nu(other) in s_targets:
                horizontal.append({"from": s["url"], "to": other})

    # Cannibalization within cluster
    cannibalized = []
    if gsc_data is not None and not gsc_data.empty:
        cluster_urls_norm = set(_nu(u) for u in cluster_urls)
        cluster_gsc = gsc_data[gsc_data["page"].apply(_nu).isin(cluster_urls_norm)]
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

    # ── Link health issues ────────────────────────────────────
    link_issues = []

    # Hub→Spoke: hub MUST link to all spokes
    spokes_without_hub_link = [s["url"] for s in spokes if s["url"] not in hub_to_spoke]
    if spokes_without_hub_link:
        link_issues.append({
            "severity": "critical" if len(spokes_without_hub_link) > len(spokes) * 0.5 else "warn",
            "type": "hub_to_spoke_missing",
            "msg": f"Hub does NOT link to {len(spokes_without_hub_link)}/{len(spokes)} spoke pages. Hub must link down to all spokes.",
            "pages": spokes_without_hub_link[:10],
        })

    # Spoke→Hub: all spokes MUST link back to hub
    spokes_without_backlink = [s["url"] for s in spokes if s["url"] not in spoke_to_hub]
    if spokes_without_backlink:
        link_issues.append({
            "severity": "critical" if len(spokes_without_backlink) > len(spokes) * 0.5 else "warn",
            "type": "spoke_to_hub_missing",
            "msg": f"{len(spokes_without_backlink)}/{len(spokes)} spokes do NOT link back to hub. Every spoke must link to its pillar.",
            "pages": spokes_without_backlink[:10],
        })

    # Horizontal: spokes should cross-link to siblings
    spoke_with_sibling_links = set()
    for h in horizontal:
        spoke_with_sibling_links.add(h["from"])
    isolated_spokes = [s["url"] for s in spokes if s["url"] not in spoke_with_sibling_links]
    if isolated_spokes and len(spokes) >= 3:
        link_issues.append({
            "severity": "warn",
            "type": "isolated_spokes",
            "msg": f"{len(isolated_spokes)}/{len(spokes)} spokes have no horizontal links to sibling pages.",
            "pages": isolated_spokes[:10],
        })

    return {
        "topic": cluster.get("topic", ""),
        "core_terms": cluster.get("core_terms", []),
        "query_count": cluster.get("query_count", 0),
        "total_impressions": cluster.get("total_impressions", 0),
        "total_clicks": cluster.get("total_clicks", 0),
        "hub_url": hub_url,
        "hub_title": hub_profile["title"][:80],
        "hub_h1": hub_profile["h1"][:80],
        "hub_word_count": hub_profile["word_count"],
        "hub_outlinks": len(hub_outlink_targets),
        "hub_content": hub_content,
        "hub_keywords": hub_profile["content_audit"].get("target_keywords", [])[:10],
        "spokes": spokes,
        "spoke_keywords": spoke_keywords,
        "hub_to_spoke_links": hub_to_spoke,
        "spoke_to_hub_links": spoke_to_hub,
        "horizontal_links": horizontal,
        "link_issues": link_issues,
        "cannibalized_keywords": cannibalized,
    }


def _run_cluster_eval(
    cluster: dict,
    audit_results,
    tc: dict,
    gsc_data,
    sf_link_map,
    site_context: str,
    language: str,
    all_site_urls,
    health_key: str,
) -> dict:
    """Single source of truth for evaluating one cluster + persisting.

    Wraps the whole flow (_build_cluster_data → AI call → save) in one
    except handler that ALWAYS persists a structured result so the UI
    never lands in the inconsistent 'NOT EVALUATED + Error: ...' state
    we kept hitting before — every callsite (batch, per-cluster button,
    retry) now goes through this so they all behave the same way on
    failure. Returns the persisted dict so the caller can act on it
    (e.g. log progress) without having to re-read session_state.
    """
    from utils.ai_generator import get_client, evaluate_cluster_health
    from utils.persistence import save as _persist_save
    from config import get_anthropic_key

    try:
        client = get_client(get_anthropic_key())
        cd = _build_cluster_data(cluster, audit_results, tc, gsc_data, sf_link_map)
        if not cd:
            payload = {
                "error": "Cluster had no usable pages after defensive filtering",
                "error_type": "NoUsablePages",
                "traceback": "",
                "health_score": 0,
            }
        else:
            payload = evaluate_cluster_health(
                client, cd, site_context, language, all_site_urls,
            )
    except Exception as e:
        import traceback as _tb_run
        tb_text = _tb_run.format_exc()
        # Print to Railway logs too so the trace is recoverable even if
        # the UI render path itself has a bug — belt and braces.
        print(f"[cluster_health] eval failed for {cluster.get('topic', '?')}: {e}")
        print(tb_text)
        payload = {
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": tb_text[-2000:],
            "health_score": 0,
        }

    st.session_state[health_key] = payload
    try:
        _persist_save(health_key)
    except Exception as save_e:
        print(f"[cluster_health] persist failed for {health_key}: {save_e}")
    return payload


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
    evaluated = sum(1 for c in clusters_sorted if f"_cluster_health_{stable_hash(c.get('topic',''))}" in st.session_state)

    # Build site URL list for AI
    all_site_urls = sorted(set(r["url"] for r in audit_results if r.get("url")))
    if gsc_data is not None and hasattr(gsc_data, "page"):
        all_site_urls = sorted(set(all_site_urls + gsc_data["page"].unique().tolist()))

    c1, c2, c3 = st.columns(3)
    c1.metric("Topic clusters", len(clusters_sorted))
    c2.metric("Evaluated", evaluated)
    c3.metric("Total impressions", f"{sum(c.get('total_impressions', 0) for c in clusters_sorted):,}")

    st.markdown("---")

    # ── Bulk evaluate / Clear buttons ────────────────────────────
    col_gen, col_clear, col_info = st.columns([1, 1, 2])
    with col_gen:
        gen_top = st.button("Evaluate top 5 clusters", type="primary")
    with col_clear:
        if st.button("Clear all cached evaluations"):
            keys_to_del = [k for k in st.session_state if k.startswith("_cluster_health_")]
            for k in keys_to_del:
                del st.session_state[k]
            st.rerun()
    with col_info:
        st.markdown(
            "<span style='font-size:0.75rem; color:#6b6b8a;'>"
            "~30 seconds per cluster. Results cached.</span>",
            unsafe_allow_html=True,
        )

    if gen_top:
        with st.status("Evaluating clusters...", expanded=True) as status:
            progress = st.progress(0)
            log = st.empty()

            for i, cluster in enumerate(clusters_sorted[:5]):
                topic = cluster.get("topic", f"Cluster {i}")
                health_key = f"_cluster_health_{stable_hash(topic)}"

                if health_key in st.session_state:
                    log.write(f"[{i+1}/5] {topic} — cached")
                    progress.progress((i + 1) / 5)
                    continue

                log.write(f"[{i+1}/5] Evaluating: {topic}...")
                payload = _run_cluster_eval(
                    cluster, audit_results, tc, gsc_data, sf_link_map,
                    site_context, language, all_site_urls, health_key,
                )
                if payload.get("error"):
                    log.write(f"[{i+1}/5] {topic} — failed: {payload.get('error_type')}: {payload.get('error')}")
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
        health_key = f"_cluster_health_{stable_hash(topic)}"
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
                if st.button(f"Evaluate this cluster", key=f"btn_eval_{stable_hash(topic)}", type="primary"):
                    with st.spinner(f"AI evaluating {topic}..."):
                        _run_cluster_eval(
                            cluster, audit_results, tc, gsc_data, sf_link_map,
                            site_context, language, all_site_urls, health_key,
                        )
                        st.rerun()
            else:
                health = st.session_state[health_key]

                if health.get("error"):
                    err_type = health.get("error_type", "")
                    err_text = health.get("error", "")
                    label = f"{err_type}: {err_text}" if err_type else err_text
                    st.error(f"Evaluation failed — {label}")
                    tb = health.get("traceback", "")
                    if tb:
                        # NOTE: cannot use st.expander here — this whole
                        # block is already inside an outer st.expander
                        # (the per-cluster "Health check: …" expander)
                        # and Streamlit forbids nested expanders with a
                        # hard API error. Use st.popover, which is
                        # explicitly allowed inside expanders. See
                        # mshop_admin_push_ui.py for the same workaround.
                        with st.popover("Stack trace (for debugging)"):
                            st.code(tb, language="python")
                    else:
                        st.caption(
                            "No stack trace was captured for this cached failure "
                            "(it was stored before the trace-capture fix shipped). "
                            "Click Retry to re-run with the new error handler — the "
                            "trace will appear if it fails again."
                        )
                    if st.button("Retry", key=f"btn_retry_cl_{stable_hash(topic)}"):
                        with st.spinner(f"Re-running evaluation for {topic}..."):
                            _run_cluster_eval(
                                cluster, audit_results, tc, gsc_data, sf_link_map,
                                site_context, language, all_site_urls, health_key,
                            )
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
                if st.button("Regenerate evaluation", key=f"btn_regen_cl_{stable_hash(topic)}"):
                    del st.session_state[health_key]
                    st.rerun()
