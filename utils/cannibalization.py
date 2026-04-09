"""
Cannibalization detection from GSC data.
Identifies keywords where multiple pages compete for the same query.
"""

import pandas as pd
import numpy as np


def _classify_cannibal_type(winner: str, losers: list, pages_detail: list, audit_lookup=None) -> dict:
    """
    Classify WHAT kind of cannibalization this is, with a concrete
    Magento-specific action description per type.

    Types:
      category_vs_children  — A category + its sub-categories/products compete.
                              This is NORMAL on e-commerce sites. Fix = differentiate meta.
      products_same_parent  — Multiple products under the same category compete.
                              Fix = differentiate product meta per variant.
      products_no_parent    — Multiple products from different areas compete for a
                              generic term. Fix = create a category that targets it.
      true_duplicate        — Two very similar pages at same depth. Fix = 301 redirect.
      unrelated             — Pages with no structural relationship. Fix = per-page meta.
    """
    from urllib.parse import urlparse

    def _path_of(u):
        return urlparse(str(u)).path.rstrip("/") or "/"

    all_urls = [winner] + list(losers)
    all_paths = [_path_of(u) for u in all_urls]
    segments_list = [[s for s in p.split("/") if s] for p in all_paths]
    depths = [len(s) for s in segments_list]

    # ── Find parent-child relationships ──────────────────────
    # Check if ANY path is a prefix of other paths (majority, not all).
    # This catches /sexdockor being parent of /sexdockor/torso even when
    # /intimate-collection (unrelated) is also in the mix.
    parent_path = None
    parent_children = []
    outliers = []

    paths_by_depth = sorted(zip(all_paths, all_urls), key=lambda x: len(x[0]))
    for candidate_path, candidate_url in paths_by_depth:
        if len(candidate_path) <= 1:
            continue
        children = []
        others = []
        for p, u in zip(all_paths, all_urls):
            if p == candidate_path:
                continue
            if p.startswith(candidate_path + "/"):
                children.append(u)
            else:
                others.append(u)
        # If this path is parent of at least 2 others → category_vs_children
        if len(children) >= 2:
            parent_path = candidate_path
            parent_children = children
            outliers = others
            break

    if parent_path:
        outlier_note = ""
        if outliers:
            outlier_note = (
                f" Also competing: {', '.join(_path_of(o) for o in outliers)} "
                f"(unrelated — check why they rank for this query)."
            )
        parent_url_full = [u for p, u in zip(all_paths, all_urls) if p == parent_path]
        return {
            "type": "category_vs_children",
            "action": (
                f"This is a CATEGORY + its sub-pages competing. This is NORMAL on "
                f"e-commerce sites — not a bug to fix with redirects.\n\n"
                f"**What to do in Magento:**\n"
                f"1. Parent category targets the GENERIC query in meta title\n"
                f"2. Each sub-category/product gets a SPECIFIC variant in its meta title\n"
                f"3. Ensure parent page links visibly to all sub-pages\n"
                f"4. Click 'Generate meta' below to get ready-to-paste titles{outlier_note}"
            ),
            "parent_url": parent_url_full[0] if parent_url_full else None,
            "suggested_parent_path": None,
        }

    # ── Same parent directory → products/variants under one category ──
    parent_dirs = set()
    for segs in segments_list:
        parent_dirs.add("/" + "/".join(segs[:-1]) if len(segs) > 1 else "/")
    if len(parent_dirs) == 1 and len(all_paths) >= 2:
        shared_parent = next(iter(parent_dirs))
        return {
            "type": "products_same_parent",
            "action": (
                f"Multiple pages under `{shared_parent}` compete for the same query.\n\n"
                f"**What to do in Magento:**\n"
                f"1. Each page gets a UNIQUE meta title with its specific variant "
                f"(brand name, color, size, feature)\n"
                f"2. The parent category `{shared_parent}` should target the generic query\n"
                f"3. Click 'Generate meta' below to get differentiated titles"
            ),
            "parent_url": shared_parent,
            "suggested_parent_path": None,
        }

    # ── Two pages only, same depth → likely true duplicates ──
    if len(all_paths) == 2 and abs(depths[0] - depths[1]) <= 1:
        return {
            "type": "true_duplicate",
            "action": (
                f"Two pages at similar depth compete for the same query.\n\n"
                f"**What to do in Magento:**\n"
                f"1. Keep the 🏆 WINNER page\n"
                f"2. Copy any unique content from the loser to the winner\n"
                f"3. Set up 301 redirect: loser → winner (URL Rewrite Management)\n"
                f"4. Update any internal links pointing to the loser"
            ),
            "parent_url": None,
            "suggested_parent_path": None,
        }

    # ── Multiple products from different areas, no shared structure ──
    # This usually means a generic query (e.g. "dildo") has no proper
    # category page, so random products compete for it.
    if len(all_paths) >= 3:
        # Check if the winner looks like a category (shorter path, more generic)
        winner_path = _path_of(winner)
        winner_depth = len([s for s in winner_path.split("/") if s])
        min_depth = min(depths)
        if winner_depth == min_depth:
            return {
                "type": "category_vs_children",
                "action": (
                    f"A category page competes with product pages for a generic query.\n\n"
                    f"**What to do in Magento:**\n"
                    f"1. Strengthen the WINNER (category page) meta title for the generic query\n"
                    f"2. Each product page targets its SPECIFIC product name in meta\n"
                    f"3. Ensure products are assigned to the winning category\n"
                    f"4. Click 'Generate meta' below"
                ),
                "parent_url": winner,
                "suggested_parent_path": None,
            }
        else:
            return {
                "type": "products_no_parent",
                "action": (
                    f"Multiple products compete for a generic query but there's no "
                    f"category page targeting it.\n\n"
                    f"**What to do in Magento:**\n"
                    f"1. CREATE a new category page targeting this query\n"
                    f"2. Assign all competing products to the new category\n"
                    f"3. Write intro text + meta title targeting the generic query\n"
                    f"4. Each product keeps its specific product-name meta"
                ),
                "parent_url": None,
                "suggested_parent_path": "/" + all_paths[0].split("/")[1] if segments_list[0] else None,
            }

    # ── Fallback: 2 pages, different depths ──
    return {
        "type": "unrelated",
        "action": (
            f"Two structurally unrelated pages compete for the same query.\n\n"
            f"**What to do in Magento:**\n"
            f"1. Decide which page should own this query\n"
            f"2. Optimize that page's meta title for the query\n"
            f"3. Change the other page's meta to target a DIFFERENT keyword\n"
            f"4. Click 'Generate meta' below"
        ),
        "parent_url": None,
        "suggested_parent_path": None,
    }


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

        # Pick winner: highest (clicks * 2 + referring_domains * 10 + authority_score)
        winner_score = -1
        winner_page = best_page["page"]
        for pd_item in pages_detail:
            score = pd_item["clicks"] * 2 + pd_item["referring_domains"] * 10 + pd_item["authority_score"]
            if score > winner_score:
                winner_score = score
                winner_page = pd_item["page"]

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

        # ── Cannibalization type classification ───────────
        # Determines WHAT action to take, not just whether there's a problem.
        cannibal_type = _classify_cannibal_type(winner_page, loser_pages, pages_detail, audit_lookup=None)

        # Different intents → don't merge, differentiate
        if len(unique_intents) > 1:
            intent_desc = ", ".join(f"{url.split('/')[-2] or url}: {intent}" for url, intent in page_intents.items())
            merge_action = (
                f"DIFFERENT INTENTS — don't merge, differentiate content instead. "
                f"Intents: {intent_desc}. "
                f"Make each page target its specific intent. Add canonical or noindex if needed. "
                f"The blog/guide page should link to the category page and vice versa."
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
