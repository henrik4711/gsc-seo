"""
Site Cleanup — Site-wide actions: pages to delete, merge, redirect, noindex.
Different from Quick Wins which is per-page improvements.
"""

import streamlit as st
from utils.ui_helpers import normalize_url, stable_hash, shorten_url


def _pages_to_merge():
    """Combined from cannibalization + ideal structure + gap analysis."""
    merges = []
    seen_pairs = set()

    # Source 1: Ideal structure (AI-generated merges)
    ideal = st.session_state.get("_ideal_structure") or {}
    if isinstance(ideal, dict):
        for m in ideal.get("merge", []) or []:
            if not isinstance(m, dict):
                continue
            from_urls = m.get("from", [])
            to_url = m.get("to", "")
            why = m.get("why", "")
            if not to_url or not from_urls:
                continue
            for from_url in from_urls:
                pair = tuple(sorted([normalize_url(to_url), normalize_url(from_url)]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                merges.append({
                    "keep": to_url,
                    "redirect": from_url,
                    "query": "(ideal structure recommendation)",
                    "lost_clicks": 0,
                    "severity": "ai-recommended",
                    "reason": why,
                    "source": "ideal_structure",
                })

    # Source 2: Cannibalization data
    cannibal_df = st.session_state.get("cannibalization")
    if cannibal_df is None or cannibal_df.empty:
        return merges

    for _, row in cannibal_df.iterrows():
        if row.get("severity") not in ("severe", "moderate"):
            continue
        winner = row.get("recommended_winner", "")
        merge_action = row.get("merge_action", "")

        # Skip "different intent" cases — these should NOT merge
        if "DIFFERENT INTENTS" in merge_action or "Don't merge" in merge_action:
            continue
        if "Homepage involved" in merge_action:
            continue

        pages_detail = row.get("pages_detail", [])
        if not isinstance(pages_detail, list) or len(pages_detail) < 2:
            continue

        losers = [p["page"] for p in pages_detail if normalize_url(p.get("page", "")) != normalize_url(winner)]
        for loser in losers:
            pair = tuple(sorted([normalize_url(winner), normalize_url(loser)]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            merges.append({
                "keep": winner,
                "redirect": loser,
                "query": row["query"],
                "lost_clicks": row["lost_clicks_estimate"],
                "severity": row["severity"],
            })
    return merges[:50]


def _pages_to_create():
    """NEW pages to create — from ideal structure + content roadmap + page-level plans."""
    creates = []
    seen = set()

    # Source 1: Ideal structure
    ideal = st.session_state.get("_ideal_structure") or {}
    if isinstance(ideal, dict):
        for c in ideal.get("create", []) or []:
            if not isinstance(c, dict):
                continue
            url = c.get("url", "")
            if url in seen:
                continue
            seen.add(url)
            creates.append({
                "url": url,
                "type": c.get("type", "page"),
                "keyword": c.get("kw", ""),
                "why": c.get("why", ""),
                "source": "ideal_structure",
            })

    # Source 2: Content roadmap (from topic_clusters)
    roadmap = st.session_state.get("content_roadmap", {})
    if isinstance(roadmap, dict):
        for a in roadmap.get("new_articles", []) or []:
            if not isinstance(a, dict):
                continue
            title = a.get("suggested_title", "")
            if title in seen:
                continue
            seen.add(title)
            creates.append({
                "url": f"(new article: {title})",
                "type": a.get("type", "blog"),
                "keyword": ", ".join(a.get("target_keywords", [])[:3]),
                "why": a.get("why", ""),
                "source": "content_roadmap",
                "priority": a.get("priority", ""),
            })

    # Source 3: Per-page plans (collected from all AI plans)
    for key, val in st.session_state.items():
        if not key.startswith("_ai_plan_") or not isinstance(val, dict):
            continue
        for nc in val.get("new_content_suggestions", []) or []:
            if not isinstance(nc, dict):
                continue
            title = nc.get("suggested_title", "")
            if not title or title in seen:
                continue
            seen.add(title)
            creates.append({
                "url": f"(new article: {title})",
                "type": nc.get("type", "blog"),
                "keyword": ", ".join(nc.get("target_keywords", [])[:3]),
                "why": nc.get("why", ""),
                "source": "page_plan",
                "link_from": nc.get("link_from", ""),
            })

    return creates[:100]


def _pages_to_delete_ideal():
    """Pages to delete from ideal structure."""
    ideal = st.session_state.get("_ideal_structure") or {}
    if not isinstance(ideal, dict):
        return []
    deletes = []
    for d in ideal.get("delete", []) or []:
        if not isinstance(d, dict):
            continue
        deletes.append({
            "url": d.get("url", ""),
            "why": d.get("why", ""),
            "source": "ideal_structure",
        })
    return deletes


def _pages_to_redirect():
    """Broken pages (4xx) that have backlinks — should be redirected to similar page."""
    issues = st.session_state.get("sf_crawl_issues", {})
    broken = issues.get("broken_links", [])
    page_authority = st.session_state.get("page_authority")

    redirects = []
    for b in broken:
        url = b.get("url", "")
        rd = 0
        if page_authority is not None and not page_authority.empty:
            match = page_authority[page_authority["page"].apply(normalize_url) == normalize_url(url)]
            if not match.empty:
                rd = int(match.iloc[0].get("referring_domains", 0))
        redirects.append({
            "url": url,
            "status": b.get("status_code", 404),
            "referring_domains": rd,
            "action": "Redirect to closest matching page (preserve any backlinks)" if rd > 0 else "Delete or redirect",
        })
    redirects.sort(key=lambda x: -x["referring_domains"])
    return redirects


def _pages_to_noindex():
    """Pages that should be noindexed: faceted URLs, thin pages, near-duplicates."""
    issues = st.session_state.get("sf_crawl_issues", {})

    noindex_candidates = []

    # Faceted URLs (Magento parameters)
    faceted = issues.get("faceted_urls", [])
    for f in faceted[:50]:
        noindex_candidates.append({
            "url": f.get("url", ""),
            "reason": "Faceted/parameter URL — wastes crawl budget",
            "type": "faceted",
        })

    # Thin pages
    thin = issues.get("thin_pages", [])
    for t in thin[:30]:
        noindex_candidates.append({
            "url": t.get("url", ""),
            "reason": f"Thin content ({t.get('word_count', 0)} words)",
            "type": "thin",
        })

    # Near-duplicates (only the duplicate, not the original)
    near_dupes = issues.get("near_duplicates", [])
    for d in near_dupes[:30]:
        noindex_candidates.append({
            "url": d.get("url", ""),
            "reason": f"Near-duplicate of {d.get('closest_match', '')}",
            "type": "duplicate",
        })

    return noindex_candidates


def _generate_cannibal_subcategory_meta(query: str, pages: list, row, ai_key: str):
    """
    Generate differentiated meta titles + descriptions for each page in a
    sub-category/brand-variant cannibalization conflict.
    Uses the existing generate_meta_suggestions() AI function.
    """
    from config import get_anthropic_key, has_anthropic_key
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    from utils.ai_generator import get_client, generate_meta_suggestions
    from utils.persistence import save

    client = get_client(get_anthropic_key())
    audit_results = st.session_state.get("audit_results", [])
    audit_by_url = {normalize_url(r.get("url", "")): r for r in audit_results}

    results = {}
    for p in pages:
        page_url = p.get("page", "")
        page_norm = normalize_url(page_url)
        audit = audit_by_url.get(page_norm, {})
        if not audit:
            # Minimal fallback if no audit data
            audit = {"url": page_url, "title": "", "h1": "", "h2s": [],
                     "word_count": 0, "page_type": "category"}

        # Extract path segments to suggest variant-specific keywords
        from urllib.parse import urlparse
        path = urlparse(page_url).path.rstrip("/")
        last_segment = path.split("/")[-1] if path else ""
        variant_kw = last_segment.replace("-", " ") if last_segment else ""

        # Build target keywords: generic query + variant-specific
        target_kws = [query]
        if variant_kw and variant_kw != query:
            target_kws.append(f"{variant_kw} {query}")
            target_kws.append(f"{query} {variant_kw}")

        try:
            meta_result = generate_meta_suggestions(
                client=client,
                page_data=audit,
                target_keywords=target_kws,
                site_context=st.session_state.get("site_context", ""),
                language=st.session_state.get("content_language", "Swedish"),
                n_variants=2,
            )
            results[page_url] = meta_result
        except Exception as e:
            results[page_url] = {"error": str(e), "variants": []}

    st.session_state[ai_key] = results
    save(ai_key)


def _validate_subcategory_quality(parent_url: str, child_pages: list):
    """
    For a sub-category split, check:
    1. Does the parent page link to each child?
    2. Are child titles differentiated from parent title?
    3. Is child content a near-duplicate of parent?
    Returns dict of issues.
    """
    audit_results = st.session_state.get("audit_results", [])
    audit_by_url = {normalize_url(r.get("url", "")): r for r in audit_results}
    sf_link_map = st.session_state.get("sf_link_map") or {}
    links_to = sf_link_map.get("links_to") if isinstance(sf_link_map, dict) else {}

    parent_norm = normalize_url(parent_url)
    parent_audit = audit_by_url.get(parent_norm, {})
    parent_title = (parent_audit.get("title") or "").lower().strip()
    parent_h1 = (parent_audit.get("h1") or "").lower().strip()
    parent_word_count = parent_audit.get("word_count", 0)

    issues = []

    # Check which child pages have an incoming link from the parent
    parent_outbound = set()
    if isinstance(links_to, dict):
        # links_to maps a page -> set of pages that link TO it
        # To get parent's outbound links, check each child's incoming set
        pass

    # Alternative: walk audit's internal_links for parent (if stored)
    parent_internal_links = parent_audit.get("internal_links") or []
    if isinstance(parent_internal_links, list):
        parent_outbound = {normalize_url(l) if isinstance(l, str) else normalize_url(l.get("url", "")) for l in parent_internal_links}
    parent_outbound.discard("")

    for child in child_pages:
        child_url = child.get("page", "") if isinstance(child, dict) else child
        child_norm = normalize_url(child_url)
        if child_norm == parent_norm:
            continue  # skip self
        child_audit = audit_by_url.get(child_norm, {})
        child_title = (child_audit.get("title") or "").lower().strip()
        child_h1 = (child_audit.get("h1") or "").lower().strip()
        child_wc = child_audit.get("word_count", 0)

        # Check 1: does parent link to child?
        has_link = child_norm in parent_outbound
        if not has_link:
            issues.append({
                "page": child_url,
                "severity": "high",
                "issue": f"Parent `{parent_url}` does NOT link to this sub-category",
                "fix": f"Add internal link from parent category to this sub-category",
            })

        # Check 2: title differentiated?
        if parent_title and child_title and parent_title == child_title:
            issues.append({
                "page": child_url,
                "severity": "high",
                "issue": "Title is IDENTICAL to parent category",
                "fix": "Rewrite title to include the sub-category variant term",
            })
        elif parent_title and child_title:
            # Same base: if child title only differs by 1-2 words it's near-dupe
            parent_words = set(parent_title.split())
            child_words = set(child_title.split())
            overlap = len(parent_words & child_words)
            if overlap >= len(parent_words) - 1 and overlap >= len(child_words) - 1:
                issues.append({
                    "page": child_url,
                    "severity": "medium",
                    "issue": "Title is nearly identical to parent — no variant differentiation",
                    "fix": "Rewrite to emphasize the sub-category variant",
                })

        # Check 3: content near-duplicate by word count similarity
        if parent_word_count > 100 and child_wc > 100:
            ratio = min(parent_word_count, child_wc) / max(parent_word_count, child_wc)
            if ratio > 0.9 and parent_h1 == child_h1:
                issues.append({
                    "page": child_url,
                    "severity": "medium",
                    "issue": f"Content size ({child_wc}w) near identical to parent ({parent_word_count}w) AND same H1 — suspected duplicate",
                    "fix": "Rewrite body to focus specifically on the variant",
                })

        # Check 4: child has very thin content
        if child_wc < 100:
            issues.append({
                "page": child_url,
                "severity": "high",
                "issue": f"Sub-category has thin content ({child_wc} words)",
                "fix": "Add editorial text specific to this variant (aim 300+ words)",
            })

    return issues


def _classify_orphans():
    """
    Cross-reference orphan list with traffic + backlinks + clusters.
    Returns dict with 4 buckets: delete, reconnect, redirect, investigate.

    - DELETE: orphan AND 0 traffic AND 0 backlinks AND not in any cluster
    - RECONNECT: orphan BUT has traffic OR is part of a topic cluster
    - REDIRECT: orphan AND 0 traffic BUT has backlinks (preserve link equity)
    - INVESTIGATE: anything that doesn't fit cleanly
    """
    sf_issues = st.session_state.get("sf_crawl_issues") or {}
    orphan_list = sf_issues.get("orphan_pages") or []
    if not orphan_list:
        return {"delete": [], "reconnect": [], "redirect": [], "investigate": []}

    audit_results = st.session_state.get("audit_results", [])
    audit_by_url = {normalize_url(r.get("url", "")): r for r in audit_results}

    page_authority = st.session_state.get("page_authority")
    auth_lookup = {}
    if page_authority is not None and not page_authority.empty:
        for _, row in page_authority.iterrows():
            auth_lookup[normalize_url(str(row.get("page", "")))] = int(row.get("referring_domains", 0))

    topic_clusters = st.session_state.get("topic_clusters", {})
    clustered_urls = set()
    if isinstance(topic_clusters, dict):
        for k in (topic_clusters.get("page_topics") or {}).keys():
            clustered_urls.add(normalize_url(k))

    gsc_data = st.session_state.get("gsc_data")
    gsc_pages = {}
    if gsc_data is not None and hasattr(gsc_data, "groupby") and not gsc_data.empty:
        for page, grp in gsc_data.groupby("page"):
            gsc_pages[normalize_url(str(page))] = {
                "impressions": int(grp["impressions"].sum()),
                "clicks": int(grp["clicks"].sum()),
            }

    buckets = {"delete": [], "reconnect": [], "redirect": [], "investigate": [], "needs_content": []}

    for o in orphan_list:
        url = o.get("url") if isinstance(o, dict) else o
        if not url:
            continue
        norm = normalize_url(url)
        audit = audit_by_url.get(norm) or {}
        rd = auth_lookup.get(norm, 0)
        gsc = gsc_pages.get(norm, {"impressions": 0, "clicks": 0})
        in_cluster = norm in clustered_urls
        word_count = audit.get("word_count", 0)
        page_type = audit.get("page_type", "unknown")

        signals = {
            "url": url,
            "impressions": gsc["impressions"],
            "clicks": gsc["clicks"],
            "referring_domains": rd,
            "in_cluster": in_cluster,
            "word_count": word_count,
            "page_type": page_type,
        }

        has_traffic = gsc["impressions"] >= 10 or gsc["clicks"] > 0
        has_backlinks = rd > 0
        has_content = word_count >= 200
        is_product = page_type == "product"

        # PRODUCTS ARE NEVER AUTO-DELETED — they can be sold, so the right
        # action for thin products is to add content + reconnect, not delete.
        if is_product and not has_content:
            signals["reason"] = (
                f"Product with thin content ({word_count}w) — add description in "
                f"Magento and assign to category. DO NOT DELETE."
            )
            buckets["needs_content"].append(signals)
        elif not has_traffic and not has_backlinks and not in_cluster and not has_content and not is_product:
            signals["reason"] = f"No traffic ({gsc['impressions']} impr), no backlinks, no cluster, thin ({word_count}w)"
            buckets["delete"].append(signals)
        elif has_backlinks and not has_traffic:
            signals["reason"] = f"Has {rd} backlinks but no traffic — 301 to closest live page to preserve equity"
            buckets["redirect"].append(signals)
        elif has_traffic or in_cluster:
            reasons = []
            if has_traffic:
                reasons.append(f"{gsc['impressions']} impr / {gsc['clicks']} clicks")
            if in_cluster:
                reasons.append("in topic cluster")
            if has_backlinks:
                reasons.append(f"{rd} backlinks")
            signals["reason"] = "Misclassified orphan: " + ", ".join(reasons) + " — needs internal link from category/related page"
            buckets["reconnect"].append(signals)
        else:
            signals["reason"] = f"Edge case: {gsc['impressions']} impr, {rd} bl, cluster={in_cluster}, {word_count}w"
            buckets["investigate"].append(signals)

    # Sort each bucket by impact (most impressions/backlinks first)
    buckets["reconnect"].sort(key=lambda x: -(x["impressions"] + x["referring_domains"] * 100))
    buckets["redirect"].sort(key=lambda x: -x["referring_domains"])
    buckets["delete"].sort(key=lambda x: x["url"])
    buckets["needs_content"].sort(key=lambda x: x["url"])
    return buckets


def _pages_to_delete():
    """Pages with no traffic, no backlinks, thin content."""
    audit_results = st.session_state.get("audit_results", [])
    page_authority = st.session_state.get("page_authority")

    candidates = []
    for r in audit_results:
        url = r.get("url", "")
        impressions = r.get("impressions", 0)
        clicks = r.get("clicks", 0)
        word_count = r.get("word_count", 0)

        # Get backlinks
        rd = 0
        if page_authority is not None and not page_authority.empty:
            match = page_authority[page_authority["page"].apply(normalize_url) == normalize_url(url)]
            if not match.empty:
                rd = int(match.iloc[0].get("referring_domains", 0))

        # Candidate for deletion: no traffic, no backlinks, thin content
        if impressions < 10 and clicks == 0 and rd == 0 and word_count < 200:
            candidates.append({
                "url": url,
                "impressions": impressions,
                "word_count": word_count,
                "page_type": r.get("page_type", "unknown"),
            })
    return candidates[:50]


def _blogs_to_review():
    """Blog posts with REWRITE quality verdict or zero traffic."""
    audit_results = st.session_state.get("audit_results", [])
    blogs = []
    for r in audit_results:
        # Only real blogs/faq — NOT info/corporate pages like /hjalp/, /jobb, /kontakt
        if r.get("page_type") not in ("blog", "faq"):
            continue
        url = r.get("url", "")
        impressions = r.get("impressions", 0)
        url_hash = stable_hash(url)
        quality = st.session_state.get(f"_quality_{url_hash}")
        if quality:
            verdict = quality.get("verdict", "")
            score = quality.get("score", 0)
            if verdict == "REWRITE" or (verdict == "IMPROVE" and score <= 4):
                blogs.append({
                    "url": url,
                    "verdict": verdict,
                    "score": score,
                    "summary": quality.get("summary", "")[:200],
                    "impressions": impressions,
                })
        elif impressions == 0:
            blogs.append({
                "url": url,
                "verdict": "ZERO TRAFFIC",
                "score": 0,
                "summary": "Blog has 0 impressions — consider deleting or improving",
                "impressions": 0,
            })
    return blogs[:30]


def render():
    st.markdown("## 🧹 Site Cleanup")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1rem;'>"
        "Site-wide cleanup actions: pages to delete, merge, redirect, noindex. "
        "These are decisions that affect site structure, not single-page improvements.</p>",
        unsafe_allow_html=True,
    )

    if "audit_results" not in st.session_state:
        st.warning("Run **⚡ Run Pipeline** first to get analysis data.")
        return

    # Site validation summary
    site_val = st.session_state.get("_site_validation")
    if isinstance(site_val, dict) and site_val.get("overall_health_score") is not None:
        health = site_val.get("overall_health_score", 0)
        score_color = "#33dd88" if health >= 70 else "#ffaa33" if health >= 40 else "#ff4455"
        st.markdown(
            f"<div style='background:#0d0d15; border-left:4px solid {score_color}; padding:0.8rem; border-radius:0 6px 6px 0; margin-bottom:1rem;'>"
            f"<div style='font-size:0.9rem; color:#e8e8f0;'><strong>Site Health: {health}/100</strong></div>"
            f"<div style='font-size:0.8rem; color:#c8b4ff;'>{site_val.get('summary', '')}</div></div>",
            unsafe_allow_html=True,
        )

    # Ideal structure summary (if run)
    ideal = st.session_state.get("_ideal_structure")
    if isinstance(ideal, dict):
        n_clusters = len(ideal.get("clusters", []))
        n_merges = len(ideal.get("merge", []))
        n_deletes = len(ideal.get("delete", []))
        n_creates = len(ideal.get("create", []))
        st.markdown(
            f"<div style='background:#0d0d15; border:1px solid #5533ff; padding:0.6rem; border-radius:6px; margin-bottom:1rem;'>"
            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#5533ff; margin-bottom:0.3rem;'>AI IDEAL STRUCTURE</div>"
            f"<div style='font-size:0.8rem; color:#c8b4ff;'>"
            f"{n_clusters} ideal clusters · {n_merges} pages to merge · {n_deletes} to delete · {n_creates} to create</div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("💡 Run **Generate Ideal Structure** in Site Map to get AI-recommended merges, deletes, and new pages.")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "🔀 Merge",
        "➕ Create",
        "↗ Redirect",
        "🚫 Noindex",
        "🗑 Delete",
        "📝 Blogs review",
        "🧩 Topic Gaps",
    ])

    # ── TAB 1: CANNIBALIZATION ACTIONS ──────────────────────
    with tab1:
        st.markdown("### Keyword conflicts — what to do")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "Pages competing for the same query. Each conflict is classified automatically with "
            "concrete Magento instructions. Click an item to see what to do + generate new meta titles.</p>",
            unsafe_allow_html=True,
        )

        cannibal_df = st.session_state.get("cannibalization")
        if cannibal_df is None or cannibal_df.empty:
            st.info("No cannibalization data — run Step 5 in Run Pipeline.")
        else:
            work = cannibal_df[cannibal_df["severity"].isin(["severe", "moderate"])].copy()
            work = work[~work["merge_action"].str.contains("DIFFERENT INTENTS|Homepage involved", na=False)]

            # Group by cannibal_type
            grouped = {}
            for _, row in work.iterrows():
                t = row.get("cannibal_type", "unknown")
                grouped.setdefault(t, []).append(row)

            type_ui = {
                "duplicate_categories": ("⚠ Duplicate categories — MERGE", "#ff6644",
                    "Two category pages target the same query. This is true cannibalization. "
                    "**Fix:** pick ONE winner, 301 redirect the loser, move products, update meta to cover both keywords."),
                "category_vs_children": ("🌳 Category + sub-pages", "#33dd88",
                    "NORMAL for e-commerce. Parent category and its sub-pages/products both rank for a generic query. "
                    "**Fix:** differentiate meta titles. Parent = generic, children = specific variant."),
                "products_same_parent": ("🎯 Products under same category", "#5533ff",
                    "Multiple products in the same category compete for one query. "
                    "**Fix:** give each product a UNIQUE meta title with its brand/variant."),
                "true_duplicate": ("🔀 True duplicates — merge", "#ff4455",
                    "Two nearly identical pages. **Fix:** 301 redirect the loser to the winner."),
                "products_no_parent": ("🏗 Missing category page", "#ffaa33",
                    "Products compete for a generic query but no category page targets it. "
                    "**Fix:** CREATE a new category in Magento and assign the products."),
                "unrelated": ("🔗 Unrelated pages", "#9b9bb8",
                    "Structurally unrelated pages compete. **Fix:** pick which page owns the query, differentiate the other."),
            }

            # Counts
            cols = st.columns(len(type_ui))
            for i, (tk, (label, color, _)) in enumerate(type_ui.items()):
                count = len(grouped.get(tk, []))
                if count > 0:
                    cols[i].metric(label.split(" ", 1)[0] + " " + label.split(" ", 1)[1][:20], count)
            st.markdown("---")

            for tk in type_ui:
                rows = grouped.get(tk, [])
                if not rows:
                    continue
                label, color, explanation = type_ui[tk]

                st.markdown(
                    f"<div style='border-left:4px solid {color}; padding:0.6rem 0.8rem; margin:1rem 0; background:#0d0d15; border-radius:0 4px 4px 0;'>"
                    f"<div style='font-weight:700; color:#e8e8f0; font-size:1.05rem;'>{label} ({len(rows)})</div>"
                    f"<div style='color:#c8b4ff; font-size:0.85rem; margin-top:0.3rem;'>{explanation}</div></div>",
                    unsafe_allow_html=True,
                )

                for row in sorted(rows, key=lambda r: -r.get("lost_clicks_estimate", 0))[:15]:
                    query = row["query"]
                    winner = row["recommended_winner"]
                    pages = row["pages_detail"]
                    lost = row.get("lost_clicks_estimate", 0)
                    parent = row.get("cannibal_parent_url")
                    action_text = row.get("cannibal_action", "")

                    with st.expander(f"'{query}' — {len(pages)} pages · {lost:,} lost clicks"):
                        # Pages table
                        st.markdown("**Pages competing for this query:**")
                        for p in pages:
                            page_url = p.get("page", "")
                            is_winner = normalize_url(page_url) == normalize_url(winner)
                            marker = " 🏆" if is_winner else ""
                            st.markdown(
                                f"- `{shorten_url(page_url)}` · pos {p.get('position','?')} · "
                                f"{p.get('clicks',0)} cl · {p.get('impressions',0):,} impr{marker}"
                            )

                        # Action instructions (rendered as markdown)
                        if action_text:
                            st.markdown("---")
                            st.markdown(action_text)

                        # Quality validation for category_vs_children
                        if tk == "category_vs_children" and parent:
                            issues = _validate_subcategory_quality(parent, pages)
                            if issues:
                                st.markdown("**🚨 Detected issues:**")
                                for iss in issues:
                                    sev_icon = "🔴" if iss["severity"] == "high" else "🟡"
                                    st.markdown(f"{sev_icon} `{shorten_url(iss['page'])}` — {iss['issue']}")
                                    st.caption(f"Fix: {iss['fix']}")

                        # AI meta generation button — available for ALL types
                        ai_key = f"_cannibal_meta_{stable_hash(query)}"
                        if ai_key in st.session_state:
                            meta_results = st.session_state[ai_key]
                            st.markdown("**✅ Generated meta (copy-paste into Magento):**")
                            for page_url, meta in meta_results.items():
                                variants = meta.get("variants", [])
                                if variants:
                                    best = variants[0]
                                    st.markdown(f"**`{shorten_url(page_url)}`**")
                                    st.code(
                                        f"Title: {best.get('title','')}\n"
                                        f"Description: {best.get('description','')}",
                                        language="text",
                                    )
                        else:
                            if st.button(
                                f"🤖 Generate differentiated meta titles for all {len(pages)} pages",
                                key=f"btn_{ai_key}",
                            ):
                                with st.spinner("AI generating meta per page..."):
                                    try:
                                        _generate_cannibal_subcategory_meta(query, pages, row, ai_key)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error: {e}")

                        # For true_duplicate + duplicate_categories: show redirect instructions
                        if tk in ("true_duplicate", "duplicate_categories"):
                            losers = [p["page"] for p in pages if normalize_url(p["page"]) != normalize_url(winner)]
                            st.markdown("**301 redirect (paste in Magento URL Rewrite Management):**")
                            for l in losers[:5]:
                                st.code(f"{l}  →  {winner}", language="text")
                            if tk == "duplicate_categories":
                                st.info("After redirect: move all products from loser category to winner category in Magento → Catalog → Categories.")

    # ── TAB 2: CREATE ─────────────────────────────────────────
    with tab2:
        creates = _pages_to_create()
        st.markdown(f"### {len(creates)} new pages/articles to create")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "Combined from: AI ideal structure + content roadmap + per-page plans.</p>",
            unsafe_allow_html=True,
        )
        if not creates:
            st.success("No new pages recommended")
        # Group by source
        by_source = {}
        for c in creates:
            by_source.setdefault(c.get("source", "other"), []).append(c)
        for source, items in by_source.items():
            source_labels = {
                "ideal_structure": "🏗 AI Ideal Structure",
                "content_roadmap": "📊 Content Roadmap (from topic clusters)",
                "page_plan": "📄 Per-page Implementation Plans",
            }
            st.markdown(f"#### {source_labels.get(source, source)} ({len(items)} items)")
            for c in items[:20]:
                label = c.get("url", "") if c.get("url", "").startswith("(") else f"`{c.get('url', '')}`"
                st.markdown(f"- {label}")
                if c.get("keyword"):
                    st.markdown(f"  <div style='color:#c8b4ff; font-size:0.75rem; margin-left:1rem;'>Keywords: {c.get('keyword', '')}</div>", unsafe_allow_html=True)
                if c.get("why"):
                    st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>{c.get('why', '')[:200]}</div>", unsafe_allow_html=True)
                if c.get("link_from"):
                    st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>Link from: {c.get('link_from', '')}</div>", unsafe_allow_html=True)

    # ── TAB 3: REDIRECT ──────────────────────────────────────
    with tab3:
        redirects = _pages_to_redirect()
        st.markdown(f"### {len(redirects)} broken pages to redirect")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "These pages return 4xx errors. Redirect to closest matching page to preserve any link equity.</p>",
            unsafe_allow_html=True,
        )
        if not redirects:
            st.success("No broken pages detected")
        for r in redirects[:30]:
            priority = "🔴 HIGH" if r["referring_domains"] > 0 else "⚪ LOW"
            st.markdown(f"- {priority} `{r['url']}` ({r['status']}) · {r['referring_domains']} backlinks")
            st.markdown(f"  <div style='color:#9b9bb8; font-size:0.8rem; margin-left:1rem;'>{r['action']}</div>", unsafe_allow_html=True)

    # ── TAB 4: NOINDEX ───────────────────────────────────────
    with tab4:
        noindex = _pages_to_noindex()
        st.markdown(f"### {len(noindex)} pages to noindex / block in robots.txt")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "These pages waste crawl budget without SEO value. Add noindex meta or block in robots.txt.</p>",
            unsafe_allow_html=True,
        )
        if not noindex:
            st.success("No noindex candidates")

        # Group by type
        by_type = {}
        for n in noindex:
            by_type.setdefault(n["type"], []).append(n)

        for type_key, items in by_type.items():
            with st.expander(f"{type_key.upper()} ({len(items)} pages)", expanded=False):
                if type_key == "faceted":
                    st.info("Magento 1.9 faceted URLs. Block via robots.txt:")
                    st.code("Disallow: /*?dir=\nDisallow: /*?limit=\nDisallow: /*?mode=\nDisallow: /*?order=\nDisallow: /*?p=\nDisallow: /*?SID=", language="text")
                for item in items[:30]:
                    st.markdown(f"- `{item['url']}` — {item['reason']}")

    # ── TAB 5: DELETE ────────────────────────────────────────
    with tab5:
        # Smart orphan classification — distinguish real orphans from misclassified
        orphan_buckets = _classify_orphans()
        n_orphan_total = sum(len(v) for v in orphan_buckets.values())

        if n_orphan_total > 0:
            st.markdown(f"### 🧭 Smart orphan classification ({n_orphan_total} total)")
            st.markdown(
                "<p style='color:#9b9bb8; font-size:0.85rem;'>"
                "Cross-references SF orphan list with GSC traffic, Ahrefs backlinks, "
                "and topic clusters. NOT all orphans should be deleted — many just lost their internal link.</p>",
                unsafe_allow_html=True,
            )
            cols = st.columns(5)
            cols[0].metric("🗑 Delete (true orphan)", len(orphan_buckets["delete"]))
            cols[1].metric("🔗 Reconnect (misclassified)", len(orphan_buckets["reconnect"]))
            cols[2].metric("↗ Redirect (has backlinks)", len(orphan_buckets["redirect"]))
            cols[3].metric("📝 Needs content (products)", len(orphan_buckets["needs_content"]))
            cols[4].metric("❓ Investigate", len(orphan_buckets["investigate"]))

            if orphan_buckets["needs_content"]:
                with st.expander(f"📝 Products needing content ({len(orphan_buckets['needs_content'])}) — DO NOT delete", expanded=False):
                    st.info("These are PRODUCT pages with thin/missing content. They can still be sold — add descriptions in Magento and assign to the right category. Never auto-delete products.")
                    for o in orphan_buckets["needs_content"][:50]:
                        st.markdown(f"- `{o['url']}` ({o['word_count']}w)")
                        st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>{o['reason']}</div>", unsafe_allow_html=True)

            with st.expander(f"🔗 Reconnect ({len(orphan_buckets['reconnect'])}) — DO NOT delete", expanded=False):
                st.info("These pages have traffic, backlinks, or are in topic clusters. They lost their internal link but should be RECONNECTED via category navigation, not deleted.")
                for o in orphan_buckets["reconnect"][:50]:
                    st.markdown(f"- `{o['url']}` ({o['page_type']}, {o['word_count']}w)")
                    st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>{o['reason']}</div>", unsafe_allow_html=True)

            with st.expander(f"↗ Redirect ({len(orphan_buckets['redirect'])}) — preserve link equity", expanded=False):
                st.info("These pages have backlinks but zero traffic. 301-redirect them to the closest live, related page to preserve link equity. Do NOT just delete — you'd lose the backlinks.")
                for o in orphan_buckets["redirect"][:50]:
                    st.markdown(f"- `{o['url']}` ({o['referring_domains']} backlinks)")
                    st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>{o['reason']}</div>", unsafe_allow_html=True)

            with st.expander(f"🗑 True orphans to delete ({len(orphan_buckets['delete'])})", expanded=False):
                st.warning("These have NO traffic, NO backlinks, NO cluster, and thin content. Safe to delete.")
                for o in orphan_buckets["delete"][:50]:
                    st.markdown(f"- `{o['url']}` ({o['page_type']}, {o['word_count']}w)")

            if orphan_buckets["investigate"]:
                with st.expander(f"❓ Investigate ({len(orphan_buckets['investigate'])})", expanded=False):
                    st.markdown("Edge cases — manual review needed.")
                    for o in orphan_buckets["investigate"][:50]:
                        st.markdown(f"- `{o['url']}` — {o['reason']}")
            st.markdown("---")

        deletes = _pages_to_delete()
        ideal_deletes = _pages_to_delete_ideal()
        st.markdown(f"### {len(deletes) + len(ideal_deletes)} pages to consider deleting")

        if ideal_deletes:
            st.markdown("#### 🏗 AI Ideal Structure recommendations")
            st.markdown(
                "<p style='color:#9b9bb8; font-size:0.85rem;'>Pages the AI recommends deleting based on site architecture review.</p>",
                unsafe_allow_html=True,
            )
            for d in ideal_deletes[:30]:
                st.markdown(f"- `{d.get('url', '')}` — {d.get('why', '')}")
            st.markdown("---")

        st.markdown("#### 📊 Data-driven candidates (no traffic, no backlinks, thin content)")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "Pages with: 0 clicks, <10 impressions, 0 backlinks, <200 words.</p>",
            unsafe_allow_html=True,
        )
        if not deletes:
            st.success("No clearly deletable pages from data analysis")
        for d in deletes[:30]:
            st.markdown(f"- `{d['url']}` ({d['page_type']}) · {d['word_count']} words · {d['impressions']} impressions")

    # ── TAB 6: BLOGS TO REVIEW ───────────────────────────────
    with tab6:
        blogs = _blogs_to_review()
        st.markdown(f"### {len(blogs)} blog/guide pages needing review")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "Blog posts with REWRITE verdict from AI quality check, or zero traffic. "
            "Either rewrite, delete, or repurpose.</p>",
            unsafe_allow_html=True,
        )
        if not blogs:
            st.success("No blogs flagged for review")
        for b in blogs[:30]:
            v_color = {"REWRITE": "#ff4455", "IMPROVE": "#ffaa33", "ZERO TRAFFIC": "#6b6b8a"}.get(b["verdict"], "#6b6b8a")
            with st.expander(f"[{b['verdict']}] {shorten_url(b['url'])} · {b['impressions']} impressions"):
                st.markdown(f"**Score:** {b['score']}/10")
                st.markdown(f"**Issue:** {b['summary']}")
                st.markdown(f"**Options:**")
                st.markdown("1. **Rewrite** — use Quick Wins to generate new content")
                st.markdown("2. **Delete** — if topic is irrelevant or covered elsewhere")
                st.markdown("3. **Merge** — combine with another article on same topic")
                st.markdown("4. **Redirect** — if better content exists, 301 to that page")

    # ── TAB 7: TOPIC GAPS ────────────────────────────────────
    with tab7:
        gaps = st.session_state.get("content_gaps", []) or []
        st.markdown(f"### {len(gaps)} topic clusters with content gaps")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "Topics where the site underperforms: poor CTR despite impressions, "
            "topic split across too many pages, thin coverage, or missing backlinks. "
            "Source: topic cluster analysis (pipeline step 6).</p>",
            unsafe_allow_html=True,
        )
        if not gaps:
            st.info("No gaps found — run **Build Topic Clusters** in Run Pipeline first.")
        else:
            high = [g for g in gaps if isinstance(g, dict) and g.get("priority") == "high"]
            medium = [g for g in gaps if isinstance(g, dict) and g.get("priority") == "medium"]

            if high:
                st.markdown("#### 🔴 High priority")
                for g in high[:30]:
                    with st.expander(f"{g.get('topic','?')} · {g.get('impressions',0):,} impressions · {g.get('queries',0)} queries"):
                        for issue in g.get("issues", []):
                            st.markdown(f"- {issue}")
                        st.markdown(
                            "<div style='color:#9b9bb8; font-size:0.75rem; margin-top:0.5rem;'>"
                            "Action: review in Topic Clusters view for consolidation, new content, or link building.</div>",
                            unsafe_allow_html=True,
                        )

            if medium:
                st.markdown("#### 🟡 Medium priority")
                for g in medium[:30]:
                    with st.expander(f"{g.get('topic','?')} · {g.get('impressions',0):,} impressions · {g.get('queries',0)} queries"):
                        for issue in g.get("issues", []):
                            st.markdown(f"- {issue}")
