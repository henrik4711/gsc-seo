"""
Cluster Health Check — AI evaluates entire topic clusters
Checks: hub-spoke linking, keyword distribution, content gaps, cannibalization

UI-only: every helper that does data prep / AI orchestration lives in
utils/cluster_health_runner.py. This view imports and renders.
"""

import streamlit as st
from config import get_anthropic_key, has_anthropic_key
from utils.ui_helpers import stable_hash
from utils.cluster_health_runner import run_cluster_eval as _run_cluster_eval


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
    total_clusters = len(clusters_sorted)
    col_n, col_gen, col_clear, col_info = st.columns([1, 1.4, 1, 2])
    with col_n:
        # User-configurable how many top clusters to evaluate. Default 5
        # is a sane starting point (~$1.50 + ~2.5 min) but the user is
        # not stuck with it — they can run all 71 in one go if they want.
        n_to_eval = st.number_input(
            "How many",
            min_value=1,
            max_value=max(1, total_clusters),
            value=min(5, total_clusters),
            step=1,
            key="cluster_health_n",
            help=(
                "How many top-impressions clusters to evaluate in this batch. "
                "Skips clusters that already have a cached evaluation. "
                "Cost: ~$0.30 + ~30 sec per cluster."
            ),
        )
    with col_gen:
        gen_top = st.button(
            f"Evaluate {n_to_eval} cluster{'s' if n_to_eval != 1 else ''}",
            type="primary",
        )
    with col_clear:
        if st.button("Clear all cached"):
            keys_to_del = [k for k in st.session_state if k.startswith("_cluster_health_")]
            for k in keys_to_del:
                del st.session_state[k]
            st.rerun()
    with col_info:
        est_cost = n_to_eval * 0.30
        est_min = n_to_eval * 0.5
        st.markdown(
            f"<span style='font-size:0.75rem; color:#6b6b8a;'>"
            f"~${est_cost:.2f} · ~{est_min:.0f} min · skips cached "
            f"({total_clusters} clusters total)</span>",
            unsafe_allow_html=True,
        )

    if gen_top:
        with st.status("Evaluating clusters...", expanded=True) as status:
            progress = st.progress(0)
            log = st.empty()

            n = int(n_to_eval)
            for i, cluster in enumerate(clusters_sorted[:n]):
                topic = cluster.get("topic", f"Cluster {i}")
                health_key = f"_cluster_health_{stable_hash(topic)}"

                if health_key in st.session_state:
                    log.write(f"[{i+1}/{n}] {topic} — cached")
                    progress.progress((i + 1) / n)
                    continue

                log.write(f"[{i+1}/{n}] Evaluating: {topic}...")
                payload = _run_cluster_eval(
                    cluster, audit_results, tc, gsc_data, sf_link_map,
                    site_context, language, all_site_urls, health_key,
                )
                if payload.get("error"):
                    log.write(f"[{i+1}/{n}] {topic} — failed: {payload.get('error_type')}: {payload.get('error')}")
                progress.progress((i + 1) / n)

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

                # Detect the "AI succeeded but returned an empty placeholder"
                # case: score 0 AND no health_summary AND no section data.
                # This used to render as a confusing empty card with just a
                # "Regenerate" button and no indication something was wrong.
                has_real_content = bool(
                    health.get("health_summary")
                    or health.get("hub_assessment")
                    or health.get("vertical_linking")
                    or health.get("horizontal_linking")
                    or health.get("priority_actions")
                )
                if score == 0 and not has_real_content:
                    st.warning(
                        "AI returned an empty/placeholder response (score=0 with "
                        "no summary or sections). Most likely the model copied "
                        "the JSON template literally instead of filling it in. "
                        "Use Regenerate below to retry — usually succeeds on the "
                        "second attempt. The raw response is shown below for "
                        "inspection."
                    )
                    with st.popover("Raw AI response (for debugging)"):
                        import json as _dbg_json
                        st.code(
                            _dbg_json.dumps(health, ensure_ascii=False, indent=2),
                            language="json",
                        )
                elif health.get("_truncated"):
                    # AI ran out of tokens mid-response. We salvaged what
                    # we could but some sections may be incomplete. Tell
                    # the user so they don't act on partial data.
                    st.info(
                        "⚠ This evaluation was salvaged from a truncated AI "
                        "response (the model hit its max_tokens cap before "
                        "finishing). Sections shown are valid but some may be "
                        "missing or partial. Regenerate to try for a full result."
                    )

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
                        # NOTE: cannot use st.expander here — we're
                        # already inside the per-cluster "Health check"
                        # expander, and Streamlit forbids nested expanders
                        # with a hard API error. Render as a styled
                        # bordered section header instead. (Same fix as
                        # the trace-popover crash earlier.)
                        st.markdown(
                            f"<div style='background:#12121f; border-left:4px solid {color}; "
                            f"padding:0.5rem 0.8rem; margin:0.8rem 0 0.4rem 0; border-radius:0 4px 4px 0;'>"
                            f"<span style='color:{color}; font-weight:700; font-size:0.9rem;'>"
                            f"{section_title}</span></div>",
                            unsafe_allow_html=True,
                        )
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
