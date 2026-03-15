"""
Google Search Console API client
Handles authentication via service account and data retrieval
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

# Expected CTR by position (industry averages - adjustable)
CTR_BENCHMARKS = {
    1:  0.287,
    2:  0.157,
    3:  0.110,
    4:  0.080,
    5:  0.065,
    6:  0.054,
    7:  0.046,
    8:  0.040,
    9:  0.035,
    10: 0.030,
    11: 0.022,
    12: 0.018,
    13: 0.015,
    14: 0.013,
    15: 0.012,
    16: 0.010,
    17: 0.009,
    18: 0.008,
    19: 0.007,
    20: 0.006,
}


def get_expected_ctr(position: float) -> float:
    """Get expected CTR for a given average position"""
    pos_int = min(20, max(1, round(position)))
    return CTR_BENCHMARKS.get(pos_int, 0.005)


def get_ctr_gap(actual_ctr: float, position: float) -> float:
    """Calculate CTR gap (negative = underperforming)"""
    expected = get_expected_ctr(position)
    if expected == 0:
        return 0
    return (actual_ctr - expected) / expected  # relative gap


def build_gsc_service(credentials_json: dict):
    """Build GSC API service from service account credentials dict"""
    if not GOOGLE_AVAILABLE:
        raise ImportError("google-auth and google-api-python-client are required")
    
    credentials = service_account.Credentials.from_service_account_info(
        credentials_json, scopes=SCOPES
    )
    service = build("searchconsole", "v1", credentials=credentials)
    return service


def list_properties(service) -> list:
    """List all verified GSC properties"""
    result = service.sites().list().execute()
    return [s["siteUrl"] for s in result.get("siteEntry", [])]


def fetch_gsc_data(
    service,
    site_url: str,
    days: int = 90,
    row_limit: int = 5000,
    min_impressions: int = 10,
) -> pd.DataFrame:
    """
    Fetch query + page level data from GSC
    Returns DataFrame with columns: page, query, clicks, impressions, ctr, position
    """
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    request = {
        "startDate": str(start_date),
        "endDate": str(end_date),
        "dimensions": ["page", "query"],
        "rowLimit": row_limit,
        "startRow": 0,
        "dataState": "final",
    }
    
    response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
    rows = response.get("rows", [])
    
    if not rows:
        return pd.DataFrame()
    
    records = []
    for row in rows:
        records.append({
            "page": row["keys"][0],
            "query": row["keys"][1],
            "clicks": row["clicks"],
            "impressions": row["impressions"],
            "ctr": row["ctr"],
            "position": row["position"],
        })
    
    df = pd.DataFrame(records)
    
    # Filter low-impression queries (noise)
    df = df[df["impressions"] >= min_impressions].copy()
    
    # Add analysis columns
    df["expected_ctr"] = df["position"].apply(get_expected_ctr)
    df["ctr_gap_pct"] = df.apply(
        lambda r: get_ctr_gap(r["ctr"], r["position"]) * 100, axis=1
    )
    df["ctr_gap_abs"] = df["ctr"] - df["expected_ctr"]
    df["lost_clicks_estimate"] = (
        (df["expected_ctr"] - df["ctr"]).clip(lower=0) * df["impressions"]
    ).round(0).astype(int)
    df["position_rounded"] = df["position"].round(1)
    
    return df


def fetch_page_level_summary(
    service,
    site_url: str,
    days: int = 90,
) -> pd.DataFrame:
    """
    Page-level aggregated data (for overview metrics)
    """
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    request = {
        "startDate": str(start_date),
        "endDate": str(end_date),
        "dimensions": ["page"],
        "rowLimit": 5000,
        "dataState": "final",
    }
    
    response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
    rows = response.get("rows", [])
    
    if not rows:
        return pd.DataFrame()
    
    records = [
        {
            "page": row["keys"][0],
            "clicks": row["clicks"],
            "impressions": row["impressions"],
            "ctr": row["ctr"],
            "position": row["position"],
        }
        for row in rows
    ]
    
    df = pd.DataFrame(records)
    df["expected_ctr"] = df["position"].apply(get_expected_ctr)
    df["ctr_gap_pct"] = df.apply(
        lambda r: get_ctr_gap(r["ctr"], r["position"]) * 100, axis=1
    )
    df["lost_clicks_estimate"] = (
        (df["expected_ctr"] - df["ctr"]).clip(lower=0) * df["impressions"]
    ).round(0).astype(int)
    
    return df


def identify_ctr_gaps(df: pd.DataFrame, gap_threshold: float = -20.0) -> pd.DataFrame:
    """
    Filter to pages/queries where CTR is significantly below benchmark
    gap_threshold: percentage below expected (e.g., -20 = 20% below expected)
    """
    gaps = df[df["ctr_gap_pct"] <= gap_threshold].copy()
    gaps = gaps.sort_values("lost_clicks_estimate", ascending=False)
    return gaps


# ── Dummy/demo data for testing without live GSC ──────────────────────────────

def generate_demo_data() -> pd.DataFrame:
    """Generate realistic-looking demo data for UI testing"""
    import numpy as np
    np.random.seed(42)
    
    pages = [
        "https://mshop.se/vibratorer/",
        "https://mshop.se/dildoer/",
        "https://mshop.se/lingeri/",
        "https://mshop.se/kondomtillbehor/",
        "https://mshop.se/parbindsel/",
        "https://mshop.se/analleksaker/",
        "https://mshop.se/vibratorer/klitoris/",
        "https://mshop.se/products/we-vibe-chorus/",
        "https://mshop.se/products/womanizer-premium-2/",
        "https://mshop.se/lustgel/",
        "https://mshop.se/sm-leksaker/",
        "https://mshop.se/massagestavar/",
    ]
    
    queries_by_page = {
        pages[0]: ["vibrator", "vibratorer billiga", "bästa vibratorn", "vibrator för par", "vibrator test"],
        pages[1]: ["dildo", "realistisk dildo", "köpa dildo", "stor dildo", "dildo med sugpropp"],
        pages[2]: ["sexig lingeri", "erotisk lingeri", "lingeri dam", "body stocking", "underkläder sexig"],
        pages[3]: ["kondomer", "stora kondomer", "tunna kondomer", "kondomer köpa", "kondom gel"],
        pages[4]: ["sexleksaker par", "parvibrator", "leksaker för par", "paringssex", "vibrator för par"],
        pages[5]: ["analplugg", "anal vibrator", "analset", "anal dildo", "analleksaker nybörjare"],
        pages[6]: ["klitoris vibrator", "vibrator klitoris", "suger vibrator", "womanizer", "klitorisstimulator"],
        pages[7]: ["we-vibe chorus", "we vibe", "parvibrator app", "vibrator med app"],
        pages[8]: ["womanizer premium", "womanizer 2", "lufttrycksvibrator", "sugvibrator"],
        pages[9]: ["glidmedel", "lustgel", "massageolja", "glidmedel vattenbaserat"],
        pages[10]: ["handbojor", "bondage", "sm-utrustning", "bindning", "läder bondage"],
        pages[11]: ["massagestav", "magic wand", "stor vibrator", "massager"],
    }
    
    records = []
    for page, queries in queries_by_page.items():
        for query in queries:
            pos = np.random.uniform(1.5, 18.0)
            expected = get_expected_ctr(pos)
            # Some pages underperform, some overperform
            modifier = np.random.choice([0.3, 0.5, 0.7, 1.0, 1.2, 1.5], p=[0.1, 0.2, 0.3, 0.2, 0.1, 0.1])
            actual_ctr = expected * modifier
            impressions = int(np.random.lognormal(5, 1))
            clicks = int(actual_ctr * impressions)
            
            records.append({
                "page": page,
                "query": query,
                "clicks": clicks,
                "impressions": max(impressions, 15),
                "ctr": actual_ctr,
                "position": pos,
                "expected_ctr": expected,
                "ctr_gap_pct": get_ctr_gap(actual_ctr, pos) * 100,
                "ctr_gap_abs": actual_ctr - expected,
                "lost_clicks_estimate": max(0, int((expected - actual_ctr) * impressions)),
                "position_rounded": round(pos, 1),
            })
    
    return pd.DataFrame(records)
