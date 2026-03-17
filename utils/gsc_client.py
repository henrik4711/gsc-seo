"""
Google Search Console API client
Handles authentication via service account and data retrieval
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import ssl
import time

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def _execute_with_retry(request):
    """Execute a Google API request with retry on SSL/transient errors."""
    for attempt in range(MAX_RETRIES):
        try:
            return request.execute()
        except (ssl.SSLError, OSError, ConnectionError) as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                raise RuntimeError(
                    f"Google API SSL error after {MAX_RETRIES} retries. "
                    f"This is usually a temporary network issue — try again in a minute. "
                    f"Original error: {e}"
                ) from e


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
    result = _execute_with_retry(service.sites().list())
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
    
    response = _execute_with_retry(service.searchanalytics().query(siteUrl=site_url, body=request))
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
    
    response = _execute_with_retry(service.searchanalytics().query(siteUrl=site_url, body=request))
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
        "https://demo-store.example.com/headphones/",
        "https://demo-store.example.com/laptops/",
        "https://demo-store.example.com/running-shoes/",
        "https://demo-store.example.com/smartwatches/",
        "https://demo-store.example.com/backpacks/",
        "https://demo-store.example.com/keyboards/",
        "https://demo-store.example.com/headphones/wireless/",
        "https://demo-store.example.com/products/sony-wh1000xm5/",
        "https://demo-store.example.com/products/macbook-air-m3/",
        "https://demo-store.example.com/phone-cases/",
        "https://demo-store.example.com/monitors/",
        "https://demo-store.example.com/webcams/",
    ]

    queries_by_page = {
        pages[0]: ["headphones", "best headphones", "wireless headphones", "noise cancelling headphones", "headphones review"],
        pages[1]: ["laptop", "best budget laptop", "laptop for students", "lightweight laptop", "laptop deals"],
        pages[2]: ["running shoes", "best running shoes", "trail running shoes", "running shoes women", "marathon shoes"],
        pages[3]: ["smartwatch", "best smartwatch", "fitness tracker", "smartwatch for running", "gps watch"],
        pages[4]: ["backpack", "travel backpack", "laptop backpack", "hiking backpack", "waterproof backpack"],
        pages[5]: ["mechanical keyboard", "wireless keyboard", "gaming keyboard", "keyboard switch types", "ergonomic keyboard"],
        pages[6]: ["wireless earbuds", "bluetooth headphones", "earbuds for running", "budget earbuds", "true wireless"],
        pages[7]: ["sony wh1000xm5", "sony headphones", "best noise cancelling", "sony xm5 review"],
        pages[8]: ["macbook air m3", "macbook air review", "best ultrabook", "macbook vs dell xps"],
        pages[9]: ["phone case", "iphone case", "protective case", "clear phone case", "rugged case"],
        pages[10]: ["monitor", "4k monitor", "ultrawide monitor", "gaming monitor", "monitor for work"],
        pages[11]: ["webcam", "best webcam", "4k webcam", "streaming webcam", "webcam for zoom"],
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
