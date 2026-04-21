"""
Quick Wins — One page at a time, fully generated, approve/reject workflow.
For users who want fast wins without navigating multiple menus.
"""

import streamlit as st
from config import get_anthropic_key, has_anthropic_key
from utils.ui_helpers import stable_hash, normalize_url, shorten_url, extract_content_summary


def _get_top_pages(audit_results, top_n=20):
    """Get top pages by lost clicks, excluding done and merge/delete scheduled pages."""
    # Build sets of URLs scheduled for merge (as source) or delete in ideal structure
    ideal = st.session_state.get("_ideal_structure") or {}
    excluded_urls = set()
    if isinstance(ideal, dict):
        for m in ideal.get("merge", []) or []:
            if isinstance(m, dict):
                for from_url in m.get("from", []):
                    excluded_urls.add(normalize_url(from_url))
        for d in ideal.get("delete", []) or []:
            if isinstance(d, dict) and d.get("url"):
                excluded_urls.add(normalize_url(d["url"]))

    # Build set of URLs with crawl issues for priority boosting
    sf_crawl_issues = st.session_state.get("sf_crawl_issues") or {}
    crawl_issue_urls = set()
    for b in sf_crawl_issues.get("broken_links", []) or []:
        if b.get("url"):
            crawl_issue_urls.add(normalize_url(b["url"]))
    for c in sf_crawl_issues.get("canonical_issues", []) or []:
        if c.get("url"):
            crawl_issue_urls.add(normalize_url(c["url"]))

    pages = []
    excluded_count = 0
    for r in audit_results:
        if not r.get("url"):
            continue
        url_hash = stable_hash(r["url"])
        if st.session_state.get(f"_qw_done_{url_hash}", False):
            continue
        # Exclude pages scheduled for merge/delete
        if normalize_url(r["url"]) in excluded_urls:
            excluded_count += 1
            continue
        # Use brand-filtered lost clicks from page profile
        from utils.page_profile import build_page_profile as _bpp_qw
        _prof = _bpp_qw(r["url"])
        _filtered_lost = sum(g.get("lost_clicks", 0) for g in _prof.get("ctr_gaps", []))
        pages.append({
            "url": r["url"],
            "page_type": r.get("page_type", "unknown"),
            "impressions": _prof.get("total_impressions", 0),
            "lost_clicks": _filtered_lost,
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
    # Sort by lost_clicks (primary) with quality verdict + crawl issue boost (secondary).
    # REWRITE pages get priority boost, KEEP pages get deprioritized.
    # Pages with crawl issues get a boost similar to REWRITE.
    def _sort_key(p):
        quality = st.session_state.get(f"_quality_{stable_hash(p['url'])}")
        verdict = quality.get("verdict", "") if quality else ""
        # Boost: REWRITE=2, IMPROVE=1, KEEP/unknown=0
        verdict_boost = {"REWRITE": 2, "IMPROVE": 1}.get(verdict, 0)
        # Crawl issue boost: pages with broken links or canonical issues get +2
        crawl_boost = 2 if normalize_url(p["url"]) in crawl_issue_urls else 0
        total_boost = verdict_boost + crawl_boost
        # Combined: lost_clicks + boost bonus (scaled to not overwhelm lost_clicks)
        return -(p["lost_clicks"] + total_boost * max(p["lost_clicks"] * 0.3, 50))
    pages.sort(key=_sort_key)

    # Store excluded count for display
    st.session_state["_qw_excluded_count"] = excluded_count

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
        generate_page_content,
        generate_intro_rewrite,
    )

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

    # ── Gather CTR gaps for this page ──
    # Build profile once — single source for all derived data
    from utils.page_profile import build_page_profile
    _profile = build_page_profile(url)

    # ── Generate implementation plan (includes meta, steps, links, articles)
    plan_key = f"_ai_plan_{url_hash}"
    if plan_key not in st.session_state:
        with st.spinner("Generating implementation plan..."):
            try:
                result = generate_page_implementation_plan(
                    client, audit, site_context, all_site_urls, language, topic_clusters,
                    ctr_gaps_for_page=_profile.get("ctr_gaps") or [],
                    cannibal_link_targets=_profile.get("cannibal_link_targets") or [],
                    cluster_link_outgoing=_profile.get("cluster_link_outgoing") or [],
                    structural_signals=_profile.get("structural_signals") or {},
                    editorial_images=_profile.get("editorial_images") or [],
                )
                st.session_state[plan_key] = result
            except Exception as e:
                st.error(f"Plan generation failed: {e}")
                st.session_state[plan_key] = {"error": str(e), "steps": []}

    # ── Bottom text + intro text are generated on-demand (not auto) to keep page load fast
    # They will be triggered by buttons in the page view below

    from utils.persistence import save_ai_cache
    save_ai_cache()


def _build_total_plan(page, plan_data, text_data, intro_data):
    """Build ordered action list with priorities and time estimates."""
    from utils.page_profile import build_page_profile

    url = page["url"]
    audit = page["audit"]
    url_hash = stable_hash(url)
    profile = build_page_profile(url)
    actions = []

    # Priority 1: Cannibalization — NEVER suggest redirecting homepage, sale pages, etc.
    from urllib.parse import urlparse as _up_qw
    page_path = _up_qw(normalize_url(url)).path.rstrip("/")
    is_homepage = page_path == "" or page_path == "/"

    for cannibal in profile["cannibalization"]:
        if cannibal.get("is_winner"):
            actions.append({
                "priority": 1,
                "title": f"CANNIBALIZATION: This page WINS for '{cannibal['query']}'",
                "detail": f"{cannibal.get('lost_clicks', 0):,.0f} lost clicks. Other pages should link here.",
                "time": 15,
                "type": "cannibalization",
            })
        else:
            # NEVER redirect: homepage, sale pages, or pages with different intent
            from utils.site_patterns import get_sale_patterns
            is_sale = any(sp in url.lower() for sp in get_sale_patterns())
            if is_homepage:
                actions.append({
                    "priority": 1,
                    "title": f"CANNIBALIZATION: Homepage competes for '{cannibal['query']}'",
                    "detail": f"Do NOT redirect homepage. Instead: strengthen {', '.join(cannibal.get('competing_pages', [])[:2])} to own this query, so homepage stops competing.",
                    "time": 10,
                    "type": "cannibalization",
                })
            elif is_sale:
                actions.append({
                    "priority": 1,
                    "title": f"CANNIBALIZATION: Sale page competes for '{cannibal['query']}'",
                    "detail": f"Do NOT redirect. Differentiate meta to target sale variant. Add link to main category.",
                    "time": 10,
                    "type": "cannibalization",
                })
            else:
                actions.append({
                    "priority": 1,
                    "title": f"CANNIBALIZATION: This page competes for '{cannibal['query']}'",
                    "detail": f"Differentiate meta from {', '.join(cannibal.get('competing_pages', [])[:2])}. See Site Cleanup → Merge tab for full analysis.",
                    "time": 10,
                    "type": "cannibalization",
                })
        break  # Only show first cannibalization issue

    # Priority 2: Meta title + description — only if actually different from current
    if plan_data.get("meta_changed"):
        new_title = plan_data.get("meta_title", "")
        new_desc = plan_data.get("meta_description", "")
        current_title = (page.get("title") or "").strip()
        current_desc = (page.get("meta_description") or "").strip()
        # Skip if AI suggestion is identical to current meta
        title_changed = new_title.strip() and new_title.strip().lower() != current_title.lower()
        desc_changed = new_desc.strip() and new_desc.strip().lower() != current_desc.lower()
        if title_changed or desc_changed:
            detail_parts = []
            if title_changed:
                detail_parts.append(f"Current title: {current_title} ({len(current_title)} chars)\nNew title: {new_title} ({len(new_title)} chars)")
            else:
                detail_parts.append(f"Title: OK (no change needed)")
            if desc_changed:
                detail_parts.append(f"Current desc: {current_desc[:80]}... ({len(current_desc)} chars)\nNew desc: {new_desc} ({len(new_desc)} chars)")
            else:
                detail_parts.append(f"Description: OK (no change needed)")
            actions.append({
                "priority": 2,
                "title": "Update meta title and description",
                "detail": "\n".join(detail_parts),
                "time": 5,
                "type": "meta",
            })

    # Priority 3: Replace bottom text — only if current bottom text is thin or missing
    if text_data and text_data.get("html"):
        wc = text_data.get("word_count", 0)
        current_bottom_words = audit.get("bottom_word_count", 0)
        # Skip if current bottom text is already substantial (300+ words) and new text isn't significantly longer
        if current_bottom_words >= 300 and wc <= current_bottom_words * 1.3:
            actions.append({
                "priority": 3,
                "title": "Bottom text already adequate — review AI suggestion",
                "detail": f"Current: {current_bottom_words} words. AI generated: {wc} words. Current text may already be good enough — only replace if quality is poor.",
                "time": 5,
                "type": "bottom_text",
            })
        else:
            actions.append({
                "priority": 3,
                "title": "Replace bottom text (below product grid)",
                "detail": f"Current: {current_bottom_words} words. New text: {wc} words with FAQ, E-E-A-T, products. Download HTML and paste into Magento Description field.",
                "time": 10,
                "type": "bottom_text",
            })

    # Priority 4: Replace intro text — only if current intro is thin or missing
    if intro_data and not intro_data.get("error"):
        new_intro = intro_data.get("rewritten_intro") or intro_data.get("html", "") or intro_data.get("text", "")
        if new_intro:
            intro_wc = len(new_intro.split())
            current_intro_words = audit.get("intro_word_count", 0)
            if current_intro_words >= 80:
                # Current intro is decent length — flag as review, not replace
                actions.append({
                    "priority": 4,
                    "title": "Intro text exists — review AI suggestion",
                    "detail": f"Current intro: {current_intro_words} words (already meets minimum). AI suggestion: {intro_wc} words. Only replace if current intro lacks target keywords.",
                    "time": 5,
                    "type": "intro",
                })
            else:
                actions.append({
                    "priority": 4,
                    "title": "Update intro text (above product grid)",
                    "detail": f"Current intro: {current_intro_words} words (too thin). New intro: {intro_wc} words. Paste as first paragraph of Description.",
                    "time": 5,
                    "type": "intro",
                })

    # Priority 5: Add missing internal links
    content_audit = audit.get("content_audit") or {}
    linking = content_audit.get("linking") or {}
    link_details = linking.get("details") or {}
    missing_links = link_details.get("missing_crosslinks", [])
    if missing_links:
        actions.append({
            "priority": 5,
            "title": f"Add {len(missing_links)} missing internal links to cluster pages",
            "detail": "See [INBOUND LINKS] section for specific URLs and anchor texts",
            "time": len(missing_links) * 2,
            "type": "links_add",
        })

    # Priority 6: Remove bad links
    links_to_remove = link_details.get("links_to_remove", [])
    if links_to_remove:
        actions.append({
            "priority": 6,
            "title": f"Review {len(links_to_remove)} links pointing outside topic cluster",
            "detail": "Remove only if they harm topical focus — be conservative",
            "time": 5,
            "type": "links_remove",
        })

    # Priority 7: New articles to write — combined from plan + content_roadmap + content_gaps
    new_articles = list(plan_data.get("new_content_suggestions", []) or [])

    # Add from content_roadmap if this URL is the link_from source
    roadmap = st.session_state.get("content_roadmap", {})
    if isinstance(roadmap, dict):
        for a in roadmap.get("new_articles", []) or []:
            if isinstance(a, dict):
                link_from = a.get("supporting_page") or a.get("link_from", "")
                if normalize_url(link_from) == normalize_url(url):
                    new_articles.append(a)

    # Deduplicate by title
    seen_titles = set()
    unique_articles = []
    for a in new_articles:
        if isinstance(a, dict):
            title = a.get("suggested_title", "")
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_articles.append(a)
    new_articles = unique_articles
    if new_articles:
        actions.append({
            "priority": 7,
            "title": f"Write {len(new_articles)} supporting blog articles",
            "detail": f"Topics: {', '.join(a.get('suggested_title', '')[:40] for a in new_articles[:3])}",
            "time": len(new_articles) * 60,
            "type": "blogs",
        })

    # Priority 7b: Topic-level gaps (from profile's content_gaps + clusters)
    page_gaps = profile["content_gaps"]
    if page_gaps:
        all_issues = []
        for g in page_gaps:
            for iss in g.get("issues", []):
                all_issues.append(f"[{g.get('topic', g.get('cluster', '?'))}] {iss}")
        if all_issues:
            actions.append({
                "priority": 7,
                "title": f"Topic gaps: {len(all_issues)} issue(s) in clusters this page belongs to",
                "detail": " · ".join(all_issues[:3]) + (" ..." if len(all_issues) > 3 else ""),
                "time": 15,
                "type": "topic_gaps",
            })

    # Priority 8: Technical fixes
    tech_items = []
    schema_types = audit.get("schema_types", []) or []
    if not any("breadcrumb" in str(s).lower() for s in schema_types):
        tech_items.append("BreadcrumbList schema")
    if page["page_type"] == "category" and not any("itemlist" in str(s).lower() for s in schema_types):
        tech_items.append("ItemList schema")
    images_no_alt = audit.get("images_without_alt", 0)
    if images_no_alt > 0:
        tech_items.append(f"{images_no_alt} alt texts")
    if tech_items:
        actions.append({
            "priority": 8,
            "title": f"Technical fixes: {', '.join(tech_items)}",
            "detail": "Add schema markup and fix alt texts",
            "time": 15,
            "type": "technical",
        })

    return actions


def _validate_generated_content(page, text_data, plan_data):
    """
    Post-generation validation layer.
    Verifies AI-generated content actually uses correct URLs, products, images.
    Returns dict with passed/failed checks.
    """
    import re

    results = {
        "checks": [],
        "passed": 0,
        "failed": 0,
        "warnings": 0,
    }

    def _check(passed, message, severity="error"):
        results["checks"].append({"passed": passed, "message": message, "severity": severity})
        if passed:
            results["passed"] += 1
        elif severity == "warning":
            results["warnings"] += 1
        else:
            results["failed"] += 1

    audit = page["audit"]
    html = text_data.get("html", "") if text_data else ""

    # ── 1. Check all URLs in generated HTML exist on the site ──
    all_site_urls = set()
    audit_results = st.session_state.get("audit_results", [])
    for r in audit_results:
        if r.get("url"):
            all_site_urls.add(normalize_url(r["url"]))
    gsc = st.session_state.get("gsc_data")
    if gsc is not None and hasattr(gsc, "page"):
        for p in gsc["page"].unique():
            all_site_urls.add(normalize_url(str(p)))

    if html:
        urls_in_html = re.findall(r'href=["\']([^"\']+)["\']', html)
        site_urls_used = [u for u in urls_in_html if "mshop.se" in u or u.startswith("/")]

        invented = []
        for u in site_urls_used:
            norm = normalize_url(u)
            if norm not in all_site_urls:
                invented.append(u)

        if invented:
            _check(False, f"{len(invented)} invented URLs in generated text (not on site): {', '.join(invented[:3])}", "error")
        else:
            _check(True, f"All {len(site_urls_used)} internal URLs exist on the site", "info")

        # ── 2. Check URLs don't point to broken pages ──
        crawl_issues = st.session_state.get("sf_crawl_issues", {})
        broken_urls = set(normalize_url(b.get("url", "")) for b in crawl_issues.get("broken_links", []))
        redirected_urls = set(normalize_url(r.get("url", "")) for r in crawl_issues.get("redirect_chains", []))
        noindex_urls = set(normalize_url(n.get("url", "")) for n in crawl_issues.get("non_indexable", []))

        broken_in_text = [u for u in site_urls_used if normalize_url(u) in broken_urls]
        redirect_in_text = [u for u in site_urls_used if normalize_url(u) in redirected_urls]
        noindex_in_text = [u for u in site_urls_used if normalize_url(u) in noindex_urls]

        if broken_in_text:
            _check(False, f"{len(broken_in_text)} links point to BROKEN pages: {', '.join(broken_in_text[:3])}", "error")
        else:
            _check(True, "No links to broken pages", "info")

        if redirect_in_text:
            _check(False, f"{len(redirect_in_text)} links point to REDIRECT pages: {', '.join(redirect_in_text[:3])}", "warning")

        if noindex_in_text:
            _check(False, f"{len(noindex_in_text)} links point to NON-INDEXABLE pages: {', '.join(noindex_in_text[:3])}", "warning")

        # ── 3. Check product images are actually used ──
        real_products = audit.get("products", []) or []
        if real_products:
            real_image_urls = set(p.get("image", "") for p in real_products if p.get("image"))
            images_in_html = set(re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html))

            if real_image_urls:
                used_real_images = real_image_urls & images_in_html
                if used_real_images:
                    _check(True, f"Uses {len(used_real_images)}/{len(real_image_urls)} real product images", "info")
                else:
                    _check(False, f"0/{len(real_image_urls)} real product images used — AI may have invented image paths", "warning")

        # ── 4. Check product URLs are real ──
        real_product_urls = set(normalize_url(p.get("url", "")) for p in real_products if p.get("url"))
        product_link_urls = set(normalize_url(u) for u in site_urls_used
                                if any(patt in u.lower() for patt in ["/produkt", "/product", "/p/"]))

        if real_product_urls and product_link_urls:
            invented_products = product_link_urls - real_product_urls - all_site_urls
            if invented_products:
                _check(False, f"{len(invented_products)} invented product URLs", "error")
            else:
                _check(True, "All product URLs are real", "info")

        # ── 5. Check minimum link count ──
        link_count = len(site_urls_used)
        if link_count < 8:
            _check(False, f"Only {link_count} internal links (target: 8-12)", "warning")
        else:
            _check(True, f"{link_count} internal links (good)", "info")

        # ── 6. Check FAQ section present ──
        if page["page_type"] == "category":
            has_faq = "vanliga frågor" in html.lower() or "<h2" in html.lower() and "faq" in html.lower()
            _check(has_faq, "FAQ section present" if has_faq else "FAQ section missing", "warning" if not has_faq else "info")

        # ── 7. Check target keywords are present ──
        target_keywords = audit.get("target_keywords", [])[:5]
        if target_keywords:
            html_lower = html.lower()
            missing_kws = [kw for kw in target_keywords if kw.lower() not in html_lower]
            if missing_kws:
                _check(False, f"{len(missing_kws)}/{len(target_keywords)} target keywords missing: {', '.join(missing_kws[:3])}", "warning")
            else:
                _check(True, f"All {len(target_keywords)} target keywords present", "info")

    return results


def _export_page_as_markdown(page, plan_data, text_data, intro_data):
    """Export everything for this page as markdown."""
    url = page["url"]
    audit = page["audit"]
    md = []

    md.append(f"# {url}")
    md.append("")
    md.append(f"## Metrics")
    md.append(f"- **Impressions:** {page['impressions']:,}")
    md.append(f"- **Lost clicks:** {page['lost_clicks']:,}")
    md.append(f"- **Meta score:** {page['meta_score']}/100")
    md.append(f"- **Content score:** {page['content_score']}/100")
    md.append(f"- **Page type:** {page['page_type']}")
    md.append(f"- **Word count:** {page['word_count']}")
    md.append(f"- **Intent:** {audit.get('search_intent', 'unknown')}")
    md.append(f"- **Referring domains:** {audit.get('referring_domains', 0)}")
    md.append("")

    # Total Plan
    total_plan = _build_total_plan(page, plan_data, text_data, intro_data)
    if total_plan:
        total_time = sum(a["time"] for a in total_plan)
        md.append(f"## TOTAL PLAN ({total_time} min total)")
        md.append("")
        for a in total_plan:
            md.append(f"### {a['priority']}. {a['title']} ({a['time']} min)")
            md.append(a["detail"])
            md.append("")

    # Meta
    md.append("## META")
    md.append(f"**Current title** ({len(page['title'] or '')} chars):")
    md.append(f"`{page['title']}`")
    md.append("")
    md.append(f"**Current description** ({len(page['meta_description'] or '')} chars):")
    md.append(f"`{page['meta_description']}`")
    md.append("")
    if plan_data.get("meta_changed"):
        md.append(f"**New title** ({len(plan_data.get('meta_title', ''))} chars):")
        md.append(f"`{plan_data.get('meta_title', '')}`")
        md.append("")
        md.append(f"**New description** ({len(plan_data.get('meta_description', ''))} chars):")
        md.append(f"`{plan_data.get('meta_description', '')}`")
        md.append("")

    # Intro text
    if intro_data and not intro_data.get("error"):
        new_intro = intro_data.get("rewritten_intro") or intro_data.get("html", "") or intro_data.get("text", "")
        if new_intro:
            md.append("## NEW INTRO TEXT (above product grid)")
            md.append("")
            md.append(new_intro)
            md.append("")

    # Bottom text
    if text_data and (text_data.get("bottom_html") or text_data.get("html")):
        md.append("## NEW BOTTOM TEXT (below product grid)")
        wc = text_data.get("bottom_word_count") or text_data.get("word_count", 0)
        md.append(f"- Word count: {wc}")
        ex_kws, ex_links, ex_prods = extract_content_summary(text_data)
        md.append(f"- Keywords: {', '.join(ex_kws)}")
        md.append(f"- Internal links: {len(ex_links)}")
        md.append(f"- Products: {len(ex_prods)}")
        md.append("")
        md.append("```html")
        md.append(text_data.get("bottom_html") or text_data.get("html", ""))
        md.append("```")
        md.append("")

    # Plan steps
    plan_steps = plan_data.get("steps", [])
    if plan_steps:
        md.append("## IMPLEMENTATION STEPS")
        md.append("")
        for i, s in enumerate(plan_steps, 1):
            md.append(f"### {i}. {s.get('action', '')} ({s.get('time_minutes', '?')} min)")
            md.append(f"**Problem:** {s.get('detail', '')}")
            md.append(f"**Action:** {s.get('instruction', '')}")
            md.append("")

    # New articles
    new_articles = plan_data.get("new_content_suggestions", [])
    if new_articles:
        md.append("## NEW ARTICLES TO WRITE")
        md.append("")
        for a in new_articles:
            md.append(f"### {a.get('suggested_title', '')}")
            md.append(f"**Why:** {a.get('why', '')}")
            md.append(f"**Keywords:** {', '.join(a.get('target_keywords', []))}")
            md.append(f"**Link from:** {a.get('link_from', '')}")
            md.append("")

    # Links
    content_audit = audit.get("content_audit") or {}
    linking = content_audit.get("linking") or {}
    link_details = linking.get("details") or {}

    missing_links = link_details.get("missing_crosslinks", [])
    if missing_links:
        md.append("## INTERNAL LINKS TO ADD")
        md.append("")
        for l in missing_links[:10]:
            md.append(f"- Link to `{l.get('url', '')}` (shared topics: {', '.join(l.get('shared_topics', [])[:2])})")
        md.append("")

    links_to_remove = link_details.get("links_to_remove", [])
    if links_to_remove:
        md.append("## LINKS TO REVIEW (possibly remove)")
        md.append("")
        for l in links_to_remove[:10]:
            md.append(f"- `{l.get('url', '')}` — anchor: '{l.get('anchor', '')}'")
        md.append("")

    # Cannibalization (from profile)
    from utils.page_profile import build_page_profile as _bpp_export
    _export_profile = _bpp_export(url)
    cannibal_entries = _export_profile["cannibalization"]
    if cannibal_entries:
        md.append("## CANNIBALIZATION CONFLICTS")
        md.append("")
        for entry in cannibal_entries[:5]:
            winner_text = "This page WINS" if entry.get("is_winner") else f"Competing: {', '.join(entry.get('competing_pages', []))}"
            md.append(f"- **'{entry.get('query', '')}'** [{entry.get('type', '').upper()}]")
            md.append(f"  - {winner_text}")
            md.append(f"  - Lost clicks: {entry.get('lost_clicks', 0):,.0f}")
        md.append("")

    return "\n".join(md)


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

    # ── REQUIRED: Site validation before per-page work ───────
    site_validation = st.session_state.get("_site_validation")
    if not site_validation or not isinstance(site_validation, dict):
        st.error(
            "⚠ **Site structure validation NOT yet run.** "
            "You should validate the OVERALL site structure before working on individual pages — "
            "otherwise link recommendations and cleanup may be based on flawed assumptions."
        )
        if st.button("Go to Run Pipeline → Step 9: Site Validation", type="primary"):
            st.session_state["selected_page"] = "⚡ Run Pipeline"
            st.rerun()
        st.warning("You can still continue below, but recommendations will be less accurate.")
        st.markdown("---")
    else:
        # Show site health summary
        health_score = site_validation.get("overall_health_score", 0)
        summary = site_validation.get("summary", "")
        critical_issues = site_validation.get("critical_issues", [])
        priority_actions = site_validation.get("priority_actions", [])

        score_color = "#33dd88" if health_score >= 70 else "#ffaa33" if health_score >= 40 else "#ff4455"

        with st.expander(f"🏗 Site Architecture — Health {health_score}/100", expanded=(health_score < 50)):
            st.markdown(
                f"<div style='background:#0d0d15; border-left:4px solid {score_color}; padding:0.8rem; border-radius:0 6px 6px 0; margin-bottom:1rem;'>"
                f"<div style='font-size:0.85rem; color:#c8b4ff;'>{summary}</div></div>",
                unsafe_allow_html=True,
            )
            if critical_issues:
                st.markdown("**Critical site-level issues:**")
                for issue in critical_issues[:5]:
                    st.markdown(f"- {issue}")
            if priority_actions:
                st.markdown("**Site-wide priority actions:**")
                for pa in priority_actions[:5]:
                    if isinstance(pa, dict):
                        st.markdown(f"- **[{pa.get('impact', '?').upper()}]** {pa.get('action', '')} ({pa.get('pages_affected', 0)} pages affected)")
                    else:
                        st.markdown(f"- {pa}")
            st.info("These site-wide issues should be addressed BEFORE or ALONGSIDE per-page work. Per-page recommendations below are informed by this context.")

    audit_results = st.session_state["audit_results"]
    pages = _get_top_pages(audit_results, top_n=20)

    excluded_count = st.session_state.get("_qw_excluded_count", 0)
    if excluded_count > 0:
        st.markdown(
            f"<div style='font-size:0.8rem; color:#9b9bb8; margin-bottom:0.5rem;'>"
            f"{excluded_count} page(s) excluded (scheduled for merge/delete in ideal structure)</div>",
            unsafe_allow_html=True,
        )

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

    # Check if this page is scheduled for merge/delete in ideal structure
    ideal = st.session_state.get("_ideal_structure", {})
    merge_target = None
    delete_reason = None
    if isinstance(ideal, dict):
        for m in ideal.get("merge", []) or []:
            if isinstance(m, dict):
                from_urls = [normalize_url(u) for u in m.get("from", [])]
                if normalize_url(url) in from_urls:
                    merge_target = {"to": m.get("to", ""), "why": m.get("why", "")}
                    break
        for d in ideal.get("delete", []) or []:
            if isinstance(d, dict) and normalize_url(d.get("url", "")) == normalize_url(url):
                delete_reason = d.get("why", "")
                break

    if merge_target:
        st.error(
            f"⚠ **AI Ideal Structure recommends MERGING this page** into `{merge_target['to']}`\n\n"
            f"**Reason:** {merge_target['why']}\n\n"
            f"**Action:** Copy unique content to target, set up 301 redirect, update internal links. "
            f"Do NOT invest in improving this page — it should be removed."
        )

    if delete_reason:
        st.error(
            f"⚠ **AI Ideal Structure recommends DELETING this page**\n\n"
            f"**Reason:** {delete_reason}\n\n"
            f"**Action:** Delete the page, set up 301 redirect to a related page if it has backlinks."
        )

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

    # ── DO THIS FIRST — clear, single top-priority action ──
    issues = _detect_issues(page)
    if issues:
        top_issue = issues[0]
        st.markdown(
            f"<div style='background:#1a1020; border:2px solid #ff6644; border-radius:8px; "
            f"padding:1rem; margin:0.5rem 0 1rem 0;'>"
            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; "
            f"color:#ff6644; letter-spacing:0.05em; margin-bottom:0.3rem;'>DO THIS FIRST</div>"
            f"<div style='font-size:1rem; color:#e8e8f0; font-weight:600;'>{top_issue}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Other issues ────────────────────────────────────────
    if len(issues) > 1:
        with st.expander(f"All {len(issues)} issues detected", expanded=False):
            for issue in issues:
                st.markdown(f"- {issue}")
    elif not issues:
        st.success("No major issues detected on this page")

    st.markdown("---")

    # ── TOTAL PLAN (ordered action list) ────────────────────
    plan_key = f"_ai_plan_{url_hash}"
    text_key = f"_bottom_text_{url_hash}"
    intro_key = f"_intro_text_{url_hash}"

    plan_data = st.session_state.get(plan_key, {})
    text_data = st.session_state.get(text_key, {})
    intro_data = st.session_state.get(intro_key, {})

    if plan_data and not plan_data.get("error"):
        total_plan = _build_total_plan(page, plan_data, text_data, intro_data)
        if total_plan:
            total_time = sum(a["time"] for a in total_plan)

            st.markdown(f"### 📋 TOTAL PLAN — {len(total_plan)} actions · ~{total_time} min")
            st.markdown(
                "<p style='color:#9b9bb8; font-size:0.85rem;'>"
                "Ordered by priority. Start from #1 and work down.</p>",
                unsafe_allow_html=True,
            )

            for a in total_plan:
                priority_colors = {
                    1: "#ff4455",  # Cannibalization
                    2: "#ff6644",  # Meta
                    3: "#ffaa33",  # Bottom text
                    4: "#ffaa33",  # Intro
                    5: "#c8b4ff",  # Links add
                    6: "#c8b4ff",  # Links remove
                    7: "#5bb4d4",  # Blogs
                    8: "#6b6b8a",  # Technical
                }
                color = priority_colors.get(a["priority"], "#6b6b8a")
                st.markdown(
                    f"<div style='background:#0d0d15; border-left:3px solid {color}; padding:0.6rem 0.8rem; margin-bottom:0.4rem; border-radius:0 4px 4px 0;'>"
                    f"<div style='font-size:0.85rem; color:#e8e8f0;'><strong>{a['priority']}. {a['title']}</strong> "
                    f"<span style='color:{color}; font-size:0.7rem;'>· {a['time']} min</span></div>"
                    f"<div style='color:#9b9bb8; font-size:0.75rem; margin-top:0.2rem;'>{a['detail']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            # Export button
            col_exp1, col_exp2 = st.columns([3, 1])
            with col_exp2:
                markdown_export = _export_page_as_markdown(page, plan_data, text_data, intro_data)
                st.download_button(
                    "📄 Export all to Markdown",
                    data=markdown_export,
                    file_name=f"seo_plan_{shorten_url(url).replace('/', '_').strip('_')}.md",
                    mime="text/markdown",
                    key=f"export_{url_hash}",
                    use_container_width=True,
                )
            st.markdown("---")

    # ── Generate / Show fixes ────────────────────────────────
    has_plan = bool(plan_data and not plan_data.get("error"))
    has_text = bool(text_data and not text_data.get("error"))
    has_intro = bool(intro_data and not intro_data.get("error"))

    if not has_plan:
        st.markdown("### AI fixes — not generated yet")
        st.info("Click below to generate implementation plan for this page (~20 seconds)")
        if st.button("Generate plan", type="primary", use_container_width=True, key=f"gen_all_{url_hash}"):
            _generate_all_fixes(page)
            st.rerun()
    else:
        # Check if old format — show prominent regenerate button
        is_old_format = has_text and not (text_data.get("top_html") or text_data.get("bottom_html") or text_data.get("faq_schema"))
        col_h1, col_h2 = st.columns([3, 2] if is_old_format else [4, 1])
        with col_h1:
            st.markdown("### AI-generated fixes")
        with col_h2:
            btn_label = "🔄 Regenerate with new rules" if is_old_format else "Regenerate"
            btn_type = "primary" if is_old_format else "secondary"
            if st.button(btn_label, key=f"regen_{url_hash}", type=btn_type, use_container_width=True):
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
        if not has_text and page["page_type"] == "category":
            st.markdown("#### [PRIMARY] Bottom text — not generated yet")
            if st.button("Generate bottom text", type="primary", key=f"gen_bottom_{url_hash}"):
                with st.spinner("Generating page text with FAQ + E-E-A-T..."):
                    try:
                        from utils.ai_generator import generate_page_content
                        result = generate_page_content(url)
                        st.session_state[text_key] = result
                    except Exception as e:
                        st.error(f"Text generation failed: {e}")
                        st.session_state[text_key] = {"error": str(e)}
                    from utils.persistence import save_ai_cache
                    save_ai_cache()
                st.rerun()
            st.markdown("---")

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
            # Check if generated with new rules (top/bottom split + FAQ schema)
            has_new_format = text_data.get("top_html") or text_data.get("bottom_html") or text_data.get("faq_schema")
            if not has_new_format and text_data.get("html"):
                st.warning("⚠ Text generated with old rules. Click **Regenerate** below for improved text with FAQ schema, product images, hierarchy links, and no prices.")
            html = text_data.get("bottom_html") or text_data.get("html", "")
            wc = text_data.get("bottom_word_count") or text_data.get("word_count", 0)
            kws, links, prods = extract_content_summary(text_data)
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

            # ── Push to Magento (preview → confirm) ──
            from utils.footer_push_ui import render_footer_push_block
            render_footer_push_block(url, html, key_prefix=f"qw_push_{url_hash}")

            st.markdown(
                "<div style='background:#0d0d15; border-left:3px solid #5533ff; padding:0.8rem; margin:0.5rem 0;'>"
                "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#5533ff;'>MANUAL FALLBACK — IF PUSH IS NOT AVAILABLE</div>"
                "<div style='font-size:0.85rem; color:#c8b4ff;'>"
                "1) Download HTML  2) Magento Admin → Catalog → Categories → this category  "
                "3) Paste into <strong>Description</strong> field (NOT 'Page Title' or 'Meta')  "
                "4) Make sure 'Display Mode' is set to 'Products and Static Block' or 'Static Block and Products' "
                "5) Save and clear cache</div></div>",
                unsafe_allow_html=True,
            )
            _approval_button("Bottom Text", f"{url_hash}_text")

            # ── QUALITY VALIDATION of generated content ──
            st.markdown("##### Quality validation")
            val_results = _validate_generated_content(page, text_data, plan)
            total_checks = len(val_results["checks"])
            passed = val_results["passed"]
            failed = val_results["failed"]
            warnings = val_results["warnings"]

            # Status badge
            if failed == 0 and warnings == 0:
                badge_color = "#33dd88"
                badge_text = f"✓ All {total_checks} validations passed"
            elif failed == 0:
                badge_color = "#ffaa33"
                badge_text = f"⚠ {passed}/{total_checks} passed, {warnings} warnings"
            else:
                badge_color = "#ff4455"
                badge_text = f"✗ {failed} FAILED, {warnings} warnings, {passed} passed"

            st.markdown(
                f"<div style='background:#0d0d15; border:2px solid {badge_color}; border-radius:6px; padding:0.6rem; margin:0.5rem 0;'>"
                f"<div style='font-size:0.85rem; color:{badge_color}; font-weight:600;'>{badge_text}</div></div>",
                unsafe_allow_html=True,
            )

            # Show individual check results
            with st.expander("View all validation checks", expanded=(failed > 0)):
                for check in val_results["checks"]:
                    icon = "✓" if check["passed"] else ("✗" if check["severity"] == "error" else "⚠")
                    color = "#33dd88" if check["passed"] else ("#ff4455" if check["severity"] == "error" else "#ffaa33")
                    st.markdown(
                        f"<div style='font-size:0.8rem; color:{color}; margin:0.2rem 0;'>"
                        f"{icon} {check['message']}</div>",
                        unsafe_allow_html=True,
                    )
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

            # Pre-compute meta cache key so both title + description sections can use it
            meta_key = f"_cannibal_meta_{stable_hash(page['url'])}"

            # Title
            t_status = "⚠ TOO LONG" if title_too_long else "⚠ TOO SHORT" if title_too_short else "✓ OK"
            st.markdown(f"**Current title:** `{page['title']}` ({len(page['title'])} chars) {t_status}")
            if new_title and new_title != page['title']:
                st.markdown(f"**New title:** `{new_title}` ({len(new_title)} chars)")
            else:
                # Generate meta via AI instead of asking user to write manually
                if meta_key in st.session_state:
                    cached_meta = st.session_state[meta_key]
                    if isinstance(cached_meta, dict):
                        variants = cached_meta.get("variants", [])
                        if variants:
                            st.markdown(f"**Suggested title:** `{variants[0].get('title', '')}` ({len(variants[0].get('title', ''))} chars)")
                if meta_key not in st.session_state:
                    if st.button("🤖 Generate meta title + description", key=f"gen_meta_{stable_hash(page['url'])}"):
                        try:
                            from utils.ai_generator import get_client, generate_meta_suggestions
                            from config import get_anthropic_key
                            client = get_client(get_anthropic_key())
                            profile = build_page_profile(page["url"])
                            target_kws = [q["query"] for q in profile.get("gsc_queries", [])[:5]]
                            result = generate_meta_suggestions(client, page["audit"], target_kws,
                                st.session_state.get("site_context", ""),
                                st.session_state.get("content_language", "Swedish"))
                            st.session_state[meta_key] = result
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

            # Description
            d_status = "⚠ TOO LONG" if desc_too_long else "⚠ TOO SHORT" if desc_too_short else "✓ OK"
            st.markdown(f"**Current description:** `{(page['meta_description'] or '')[:100]}...` ({len(page['meta_description'] or '')} chars) {d_status}")
            if new_desc and new_desc != page['meta_description']:
                st.markdown(f"**New description:** `{new_desc}` ({len(new_desc)} chars)")
            elif meta_key in st.session_state:
                cached_meta = st.session_state.get(meta_key, {})
                if isinstance(cached_meta, dict):
                    variants = cached_meta.get("variants", [])
                    if variants:
                        st.markdown(f"**Suggested description:** `{variants[0].get('description', '')}` ({len(variants[0].get('description', ''))} chars)")

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
        elif page["page_type"] == "category" and not has_intro:
            st.markdown(f"#### [INTRO] Intro text — not generated yet ({intro_words_current} words currently)")
            if st.button("Generate intro text", key=f"gen_intro_{url_hash}"):
                with st.spinner("Generating intro text..."):
                    try:
                        missing_kws = []
                        content_audit = page["audit"].get("content_audit") or {}
                        kw_coverage = content_audit.get("keyword_coverage") or {}
                        missing_kws = (kw_coverage.get("missing", []) or [])[:8]
                        from utils.ai_generator import get_client, generate_intro_rewrite
                        client = get_client(get_anthropic_key())
                        site_context = st.session_state.get("site_context", "")
                        language = st.session_state.get("content_language", "Swedish")
                        result = generate_intro_rewrite(
                            client,
                            missing_keywords=missing_kws,
                            existing_intro=page["audit"].get("intro_text", "") or "",
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
                st.rerun()
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
            for art_idx, art in enumerate(new_articles[:5]):
                art_title = art.get('suggested_title', '')
                art_hash = stable_hash(f"{url}_{art_title}")
                art_cache_key = f"_gen_article_{art_hash}"

                st.markdown(f"**{art_idx+1}. {art_title}**")
                st.markdown(f"<div style='color:#9b9bb8; font-size:0.85rem; margin-left:1rem;'>{art.get('why', '')[:200]}</div>", unsafe_allow_html=True)
                if art.get("target_keywords"):
                    st.markdown(f"<div style='color:#c8b4ff; font-size:0.75rem; margin-left:1rem;'>Keywords: {', '.join(art.get('target_keywords', [])[:5])}</div>", unsafe_allow_html=True)
                if art.get("link_from"):
                    st.markdown(f"<div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>Link from: {art.get('link_from', '')}</div>", unsafe_allow_html=True)

                if art_cache_key in st.session_state:
                    article_data = st.session_state[art_cache_key]
                    article_html = article_data.get("html", "") if isinstance(article_data, dict) else ""
                    wc = article_data.get("word_count", 0) if isinstance(article_data, dict) else 0
                    st.markdown(f"<div style='color:#33dd88; font-size:0.75rem; margin-left:1rem;'>✓ Generated: {wc} words</div>", unsafe_allow_html=True)
                    with st.expander(f"View article {art_idx+1}", expanded=False):
                        st.code(article_html[:3000] + ("..." if len(article_html) > 3000 else ""), language="html")
                    st.download_button(
                        "Download article HTML",
                        data=article_html,
                        file_name=f"blog_{art_hash}.html",
                        mime="text/html",
                        key=f"dl_art_{art_hash}",
                    )
                else:
                    if st.button(f"Generate full article", key=f"gen_art_{art_hash}"):
                        try:
                            from utils.ai_generator import generate_full_article_html
                            client = get_client(get_anthropic_key())
                            with st.spinner(f"Generating article: {art_title}..."):
                                audit_results_list = st.session_state.get("audit_results", [])
                                raw_urls_s = set(r["url"] for r in audit_results_list if r.get("url"))
                                all_site_urls_local = sorted(raw_urls_s)
                                article_result = generate_full_article_html(
                                    client,
                                    title=art_title,
                                    keywords=art.get("target_keywords", []),
                                    content_type=art.get("type", "guide"),
                                    products=None,
                                    link_from_url=art.get("link_from", url),
                                    tone_sample="",
                                    site_context=st.session_state.get("site_context", ""),
                                    language=st.session_state.get("content_language", "Swedish"),
                                    all_site_urls=all_site_urls_local,
                                    cluster_context=f"This article supports {url} as part of its topic cluster",
                                )
                            st.session_state[art_cache_key] = article_result
                            from utils.persistence import save_ai_cache
                            save_ai_cache()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Article generation failed: {e}")
                st.markdown("")
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
        audit = page["audit"]  # Local alias for the audit data
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

        if link_fix_suggestions:
            st.markdown(f"**Suggested new internal links FROM other pages TO this page:** {len(link_fix_suggestions)}")
            for fix in link_fix_suggestions[:5]:
                st.markdown(f"- From: `{fix.get('from_url', '')}`  →  Add link with anchor: **{fix.get('suggested_anchor', '')}**")
                if fix.get("reason"):
                    st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>{fix.get('reason', '')}</div>", unsafe_allow_html=True)
        st.markdown("---")

        # ── Links to REMOVE from this page ──
        links_to_remove = link_details.get("links_to_remove") or []
        if links_to_remove:
            st.markdown(f"#### [REMOVE LINKS] {len(links_to_remove)} links to consider removing")
            st.markdown(
                "<p style='color:#9b9bb8; font-size:0.8rem;'>"
                "These links point to pages outside this topic cluster. "
                "Remove only if they don't serve user navigation.</p>",
                unsafe_allow_html=True,
            )
            for l in links_to_remove[:5]:
                st.markdown(f"- `{l.get('url', '')}` (anchor: '{l.get('anchor', '')}')")
            _approval_button("Remove links", f"{url_hash}_remove")
            st.markdown("---")

        # ── Cannibalization: keywords competing with other pages ──
        cannibal_df = st.session_state.get("cannibalization")
        if cannibal_df is not None and not cannibal_df.empty:
            page_cannibals = []
            for _, row in cannibal_df.iterrows():
                pages_detail = row.get("pages_detail", [])
                if isinstance(pages_detail, list):
                    for p in pages_detail:
                        if normalize_url(p.get("page", "")) == normalize_url(url):
                            # Capture ALL competing URLs (excluding this page itself)
                            competing = []
                            for pp in pages_detail:
                                pu = pp.get("page", "")
                                if normalize_url(pu) != normalize_url(url):
                                    competing.append({
                                        "url": pu,
                                        "position": pp.get("position", "?"),
                                        "clicks": pp.get("clicks", 0),
                                        "impressions": pp.get("impressions", 0),
                                    })
                            page_cannibals.append({
                                "query": row["query"],
                                "severity": row["severity"],
                                "lost_clicks": row["lost_clicks_estimate"],
                                "winner": row.get("recommended_winner", ""),
                                "merge_action": row.get("merge_action", ""),
                                "page_count": row.get("page_count", 2),
                                "competing_pages": competing,
                            })
                            break
            if page_cannibals:
                # ── CONSOLIDATE: group by competing URL so the same
                # competitor doesn't repeat 5x for keyword variants ──
                from collections import defaultdict
                by_competitor = defaultdict(lambda: {"queries": [], "total_lost": 0, "merge_action": "", "severity": "mild", "is_winner": True, "competing_pages": []})
                for c in page_cannibals:
                    # Build a key from the competing URLs (sorted)
                    comp_key = tuple(sorted(normalize_url(cp["url"]) for cp in (c.get("competing_pages") or [])))
                    if not comp_key:
                        comp_key = ("unknown",)
                    grp = by_competitor[comp_key]
                    grp["queries"].append(c["query"])
                    grp["total_lost"] += c.get("lost_clicks", 0)
                    if c.get("severity") == "severe":
                        grp["severity"] = "severe"
                    elif c.get("severity") == "moderate" and grp["severity"] == "mild":
                        grp["severity"] = "moderate"
                    if not (normalize_url(c.get("winner", "")) == normalize_url(url)):
                        grp["is_winner"] = False
                    if not grp["merge_action"] and c.get("merge_action"):
                        grp["merge_action"] = c["merge_action"]
                    if not grp["competing_pages"] and c.get("competing_pages"):
                        grp["competing_pages"] = c["competing_pages"]

                groups = sorted(by_competitor.values(), key=lambda g: -g["total_lost"])
                total_conflicts = len(page_cannibals)
                unique_competitors = len(groups)
                st.markdown(f"#### [CANNIBALIZATION] {total_conflicts} keyword conflicts → {unique_competitors} unique competitor(s)")

                for grp in groups[:5]:
                    sev_color = {"severe": "#ff4455", "moderate": "#ffaa33", "mild": "#6b6b8a"}.get(grp["severity"], "#6b6b8a")
                    winner_label = "🏆 This page WINS" if grp["is_winner"] else "✗ Competitor leads"
                    queries_str = ", ".join(f"'{q}'" for q in grp["queries"][:5])
                    if len(grp["queries"]) > 5:
                        queries_str += f" +{len(grp['queries'])-5} more"

                    st.markdown(
                        f"<div style='background:#12121f; border-left:4px solid {sev_color}; "
                        f"padding:0.8rem; margin:0.5rem 0; border-radius:0 6px 6px 0;'>"
                        f"<div style='font-size:0.9rem; color:#e8e8f0; font-weight:600;'>"
                        f"{len(grp['queries'])} keywords: {queries_str}</div>"
                        f"<div style='color:{sev_color}; font-size:0.8rem; margin-top:0.2rem;'>"
                        f"[{grp['severity'].upper()}] · {grp['total_lost']:,} total lost clicks · {winner_label}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                    if grp.get("competing_pages"):
                        st.markdown("**Competing with:**")
                        for cp in grp["competing_pages"]:
                            st.markdown(
                                f"- `{cp['url']}` — pos {cp.get('position','?')} · "
                                f"{cp.get('clicks',0)} clicks · {cp.get('impressions',0):,} impressions"
                            )

                    if grp.get("merge_action"):
                        with st.expander("What to do (click to expand)", expanded=False):
                            st.markdown(grp["merge_action"])

                _approval_button("Cannibal", f"{url_hash}_cannibal")
                st.markdown("---")

        # ── Schema, alt text, crawl issues ──
        st.markdown("#### [TECHNICAL]")
        tech_items = []

        # Schema
        schema_types = audit.get("schema_types", []) or []
        if not any("breadcrumb" in str(s).lower() for s in schema_types):
            tech_items.append("Missing BreadcrumbList schema")
        if page["page_type"] == "category" and not any("itemlist" in str(s).lower() or "collection" in str(s).lower() for s in schema_types):
            tech_items.append("Missing ItemList/Collection schema (recommended for category pages)")

        # Alt text
        images_no_alt = audit.get("images_without_alt", 0)
        if images_no_alt > 0:
            tech_items.append(f"{images_no_alt} images missing alt text")

        # Crawl issues for this URL
        crawl_issues = st.session_state.get("sf_crawl_issues", {})
        if crawl_issues:
            for issue_type in ["broken_links", "non_indexable", "redirect_chains", "canonical_issues", "near_duplicates"]:
                items = crawl_issues.get(issue_type, [])
                for item in items:
                    if normalize_url(item.get("url", "")) == normalize_url(url):
                        tech_items.append(f"{issue_type.replace('_', ' ').title()}: {item.get('action', '')[:100]}")
                        break

        # Authority
        rd = audit.get("referring_domains", 0)
        if rd < 5:
            tech_items.append(f"LOW backlink authority: only {rd} referring domains — this page needs link building")
        elif rd >= 50:
            tech_items.append(f"✓ Strong authority: {rd} referring domains")

        # AI quality verdict
        from utils.ui_helpers import stable_hash as _sh
        quality = st.session_state.get(f"_quality_{_sh(url)}")
        if quality:
            verdict = quality.get("verdict", "")
            score = quality.get("score", 0)
            v_color = {"REWRITE": "#ff4455", "IMPROVE": "#ffaa33", "KEEP": "#33dd88"}.get(verdict, "#6b6b8a")
            tech_items.append(f"<span style='color:{v_color}; font-weight:600;'>AI text quality: {verdict} ({score}/10)</span> — {quality.get('summary', '')[:120]}")

        if tech_items:
            for item in tech_items:
                st.markdown(f"- {item}", unsafe_allow_html=True)
        else:
            st.markdown("<div style='color:#33dd88;'>No technical issues detected</div>", unsafe_allow_html=True)
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
