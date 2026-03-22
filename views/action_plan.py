"""
Action Plan — AI-Powered Implementation Guide
Each page gets a complete, AI-verified implementation plan.
No rule-based guessing — Claude evaluates all data and creates precise steps.
"""

import streamlit as st
import json
import pandas as pd
from config import get_anthropic_key, has_anthropic_key
from utils.ui_helpers import shorten_url, stable_hash
from utils.ai_generator import _clean_body_text


def _get_ai_quality_badge(url):
    """Get cached AI quality score if available."""
    qkey = f"_quality_{stable_hash(url)}"
    q = st.session_state.get(qkey)
    if not q:
        return "<span style='color:#6b6b8a;'>AI text: —</span>"
    verdict = q.get("verdict", "?")
    score = q.get("score", 0)
    v_color = {"REWRITE": "#ff4455", "IMPROVE": "#ffaa33", "KEEP": "#33dd88"}.get(verdict, "#6b6b8a")
    return f"<span style='color:{v_color}; font-weight:600;'>AI text: {score}/10 ({verdict})</span>"


def _sort_pages_by_impact(audit_results):
    """Sort audited pages by potential impact (lost clicks)."""
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
            "referring_domains": r.get("referring_domains", 0),
            "backlinks": r.get("backlinks", 0),
            "authority_score": r.get("authority_score", 0),
        })
    pages.sort(key=lambda p: -p["lost_clicks"])
    return pages


def render():
    st.markdown("## Implementation Guide")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1.5rem;'>"
        "AI-verified step-by-step plan for every page. Sorted by impact — work from the top. "
        "Click a page to generate its plan.</p>",
        unsafe_allow_html=True,
    )

    has_audit = "audit_results" in st.session_state and st.session_state["audit_results"]
    has_gaps = "ctr_gaps" in st.session_state

    if not has_audit:
        st.warning("Run **6. Page Auditor** first (bulk audit recommended)")
        if has_gaps:
            _show_ctr_only_plan()
        return

    if not has_anthropic_key():
        st.warning("Add Anthropic API key in **1. Setup** — needed for AI implementation plans")
        return

    audit_results = st.session_state["audit_results"]
    topic_clusters = st.session_state.get("topic_clusters", {})
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")

    # Build site URL list for AI to reference real URLs
    # Build site URL list for AI — include ALL URLs that rank in GSC
    raw_urls = set(r["url"] for r in audit_results if r.get("url"))
    gsc = st.session_state.get("gsc_data")
    if gsc is not None and hasattr(gsc, "page"):
        raw_urls.update(gsc["page"].unique().tolist())
    all_site_urls = sorted(raw_urls)

    pages = _sort_pages_by_impact(audit_results)

    # ── Ensure homepage is always included and pinned to top ──────
    site_url = st.session_state.get("gsc_site", "")
    homepage_url = site_url.rstrip("/") + "/" if site_url else ""
    if homepage_url:
        homepage_in_list = any(p["url"] == homepage_url for p in pages)
        if not homepage_in_list:
            # Homepage not audited yet — add it with GSC data if available
            hp_impressions = 0
            hp_clicks = 0
            if gsc is not None and hasattr(gsc, "page"):
                hp_data = gsc[gsc["page"] == homepage_url]
                if not hp_data.empty:
                    hp_impressions = int(hp_data["impressions"].sum())
                    hp_clicks = int(hp_data["clicks"].sum())
            pages.insert(0, {
                "url": homepage_url,
                "page_type": "homepage",
                "impressions": hp_impressions,
                "lost_clicks": hp_clicks * 0.5,  # Estimate
                "meta_score": None,
                "content_score": None,
                "referring_domains": 0,
                "backlinks": 0,
                "authority_score": 0,
            })
        else:
            # Move homepage to top
            hp = next(p for p in pages if p["url"] == homepage_url)
            pages.remove(hp)
            pages.insert(0, hp)

    if not pages:
        st.info("No audited pages found")
        return

    # ── Summary ───────────────────────────────────────────────────
    total_lost = sum(p["lost_clicks"] for p in pages)
    c1, c2, c3 = st.columns(3)
    c1.metric("Pages audited", len(pages))
    c2.metric("Total lost clicks", f"{total_lost:,.0f}")
    c3.metric("Pages with plan", sum(1 for p in pages if f"_ai_plan_{stable_hash(p['url'])}" in st.session_state))

    st.markdown("---")

    # ── Generate / Clear buttons ─────────────────────────────────
    col_gen, col_clear, col_info = st.columns([1, 1, 2])
    with col_gen:
        gen_top = st.button("Generate plans for top 10 pages", type="primary")
    with col_clear:
        if st.button("Clear all cached plans"):
            keys_to_del = [k for k in st.session_state if k.startswith("_ai_plan_") or k.startswith("_kw_filter_") or k.startswith("impl_ai_")]
            for k in keys_to_del:
                del st.session_state[k]
            st.rerun()
    with col_info:
        st.markdown(
            "<span style='font-size:0.75rem; color:#6b6b8a;'>"
            "~20 seconds per page. Plans are cached — you only pay once per page.</span>",
            unsafe_allow_html=True,
        )

    if gen_top:
        from utils.ai_generator import get_client, generate_page_implementation_plan
        client = get_client(get_anthropic_key())

        with st.status(f"Generating AI plans for top 10 pages...", expanded=True) as status:
            progress = st.progress(0)
            log = st.empty()

            top_pages = pages[:10]
            for i, p in enumerate(top_pages):
                plan_key = f"_ai_plan_{stable_hash(p['url'])}"
                if plan_key in st.session_state:
                    log.write(f"[{i+1}/10] {p['url']} — already cached")
                    progress.progress((i + 1) / 10)
                    continue

                log.write(f"[{i+1}/10] {p['url']}...")
                try:
                    page_r = next((r for r in audit_results if r["url"] == p["url"]), None)
                    if not page_r:
                        from utils.page_scraper import scrape_page
                        page_r = scrape_page(p["url"])
                        page_r["url"] = p["url"]
                        if gsc is not None and hasattr(gsc, "page"):
                            pg = gsc[gsc["page"] == p["url"]]
                            if not pg.empty:
                                page_r["impressions"] = int(pg["impressions"].sum())
                                page_r["clicks"] = int(pg["clicks"].sum())
                                page_r["target_keywords"] = pg.sort_values("impressions", ascending=False)["query"].head(15).tolist()
                    result = generate_page_implementation_plan(
                        client, page_r, site_context, all_site_urls, language, topic_clusters,
                    )
                    st.session_state[plan_key] = result
                except Exception as e:
                    st.session_state[plan_key] = {"error": str(e), "steps": []}
                # Save after EACH page — never lose results
                from utils.persistence import save_ai_cache
                save_ai_cache()
                progress.progress((i + 1) / 10)

            status.update(label="Plans generated", state="complete", expanded=False)
        st.rerun()

    # ── Pagination ────────────────────────────────────────────────
    PAGES_PER_VIEW = 10
    total_count = len(pages)
    max_page = max(1, (total_count + PAGES_PER_VIEW - 1) // PAGES_PER_VIEW)
    current_page = st.number_input("Page", min_value=1, max_value=max_page, value=1, key="impl_page")
    start = (current_page - 1) * PAGES_PER_VIEW
    visible = pages[start:start + PAGES_PER_VIEW]

    st.markdown(f"**Showing {start+1}-{min(start+PAGES_PER_VIEW, total_count)} of {total_count} pages**")

    # ── Page cards ────────────────────────────────────────────────
    for p in visible:
        url = p["url"]
        plan_key = f"_ai_plan_{stable_hash(url)}"
        has_plan = plan_key in st.session_state
        ptype = p["page_type"].upper()
        lost = p["lost_clicks"]
        impr = p["impressions"]
        meta_s = p["meta_score"]
        content_s = p["content_score"]

        rd = p.get("referring_domains", 0)
        bl = p.get("backlinks", 0)

        border = "#ff4455" if lost > 1000 else "#ffaa33" if lost > 200 else "#2a2a40"
        plan_badge = "<span style='color:#33dd88; font-size:0.65rem;'>PLAN READY</span>" if has_plan else "<span style='color:#6b6b8a; font-size:0.65rem;'>NO PLAN YET</span>"

        # Backlink status: green/yellow/red based on impressions vs referring domains
        if rd >= 10 or (impr < 500 and rd >= 3):
            bl_color = "#33dd88"
            bl_label = "OK"
        elif rd >= 3 or (impr < 1000 and rd >= 1):
            bl_color = "#ffaa33"
            bl_label = "LOW"
        else:
            bl_color = "#ff4455"
            bl_label = "NONE" if rd == 0 else "CRITICAL"

        # Card header
        st.markdown(
            f"<div style='background:#12121f; border:1px solid {border}; border-left:4px solid {border}; "
            f"border-radius:6px; padding:1rem; margin-bottom:0.3rem;'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;'>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:{border}; "
            f"text-transform:uppercase;'>{ptype}</span>"
            f"<div>{plan_badge} · "
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#6b6b8a;'>"
            f"{impr:,} impr · {lost:,.0f} lost clicks</span></div>"
            f"</div>"
            f"<div style='font-size:1rem; color:#e8e8f0; font-weight:600;'>{url}</div>"
            f"<div style='font-size:0.72rem; color:#6b6b8a; margin-top:0.2rem;'>"
            f"Meta: {meta_s if meta_s is not None else '?'}/100 · "
            f"Algo: {content_s if content_s is not None and content_s > 0 else '?'}/100 · "
            f"{_get_ai_quality_badge(url)} · "
            f"Backlinks: <span style='color:{bl_color}; font-weight:600;'>{rd} domains ({bl_label})</span>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        url_hash = stable_hash(url)

        with st.expander(f"Implementation plan for {shorten_url(url)}", expanded=False):
            # Generate plan button (per page)
            if not has_plan:
                if st.button(f"Generate AI plan", key=f"btn_gen_plan_{url_hash}", type="primary"):
                    with st.spinner(f"AI analyzing {url}..."):
                        try:
                            from utils.ai_generator import get_client, generate_page_implementation_plan
                            client = get_client(get_anthropic_key())
                            page_r = next((r for r in audit_results if r["url"] == url), None)
                            if not page_r:
                                # Page not in audit_results — scrape live
                                from utils.page_scraper import scrape_page
                                page_r = scrape_page(url)
                                page_r["url"] = url
                                # Add GSC data
                                if gsc is not None and hasattr(gsc, "page"):
                                    pg = gsc[gsc["page"] == url]
                                    if not pg.empty:
                                        page_r["impressions"] = int(pg["impressions"].sum())
                                        page_r["clicks"] = int(pg["clicks"].sum())
                                        page_r["target_keywords"] = pg.sort_values("impressions", ascending=False)["query"].head(15).tolist()
                            result = generate_page_implementation_plan(
                                client, page_r, site_context, all_site_urls, language, topic_clusters,
                            )
                            st.session_state[plan_key] = result
                            from utils.persistence import save_ai_cache
                            save_ai_cache()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
            else:
                plan = st.session_state[plan_key]

                if plan.get("error"):
                    st.error(f"Plan generation failed: {plan['error']}")
                    if st.button("Retry", key=f"btn_retry_{url_hash}"):
                        del st.session_state[plan_key]
                        st.rerun()
                    continue

                # Overall assessment
                assessment = plan.get("overall_assessment", "")
                primary_kw = plan.get("primary_keyword", "")
                if assessment:
                    st.markdown(
                        f"<div style='background:#0d0d15; border-left:3px solid #5533ff; padding:0.8rem; "
                        f"border-radius:0 6px 6px 0; margin-bottom:1rem;'>"
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#5533ff; "
                        f"margin-bottom:0.3rem;'>AI ASSESSMENT · Primary keyword: {primary_kw}</div>"
                        f"<div style='font-size:0.85rem; color:#c8b4ff;'>{assessment}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                # ── Meta title + description (always shown prominently) ──
                meta_title = plan.get("meta_title", "")
                meta_desc_plan = plan.get("meta_description", "")
                meta_changed = plan.get("meta_changed", False)
                mt_chars = plan.get("meta_title_chars", len(meta_title))
                md_chars = plan.get("meta_description_chars", len(meta_desc_plan))

                if meta_title or meta_desc_plan:
                    # Get current values from audit
                    page_r = next((r for r in audit_results if r["url"] == url), {})
                    current_title = page_r.get("title") or ""
                    current_desc = page_r.get("meta_description") or ""

                    mt_color = "#33dd88" if 50 <= mt_chars <= 60 else "#ffaa33" if mt_chars > 0 else "#ff4455"
                    md_color = "#33dd88" if 140 <= md_chars <= 160 else "#ffaa33" if md_chars > 0 else "#ff4455"

                    change_label = "RECOMMENDED CHANGE" if meta_changed else "CURRENT (OK)"
                    change_border = "#ffaa33" if meta_changed else "#33dd88"

                    st.markdown(
                        f"<div style='background:#12121f; border:2px solid {change_border}; border-radius:8px; padding:1rem; margin-bottom:1rem;'>"
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:{change_border}; "
                        f"margin-bottom:0.5rem;'>META TITLE & DESCRIPTION · {change_label}</div>"
                        # Current
                        f"{'<div style=\"font-size:0.72rem; color:#6b6b8a; margin-bottom:0.3rem;\">Current title: ' + current_title + ' (' + str(len(current_title)) + ' chars)</div>' if meta_changed and current_title else ''}"
                        f"{'<div style=\"font-size:0.72rem; color:#6b6b8a; margin-bottom:0.5rem;\">Current desc: ' + current_desc[:80] + '... (' + str(len(current_desc)) + ' chars)</div>' if meta_changed and current_desc else ''}"
                        # Recommended
                        f"<div style='margin-bottom:0.4rem;'>"
                        f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:{mt_color};'>TITLE · {mt_chars} chars</span><br>"
                        f"<span style='font-size:0.95rem; color:#e8e8f0; font-weight:500;'>{meta_title}</span></div>"
                        f"<div>"
                        f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:{md_color};'>DESCRIPTION · {md_chars} chars</span><br>"
                        f"<span style='font-size:0.85rem; color:#b8b8d0;'>{meta_desc_plan}</span></div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                    if meta_changed:
                        st.code(f"Title: {meta_title}\nDescription: {meta_desc_plan}", language="text")

                # Steps
                steps = plan.get("steps", [])
                if not steps:
                    st.success("No issues found — this page looks good!")
                    continue

                total_time = sum(s.get("time_minutes", 0) for s in steps)
                st.markdown(f"**{len(steps)} steps · ~{total_time} minutes total**")

                for step_idx, step in enumerate(steps, 1):
                    time_str = f"{step.get('time_minutes', 0)} min"
                    step_type = step.get("type", "content")
                    type_colors = {
                        "meta": "#c8b4ff",
                        "content": "#5533ff",
                        "links": "#ffaa33",
                        "schema": "#33dd88",
                        "structure": "#6b6baa",
                    }
                    type_color = type_colors.get(step_type, "#6b6b8a")

                    st.markdown(
                        f"<div style='background:#0d0d15; border-left:3px solid {type_color}; padding:0.7rem 1rem; "
                        f"border-radius:0 6px 6px 0; margin-bottom:0.6rem;'>"
                        f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.3rem;'>"
                        f"<span style='color:{type_color}; font-weight:700; font-size:0.95rem;'>"
                        f"Step {step_idx}: {step.get('action', '')}</span>"
                        f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#6b6b8a;'>"
                        f"{step_type.upper()} · ~{time_str}</span>"
                        f"</div>"
                        f"<div style='font-size:0.82rem; color:#9b9bb8; margin-bottom:0.4rem;'>"
                        f"{step.get('detail', '')}</div>"
                        f"<div style='font-size:0.85rem; color:#c8b4ff; line-height:1.5;'>"
                        f"{step.get('instruction', '')}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                    # Only show schema button per step — content/links handled by bottom text generator
                    if step_type == "schema":
                        ai_result_key = f"impl_ai_{url_hash}_{step_idx}"
                        if st.button("Generate schema markup", key=f"btn_ai_schema_{url_hash}_{step_idx}"):
                            try:
                                from utils.ai_generator import generate_schema_markup
                                page_r = next((r for r in audit_results if r["url"] == url), {})
                                result = generate_schema_markup(
                                    page_type=page_r.get("page_type", "unknown"),
                                    url=url,
                                    title=page_r.get("title", ""),
                                    description=page_r.get("meta_description", ""),
                                    h1=page_r.get("h1", ""),
                                    site_name=site_context,
                                    site_url=st.session_state.get("gsc_site", ""),
                                )
                                st.session_state[ai_result_key] = ("schema", result)
                            except Exception as e:
                                st.error(f"Error: {e}")

                        if ai_result_key in st.session_state:
                            _, res = st.session_state[ai_result_key]
                            if isinstance(res, dict):
                                st.markdown(
                                    f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#33dd88;'>"
                                    f"PASTE THIS IN &lt;head&gt; — SCHEMA ({', '.join(res.get('types', []))})</div>",
                                    unsafe_allow_html=True,
                                )
                                st.code(res.get("json_ld", ""), language="html")

                # New content suggestions
                new_content = plan.get("new_content_suggestions", [])
                if new_content:
                    st.markdown("#### New Content to Create")
                    for nc_idx, nc in enumerate(new_content):
                        nc_type = nc.get("type", "blog").upper()
                        nc_title = nc.get("suggested_title", "")
                        nc_kws = nc.get("target_keywords", [])
                        nc_kws_str = ", ".join(nc_kws)
                        nc_why = nc.get("why", "")
                        nc_link = nc.get("link_from", "")
                        st.markdown(
                            f"<div style='background:#0d0d15; border-left:3px solid #c8b4ff; padding:0.7rem 1rem; "
                            f"border-radius:0 6px 6px 0; margin-bottom:0.5rem;'>"
                            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#c8b4ff;'>{nc_type}</span>"
                            f"<div style='font-size:0.95rem; color:#e8e8f0; font-weight:600; margin:0.3rem 0;'>{nc_title}</div>"
                            f"<div style='font-size:0.8rem; color:#9b9bb8;'>Keywords: {nc_kws_str}</div>"
                            f"<div style='font-size:0.8rem; color:#9b9bb8;'>Why: {nc_why}</div>"
                            f"{'<div style=\"font-size:0.8rem; color:#5533ff;\">Link from: ' + nc_link + '</div>' if nc_link else ''}"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                        # Generate full article button
                        article_key = f"_gen_article_{url_hash}_{nc_idx}"
                        if st.button(f"Generate full article with products", key=f"btn_gen_article_{url_hash}_{nc_idx}", type="primary"):
                            with st.spinner("Scraping products + generating article... (~60 sec)"):
                                try:
                                    from utils.product_scraper import scrape_products_from_page
                                    from utils.ai_generator import get_client, generate_full_article_html

                                    client = get_client(get_anthropic_key())

                                    # Scrape products from the linked category page
                                    products = []
                                    if nc_link:
                                        products = scrape_products_from_page(nc_link, max_products=8)

                                    # Get tone of voice sample from existing page
                                    tone_sample = ""
                                    if nc_link:
                                        page_r = next((r for r in audit_results if r["url"] == nc_link), {})
                                        tone_sample = (page_r.get("intro_text") or page_r.get("bottom_text") or "")[:500]

                                    # Build cluster context for the article
                                    from utils.ai_generator import _format_cluster_context
                                    page_r_for_ctx = next((r for r in audit_results if r["url"] == nc_link), {})
                                    cluster_ctx = _format_cluster_context(page_r_for_ctx, topic_clusters) if nc_link else ""

                                    result = generate_full_article_html(
                                        client,
                                        title=nc_title,
                                        keywords=nc_kws,
                                        content_type=nc.get("type", "blog"),
                                        products=products,
                                        link_from_url=nc_link,
                                        tone_sample=tone_sample,
                                        site_context=site_context,
                                        language=language,
                                        all_site_urls=all_site_urls,
                                        cluster_context=cluster_ctx,
                                    )
                                    st.session_state[article_key] = result
                                except Exception as e:
                                    st.error(f"Error: {e}")

                        if article_key in st.session_state:
                            art = st.session_state[article_key]
                            wc = art.get("word_count", 0)
                            prods = art.get("products_featured", [])

                            st.markdown(
                                f"<div style='background:#0d1a0d; border-left:3px solid #33dd88; padding:0.6rem; "
                                f"border-radius:0 6px 6px 0; margin-bottom:0.3rem;'>"
                                f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#33dd88;'>"
                                f"ARTICLE READY · {wc} words · {len(prods)} products</span></div>",
                                unsafe_allow_html=True,
                            )

                            # Meta tags
                            st.code(
                                f"Meta title: {art.get('meta_title', '')}\n"
                                f"Meta description: {art.get('meta_description', '')}",
                                language="text",
                            )

                            # Preview
                            with st.expander("Preview article", expanded=True):
                                st.markdown(art.get("html", ""), unsafe_allow_html=True)

                            # Copy HTML
                            with st.expander("Copy HTML source"):
                                st.code(art.get("html", ""), language="html")

                            # Download
                            st.download_button(
                                "Download HTML",
                                art.get("html", "").encode("utf-8"),
                                f"article_{nc_idx}.html",
                                "text/html",
                                key=f"dl_article_{url_hash}_{nc_idx}",
                            )

                # Text rewrite suggestions
                rewrites = plan.get("text_rewrites", [])
                if rewrites:
                    st.markdown("#### Sections to Rewrite")
                    page_r = next((r for r in audit_results if r["url"] == url), {})

                    for rw_idx, rw in enumerate(rewrites):
                        section_name = rw.get("section", "")
                        problem = rw.get("current_problem", "")
                        angle = rw.get("suggested_angle", "")

                        st.markdown(
                            f"<div style='background:#1a0d0d; border-left:3px solid #ff4455; padding:0.7rem 1rem; "
                            f"border-radius:0 6px 6px 0; margin-bottom:0.5rem;'>"
                            f"<div style='font-size:0.9rem; color:#ff4455; font-weight:600; margin-bottom:0.3rem;'>{section_name}</div>"
                            f"<div style='font-size:0.8rem; color:#9b9bb8; margin-bottom:0.3rem;'>Problem: {problem}</div>"
                            f"<div style='font-size:0.8rem; color:#c8b4ff;'>New angle: {angle}</div>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                        # Show current text snippet
                        current_text = _clean_body_text(page_r, 1000) if page_r else ""
                        if current_text:
                            show_current = st.toggle("Show current text", key=f"toggle_current_{url_hash}_{rw_idx}")
                            if show_current:
                                st.markdown(
                                    f"<div style='background:#1a0d0d; border:1px solid #2a2a40; border-radius:6px; padding:0.6rem; margin:0.3rem 0;'>"
                                    f"<div style='font-size:0.6rem; color:#ff4455; font-family:\"IBM Plex Mono\",monospace;'>CURRENT TEXT</div>"
                                    f"<div style='font-size:0.8rem; color:#9b9bb8;'>{current_text[:500]}{'...' if len(current_text) > 500 else ''}</div>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )

                        # AI rewrite button
                        rewrite_key = f"_rewrite_{url_hash}_{rw_idx}"
                        if st.button(f"AI: Rewrite this section", key=f"btn_rewrite_{url_hash}_{rw_idx}", type="primary"):
                            with st.spinner("AI rewriting section..."):
                                try:
                                    from utils.ai_generator import get_client, generate_keyword_text
                                    client = get_client(get_anthropic_key())

                                    # Build specific prompt context from the rewrite suggestion
                                    rewrite_context = (
                                        f"SECTION TO REWRITE: {section_name}\n"
                                        f"PROBLEM: {problem}\n"
                                        f"NEW ANGLE: {angle}\n\n"
                                        f"CURRENT TEXT:\n{current_text[:800]}"
                                    )

                                    result = generate_keyword_text(
                                        client,
                                        page_r.get("target_keywords", [])[:10],
                                        rewrite_context,
                                        page_r.get("page_type", "unknown"),
                                        site_context, language,
                                    )
                                    st.session_state[rewrite_key] = result
                                except Exception as e:
                                    st.error(f"Error: {e}")

                        if rewrite_key in st.session_state:
                            res = st.session_state[rewrite_key]
                            st.markdown(
                                "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#33dd88; "
                                "margin:0.3rem 0;'>COPY THIS — REWRITTEN SECTION</div>",
                                unsafe_allow_html=True,
                            )
                            st.markdown(
                                f"<div style='background:#0d1a0d; border-left:3px solid #33dd88; padding:0.8rem; "
                                f"border-radius:0 6px 6px 0;'>"
                                f"<div style='color:#e8e8f0; line-height:1.6;'>{res.get('optimized_text', '')}</div>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                            kws = res.get("keywords_integrated", [])
                            if kws:
                                st.markdown(f"<span style='font-size:0.7rem; color:#33dd88;'>Keywords: {', '.join(kws)}</span>", unsafe_allow_html=True)
                            st.code(res.get("optimized_text", ""), language="text")

                # ── MAIN ACTION: Generate complete page text ─────────
                page_r = next((r for r in audit_results if r["url"] == url), {})
                # Show text generation for ALL page types (not just category)
                if True:
                    st.markdown("---")
                    st.markdown(
                        "<div style='background:#0d0d15; border:2px solid #5533ff; border-radius:8px; padding:1rem; margin:0.5rem 0;'>"
                        "<div style='font-family:\"Syne\",sans-serif; font-size:1.1rem; font-weight:700; color:#c8b4ff; margin-bottom:0.5rem;'>"
                        "Generate Complete Page Text</div>"
                        "<div style='font-size:0.85rem; color:#9b9bb8;'>"
                        "This generates the FULL page text with all fixes from the steps above included: "
                        "keywords, internal links, product recommendations, buying guide, FAQ — everything in one go. "
                        "Ready to paste into CMS.</div>"
                        "</div>",
                        unsafe_allow_html=True,
                    )

                    # Show current text
                    current_body = _clean_body_text(page_r, 2000)
                    if current_body:
                        show_current = st.toggle("Show current page text", key=f"toggle_body_{url_hash}")
                        if show_current:
                            st.markdown(
                                f"<div style='background:#1a0d0d; border:1px solid #2a2a40; border-radius:6px; padding:0.8rem; margin:0.3rem 0;'>"
                                f"<div style='font-size:0.6rem; color:#ff4455; font-family:\"IBM Plex Mono\",monospace; margin-bottom:0.3rem;'>"
                                f"CURRENT TEXT ({len(current_body.split())} words)</div>"
                                f"<div style='font-size:0.8rem; color:#9b9bb8; line-height:1.5;'>{current_body}</div>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                    # ── Intro text (above product grid) ──────────────
                    intro_key = f"_intro_text_{url_hash}"
                    current_intro = _clean_body_text(page_r.get("intro_text") or "", 500)

                    # Check if AI plan mentions intro issues
                    intro_needs_fix = False
                    intro_reason = ""
                    for s in steps:
                        s_text = (s.get("action", "") + " " + s.get("detail", "") + " " + s.get("instruction", "")).lower()
                        if "intro" in s_text or "introduction" in s_text or "first paragraph" in s_text:
                            intro_needs_fix = True
                            intro_reason = s.get("detail", "")
                            break
                    # Also check text_rewrites
                    for rw in plan.get("text_rewrites", []):
                        if "intro" in rw.get("section", "").lower():
                            intro_needs_fix = True
                            intro_reason = rw.get("current_problem", "")
                            break
                    # Also flag if intro is too short or empty
                    if current_intro and len(current_intro.split()) < 30:
                        intro_needs_fix = True
                        intro_reason = f"Intro is only {len(current_intro.split())} words — too short"
                    elif not current_intro:
                        intro_needs_fix = True
                        intro_reason = "No intro text found above product grid"

                    if intro_needs_fix:
                        st.markdown(
                            f"<div style='background:#1a0d0d; border-left:3px solid #ffaa33; padding:0.6rem; border-radius:0 6px 6px 0; margin:0.5rem 0;'>"
                            f"<div style='font-size:0.85rem; color:#ffaa33; font-weight:600;'>Intro needs improvement</div>"
                            f"<div style='font-size:0.8rem; color:#9b9bb8;'>{intro_reason}</div>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                        if current_intro:
                            st.markdown(
                                f"<div style='background:#1a0d0d; border:1px solid #2a2a40; border-radius:6px; padding:0.5rem; margin:0.3rem 0;'>"
                                f"<div style='font-size:0.6rem; color:#ff4455; font-family:\"IBM Plex Mono\",monospace;'>CURRENT INTRO ({len(current_intro.split())} words)</div>"
                                f"<div style='font-size:0.8rem; color:#9b9bb8;'>{current_intro}</div>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                        if st.button("Generate new intro text", key=f"btn_intro_{url_hash}"):
                            with st.spinner("Generating intro..."):
                                try:
                                    from utils.ai_generator import get_client, generate_intro_rewrite
                                    client = get_client(get_anthropic_key())
                                    result = generate_intro_rewrite(
                                        client,
                                        page_r.get("target_keywords", []),
                                        current_intro or _clean_body_text(page_r, 500),
                                        page_r.get("page_type", "category"),
                                        url, site_context, language,
                                    )
                                    st.session_state[intro_key] = result
                                except Exception as e:
                                    st.error(f"Error: {e}")

                        if intro_key in st.session_state:
                            intro_res = st.session_state[intro_key]
                            st.markdown(
                                f"<div style='background:#0d1a0d; border:2px solid #33dd88; border-radius:6px; padding:0.8rem; margin:0.5rem 0;'>"
                                f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#33dd88; margin-bottom:0.3rem;'>"
                                f"NEW INTRO — PASTE ABOVE PRODUCT GRID</div>"
                                f"<div style='font-size:0.9rem; color:#e8e8f0; line-height:1.6;'>{intro_res.get('optimized_text', '')}</div>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                            kws = intro_res.get("keywords_integrated", [])
                            if kws:
                                st.markdown(f"<span style='font-size:0.7rem; color:#33dd88;'>Keywords: {', '.join(kws)}</span>", unsafe_allow_html=True)
                            st.code(intro_res.get("optimized_text", ""), language="text")
                    else:
                        # Intro is OK
                        if current_intro:
                            st.markdown(
                                f"<div style='border-left:3px solid #33dd88; padding:0.5rem 0.8rem; margin:0.3rem 0;'>"
                                f"<span style='color:#33dd88; font-size:0.8rem; font-weight:600;'>Intro text OK</span> "
                                f"<span style='color:#6b6b8a; font-size:0.75rem;'>({len(current_intro.split())} words)</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                    st.markdown("---")

                    # ── Bottom text (below product grid) ──────────────
                    st.markdown("**Bottom text** (below product grid, 800-1500 words)")
                    bottom_key = f"_bottom_text_{url_hash}"
                    if st.button("Generate bottom text with products & links", key=f"btn_bottom_{url_hash}", type="primary"):
                        with st.spinner("Scraping products + generating bottom text... (~60 sec)"):
                            try:
                                from utils.product_scraper import scrape_products_from_page
                                from utils.ai_generator import get_client, generate_category_bottom_text
                                from urllib.parse import urlparse as _up_bt

                                client = get_client(get_anthropic_key())

                                # Scrape products from this category
                                products = scrape_products_from_page(url, max_products=6)

                                # Find subcategory URLs (children in URL hierarchy)
                                page_path = _up_bt(url).path.lower().rstrip("/")
                                subcategory_urls = [
                                    u for u in all_site_urls
                                    if _up_bt(u).path.lower().rstrip("/").startswith(page_path + "/")
                                    and _up_bt(u).path.lower().rstrip("/").count("/") == page_path.count("/") + 1
                                ]

                                # Find sibling URLs (same parent)
                                parent_path = "/".join(page_path.split("/")[:-1])
                                sibling_urls = [
                                    u for u in all_site_urls
                                    if u != url
                                    and _up_bt(u).path.lower().rstrip("/").startswith(parent_path + "/")
                                    and _up_bt(u).path.lower().rstrip("/").count("/") == page_path.count("/")
                                ] if parent_path else []

                                result = generate_category_bottom_text(
                                    client, url,
                                    page_r.get("title", ""),
                                    page_r.get("h1", ""),
                                    page_r.get("bottom_text", "") or (page_r.get("body_text") or "")[-2000:],
                                    page_r.get("target_keywords", []),
                                    subcategory_urls=subcategory_urls[:20],
                                    sibling_urls=sibling_urls[:10],
                                    products=products,
                                    all_site_urls=all_site_urls,
                                    site_context=site_context,
                                    language=language,
                                )
                                st.session_state[bottom_key] = result
                            except Exception as e:
                                st.error(f"Error: {e}")

                    if bottom_key in st.session_state:
                        bt = st.session_state[bottom_key]
                        wc = bt.get("word_count", 0)
                        kws = bt.get("keywords_integrated", [])
                        links = bt.get("internal_links_added", [])
                        prods = bt.get("products_featured", [])

                        # Summary of what changed
                        st.markdown(
                            f"<div style='background:#0d1a0d; border:2px solid #33dd88; border-radius:8px; padding:1rem; margin:0.5rem 0;'>"
                            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#33dd88; margin-bottom:0.5rem;'>"
                            f"NEW TEXT READY — COPY THIS TO REPLACE CURRENT TEXT</div>"
                            f"<div style='font-size:0.85rem; color:#e8e8f0; margin-bottom:0.5rem;'>"
                            f"<strong>{wc} words</strong> · "
                            f"<strong>{len(kws)} keywords</strong> integrated · "
                            f"<strong>{len(links)} internal links</strong> · "
                            f"<strong>{len(prods)} products</strong> featured</div>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                        # What changed and why
                        st.markdown("**What's different from current text:**")
                        changes = []
                        if kws:
                            changes.append(f"Keywords added: {', '.join(kws[:10])}")
                        if links:
                            site_origin = st.session_state.get("gsc_site", "").rstrip("/")
                            changes.append(f"Internal links to: {', '.join(l.replace(site_origin, '') for l in links[:8])}")
                        if prods:
                            changes.append(f"Products featured: {', '.join(prods[:5])}")
                        # Get step summaries as change reasons
                        for s in steps:
                            if s.get("type") in ("content", "links"):
                                changes.append(f"Fix: {s.get('action', '')}")
                        for c in changes[:8]:
                            st.markdown(f"<div style='font-size:0.8rem; color:#c8b4ff; padding:1px 0;'>+ {c}</div>", unsafe_allow_html=True)

                        # Preview
                        st.markdown("---")
                        st.markdown("**New text preview:**")
                        st.markdown(bt.get("html", ""), unsafe_allow_html=True)

                        # Copy HTML
                        st.markdown("---")
                        st.markdown("**Copy HTML source:**")
                        st.code(bt.get("html", ""), language="html")

                        st.download_button(
                            "Download HTML",
                            bt.get("html", "").encode("utf-8"),
                            f"bottom_text_{url_hash}.html",
                            "text/html",
                            key=f"dl_bottom_{url_hash}",
                        )

                        if kws:
                            with st.expander(f"Keywords integrated ({len(kws)})"):
                                st.markdown(", ".join(kws))
                        if links:
                            with st.expander(f"Internal links ({len(links)})"):
                                for lk in links:
                                    st.markdown(f"- `{lk}`")

                # Regenerate plan button
                if st.button("Regenerate plan", key=f"btn_regen_{url_hash}"):
                    del st.session_state[plan_key]
                    st.rerun()

    # ── Download ──────────────────────────────────────────────────
    st.markdown("---")
    all_plans = {}
    for p in pages:
        pk = f"_ai_plan_{stable_hash(p['url'])}"
        if pk in st.session_state:
            plan = st.session_state[pk]
            if not plan.get("error"):
                all_plans[p["url"]] = plan

    if all_plans:
        st.download_button(
            f"Download all plans ({len(all_plans)} pages)",
            json.dumps(all_plans, ensure_ascii=False, indent=2).encode("utf-8"),
            "implementation_plans.json",
            "application/json",
        )

    st.session_state["action_plan"] = True


def _show_ctr_only_plan():
    """Simple action plan from CTR gaps only"""
    gaps = st.session_state["ctr_gaps"]

    page_summary = (
        gaps.groupby("page")
        .agg(
            lost_clicks=("lost_clicks_estimate", "sum"),
            avg_pos=("position", "mean"),
            avg_gap=("ctr_gap_pct", "mean"),
            top_kws=("query", lambda x: ", ".join(x.head(3)))
        )
        .reset_index()
        .sort_values("lost_clicks", ascending=False)
        .head(20)
    )

    st.markdown("### Top Pages with CTR Gap (run Page Auditor for full implementation plan)")

    for _, row in page_summary.iterrows():
        url_short = shorten_url(row["page"])
        priority = "CRITICAL" if row["lost_clicks"] > 50 else "MEDIUM" if row["lost_clicks"] > 20 else "LOW"
        pri_color = {"CRITICAL": "#ff4455", "MEDIUM": "#ffaa33", "LOW": "#33dd88"}[priority]

        st.markdown(f"""
        <div style="background:#12121f; border-left:3px solid {pri_color}; border-radius:6px; padding:0.8rem; margin-bottom:0.5rem;">
            <div style="display:flex; justify-content:space-between;">
                <div>
                    <span style="font-size:0.85rem; color:#e8e8f0; font-weight:500;">{url_short}</span><br>
                    <span style="font-size:0.75rem; color:#6b6b8a; font-family:'IBM Plex Mono',monospace;">Keywords: {row['top_kws']}</span>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:0.7rem; color:{pri_color}; font-weight:600;">{priority}</div>
                    <div style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#ff4455;">
                        -{row['lost_clicks']:.0f} clicks/mo
                    </div>
                    <div style="font-size:0.7rem; color:#6b6b8a;">Pos. {row['avg_pos']:.1f}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
