"""
Cannibalization detection from GSC data.
Identifies keywords where multiple pages compete for the same query.
"""

import pandas as pd
import numpy as np



def _classify_cannibal_type(winner, losers, pages_detail, audit_lookup=None):
    """Classify cannibalization using REAL page_type from audit_results,
    topic cluster membership, and sf_link_map structural signals."""
    import streamlit as _st
    from utils.url_helpers import (
        url_path as _path_of,
        is_sale_url as _is_sale,
        normalize_url as _nu,
        path_is_descendant,
    )

    audit_results = _st.session_state.get("audit_results", [])
    type_lookup = {}
    for ar in audit_results:
        type_lookup[_nu(ar.get("url", ""))] = ar.get("page_type", "unknown")

    # ── Additional signal: topic cluster membership ──────────
    topic_clusters = _st.session_state.get("topic_clusters")
    page_topics = topic_clusters.get("page_topics", {}) if isinstance(topic_clusters, dict) else {}
    all_urls = [winner] + list(losers)

    def _cluster_names(u):
        """Return set of cluster/topic names this URL belongs to."""
        topics = page_topics.get(u, [])
        if not topics:
            # Try normalized lookup
            topics = page_topics.get(_nu(u), [])
        return set(t.get("topic", "") for t in topics if t.get("topic"))

    winner_clusters = _cluster_names(winner)
    same_cluster = False
    different_clusters = False
    if winner_clusters:
        for loser in losers:
            loser_clusters = _cluster_names(loser)
            if loser_clusters:
                if winner_clusters & loser_clusters:
                    same_cluster = True
                else:
                    different_clusters = True

    # ── Additional signal: winner already links to losers (intentional) ──
    sf_link_map = _st.session_state.get("sf_link_map")
    winner_links_to_losers = False
    if sf_link_map and isinstance(sf_link_map, dict):
        links_from = sf_link_map.get("links_from", {})
        winner_outlinks = links_from.get(_nu(winner), [])
        loser_norms = set(_nu(l) for l in losers)
        for link_item in winner_outlinks:
            target = link_item.get("url", "") if isinstance(link_item, dict) else str(link_item)
            if _nu(target) in loser_norms:
                winner_links_to_losers = True
                break

    all_urls = [winner] + list(losers)
    page_types = {u: type_lookup.get(_nu(u), "unknown") for u in all_urls}

    # Sale/REA filter pages are stored as "category" in audit_results but
    # serve a different purpose (price filter view, not a true category).
    # Exclude them from the category count so they don't trigger
    # false-positive "duplicate_categories" classifications.
    sale_pages = [u for u in all_urls if _is_sale(u)]
    categories = [u for u in all_urls if page_types[u] == "category" and not _is_sale(u)]
    products = [u for u in all_urls if page_types[u] == "product"]
    n_cat, n_prod, n_sale = len(categories), len(products), len(sale_pages)

    def _has_prefix(urls):
        for i, u1 in enumerate(urls):
            for j, u2 in enumerate(urls):
                if i != j and (path_is_descendant(u2, u1) or path_is_descendant(u1, u2)):
                    return True
        return False

    # Build additional context notes from cluster + link signals
    _extra_notes = []
    if same_cluster:
        _extra_notes.append("Pages are in the **same topic cluster** — consolidation is safe.")
    if different_clusters:
        _extra_notes.append("Pages are in **different topic clusters** — differentiate content rather than merge.")
    if winner_links_to_losers:
        _extra_notes.append("Winner already **links to losers** — this may be intentional structure (hub→spoke).")
    _extra_suffix = "\n\n" + " ".join(_extra_notes) if _extra_notes else ""

    if n_cat >= 2 and not _has_prefix(categories):
        return {"type": "duplicate_categories",
            "action": f"**{n_cat} category pages** target the same query \u2014 true cannibalization.\n\n**What to do in Magento:**\n1. Pick ONE category to own this query (\U0001f3c6 winner)\n2. 301 redirect the loser category to the winner\n3. Move all products from loser to winner category\n4. Update winner meta to target BOTH keyword variants\n5. Click 'Generate meta' below{_extra_suffix}",
            "parent_url": None, "suggested_parent_path": None}

    if n_cat >= 2 and _has_prefix(categories):
        cat_sorted = sorted(categories, key=lambda u: len(_path_of(u)))
        parent_url = cat_sorted[0]
        outliers = [u for u in all_urls if u != parent_url and not _path_of(u).startswith(_path_of(parent_url) + "/")]
        note = ""
        if outliers:
            note = "\n\nAlso competing: " + ", ".join(_path_of(o) for o in outliers) + " \u2014 unrelated, check why they rank."
        return {"type": "category_vs_children",
            "action": f"**Parent category + sub-categories** compete. NORMAL on e-commerce.\n\n**What to do in Magento:**\n1. Parent `{_path_of(parent_url)}` targets the GENERIC query\n2. Each sub-category gets a SPECIFIC variant in meta title\n3. Ensure parent links to all sub-categories\n4. Click 'Generate meta' below{note}{_extra_suffix}",
            "parent_url": parent_url, "suggested_parent_path": None}

    if n_cat == 1 and n_prod >= 1:
        cat_url = categories[0]
        return {"type": "category_vs_products",
            "action": f"**1 category + {n_prod} product(s)** compete. Category should own the generic query.\n\n**What to do in Magento:**\n1. Optimize `{_path_of(cat_url)}` meta for the generic query\n2. Each product targets its SPECIFIC name/brand\n3. Ensure products are assigned to this category\n4. Click 'Generate meta' below{_extra_suffix}",
            "parent_url": cat_url, "suggested_parent_path": None}

    if n_prod >= 2 and n_cat == 0:
        parent_dirs = set()
        for u in products:
            segs = [s for s in _path_of(u).split("/") if s]
            parent_dirs.add("/" + "/".join(segs[:-1]) if len(segs) > 1 else "/")
        if len(parent_dirs) == 1:
            shared = next(iter(parent_dirs))
            return {"type": "products_same_parent",
                "action": f"**{n_prod} products** under `{shared}` compete.\n\n**What to do in Magento:**\n1. Each product gets UNIQUE meta with its brand/variant\n2. Ensure `{shared}` category targets the generic query\n3. Click 'Generate meta' below{_extra_suffix}",
                "parent_url": shared, "suggested_parent_path": None}
        return {"type": "products_no_category",
            "action": f"**{n_prod} products** from different areas compete, NO category targets this query.\n\n**What to do in Magento:**\n1. CREATE a new category page targeting this query\n2. Assign all competing products\n3. Write intro + meta for the generic query{_extra_suffix}",
            "parent_url": None, "suggested_parent_path": None}

    if len(all_urls) == 2:
        t = page_types.get(all_urls[0], "page")
        return {"type": "true_duplicate",
            "action": f"Two {t} pages compete.\n\n**What to do in Magento:**\n1. Keep the \U0001f3c6 WINNER\n2. Copy unique content from loser to winner\n3. 301 redirect loser \u2192 winner\n4. Update internal links{_extra_suffix}",
            "parent_url": None, "suggested_parent_path": None}

    tc = {}
    for t in page_types.values():
        tc[t] = tc.get(t, 0) + 1
    ts = ", ".join(f"{t}: {c}" for t, c in tc.items())
    return {"type": "mixed",
        "action": f"**Mixed types** ({ts}) compete.\n\n**What to do:**\n1. Category owns generic query\n2. Products target specific names\n3. Click 'Generate meta' below{_extra_suffix}",
        "parent_url": None, "suggested_parent_path": None}

def _get_brand_keywords(df: pd.DataFrame) -> set:
    """
    Detect brand/navigational keywords that should be excluded from cannibalization.

    Brand keywords are identified by:
    1. Queries containing the domain name (e.g. "mshop" from mshop.se)
    2. Queries appearing on many pages (>5% of all pages or 10+ pages)
    3. Queries where homepage has >10x more clicks than any other page
    """
    import streamlit as st
    brand_kws = set()

    # Method 1: Domain-based brand terms
    site = st.session_state.get("gsc_site", "")
    if site:
        from urllib.parse import urlparse
        domain = urlparse(site).netloc.replace("www.", "").split(".")[0]  # "mshop" from "www.mshop.se"
        if domain and len(domain) >= 3:
            # Any query containing the domain name is a brand query
            brand_mask = df["query"].str.contains(domain, case=False, na=False)
            brand_kws.update(df[brand_mask]["query"].unique())

    # Method 2: Queries on many pages (navigational queries)
    total_pages = df["page"].nunique()
    if total_pages >= 10:
        kw_page_counts = df.groupby("query")["page"].nunique()
        threshold = max(10, total_pages * 0.05)  # 5% of pages or 10, whichever is higher
        brand_kws.update(kw_page_counts[kw_page_counts >= threshold].index)

    # Method 3: Homepage-dominated queries (navigational intent)
    homepage = st.session_state.get("gsc_site", "").rstrip("/")
    if homepage:
        from utils.ui_helpers import normalize_url
        hp_norm = normalize_url(homepage)
        for query in df["query"].unique():
            q_data = df[df["query"] == query]
            if len(q_data) < 2:
                continue
            hp_rows = q_data[q_data["page"].apply(normalize_url) == hp_norm]
            if hp_rows.empty:
                continue
            hp_clicks = hp_rows["clicks"].sum()
            other_clicks = q_data["clicks"].sum() - hp_clicks
            # If homepage gets >10x the clicks of all other pages combined → navigational
            if hp_clicks > 0 and (other_clicks == 0 or hp_clicks / max(other_clicks, 1) > 10):
                brand_kws.add(query)

    return brand_kws


def detect_cannibalization(df: pd.DataFrame, min_impressions: int = 10) -> pd.DataFrame:
    """
    Find queries where multiple pages rank, indicating cannibalization.
    Filters out brand keywords (appear on >30% of pages) — these are NOT cannibalization.

    Returns DataFrame with columns:
    - query, page_count, pages (list), positions, clicks, impressions
    - cannibalization_type: severe / moderate / mild
    - recommended_winner: page with best CTR or most clicks
    - lost_clicks_estimate: estimated clicks lost due to split
    """
    if df.empty:
        return pd.DataFrame()

    # Filter low-impression noise
    filtered = df[df["impressions"] >= min_impressions].copy()

    # Filter out brand keywords — they naturally rank on many pages
    brand_kws = _get_brand_keywords(filtered)
    if brand_kws:
        filtered = filtered[~filtered["query"].isin(brand_kws)].copy()

    # Group by query: find queries with multiple pages
    query_pages = (
        filtered.groupby("query")
        .agg(
            page_count=("page", "nunique"),
            pages=("page", list),
            total_clicks=("clicks", "sum"),
            total_impressions=("impressions", "sum"),
        )
        .reset_index()
    )

    # Only keep queries with 2+ pages
    cannibalized = query_pages[query_pages["page_count"] >= 2].copy()

    if cannibalized.empty:
        return pd.DataFrame()

    # Enrich with per-page details
    records = []
    for _, row in cannibalized.iterrows():
        query = row["query"]
        query_data = filtered[filtered["query"] == query].sort_values("clicks", ascending=False)

        pages_detail = []
        for _, p in query_data.iterrows():
            pages_detail.append({
                "page": p["page"],
                "position": round(p["position"], 1),
                "clicks": int(p["clicks"]),
                "impressions": int(p["impressions"]),
                "ctr": round(p["ctr"] * 100, 2) if p["ctr"] < 1 else round(p["ctr"], 2),
            })

        # Determine winner: consider clicks + position + backlink authority
        import streamlit as _st
        page_auth = _st.session_state.get("page_authority")

        best_page = query_data.iloc[0]  # Default: most clicks
        positions = [p["position"] for p in pages_detail]
        best_position = min(positions)
        worst_position = max(positions)
        position_spread = worst_position - best_position

        # Enrich pages with backlink data + determine winner
        for pd_item in pages_detail:
            pd_item["referring_domains"] = 0
            pd_item["authority_score"] = 0
            if page_auth is not None and not page_auth.empty:
                from utils.ui_helpers import normalize_url as _nu
                match = page_auth[page_auth["page"].apply(_nu) == _nu(pd_item["page"])]
                if not match.empty:
                    pd_item["referring_domains"] = int(match.iloc[0].get("referring_domains", 0))
                    pd_item["authority_score"] = int(match.iloc[0].get("authority_score", 0))

        # Pick winner: prefer CATEGORY pages over products for generic queries.
        # Category pages are better owners of generic queries because they serve
        # browse/explore intent and link to products.
        # Detection: use audit_results page_type if available, else use URL depth.
        audit_results = _st.session_state.get("audit_results", [])
        from urllib.parse import urlparse as _urlparse
        _audit_types = {}
        for ar in audit_results:
            from utils.ui_helpers import normalize_url as _nu2
            _audit_types[_nu2(ar.get("url", ""))] = ar.get("page_type", "unknown")

        winner_score = -1
        winner_page = best_page["page"]
        for pd_item in pages_detail:
            page_url = pd_item["page"]
            page_type = _audit_types.get(_nu(page_url), "unknown")
            category_bonus = 500 if page_type == "category" else 0
            url_depth = len([s for s in _urlparse(page_url).path.split("/") if s])
            depth_bonus = max(0, (5 - url_depth) * 50)
            score = (pd_item["clicks"] * 2 + pd_item["referring_domains"] * 10
                     + pd_item["authority_score"] + category_bonus + depth_bonus)
            if score > winner_score:
                winner_score = score
                winner_page = page_url

        # Generate merge instruction — context-aware
        loser_pages = [p["page"] for p in pages_detail if p["page"] != winner_page]
        from urllib.parse import urlparse

        # Detect page types from URL patterns
        def _page_intent(url):
            path = urlparse(url).path.lower()
            if path.rstrip("/") == "" or path == "/":
                return "homepage"
            if "/blog/" in path or "/guide/" in path or "/artikel/" in path or "/tips/" in path:
                return "informational"
            from utils.site_patterns import get_local_patterns
            _local = get_local_patterns()
            if _local and any(loc in path for loc in _local):
                return "local"
            if "/topplistan/" in path or "/topp-" in path or "/bast-" in path:
                return "listicle"
            return "transactional"

        winner_intent = _page_intent(winner_page)
        page_intents = {p["page"]: _page_intent(p["page"]) for p in pages_detail}
        unique_intents = set(page_intents.values())

        # ── Check if meta titles are already differentiated ───
        # If pages already have unique, keyword-focused titles → "already handled"
        page_titles = {}
        for ar in audit_results:
            page_titles[_nu(ar.get("url", ""))] = (ar.get("title") or "").lower().strip()

        titles_in_conflict = [page_titles.get(_nu(p["page"]), "") for p in pages_detail]
        titles_in_conflict = [t for t in titles_in_conflict if t]  # drop empty

        already_differentiated = False
        if len(titles_in_conflict) >= 2:
            # Titles are differentiated if they share <50% of words
            title_word_sets = [set(t.split()) for t in titles_in_conflict]
            all_diffs = []
            for i in range(len(title_word_sets)):
                for j in range(i + 1, len(title_word_sets)):
                    overlap = len(title_word_sets[i] & title_word_sets[j])
                    total = max(len(title_word_sets[i] | title_word_sets[j]), 1)
                    all_diffs.append(overlap / total)
            avg_overlap = sum(all_diffs) / max(len(all_diffs), 1)
            if avg_overlap < 0.5:
                already_differentiated = True

        # ── Cannibalization type classification ───────────
        # Determines WHAT action to take, not just whether there's a problem.
        cannibal_type = _classify_cannibal_type(winner_page, loser_pages, pages_detail, audit_lookup=None)

        if already_differentiated:
            cannibal_type["already_differentiated"] = True

            # Deeper check: titles OK, but is CONTENT + LINKING also aligned?
            # Build per-page diagnosis
            content_issues = []
            linking_issues = []

            # Get body text and link data
            audit_by_url = {_nu(ar.get("url", "")): ar for ar in audit_results}
            sf_link_map = _st.session_state.get("sf_link_map") or {}
            links_from = sf_link_map.get("links_from", {}) if isinstance(sf_link_map, dict) else {}

            all_conflict_urls = [_nu(p["page"]) for p in pages_detail]

            quality_issues = []
            from utils.ui_helpers import stable_hash as _sh

            for p in pages_detail:
                p_url = p["page"]
                p_norm = _nu(p_url)
                p_audit = audit_by_url.get(p_norm, {})
                # Use EDITORIAL text (intro + bottom) for quality checks, not full body
                # which includes product grid prices ("kr rea" x26 = product cards, not editorial)
                _intro = (p_audit.get("intro_text") or "")
                _bottom = (p_audit.get("bottom_text") or "")
                _editorial = (_intro + " " + _bottom).strip().lower()
                p_body = _editorial if _editorial and len(_editorial) > 50 else (p_audit.get("body_text") or "").lower()
                p_wc = p_audit.get("total_editorial_words", 0) or p_audit.get("word_count", 0)
                short = p_url.split("/")[-1][:30]

                # Check 0: AI quality verdict (E-E-A-T, relevance, depth)
                q_key = f"_quality_{_sh(p_url)}"
                q_data = _st.session_state.get(q_key, {})
                if isinstance(q_data, dict) and q_data.get("verdict"):
                    verdict = q_data.get("verdict", "")
                    score = q_data.get("score", 0)
                    summary = q_data.get("summary", "")
                    if verdict == "REWRITE":
                        quality_issues.append(
                            f"🔴 `{short}`: **REWRITE** ({score}/10) — {summary[:100]}"
                        )
                    elif verdict == "IMPROVE" and score <= 5:
                        quality_issues.append(
                            f"🟡 `{short}`: **IMPROVE** ({score}/10) — {summary[:100]}"
                        )

                # Check 1: does query appear in body text?
                if query.lower() not in p_body and p_wc > 0:
                    content_issues.append(
                        f"`{short}`: query **'{query}'** not found in body text ({p_wc} words)"
                    )

                # Check 2: is content thin?
                if p_wc < 200 and p_audit.get("page_type") == "category":
                    content_issues.append(
                        f"`{short}`: only {p_wc} words — needs more targeted content"
                    )

                # Check 3: keyword stuffing (same 2-3 word phrase >5 times)
                # Filter out product-grid metadata tokens (prices, "kr", "rea",
                # "pris", digits) so 36 products in the grid don't trigger a
                # false-positive "stuffing" on "krreatid. pris:929".
                if p_body and p_wc > 100:
                    from collections import Counter
                    import re as _re_stuff
                    _price_re = _re_stuff.compile(
                        r"\b("
                        r"\d+[\s:.-]*kr|\d+\s*:-|\d+\s*sek|"
                        r"pris[:.]?\s*\d*|reatid|krretid|krreatid|"
                        r"kolla\s*att|"
                        r"\d{3,}"
                        r")\b",
                        _re_stuff.I,
                    )
                    _cleaned = _price_re.sub(" ", p_body)
                    # Also drop pure-numeric or too-short tokens from the word list
                    words = [
                        w for w in _cleaned.split()
                        if len(w) >= 3 and not w.isdigit()
                        and w not in ("kr", "sek", "rea", "pris", "reatid")
                    ]
                    bigrams = [f"{words[j]} {words[j+1]}" for j in range(len(words)-1)]
                    bigram_counts = Counter(bigrams).most_common(5)
                    for phrase, count in bigram_counts:
                        # Skip bigrams where either word is still noise
                        tokens = phrase.split()
                        if any(t in ("kr", "rea", "pris") or t.isdigit() for t in tokens):
                            continue
                        if count >= 6 and len(phrase) > 5:
                            content_issues.append(
                                f"`{short}`: **keyword stuffing** — '{phrase}' repeated {count} times"
                            )
                            break

                # Check 4: no real product/brand references on category pages
                if p_audit.get("page_type") == "category" and p_wc > 200:
                    has_specifics = any(term in p_body for term in [" kr", ":-", "pris", "modell", "märke", "brand"])
                    if not has_specifics:
                        content_issues.append(
                            f"`{short}`: **generic text** — no product names, prices, or brand mentions"
                        )

                # Check 3: smart internal link recommendations
                # NOT "every page links to every other page" — use site architecture:
                # - Category → parent category (if exists): anchor = parent's primary query
                # - Category → sub-categories: anchor = sub-category's primary query
                # - Product → its parent category: anchor = category's primary query
                # - /rea/ variant → main category: anchor = generic query
                # NEVER suggest product-to-product cross-links.

                p_outbound = set()
                p_internal_links = p_audit.get("internal_links") or []
                if isinstance(p_internal_links, list):
                    for link in p_internal_links:
                        link_url = link.get("url", "") if isinstance(link, dict) else str(link)
                        if link_url:
                            p_outbound.add(_nu(link_url))
                for lf_url, targets in links_from.items():
                    if _nu(lf_url) == p_norm and isinstance(targets, list):
                        for t in targets:
                            t_url = t.get("target", "") if isinstance(t, dict) else str(t)
                            if t_url:
                                p_outbound.add(_nu(t_url))

                from utils.url_helpers import url_path as _up_path, path_is_descendant as _pid
                p_type = _audit_types.get(p_norm, "unknown")
                p_path = _up_path(p_url)

                # Find the winner/main category — that's the page products/variants should link TO
                winner_norm = _nu(winner_page)
                winner_path = _up_path(winner_page)

                # Only recommend links that make architectural sense
                if p_norm != winner_norm:
                    # This page should link to the winner (main category)
                    if winner_norm not in p_outbound:
                        # Anchor = the winner's primary query from GSC (not the shared query)
                        winner_anchor = query  # fallback
                        winner_title = page_titles.get(winner_norm, "")
                        if winner_title:
                            # Extract main keyword from title (first few words before | or -)
                            import re as _re
                            title_kw = _re.split(r'[|–—\-»]', winner_title)[0].strip()
                            if title_kw and len(title_kw) < 40:
                                winner_anchor = title_kw
                        linking_issues.append(
                            f"`{short}` should link to `{winner_path.split('/')[-1]}` "
                            f"with anchor **\"{winner_anchor}\"**"
                        )
                else:
                    # This IS the winner — check if it links to sub-pages/variants
                    for other_url in all_conflict_urls:
                        if other_url == p_norm:
                            continue
                        other_type = _audit_types.get(other_url, "unknown")
                        other_path = _up_path(other_url)
                        # Only suggest winner → child if child is under winner's path
                        is_child = _pid(other_url, p_url)
                        if is_child and other_url not in p_outbound:
                            other_title = page_titles.get(other_url, "")
                            other_anchor = other_path.split("/")[-1].replace("-", " ")
                            if other_title:
                                kw = _re.split(r'[|–—\-»]', other_title)[0].strip()
                                if kw and len(kw) < 40:
                                    other_anchor = kw
                            linking_issues.append(
                                f"`{short}` should link to sub-page `{other_path.split('/')[-1]}` "
                                f"with anchor **\"{other_anchor}\"**"
                            )

            # Build action text
            parts = ["✅ **Meta titles are already differentiated.**\n"]
            parts.append("Current titles:\n" + "\n".join(
                f"- `{p['page'].split('/')[-1]}`: {page_titles.get(_nu(p['page']), '(unknown)')}"
                for p in pages_detail[:5]
            ))

            if quality_issues:
                parts.append(f"\n\n📊 **Content quality (E-E-A-T) issues ({len(quality_issues)}):**")
                for qi in quality_issues[:5]:
                    parts.append(f"- {qi}")

            if content_issues:
                parts.append(f"\n\n⚠️ **Keyword targeting issues ({len(content_issues)}):**")
                for ci in content_issues[:5]:
                    parts.append(f"- {ci}")

            if linking_issues:
                parts.append(f"\n\n🔗 **Missing internal links ({len(linking_issues)}):**")
                for li in linking_issues[:5]:
                    parts.append(f"- {li}")

            if not content_issues and not linking_issues and not quality_issues:
                parts.append("\n\n✅ Content is targeted, quality is good, and pages are interlinked. **Monitor only.**")
                cannibal_type["fully_resolved"] = True
            else:
                parts.append("\n\nClick **Generate meta** below for AI content recommendations.")

            cannibal_type["action"] = "\n".join(parts)
            cannibal_type["has_content_issues"] = len(content_issues) > 0
            cannibal_type["has_linking_issues"] = len(linking_issues) > 0

        # Different intents → don't merge, differentiate with specific guidance
        if len(unique_intents) > 1:
            # Build per-page role + concrete action
            from urllib.parse import urlparse as _urp
            intent_labels = {
                "transactional": ("🛒 SHOP page", "buyers ready to purchase"),
                "listicle":      ("📊 LISTICLE", "researchers comparing options"),
                "informational": ("📖 GUIDE",    "people learning about the topic"),
                "guide":         ("📖 GUIDE",    "people learning about the topic"),
                "homepage":      ("🏠 HOMEPAGE", "general site visitors"),
            }
            role_lines = []
            transactional_url = ""
            listicle_url = ""
            guide_url = ""
            for u, intent in page_intents.items():
                short = _urp(u).path.rstrip("/") or u
                label, audience = intent_labels.get(intent, (intent.upper(), "varies"))
                role_lines.append(f"  • `{short}` = **{label}** (targets {audience})")
                if intent == "transactional":
                    transactional_url = u
                elif intent == "listicle":
                    listicle_url = u
                elif intent in ("informational", "guide"):
                    guide_url = u

            # Concrete action depending on intent mix
            specific_steps = []
            if transactional_url and listicle_url:
                specific_steps = [
                    f"**This is GOOD cannibalization** — both pages serve different parts of the buyer journey on the same keyword.",
                    f"**WHAT to do:** strengthen the difference, don't merge.",
                    f"**1. On the SHOP page** (`{_urp(transactional_url).path}`):",
                    f"   - Top: focus on \"Shop {row.get('query','this category')}\" — emphasize stock, price, fast shipping, brands carried.",
                    f"   - Add a prominent box: *\"Not sure which to pick? See our top picks → [link to listicle]\"*",
                    f"**2. On the LISTICLE page** (`{_urp(listicle_url).path}`):",
                    f"   - Frame as \"Best {row.get('query','X')} {2026}\" — comparisons, pros/cons, expert verdict.",
                    f"   - End each top-pick with: *\"Buy on Mshop → [link to product] | Browse all → [link to shop page]\"*",
                    f"**WHY:** Google may rank either for the same query depending on search modifier (\"buy\" vs \"best\"). Cross-links prevent users from leaving the site.",
                    f"**HOW in Magento:** Open each page → Description → add the cross-link `<a href=\"OTHER_URL\">anchor text</a>` near top + bottom.",
                ]
            elif transactional_url and guide_url:
                specific_steps = [
                    f"**Shop page + Guide page on same keyword** — different funnel stages.",
                    f"**WHAT to do:** make the guide a feeder to the shop page.",
                    f"**1. On the GUIDE** (`{_urp(guide_url).path}`):",
                    f"   - Add a top callout: *\"Ready to buy? → [Shop {row.get('query','this category')}]\"*",
                    f"   - End with a product strip linking to the SHOP page.",
                    f"**2. On the SHOP page** (`{_urp(transactional_url).path}`):",
                    f"   - In bottom text, link back to the guide: *\"New to this? Read our [guide to {row.get('query','X')}]\"*",
                    f"**WHY:** the guide attracts top-of-funnel traffic; the shop converts. Linking funnels users from research → purchase.",
                ]
            else:
                specific_steps = [
                    f"**Different intents** — mixed page types ranking for the same query.",
                    f"**WHAT to do:** add cross-links so both pages help each other.",
                    f"**HOW:** on each page, add a contextual link to the other with anchor `{row.get('query','this query')}`.",
                ]

            merge_action = (
                f"**Page roles:**\n" + "\n".join(role_lines) + "\n\n" +
                "\n".join(specific_steps)
            )
        # Homepage involved → never merge into homepage
        elif "homepage" in unique_intents:
            merge_action = (
                f"Homepage is involved — don't redirect category/product pages to homepage. "
                f"Instead: strengthen each page's unique keyword focus."
            )
        # Same intent, similar pages → merge candidate
        elif row["page_count"] == 2 and position_spread < 3:
            merge_action = (
                f"Similar pages competing. Consider: "
                f"1) Differentiate content — give each a unique angle, OR "
                f"2) KEEP: {winner_page} and REDIRECT: {loser_pages[0]} -> {winner_page} (301). "
                f"Check which page converts better before deciding."
            )
        else:
            merge_action = (
                f"KEEP: {winner_page} (redirect others here). "
                f"REDIRECT: {', '.join(loser_pages[:3])} -> {winner_page} (301 redirect). "
                f"Steps: 1) Copy unique content from loser to winner 2) Set up 301 redirect 3) Update internal links."
            )

        # Classify severity
        if row["page_count"] >= 3 and position_spread > 5:
            severity = "severe"
        elif row["page_count"] >= 3 or position_spread > 10:
            severity = "severe"
        elif position_spread < 3:
            severity = "moderate"
        else:
            severity = "mild"

        # Estimate lost clicks: if all impressions went to best page's CTR
        best_ctr = best_page["ctr"] if best_page["ctr"] < 1 else best_page["ctr"] / 100
        potential_clicks = best_ctr * row["total_impressions"]
        lost_clicks = max(0, int(potential_clicks - row["total_clicks"]))

        # Lower severity only if FULLY resolved (titles + content + links all OK)
        if cannibal_type.get("fully_resolved"):
            severity = "handled"

        records.append({
            "query": query,
            "page_count": row["page_count"],
            "severity": severity,
            "total_clicks": int(row["total_clicks"]),
            "total_impressions": int(row["total_impressions"]),
            "position_spread": round(position_spread, 1),
            "recommended_winner": winner_page,
            "winner_position": round(best_page["position"], 1),
            "winner_clicks": int(best_page["clicks"]),
            "merge_action": merge_action,
            "lost_clicks_estimate": lost_clicks,
            "pages_detail": pages_detail,
            "cannibal_type": cannibal_type.get("type", "unknown"),
            "cannibal_action": cannibal_type.get("action", ""),
            "cannibal_parent_url": cannibal_type.get("parent_url"),
            "cannibal_suggested_parent": cannibal_type.get("suggested_parent_path"),
            "already_differentiated": cannibal_type.get("already_differentiated", False),
        })

    result = pd.DataFrame(records)
    result = result.sort_values("lost_clicks_estimate", ascending=False).reset_index(drop=True)
    return result


def get_page_cannibalization_summary(cannibal_df: pd.DataFrame) -> pd.DataFrame:
    """
    Summarize cannibalization per PAGE (not per query).
    Shows which pages are involved in the most conflicts.
    """
    if cannibal_df.empty:
        return pd.DataFrame()

    page_records = []
    for _, row in cannibal_df.iterrows():
        for page_detail in row["pages_detail"]:
            page_records.append({
                "page": page_detail["page"],
                "query": row["query"],
                "severity": row["severity"],
                "is_winner": page_detail["page"] == row["recommended_winner"],
                "position": page_detail["position"],
                "clicks": page_detail["clicks"],
                "lost_clicks": row["lost_clicks_estimate"] if page_detail["page"] != row["recommended_winner"] else 0,
            })

    page_df = pd.DataFrame(page_records)

    summary = (
        page_df.groupby("page")
        .agg(
            cannibal_queries=("query", "count"),
            severe_count=("severity", lambda x: (x == "severe").sum()),
            is_winner_count=("is_winner", "sum"),
            is_loser_count=("is_winner", lambda x: (~x).sum()),
            total_lost_clicks=("lost_clicks", "sum"),
        )
        .reset_index()
        .sort_values("cannibal_queries", ascending=False)
    )

    summary["win_rate"] = (summary["is_winner_count"] / summary["cannibal_queries"] * 100).round(0)
    return summary


def get_cannibalization_clusters(cannibal_df: pd.DataFrame) -> list:
    """
    Group cannibalized queries into clusters of related pages.
    Returns list of dicts with cluster info.
    """
    if cannibal_df.empty:
        return []

    # Build page-to-page co-occurrence
    page_pairs = {}
    for _, row in cannibal_df.iterrows():
        pages = [p["page"] for p in row["pages_detail"]]
        for i, p1 in enumerate(pages):
            for p2 in pages[i + 1:]:
                key = tuple(sorted([p1, p2]))
                if key not in page_pairs:
                    page_pairs[key] = {"queries": [], "total_lost": 0}
                page_pairs[key]["queries"].append(row["query"])
                page_pairs[key]["total_lost"] += row["lost_clicks_estimate"]

    clusters = []
    for (p1, p2), data in sorted(page_pairs.items(), key=lambda x: -x[1]["total_lost"]):
        clusters.append({
            "page_1": p1,
            "page_2": p2,
            "shared_queries": len(data["queries"]),
            "query_examples": data["queries"][:10],
            "total_lost_clicks": data["total_lost"],
        })

    return clusters
