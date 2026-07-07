"""Shared topic-clustering orchestration — the ONE place clusters are built.

Both the NiceGUI pipeline and (later) the Streamlit view call
``generate_topic_clusters()``; the logic lives here, never in a view
(goal #5 — no duplicated code).

Key change vs the old GSC-only clustering
-----------------------------------------
Keywords now come from the unified keyword universe
(utils/keyword_universe.py), so **competitor gap keywords** — terms
competitors rank for but mshop does not — drive clustering too, instead of
only the ~1/5 of terms mshop already ranks for.

Because GSC impressions (90-day counts) and Ahrefs volume (monthly) are on
different scales, we do NOT merge them into one weight and sort — that would
let high-impression own-keywords crowd every competitor gap out of the
input. Instead we take a quota of each: the top own keywords by impressions
PLUS the top gap keywords by volume. Every cluster is then tagged with which
of its keywords are gaps, so downstream "new content" steps get
competitor-driven opportunities.

The pure builder (`build_clustering_input`) takes DataFrames and is unit
tested. Only `generate_topic_clusters` touches state()/persistence.
"""

from __future__ import annotations

import re

import pandas as pd


def _norm_kw(kw) -> str:
    return re.sub(r"\s+", " ", str(kw).strip().lower())


def _gsc_pages_by_query(gsc_df: pd.DataFrame) -> dict:
    """Map normalized query -> up to 3 pages mshop ranks with (for enrichment)."""
    if gsc_df is None or getattr(gsc_df, "empty", True) or "query" not in gsc_df.columns:
        return {}
    out: dict = {}
    for q, grp in gsc_df.groupby("query"):
        out[_norm_kw(q)] = grp["page"].dropna().unique().tolist()[:3]
    return out


def build_clustering_input(
    universe_df: pd.DataFrame,
    gsc_df: pd.DataFrame | None = None,
    own_limit: int = 250,
    gap_limit: int = 250,
):
    """Select the keywords to cluster from the universe (own quota + gap quota).

    Returns ``(keywords_data, gap_lookup)`` where:
      - ``keywords_data`` is the list of dicts ai_generate_clusters expects
        (keyword / impressions / clicks / position / pages) plus ``volume``
        and ``is_gap`` extras (harmless to the prompt, used for tagging).
      - ``gap_lookup`` maps normalized keyword -> row info (is_gap, volume,
        competitors) so clusters can be tagged after the AI groups them.

    ``impressions`` carries the weight the prompt sorts on: real GSC
    impressions for own keywords, search volume for gaps (so a
    high-volume gap is not treated as zero-value).
    """
    if universe_df is None or universe_df.empty:
        return [], {}

    pages_by_q = _gsc_pages_by_query(gsc_df)

    own = universe_df[universe_df["own_ranks"]].copy()
    # Own keywords weighted by real impressions (fall back to volume when a
    # keyword only came from an Ahrefs own-export with no GSC impressions).
    own["_weight"] = own[["own_impressions", "volume"]].max(axis=1)
    own = own.sort_values("_weight", ascending=False).head(max(0, own_limit))

    gaps = universe_df[universe_df["is_gap"]].copy()
    gaps = gaps.sort_values("volume", ascending=False).head(max(0, gap_limit))

    selected = pd.concat([own, gaps], ignore_index=True)

    keywords_data = []
    gap_lookup: dict = {}
    for _, r in selected.iterrows():
        norm = _norm_kw(r["keyword"])
        is_gap = bool(r["is_gap"])
        weight = int(r["volume"]) if is_gap else int(max(r["own_impressions"], r["volume"]))
        keywords_data.append({
            "keyword": r["keyword"],
            "impressions": weight,
            "clicks": int(r["own_clicks"]),
            "position": float(r["own_position"]) if r["own_position"] else 0.0,
            "pages": pages_by_q.get(norm, []),
            "volume": int(r["volume"]),
            "is_gap": is_gap,
        })
        gap_lookup[norm] = {
            "is_gap": is_gap,
            "volume": int(r["volume"]),
            "competitors": list(r["competitors"]) if r["competitors"] is not None else [],
        }
    return keywords_data, gap_lookup


def tag_clusters_with_gaps(clusters: list, gap_lookup: dict) -> list:
    """Annotate each cluster with its gap (competitor-opportunity) keywords.

    Adds per cluster:
      - ``gap_keywords``      keywords competitors rank for, mshop doesn't
      - ``own_keywords``      keywords mshop already ranks for
      - ``gap_volume``        summed search volume of the gap keywords
      - ``is_opportunity``    True when the cluster is mostly gaps with no
                              existing mshop page (→ candidate for NEW content)

    Mutates in place and returns the list. Unknown keywords (not in the
    universe selection) are treated as own to avoid over-flagging.
    """
    for c in clusters or []:
        gap_kws, own_kws, gap_vol = [], [], 0
        for kw in c.get("keywords", []) or []:
            info = gap_lookup.get(_norm_kw(kw))
            if info and info["is_gap"]:
                gap_kws.append(kw)
                gap_vol += info["volume"]
            else:
                own_kws.append(kw)
        c["gap_keywords"] = gap_kws
        c["own_keywords"] = own_kws
        c["gap_volume"] = gap_vol
        has_own_page = bool(c.get("pages"))
        c["is_opportunity"] = bool(gap_kws) and len(gap_kws) >= len(own_kws) and not has_own_page
    return clusters


# ── state orchestration ──────────────────────────────────────────────

def generate_topic_clusters(client=None, own_limit: int = 250, gap_limit: int = 250) -> dict:
    """Build topic clusters from the keyword universe and store them.

    Reads keyword_universe (+ gsc_data for page enrichment) from state,
    calls the AI clusterer, enriches clusters with mshop pages, tags gap
    opportunities, and writes topic_clusters (+ content_gaps +
    content_roadmap) back to state and disk. Returns the topic_clusters dict.

    Falls back to GSC-only clustering when no universe exists yet, so the
    step is safe to run before any competitor upload.
    """
    from utils.state import state
    from utils.persistence import save_key, _save_ai_key, _volume_available
    from utils.ai_generator import get_client, ai_generate_clusters
    from utils.topic_clusters import (
        build_topic_clusters, normalize_cluster_pages,
        identify_content_gaps, generate_content_roadmap,
    )
    from config import get_anthropic_key

    s = state()
    gsc_df = s.get("gsc_data")
    universe = s.get("keyword_universe")
    language = s.get("content_language", "Swedish")
    site_context = s.get("site_context", "")

    # Prefer the universe; fall back to raw GSC so the step still works
    # before any competitor keywords are imported.
    keywords_data, gap_lookup = build_clustering_input(
        universe, gsc_df, own_limit=own_limit, gap_limit=gap_limit
    )
    if not keywords_data:
        if gsc_df is None or getattr(gsc_df, "empty", True):
            raise ValueError("No keyword data — fetch GSC and/or import competitor keywords first")
        # Legacy path: cluster straight from GSC top queries.
        kw = gsc_df.groupby("query").agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            position=("position", "mean"),
        ).sort_values("impressions", ascending=False).head(250).reset_index()
        keywords_data = [{
            "keyword": r["query"], "impressions": int(r["impressions"]),
            "clicks": int(r["clicks"]), "position": round(r["position"], 1),
            "pages": gsc_df[gsc_df["query"] == r["query"]]["page"].unique().tolist()[:3],
            "is_gap": False,
        } for _, r in kw.iterrows()]
        gap_lookup = {}

    if client is None:
        client = get_client(get_anthropic_key())

    result = ai_generate_clusters(
        client, keywords_data, site_context=site_context, language=language
    )

    # Base structure from the algorithmic clusterer (page_topics etc.),
    # overridden by the AI clusters when present.
    fallback = build_topic_clusters(
        gsc_df if gsc_df is not None else pd.DataFrame(), min_cluster_size=2
    )
    if result and result.get("clusters"):
        ai_clusters = result["clusters"]
        # Enrich each AI cluster with mshop page data from GSC so the
        # primary-cluster dedup downstream has real weights to compare on.
        if gsc_df is not None and not getattr(gsc_df, "empty", True):
            for c in ai_clusters:
                cluster_queries = c.get("queries", []) or c.get("keywords", [])
                cdf = gsc_df[gsc_df["query"].isin(cluster_queries)]
                page_agg = cdf.groupby("page").agg(
                    query_count=("query", "nunique"),
                    total_clicks=("clicks", "sum"),
                    total_impressions=("impressions", "sum"),
                    avg_position=("position", "mean"),
                ).reset_index().sort_values("total_clicks", ascending=False)
                c["pages"] = [{
                    "page": r["page"],
                    "query_count": int(r["query_count"]),
                    "total_clicks": int(r["total_clicks"]),
                    "total_impressions": int(r["total_impressions"]),
                    "avg_position": float(r["avg_position"]) if pd.notna(r["avg_position"]) else 0.0,
                } for _, r in page_agg.head(20).iterrows()]
                c["page_count"] = len(c["pages"])
        normalize_cluster_pages(ai_clusters)
        tag_clusters_with_gaps(ai_clusters, gap_lookup)
        fallback["clusters"] = ai_clusters
        fallback["summary"] = result.get("summary", "")

    s["topic_clusters"] = fallback
    save_key("topic_clusters")

    # Downstream artifacts (best-effort — never fail the whole step).
    auth = s.get("page_authority")
    try:
        s["content_gaps"] = identify_content_gaps(fallback.get("clusters", []), auth)
        save_key("content_gaps")
    except Exception as e:
        print(f"[clustering] content_gaps failed: {e}")
    try:
        s["content_roadmap"] = generate_content_roadmap(
            fallback.get("clusters", []), gsc_df, auth, language=language
        )
        save_key("content_roadmap")
    except Exception as e:
        print(f"[clustering] content_roadmap failed: {e}")

    return fallback
