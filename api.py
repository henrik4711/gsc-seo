"""
Read-only REST API for wp_publisher and other external systems.
Reads directly from /data volume — no Streamlit dependency.

Run standalone:  uvicorn api:app --host=0.0.0.0 --port=$PORT
"""

import os
import json
import glob as globmod
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# ── Config ──────────────────────────────────────────────────────

DATA_DIR = os.environ.get("DATA_DIR", "/data")
AI_CACHE_DIR = os.path.join(DATA_DIR, "ai_cache")
API_KEY = os.environ.get("WP_PUBLISHER_API_KEY", "")

app = FastAPI(
    title="SEO Optimizer API",
    description="Read-only access to SEO analysis data for wp_publisher",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Auth ────────────────────────────────────────────────────────

def _check_key(x_api_key: Optional[str] = Header(None)):
    if not API_KEY:
        raise HTTPException(500, "WP_PUBLISHER_API_KEY not configured on server")
    if x_api_key != API_KEY:
        raise HTTPException(401, "Invalid or missing X-API-Key header")


# ── Data loaders (read from disk, no Streamlit) ────────────────

def _load_json(filename: str) -> Optional[dict | list]:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_csv_as_records(filename: str) -> Optional[list[dict]]:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    import pandas as pd
    df = pd.read_csv(path)
    if df.empty:
        return None
    return df.to_dict("records")


def _load_ai_cache(prefix: str) -> dict:
    """Load all AI cache files matching a prefix. Returns {url_hash: data}."""
    results = {}
    if not os.path.isdir(AI_CACHE_DIR):
        return results
    for fpath in globmod.glob(os.path.join(AI_CACHE_DIR, f"{prefix}*.json")):
        key = os.path.basename(fpath)[:-5]  # remove .json
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                results[key] = json.load(f)
        except Exception:
            pass
    return results


def _load_setting(filename: str) -> Optional[str]:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _available_data_keys() -> list[str]:
    """List which data files actually exist on disk."""
    keys = []
    file_map = {
        "audit_results": "audit_results.json",
        "gsc_data": "gsc_data.csv",
        "ctr_gaps": "ctr_gaps.csv",
        "cannibalization": "cannibalization.json",
        "topic_clusters": "topic_clusters.json",
        "content_roadmap": "content_roadmap.json",
        "sf_link_map": "sf_link_map.json",
        "page_authority": "page_authority.csv",
    }
    for key, fname in file_map.items():
        if os.path.exists(os.path.join(DATA_DIR, fname)):
            keys.append(key)
    # Count AI cache files
    if os.path.isdir(AI_CACHE_DIR):
        ai_count = len([f for f in os.listdir(AI_CACHE_DIR) if f.endswith(".json")])
        if ai_count > 0:
            keys.append(f"ai_cache ({ai_count} files)")
    return keys


# ── Endpoints ───────────────────────────────────────────────────

@app.get("/api/health")
def health():
    """Public health check — no API key required."""
    return {
        "status": "ok",
        "data_dir": DATA_DIR,
        "data_keys": _available_data_keys(),
    }


@app.get("/api/site-structure")
def site_structure(x_api_key: Optional[str] = Header(None)):
    """Topic clusters, category hierarchy, and content roadmap."""
    _check_key(x_api_key)

    clusters = _load_json("topic_clusters.json")
    roadmap = _load_json("content_roadmap.json")
    site_context = _load_setting("site_context.txt")
    language = _load_setting("content_language.txt")

    if not clusters:
        raise HTTPException(404, "topic_clusters not available — run Step 4 in pipeline")

    # Summarize clusters (don't send all raw queries)
    cluster_summary = []
    for c in clusters.get("clusters", []):
        cluster_summary.append({
            "topic": c.get("topic"),
            "query_count": c.get("query_count", 0),
            "total_clicks": c.get("total_clicks", 0),
            "total_impressions": c.get("total_impressions", 0),
            "page_count": c.get("page_count", 0),
            "pages": c.get("pages", []),
            "is_split": c.get("is_split", False),
        })

    return {
        "site_context": site_context,
        "language": language,
        "cluster_count": len(cluster_summary),
        "clusters": cluster_summary,
        "page_topics": clusters.get("page_topics", {}),
        "content_roadmap": roadmap,
    }


@app.get("/api/top-keywords")
def top_keywords(
    limit: int = Query(50, ge=1, le=500),
    x_api_key: Optional[str] = Header(None),
):
    """Top keywords sorted by impressions, with CTR and position."""
    _check_key(x_api_key)

    records = _load_csv_as_records("gsc_data.csv")
    if not records:
        raise HTTPException(404, "gsc_data not available — run Step 2 in pipeline")

    # Aggregate by query (sum clicks/impressions, weighted avg position)
    from collections import defaultdict
    by_query = defaultdict(lambda: {"clicks": 0, "impressions": 0, "pos_sum": 0.0, "count": 0, "pages": set()})
    for r in records:
        q = r.get("query", "")
        if not q:
            continue
        entry = by_query[q]
        entry["clicks"] += int(r.get("clicks", 0) or 0)
        entry["impressions"] += int(r.get("impressions", 0) or 0)
        entry["pos_sum"] += float(r.get("position", 0) or 0)
        entry["count"] += 1
        page = r.get("page", "")
        if page:
            entry["pages"].add(page)

    keywords = []
    for query, data in by_query.items():
        impr = data["impressions"]
        clicks = data["clicks"]
        avg_pos = round(data["pos_sum"] / data["count"], 1) if data["count"] else 0
        ctr = round(clicks / impr, 4) if impr > 0 else 0
        keywords.append({
            "query": query,
            "clicks": clicks,
            "impressions": impr,
            "position": avg_pos,
            "ctr": ctr,
            "pages": sorted(data["pages"]),
        })

    keywords.sort(key=lambda k: -k["impressions"])
    return {"count": len(keywords), "keywords": keywords[:limit]}


@app.get("/api/content-gaps")
def content_gaps(x_api_key: Optional[str] = Header(None)):
    """Topics we should write about but don't rank for yet."""
    _check_key(x_api_key)

    roadmap = _load_json("content_roadmap.json")
    if not roadmap:
        raise HTTPException(404, "content_roadmap not available — run Step 10 in pipeline")

    return {
        "total_articles_needed": roadmap.get("total_articles", 0),
        "total_opportunity_impressions": roadmap.get("total_opportunity_impressions", 0),
        "articles_needed": roadmap.get("articles_needed", []),
        "supporting_content": roadmap.get("supporting_content", []),
    }


@app.get("/api/page-audit")
def page_audit(
    url: str = Query(..., description="Full URL to look up"),
    x_api_key: Optional[str] = Header(None),
):
    """Full audit data for a specific URL."""
    _check_key(x_api_key)

    audit = _load_json("audit_results.json")
    if not audit:
        raise HTTPException(404, "audit_results not available — run Step 6 in pipeline")

    target = _normalize_url(url)
    match = None
    for r in audit:
        if _normalize_url(r.get("url", "")) == target:
            match = r
            break

    if not match:
        raise HTTPException(404, f"No audit data for URL: {url}")

    # Enrich with quality verdict + AI plan if available
    # stable_hash uses the URL as stored in audit_results (already normalized)
    from utils.quality_check_runner import quality_key as _api_qk
    quality_path = os.path.join(AI_CACHE_DIR, f"{_api_qk(match['url'])}.json")
    url_hash = _stable_hash(match["url"])
    if os.path.exists(quality_path):
        try:
            with open(quality_path, "r", encoding="utf-8") as f:
                match["quality_assessment"] = json.load(f)
        except Exception:
            pass

    # Enrich with AI plan if available
    plan_path = os.path.join(AI_CACHE_DIR, f"_ai_plan_{url_hash}.json")
    if os.path.exists(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                match["ai_plan"] = json.load(f)
        except Exception:
            pass

    return match


@app.get("/api/page-audits")
def page_audits(
    page_type: Optional[str] = Query(None, description="Filter by page type: category, product, blog, faq, info"),
    limit: int = Query(100, ge=1, le=1000),
    x_api_key: Optional[str] = Header(None),
):
    """List all audited pages (summary), optionally filtered by type."""
    _check_key(x_api_key)

    audit = _load_json("audit_results.json")
    if not audit:
        raise HTTPException(404, "audit_results not available — run Step 6 in pipeline")

    results = []
    for r in audit:
        if page_type and r.get("page_type") != page_type:
            continue
        results.append({
            "url": r.get("url"),
            "page_type": r.get("page_type"),
            "title": r.get("title"),
            "h1": r.get("h1"),
            "meta_description": r.get("meta_description"),
            "word_count": r.get("word_count", 0),
            "intro_word_count": r.get("intro_word_count", 0),
            "bottom_word_count": r.get("bottom_word_count", 0),
            "total_editorial_words": r.get("total_editorial_words", 0),
            "meta_score": r.get("meta_score"),
            "content_score": r.get("content_score"),
            "impressions": r.get("impressions", 0),
            "clicks": r.get("clicks", 0),
            "lost_clicks_estimate": r.get("lost_clicks_estimate", 0),
            "position": r.get("position"),
        })

    results.sort(key=lambda r: -(r.get("impressions") or 0))
    return {"count": len(results), "pages": results[:limit]}


@app.get("/api/internal-links")
def internal_links(x_api_key: Optional[str] = Header(None)):
    """Internal linking structure from Screaming Frog analysis."""
    _check_key(x_api_key)

    link_map = _load_json("sf_link_map.json")
    if not link_map:
        raise HTTPException(404, "sf_link_map not available — upload Screaming Frog data in Step 3")

    return {
        "total_links": link_map.get("total_links", 0),
        "unique_pairs": link_map.get("unique_pairs", 0),
        "unique_pages": link_map.get("unique_pages", 0),
        "links_from": link_map.get("links_from", {}),
        "links_to": link_map.get("links_to", {}),
        "anchor_quality": link_map.get("anchor_quality", {}),
    }


@app.get("/api/cannibalization")
def cannibalization(x_api_key: Optional[str] = Header(None)):
    """Keyword conflicts — multiple pages competing for same queries."""
    _check_key(x_api_key)

    data = _load_json("cannibalization.json")
    if not data:
        raise HTTPException(404, "cannibalization not available — run Step 8 in pipeline")

    # cannibalization is saved as dataframe_json (list of records)
    if isinstance(data, list):
        return {"count": len(data), "conflicts": data}
    return {"count": 0, "conflicts": []}


@app.get("/api/quality-verdicts")
def quality_verdicts(x_api_key: Optional[str] = Header(None)):
    """AI quality verdicts for all checked pages (KEEP/IMPROVE/REWRITE)."""
    _check_key(x_api_key)

    from utils.quality_check_runner import QUALITY_KEY_PREFIX as _QPF
    verdicts = _load_ai_cache(_QPF)
    if not verdicts:
        raise HTTPException(404, "No quality verdicts — run Step 7 in pipeline")

    # Build URL lookup from audit_results
    audit = _load_json("audit_results.json") or []
    hash_to_url = {}
    for r in audit:
        u = r.get("url", "")
        if u:
            hash_to_url[_stable_hash(u)] = u

    results = []
    for key, data in verdicts.items():
        url_hash = key[len(_QPF):]
        results.append({
            "url": hash_to_url.get(url_hash, f"(hash:{url_hash})"),
            "verdict": data.get("verdict"),
            "score": data.get("score"),
            "summary": data.get("summary"),
            "main_issues": data.get("main_issues", []),
        })

    results.sort(key=lambda r: r.get("score") or 0)
    return {"count": len(results), "verdicts": results}


# ── Helpers ─────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    """Must match utils.ui_helpers.normalize_url (without Streamlit dependency)."""
    if not url:
        return ""
    u = str(url).strip()
    if "#" in u:
        u = u[:u.index("#")]
    if "?" in u:
        u = u[:u.index("?")]
    u = u.replace("http://", "https://")
    u = u.replace("://www.", "://")
    u = u.rstrip("/")
    u = u.lower()
    return u


def _stable_hash(text: str) -> str:
    """Must match utils.ui_helpers.stable_hash exactly."""
    import hashlib
    return hashlib.md5(text.encode()).hexdigest()[:8]
