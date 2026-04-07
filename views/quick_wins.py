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
        st.markdown("### AI-generated fixes")

        plan = st.session_state.get(plan_key, {})

        # Fix 1: Meta title + description
        if plan.get("meta_changed"):
            st.markdown("#### [1] Meta title + description")
            new_title = plan.get("meta_title", "")
            new_desc = plan.get("meta_description", "")
            st.markdown(f"**Current title:** `{page['title']}` ({len(page['title'])} chars)")
            st.markdown(f"**New title:** `{new_title}` ({len(new_title)} chars)")
            st.markdown(f"**Current description:** `{page['meta_description'][:100]}...`")
            st.markdown(f"**New description:** `{new_desc}` ({len(new_desc)} chars)")
            st.code(f"Title: {new_title}\nDescription: {new_desc}", language="text")
            _approval_button("Meta", f"{url_hash}_meta")
            st.markdown("---")

        # Fix 2: Page text (category only)
        if has_text:
            st.markdown("#### [2] New page text (with FAQ + E-E-A-T)")
            text_data = st.session_state[text_key]
            html = text_data.get("html", "")
            wc = text_data.get("word_count", 0)
            kws = text_data.get("keywords_integrated", [])
            links = text_data.get("internal_links_added", [])
            st.markdown(f"**Word count:** {wc} · **Keywords integrated:** {len(kws)} · **Internal links:** {len(links)}")
            with st.expander("View HTML preview", expanded=False):
                st.code(html[:3000] + ("..." if len(html) > 3000 else ""), language="html")
            st.download_button(
                "Download HTML",
                data=html,
                file_name=f"{shorten_url(url).replace('/', '_').strip('_')}.html",
                mime="text/html",
                key=f"dl_text_{url_hash}",
            )
            _approval_button("Text", f"{url_hash}_text")
            st.markdown("---")

        # Fix 3: Implementation steps
        steps = plan.get("steps", [])
        if steps:
            st.markdown(f"#### [3] {len(steps)} action steps")
            for i, s in enumerate(steps[:5], 1):
                st.markdown(f"**{i}. {s.get('action', '')}** ({s.get('time_minutes', '?')} min)")
                st.markdown(f"<div style='color:#9b9bb8; font-size:0.85rem; margin-left:1rem;'>{s.get('detail', '')}</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='color:#c8b4ff; font-size:0.85rem; margin-left:1rem;'>→ {s.get('instruction', '')}</div>", unsafe_allow_html=True)
            _approval_button("Steps", f"{url_hash}_steps")
            st.markdown("---")

        # Fix 4: New articles to write
        new_articles = plan.get("new_content_suggestions", [])
        if new_articles:
            st.markdown(f"#### [4] {len(new_articles)} new article suggestions")
            for art in new_articles[:3]:
                st.markdown(f"- **{art.get('suggested_title', '')}**")
                st.markdown(f"  <div style='color:#9b9bb8; font-size:0.85rem; margin-left:1rem;'>{art.get('why', '')[:200]}</div>", unsafe_allow_html=True)
            _approval_button("Articles", f"{url_hash}_articles")
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
