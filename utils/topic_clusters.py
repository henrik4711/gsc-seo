"""
Topic clustering from GSC keyword data.
Groups queries into semantic clusters and maps them to pages.
Identifies content gaps and overlap between pages.
"""

import pandas as pd
import numpy as np
from collections import defaultdict
import re
from urllib.parse import urlparse


def _is_homepage(url: str) -> bool:
    """Homepage urls — never spokes/hubs in topical clusters.
    Google may rank the homepage for cluster head terms (especially for
    brand/category queries), but structurally the homepage isn't a
    spoke under any category — it's its own traffic magnet."""
    if not url:
        return False
    try:
        path = urlparse(url).path or ""
    except Exception:
        path = url
    path = path.strip()
    if path in ("", "/"):
        return True
    # Strip trailing slash, common query/fragment artifacts already gone.
    return path.rstrip("/") == ""


def normalize_cluster_pages(clusters: list) -> list:
    """
    Apply two architecture rules to a list of enriched clusters:

      1. Homepage is never a spoke. Drop homepage rows from cluster.pages.
      2. Each page belongs to ONE primary cluster (the cluster where it
         contributes the most queries). Remove from non-primary clusters.

    Cluster-level queries / total_clicks / total_impressions are NOT
    touched — those still reflect the cluster's full reach. Only the
    spoke list (cluster.pages) is deduped.

    Mutates clusters in-place AND returns it (chainable). Callers that
    receive clusters from a different code path (e.g. AI clustering)
    must call this before the clusters are saved/used elsewhere, or the
    rules won't apply.
    """
    if not clusters:
        return clusters
    # Rule 1: drop homepage rows from each cluster's pages list
    for c in clusters:
        original = c.get("pages", []) or []
        c["pages"] = [p for p in original
                      if isinstance(p, dict) and p.get("page")
                      and not _is_homepage(p["page"])]
        c["page_count"] = len(c["pages"])
        c["is_split"] = len(c["pages"]) > 1
    # Rule 2: assign each page to its primary cluster (most queries),
    # remove from non-primary cluster.pages
    page_cluster_strength: dict = defaultdict(list)
    for ci, c in enumerate(clusters):
        for p in c.get("pages", []) or []:
            page_cluster_strength[p["page"]].append(
                (ci, p.get("query_count", 0), p.get("total_clicks", 0))
            )
    primary_of: dict = {}
    for page, entries in page_cluster_strength.items():
        entries.sort(key=lambda x: (-x[1], -x[2], x[0]))
        primary_of[page] = entries[0][0]
    for ci, c in enumerate(clusters):
        kept = [p for p in c.get("pages", []) or []
                if primary_of.get(p["page"]) == ci]
        c["pages"] = kept
        c["page_count"] = len(kept)
        c["is_split"] = len(kept) > 1
    return clusters


def build_topic_clusters(df: pd.DataFrame, min_cluster_size: int = 2) -> dict:
    """
    Cluster GSC queries into topic groups based on shared words and pages.

    Returns dict with:
    - clusters: list of topic clusters
    - page_topics: mapping of page -> primary topics
    - overlap_matrix: pages that share topic clusters
    """
    if df.empty:
        return {"clusters": [], "page_topics": {}, "overlap_matrix": []}

    # Step 1: Tokenize and find shared stems
    queries = df[["query", "page", "clicks", "impressions", "position"]].copy()
    queries["tokens"] = queries["query"].apply(_tokenize)

    # Step 2: Build word-to-query index
    word_queries = defaultdict(set)
    for idx, row in queries.iterrows():
        for token in row["tokens"]:
            word_queries[token].add(idx)

    # Step 3: Group queries by shared significant words
    # Use 2-gram approach for better clustering
    query_bigrams = {}
    for idx, row in queries.iterrows():
        tokens = row["tokens"]
        bigrams = set()
        bigrams.update(tokens)  # unigrams
        for i in range(len(tokens) - 1):
            bigrams.add(f"{tokens[i]}_{tokens[i+1]}")
        query_bigrams[idx] = bigrams

    # Step 4: Cluster using shared token overlap
    clusters = _cluster_queries(queries, query_bigrams, min_cluster_size)

    # Step 5: Enrich clusters with page mapping
    enriched_clusters = []
    for cluster in clusters:
        cluster_queries = queries.loc[cluster["query_indices"]]
        pages = cluster_queries.groupby("page").agg(
            query_count=("query", "count"),
            total_clicks=("clicks", "sum"),
            total_impressions=("impressions", "sum"),
            avg_position=("position", "mean"),
        ).reset_index().sort_values("total_clicks", ascending=False)
        # Drop homepage rows — homepage is never a spoke. Google ranks it
        # for cluster head terms (esp. brand/category), but structurally it
        # isn't part of any topical hierarchy.
        if not pages.empty:
            pages = pages[~pages["page"].apply(_is_homepage)].reset_index(drop=True)

        # Robust click sum: try multiple sources, take the maximum
        # (defensive against dtype issues, missing values, etc.)
        click_from_queries = int(pd.to_numeric(cluster_queries["clicks"], errors="coerce").fillna(0).sum())
        click_from_pages = int(pages["total_clicks"].sum()) if "total_clicks" in pages.columns else 0
        impr_from_queries = int(pd.to_numeric(cluster_queries["impressions"], errors="coerce").fillna(0).sum())
        impr_from_pages = int(pages["total_impressions"].sum()) if "total_impressions" in pages.columns else 0

        enriched_clusters.append({
            "topic": cluster["label"],
            "core_terms": cluster["core_terms"],
            "query_count": cluster_queries["query"].nunique(),
            "queries": cluster_queries["query"].unique().tolist(),
            "total_clicks": max(click_from_queries, click_from_pages),
            "total_impressions": max(impr_from_queries, impr_from_pages),
            "pages": pages.to_dict("records"),
            "page_count": len(pages),
            "is_split": len(pages) > 1,  # topic served by multiple pages
        })

    enriched_clusters.sort(key=lambda x: -x["total_impressions"])

    # Step 5b: enforce two architecture rules — drop homepage as spoke,
    # assign each page to its primary cluster only. Same logic also runs
    # on AI-clustered output via the same helper (see views/run_pipeline).
    normalize_cluster_pages(enriched_clusters)

    # Step 6: Build page-topic mapping
    page_topics = defaultdict(list)
    for cluster in enriched_clusters:
        for page_data in cluster["pages"]:
            page_topics[page_data["page"]].append({
                "topic": cluster["topic"],
                "queries_in_topic": page_data["query_count"],
                "clicks": page_data["total_clicks"],
            })

    # Step 7: Find page overlap (pages sharing topics)
    overlap = _find_page_overlap(enriched_clusters)

    return {
        "clusters": enriched_clusters,
        "page_topics": dict(page_topics),
        "overlap_matrix": overlap,
    }


def identify_content_gaps(clusters: list, authority_data: pd.DataFrame = None) -> list:
    """
    Identify topics that are underserved or missing proper content.
    """
    gaps = []
    for cluster in clusters:
        issues = []

        # High impressions but low clicks = poor content/meta
        if cluster["total_impressions"] > 100 and cluster["total_clicks"] < cluster["total_impressions"] * 0.02:
            issues.append("Low CTR despite high impressions - content/meta needs improvement")

        # Topic split across many pages = cannibalization risk
        if cluster["page_count"] >= 3:
            issues.append(f"Topic split across {cluster['page_count']} pages - consolidation needed")

        # Single page with many queries but low clicks
        if cluster["page_count"] == 1 and cluster["query_count"] > 10 and cluster["total_clicks"] < 50:
            issues.append("Many related queries but low traffic - content depth needed")

        # Check authority if available
        if authority_data is not None and not authority_data.empty:
            for page_data in cluster["pages"]:
                page = page_data["page"]
                from utils.ui_helpers import normalize_url as _nu
                auth = authority_data[authority_data["page"].apply(_nu) == _nu(page)]
                if not auth.empty and auth.iloc[0].get("referring_domains", 0) == 0:
                    issues.append(f"No backlinks to {page} - needs link building")

        if issues:
            gaps.append({
                "topic": cluster["topic"],
                "queries": cluster["query_count"],
                "impressions": cluster["total_impressions"],
                "issues": issues,
                "priority": "high" if len(issues) >= 2 else "medium",
            })

    gaps.sort(key=lambda x: -x["impressions"])
    return gaps


def _tokenize(query: str) -> list:
    """Tokenize and clean a search query."""
    # Remove common Swedish/Danish stop words
    stop_words = {
        "i", "och", "att", "en", "ett", "den", "det", "som", "av", "till",
        "med", "for", "har", "vi", "kan", "om", "men", "var", "inte",
        "der", "og", "er", "af", "til", "med", "fra", "som", "et",
        "de", "den", "at", "pa", "en", "kan", "vi", "har", "ikke",
        "the", "and", "for", "with", "this", "that", "from", "are", "was",
        "a", "an", "in", "on", "to", "of", "is", "it",
        "köpa", "bäst", "bästa", "billig", "billiga", "online",
        "kob", "bedst", "bedste", "billig", "billige",
    }

    tokens = re.findall(r"\w+", query.lower())
    return [t for t in tokens if t not in stop_words and len(t) > 1]


def _cluster_queries(queries: pd.DataFrame, query_bigrams: dict, min_size: int) -> list:
    """Simple greedy clustering based on token overlap."""
    assigned = set()
    clusters = []

    # Sort queries by impressions (cluster around high-value queries first)
    sorted_indices = queries.sort_values("impressions", ascending=False).index.tolist()

    for seed_idx in sorted_indices:
        if seed_idx in assigned:
            continue

        seed_tokens = query_bigrams.get(seed_idx, set())
        if not seed_tokens:
            continue

        # Find similar queries
        cluster_indices = {seed_idx}
        for other_idx in sorted_indices:
            if other_idx in assigned or other_idx == seed_idx:
                continue
            other_tokens = query_bigrams.get(other_idx, set())
            if not other_tokens:
                continue

            overlap = len(seed_tokens & other_tokens)
            union = len(seed_tokens | other_tokens)
            if union > 0 and overlap / union >= 0.25:
                cluster_indices.add(other_idx)

        if len(cluster_indices) >= min_size:
            assigned.update(cluster_indices)

            # Generate cluster label from most common terms
            all_tokens = []
            for idx in cluster_indices:
                all_tokens.extend(queries.loc[idx, "tokens"])

            from collections import Counter
            common = Counter(all_tokens).most_common(3)
            label = " + ".join([t[0] for t in common])
            core_terms = [t[0] for t in common]

            clusters.append({
                "label": label,
                "core_terms": core_terms,
                "query_indices": list(cluster_indices),
            })

    return clusters


def _find_page_overlap(clusters: list) -> list:
    """Find pairs of pages that share topic clusters."""
    page_pair_topics = defaultdict(list)

    for cluster in clusters:
        if cluster["page_count"] < 2:
            continue
        pages = [p["page"] for p in cluster["pages"]]
        for i, p1 in enumerate(pages):
            for p2 in pages[i + 1:]:
                key = tuple(sorted([p1, p2]))
                page_pair_topics[key].append(cluster["topic"])

    overlap = []
    for (p1, p2), topics in sorted(page_pair_topics.items(), key=lambda x: -len(x[1])):
        overlap.append({
            "page_1": p1,
            "page_2": p2,
            "shared_topics": len(topics),
            "topic_names": topics,
        })

    return overlap


# ══════════════════════════════════════════════════════════════════
# CONTENT ROADMAP (WP4)
# ══════════════════════════════════════════════════════════════════

def generate_content_roadmap(
    clusters: list, page_topics: dict, gsc_data: pd.DataFrame = None,
    authority_data: pd.DataFrame = None,
) -> dict:
    """
    Generate a content roadmap: identify uncovered subtopics that need new articles,
    thin clusters that need supporting content, and provide specific article suggestions
    with internal linking plans.
    """
    from utils.category_analyzer import _group_queries_into_subtopics

    articles_needed = []
    supporting_content = []
    total_opportunity = 0

    for cluster in clusters:
        queries = cluster.get("queries", [])
        core_terms = cluster.get("core_terms", [])
        pages = cluster.get("pages", [])
        topic_label = cluster.get("topic", "")
        primary_page = pages[0]["page"] if pages else None

        # Group queries into subtopics
        subtopics = _group_queries_into_subtopics(queries)

        # Get impressions per query from GSC data
        query_impressions = {}
        if gsc_data is not None and not gsc_data.empty:
            for q in queries:
                qdata = gsc_data[gsc_data["query"] == q]
                if not qdata.empty:
                    query_impressions[q] = int(qdata["impressions"].sum())

        # Check each subtopic for coverage
        for st_item in subtopics:
            if st_item["topic"] == "(other)":
                continue

            st_queries = st_item["queries"]
            st_impressions = sum(query_impressions.get(q, 0) for q in st_queries)

            # Is this subtopic well-covered by an existing page?
            covered = False
            if gsc_data is not None:
                for q in st_queries:
                    qdata = gsc_data[gsc_data["query"] == q]
                    if not qdata.empty and qdata["position"].min() <= 15:
                        covered = True
                        break

            # Also check if an existing page title/URL already covers this subtopic
            if not covered:
                st_topic_lower = st_item["topic"].lower()
                for p in pages:
                    p_url = p["page"].lower()
                    if st_topic_lower in p_url or st_topic_lower.replace(" ", "-") in p_url:
                        covered = True
                        break

            if not covered and st_impressions >= 50:
                content_type = _infer_content_type(st_queries)
                top_query = max(st_queries, key=lambda q: query_impressions.get(q, 0))

                title_prefix = {
                    "how-to": "How to",
                    "comparison": "Comparing",
                    "listicle": "Best",
                    "explainer": "What is",
                    "guide": "Guide:",
                }.get(content_type, "Guide:")

                suggested_title = f"{title_prefix} {top_query.title()}"

                # Internal linking plan
                linking_plan = []
                if primary_page:
                    linking_plan.append({
                        "from": primary_page,
                        "to": "(new article)",
                        "anchor": " ".join(core_terms[:2]) + " " + st_item["topic"],
                        "direction": "hub → article",
                    })
                    linking_plan.append({
                        "from": "(new article)",
                        "to": primary_page,
                        "anchor": " ".join(core_terms[:2]),
                        "direction": "article → hub",
                    })

                articles_needed.append({
                    "suggested_title": suggested_title,
                    "target_keywords": st_queries[:8],
                    "estimated_impressions": st_impressions,
                    "content_type": content_type,
                    "supporting_page": primary_page,
                    "cluster_topic": topic_label,
                    "subtopic": st_item["topic"],
                    "internal_linking_plan": linking_plan,
                    "priority": "high" if st_impressions >= 200 else "medium" if st_impressions >= 100 else "low",
                })
                total_opportunity += st_impressions

        # Check if cluster needs more supporting content overall
        page_count = cluster.get("page_count", 0)
        query_count = cluster.get("query_count", 0)
        total_impressions = cluster.get("total_impressions", 0)

        has_informational = False
        for p in pages:
            p_url = p["page"].lower()
            if any(pat in p_url for pat in ["/blog", "/guide", "/artikel", "/tips", "/how-to", "/faq"]):
                has_informational = True
                break

        if page_count <= 2 and query_count >= 8 and total_impressions >= 200:
            supporting_content.append({
                "cluster_topic": topic_label,
                "primary_page": primary_page,
                "page_count": page_count,
                "query_count": query_count,
                "impressions": total_impressions,
                "has_informational": has_informational,
                "recommendation": (
                    "Add blog/guide content to support this category"
                    if not has_informational else
                    "Consider adding more depth: comparison articles, FAQ pages, or buyer's guides"
                ),
            })

    # Sort by priority and impressions
    articles_needed.sort(key=lambda x: (
        {"high": 0, "medium": 1, "low": 2}.get(x["priority"], 3),
        -x["estimated_impressions"],
    ))

    supporting_content.sort(key=lambda x: -x["impressions"])

    return {
        "articles_needed": articles_needed,
        "supporting_content": supporting_content,
        "total_articles": len(articles_needed),
        "total_opportunity_impressions": total_opportunity,
        "total_supporting_gaps": len(supporting_content),
    }


def _infer_content_type(queries: list) -> str:
    """Infer the best content type from a list of queries (multilingual)."""
    text = " ".join(queries).lower()

    # How-to patterns
    if re.search(r"\b(how to|how do|hur|hvordan|guide to|steg för steg)\b", text):
        return "how-to"

    # Comparison patterns
    if re.search(r"\b(vs\.?|versus|compare|jämför|sammenlign|eller|or\b.*\bor\b|skillnad)", text):
        return "comparison"

    # Listicle patterns
    if re.search(r"\b(best|top \d|bäst|bedst|bra|topp)\b", text):
        return "listicle"

    # Explainer patterns
    if re.search(r"\b(what is|what are|vad är|hvad er|definition|meaning)\b", text):
        return "explainer"

    return "guide"
