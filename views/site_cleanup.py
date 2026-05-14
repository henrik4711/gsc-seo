"""
Site Cleanup — Site-wide actions: pages to delete, merge, redirect, noindex.
Different from Quick Wins which is per-page improvements.
Also includes unclustered-page assignment + cluster balance (formerly Structure Fix).
"""

import streamlit as st
from utils.ui_helpers import normalize_url, stable_hash, shorten_url
from views.structure_fix import (
    _audit_lookup,
    _get_unclustered,
    _render_unclustered,
    _render_cluster_balance,
)


def _novice_box(what: str, why: str, how: str, border: str = "#5533ff"):
    """Render a standardized NOVICE explanation card: What / Why / How."""
    st.markdown(
        f"<div style='background:#0d0d15; border:1px solid {border}; border-radius:8px; "
        f"padding:1rem; margin:0.5rem 0 1rem 0;'>"
        f"<div style='font-size:0.7rem; color:{border}; font-family:\"IBM Plex Mono\",monospace; "
        f"letter-spacing:0.05em; margin-bottom:0.4rem;'>NOVICE EXPLANATION</div>"
        f"<div style='font-size:0.9rem; color:#e8e8f0; font-weight:700;'>What is this?</div>"
        f"<div style='font-size:0.85rem; color:#c8b4ff; margin:0.3rem 0 0.8rem 0;'>{what}</div>"
        f"<div style='font-size:0.9rem; color:#e8e8f0; font-weight:700;'>Why this matters</div>"
        f"<div style='font-size:0.85rem; color:#c8b4ff; margin:0.3rem 0 0.8rem 0;'>{why}</div>"
        f"<div style='font-size:0.9rem; color:#e8e8f0; font-weight:700;'>How to do it (step by step)</div>"
        f"<div style='font-size:0.85rem; color:#c8b4ff; margin-top:0.3rem;'>{how}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _classify_conflict_page(page_url: str, winner_url: str, query: str,
                             page_data: dict, audit_lookup: dict) -> dict:
    """
    Decide the specific role + action for one page in a cannibalization conflict.

    Returns dict: {role, label, color, action_html}
    """
    from urllib.parse import urlparse
    from utils.site_patterns import get_sale_patterns

    norm = normalize_url(page_url)
    winner_norm = normalize_url(winner_url)

    # Winner
    if norm == winner_norm:
        return {
            "role": "WINNER",
            "label": "🏆 KEEP — strengthen this page",
            "color": "#33dd88",
            "action_html": (
                f"This is the page Google already prefers. Make sure its meta title + H1 both "
                f"contain <code>{query}</code>. Every other page in this conflict must either "
                f"redirect here, link here, or clearly target a different variant."
            ),
        }

    # Pull page type from audit_lookup (fast) — fall back to page_data
    audit = audit_lookup.get(norm, {}) or {}
    page_type = audit.get("page_type") or page_data.get("page_type", "") or ""

    # SALE / REA page
    try:
        sale_patterns = get_sale_patterns()
    except Exception:
        sale_patterns = ["/rea/", "/sale/", "/udsalg/", "billig"]
    if any(sp in page_url.lower() for sp in sale_patterns):
        return {
            "role": "SALE PAGE",
            "label": "🏷 KEEP for UX — stop it competing on the keyword",
            "color": "#ffaa33",
            "action_html": (
                "Customers use this page as a \"cheap/sale\" filter — don't delete or redirect it. "
                "But it must stop competing on the main keyword. Pick ONE of:<br>"
                "<strong>Option A (recommended): strip the SEO text.</strong> In Magento → Catalog → "
                "Categories → open this page → remove the intro paragraph and the bottom editorial "
                "text. Leave ONLY H1 + product grid. Page still works for shoppers, no longer "
                "competes on the keyword.<br>"
                "<strong>Option B: noindex.</strong> Open this page → Design tab → Custom Layout "
                "Update → add <code>&lt;meta name=\"robots\" content=\"noindex,follow\"&gt;</code>. "
                "Page stays live for direct visitors, Google drops it from results. Use this if "
                "the intro text is important for conversions.<br>"
                f"<strong>Also add</strong> a link in the H1 area to the winner: "
                f"<code>&lt;a href=\"{winner_url}\"&gt;{query}&lt;/a&gt;</code>"
            ),
        }

    # PRODUCT page
    if page_type == "product":
        return {
            "role": "PRODUCT",
            "label": "📦 KEEP as product — cannot be merged",
            "color": "#5bb4d4",
            "action_html": (
                f"This is a product page, not a category. It can't be merged with a category. "
                f"Three concrete fixes:<br>"
                f"1. In Magento → Catalog → Products → open this product → <strong>Categories</strong> "
                f"tab. Ensure it's assigned to the winner category "
                f"(<code>{shorten_url(winner_url)}</code>) so visitors to the winner find it.<br>"
                f"2. In the product's <strong>description</strong> field, add one contextual link "
                f"back to the winner category with anchor text <code>{query}</code>: "
                f"<code>&lt;a href=\"{winner_url}\"&gt;{query}&lt;/a&gt;</code> (this tells Google "
                f"the winner is the authoritative page for the generic query).<br>"
                f"3. Rewrite the product's meta title to include the <strong>brand or variant "
                f"name</strong> instead of just the generic keyword "
                f"(e.g. \"Pocket Pussy Mia — [Brand] · mshop\"). This makes the product target a "
                f"long-tail query, not compete on <code>{query}</code>."
            ),
        }

    # Path-based geometry — single source of truth via url_helpers
    from utils.url_helpers import url_path, url_segments, path_is_descendant, paths_are_siblings, shared_top_level
    winner_path = url_path(winner_norm)
    loser_path = url_path(norm)

    # SUB-CATEGORY of winner
    if path_is_descendant(page_url, winner_url):
        return {
            "role": "SUB-CATEGORY",
            "label": "🌳 KEEP — sub-category of winner",
            "color": "#33dd88",
            "action_html": (
                f"This lives UNDER the winner in the URL tree — it's a legitimate sub-category, "
                f"not a duplicate. Action:<br>"
                f"1. Differentiate the meta title: the parent targets generic <code>{query}</code>, "
                f"this child targets the variant (look at the last URL segment for the variant term).<br>"
                f"2. Make sure the winner page links TO this sub-category (category tree, breadcrumb, "
                f"or a feature box on the winner)."
            ),
        }

    # SIBLING (same parent directory)
    if paths_are_siblings(page_url, winner_url):
        return {
            "role": "SIBLING",
            "label": "🌳 KEEP — sibling category (different variant)",
            "color": "#33dd88",
            "action_html": (
                f"Same parent folder as the winner — it's a sibling targeting a different variant. "
                f"Don't merge. Action:<br>"
                f"1. Differentiate the meta title to emphasize THIS page's variant term.<br>"
                f"2. Add a cross-link from this page to the winner with anchor "
                f"<code>{query}</code>, and a link on the winner to this sibling with anchor "
                f"for its variant."
            ),
        }

    # DIFFERENT TREE (different top-level section)
    if not shared_top_level(page_url, winner_url):
        return {
            "role": "DIFFERENT PURPOSE",
            "label": "🔀 KEEP — different site section / intent",
            "color": "#c8b4ff",
            "action_html": (
                f"This page lives in a different part of the site tree, so it likely serves a "
                f"different intent. Don't merge. Action:<br>"
                f"1. Differentiate the meta title so the intent difference is obvious.<br>"
                f"2. Add an in-body link to the winner with anchor <code>{query}</code> — this "
                f"tells Google the winner is the primary page for the generic query while this "
                f"page keeps its own niche."
            ),
        }

    # TRUE DUPLICATE — same level, same tree, similar structure
    return {
        "role": "TRUE DUPLICATE",
        "label": "🗑 301 REDIRECT to winner",
        "color": "#ff4455",
        "action_html": (
            f"Same-level duplicate of the winner. Action:<br>"
            f"1. Copy any unique content from this page into the winner first.<br>"
            f"2. Magento → Marketing → SEO &amp; Search → <strong>URL Rewrites</strong> → Add URL "
            f"Rewrite. Request Path = <code>{url_path(page_url)}</code>, Target Path = "
            f"<code>{url_path(winner_url)}</code>, Redirect Type = <strong>Permanent (301)</strong>.<br>"
            f"3. Magento → Catalog → Categories → move all products from this category to the winner.<br>"
            f"4. Delete this category."
        ),
    }


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

    # Build set of existing URLs + titles for duplicate checking
    audit_results = st.session_state.get("audit_results", [])
    existing_urls = set()
    existing_titles_lower = set()
    existing_url_segments = set()
    for r in audit_results:
        u = normalize_url(r.get("url", ""))
        if u:
            existing_urls.add(u)
            # Extract path segments for fuzzy URL matching
            from utils.url_helpers import url_path as _up, url_segments as _usegs
            for seg in _usegs(u):
                if len(seg) > 3:
                    existing_url_segments.add(seg)
        t = (r.get("title") or "").lower().strip()
        if t:
            existing_titles_lower.add(t)

    def _already_exists(url_or_title: str) -> str:
        """Check if page already exists. Returns reason string or empty."""
        # Check exact URL match
        norm = normalize_url(url_or_title)
        if norm in existing_urls:
            return f"Page already exists: {url_or_title}"
        # Check if URL path matches an existing page
        path = _up(url_or_title).lower() if "://" in url_or_title or url_or_title.startswith("/") else ""
        if path:
            for eu in existing_urls:
                if _up(eu).lower() == path:
                    return f"URL path already exists: {eu}"
        # Check title similarity
        title_lower = url_or_title.lower().strip()
        if title_lower in existing_titles_lower:
            return f"Page with same title already exists"
        return ""

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
            exists = _already_exists(url)
            entry = {
                "url": url,
                "type": c.get("type", "page"),
                "keyword": c.get("kw", ""),
                "why": c.get("why", ""),
                "source": "ideal_structure",
            }
            if exists:
                entry["already_exists"] = exists
            creates.append(entry)

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
            exists = _already_exists(title)
            entry = {
                "url": f"(new article: {title})",
                "type": a.get("type", "blog"),
                "keyword": ", ".join(a.get("target_keywords", [])[:3]),
                "why": a.get("why", ""),
                "source": "content_roadmap",
                "priority": a.get("priority", ""),
            }
            if exists:
                entry["already_exists"] = exists
            creates.append(entry)

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
            exists = _already_exists(title)
            entry = {
                "url": f"(new article: {title})",
                "type": nc.get("type", "blog"),
                "keyword": ", ".join(nc.get("target_keywords", [])[:3]),
                "why": nc.get("why", ""),
                "source": "page_plan",
                "link_from": nc.get("link_from", ""),
            }
            if exists:
                entry["already_exists"] = exists
            creates.append(entry)

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

    # Build set of pages that already have redirects in place
    redirect_chains = issues.get("redirect_chains", [])
    already_redirected = set()
    for rc in redirect_chains:
        if isinstance(rc, dict) and rc.get("url"):
            already_redirected.add(normalize_url(rc["url"]))

    # Build set of active pages (have impressions/traffic) to avoid redirecting them
    audit_results = st.session_state.get("audit_results", [])
    active_pages = set()
    for r in audit_results:
        if r.get("impressions", 0) > 0 or r.get("clicks", 0) > 0:
            active_pages.add(normalize_url(r.get("url", "")))

    redirects = []
    for b in broken:
        url = b.get("url", "")
        norm = normalize_url(url)

        # Skip if redirect is already in place
        if norm in already_redirected:
            continue

        # Skip if page is actually active (may be a false positive from crawl)
        if norm in active_pages:
            continue

        rd = 0
        if page_authority is not None and not page_authority.empty:
            match = page_authority[page_authority["page"].apply(normalize_url) == norm]
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


def _generate_cannibal_rewrite(page_url: str, query: str, issues: list, context: str, rewrite_key: str):
    """
    Generate COMPLETE new body text for a page, fixing ALL detected issues.
    Thin wrapper around generate_page_content() — the unified text generator.
    """
    from utils.ai_generator import generate_page_content
    from utils.persistence import save

    result = generate_page_content(page_url, target_query=query)
    st.session_state[rewrite_key] = result
    save(rewrite_key)


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
        from utils.url_helpers import url_last_segment as _uls
        variant_kw = _uls(page_url).replace("-", " ")

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
    from utils.page_profile import build_page_profile

    parent_profile = build_page_profile(parent_url)
    parent_norm = normalize_url(parent_url)
    parent_title = parent_profile["title"].lower().strip()
    parent_h1 = parent_profile["h1"].lower().strip()
    parent_word_count = parent_profile["word_count"]

    issues = []

    # Build set of parent's outbound link targets (from profile)
    parent_outbound = set()
    for lnk in parent_profile["internal_links_out"]:
        link_url = normalize_url(lnk.get("url", ""))
        if link_url:
            parent_outbound.add(link_url)

    for child in child_pages:
        child_url = child.get("page", "") if isinstance(child, dict) else child
        child_norm = normalize_url(child_url)
        if child_norm == parent_norm:
            continue  # skip self
        child_profile = build_page_profile(child_url)
        child_title = child_profile["title"].lower().strip()
        child_h1 = child_profile["h1"].lower().strip()
        child_wc = child_profile["word_count"]

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
        from utils.quality_check_runner import quality_key as _qk_sc2
        quality = st.session_state.get(_qk_sc2(url))
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
        "Site-wide cleanup actions — all the structural decisions in one place: "
        "merge duplicates, create missing pages, fix broken URLs, noindex junk, delete dead pages, "
        "review blogs, fill topic gaps, assign unclustered pages, and balance topic clusters.</p>",
        unsafe_allow_html=True,
    )

    # Overall novice-friendly how-to-work-through-this banner
    st.markdown(
        "<div style='background:#0d0d15; border:2px solid #5533ff; border-radius:10px; "
        "padding:1.2rem; margin-bottom:1.5rem;'>"
        "<div style='font-size:1.05rem; color:#e8e8f0; font-weight:700; margin-bottom:0.6rem;'>"
        "🎓 New here? Do the tabs in this order</div>"
        "<div style='font-size:0.85rem; color:#c8b4ff; line-height:1.6;'>"
        "<strong>1. Merge</strong> — the biggest SEO win. Fix pages fighting each other for the same keyword.<br>"
        "<strong>2. Delete</strong> — remove or hide dead weight pages that drag the whole site down.<br>"
        "<strong>3. Redirect</strong> — fix broken URLs (404s) that still have links pointing at them.<br>"
        "<strong>4. Noindex</strong> — tell Google to ignore junk URLs (filter pages, duplicates).<br>"
        "<strong>5. Create</strong> — add the pages Google wants to see but your site is missing.<br>"
        "<strong>6. Blogs review</strong> — rewrite, delete, or merge weak blog articles.<br>"
        "<strong>7. Topic Gaps</strong> — where your site underperforms on whole subject areas.<br>"
        "<strong>8. Unclustered Pages</strong> — assign orphan pages to the right topic group.<br>"
        "<strong>9. Cluster Balance</strong> — see which topics need more pages or have too many.<br><br>"
        "You don't have to finish everything today. Do each tab in chunks, save as you go, "
        "and come back. Each tab below has its own <strong>NOVICE EXPLANATION</strong> card "
        "with plain-English What / Why / How.</div></div>",
        unsafe_allow_html=True,
    )

    # ── TEMP diagnostic: download editorial-container diagnostics as JSON ──
    with st.expander("📊 TEMP — download editorial container diagnostics (JSON)", expanded=False):
        st.caption(
            "Collected during Page Auditor scrape. One row per page with all div/section "
            "class signatures that contain editorial text + images. Use offline (Claude, "
            "Excel, etc.) to figure out which container classes to add to the regex — "
            "no re-scrape needed."
        )
        audit_results_all = st.session_state.get("audit_results", []) or []
        diag_rows = []
        for r in audit_results_all:
            cands = r.get("editorial_container_candidates") or []
            intro = (r.get("intro_text") or "")[:600]
            bottom = (r.get("bottom_text") or "")[:2000]
            body = (r.get("body_text") or "")[:2000]
            if not cands and not intro and not bottom:
                continue
            diag_rows.append({
                "url": r.get("url", ""),
                "page_type": r.get("page_type", ""),
                "title": r.get("title", ""),
                "editorial_image_count": r.get("editorial_image_count", 0),
                "editorial_images": r.get("editorial_images", []) or [],
                "intro_word_count": r.get("intro_word_count", 0),
                "bottom_word_count": r.get("bottom_word_count", 0),
                "total_editorial_words": r.get("total_editorial_words", 0),
                "word_count": r.get("word_count", 0),
                "intro_text_sample": intro,
                "bottom_text_sample": bottom,
                "body_text_sample": body,
                "container_candidates": cands,
            })

        if not diag_rows:
            st.info(
                "No diagnostic data yet. Re-run **Step 6 (Page Auditor)** once — "
                "every scrape now saves this automatically."
            )
        else:
            import json
            from datetime import datetime
            st.success(f"Diagnostics available for {len(diag_rows)} page(s).")
            json_blob = json.dumps(diag_rows, ensure_ascii=False, indent=2)
            fname = f"editorial_container_diagnostics_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
            st.download_button(
                label=f"⬇ Download {fname} ({len(json_blob)//1024} KB)",
                data=json_blob,
                file_name=fname,
                mime="application/json",
                type="primary",
            )

    # ── TEMP diagnostic: single-page image preservation test ──
    with st.expander("🔬 TEMP TEST — check image preservation on ONE page (skip the 4h pipeline)", expanded=False):
        st.caption(
            "Tests the full flow on a single URL: scrape → capture editorial images → "
            "run AI rewrite → verify each image src appears verbatim in the generated HTML."
        )
        test_url = st.text_input(
            "URL to test",
            value="https://www.mshop.se/sexleksaker/sexleksaker-for-honom/pocket-pussy",
            key="_img_test_url",
        )
        test_query = st.text_input("Target keyword", value="pocket pussy", key="_img_test_kw")
        if st.button("Run image-preservation test", type="primary", key="_img_test_btn"):
            from utils.page_scraper import scrape_page
            from utils.ai_generator import generate_page_content

            # Step 1 — scrape
            with st.spinner("Scraping page..."):
                scraped = scrape_page(test_url)
            imgs = scraped.get("editorial_images", []) or []
            diag = scraped.get("editorial_image_diag", {}) or {}
            st.markdown(f"**Step 1 · Scrape** — captured **{len(imgs)}** editorial image(s)")
            if diag:
                st.caption(
                    f"Intro containers found: {diag.get('intro_containers',0)} · "
                    f"Bottom/SEO containers found: {diag.get('bottom_containers',0)} · "
                    f"<img> inside them: {diag.get('total',0)} · "
                    f"kept: {diag.get('kept',0)} · "
                    f"skipped (product-card) = {diag.get('skipped_product',0)} · "
                    f"skipped (nav) = {diag.get('skipped_nav',0)} · "
                    f"skipped (no usable src) = {diag.get('skipped_no_src',0)} · "
                    f"skipped (dupe) = {diag.get('skipped_dupe',0)}"
                )
            if imgs:
                for i, im in enumerate(imgs, 1):
                    st.markdown(
                        f"`{i}.` section=`{im.get('section','?')}` · "
                        f"alt=`{im.get('alt','') or '(none)'}`<br>"
                        f"&nbsp;&nbsp;src=`{im.get('src','')}`" +
                        (f"<br>&nbsp;&nbsp;link_href=`{im['link_href']}`" if im.get('link_href') else "") +
                        (f"<br>&nbsp;&nbsp;caption=`{im['caption']}`" if im.get('caption') else ""),
                        unsafe_allow_html=True,
                    )
            else:
                st.error("❌ No editorial images captured during scrape.")
                # Deep-dive: dump div classes from the live page so we can
                # identify the correct intro + bottom container class names.
                st.markdown("**Raw diagnostic — divs that contain editorial text:**")
                try:
                    import requests as _rq
                    from bs4 import BeautifulSoup as _BS
                    _r = _rq.get(test_url, headers={"User-Agent": "Mozilla/5.0 SEOBot"}, timeout=20)
                    _soup = _BS(_r.text, "html.parser")

                    # Find divs that contain <p> or <h2> with substantial text AND at least one <img>
                    candidates = []
                    for d in _soup.find_all(["div", "section"]):
                        cls = " ".join(d.get("class") or [])
                        if not cls:
                            continue
                        if any(skip in cls.lower() for skip in ("product-card", "product-item", "card-product", "price-box", "swiper-slide", "category-product")):
                            continue
                        imgs_in = d.find_all("img", recursive=True)
                        ps_in = d.find_all(["p", "h2", "h3"], recursive=True)
                        text_len = sum(len(p.get_text(strip=True)) for p in ps_in)
                        # Editorial-ish: substantial text AND at least 1 image AND not the whole page
                        if imgs_in and text_len > 100 and text_len < 20000:
                            candidates.append({
                                "classes": cls,
                                "tag": d.name,
                                "text_chars": text_len,
                                "imgs": len(imgs_in),
                                "sample": d.get_text(strip=True)[:120],
                            })
                    # Dedupe by classes
                    seen_cls = set()
                    dedup = []
                    for c in candidates:
                        if c["classes"] not in seen_cls:
                            seen_cls.add(c["classes"])
                            dedup.append(c)
                    dedup.sort(key=lambda x: -x["imgs"])
                    st.caption(f"Found {len(dedup)} div/section candidates containing text + images:")
                    for i, c in enumerate(dedup[:15], 1):
                        st.code(
                            f"{i}. <{c['tag']} class=\"{c['classes']}\">\n"
                            f"   text_chars={c['text_chars']}, imgs={c['imgs']}\n"
                            f"   sample: {c['sample']!r}",
                            language="text",
                        )
                    st.info("Copy the class names of the editorial container(s) — paste them back and I'll add them to the intro/bottom regex.")
                except Exception as _e:
                    st.error(f"Raw fetch failed: {_e}")
                st.stop()

            # Step 2 — inject minimal audit entry so build_page_profile sees editorial_images
            from utils.ui_helpers import normalize_url as _nu
            norm = _nu(test_url)
            original_audit = list(st.session_state.get("audit_results", []) or [])
            test_entry = {
                "url": test_url,
                "page_type": scraped.get("page_type") or "category",
                "title": scraped.get("title", ""),
                "meta_description": scraped.get("description") or scraped.get("meta_description", ""),
                "h1": scraped.get("h1", ""),
                "h2s": scraped.get("h2s", []) or [],
                "word_count": scraped.get("word_count", 0),
                "body_text": scraped.get("body_text", ""),
                "intro_text": scraped.get("intro_text", ""),
                "bottom_text": scraped.get("bottom_text", ""),
                "editorial_images": imgs,
                "total_editorial_words": scraped.get("total_editorial_words", 0),
                "internal_links": scraped.get("internal_links", []) or [],
                "schema_types": scraped.get("schema_types", []) or [],
                "content_audit": {"products": []},
                "products": [],
            }
            filtered = [r for r in original_audit if _nu(r.get("url", "")) != norm]
            st.session_state["audit_results"] = filtered + [test_entry]
            st.markdown(f"**Step 2 · Inject** — audit_results now has {len(filtered) + 1} entries (injected test entry with `editorial_images`)")

            # Step 3 — run AI rewrite
            st.markdown("**Step 3 · AI rewrite** — calling `generate_page_content`…")
            try:
                with st.spinner("AI generating rewrite (may take 30-60s)..."):
                    result = generate_page_content(test_url, target_query=test_query)
            except Exception as e:
                st.error(f"❌ AI error: {e}")
                # Restore audit
                st.session_state["audit_results"] = original_audit
                st.stop()

            # Step 4 — verify each scraped image src appears in the generated HTML
            top_html = result.get("top_html", "") or ""
            bottom_html = result.get("bottom_html", "") or ""
            combined = top_html + "\n" + bottom_html

            st.markdown("**Step 4 · Verify image preservation**")
            pass_count = 0
            for i, im in enumerate(imgs, 1):
                src = im.get("src", "")
                found = src and (src in combined)
                pass_count += 1 if found else 0
                icon = "✅" if found else "❌"
                section_hit = "top" if src in top_html else ("bottom" if src in bottom_html else "MISSING")
                st.markdown(f"{icon} `{i}.` expected in `{im.get('section','?')}` · found in `{section_hit}`<br>&nbsp;&nbsp;`{src}`", unsafe_allow_html=True)

            if pass_count == len(imgs):
                st.success(f"🎉 ALL {len(imgs)} images preserved verbatim in AI output")
            else:
                st.error(f"⚠ Only {pass_count}/{len(imgs)} images preserved — AI is dropping images")

            # Restore original audit_results so this test doesn't pollute other views
            st.session_state["audit_results"] = original_audit

            with st.expander("Show raw generated HTML"):
                st.markdown("**TOP TEXT:**")
                st.code(top_html or "(empty)", language="html")
                st.markdown("**BOTTOM TEXT:**")
                st.code(bottom_html or "(empty)", language="html")

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

    # Precompute for tab labels
    audit_lookup = _audit_lookup()
    topic_clusters_data = st.session_state.get("topic_clusters", {}) or {}
    page_topics = topic_clusters_data.get("page_topics", {}) if isinstance(topic_clusters_data, dict) else {}
    clusters_list = topic_clusters_data.get("clusters", []) if isinstance(topic_clusters_data, dict) else []
    unclustered_pages = _get_unclustered(audit_lookup, page_topics)

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
        "🔀 Merge",
        "➕ Create",
        "↗ Redirect",
        "🚫 Noindex",
        "🗑 Delete",
        "📝 Blogs review",
        "🧩 Topic Gaps",
        f"🧭 Unclustered ({len(unclustered_pages)})",
        f"⚖ Cluster Balance ({len(clusters_list)})",
    ])

    # ── TAB 1: CANNIBALIZATION ACTIONS ──────────────────────
    with tab1:
        st.markdown("### Keyword conflicts — what to do")
        _novice_box(
            what=(
                "Two or more of your own pages are showing up in Google for the SAME search word. "
                "That means they are fighting each other — Google can't decide which one to rank, so "
                "it usually pushes both down in the results. This is called <strong>keyword "
                "cannibalization</strong>."
            ),
            why=(
                "Every time two of your pages compete for the same keyword, you lose traffic that "
                "should have gone to ONE strong page. The list below shows an estimate of \"lost "
                "clicks\" per conflict — that is real money leaving to competitors. Fixing this is "
                "usually the single biggest SEO win you can make without writing new content."
            ),
            how=(
                "1. Open each conflict card below.<br>"
                "2. The winner (🏆) is the page Google already prefers — keep it.<br>"
                "3. Depending on the conflict type, the tool tells you exactly what to do:<br>"
                "&nbsp;&nbsp;• <strong>Duplicate categories</strong>: 301-redirect the loser → the winner, "
                "move its products to the winner in Magento → Catalog → Categories.<br>"
                "&nbsp;&nbsp;• <strong>Category + sub-categories / Category + products</strong>: don't merge — "
                "click <em>Generate differentiated meta titles</em> and paste the new titles/descriptions "
                "into Magento (Stores → Attributes or directly on the category/product).<br>"
                "&nbsp;&nbsp;• <strong>Products under same category</strong>: each product needs a UNIQUE meta "
                "title with its brand/variant name.<br>"
                "&nbsp;&nbsp;• <strong>Missing category page</strong>: create a new category in Magento and "
                "assign the competing products to it.<br>"
                "4. For 301 redirects: Magento Admin → Marketing → SEO &amp; Search → URL Rewrites → "
                "Add URL Rewrite. Set Request Path = loser URL, Target Path = winner URL, Redirect Type "
                "= Permanent (301)."
            ),
            border="#ff6644",
        )
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
            all_work = cannibal_df[cannibal_df["severity"].isin(["severe", "moderate", "handled"])].copy()
            all_work = all_work[~all_work["merge_action"].str.contains("DIFFERENT INTENTS|Homepage involved", na=False)]

            # Split: items needing action vs already handled
            # Filter on severity="handled" (only set when FULLY resolved:
            # titles differentiated + content OK + links OK + quality OK).
            # NOT on already_differentiated which only checks titles.
            handled = all_work[all_work["severity"] == "handled"] if "severity" in all_work.columns else all_work.iloc[0:0]
            work = all_work[all_work["severity"] != "handled"] if "severity" in all_work.columns else all_work

            if len(handled) > 0:
                st.success(f"✅ {len(handled)} conflicts already have differentiated meta titles — no action needed. Showing only items that need work.")

            # Group by cannibal_type
            grouped = {}
            for _, row in work.iterrows():
                t = row.get("cannibal_type", "unknown")
                grouped.setdefault(t, []).append(row)

            type_ui = {
                "duplicate_categories": ("⚠ Duplicate categories — MIXED fix", "#ff6644",
                    "Multiple pages rank for the same category query — BUT each competing page "
                    "usually has a different role (sale page, product, sibling category, sub-category, "
                    "or true duplicate). Don't blindly 301 all of them. "
                    "**Each page below shows its own classification + specific action.** "
                    "Typical pattern: keep the winner, strip SEO text or noindex sale pages, "
                    "add contextual links from products to the winner, differentiate meta on siblings, "
                    "and 301 only the real duplicates."),
                "category_vs_children": ("🌳 Category + sub-categories", "#33dd88",
                    "NORMAL. Parent category and its sub-categories both rank. "
                    "**Fix:** differentiate meta. Parent = generic, children = specific variant."),
                "category_vs_products": ("📦 Category + products", "#44bb88",
                    "NORMAL. A category and its products both rank for a generic query. "
                    "**Fix:** category meta targets generic, product meta targets product name."),
                "products_same_parent": ("🎯 Products under same category", "#5533ff",
                    "Products in the same category compete. "
                    "**Fix:** each product gets UNIQUE meta with its brand/variant."),
                "products_no_category": ("🏗 Missing category page", "#ffaa33",
                    "Products compete for a generic query but no category targets it. "
                    "**Fix:** CREATE a new category in Magento and assign the products."),
                "true_duplicate": ("🔀 True duplicates — merge", "#ff4455",
                    "Two similar pages compete. **Fix:** 301 redirect the loser to the winner."),
                "mixed": ("🔗 Mixed types", "#9b9bb8",
                    "Different page types compete. **Fix:** category owns generic query, products/blogs target specific variants."),
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

                        # For types with heterogeneous roles, render per-page classification cards
                        show_per_page_roles = tk in (
                            "duplicate_categories", "true_duplicate", "mixed",
                            "products_no_category", "category_vs_products",
                            "products_same_parent",
                        )
                        audit_lookup_for_conflict = _audit_lookup() if show_per_page_roles else {}

                        for p in pages:
                            page_url = p.get("page", "")
                            is_winner = normalize_url(page_url) == normalize_url(winner)
                            marker = " 🏆" if is_winner else ""

                            if show_per_page_roles:
                                classification = _classify_conflict_page(
                                    page_url, winner, query, p, audit_lookup_for_conflict
                                )
                                st.markdown(
                                    f"<div style='background:#12121f; border-left:4px solid {classification['color']}; "
                                    f"padding:0.8rem; margin:0.6rem 0; border-radius:0 6px 6px 0;'>"
                                    f"<div style='display:flex; justify-content:space-between; align-items:start; gap:0.5rem;'>"
                                    f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.8rem; color:#e8e8f0;'>"
                                    f"{shorten_url(page_url)}{marker}</div>"
                                    f"<span style='font-size:0.65rem; color:{classification['color']}; "
                                    f"background:{classification['color']}22; padding:0.15rem 0.5rem; border-radius:3px; "
                                    f"white-space:nowrap;'>{classification['role']}</span></div>"
                                    f"<div style='font-size:0.7rem; color:#6b6b8a; margin-top:0.2rem;'>"
                                    f"pos {p.get('position','?')} · {p.get('clicks',0)} clicks · "
                                    f"{p.get('impressions',0):,} impressions</div>"
                                    f"<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600; margin-top:0.6rem;'>"
                                    f"{classification['label']}</div>"
                                    f"<div style='font-size:0.8rem; color:#c8b4ff; margin-top:0.3rem; line-height:1.5;'>"
                                    f"{classification['action_html']}</div>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                            else:
                                st.markdown(
                                    f"- `{shorten_url(page_url)}` · pos {p.get('position','?')} · "
                                    f"{p.get('clicks',0)} cl · {p.get('impressions',0):,} impr{marker}"
                                )

                        # Action instructions (rendered as markdown) — only for non-role types
                        # (role types already have richer per-page instructions above)
                        if action_text and not show_per_page_roles:
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

                        # ── Rewrite content button per page with issues ──
                        # Only for pages that are NOT being redirected (redirect + rewrite = contradictory)
                        # Build set of pages that WILL be redirected (for suppressing rewrite button)
                        redirect_losers_set = set()
                        if tk in ("true_duplicate", "duplicate_categories"):
                            from utils.site_patterns import get_sale_patterns as _gsp
                            _sale_pats = _gsp()
                            from urllib.parse import urlparse as _up2
                            _winner_p = _up2(normalize_url(winner)).path.rstrip("/")
                            _winner_parent = "/".join(_winner_p.split("/")[:-1]) if "/" in _winner_p else ""
                            for rp in pages:
                                rp_norm = normalize_url(rp.get("page", ""))
                                rp_path = _up2(rp_norm).path.rstrip("/")
                                rp_parent = "/".join(rp_path.split("/")[:-1]) if "/" in rp_path else ""
                                if rp_norm == normalize_url(winner):
                                    continue
                                if any(sp in rp.get("page", "").lower() for sp in _sale_pats):
                                    continue
                                if _winner_p and rp_path.startswith(_winner_p + "/"):
                                    continue
                                if _winner_parent and rp_parent == _winner_parent and _winner_parent != "":
                                    continue  # sibling category
                                from utils.page_profile import build_page_profile as _bpp
                                if _bpp(rp.get("page", "")).get("page_type") == "product":
                                    continue
                                # Different-purpose detection: loser serves a more specific intent
                                _w_segs = [s for s in _winner_p.split("/") if s]
                                _l_segs = [s for s in rp_path.split("/") if s]
                                _deeper = len(_l_segs) > len(_w_segs)
                                # Get winner title from pages list
                                _wt = next((pp.get("title", "") for pp in pages if normalize_url(pp.get("page", "")) == normalize_url(winner)), "") or ""
                                _w_title_words = set(_wt.lower().split())
                                _l_title = rp.get("title", "") or ""
                                _l_title_words = set(_l_title.lower().split())
                                _has_extra_words = bool(_l_title_words - _w_title_words) if _w_title_words and _l_title_words else False
                                _w_tree = _w_segs[0] if _w_segs else ""
                                _l_tree = _l_segs[0] if _l_segs else ""
                                _diff_tree = _w_tree != _l_tree and _w_tree and _l_tree
                                if _deeper or _has_extra_words or _diff_tree:
                                    continue  # different purpose — keep both
                                redirect_losers_set.add(rp_norm)

                        for p in pages:
                            p_url = p.get("page", "")
                            p_norm = normalize_url(p_url)
                            p_short = shorten_url(p_url)
                            rewrite_key = f"_cannibal_rewrite_{stable_hash(p_url + query)}"

                            # Collect all issues for this specific page from action_text
                            page_issues = []
                            if action_text and p_short in action_text:
                                page_issues.append("See issues above")
                            # Add quality verdict
                            from utils.quality_check_runner import quality_key as _qk_sc
                            q_data = st.session_state.get(_qk_sc(p_url), {})
                            if isinstance(q_data, dict) and q_data.get("verdict") in ("REWRITE", "IMPROVE"):
                                page_issues.extend(q_data.get("main_issues", []))
                                page_issues.extend(q_data.get("specific_fixes", []))

                            if rewrite_key in st.session_state:
                                rw = st.session_state[rewrite_key]
                                has_split = isinstance(rw, dict) and (rw.get("top_html") or rw.get("bottom_html"))
                                has_single = isinstance(rw, dict) and rw.get("html") and not has_split

                                if has_split:
                                    st.markdown(f"**✅ Rewritten texts for `{p_short}`:**")

                                    # TOP TEXT
                                    top_html = rw.get("top_html", "")
                                    if top_html:
                                        st.markdown("**📌 TOP TEXT** (paste in Magento → Category → Description, ABOVE product grid)")
                                        st.markdown(
                                            f"<div style='background:#1a1a2e; border:1px solid #33dd88; border-radius:6px; padding:1rem; margin:0.5rem 0;'>{top_html}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        st.text_area(
                                            "Top text HTML (select all + copy)",
                                            value=top_html,
                                            height=120,
                                            key=f"ta_top_{rewrite_key}",
                                        )

                                    # BOTTOM TEXT — includes FAQ schema merged in
                                    bottom_html = rw.get("bottom_html", "")
                                    faq_schema = rw.get("faq_schema")
                                    if isinstance(faq_schema, dict) and faq_schema.get("mainEntity"):
                                        import json as _json
                                        schema_script = f'<script type="application/ld+json">\n{_json.dumps(faq_schema, ensure_ascii=False, indent=2)}\n</script>'
                                        bottom_html = bottom_html + "\n" + schema_script

                                    if bottom_html:
                                        st.markdown("**📌 BOTTOM TEXT + FAQ SCHEMA** (paste in Magento → Category → Description, BELOW product grid. Schema is included at the end.)")
                                        st.markdown(
                                            f"<div style='background:#1a1a2e; border:1px solid #5533ff; border-radius:6px; padding:1rem; margin:0.5rem 0;'>{rw.get('bottom_html', '')}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        st.text_area(
                                            "Bottom text + FAQ schema HTML (select all + copy — paste as ONE block)",
                                            value=bottom_html,
                                            height=350,
                                            key=f"ta_bottom_{rewrite_key}",
                                        )

                                    fixed = rw.get("issues_fixed", [])
                                    if fixed:
                                        st.caption("Issues fixed: " + " · ".join(fixed))

                                    combined = (top_html or "") + "\n\n<!-- PRODUCT GRID -->\n\n" + (bottom_html or "")
                                    st.download_button(
                                        f"⬇ Download all",
                                        data=combined,
                                        file_name=f"{p_url.split('/')[-1] or 'page'}_rewrite.html",
                                        mime="text/html",
                                        key=f"dl_{rewrite_key}",
                                    )

                                elif has_single:
                                    # Fallback for old format (single html field)
                                    st.markdown(f"**✅ Rewritten text for `{p_short}`** ({rw.get('word_count', '?')} words):")
                                    st.markdown(
                                        f"<div style='background:#1a1a2e; border:1px solid #2a2a40; border-radius:6px; padding:1rem; margin:0.5rem 0;'>{rw['html']}</div>",
                                        unsafe_allow_html=True,
                                    )
                                    st.text_area("HTML source", value=rw["html"], height=300, key=f"ta_{rewrite_key}")
                                    st.download_button(f"⬇ Download", data=rw["html"], file_name=f"{p_url.split('/')[-1]}_rewrite.html", mime="text/html", key=f"dl_{rewrite_key}")
                            elif page_issues or (isinstance(q_data, dict) and q_data.get("verdict") == "REWRITE"):
                                # Don't show rewrite for pages being redirected (contradictory)
                                if p_norm in redirect_losers_set:
                                    st.caption(f"↗ `{p_short}` will be 301 redirected — no rewrite needed")
                                elif st.button(f"📝 Rewrite content for {p_short}", key=f"btn_{rewrite_key}"):
                                    with st.spinner(f"AI rewriting content for {p_short}..."):
                                        try:
                                            _generate_cannibal_rewrite(p_url, query, page_issues, action_text, rewrite_key)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Error: {e}")

                        # For true_duplicate + duplicate_categories: show redirect instructions
                        # BUT skip pages that serve a different PURPOSE (sale/rea pages, filter views)
                        if tk in ("true_duplicate", "duplicate_categories"):
                            losers = [p["page"] for p in pages if normalize_url(p["page"]) != normalize_url(winner)]
                            # Filter out pages that should NOT be redirected:
                            # 1. Sale/discount pages (serve different purpose) — from config, not hardcoded
                            # 2. Sub-categories of the winner (they're children, not duplicates)
                            # 3. Product pages (they're products, not duplicate categories)
                            from utils.site_patterns import get_sale_patterns
                            sale_patterns = get_sale_patterns()
                            from urllib.parse import urlparse as _up
                            winner_url_path = _up(normalize_url(winner)).path.rstrip("/")

                            real_losers = []
                            skipped_losers = []
                            for l in losers:
                                l_lower = l.lower()
                                l_norm = normalize_url(l)
                                l_url_path = _up(l_norm).path.rstrip("/")
                                skip_reason = None

                                # Parent paths for sibling detection
                                winner_parent = "/".join(winner_url_path.split("/")[:-1]) if "/" in winner_url_path else ""
                                loser_parent = "/".join(l_url_path.split("/")[:-1]) if "/" in l_url_path else ""

                                if any(sp in l_lower for sp in sale_patterns):
                                    skip_reason = "sale/discount page — keep, differentiate meta + add link to main category"
                                elif winner_url_path and l_url_path.startswith(winner_url_path + "/"):
                                    skip_reason = "sub-category of winner — keep, differentiate meta + add link to parent"
                                elif winner_parent and loser_parent == winner_parent and winner_parent != "":
                                    # SIBLINGS: same parent directory (e.g. /dildos/klassisk-dildo + /dildos/dildo-maskin)
                                    skip_reason = f"sibling category under {winner_parent}/ — keep, each targets a different product type"
                                else:
                                    from utils.page_profile import build_page_profile
                                    l_profile = build_page_profile(l)
                                    if l_profile.get("page_type") == "product":
                                        skip_reason = "product page — keep, differentiate meta + ensure assigned to category"

                                # Different-purpose detection: loser serves a more specific intent
                                if not skip_reason:
                                    _w_segs = [s for s in winner_url_path.split("/") if s]
                                    _l_segs = [s for s in l_url_path.split("/") if s]
                                    _deeper = len(_l_segs) > len(_w_segs)
                                    # Get winner title from pages list
                                    _wt = next((pp.get("title", "") for pp in pages if normalize_url(pp.get("page", "")) == normalize_url(winner)), "") or ""
                                    _w_title_words = set(_wt.lower().split())
                                    # Get loser title from pages list
                                    _lt = next((pp.get("title", "") for pp in pages if normalize_url(pp.get("page", "")) == l_norm), "") or ""
                                    _l_title_words = set(_lt.lower().split())
                                    _has_extra_words = bool(_l_title_words - _w_title_words) if _w_title_words and _l_title_words else False
                                    _w_tree = _w_segs[0] if _w_segs else ""
                                    _l_tree = _l_segs[0] if _l_segs else ""
                                    _diff_tree = _w_tree != _l_tree and _w_tree and _l_tree
                                    if _deeper or _has_extra_words or _diff_tree:
                                        skip_reason = "different purpose — keep both, differentiate meta + add cross-links"

                                if skip_reason:
                                    skipped_losers.append((l, skip_reason))
                                else:
                                    real_losers.append(l)

                            if skipped_losers:
                                st.info(
                                    f"**{len(skipped_losers)} page(s) kept (not redirected) — add links instead:**"
                                )
                                for s_url, reason in skipped_losers:
                                    st.markdown(f"- `{shorten_url(s_url)}` — {reason}")
                                    st.markdown(
                                        f"  → Add link to winner: `<a href=\"{winner}\">{query}</a>`"
                                    )

                            if real_losers:
                                st.markdown("**301 redirect (paste in Magento URL Rewrite Management):**")
                                for l in real_losers[:5]:
                                    st.code(f"{l}  →  {winner}", language="text")
                                if tk == "duplicate_categories":
                                    st.info("After redirect: move all products from loser category to winner category in Magento → Catalog → Categories.")

    # ── TAB 2: CREATE ─────────────────────────────────────────
    with tab2:
        creates = _pages_to_create()
        st.markdown(f"### {len(creates)} new pages/articles to create")
        _novice_box(
            what=(
                "People are searching Google for these topics right now — but your site has NO page "
                "that targets those searches. So Google sends that traffic to your competitors instead. "
                "Each item in the list is a missing page the AI has identified based on your GSC data, "
                "topic clusters, and ideal site architecture."
            ),
            why=(
                "You can't rank for a keyword if you don't have a page about it. Creating a missing "
                "category, guide, or blog post is the most direct way to grow traffic. The AI only "
                "lists pages where there is proven search demand AND a realistic chance for your "
                "domain to rank — so this is not a wish list, it's a work list."
            ),
            how=(
                "1. Pick an item from the list below. Look at its <strong>Target keyword</strong> — "
                "that is what the new page must target.<br>"
                "2. Create the page in Magento:<br>"
                "&nbsp;&nbsp;• Category page → Catalog → Categories → Add Subcategory.<br>"
                "&nbsp;&nbsp;• CMS page → Content → Pages → Add New Page.<br>"
                "&nbsp;&nbsp;• Blog post → whatever blog module you use.<br>"
                "3. Use the tool's <strong>Content Generator</strong> (left menu) to AI-write the body "
                "text using the target keyword.<br>"
                "4. Set the meta title and description (aim for the target keyword in both).<br>"
                "5. Add internal links TO the new page from 2–3 related existing pages (otherwise "
                "Google won't find it quickly)."
            ),
            border="#5bb4d4",
        )
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
                if c.get("already_exists"):
                    st.markdown(f"- ~~{label}~~ — **SKIP: {c['already_exists']}**")
                else:
                    st.markdown(f"- {label}")
                if c.get("keyword"):
                    st.markdown(f"  <div style='color:#c8b4ff; font-size:0.75rem; margin-left:1rem;'>Keywords: {c.get('keyword', '')}</div>", unsafe_allow_html=True)
                if c.get("why"):
                    st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>{c.get('why', '')[:200]}</div>", unsafe_allow_html=True)
                if c.get("link_from"):
                    st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>Link from: {c.get('link_from', '')}</div>", unsafe_allow_html=True)

    # ── TAB 3: REDIRECT ──────────────────────────────────────
    with tab3:
        from utils import action_ui as _aui
        redirects = _pages_to_redirect()
        st.markdown(f"### {len(redirects)} broken pages to redirect")
        _novice_box(
            what=(
                "These URLs used to exist on your site but now return an error (404 Not Found, 410 "
                "Gone, etc.). Some of them still have <strong>backlinks</strong> — meaning other "
                "websites are linking to them. Every broken link is a dead end for both Google and "
                "human visitors."
            ),
            why=(
                "Backlinks are like votes of trust from other websites to yours. When a URL is broken, "
                "that vote is lost — the trust evaporates. A 301 redirect transfers most of that "
                "trust to a new URL, so you keep the SEO value. URLs marked 🔴 HIGH below have "
                "backlinks — fix those FIRST or you're throwing away free ranking power."
            ),
            how=(
                "1. Start with the 🔴 HIGH priority items (they have backlinks).<br>"
                "2. For each broken URL, find the closest still-alive page on your site that covers "
                "the same topic. If no good match exists, redirect to the nearest category page "
                "(never to the homepage — that's a soft signal Google penalizes).<br>"
                "3. In Magento Admin → Marketing → SEO &amp; Search → URL Rewrites → Add URL Rewrite:<br>"
                "&nbsp;&nbsp;• Store: your store<br>"
                "&nbsp;&nbsp;• Request Path: the broken URL path (e.g. <code>/old-page</code>)<br>"
                "&nbsp;&nbsp;• Target Path: the new destination path<br>"
                "&nbsp;&nbsp;• Redirect Type: <strong>Permanent (301)</strong><br>"
                "4. Test by visiting the old URL in an incognito window — it should land on the new page."
            ),
            border="#ffaa33",
        )
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "These pages return 4xx errors. Redirect to closest matching page to preserve any link equity.</p>",
            unsafe_allow_html=True,
        )
        if not redirects:
            st.success("No broken pages detected")
        else:
            show_done = _aui.filter_toolbar("redirect", len(redirects))
            visible = _aui.filter_visible(redirects, "redirect", lambda r: stable_hash(r["url"]), show_done)
            visible = visible[:30]
            for r in visible:
                priority = "🔴 HIGH" if r["referring_domains"] > 0 else "⚪ LOW"
                content = (
                    f"<div>{priority} <code>{r['url']}</code> "
                    f"<span style='color:#6b6b8a;'>({r['status']})</span> · "
                    f"{r['referring_domains']} backlinks</div>"
                    f"<div style='color:#9b9bb8; font-size:0.8rem; margin-left:1rem; margin-top:0.2rem;'>"
                    f"{r['action']}</div>"
                )
                _aui.render_action_row("redirect", stable_hash(r["url"]), content, key_suffix="t3")
            _aui.bulk_done_button("redirect", [stable_hash(r["url"]) for r in visible], key_suffix="t3")

    # ── TAB 4: NOINDEX ───────────────────────────────────────
    with tab4:
        noindex = _pages_to_noindex()
        st.markdown(f"### {len(noindex)} pages to noindex / block in robots.txt")
        _novice_box(
            what=(
                "Magento automatically creates URLs for filters, sort orders, pagination, session "
                "IDs, and other technical things (e.g. <code>?dir=asc</code>, <code>?p=2</code>, "
                "<code>?SID=abc123</code>). These are NOT real pages — they are just different views "
                "of the same category. Thin pages and near-duplicates also show up here."
            ),
            why=(
                "Google has a limited <strong>crawl budget</strong> for your site — a maximum number "
                "of URLs it will visit each day. If 80% of your crawl budget is wasted on junk filter "
                "URLs, Google never gets to your real important pages. Blocking the junk in robots.txt "
                "or adding a <code>noindex</code> tag tells Google: \"don't bother with these, focus "
                "on the good stuff.\""
            ),
            how=(
                "<strong>For filter/parameter URLs (faceted):</strong> block in robots.txt — faster "
                "than noindex because Google doesn't even have to visit the page. Open your "
                "<code>robots.txt</code> file (in Magento root) and paste the rules shown below each "
                "group.<br><br>"
                "<strong>For thin / duplicate pages:</strong><br>"
                "1. Open the page in Magento.<br>"
                "2. Go to the <strong>Design</strong> tab (or \"Custom Layout Update\" field).<br>"
                "3. Paste: <code>&lt;meta name=\"robots\" content=\"noindex,follow\"&gt;</code><br>"
                "4. Save. Google will drop it from the index on its next crawl (1–4 weeks).<br><br>"
                "Do NOT noindex pages that already rank or have backlinks — use Merge or Redirect "
                "instead for those."
            ),
            border="#9b9bb8",
        )
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

        if noindex:
            from utils import action_ui as _aui_t4
            show_done_t4 = _aui_t4.filter_toolbar("noindex", len(noindex), key_prefix="t4")
        else:
            show_done_t4 = False

        for type_key, items in by_type.items():
            with st.expander(f"{type_key.upper()} ({len(items)} pages)", expanded=False):
                if type_key == "faceted":
                    st.info("Magento 1.9 faceted URLs. Block via robots.txt:")
                    st.code("Disallow: /*?dir=\nDisallow: /*?limit=\nDisallow: /*?mode=\nDisallow: /*?order=\nDisallow: /*?p=\nDisallow: /*?SID=", language="text")
                from utils import action_ui as _aui_t4i
                visible_items = _aui_t4i.filter_visible(items, "noindex", lambda it: stable_hash(it["url"]), show_done_t4)
                visible_items = visible_items[:30]
                for item in visible_items:
                    content = (
                        f"<div><code>{item['url']}</code></div>"
                        f"<div style='color:#9b9bb8; font-size:0.8rem; margin-left:1rem; margin-top:0.2rem;'>"
                        f"{item['reason']}</div>"
                    )
                    _aui_t4i.render_action_row("noindex", stable_hash(item["url"]), content, key_suffix=f"t4_{type_key}")
                _aui_t4i.bulk_done_button("noindex", [stable_hash(it["url"]) for it in visible_items], key_suffix=f"t4_{type_key}")

    # ── TAB 5: DELETE ────────────────────────────────────────
    with tab5:
        _novice_box(
            what=(
                "Pages that currently exist on your site but look dead: no visitors, no backlinks, "
                "very little content, not part of any topic group. The tool also flags "
                "<strong>orphan pages</strong> — pages that nothing on your site links to (customers "
                "can only reach them by typing the URL directly)."
            ),
            why=(
                "Every page on your site is evaluated by Google as part of the overall site quality. "
                "A site with lots of weak, empty, useless pages is treated as a low-quality site. "
                "Cleaning out dead weight literally lifts the ranking of your <em>remaining</em> pages. "
                "BUT: be careful — some \"orphans\" have hidden value (backlinks, or they just lost "
                "their link). The tool sorts them for you so you don't delete the wrong thing."
            ),
            how=(
                "<strong>Go through the 5 buckets below in this order:</strong><br><br>"
                "1. <strong>📝 Needs content (products)</strong> — NEVER delete. These are real "
                "products you can sell. Add a description in Magento and assign to a category.<br>"
                "2. <strong>🔗 Reconnect</strong> — NEVER delete. These pages have traffic or are in "
                "topic clusters; they just lost their internal link. Add a link from the relevant "
                "category or parent page.<br>"
                "3. <strong>↗ Redirect</strong> — do NOT delete outright. These have backlinks. "
                "Set up a 301 redirect to the closest matching page (Magento → Marketing → URL "
                "Rewrites) so you keep the SEO value.<br>"
                "4. <strong>🗑 True orphans</strong> — safe to delete in Magento (Catalog → Categories "
                "/ Pages → select → Delete). Also set up a 301 redirect to the nearest relevant page "
                "as a safety net.<br>"
                "5. <strong>❓ Investigate</strong> — edge cases. Open each URL in your browser and "
                "judge manually.<br><br>"
                "<strong>Alternative to deleting:</strong> if unsure, just add the page to robots.txt "
                "<code>Disallow:</code> — it stays live for the rare direct visitor, but Google stops "
                "wasting crawl budget on it."
            ),
            border="#ff4455",
        )
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

            from utils import action_ui as _aui_t5

            def _render_orphan_bucket(label_emoji_count, info_msg, info_kind, bucket_items, action_type, suffix):
                with st.expander(label_emoji_count, expanded=False):
                    if info_kind == "info":
                        st.info(info_msg)
                    elif info_kind == "warn":
                        st.warning(info_msg)
                    if not bucket_items:
                        return
                    show = _aui_t5.filter_toolbar(action_type, len(bucket_items), key_prefix=f"t5_{suffix}_")
                    visible = _aui_t5.filter_visible(bucket_items, action_type, lambda o: stable_hash(o["url"]), show)
                    visible = visible[:50]
                    for o in visible:
                        bl_extra = f" · {o.get('referring_domains', 0)} backlinks" if action_type == "redirect" else ""
                        content = (
                            f"<div><code>{o['url']}</code> "
                            f"<span style='color:#6b6b8a;'>({o.get('page_type', '?')}, {o.get('word_count', 0)}w{bl_extra})</span></div>"
                            f"<div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem; margin-top:0.2rem;'>"
                            f"{o.get('reason', '')}</div>"
                        )
                        _aui_t5.render_action_row(action_type, stable_hash(o["url"]), content, key_suffix=f"t5_{suffix}")
                    _aui_t5.bulk_done_button(action_type, [stable_hash(o["url"]) for o in visible], key_suffix=f"t5_{suffix}")

            if orphan_buckets["needs_content"]:
                _render_orphan_bucket(
                    f"📝 Products needing content ({len(orphan_buckets['needs_content'])}) — DO NOT delete",
                    "These are PRODUCT pages with thin/missing content. They can still be sold — add descriptions in Magento and assign to the right category. Never auto-delete products.",
                    "info", orphan_buckets["needs_content"], "needs_content", "needs",
                )

            _render_orphan_bucket(
                f"🔗 Reconnect ({len(orphan_buckets['reconnect'])}) — DO NOT delete",
                "These pages have traffic, backlinks, or are in topic clusters. They lost their internal link but should be RECONNECTED via category navigation, not deleted.",
                "info", orphan_buckets["reconnect"], "reconnect", "rec",
            )

            _render_orphan_bucket(
                f"↗ Redirect ({len(orphan_buckets['redirect'])}) — preserve link equity",
                "These pages have backlinks but zero traffic. 301-redirect them to the closest live, related page to preserve link equity. Do NOT just delete — you'd lose the backlinks.",
                "info", orphan_buckets["redirect"], "redirect", "redir",
            )

            _render_orphan_bucket(
                f"🗑 True orphans to delete ({len(orphan_buckets['delete'])})",
                "These have NO traffic, NO backlinks, NO cluster, and thin content. Safe to delete.",
                "warn", orphan_buckets["delete"], "delete", "del",
            )

            if orphan_buckets["investigate"]:
                _render_orphan_bucket(
                    f"❓ Investigate ({len(orphan_buckets['investigate'])})",
                    "Edge cases — manual review needed.",
                    "info", orphan_buckets["investigate"], "delete", "inv",
                )
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
            from utils import action_ui as _aui_id
            show_id = _aui_id.filter_toolbar("delete", len(ideal_deletes), key_prefix="t5_ideal_")
            visible_id = _aui_id.filter_visible(ideal_deletes, "delete", lambda d: stable_hash(d.get("url", "")), show_id)
            visible_id = visible_id[:30]
            for d in visible_id:
                content = (
                    f"<div><code>{d.get('url', '')}</code></div>"
                    f"<div style='color:#9b9bb8; font-size:0.8rem; margin-left:1rem; margin-top:0.2rem;'>"
                    f"{d.get('why', '')}</div>"
                )
                _aui_id.render_action_row("delete", stable_hash(d.get("url", "")), content, key_suffix="t5_ideal")
            _aui_id.bulk_done_button("delete", [stable_hash(d.get("url", "")) for d in visible_id], key_suffix="t5_ideal")
            st.markdown("---")

        st.markdown("#### 📊 Data-driven candidates (no traffic, no backlinks, thin content)")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "Pages with: 0 clicks, <10 impressions, 0 backlinks, <200 words.</p>",
            unsafe_allow_html=True,
        )
        if not deletes:
            st.success("No clearly deletable pages from data analysis")
        else:
            from utils import action_ui as _aui_dd
            show_dd = _aui_dd.filter_toolbar("delete", len(deletes), key_prefix="t5_data_")
            visible_dd = _aui_dd.filter_visible(deletes, "delete", lambda d: stable_hash(d["url"]), show_dd)
            visible_dd = visible_dd[:30]
            for d in visible_dd:
                content = (
                    f"<div><code>{d['url']}</code> "
                    f"<span style='color:#6b6b8a;'>({d['page_type']}) · "
                    f"{d['word_count']} words · {d['impressions']} impressions</span></div>"
                )
                _aui_dd.render_action_row("delete", stable_hash(d["url"]), content, key_suffix="t5_data")
            _aui_dd.bulk_done_button("delete", [stable_hash(d["url"]) for d in visible_dd], key_suffix="t5_data")

    # ── TAB 6: BLOGS TO REVIEW ───────────────────────────────
    with tab6:
        blogs = _blogs_to_review()
        st.markdown(f"### {len(blogs)} blog/guide pages needing review")
        _novice_box(
            what=(
                "Blog posts and guides that either (a) the AI quality scorer rated as weak — vague, "
                "outdated, thin, or not really useful — or (b) have gotten ZERO traffic. Unlike a "
                "category page, a blog post only exists to bring in readers; if nobody reads it, "
                "it's pure dead weight."
            ),
            why=(
                "Google uses a concept called \"site quality\" — the average quality of ALL pages on "
                "your site. One great category page + fifty weak blog posts averages out to \"weak "
                "site.\" Removing or rewriting bad blog posts physically raises your whole site's "
                "ranking potential. This is one of the easiest wins on older sites with years of "
                "blogging history."
            ),
            how=(
                "Open each blog expander and pick one of four actions:<br><br>"
                "<strong>1. Rewrite</strong> — if the topic is still relevant but the article is "
                "weak. Go to Quick Wins → find the blog → click \"Generate content\" to get an "
                "AI-written replacement. Paste into Magento over the old content.<br>"
                "<strong>2. Delete</strong> — if the topic is irrelevant, outdated, or covered "
                "elsewhere. Delete in Magento AND set up a 301 redirect to the closest remaining "
                "relevant article (never to a product or homepage).<br>"
                "<strong>3. Merge</strong> — if two blogs cover nearly the same topic, pick the "
                "stronger one, copy any unique value from the weaker one into it, then 301 redirect "
                "weaker → stronger.<br>"
                "<strong>4. Redirect</strong> — if a newer/better page already exists for this topic, "
                "just 301 the weak blog to that page.<br><br>"
                "Start with the 🔴 REWRITE verdicts — those are the posts that actively hurt rankings."
            ),
            border="#ffaa33",
        )
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "Blog posts with REWRITE verdict from AI quality check, or zero traffic. "
            "Either rewrite, delete, or repurpose.</p>",
            unsafe_allow_html=True,
        )
        if not blogs:
            st.success("No blogs flagged for review")
        else:
            from utils import action_ui as _aui_t6, action_status as _as_t6
            show_b = _aui_t6.filter_toolbar("blog_review", len(blogs), key_prefix="t6")
            visible_b = _aui_t6.filter_visible(blogs, "blog_review", lambda b: stable_hash(b["url"]), show_b)
            visible_b = visible_b[:30]
            for b in visible_b:
                bid = stable_hash(b["url"])
                done = _as_t6.is_done("blog_review", bid)
                badge = " " + _aui_t6.done_badge_html("blog_review", bid) if done else ""
                row_cols = st.columns([8, 2])
                with row_cols[0]:
                    with st.expander(f"[{b['verdict']}] {shorten_url(b['url'])} · {b['impressions']} impressions{badge}"):
                        st.markdown(f"**Score:** {b['score']}/10")
                        st.markdown(f"**Issue:** {b['summary']}")
                        st.markdown(f"**Options:**")
                        st.markdown("1. **Rewrite** — use Quick Wins to generate new content")
                        st.markdown("2. **Delete** — if topic is irrelevant or covered elsewhere")
                        st.markdown("3. **Merge** — combine with another article on same topic")
                        st.markdown("4. **Redirect** — if better content exists, 301 to that page")
                with row_cols[1]:
                    _aui_t6.mark_button("blog_review", bid, key_suffix="t6")
            _aui_t6.bulk_done_button("blog_review", [stable_hash(b["url"]) for b in visible_b], key_suffix="t6")

    # ── TAB 7: TOPIC GAPS ────────────────────────────────────
    with tab7:
        gaps = st.session_state.get("content_gaps", []) or []
        st.markdown(f"### {len(gaps)} topic clusters with content gaps")
        _novice_box(
            what=(
                "A <strong>topic cluster</strong> is a group of pages on your site that all talk "
                "about the same broad subject (e.g. all your dildo pages form the \"dildo\" cluster). "
                "This tab shows clusters where something is going wrong at the <em>topic</em> level, "
                "not the individual page level: low click-through rate despite many impressions, too "
                "few pages for the demand, or not enough backlinks pointing to the topic."
            ),
            why=(
                "Google ranks topics, not just pages. If your \"vibrator\" cluster only has 2 pages "
                "but your competitor has 20, Google sees your competitor as the expert — and all "
                "20 of their pages rank above your 2. Filling topic gaps means you compete at the "
                "cluster level, which lifts ALL your pages in that topic at once."
            ),
            how=(
                "<strong>For each 🔴 High priority gap:</strong><br>"
                "1. Open the expander and read the specific issues listed.<br>"
                "2. Based on the issues, take one of these actions:<br>"
                "&nbsp;&nbsp;• <strong>Poor CTR but good impressions</strong>: rewrite the meta title "
                "+ description on the top-ranking page in this cluster (use Quick Wins view).<br>"
                "&nbsp;&nbsp;• <strong>Too few pages / thin coverage</strong>: go to the Create tab "
                "above and create 2–4 new supporting pages (a buying guide, FAQ, comparison, "
                "\"best of\" list) — all linking to each other and to the main category.<br>"
                "&nbsp;&nbsp;• <strong>Pages split across too many pages</strong>: go to the Merge tab "
                "— the same conflicts are flagged there with specific merge instructions.<br>"
                "&nbsp;&nbsp;• <strong>Missing backlinks</strong>: this is an off-site task — do "
                "outreach, guest posts, or product PR to get links pointing to the main cluster page.<br>"
                "3. Then open the <strong>Cluster Balance</strong> tab to visually confirm the "
                "cluster now looks healthy (green)."
            ),
            border="#c8b4ff",
        )
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
            from utils import action_ui as _aui_t7, action_status as _as_t7
            high = [g for g in gaps if isinstance(g, dict) and g.get("priority") == "high"]
            medium = [g for g in gaps if isinstance(g, dict) and g.get("priority") == "medium"]
            all_gaps = high + medium

            def _gap_id(g):
                return stable_hash(f"{g.get('topic', '')}::{g.get('queries', 0)}")

            show_gaps = _aui_t7.filter_toolbar("topic_gap", len(all_gaps), key_prefix="t7")

            def _render_gap_section(gap_list, header):
                if not gap_list:
                    return
                visible = _aui_t7.filter_visible(gap_list, "topic_gap", _gap_id, show_gaps)[:30]
                if not visible:
                    return
                st.markdown(header)
                for g in visible:
                    gid = _gap_id(g)
                    done = _as_t7.is_done("topic_gap", gid)
                    badge = " " + _aui_t7.done_badge_html("topic_gap", gid) if done else ""
                    cols = st.columns([8, 2])
                    with cols[0]:
                        with st.expander(
                            f"{g.get('topic','?')} · {g.get('impressions',0):,} impressions · {g.get('queries',0)} queries{badge}"
                        ):
                            for issue in g.get("issues", []):
                                st.markdown(f"- {issue}")
                            if header.startswith("#### 🔴"):
                                st.markdown(
                                    "<div style='color:#9b9bb8; font-size:0.75rem; margin-top:0.5rem;'>"
                                    "Action: review in Topic Clusters view for consolidation, new content, or link building.</div>",
                                    unsafe_allow_html=True,
                                )
                    with cols[1]:
                        _aui_t7.mark_button("topic_gap", gid, key_suffix="t7")
                _aui_t7.bulk_done_button(
                    "topic_gap",
                    [_gap_id(g) for g in visible],
                    key_suffix=f"t7_{header[:8]}",
                )

            _render_gap_section(high, "#### 🔴 High priority")
            _render_gap_section(medium, "#### 🟡 Medium priority")

    # ── TAB 8: UNCLUSTERED PAGES ─────────────────────────────
    with tab8:
        st.markdown(f"### Unclustered pages — assign to a topic")
        _novice_box(
            what=(
                "A <strong>topic cluster</strong> is a group of pages about the same subject. The "
                "pages listed here are NOT part of any cluster — they exist, but the tool doesn't "
                "know which topic they belong to. To Google's topical-authority algorithm, they are "
                "effectively invisible: they contribute nothing to showing expertise in any subject."
            ),
            why=(
                "Google rewards sites where related pages are clearly connected around a central "
                "topic (think of it like a well-organized library with clear sections versus a "
                "random pile of books). Every page you assign to a cluster makes that topic stronger. "
                "Unclustered pages are wasted potential — usually just one dropdown-pick away from "
                "becoming useful ranking fuel."
            ),
            how=(
                "1. Use the dropdown next to each page to pick the cluster it belongs to.<br>"
                "2. Look at the URL — it usually tells you the topic. Examples:<br>"
                "&nbsp;&nbsp;• <code>/bondage-bdsm/handklovar</code> → pick \"bondage\" or \"bdsm\"<br>"
                "&nbsp;&nbsp;• <code>/sexleksaker/vibratorer/bullet</code> → pick \"vibratorer\"<br>"
                "&nbsp;&nbsp;• <code>/blogg/guide-till-dildos</code> → pick \"dildos\"<br>"
                "3. If no cluster fits: leave it blank. That's fine — you're not forced to assign.<br>"
                "4. You do NOT have to finish them all today. Do 25 at a time. Click <strong>Save "
                "cluster assignments</strong>. Come back later for the next batch.<br>"
                "5. Pages are sorted by traffic (highest first) so you fix the most impactful ones first."
            ),
            border="#5bb4d4",
        )
        cluster_names = sorted(set(c.get("topic", "") for c in clusters_list if c.get("topic")))

        # ── Diagnostic: are unclustered URLs really unclustered, or is
        # this a URL-normalization mismatch (www vs non-www, query
        # params, trailing slash)? Compare audit URL set vs cluster URL
        # set after re-normalizing both, show overlap stats + examples.
        with st.expander("🔬 Diagnose: is the count real or a normalization issue?", expanded=False):
            from utils.ui_helpers import normalize_url as _nu_dx
            _audit_results = st.session_state.get("audit_results", []) or []
            _topic_clusters = st.session_state.get("topic_clusters", {}) or {}
            _page_topics = _topic_clusters.get("page_topics", {}) or {}

            _audit_norms = {_nu_dx(r.get("url", "")) for r in _audit_results if r.get("url")}
            _cluster_norms = {_nu_dx(u) for u in _page_topics.keys() if u}
            _overlap = _audit_norms & _cluster_norms
            _audit_only = _audit_norms - _cluster_norms
            _cluster_only = _cluster_norms - _audit_norms

            d1, d2, d3 = st.columns(3)
            d1.metric("Audit URLs (normalized)", len(_audit_norms))
            d2.metric("Cluster URLs (normalized)", len(_cluster_norms))
            d3.metric("Overlap", len(_overlap))

            st.caption(
                f"**Audit-only (= unclustered):** {len(_audit_only)}  ·  "
                f"**Cluster-only (in clusters but not audited):** {len(_cluster_only)}"
            )

            # Hunt for near-matches: URLs that DIFFER only by trivial
            # things (case, www, trailing slash, query). If many appear
            # here, normalization IS the bug.
            import re as _re_dx
            def _strip_for_match(u: str) -> str:
                # Strip protocol + www + query + fragment + trailing slash, lowercase
                return _re_dx.sub(
                    r"^https?://(www\.)?|[?#].*$|/+$", "", (u or "").lower()
                )
            _audit_loose = {_strip_for_match(u): u for u in _audit_norms}
            _cluster_loose = {_strip_for_match(u): u for u in _cluster_norms}
            _loose_overlap = set(_audit_loose) & set(_cluster_loose)
            _strict_overlap_loose = {_strip_for_match(u) for u in _overlap}
            _possible_normalization_misses = _loose_overlap - _strict_overlap_loose
            if _possible_normalization_misses:
                st.warning(
                    f"⚠ Found **{len(_possible_normalization_misses)}** URL pairs that "
                    f"loosely match but DIDN'T match strictly — these are likely "
                    f"normalization issues (www, trailing slash, casing, query params)."
                )
                st.caption("First 10 mismatched pairs (audit URL ↔ cluster URL):")
                for k in list(_possible_normalization_misses)[:10]:
                    st.code(f"audit:   {_audit_loose[k]}\ncluster: {_cluster_loose[k]}", language="text")
            else:
                st.success("No loose-match misses — the unclustered count is REAL, not a normalization bug.")

            # Show 10 sample audit-only URLs so user can spot-check
            st.markdown("**Sample of 20 audit-only (unclustered) URLs — spot-check below:**")
            _sample_audit_only = sorted(_audit_only)[:20]
            for u in _sample_audit_only:
                st.code(u, language="text")

            # Show 10 sample cluster-only URLs (in clusters but not in audit)
            if _cluster_only:
                st.markdown(f"**Sample of 10 cluster-only URLs (in clusters but missing from audit):**")
                for u in sorted(_cluster_only)[:10]:
                    st.code(u, language="text")

            # CSV download for the FULL audit-only list
            import io as _io_dx
            csv_buf = _io_dx.StringIO()
            csv_buf.write("normalized_url,page_type,impressions,clicks,word_count,title\n")
            _audit_by_norm = {_nu_dx(r.get("url", "")): r for r in _audit_results if r.get("url")}
            for u in sorted(_audit_only):
                r = _audit_by_norm.get(u, {})
                _t = (r.get("title") or "").replace('"', "'").replace("\n", " ")
                csv_buf.write(
                    f'"{u}","{r.get("page_type", "")}",'
                    f'{r.get("impressions", 0) or 0},'
                    f'{r.get("clicks", 0) or 0},'
                    f'{r.get("word_count", 0) or 0},'
                    f'"{_t}"\n'
                )
            st.download_button(
                f"⬇ Download full unclustered list ({len(_audit_only)} URLs) as CSV",
                data=csv_buf.getvalue(),
                file_name="unclustered_urls.csv",
                mime="text/csv",
                key="dx_dl_unclustered",
            )

        _render_unclustered(unclustered_pages, cluster_names)

    # ── TAB 9: CLUSTER BALANCE ───────────────────────────────
    with tab9:
        st.markdown(f"### Cluster balance — are your topics the right size?")
        _novice_box(
            what=(
                "Each topic cluster should ideally have between 3 and 14 pages. Think of it like a "
                "bookshelf: a topic with just 1 book looks weak to Google, but 25 books about the "
                "exact same thing is chaos. This tab color-codes your clusters so you can see at a "
                "glance which topics need more pages and which need consolidation."
            ),
            why=(
                "Google's topical authority model compares the depth of your coverage against "
                "competitors'. If the \"dildo\" search universe has 20 main subtopics and you have "
                "only 2 pages, you'll never out-rank a site with 15. And if you have 25 pages all "
                "targeting the same narrow query, they cannibalize each other. Balancing your "
                "clusters is the highest-leverage site-wide action available."
            ),
            how=(
                "<strong>Color guide:</strong><br>"
                "🔴 <strong>RED — Needs more pages</strong>: high traffic but only 1–2 pages. Big "
                "opportunity. Go to the <strong>Create</strong> tab and add 3–5 supporting pages "
                "(guide, FAQ, comparison, \"best of\" list). Use the Content Generator in the tool "
                "to AI-write them.<br><br>"
                "🟡 <strong>YELLOW — Too many pages</strong>: 15+ pages competing in the same topic. "
                "Open the page list, look for near-duplicates, and go to the <strong>Merge</strong> "
                "tab — the same conflicts are flagged there with concrete 301-redirect instructions. "
                "For pages that are genuinely different, make sure each has a unique meta title "
                "targeting a different keyword.<br><br>"
                "🟢 <strong>GREEN — Healthy</strong>: 3–14 pages. No action needed. Focus on red + "
                "yellow first.<br><br>"
                "⚪ <strong>GREY — Low priority</strong>: few pages AND low traffic. Ignore for now "
                "or come back after everything else is cleaned up."
            ),
            border="#33dd88",
        )
        _render_cluster_balance(clusters_list, audit_lookup)

    st.session_state["_site_cleanup_viewed"] = True
    st.session_state["_structure_fix_viewed"] = True  # legacy alias
