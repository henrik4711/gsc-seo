"""
Quick Wins — One page at a time, fully generated, approve/reject workflow.
For users who want fast wins without navigating multiple menus.
"""

import streamlit as st
from config import get_anthropic_key, has_anthropic_key
from utils.ui_helpers import stable_hash, normalize_url, shorten_url


def _get_top_pages(audit_results, top_n=20):
    """Get top pages by lost clicks, excluding done."""
    pages = []
    for r in audit_results:
        if not r.get("url"):
            continue
        url_hash = stable_hash(r["url"])
        if st.session_state.get(f"_qw_done_{url_hash}", False):
            continue
        pages.append({
            "url": r["url"],
            "page_type": r.get("page_type", "unknown"),
            "impressions": r.get("impressions", 0),
            "lost_clicks": r.get("lost_clicks_estimate", 0),
            "meta_score": r.get("meta_score") or 0,
            "content_score": r.get("content_score") or 0,
            "title": r.get("title", ""),
            "meta_description": r.get("meta_description", ""),
            "h1": r.get("h1", ""),
            "word_count": r.get("word_count", 0),
            "intro_text": r.get("intro_text", ""),
            "bottom_text": r.get("bottom_text", ""),
            "audit": r,
        })
    pages.sort(key=lambda p: -p["lost_clicks"])
    return pages[:top_n]


def _detect_issues(page):
    """Auto-detect what's wrong with this page."""
    issues = []
    audit = page["audit"]

    # Meta title
    title = page["title"] or ""
    if not title:
        issues.append("Missing meta title")
    elif len(title) < 30:
        issues.append(f"Meta title too short ({len(title)} chars, recommend 50-60)")
    elif len(title) > 65:
        issues.append(f"Meta title too long ({len(title)} chars, max 65)")

    # Meta description
    desc = page["meta_description"] or ""
    if not desc:
        issues.append("Missing meta description")
    elif len(desc) < 120:
        issues.append(f"Meta description short ({len(desc)} chars, recommend 140-160)")
    elif len(desc) > 165:
        issues.append(f"Meta description too long ({len(desc)} chars, max 165)")

    # Content audit data
    content_audit = audit.get("content_audit") or {}
    kw_coverage = content_audit.get("keyword_coverage") or {}
    missing_kws = kw_coverage.get("missing", [])
    if missing_kws:
        issues.append(f"Missing {len(missing_kws)} keywords: {', '.join(missing_kws[:5])}")

    # Internal links
    internal_links = audit.get("internal_links", 0)
    link_count = internal_links if isinstance(internal_links, int) else len(internal_links)
    if link_count < 5 and page["page_type"] == "category":
        issues.append(f"Few internal links ({link_count}, recommend 8-12)")

    # FAQ section
    if not audit.get("has_faq") and page["page_type"] == "category":
        issues.append("No FAQ section")

    # Buying guide
    if not audit.get("has_buying_guide") and page["page_type"] == "category":
        issues.append("No buying guide section")

    # Bottom text
    bottom_words = audit.get("bottom_word_count", 0)
    if bottom_words < 50 and page["page_type"] == "category":
        issues.append(f"Bottom text missing or too thin ({bottom_words} words)")

    # Linking issues
    linking = content_audit.get("linking") or {}
    missing_crosslinks = linking.get("missing_crosslinks") or []
    if missing_crosslinks:
        issues.append(f"{len(missing_crosslinks)} missing cluster cross-links")

    # Trust signals
    trust = content_audit.get("trust") or {}
    if trust:
        trust_signals = trust.get("trust_signals", {})
        if isinstance(trust_signals, dict):
            missing_trust = [k for k, v in trust_signals.items() if not v]
            if len(missing_trust) >= 3:
                issues.append(f"Missing trust signals: {', '.join(missing_trust[:3])}")

    return issues


def _generate_all_fixes(page):
    """Generate all AI fixes for a page in parallel-ish (sequential but quick)."""
    url = page["url"]
    url_hash = stable_hash(url)
    audit = page["audit"]

    if not has_anthropic_key():
        st.error("Anthropic API key missing")
        return

    from utils.ai_generator import (
        get_client,
        generate_page_implementation_plan,
        generate_category_bottom_text,
        generate_intro_rewrite,
    )
    from urllib.parse import urlparse

    client = get_client(get_anthropic_key())
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")
    topic_clusters = st.session_state.get("topic_clusters", {})

    # Build site URLs
    audit_results = st.session_state.get("audit_results", [])
    raw_urls = set(r["url"] for r in audit_results if r.get("url"))
    gsc = st.session_state.get("gsc_data")
    if gsc is not None and hasattr(gsc, "page"):
        raw_urls.update(gsc["page"].unique().tolist())
    all_site_urls = sorted(raw_urls)

    # ── Generate implementation plan (includes meta, steps, links, articles)
    plan_key = f"_ai_plan_{url_hash}"
    if plan_key not in st.session_state:
        with st.spinner("Generating implementation plan..."):
            try:
                result = generate_page_implementation_plan(
                    client, audit, site_context, all_site_urls, language, topic_clusters,
                )
                st.session_state[plan_key] = result
            except Exception as e:
                st.error(f"Plan generation failed: {e}")
                st.session_state[plan_key] = {"error": str(e), "steps": []}

    # ── Generate bottom text (only for category pages)
    text_key = f"_bottom_text_{url_hash}"
    if page["page_type"] == "category" and text_key not in st.session_state:
        with st.spinner("Generating page text with FAQ + E-E-A-T..."):
            try:
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

                # Build product list from audit data (deep_scrape_category stores rich data)
                products = []
                rich_products = audit.get("products", []) or []
                for p in rich_products[:8]:
                    products.append({
                        "name": p.get("name", ""),
                        "product_url": p.get("url", ""),
                        "image_url": p.get("image", ""),
                        "price": p.get("price", ""),
                        "description": "",
                    })

                result = generate_category_bottom_text(
                    client, url,
                    audit.get("title", ""),
                    audit.get("h1", ""),
                    audit.get("bottom_text", "") or (audit.get("body_text") or "")[-2000:],
                    audit.get("target_keywords", []),
                    subcategory_urls=subcategory_urls,
                    sibling_urls=sibling_urls,
                    products=products if products else None,
                    all_site_urls=all_site_urls,
                    site_context=site_context,
                    language=language,
                    current_intro_text=audit.get("intro_text", ""),
                    impressions=audit.get("impressions", 0),
                )
                st.session_state[text_key] = result
            except Exception as e:
                st.error(f"Text generation failed: {e}")
                st.session_state[text_key] = {"error": str(e)}

    # ── Generate intro text rewrite (only for category pages with thin/missing intro)
    intro_key = f"_intro_text_{url_hash}"
    intro_words = audit.get("intro_word_count", 0)
    if (page["page_type"] == "category"
            and intro_key not in st.session_state
            and (intro_words < 50 or not audit.get("intro_text"))):
        with st.spinner("Generating intro text..."):
            try:
                missing_kws = []
                content_audit = audit.get("content_audit") or {}
                kw_coverage = content_audit.get("keyword_coverage") or {}
                missing_kws = (kw_coverage.get("missing", []) or [])[:8]

                result = generate_intro_rewrite(
                    client,
                    missing_keywords=missing_kws,
                    existing_intro=audit.get("intro_text", "") or "",
                    page_type=page["page_type"],
                    url=url,
                    site_context=site_context,
                    language=language,
                )
                st.session_state[intro_key] = result
            except Exception as e:
                st.error(f"Intro generation failed: {e}")
                st.session_state[intro_key] = {"error": str(e)}

    from utils.persistence import save_ai_cache
    save_ai_cache()


def _approval_button(label, key):
    """Approve/Reject toggle stored in session state."""
    state_key = f"_qw_approved_{key}"
    current = st.session_state.get(state_key, None)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Approve", key=f"{key}_app", type="primary" if current == "approved" else "secondary"):
            st.session_state[state_key] = "approved"
            st.rerun()
    with col2:
        if st.button("Edit later", key=f"{key}_edit", type="primary" if current == "edit" else "secondary"):
            st.session_state[state_key] = "edit"
            st.rerun()
    with col3:
        if st.button("Reject", key=f"{key}_rej", type="primary" if current == "rejected" else "secondary"):
            st.session_state[state_key] = "rejected"
            st.rerun()

    if current:
        color = {"approved": "#33dd88", "edit": "#ffaa33", "rejected": "#ff4455"}.get(current)
        st.markdown(f"<div style='font-size:0.75rem; color:{color}; font-weight:600;'>Status: {current.upper()}</div>", unsafe_allow_html=True)


def render():
    st.markdown("## ⚡ Quick Wins")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1rem;'>"
        "One page at a time. AI generates everything automatically. "
        "You approve, edit, or reject. Fast workflow for high-impact changes.</p>",
        unsafe_allow_html=True,
    )

    if "audit_results" not in st.session_state or not st.session_state["audit_results"]:
        st.warning("No audit data. Go to **⚡ Run Pipeline** and run all steps first.")
        return

    audit_results = st.session_state["audit_results"]
    pages = _get_top_pages(audit_results, top_n=20)

    if not pages:
        st.success("All top pages marked as done. Reset done status to start over.")
        if st.button("Reset all done status"):
            keys = [k for k in st.session_state if k.startswith("_qw_done_")]
            for k in keys:
                del st.session_state[k]
            st.rerun()
        return

    # Page index navigator
    if "_qw_page_idx" not in st.session_state:
        st.session_state["_qw_page_idx"] = 0
    idx = st.session_state["_qw_page_idx"]
    if idx >= len(pages):
        idx = 0
        st.session_state["_qw_page_idx"] = 0

    # Navigation header
    nav_col1, nav_col2, nav_col3 = st.columns([1, 6, 1])
    with nav_col1:
        if st.button("◀ Previous", disabled=idx == 0, use_container_width=True):
            st.session_state["_qw_page_idx"] = max(0, idx - 1)
            st.rerun()
    with nav_col2:
        st.markdown(
            f"<div style='text-align:center; font-size:0.85rem; color:#9b9bb8;'>"
            f"Page <strong>{idx+1}</strong> of <strong>{len(pages)}</strong> top opportunities</div>",
            unsafe_allow_html=True,
        )
    with nav_col3:
        if st.button("Next ▶", disabled=idx >= len(pages) - 1, use_container_width=True):
            st.session_state["_qw_page_idx"] = min(len(pages) - 1, idx + 1)
            st.rerun()

    st.markdown("---")

    # Current page
    page = pages[idx]
    url = page["url"]
    url_hash = stable_hash(url)

    # Header card
    border = "#ff4455" if page["lost_clicks"] > 1000 else "#ffaa33" if page["lost_clicks"] > 200 else "#5533ff"
    st.markdown(
        f"<div style='background:#0d0d15; border:2px solid {border}; border-left:6px solid {border}; "
        f"border-radius:8px; padding:1rem; margin-bottom:1rem;'>"
        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:{border}; margin-bottom:0.3rem;'>"
        f"#{idx+1} · {page['page_type'].upper()}</div>"
        f"<div style='font-size:1rem; color:#e8e8f0; font-weight:600; word-break:break-all;'>{url}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Impressions", f"{page['impressions']:,}")
    c2.metric("Lost clicks", f"{page['lost_clicks']:,}")
    c3.metric("Meta score", f"{page['meta_score']}/100")
    c4.metric("Content score", f"{page['content_score']}/100")

    # ── Issues detected ──────────────────────────────────────
    st.markdown("### What's wrong (auto-detected)")
    issues = _detect_issues(page)
    if not issues:
        st.success("No major issues detected on this page")
    else:
        for issue in issues:
            st.markdown(f"- {issue}")

    st.markdown("---")

    # ── Generate / Show fixes ────────────────────────────────
    plan_key = f"_ai_plan_{url_hash}"
    text_key = f"_bottom_text_{url_hash}"
    has_plan = plan_key in st.session_state and not st.session_state[plan_key].get("error")
    has_text = text_key in st.session_state and not st.session_state[text_key].get("error")

    if not has_plan or (page["page_type"] == "category" and not has_text):
        st.markdown("### AI fixes — not generated yet")
        st.info("Click below to generate all AI fixes for this page (~30-60 seconds)")
        if st.button("Generate all fixes", type="primary", use_container_width=True):
            _generate_all_fixes(page)
            st.rerun()
    else:
        # Regenerate button always available
        col_h1, col_h2 = st.columns([4, 1])
        with col_h1:
            st.markdown("### AI-generated fixes")
        with col_h2:
            if st.button("Regenerate", key=f"regen_{url_hash}", help="Delete cached fixes and generate fresh"):
                # Clear cached results for this page
                intro_key = f"_intro_text_{url_hash}"
                for k in [plan_key, text_key, intro_key]:
                    st.session_state.pop(k, None)
                # Also delete from disk cache
                try:
                    import os
                    for k in [plan_key, text_key, intro_key]:
                        path = os.path.join("/data/ai_cache", f"{k}.json")
                        if os.path.exists(path):
                            os.remove(path)
                except Exception:
                    pass
                _generate_all_fixes(page)
                st.rerun()

        plan = st.session_state.get(plan_key, {})

        # ── PRIMARY ACTION: Replace BOTTOM text with AI-generated ──
        if has_text:
            st.markdown("#### [PRIMARY] Replace BOTTOM TEXT (below product grid)")
            st.markdown(
                "<div style='background:#0d0d15; border:1px solid #ffaa33; border-radius:6px; padding:0.6rem; margin-bottom:0.5rem;'>"
                "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#ffaa33;'>POSITION</div>"
                "<div style='font-size:0.8rem; color:#e8e8f0;'>"
                "This is the <strong>BOTTOM TEXT</strong> shown <strong>BELOW</strong> the product grid on the category page. "
                "<br>It is NOT the intro text above the products. "
                "<br>In Magento 1.9: typically the <strong>Description</strong> field on the category."
                "</div></div>",
                unsafe_allow_html=True,
            )

            # Show current intro text length so user knows we don't touch it
            intro_words = page["audit"].get("intro_word_count", 0)
            bottom_words = page["audit"].get("bottom_word_count", 0)
            st.markdown(
                f"<div style='font-size:0.75rem; color:#6b6b8a; margin-bottom:0.5rem;'>"
                f"Current intro text: {intro_words} words (above grid — NOT touched) · "
                f"Current bottom text: {bottom_words} words (below grid — REPLACED)</div>",
                unsafe_allow_html=True,
            )

            text_data = st.session_state[text_key]
            html = text_data.get("html", "")
            wc = text_data.get("word_count", 0)
            kws = text_data.get("keywords_integrated", [])
            links = text_data.get("internal_links_added", [])
            prods = text_data.get("products_featured", [])
            st.markdown(f"**New bottom text:** {wc} words · **Keywords:** {len(kws)} · **Internal links:** {len(links)} · **Products:** {len(prods)}")
            with st.expander("View HTML preview", expanded=False):
                st.code(html[:3000] + ("..." if len(html) > 3000 else ""), language="html")
            st.download_button(
                "Download HTML",
                data=html,
                file_name=f"{shorten_url(url).replace('/', '_').strip('_')}_bottom.html",
                mime="text/html",
                key=f"dl_text_{url_hash}",
            )
            st.markdown(
                "<div style='background:#0d0d15; border-left:3px solid #5533ff; padding:0.8rem; margin:0.5rem 0;'>"
                "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#5533ff;'>HOW TO USE IN MAGENTO 1.9</div>"
                "<div style='font-size:0.85rem; color:#c8b4ff;'>"
                "1) Download HTML  2) Magento Admin → Catalog → Categories → this category  "
                "3) Paste into <strong>Description</strong> field (NOT 'Page Title' or 'Meta')  "
                "4) Make sure 'Display Mode' is set to 'Products and Static Block' or 'Static Block and Products' "
                "5) Save and clear cache</div></div>",
                unsafe_allow_html=True,
            )
            _approval_button("Bottom Text", f"{url_hash}_text")
            st.markdown("---")

        # ── Meta title + description (always show with assessment) ──
        new_title = plan.get("meta_title", "") or page["title"]
        new_desc = plan.get("meta_description", "") or page["meta_description"]
        meta_changed = plan.get("meta_changed", False)

        # Auto-detect if change needed
        title_too_long = len(page["title"] or "") > 65
        title_too_short = len(page["title"] or "") < 30
        desc_too_long = len(page["meta_description"] or "") > 165
        desc_too_short = len(page["meta_description"] or "") < 120
        needs_meta_change = meta_changed or title_too_long or title_too_short or desc_too_long or desc_too_short

        if needs_meta_change:
            st.markdown("#### [META] Update meta title + description")
            st.markdown(
                f"<div style='font-size:0.75rem; color:#ffaa33; margin-bottom:0.5rem;'>"
                f"⚠ Changes needed</div>",
                unsafe_allow_html=True,
            )

            # Title
            t_status = "⚠ TOO LONG" if title_too_long else "⚠ TOO SHORT" if title_too_short else "✓ OK"
            st.markdown(f"**Current title:** `{page['title']}` ({len(page['title'])} chars) {t_status}")
            if new_title and new_title != page['title']:
                st.markdown(f"**New title:** `{new_title}` ({len(new_title)} chars)")
            else:
                st.markdown(f"<span style='color:#ffaa33;'>AI did not generate a new title — please write one manually</span>", unsafe_allow_html=True)

            # Description
            d_status = "⚠ TOO LONG" if desc_too_long else "⚠ TOO SHORT" if desc_too_short else "✓ OK"
            st.markdown(f"**Current description:** `{(page['meta_description'] or '')[:100]}...` ({len(page['meta_description'] or '')} chars) {d_status}")
            if new_desc and new_desc != page['meta_description']:
                st.markdown(f"**New description:** `{new_desc}` ({len(new_desc)} chars)")
            else:
                st.markdown(f"<span style='color:#ffaa33;'>AI did not generate a new description — please write one manually</span>", unsafe_allow_html=True)

            if new_title and new_desc and (new_title != page['title'] or new_desc != page['meta_description']):
                st.code(f"Title: {new_title}\nDescription: {new_desc}", language="text")
            _approval_button("Meta", f"{url_hash}_meta")
            st.markdown("---")
        else:
            st.markdown("#### [META] ✓ Meta is OK")
            st.markdown(
                f"<div style='font-size:0.75rem; color:#33dd88; margin-bottom:0.5rem;'>"
                f"Title: {len(page['title'])} chars · Description: {len(page['meta_description'] or '')} chars · No changes needed</div>",
                unsafe_allow_html=True,
            )
            st.markdown("---")

        # ── Intro text (above product grid) ──
        intro_key = f"_intro_text_{url_hash}"
        intro_data = st.session_state.get(intro_key)
        intro_words_current = page["audit"].get("intro_word_count", 0)

        if intro_data and not intro_data.get("error"):
            st.markdown("#### [INTRO] New intro text (above product grid)")
            st.markdown(
                "<div style='background:#0d0d15; border:1px solid #5bb4d4; border-radius:6px; padding:0.6rem; margin-bottom:0.5rem;'>"
                "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#5bb4d4;'>POSITION</div>"
                "<div style='font-size:0.8rem; color:#e8e8f0;'>"
                "This is the <strong>INTRO TEXT</strong> shown <strong>ABOVE</strong> the product grid. "
                f"Current: {intro_words_current} words. "
                "<br>In Magento 1.9: typically a CMS block above the products, or first paragraph of Description."
                "</div></div>",
                unsafe_allow_html=True,
            )
            new_intro = intro_data.get("rewritten_intro") or intro_data.get("html", "") or intro_data.get("text", "")
            new_intro_wc = len(new_intro.split()) if new_intro else 0
            st.markdown(f"**New intro:** {new_intro_wc} words")
            with st.expander("View intro text", expanded=False):
                st.code(new_intro[:1500], language="html")
            _approval_button("Intro", f"{url_hash}_intro")
            st.markdown("---")
        elif intro_words_current >= 50:
            st.markdown("#### [INTRO] ✓ Intro text is OK")
            st.markdown(
                f"<div style='font-size:0.75rem; color:#33dd88; margin-bottom:0.5rem;'>"
                f"Existing intro has {intro_words_current} words — sufficient, not regenerated</div>",
                unsafe_allow_html=True,
            )
            st.markdown("---")

        # ── Action steps (only if NOT replacing text) ──
        steps = plan.get("steps", [])
        if steps:
            with st.expander(f"[ALTERNATIVE] {len(steps)} action steps (only if you want to keep existing text)", expanded=False):
                st.markdown(
                    "<p style='color:#9b9bb8; font-size:0.85rem;'>"
                    "These steps are for fixing the EXISTING text instead of replacing it. "
                    "If you used the PRIMARY action above, you can skip these.</p>",
                    unsafe_allow_html=True,
                )
                for i, s in enumerate(steps[:5], 1):
                    st.markdown(f"**{i}. {s.get('action', '')}** ({s.get('time_minutes', '?')} min)")
                    st.markdown(f"<div style='color:#9b9bb8; font-size:0.85rem; margin-left:1rem;'>{s.get('detail', '')}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='color:#c8b4ff; font-size:0.85rem; margin-left:1rem;'>→ {s.get('instruction', '')}</div>", unsafe_allow_html=True)
            st.markdown("---")

        # ── New articles/blogs to write that support this page ──
        new_articles = plan.get("new_content_suggestions", [])
        if new_articles:
            st.markdown(f"#### [BLOGS] {len(new_articles)} new articles/guides to write")
            st.markdown(
                "<p style='color:#9b9bb8; font-size:0.8rem;'>"
                "These articles should be created and linked TO this page to support topical authority.</p>",
                unsafe_allow_html=True,
            )
            for art in new_articles[:5]:
                st.markdown(f"- **{art.get('suggested_title', '')}**")
                st.markdown(f"  <div style='color:#9b9bb8; font-size:0.85rem; margin-left:1rem;'>{art.get('why', '')[:200]}</div>", unsafe_allow_html=True)
                if art.get("target_keywords"):
                    st.markdown(f"  <div style='color:#c8b4ff; font-size:0.75rem; margin-left:1rem;'>Keywords: {', '.join(art.get('target_keywords', [])[:5])}</div>", unsafe_allow_html=True)
            _approval_button("Articles", f"{url_hash}_articles")
            st.markdown("---")
        else:
            st.markdown("#### [BLOGS] ✓ No new articles needed")
            st.markdown(
                "<div style='font-size:0.75rem; color:#33dd88; margin-bottom:0.5rem;'>"
                "AI did not identify content gaps requiring new articles.</div>",
                unsafe_allow_html=True,
            )
            st.markdown("---")

        # ── Internal links: pages that should link TO this page ──
        content_audit = audit.get("content_audit") or {}
        linking = content_audit.get("linking") or {}
        link_details = linking.get("details") or {}
        link_fix_suggestions = link_details.get("link_fix_suggestions") or []

        # Find pages that link TO this page from SF link map
        sf_link_map = st.session_state.get("sf_link_map", {})
        links_to = sf_link_map.get("links_to", {}).get(url, []) if sf_link_map else []

        # Inbound anchor stats
        inbound_stats = link_details.get("inbound_anchor_stats") or {}

        st.markdown("#### [INBOUND LINKS] Pages linking to this page")
        if inbound_stats:
            total_in = inbound_stats.get("total", 0)
            descriptive = inbound_stats.get("descriptive", 0)
            generic = inbound_stats.get("generic", 0)
            empty = inbound_stats.get("empty", 0)
            st.markdown(
                f"**Current inbound links:** {total_in} total · "
                f"{descriptive} descriptive · {generic} generic · {empty} empty anchors"
            )
            if total_in < 5:
                st.warning(f"Only {total_in} inbound links — this page needs MORE pages linking to it for topic authority")
            elif generic + empty > total_in * 0.3:
                st.warning(f"{generic + empty}/{total_in} inbound links use generic/empty anchors — ask linking pages to use better anchor text")
        else:
            st.warning("No inbound links data — this page may have very few internal links pointing to it")

        # Suggestions for which pages SHOULD link
        if link_fix_suggestions:
            st.markdown(f"**Suggested new internal links FROM other pages TO this page:** {len(link_fix_suggestions)}")
            for fix in link_fix_suggestions[:5]:
                st.markdown(f"- From: `{fix.get('from_url', '')}`  →  Add link with anchor: **{fix.get('suggested_anchor', '')}**")
                if fix.get("reason"):
                    st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>{fix.get('reason', '')}</div>", unsafe_allow_html=True)
        st.markdown("---")

        # Final actions
        st.markdown("### Done with this page?")
        fcol1, fcol2 = st.columns(2)
        with fcol1:
            if st.button("⏭ Skip (don't mark done)", use_container_width=True, key=f"skip_{url_hash}"):
                st.session_state["_qw_page_idx"] = min(len(pages) - 1, idx + 1)
                st.rerun()
        with fcol2:
            if st.button("✓ Mark done & next page", type="primary", use_container_width=True, key=f"done_{url_hash}"):
                st.session_state[f"_qw_done_{url_hash}"] = True
                # idx stays the same — list rebuilds without this page
                st.rerun()
