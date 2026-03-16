"""
Cannibalization detection from GSC data.
Identifies keywords where multiple pages compete for the same query.
"""

import pandas as pd
import numpy as np


def detect_cannibalization(df: pd.DataFrame, min_impressions: int = 10) -> pd.DataFrame:
    """
    Find queries where multiple pages rank, indicating cannibalization.

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

        # Determine winner (most clicks + best position)
        best_page = query_data.iloc[0]
        positions = [p["position"] for p in pages_detail]
        best_position = min(positions)
        worst_position = max(positions)
        position_spread = worst_position - best_position

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
            "recommended_winner": best_page["page"],
            "winner_position": round(best_page["position"], 1),
            "winner_clicks": int(best_page["clicks"]),
            "lost_clicks_estimate": lost_clicks,
            "pages_detail": pages_detail,
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
