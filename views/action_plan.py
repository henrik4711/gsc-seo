"""
Action Plan — Implementation Guide
Per-page step-by-step instructions with AI buttons for every fix.
Combines data from: audit, topic clusters, internal linking, CTR gaps.
"""

import streamlit as st
import pandas as pd
from config import get_anthropic_key, has_anthropic_key
from utils.ui_helpers import shorten_url


def _normalize(text):
    """Normalize text for comparison: handle Swedish/Danish chars."""
    import unicodedata
    # Decompose unicode chars (ä → a + combining diaeresis), strip combining marks
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _text_contains_keyword(text, keyword):
    """Check if text contains keyword, handling ä/ö/å vs a/o/a."""
    # Direct match first
    if keyword.lower() in text.lower():
        return True
    # Normalized match (ä→a, ö→o, å→a)
    if _normalize(keyword) in _normalize(text):
        return True
    # Word-level match: all significant words present
    kw_words = set(_normalize(keyword).split())
    text_norm = _normalize(text)
    if kw_words and all(w in text_norm for w in kw_words if len(w) > 2):
        return True
    return False


def _build_page_plans(audit_results, gsc_data, topic_clusters):
    """Build a detailed implementation plan per page from ALL data sources."""
    plans = []

    df = gsc_data

    for r in audit_results:
        url = r.get("url", "")
        impressions = r.get("impressions", 0)
        lost_clicks = r.get("lost_clicks_estimate", 0)
        meta_score = r.get("meta_score")
        content_score = r.get("content_score")
        page_type = r.get("page_type", "unknown")
        target_keywords = r.get("target_keywords", [])
        content_audit = r.get("content_audit") or {}
        issues = r.get("issues", [])
        meta_eval = r.get("meta_eval") or {}

        # Determine the REAL primary keyword for this page
        # Strategy: URL slug is the most reliable signal for what the page is about
        # "mshop" appears in target_keywords for every page but is never the right primary
        from urllib.parse import urlparse as _up_pk
        slug = _up_pk(url).path.strip("/").split("/")[-1]
        slug_keyword = slug.replace("-", " ").replace("_", " ") if slug else ""

        # Build brand keywords set if needed
        if "_brand_keywords" not in st.session_state:
            try:
                if gsc_data is not None and hasattr(gsc_data, "groupby") and len(gsc_data) > 0:
                    total_pages = gsc_data["page"].nunique()
                    kw_page_counts = gsc_data.groupby("query")["page"].nunique()
                    st.session_state["_brand_keywords"] = set(kw_page_counts[kw_page_counts >= total_pages * 0.3].index)
            except Exception:
                st.session_state["_brand_keywords"] = set()
        brand_lower = {b.lower() for b in st.session_state.get("_brand_keywords", set())}

        # Primary keyword: first non-brand keyword that matches the URL slug topic
        primary_keyword = ""
        slug_words = set(slug_keyword.lower().split()) if slug_keyword else set()

        # First try: keyword that contains slug words (most relevant)
        for kw in target_keywords:
            if kw.lower() not in brand_lower and set(kw.lower().split()) & slug_words:
                primary_keyword = kw
                break
        # Second try: any non-brand keyword
        if not primary_keyword:
            for kw in target_keywords:
                if kw.lower() not in brand_lower:
                    primary_keyword = kw
                    break
        # Last resort: URL slug as keyword
        if not primary_keyword:
            primary_keyword = slug_keyword or (target_keywords[0] if target_keywords else "")

        steps = []
        total_time = 0  # minutes

        # ── STEP: Fix meta title ──────────────────────────────
        title = r.get("title") or ""
        title_len = r.get("title_length") or len(title)
        title_issues = [i for i in issues if isinstance(i, dict) and i.get("field") in ("title", "title_length")]

        if title_len > 60:
            steps.append({
                "action": "Shorten meta title",
                "time": 2,
                "detail": f"Current: \"{title}\" ({title_len} chars) — must be under 60 chars",
                "what_to_do": f"Open **{url}** in CMS → Edit SEO title → Shorten to max 60 chars. Keep primary keyword **{primary_keyword}** first.",
                "ai_type": "meta",
            })
            total_time += 2
        elif title_len < 30 and title_len > 0:
            steps.append({
                "action": "Extend meta title",
                "time": 2,
                "detail": f"Current: \"{title}\" ({title_len} chars) — too short, aim for 50-60 chars",
                "what_to_do": f"Open **{url}** in CMS → Edit SEO title → Add USP/benefit to reach 50-60 chars.",
                "ai_type": "meta",
            })
            total_time += 2

        # Title missing primary keyword
        if primary_keyword and title:
            if not _text_contains_keyword(title, primary_keyword):
                steps.append({
                    "action": f"Add primary keyword to title",
                    "time": 2,
                    "detail": f"Primary keyword **\"{primary_keyword}\"** is NOT in the title",
                    "what_to_do": f"Edit title to start with or contain **\"{primary_keyword}\"**. Current: \"{title}\"",
                    "ai_type": "meta",
                })
                total_time += 2

        # ── STEP: Fix meta description ────────────────────────
        desc = r.get("meta_description") or ""
        desc_len = r.get("description_length") or len(desc)

        if not desc or desc_len < 10:
            steps.append({
                "action": "Add meta description",
                "time": 3,
                "detail": "No meta description — Google will auto-generate one (usually bad)",
                "what_to_do": f"Open **{url}** in CMS → Add meta description with **{primary_keyword}**, 140-160 chars, include CTA.",
                "ai_type": "meta",
            })
            total_time += 3
        elif desc_len < 120:
            steps.append({
                "action": "Extend meta description",
                "time": 2,
                "detail": f"Only {desc_len} chars — extend to 140-160 for full SERP display",
                "what_to_do": f"Open **{url}** in CMS → Extend meta description to 140-160 chars. Add benefits, CTA, or USP.",
                "ai_type": "meta",
            })
            total_time += 2
        elif desc_len > 165:
            steps.append({
                "action": "Shorten meta description",
                "time": 2,
                "detail": f"Currently {desc_len} chars — Google truncates at ~160",
                "what_to_do": f"Open **{url}** in CMS → Shorten meta description to max 160 chars.",
                "ai_type": "meta",
            })
            total_time += 2

        # ── STEP: Fix H1 ─────────────────────────────────────
        h1 = r.get("h1") or ""
        kw_cov = content_audit.get("keyword_coverage") or {}

        # Check H1 ourselves with unicode-aware comparison (not just audit data)
        h1_has_keyword = _text_contains_keyword(h1, primary_keyword) if (h1 and primary_keyword) else False
        if not h1_has_keyword and primary_keyword:
            steps.append({
                "action": f"Add primary keyword to H1",
                "time": 2,
                "detail": f"H1 is \"{h1 or '(empty)'}\" — does NOT contain \"{primary_keyword}\"",
                "what_to_do": f"Open **{url}** in CMS → Change H1 to include **\"{primary_keyword}\"**. H1 should match search intent.",
                "ai_type": None,
            })
            total_time += 2

        # ── STEP: Add missing keywords ────────────────────────
        missing_kws_raw = kw_cov.get("missing", [])
        coverage_pct = kw_cov.get("coverage_pct", 100)

        # Filter missing keywords: only keep those RELEVANT to this page
        # Must match the page's SPECIFIC topic, not just share generic words
        from urllib.parse import urlparse as _urlparse
        page_path = _urlparse(url).path.lower().rstrip("/")

        # Use the LAST slug segment as the specific topic (what makes this page unique)
        # /sexleksaker-for-man → "sexleksaker for man" (all words needed together)
        last_slug = page_path.split("/")[-1] if "/" in page_path else page_path.lstrip("/")
        specific_words = set(last_slug.replace("-", " ").replace("_", " ").split())
        # Remove stop words that match everything
        stop_words = {"for", "och", "med", "till", "av", "i", "pa", "den", "det", "en", "ett", "and", "the", "of", "in", "to"}
        specific_words -= stop_words
        specific_words.discard("")

        # For pillar pages: also include child slug words
        child_slug_words = set()
        if topic_clusters:
            for other_url in topic_clusters.get("page_topics", {}).keys():
                other_path = _urlparse(other_url).path.lower().rstrip("/")
                if other_path != page_path and other_path.startswith(page_path + "/"):
                    child_part = other_path[len(page_path):].replace("-", " ").replace("/", " ")
                    child_slug_words.update(w for w in child_part.split() if w and w not in stop_words)

        def _is_relevant_keyword(kw):
            kw_lower = kw.lower()
            kw_words = set(kw_lower.split()) - stop_words

            if not kw_words:
                return False

            # Must share a SPECIFIC word with the page slug (not just generic "sexleksaker")
            # For /sexleksaker-for-man: keyword must contain "man" or "män" or "honom"
            # The _normalize function handles ä→a, ö→o
            slug_specific = {_normalize(w) for w in specific_words if len(w) > 2}
            kw_normalized = {_normalize(w) for w in kw_words if len(w) > 2}

            if slug_specific and kw_normalized & slug_specific:
                return True

            # Pillar page: matches child page slugs?
            if child_slug_words:
                child_normalized = {_normalize(w) for w in child_slug_words if len(w) > 2}
                if kw_normalized & child_normalized:
                    return True

            # Matches primary keyword's specific words?
            if primary_keyword:
                pk_words = {_normalize(w) for w in primary_keyword.lower().split() if len(w) > 2} - {_normalize(w) for w in stop_words}
                # Must share a DISTINGUISHING word (not "sexleksaker" which is everywhere)
                # Use the last word of primary keyword as most specific
                pk_last = _normalize(primary_keyword.lower().split()[-1]) if primary_keyword else ""
                if pk_last and len(pk_last) > 2 and pk_last in " ".join(kw_normalized):
                    return True

            return False

        missing_kws = [kw for kw in missing_kws_raw if _is_relevant_keyword(kw)]

        if missing_kws:
            kw_list = ", ".join(missing_kws[:8])
            remaining = len(missing_kws) - 8 if len(missing_kws) > 8 else 0
            steps.append({
                "action": f"Add {len(missing_kws)} missing keywords to page text",
                "time": 30,
                "detail": f"Coverage: {coverage_pct:.0f}% — missing: **{kw_list}**{f' (+{remaining} more)' if remaining else ''}",
                "what_to_do": (
                    f"Open **{url}** in CMS. Integrate these keywords naturally into existing text or new paragraphs. "
                    f"Don't keyword-stuff — write for the customer first. "
                    f"Focus on intro paragraph and H2 sections."
                ),
                "ai_type": "keywords",
                "missing_keywords": missing_kws,
            })
            total_time += 30

        # ── STEP: Add missing topic sections ──────────────────
        topic_cov = content_audit.get("topic_coverage") or {}
        missing_subtopics = [
            s for s in (topic_cov.get("subtopics") or [])
            if s.get("status") in ("missing", "partial")
        ]

        if missing_subtopics:
            topic_names = [s["topic"] for s in missing_subtopics]
            steps.append({
                "action": f"Add {len(missing_subtopics)} missing topic sections",
                "time": 45,
                "detail": "Missing H2 sections for: **" + "**, **".join(topic_names[:5]) + "**",
                "what_to_do": (
                    f"Open **{url}** in CMS. Add a new H2 section for each missing topic. "
                    f"Each section should be 80-150 words. "
                    f"Use the topic name as H2 heading."
                ),
                "ai_type": "keywords",
                "missing_keywords": [q for s in missing_subtopics for q in s.get("queries", [])[:3]],
                "subtopics": topic_names,
            })
            total_time += 45

        # ── STEP: Fix internal links ──────────────────────────
        linking = content_audit.get("linking") or {}
        link_fixes = linking.get("link_fix_suggestions") or []
        missing_crosslinks = linking.get("missing_crosslinks") or []

        # Also check topic cluster overlap — but filter out junk topics
        if topic_clusters:
            page_topics = topic_clusters.get("page_topics", {})

            # Filter junk topics (appear on 30%+ of pages = brand/generic)
            _topic_counts = {}
            for _url_t, _tlist in page_topics.items():
                for _t in _tlist:
                    _tn = _t.get("topic", "")
                    _topic_counts[_tn] = _topic_counts.get(_tn, 0) + 1
            _total = len(page_topics)
            _junk = {tn for tn, c in _topic_counts.items() if c >= _total * 0.3}

            my_topics = set(t.get("topic", "") for t in page_topics.get(url, [])) - _junk

            # Find pages we share topics with but don't link to
            linked_urls = set()
            internal_links = r.get("internal_links", [])
            if isinstance(internal_links, list):
                for l in internal_links:
                    u = l.get("url", "")
                    linked_urls.add(u.rstrip("/").lower())

            sf_link_map = st.session_state.get("sf_link_map")
            if sf_link_map:
                for sl in sf_link_map.get("links_from", {}).get(url, []):
                    linked_urls.add(sl.get("target", "").rstrip("/").lower())

            cluster_links = []
            # Only suggest links to pages in the SAME URL hierarchy or closely related
            from urllib.parse import urlparse as _up3
            my_path_parts = _up3(url).path.lower().strip("/").split("/")

            for other_url, other_topics in page_topics.items():
                if other_url.rstrip("/").lower() == url.rstrip("/").lower():
                    continue
                other_names = set(t.get("topic", "") for t in other_topics) - _junk
                shared = my_topics & other_names
                if not shared or other_url.rstrip("/").lower() in linked_urls:
                    continue

                # Filter: only suggest links to RELATED pages, not random pages
                other_path_parts = _up3(other_url).path.lower().strip("/").split("/")
                # Related if: same parent path, or sibling, or parent/child
                is_sibling = (len(my_path_parts) >= 2 and len(other_path_parts) >= 2
                              and my_path_parts[0] == other_path_parts[0])
                is_parent_child = (
                    other_url.rstrip("/").lower().startswith(url.rstrip("/").lower() + "/") or
                    url.rstrip("/").lower().startswith(other_url.rstrip("/").lower() + "/")
                )
                if not is_sibling and not is_parent_child:
                    continue

                # Generate a NATURAL anchor text from the target page's URL slug
                target_slug = other_path_parts[-1] if other_path_parts else ""
                natural_anchor = target_slug.replace("-", " ").replace("_", " ")
                if not natural_anchor or natural_anchor == "/":
                    natural_anchor = other_url.split("/")[-2] if "/" in other_url else "related page"

                cluster_links.append({
                    "target": other_url,
                    "shared_topics": list(shared)[:3],
                    "anchor": natural_anchor,
                })
            cluster_links.sort(key=lambda x: -len(x["shared_topics"]))
            cluster_links = cluster_links[:5]
        else:
            cluster_links = []

        all_link_actions = []
        for fix in link_fixes:
            all_link_actions.append(f"Add link to `{fix.get('target_url','')}` with anchor **\"{fix.get('suggested_anchor','')}\"** in {fix.get('placement','page text')}")
        for cl in cluster_links:
            all_link_actions.append(f"Add link to `{cl['target']}` with anchor **\"{cl['anchor']}\"** (shared topics: {', '.join(cl['shared_topics'])})")

        if all_link_actions:
            link_detail = "\n".join([f"  → {la}" for la in all_link_actions[:8]])
            steps.append({
                "action": f"Add {len(all_link_actions)} internal links",
                "time": 10,
                "detail": f"Missing links to related pages:\n{link_detail}",
                "what_to_do": (
                    f"Open **{url}** in CMS. Add each link in a natural context — "
                    f"intro, bottom text, or a relevant H2 section. "
                    f"Use the suggested anchor text, not 'click here'."
                ),
                "ai_type": "links",
                "link_actions": all_link_actions,
            })
            total_time += 10

        # ── STEP: Content quality ─────────────────────────────
        word_count = r.get("word_count", 0)
        if word_count and word_count < 100 and page_type != "product":
            steps.append({
                "action": "Add content — page is too thin",
                "time": 60,
                "detail": f"Only {word_count} words — Google considers this thin content. Aim for 300+ words for categories, 500+ for guides.",
                "what_to_do": f"Open **{url}** in CMS. Add intro text, buying guide, FAQ, or descriptive sections.",
                "ai_type": "keywords",
            })
            total_time += 60

        # ── STEP: Add FAQ schema ──────────────────────────────
        has_faq = r.get("has_faq", False) or (content_audit.get("content_stats") or {}).get("has_faq", False)
        if not has_faq and page_type in ("category", "blog"):
            steps.append({
                "action": "Add FAQ section with schema",
                "time": 20,
                "detail": "No FAQ found — FAQ schema can earn rich results in Google (extra visibility)",
                "what_to_do": f"Open **{url}** in CMS. Add 3-5 FAQ questions targeting missing subtopics. Add FAQPage schema markup.",
                "ai_type": "faq",
            })
            total_time += 20

        # ── STEP: Add missing schema markup ───────────────────
        schema_types = r.get("schema_types", [])
        missing_schemas = []
        if "BreadcrumbList" not in schema_types:
            missing_schemas.append("BreadcrumbList")
        if page_type in ("category", "blog") and "FAQPage" not in schema_types and has_faq:
            missing_schemas.append("FAQPage")
        trust = content_audit.get("trust") or {}
        if not trust.get("has_org_schema", False) and url.rstrip("/").count("/") <= 3:
            missing_schemas.append("Organization")

        if missing_schemas:
            steps.append({
                "action": f"Add schema markup: {', '.join(missing_schemas)}",
                "time": 10,
                "detail": f"Missing structured data: **{', '.join(missing_schemas)}**. Schema helps Google show rich results (FAQ dropdowns, breadcrumbs in SERP).",
                "what_to_do": (
                    f"Add JSON-LD `<script>` tags to `<head>` of **{url}**. "
                    f"Click the button below to generate the exact code."
                ),
                "ai_type": "schema",
                "missing_schemas": missing_schemas,
            })
            total_time += 10

        # ── STEP: Spoke → Hub link ────────────────────────────
        # Check if this page links back to its parent/hub page
        from urllib.parse import urlparse as _up2
        page_path = _up2(url).path.lower().rstrip("/")
        path_parts = page_path.strip("/").split("/")
        if len(path_parts) >= 2:
            parent_path = "/" + "/".join(path_parts[:-1])
            # Check if we link to parent
            linked_paths = set()
            il = r.get("internal_links", [])
            if isinstance(il, list):
                for l in il:
                    linked_paths.add(_up2(l.get("url", "")).path.lower().rstrip("/"))
            sf_lm = st.session_state.get("sf_link_map")
            if sf_lm:
                for sl in sf_lm.get("links_from", {}).get(url, []):
                    linked_paths.add(_up2(sl.get("target", "")).path.lower().rstrip("/"))

            if parent_path not in linked_paths and parent_path != "":
                # Find parent URL
                parent_url = url[:url.lower().find(path_parts[-1])].rstrip("/")
                steps.append({
                    "action": f"Add link back to hub page {parent_path}",
                    "time": 5,
                    "detail": f"This spoke page does NOT link back to its hub/pillar **{parent_path}**. Google requires bidirectional hub↔spoke links for topic authority.",
                    "what_to_do": (
                        f"Open **{url}** in CMS. Add a link to **{parent_url or parent_path}** "
                        f"in the intro or bottom text. Use descriptive anchor text like the hub page's main topic."
                    ),
                    "ai_type": "links",
                    "link_actions": [f"Add link to `{parent_url or parent_path}` with anchor **\"{path_parts[-2].replace('-', ' ')}\"**"],
                })
                total_time += 5

        if not steps:
            continue

        plans.append({
            "url": url,
            "page_type": page_type,
            "impressions": impressions,
            "lost_clicks": lost_clicks,
            "meta_score": meta_score,
            "content_score": content_score,
            "steps": steps,
            "total_time": total_time,
            "target_keywords": target_keywords,
            "primary_keyword": primary_keyword,
            "body_text_snippet": (r.get("body_text") or r.get("intro_text") or "")[:800],
        })

    # Sort by lost clicks descending
    plans.sort(key=lambda p: -p["lost_clicks"])
    return plans


def render():
    st.markdown("## Implementation Guide")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1.5rem;'>"
        "Step-by-step instructions for every page. Work from the top — highest impact first. "
        "Click AI buttons to generate the exact text to paste into your CMS.</p>",
        unsafe_allow_html=True,
    )

    has_audit = "audit_results" in st.session_state and st.session_state["audit_results"]
    has_gaps = "ctr_gaps" in st.session_state
    gsc_data = st.session_state.get("gsc_data")

    if not has_audit:
        st.warning("Run **6. Page Auditor** first (bulk audit recommended for full picture)")
        if has_gaps:
            _show_ctr_only_plan()
        return

    audit_results = st.session_state["audit_results"]
    topic_clusters = st.session_state.get("topic_clusters", {})
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")

    # Cache plans in session state — only rebuild when audit changes
    # v3 = cache version bump to force rebuild after brand keyword + link fixes
    cache_key = f"_impl_plans_v6_{len(audit_results)}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = _build_page_plans(audit_results, gsc_data, topic_clusters)
    plans = st.session_state[cache_key]

    if not plans:
        st.success("All audited pages look good — no issues found!")
        return

    # ── Summary ───────────────────────────────────────────────────
    total_lost = sum(p["lost_clicks"] for p in plans)
    total_steps = sum(len(p["steps"]) for p in plans)
    total_time = sum(p["total_time"] for p in plans)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pages to fix", len(plans))
    c2.metric("Total steps", total_steps)
    c3.metric("Est. time", f"{total_time // 60}h {total_time % 60}m")
    c4.metric("Lost clicks recoverable", f"{total_lost:,.0f}")

    st.markdown("---")

    # ── Pagination ────────────────────────────────────────────────
    PAGES_PER_VIEW = 10
    total_pages_count = len(plans)
    max_page = max(1, (total_pages_count + PAGES_PER_VIEW - 1) // PAGES_PER_VIEW)
    current_page = st.number_input("Page", min_value=1, max_value=max_page, value=1, key="impl_page")
    start = (current_page - 1) * PAGES_PER_VIEW
    visible_plans = plans[start:start + PAGES_PER_VIEW]

    st.markdown(f"**Showing pages {start+1}-{min(start+PAGES_PER_VIEW, total_pages_count)} of {total_pages_count}**")

    # ── Page cards ────────────────────────────────────────────────
    for plan_idx, plan in enumerate(visible_plans):
        url = plan["url"]
        ptype = plan["page_type"].upper()
        lost = plan["lost_clicks"]
        impr = plan["impressions"]
        meta_s = plan["meta_score"]
        content_s = plan["content_score"]
        n_steps = len(plan["steps"])
        est_time = plan["total_time"]

        # Determine card border color
        if lost > 1000:
            border = "#ff4455"
        elif lost > 200:
            border = "#ffaa33"
        else:
            border = "#2a2a40"

        # Card header
        st.markdown(
            f"<div style='background:#12121f; border:1px solid {border}; border-left:4px solid {border}; "
            f"border-radius:6px; padding:1rem; margin-bottom:0.3rem;'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;'>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:{border}; "
            f"text-transform:uppercase;'>{ptype} · {n_steps} steps · ~{est_time} min</span>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#6b6b8a;'>"
            f"{impr:,} impr · {lost:,.0f} lost clicks</span>"
            f"</div>"
            f"<div style='font-size:1rem; color:#e8e8f0; font-weight:600;'>{url}</div>"
            f"<div style='font-size:0.72rem; color:#6b6b8a; margin-top:0.2rem;'>"
            f"Meta: {meta_s if meta_s is not None else '?'}/100 · Content: {content_s if content_s is not None else '?'}/100 · "
            f"Primary KW: {plan.get('primary_keyword', plan['target_keywords'][0] if plan['target_keywords'] else '?')}"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        url_hash = hash(url) & 0xFFFFFF

        with st.expander(f"Open implementation plan for {shorten_url(url)}", expanded=(plan_idx == 0)):

            for step_idx, step in enumerate(plan["steps"], 1):
                time_str = f"{step['time']} min" if step['time'] < 60 else f"{step['time'] // 60}h {step['time'] % 60}m"

                # Step card
                st.markdown(
                    f"<div style='background:#0d0d15; border-left:3px solid #5533ff; padding:0.7rem 1rem; "
                    f"border-radius:0 6px 6px 0; margin-bottom:0.6rem;'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.3rem;'>"
                    f"<span style='color:#5533ff; font-weight:700; font-size:0.95rem;'>Step {step_idx}: {step['action']}</span>"
                    f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#6b6b8a;'>~{time_str}</span>"
                    f"</div>"
                    f"<div style='font-size:0.82rem; color:#9b9bb8; margin-bottom:0.4rem;'>{step['detail']}</div>"
                    f"<div style='font-size:0.85rem; color:#c8b4ff; line-height:1.5;'>{step['what_to_do']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # AI buttons per step type
                ai_type = step.get("ai_type")
                result_key = f"impl_{url_hash}_{step_idx}"

                if ai_type == "meta" and has_anthropic_key():
                    if st.button(f"AI: Generate meta for this page", key=f"btn_impl_meta_{url_hash}_{step_idx}"):
                        with st.spinner("Generating meta..."):
                            try:
                                from utils.ai_generator import get_client, generate_meta_suggestions
                                client = get_client(get_anthropic_key())
                                page_data = dict(
                                    url=url, title=plan.get("title", ""),
                                    meta_description=plan.get("meta_description", ""),
                                    h1=plan.get("h1", ""), page_type=plan["page_type"],
                                )
                                # Find page_data from audit
                                for ar in audit_results:
                                    if ar["url"] == url:
                                        page_data = ar
                                        break
                                result = generate_meta_suggestions(
                                    client, page_data, plan["target_keywords"],
                                    site_context, language, 2,
                                )
                                st.session_state[result_key] = result
                            except Exception as e:
                                st.error(f"Error: {e}")

                elif ai_type == "keywords" and has_anthropic_key():
                    if st.button(f"AI: Generate text with keywords", key=f"btn_impl_kw_{url_hash}_{step_idx}"):
                        with st.spinner("Generating keyword-optimized text..."):
                            try:
                                from utils.ai_generator import get_client, generate_keyword_text
                                client = get_client(get_anthropic_key())
                                missing = step.get("missing_keywords", plan.get("target_keywords", []))
                                result = generate_keyword_text(
                                    client, missing, plan["body_text_snippet"],
                                    plan["page_type"], site_context, language,
                                )
                                st.session_state[result_key] = result
                            except Exception as e:
                                st.error(f"Error: {e}")

                elif ai_type == "links" and has_anthropic_key():
                    if st.button(f"AI: Generate link paragraphs", key=f"btn_impl_link_{url_hash}_{step_idx}"):
                        with st.spinner("Generating link text..."):
                            try:
                                from utils.ai_generator import get_client, generate_link_text
                                client = get_client(get_anthropic_key())
                                # Generate for first link action
                                link_actions = step.get("link_actions", [])
                                results = []
                                for la in link_actions[:3]:
                                    # Extract target URL from action text
                                    import re
                                    target_match = re.search(r'`([^`]+)`', la)
                                    anchor_match = re.search(r'\*\*"([^"]+)"\*\*', la)
                                    if target_match and anchor_match:
                                        r = generate_link_text(
                                            client, url, target_match.group(1),
                                            anchor_match.group(1), "page text",
                                            plan["target_keywords"], site_context, language,
                                        )
                                        results.append(r)
                                st.session_state[result_key] = results
                            except Exception as e:
                                st.error(f"Error: {e}")

                elif ai_type == "schema":
                    if st.button(f"Generate schema markup", key=f"btn_impl_schema_{url_hash}_{step_idx}"):
                        try:
                            from utils.ai_generator import generate_schema_markup
                            # Find page data
                            page_r = next((ar for ar in audit_results if ar["url"] == url), {})
                            faq_items_for_schema = None
                            # Check if we have generated FAQ in session
                            for sk, sv in st.session_state.items():
                                if sk.startswith(f"impl_{url_hash}_") and isinstance(sv, dict) and "faq_items" in sv:
                                    faq_items_for_schema = sv["faq_items"]
                                    break

                            result = generate_schema_markup(
                                page_type=plan["page_type"],
                                url=url,
                                title=page_r.get("title", ""),
                                description=page_r.get("meta_description", ""),
                                h1=page_r.get("h1", ""),
                                faq_items=faq_items_for_schema,
                                site_name=st.session_state.get("site_context", ""),
                                site_url=st.session_state.get("gsc_site", ""),
                            )
                            st.session_state[result_key] = result
                        except Exception as e:
                            st.error(f"Error: {e}")

                elif ai_type == "faq" and has_anthropic_key():
                    if st.button(f"AI: Generate FAQ section", key=f"btn_impl_faq_{url_hash}_{step_idx}"):
                        with st.spinner("Generating FAQ..."):
                            try:
                                from utils.ai_generator import get_client, generate_keyword_faq
                                client = get_client(get_anthropic_key())
                                subtopics = step.get("subtopics", plan["target_keywords"][:5])
                                result = generate_keyword_faq(
                                    client, subtopics, plan["target_keywords"],
                                    site_context, language,
                                )
                                st.session_state[result_key] = result
                            except Exception as e:
                                st.error(f"Error: {e}")

                # Display AI results
                if result_key in st.session_state:
                    res = st.session_state[result_key]
                    st.markdown(
                        "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#33dd88; "
                        "margin:0.3rem 0;'>COPY THIS INTO YOUR CMS</div>",
                        unsafe_allow_html=True,
                    )

                    if ai_type == "meta" and isinstance(res, dict):
                        for i, v in enumerate(res.get("variants", []), 1):
                            st.markdown(f"**Variant {i}:**")
                            st.code(f"Title: {v.get('title','')}\nDescription: {v.get('description','')}", language="text")

                    elif ai_type == "keywords" and isinstance(res, dict):
                        st.markdown(
                            f"<div style='background:#0d1a0d; border-left:3px solid #33dd88; padding:0.6rem; "
                            f"border-radius:0 4px 4px 0;'>{res.get('optimized_text', '')}</div>",
                            unsafe_allow_html=True,
                        )
                        st.code(res.get("optimized_text", ""), language="text")

                    elif ai_type == "links" and isinstance(res, list):
                        for lr in res:
                            st.markdown(
                                f"<div style='background:#0d1a0d; border-left:3px solid #33dd88; padding:0.6rem; "
                                f"border-radius:0 4px 4px 0; margin-bottom:0.3rem;'>{lr.get('paragraph', '')}</div>",
                                unsafe_allow_html=True,
                            )
                            st.code(lr.get("html", ""), language="html")

                    elif ai_type == "schema" and isinstance(res, dict):
                        st.markdown(f"**Schema types:** {', '.join(res.get('types', []))}")
                        st.code(res.get("json_ld", ""), language="html")

                    elif ai_type == "faq" and isinstance(res, dict):
                        faq_text = ""
                        for faq in res.get("faq_items", []):
                            st.markdown(f"**Q: {faq.get('question', '')}**")
                            st.markdown(faq.get("answer", ""))
                            faq_text += f"Q: {faq.get('question','')}\nA: {faq.get('answer','')}\n\n"
                        st.code(faq_text, language="text")

    # ── Download full plan ────────────────────────────────────────
    st.markdown("---")
    export = []
    for plan in plans:
        for step in plan["steps"]:
            export.append({
                "url": plan["url"],
                "page_type": plan["page_type"],
                "lost_clicks": plan["lost_clicks"],
                "step": step["action"],
                "time_minutes": step["time"],
                "detail": step["detail"],
                "what_to_do": step["what_to_do"],
            })

    import json
    st.download_button(
        "Download full implementation plan (JSON)",
        json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8"),
        "implementation_plan.json",
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
