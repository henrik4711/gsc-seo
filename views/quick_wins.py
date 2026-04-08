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


def _build_total_plan(page, plan_data, text_data, intro_data):
    """Build ordered action list with priorities and time estimates."""
    url = page["url"]
    audit = page["audit"]
    url_hash = stable_hash(url)
    actions = []

    # Priority 1: Cannibalization resolution (if this page is a LOSER)
    cannibal_df = st.session_state.get("cannibalization")
    if cannibal_df is not None and not cannibal_df.empty:
        for _, row in cannibal_df.iterrows():
            if row.get("severity") not in ("severe", "moderate"):
                continue
            pages_detail = row.get("pages_detail", [])
            if isinstance(pages_detail, list):
                is_involved = any(normalize_url(p.get("page", "")) == normalize_url(url) for p in pages_detail)
                if is_involved:
                    is_winner = normalize_url(row.get("recommended_winner", "")) == normalize_url(url)
                    merge_action = row.get("merge_action", "")
                    if "DIFFERENT INTENTS" not in merge_action and "Homepage involved" not in merge_action:
                        if is_winner:
                            actions.append({
                                "priority": 1,
                                "title": f"CANNIBALIZATION: This page WINS for '{row['query']}'",
                                "detail": f"{row['lost_clicks_estimate']:,} lost clicks. Redirect loser pages here.",
                                "time": 15,
                                "type": "cannibalization",
                            })
                        else:
                            actions.append({
                                "priority": 1,
                                "title": f"CANNIBALIZATION: This page LOSES for '{row['query']}'",
                                "detail": f"Redirect this page to: {row.get('recommended_winner', '')}",
                                "time": 10,
                                "type": "cannibalization",
                            })
                    break

    # Priority 2: Meta title + description
    if plan_data.get("meta_changed"):
        new_title = plan_data.get("meta_title", "")
        new_desc = plan_data.get("meta_description", "")
        actions.append({
            "priority": 2,
            "title": "Update meta title and description",
            "detail": f"Title: {new_title}\nDescription: {new_desc}",
            "time": 5,
            "type": "meta",
        })

    # Priority 3: Replace bottom text
    if text_data and text_data.get("html"):
        wc = text_data.get("word_count", 0)
        actions.append({
            "priority": 3,
            "title": "Replace bottom text (below product grid)",
            "detail": f"New text: {wc} words with FAQ, E-E-A-T, products. Download HTML and paste into Magento Description field.",
            "time": 10,
            "type": "bottom_text",
        })

    # Priority 4: Replace intro text
    if intro_data and not intro_data.get("error"):
        new_intro = intro_data.get("rewritten_intro") or intro_data.get("html", "") or intro_data.get("text", "")
        if new_intro:
            intro_wc = len(new_intro.split())
            actions.append({
                "priority": 4,
                "title": "Update intro text (above product grid)",
                "detail": f"New intro: {intro_wc} words. Paste as first paragraph of Description.",
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

    # Priority 7b: Topic-level gaps (from content_gaps analysis)
    content_gaps = st.session_state.get("content_gaps", []) or []
    topic_clusters_data = st.session_state.get("topic_clusters", {}) or {}
    page_topics_map = topic_clusters_data.get("page_topics", {}) if isinstance(topic_clusters_data, dict) else {}
    # Find topics this page belongs to (normalize URLs for matching)
    page_topic_names = set()
    norm_url = normalize_url(url)
    for p_url, topics in page_topics_map.items():
        if normalize_url(p_url) == norm_url and isinstance(topics, list):
            for t in topics:
                if isinstance(t, dict) and t.get("topic"):
                    page_topic_names.add(t["topic"])
    page_gaps = [g for g in content_gaps
                 if isinstance(g, dict) and g.get("topic") in page_topic_names and g.get("issues")]
    if page_gaps:
        all_issues = []
        for g in page_gaps:
            for iss in g.get("issues", []):
                all_issues.append(f"[{g.get('topic','?')}] {iss}")
        actions.append({
            "priority": 7,
            "title": f"Topic gaps: {len(all_issues)} issue(s) in clusters this page belongs to",
            "detail": " · ".join(all_issues[:3]) + (" …" if len(all_issues) > 3 else ""),
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
    if text_data and text_data.get("html"):
        md.append("## NEW BOTTOM TEXT (below product grid)")
        md.append(f"- Word count: {text_data.get('word_count', 0)}")
        md.append(f"- Keywords: {', '.join(text_data.get('keywords_integrated', []))}")
        md.append(f"- Internal links: {len(text_data.get('internal_links_added', []))}")
        md.append(f"- Products: {len(text_data.get('products_featured', []))}")
        md.append("")
        md.append("```html")
        md.append(text_data.get("html", ""))
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

    # Cannibalization
    cannibal_df = st.session_state.get("cannibalization")
    if cannibal_df is not None and not cannibal_df.empty:
        cannibal_rows = []
        for _, row in cannibal_df.iterrows():
            pages_detail = row.get("pages_detail", [])
            if isinstance(pages_detail, list):
                if any(normalize_url(p.get("page", "")) == normalize_url(url) for p in pages_detail):
                    cannibal_rows.append(row)
        if cannibal_rows:
            md.append("## CANNIBALIZATION CONFLICTS")
            md.append("")
            for row in cannibal_rows[:5]:
                is_winner = normalize_url(row.get("recommended_winner", "")) == normalize_url(url)
                winner_text = "This page WINS" if is_winner else f"Winner: {row.get('recommended_winner', '')}"
                md.append(f"- **'{row['query']}'** [{row['severity'].upper()}]")
                md.append(f"  - {winner_text}")
                md.append(f"  - Lost clicks: {row['lost_clicks_estimate']:,}")
                md.append(f"  - Action: {row.get('merge_action', '')[:200]}")
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

    # ── Issues detected ──────────────────────────────────────
    st.markdown("### What's wrong (auto-detected)")
    issues = _detect_issues(page)
    if not issues:
        st.success("No major issues detected on this page")
    else:
        for issue in issues:
            st.markdown(f"- {issue}")

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
                            page_cannibals.append({
                                "query": row["query"],
                                "severity": row["severity"],
                                "lost_clicks": row["lost_clicks_estimate"],
                                "winner": row.get("recommended_winner", ""),
                                "merge_action": row.get("merge_action", ""),
                                "page_count": row.get("page_count", 2),
                            })
                            break
            if page_cannibals:
                st.markdown(f"#### [CANNIBALIZATION] {len(page_cannibals)} keyword conflicts")
                st.markdown(
                    "<p style='color:#9b9bb8; font-size:0.8rem;'>"
                    "This page competes with other pages for these keywords.</p>",
                    unsafe_allow_html=True,
                )
                for c in page_cannibals[:5]:
                    sev_color = {"severe": "#ff4455", "moderate": "#ffaa33", "mild": "#6b6b8a"}.get(c["severity"], "#6b6b8a")
                    is_winner = normalize_url(c["winner"]) == normalize_url(url)
                    winner_label = "✓ This page is WINNER" if is_winner else f"✗ Winner: {c['winner']}"
                    st.markdown(
                        f"- **{c['query']}** "
                        f"<span style='color:{sev_color}; font-weight:600;'>[{c['severity'].upper()}]</span> · "
                        f"{c['page_count']} pages · {c['lost_clicks']:,} lost clicks · {winner_label}",
                        unsafe_allow_html=True,
                    )
                    if c.get("merge_action"):
                        st.markdown(f"  <div style='color:#c8b4ff; font-size:0.75rem; margin-left:1rem;'>{c['merge_action'][:200]}</div>", unsafe_allow_html=True)
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
