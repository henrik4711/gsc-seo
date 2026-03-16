"""
Topic clustering from GSC keyword data.
Groups queries into semantic clusters and maps them to pages.
Identifies content gaps and overlap between pages.
"""

import pandas as pd
import numpy as np
from collections import defaultdict
import re


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

        enriched_clusters.append({
            "topic": cluster["label"],
            "core_terms": cluster["core_terms"],
            "query_count": len(cluster["query_indices"]),
            "queries": cluster_queries["query"].tolist(),
            "total_clicks": int(cluster_queries["clicks"].sum()),
            "total_impressions": int(cluster_queries["impressions"].sum()),
            "pages": pages.to_dict("records"),
            "page_count": len(pages),
            "is_split": len(pages) > 1,  # topic served by multiple pages
        })

    enriched_clusters.sort(key=lambda x: -x["total_impressions"])

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
                auth = authority_data[authority_data["page"].str.rstrip("/").str.lower() == page.rstrip("/").lower()]
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
