"""
Action Center — One page for ALL recommendations and AI generation.
Replaces the need to navigate between Implementation, Internal Linking,
Missing Keywords, New Articles, etc. Everything happens here.
"""

import streamlit as st
from config import get_anthropic_key, has_anthropic_key
from utils.ui_helpers import stable_hash, normalize_url


def _get_page_actions(audit_results, top_n=100):
    """Build action list per page, sorted by lost clicks."""
    pages = []
    for r in audit_results:
        if not r.get("url"):
            continue
        pages.append({
            "url": r["url"],
            "page_type": r.get("page_type", "unknown"),
            "impressions": r.get("impressions", 0),
            "lost_clicks": r.get("lost_clicks_estimate", 0),
            "meta_score": r.get("meta_score"),
            "content_score": r.get("content_score"),
            "title": r.get("title", ""),
            "word_count": r.get("word_count", 0),
            "audit": r,
        })
    pages.sort(key=lambda p: -p["lost_clicks"])
    return pages[:top_n]


def _action_card(page, idx):
    """Render one action card with collapsed/expanded states."""
    url = page["url"]
    url_hash = stable_hash(url)
    lost = page["lost_clicks"]
    impr = page["impressions"]
    ptype = page["page_type"].upper()
    meta_s = page["meta_score"] or 0
    content_s = page["content_score"] or 0

    # Status badges
    plan_key = f"_ai_plan_{url_hash}"
    text_key = f"_bottom_text_{url_hash}"
    has_plan = plan_key in st.session_state
    has_text = text_key in st.session_state
    is_done = st.session_state.get(f"_action_done_{url_hash}", False)

    # Color border by impact
    border = "#ff4455" if lost > 1000 else "#ffaa33" if lost > 200 else "#6b6b8a"

    # Build status line
    badges = []
    if has_plan:
        badges.append("<span style='color:#33dd88;'>Plan ready</span>")
    if has_text:
        badges.append("<span style='color:#33dd88;'>Text ready</span>")
    if is_done:
        badges.append("<span style='color:#33dd88;'>DONE</span>")
    badges_html = " · ".join(badges) if badges else "<span style='color:#6b6b8a;'>Not started</span>"

    # Card header
    short_url = url.replace("https://", "").replace("http://", "")
    expander_label = f"#{idx+1}  {short_url}  |  {ptype}  |  {lost:,} lost clicks"

    with st.expander(expander_label, expanded=False):
        # Top metrics row
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Impressions", f"{impr:,}")
        c2.metric("Lost clicks", f"{lost:,}")
        c3.metric("Meta score", f"{meta_s}/100" if meta_s else "—")
        c4.metric("Content score", f"{content_s}/100" if content_s else "—")

        st.markdown(f"<div style='font-size:0.8rem; color:#9b9bb8; margin:0.5rem 0;'>{badges_html}</div>", unsafe_allow_html=True)

        # Mark done toggle
        if st.checkbox("Mark as done (hides from list)", value=is_done, key=f"done_{url_hash}"):
            st.session_state[f"_action_done_{url_hash}"] = True

        st.markdown("---")

        # Action buttons row
        bcol1, bcol2, bcol3 = st.columns(3)

        with bcol1:
            if st.button("Generate AI plan", key=f"plan_{url_hash}", use_container_width=True, type="primary" if not has_plan else "secondary"):
                _generate_plan(url, page["audit"])
                st.rerun()

        with bcol2:
            if st.button("Generate page text", key=f"text_{url_hash}", use_container_width=True):
                _generate_page_text(url, page["audit"])
                st.rerun()

        with bcol3:
            if st.button("Open in Implementation", key=f"impl_{url_hash}", use_container_width=True):
                st.session_state["selected_page"] = "14. Implementation"
                st.rerun()

        # Show plan if available
        if has_plan:
            plan = st.session_state[plan_key]
            if not plan.get("error"):
                st.markdown("**AI Plan:**")
                if plan.get("overall_assessment"):
                    st.info(plan["overall_assessment"])

                # Meta title/desc if changed — show current vs new for comparison
                if plan.get("meta_changed") and plan.get("meta_title"):
                    current_title = page.get("title", "") or ""
                    current_desc = page["audit"].get("meta_description", "") or "" if "audit" in page else ""
                    new_title = plan['meta_title']
                    new_desc = plan.get('meta_description', '')
                    # Only show if actually different from current
                    if new_title.strip().lower() != current_title.strip().lower() or new_desc.strip().lower() != current_desc.strip().lower():
                        if current_title:
                            st.markdown(f"**Current title ({len(current_title)} chars):** {current_title}")
                        st.markdown(f"**New title ({len(new_title)} chars):** {new_title}")
                        if current_desc:
                            st.markdown(f"**Current desc ({len(current_desc)} chars):** {current_desc[:100]}...")
                        st.markdown(f"**New desc ({len(new_desc)} chars):** {new_desc}")
                    else:
                        st.markdown(f"**Meta: OK** — AI confirms current meta is fine")

                # Steps
                steps = plan.get("steps", [])
                if steps:
                    st.markdown(f"**{len(steps)} steps:**")
                    for i, s in enumerate(steps[:5], 1):
                        st.markdown(f"{i}. **{s.get('action', '')}** ({s.get('time_minutes', '?')} min) — {s.get('detail', '')}")

                # New content suggestions
                new_content = plan.get("new_content_suggestions", [])
                if new_content:
                    st.markdown("**Suggested new articles:**")
                    for nc in new_content[:3]:
                        st.markdown(f"- *{nc.get('suggested_title', '')}* — {nc.get('why', '')[:120]}")

        # Show generated text if available
        if has_text:
            bt = st.session_state[text_key]
            html = bt.get("html", "")
            if html:
                st.markdown("**Generated text preview:**")
                # Can't nest expander inside an expander — use a toggle instead
                if st.toggle("Show HTML source", key=f"toggle_html_{url_hash}", value=False):
                    st.code(html[:2000] + ("..." if len(html) > 2000 else ""), language="html")
                st.download_button(
                    "Download HTML",
                    data=html,
                    file_name=f"{short_url.replace('/', '_')}.html",
                    mime="text/html",
                    key=f"dl_{url_hash}",
                )


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

        # Gather CTR gaps from profile
        profile = build_page_profile(url)
        _ctr_gaps_for_page = profile["ctr_gaps"]

        with st.spinner("AI generating plan..."):
            result = generate_page_implementation_plan(
                client, audit_data, site_context, all_site_urls, language, topic_clusters,
                ctr_gaps_for_page=_ctr_gaps_for_page,
            )
        st.session_state[f"_ai_plan_{stable_hash(url)}"] = result
        from utils.persistence import save_ai_cache
        save_ai_cache()
        st.success("Plan generated")
    except Exception as e:
        st.error(f"Error: {e}")


def _generate_page_text(url, audit_data):
    """Generate complete category bottom text."""
    if not has_anthropic_key():
        st.error("Anthropic API key missing")
        return
    try:
        from utils.ai_generator import get_client, generate_category_bottom_text
        from urllib.parse import urlparse
        client = get_client(get_anthropic_key())
        site_context = st.session_state.get("site_context", "")
        language = st.session_state.get("content_language", "Swedish")

        # Build URL lists
        audit_results = st.session_state.get("audit_results", [])
        raw_urls = set(r["url"] for r in audit_results if r.get("url"))
        gsc = st.session_state.get("gsc_data")
        if gsc is not None and hasattr(gsc, "page"):
            raw_urls.update(gsc["page"].unique().tolist())
        all_site_urls = sorted(raw_urls)

        # Find subcategory + sibling URLs
        page_path = urlparse(url).path.lower().rstrip("/")
        subcategory_urls = [
            u for u in all_site_urls
            if urlparse(u).path.lower().rstrip("/").startswith(page_path + "/")
            and urlparse(u).path.lower().rstrip("/").count("/") == page_path.count("/") + 1
        ][:20]

        parent_path = "/".join(page_path.split("/")[:-1])
        sibling_urls = [
            u for u in all_site_urls
            if u != url
            and urlparse(u).path.lower().rstrip("/").startswith(parent_path + "/")
            and urlparse(u).path.lower().rstrip("/").count("/") == page_path.count("/")
        ][:15] if parent_path else []

        with st.spinner("AI generating page text..."):
            result = generate_category_bottom_text(
                client, url,
                audit_data.get("title", ""),
                audit_data.get("h1", ""),
                audit_data.get("bottom_text", "") or (audit_data.get("body_text") or "")[-2000:],
                audit_data.get("target_keywords", []),
                subcategory_urls=subcategory_urls,
                sibling_urls=sibling_urls,
                products=None,
                all_site_urls=all_site_urls,
                site_context=site_context,
                language=language,
                current_intro_text=audit_data.get("intro_text", ""),
                impressions=audit_data.get("impressions", 0),
            )
        st.session_state[f"_bottom_text_{stable_hash(url)}"] = result
        from utils.persistence import save_ai_cache
        save_ai_cache()
        st.success("Text generated")
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
            existing_url_paths.add(urlparse(normalize_url(u)).path.lower().rstrip("/"))

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
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Generate plans for top 10 (uncached)", type="primary"):
                missing = [p for p in pages[:10] if f"_ai_plan_{stable_hash(p['url'])}" not in st.session_state]
                if not missing:
                    st.success("All top 10 already have plans")
                else:
                    progress = st.progress(0)
                    for i, p in enumerate(missing):
                        _generate_plan(p["url"], p["audit"])
                        progress.progress((i + 1) / len(missing))
                    st.rerun()
        with col_b:
            if st.button("Clear all generated plans"):
                keys = [k for k in st.session_state if k.startswith("_ai_plan_") or k.startswith("_bottom_text_")]
                for k in keys:
                    del st.session_state[k]
                st.rerun()

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
