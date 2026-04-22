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
            "url": r["url"],
            "page_type": r.get("page_type", "unknown"),
            "impressions": impressions_by_url.get(norm, 0),
            "lost_clicks": ctr_gaps_by_url.get(norm, 0.0),
            "meta_score": r.get("meta_score"),
            "content_score": r.get("content_score"),
            "title": r.get("title", ""),
            "word_count": r.get("word_count", 0),
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

        # ── Row 1: plan + open in Implementation ──────────────
        bcol1, bcol2 = st.columns(2)
        with bcol1:
            if st.button("Generate AI plan", key=f"plan_{url_hash}", use_container_width=True, type="primary" if not has_plan else "secondary"):
                _generate_plan(url, page["audit"])
                st.rerun()
        with bcol2:
            if st.button("Open in Implementation", key=f"impl_{url_hash}", use_container_width=True):
                st.session_state["selected_page"] = "14. Implementation"
                st.rerun()

        # ── Row 2: per-section generation (same as Quick Wins) ──
        meta_key = f"_meta_suggestions_{url_hash}"
        intro_key = f"_intro_text_{url_hash}"
        has_meta_suggest = meta_key in st.session_state
        has_intro = intro_key in st.session_state

        gcol1, gcol2, gcol3 = st.columns(3)
        with gcol1:
            lbl_meta = "Regenerate meta title + description" if has_meta_suggest else "Generate meta title + description"
            if st.button(lbl_meta, key=f"meta_{url_hash}", use_container_width=True):
                _generate_meta(url, page["audit"])
                st.rerun()
        with gcol2:
            lbl_intro = "Regenerate intro text" if has_intro else "Generate intro text (above product grid)"
            if st.button(lbl_intro, key=f"intro_{url_hash}", use_container_width=True):
                _generate_intro(url, page["audit"])
                st.rerun()
        with gcol3:
            lbl_bottom = "Regenerate footer text" if has_text else "Generate footer text (with links + products + images)"
            if st.button(lbl_bottom, key=f"text_{url_hash}", use_container_width=True,
                         type="primary" if not has_text else "secondary"):
                _generate_page_text(url, page["audit"])
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

        # ── Show meta suggestions if available ─────────────────
        if has_meta_suggest:
            meta_res = st.session_state[meta_key]
            if isinstance(meta_res, dict) and not meta_res.get("error"):
                variants = meta_res.get("variants", [])
                if variants:
                    st.markdown("**Meta title + description — pick a variant:**")
                    current_title = page["audit"].get("title", "") or ""
                    current_desc = page["audit"].get("meta_description", "") or ""
                    st.caption(f"Current title ({len(current_title)} chars): {current_title}")
                    st.caption(f"Current desc ({len(current_desc)} chars): {current_desc[:120]}")
                    for vi, v in enumerate(variants[:3], 1):
                        t = v.get("title", "")
                        d = v.get("description", "")
                        strategy = v.get("strategy", "")
                        st.markdown(
                            f"**Variant {vi}** · Title ({len(t)} chars) · Desc ({len(d)} chars)  \n"
                            f"Title: `{t}`  \n"
                            f"Description: `{d}`  \n"
                            f"<span style='color:#9b9bb8; font-size:0.8rem;'>Strategy: {strategy}</span>",
                            unsafe_allow_html=True,
                        )
                        st.code(f"Title: {t}\nDescription: {d}", language="text")
            elif isinstance(meta_res, dict) and meta_res.get("error"):
                st.error(f"Meta generation failed: {meta_res['error']}")

        # ── Show intro text if available ───────────────────────
        if has_intro:
            intro_res = st.session_state[intro_key]
            if isinstance(intro_res, dict) and not intro_res.get("error"):
                new_intro = (
                    intro_res.get("rewritten_intro")
                    or intro_res.get("optimized_text")
                    or intro_res.get("html", "")
                    or intro_res.get("text", "")
                )
                if new_intro:
                    st.markdown(f"**New intro text** ({len(new_intro.split())} words) — paste ABOVE product grid:")
                    st.markdown(
                        f"<div style='background:#0d1a0d; border-left:3px solid #33dd88; padding:0.8rem; border-radius:0 6px 6px 0;'>"
                        f"<div style='color:#e8e8f0; line-height:1.6;'>{new_intro}</div></div>",
                        unsafe_allow_html=True,
                    )
                    st.code(new_intro, language="text")
            elif isinstance(intro_res, dict) and intro_res.get("error"):
                st.error(f"Intro generation failed: {intro_res['error']}")

        # ── Show generated footer/bottom text if available ─────
        if has_text:
            bt = st.session_state[text_key]
            has_new_format = bt.get("top_html") or bt.get("bottom_html") or bt.get("faq_schema")
            if not has_new_format and bt.get("html"):
                st.warning("⚠ Text generated with old rules — regenerate for FAQ schema, product images, and correct links.")
            html = bt.get("bottom_html") or bt.get("html", "")
            wc = bt.get("bottom_word_count") or bt.get("word_count", 0)
            if html:
                from utils.ui_helpers import extract_content_summary, compute_lix, lix_badge
                kws, links, prods = extract_content_summary(bt)
                lix = compute_lix(html)
                lix_color, lix_msg, _ = lix_badge(lix)
                st.markdown(
                    f"**Footer text ready** — {wc} words · {len(kws)} keywords · {len(links)} links · {len(prods)} products · "
                    f"<span style='color:{lix_color};'>LIX {lix}</span>",
                    unsafe_allow_html=True,
                )
                with st.expander("View preview", expanded=False):
                    st.markdown(html, unsafe_allow_html=True)
                with st.expander("View HTML source", expanded=False):
                    st.code(html, language="html")
                st.download_button(
                    "Download HTML",
                    data=html.encode("utf-8"),
                    file_name=f"{short_url.replace('/', '_')}.html",
                    mime="text/html",
                    key=f"dl_{url_hash}",
                )
                # Push to Magento
                from utils.footer_push_ui import render_footer_push_block
                render_footer_push_block(url, html, key_prefix=f"ac_push_{url_hash}")


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


def _generate_page_text(url, audit_data):
    """Generate footer/bottom text using the shared generator (same as Quick Wins)."""
    if not has_anthropic_key():
        st.error("Anthropic API key missing")
        return
    try:
        from utils.ai_generator import generate_page_content

        with st.spinner("AI generating footer text with links + products + images..."):
            result = generate_page_content(url)
        st.session_state[f"_bottom_text_{stable_hash(url)}"] = result
        from utils.persistence import save_ai_cache
        save_ai_cache()
        st.success("Footer text generated")
    except Exception as e:
        st.error(f"Error: {e}")


def _generate_meta(url, audit_data):
    """Generate meta title + description using the shared generator (same as Quick Wins)."""
    if not has_anthropic_key():
        st.error("Anthropic API key missing")
        return
    try:
        from utils.ai_generator import get_client, generate_meta_suggestions
        from utils.page_profile import build_page_profile

        client = get_client(get_anthropic_key())
        profile = build_page_profile(url)
        target_kws = [q["query"] for q in profile.get("gsc_queries", [])[:5]]
        site_context = st.session_state.get("site_context", "")
        language = st.session_state.get("content_language", "Swedish")

        with st.spinner("AI generating meta title + description..."):
            result = generate_meta_suggestions(client, audit_data, target_kws, site_context, language)
        st.session_state[f"_meta_suggestions_{stable_hash(url)}"] = result
        from utils.persistence import save_ai_cache
        save_ai_cache()
        st.success("Meta generated")
    except Exception as e:
        st.error(f"Error: {e}")


def _generate_intro(url, audit_data):
    """Generate intro text (above product grid) using the shared generator (same as Quick Wins)."""
    if not has_anthropic_key():
        st.error("Anthropic API key missing")
        return
    try:
        from utils.ai_generator import get_client, generate_intro_rewrite

        client = get_client(get_anthropic_key())
        site_context = st.session_state.get("site_context", "")
        language = st.session_state.get("content_language", "Swedish")

        # Pull missing keywords from content audit if available (same pattern as Quick Wins)
        missing_kws = []
        content_audit = audit_data.get("content_audit") or {}
        kw_coverage = content_audit.get("keyword_coverage") or {}
        missing_kws = (kw_coverage.get("missing", []) or [])[:8]

        with st.spinner("AI generating intro text..."):
            result = generate_intro_rewrite(
                client,
                missing_keywords=missing_kws,
                existing_intro=audit_data.get("intro_text", "") or "",
                page_type=audit_data.get("page_type", "category"),
                url=url,
                site_context=site_context,
                language=language,
            )
        st.session_state[f"_intro_text_{stable_hash(url)}"] = result
        from utils.persistence import save_ai_cache
        save_ai_cache()
        st.success("Intro generated")
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
