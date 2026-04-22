"""
Action Center — One page for ALL recommendations and AI generation.
Replaces the need to navigate between Implementation, Internal Linking,
Missing Keywords, New Articles, etc. Everything happens here.
"""

import streamlit as st
from config import get_anthropic_key, has_anthropic_key
from utils.ui_helpers import stable_hash, normalize_url
from utils.url_helpers import url_path as _url_path


def _get_page_actions(audit_results, top_n=100):
    """Build action list per page, sorted by brand-filtered lost clicks.
    Optimized: pre-builds lookup dicts instead of calling build_page_profile per page.
    """
    import pandas as pd

    # ── Pre-build CTR gaps lookup by normalized URL ──
    ctr_gaps_by_url = {}
    ctr_gaps_df = st.session_state.get("ctr_gaps")
    if ctr_gaps_df is not None and isinstance(ctr_gaps_df, pd.DataFrame) and not ctr_gaps_df.empty:
        for _, row in ctr_gaps_df.iterrows():
            norm = normalize_url(row.get("page", ""))
            lost = float(row.get("lost_clicks_estimate", row.get("lost_clicks", 0)) or 0)
            if norm not in ctr_gaps_by_url:
                ctr_gaps_by_url[norm] = 0.0
            ctr_gaps_by_url[norm] += lost

    # ── Pre-build GSC impressions lookup ──
    impressions_by_url = {}
    gsc_data = st.session_state.get("gsc_data")
    if gsc_data is not None and isinstance(gsc_data, pd.DataFrame) and not gsc_data.empty:
        for norm_url, group in gsc_data.groupby(gsc_data["page"].apply(normalize_url)):
            impressions_by_url[norm_url] = int(group["impressions"].sum())

    pages = []
    for r in audit_results:
        if not r.get("url"):
            continue
        norm = normalize_url(r["url"])
        url_hash = stable_hash(r["url"])

        # Quality verdict from cached session state (no expensive profile build)
        quality = st.session_state.get(f"_quality_{url_hash}")
        verdict = quality.get("verdict") if isinstance(quality, dict) else None

        pages.append({
            # Same shape as Quick Wins' _get_top_pages so render_page_actions_card works identically.
            "url": r["url"],
            "page_type": r.get("page_type", "unknown"),
            "impressions": impressions_by_url.get(norm, 0),
            "lost_clicks": ctr_gaps_by_url.get(norm, 0.0),
            "meta_score": r.get("meta_score") or 0,
            "content_score": r.get("content_score") or 0,
            "title": r.get("title", ""),
            "meta_description": r.get("meta_description", ""),
            "h1": r.get("h1", ""),
            "word_count": r.get("word_count", 0),
            "intro_text": r.get("intro_text", ""),
            "bottom_text": r.get("bottom_text", ""),
            "audit": r,
            "quality_verdict": verdict,
            "has_old_text": bool(st.session_state.get(f"_bottom_text_{url_hash}")),
        })
    # Sort: REWRITE pages boosted, then by lost clicks
    for p in pages:
        boost = 1.3 if p["quality_verdict"] == "REWRITE" else 1.1 if p["quality_verdict"] == "IMPROVE" else 1.0
        p["_sort_score"] = p["lost_clicks"] * boost
    pages.sort(key=lambda p: -p["_sort_score"])
    return pages[:top_n]


def _action_card(page, idx):
    """Render one action card — delegates to Quick Wins' render_page_actions_card for 100% parity."""
    url = page["url"]
    url_hash = stable_hash(url)
    lost = page["lost_clicks"]
    impr = page["impressions"]
    ptype = page["page_type"].upper()

    # Same done flag as Quick Wins — marking done here also hides the page in Quick Wins.
    plan_key = f"_ai_plan_{url_hash}"
    text_key = f"_bottom_text_{url_hash}"
    has_plan = plan_key in st.session_state
    has_text = text_key in st.session_state
    is_done = st.session_state.get(f"_qw_done_{url_hash}", False)

    badges = []
    if has_plan:
        badges.append("Plan ready")
    if has_text:
        badges.append("Text ready")
    if is_done:
        badges.append("DONE")
    badges_html = " · ".join(badges) if badges else "Not started"

    short_url = url.replace("https://", "").replace("http://", "")
    # Streamlit forbids nested expanders. Quick Wins' shared card uses inner
    # expanders heavily, so the outer collapse here is a button-toggled
    # container instead of st.expander.
    toggle_key = f"_ac_open_{url_hash}"
    is_open = st.session_state.get(toggle_key, False)

    border = "#ff4455" if lost > 1000 else "#ffaa33" if lost > 200 else "#2a2a40"
    st.markdown(
        f"<div style='background:#0d0d15; border-left:4px solid {border}; "
        f"padding:0.6rem 0.8rem; border-radius:0 4px 4px 0; margin-bottom:0.2rem;'>"
        f"<div style='font-size:0.85rem; color:#e8e8f0;'><strong>#{idx+1}</strong> "
        f"<span style='color:#9b9bb8;'>{short_url}</span> "
        f"<span style='color:#6b6b8a;'>· {ptype} · {lost:,} lost clicks · {badges_html}</span></div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    btn_label = "▾ Hide details" if is_open else "▸ Show details"
    if st.button(btn_label, key=f"toggle_{url_hash}", use_container_width=True):
        st.session_state[toggle_key] = not is_open
        st.rerun()

    if is_open:
        from views.quick_wins import render_page_actions_card
        render_page_actions_card(page, idx=idx, total_pages=None, on_skip=None)
        st.markdown("---")


def _generate_plan(url, audit_data):
    """Generate AI implementation plan for a URL."""
    if not has_anthropic_key():
        st.error("Anthropic API key missing")
        return
    try:
        from utils.ai_generator import get_client, generate_page_implementation_plan
        from utils.page_profile import build_page_profile
        client = get_client(get_anthropic_key())
        site_context = st.session_state.get("site_context", "")
        language = st.session_state.get("content_language", "Swedish")
        topic_clusters = st.session_state.get("topic_clusters", {})

        # Build all_site_urls
        audit_results = st.session_state.get("audit_results", [])
        raw_urls = set(r["url"] for r in audit_results if r.get("url"))
        gsc = st.session_state.get("gsc_data")
        if gsc is not None and hasattr(gsc, "page"):
            raw_urls.update(gsc["page"].unique().tolist())
        all_site_urls = sorted(raw_urls)

        # Gather all derived signals from profile (single source of truth)
        profile = build_page_profile(url)

        with st.spinner("AI generating plan..."):
            result = generate_page_implementation_plan(
                client, audit_data, site_context, all_site_urls, language, topic_clusters,
                ctr_gaps_for_page=profile.get("ctr_gaps") or [],
                cannibal_link_targets=profile.get("cannibal_link_targets") or [],
                cluster_link_outgoing=profile.get("cluster_link_outgoing") or [],
                structural_signals=profile.get("structural_signals") or {},
                editorial_images=profile.get("editorial_images") or [],
            )
        st.session_state[f"_ai_plan_{stable_hash(url)}"] = result
        from utils.persistence import save_ai_cache
        save_ai_cache()
        st.success("Plan generated")
    except Exception as e:
        st.error(f"Error: {e}")




def _technical_section():
    """Show technical SEO issues from crawl analysis."""
    issues = st.session_state.get("sf_crawl_issues", {})
    if not issues:
        st.info("No crawl issues data. Run **Analyze Crawl Issues** in Run Pipeline.")
        return

    counts = {k: len(v) for k, v in issues.items() if v}
    if not counts:
        st.success("No technical issues found")
        return

    st.markdown("### Technical Issues (Magento 1.9)")
    cols = st.columns(4)
    items = list(counts.items())[:4]
    for i, (key, count) in enumerate(items):
        cols[i].metric(key.replace("_", " ").title(), f"{count:,}")

    if len(counts) > 4:
        cols2 = st.columns(4)
        for i, (key, count) in enumerate(list(counts.items())[4:8]):
            cols2[i].metric(key.replace("_", " ").title(), f"{count:,}")

    st.markdown("**Top issues to fix:**")
    priority_order = ["broken_links", "near_duplicates", "canonical_issues", "orphan_pages", "faceted_urls"]
    for key in priority_order:
        if issues.get(key):
            with st.expander(f"{key.replace('_', ' ').title()} ({len(issues[key])} items)", expanded=False):
                for item in issues[key][:20]:
                    url = item.get("url", "")
                    action = item.get("action", "")
                    st.markdown(f"- `{url}` — {action}")


def _new_articles_section():
    """Show new article suggestions from content roadmap."""
    roadmap = st.session_state.get("content_roadmap", {})
    articles = roadmap.get("new_articles", []) if isinstance(roadmap, dict) else []

    # Also collect from individual page plans
    plan_articles = []
    for key, val in st.session_state.items():
        if key.startswith("_ai_plan_") and isinstance(val, dict):
            for nc in val.get("new_content_suggestions", []):
                if nc.get("suggested_title"):
                    plan_articles.append(nc)

    all_articles = articles + plan_articles
    if not all_articles:
        st.info("No new article suggestions yet. Generate plans for top pages to get suggestions.")
        return

    # Build existing page titles/URLs for duplicate checking
    audit_results = st.session_state.get("audit_results", [])
    existing_titles = set()
    existing_url_paths = set()
    for r in audit_results:
        t = (r.get("title") or "").lower().strip()
        if t:
            existing_titles.add(t)
        u = r.get("url", "")
        if u:
            from urllib.parse import urlparse
            existing_url_paths.add(_url_path(normalize_url(u)).lower())

    st.markdown(f"### {len(all_articles)} New Articles to Write")
    for i, art in enumerate(all_articles[:20]):
        title = art.get("suggested_title") or art.get("title", "")
        keywords = art.get("target_keywords", [])
        why = art.get("why", "")

        # Check if similar article/page already exists
        already_exists = title.lower().strip() in existing_titles
        if not already_exists and keywords:
            # Check if any keyword matches an existing URL path segment
            for kw in keywords[:3]:
                kw_slug = kw.lower().replace(" ", "-")
                for ep in existing_url_paths:
                    if kw_slug in ep:
                        already_exists = True
                        break
                if already_exists:
                    break

        expander_label = f"{i+1}. {title}" + (" — MAY ALREADY EXIST" if already_exists else "")
        with st.expander(expander_label, expanded=False):
            if already_exists:
                st.warning("A page with a similar title or keyword already exists on the site. Check before creating.")
            if keywords:
                st.markdown(f"**Keywords:** {', '.join(keywords[:8])}")
            if why:
                st.markdown(f"**Why:** {why}")
            link_from = art.get("link_from") or art.get("supporting_page", "")
            if link_from:
                st.markdown(f"**Link from:** `{link_from}`")
            st.button("Generate full article", key=f"art_{i}_{stable_hash(title)}", help="Coming soon")


def render():
    st.markdown("## 🎯 Action Center")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1rem;'>"
        "All recommendations and AI generation in one place. Top 100 pages by impact.</p>",
        unsafe_allow_html=True,
    )

    if "audit_results" not in st.session_state or not st.session_state["audit_results"]:
        st.warning("No audit data. Go to **⚡ Run Pipeline** and run all steps first.")
        return

    audit_results = st.session_state["audit_results"]

    # ── Tabs ───────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["🎯 Top Impact (100 pages)", "📝 New Articles", "⚙ Technical"])

    with tab1:
        # Filter: hide done
        hide_done = st.checkbox("Hide pages marked as done", value=True)

        pages = _get_page_actions(audit_results, top_n=100)
        if hide_done:
            pages = [p for p in pages if not st.session_state.get(f"_action_done_{stable_hash(p['url'])}", False)]

        # Summary
        total_lost = sum(p["lost_clicks"] for p in pages)
        with_plan = sum(1 for p in pages if f"_ai_plan_{stable_hash(p['url'])}" in st.session_state)

        c1, c2, c3 = st.columns(3)
        c1.metric("Pages shown", len(pages))
        c2.metric("Total lost clicks", f"{total_lost:,}")
        c3.metric("Plans generated", f"{with_plan}/{len(pages)}")

        # Bulk actions
        col_a, col_b, col_c = st.columns([2, 1, 1])
        with col_a:
            n_to_generate = st.number_input(
                "How many top pages to generate plans for",
                min_value=1, max_value=len(pages), value=min(10, len(pages)),
                key="ac_gen_n",
                help="Generates plans for the top N pages by impact. Skips pages that already have a plan.",
            )
            if st.button(f"Generate plans for top {n_to_generate} (uncached)", type="primary", key="ac_gen_btn"):
                missing = [p for p in pages[:n_to_generate] if f"_ai_plan_{stable_hash(p['url'])}" not in st.session_state]
                if not missing:
                    st.success(f"All top {n_to_generate} already have plans — use 'Clear all plans' first to regenerate with fresh data.")
                else:
                    progress = st.progress(0)
                    status_txt = st.empty()
                    for i, p in enumerate(missing):
                        status_txt.text(f"[{i+1}/{len(missing)}] {p['url']}")
                        _generate_plan(p["url"], p["audit"])
                        progress.progress((i + 1) / len(missing))
                    status_txt.empty()
                    st.success(f"Generated {len(missing)} new plans")
                    st.rerun()
        with col_b:
            if st.button("🗑 Clear all plans", key="ac_clear_btn", use_container_width=True):
                import os
                try:
                    from utils.persistence import AI_CACHE_DIR
                except Exception:
                    AI_CACHE_DIR = None
                # Clear session state
                keys = [k for k in st.session_state if k.startswith("_ai_plan_") or k.startswith("_bottom_text_") or k.startswith("_intro_text_")]
                for k in keys:
                    del st.session_state[k]
                # Clear disk cache so plans don't reload on refresh
                disk_cleared = 0
                if AI_CACHE_DIR and os.path.isdir(AI_CACHE_DIR):
                    for f in os.listdir(AI_CACHE_DIR):
                        if f.startswith("_ai_plan_") or f.startswith("_bottom_text_") or f.startswith("_intro_text_"):
                            try:
                                os.remove(os.path.join(AI_CACHE_DIR, f))
                                disk_cleared += 1
                            except Exception:
                                pass
                st.success(f"Cleared {len(keys)} session keys + {disk_cleared} disk files")
                st.rerun()
        with col_c:
            st.caption(f"Existing: {with_plan} plans")

        st.markdown("---")

        # Pagination
        PER_PAGE = 20
        total_pages = max(1, (len(pages) + PER_PAGE - 1) // PER_PAGE)
        page_num = st.number_input("Page", min_value=1, max_value=total_pages, value=1, key="ac_page")
        start = (page_num - 1) * PER_PAGE
        visible = pages[start:start + PER_PAGE]
        st.markdown(f"**Showing {start+1}-{min(start+PER_PAGE, len(pages))} of {len(pages)}**")

        for i, p in enumerate(visible):
            _action_card(p, start + i)

    with tab2:
        _new_articles_section()

    with tab3:
        _technical_section()
