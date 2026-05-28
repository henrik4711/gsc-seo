"""
Content Freshness — detect decaying pages from GSC impression trends.

A page is "decaying" when its impressions drop materially between a recent
window and a prior window of equal length. Decaying pages with material
historical traffic are prime candidates for a content refresh (rewrite
intro, add 2026 examples, update specs) — refreshing them is cheaper than
ranking a new page and usually pays back within weeks.

Single source of truth for:
  - detect_decaying_pages: compute the decay list from two GSC windows
  - refresh_decaying_pages_data: orchestrator that fetches windows + runs
    detection + persists, called by the Content Freshness view
  - get_decaying_pages: read cached results (UI helper)
  - format_freshness_signal_for_prompt: inject decay context into AI
    regeneration prompts so refreshed text actually targets the decay angle

Per-page decay record shape:
{
  "url": "https://...",
  "prior_impressions": 1234,
  "recent_impressions": 612,
  "impression_drop_pct": 50.4,      # positive = page is losing impressions
  "prior_clicks": 87,
  "recent_clicks": 38,
  "lost_clicks": 49,                # prior - recent, clamped to 0
  "prior_position": 8.2,
  "recent_position": 11.7,
  "position_drop": 3.5,             # positive = ranking worse
  "severity": "critical" | "warn" | "watch",
}
"""

import os
import json
from datetime import datetime, timezone
from typing import Optional

import streamlit as st
import pandas as pd

from utils.persistence import AI_CACHE_DIR
from utils.ui_helpers import normalize_url


# Single-file cache key — follows the existing AI_CACHE_DIR pattern so
# it auto-loads at startup and survives Railway redeploys. The key is
# listed in AI_CACHE_PREFIXES under "_decaying_pages" so persistence.py
# picks it up.
DECAYING_CACHE_KEY = "_decaying_pages"


# Thresholds — tuned for e-commerce category/blog pages where 100+
# monthly impressions is "real traffic" and a 20%+ drop is "noticeable".
# Below these floors we'd flag noise: a page that went from 5 → 2
# impressions doesn't need a content refresh, it just happens to be
# small.
DEFAULT_MIN_PRIOR_IMPRESSIONS = 100
DEFAULT_DROP_PCT_THRESHOLD = 20.0


def detect_decaying_pages(
    recent_df: pd.DataFrame,
    prior_df: pd.DataFrame,
    min_prior_impressions: int = DEFAULT_MIN_PRIOR_IMPRESSIONS,
    drop_pct_threshold: float = DEFAULT_DROP_PCT_THRESHOLD,
) -> list:
    """Compare two GSC windows at page level and flag pages where
    impressions dropped >= drop_pct_threshold AND prior_impressions
    >= min_prior_impressions.

    Sorted by lost_clicks descending — i.e. the page where refreshing
    would recover the most traffic comes first.

    Returns [] when either window is empty or no page meets thresholds.
    """
    if recent_df is None or prior_df is None:
        return []
    if recent_df.empty and prior_df.empty:
        return []

    # Merge on page — outer so pages missing from recent (full drop)
    # are still considered. fillna(0) handles "page had 0 impressions
    # in recent window" cleanly.
    if "page" not in prior_df.columns:
        return []
    merged = prior_df.merge(
        recent_df,
        on="page",
        how="left",
        suffixes=("_prior", "_recent"),
    )
    # When recent has no data for a page, the suffix columns are NaN.
    for col in ("clicks_recent", "impressions_recent", "ctr_recent", "position_recent"):
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)

    merged["impression_drop_pct"] = (
        (merged["impressions_prior"] - merged["impressions_recent"])
        / merged["impressions_prior"].replace(0, pd.NA)
        * 100
    )
    merged["lost_clicks"] = (
        merged["clicks_prior"] - merged["clicks_recent"]
    ).clip(lower=0).round(0).astype(int)
    # Position: higher = worse. position_drop > 0 means ranking declined.
    # Skip pages that disappeared from recent (position_recent=0) so we
    # don't report a misleading "position dropped to 0" — handled below.
    merged["position_drop"] = (
        merged["position_recent"] - merged["position_prior"]
    ).round(1)

    flagged = merged[
        (merged["impressions_prior"] >= min_prior_impressions)
        & (merged["impression_drop_pct"] >= drop_pct_threshold)
    ].copy()

    if flagged.empty:
        return []

    def _severity(drop_pct: float, lost: int) -> str:
        if drop_pct >= 60 or lost >= 100:
            return "critical"
        if drop_pct >= 35 or lost >= 30:
            return "warn"
        return "watch"

    out = []
    for _, r in flagged.sort_values("lost_clicks", ascending=False).iterrows():
        drop_pct = float(r["impression_drop_pct"])
        lost = int(r["lost_clicks"])
        out.append({
            "url": str(r["page"]),
            "prior_impressions": int(r["impressions_prior"]),
            "recent_impressions": int(r["impressions_recent"]),
            "impression_drop_pct": round(drop_pct, 1),
            "prior_clicks": int(r["clicks_prior"]),
            "recent_clicks": int(r["clicks_recent"]),
            "lost_clicks": lost,
            "prior_position": round(float(r["position_prior"]), 1),
            "recent_position": round(float(r["position_recent"]), 1) if r["impressions_recent"] > 0 else None,
            "position_drop": round(float(r["position_drop"]), 1) if r["impressions_recent"] > 0 else None,
            "severity": _severity(drop_pct, lost),
        })
    return out


def refresh_decaying_pages_data(
    recent_days: int = 30,
    prior_days: int = 30,
    min_prior_impressions: int = DEFAULT_MIN_PRIOR_IMPRESSIONS,
    drop_pct_threshold: float = DEFAULT_DROP_PCT_THRESHOLD,
) -> dict:
    """Pipeline entry point — fetch two windows from GSC, detect decay,
    persist results. Returns the same payload that's stored.

    Raises ValueError if GSC isn't set up (no creds or no site picked) —
    the view catches and renders a clear message rather than letting the
    exception bubble.
    """
    from utils.gsc_client import build_gsc_service, fetch_gsc_two_windows

    creds = st.session_state.get("gsc_credentials")
    if not creds:
        raise ValueError(
            "GSC credentials missing — set them up in Setup & Connect first"
        )
    # Prefer the user-selected site (`gsc_site`, written by Setup UI); fall
    # back to the env-var default (`gsc_site_url`, set by GSC_SITE_URL).
    site_url = st.session_state.get("gsc_site") or st.session_state.get("gsc_site_url")
    if not site_url:
        raise ValueError(
            "No GSC site selected — pick one in Setup & Connect first"
        )

    service = build_gsc_service(creds)
    windows = fetch_gsc_two_windows(
        service, site_url,
        recent_days=recent_days,
        prior_days=prior_days,
    )
    decaying = detect_decaying_pages(
        windows["recent_df"],
        windows["prior_df"],
        min_prior_impressions=min_prior_impressions,
        drop_pct_threshold=drop_pct_threshold,
    )

    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "site_url": site_url,
        "recent_window": windows["recent_window"],
        "prior_window": windows["prior_window"],
        "config": {
            "min_prior_impressions": min_prior_impressions,
            "drop_pct_threshold": drop_pct_threshold,
            "recent_days": recent_days,
            "prior_days": prior_days,
        },
        "total_pages_with_traffic": int(len(windows["prior_df"])),
        "decaying_count": len(decaying),
        "decaying": decaying,
    }

    st.session_state[DECAYING_CACHE_KEY] = payload
    # Persist via the standard AI cache path so it survives Railway
    # restarts and auto-hydrates on next boot (persistence.load_all
    # picks up any file matching AI_CACHE_PREFIXES).
    try:
        os.makedirs(AI_CACHE_DIR, exist_ok=True)
        path = os.path.join(AI_CACHE_DIR, f"{DECAYING_CACHE_KEY}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
    except Exception as e:
        # Best-effort — surfacing a save error here would mask the
        # actual detection result the user just paid Claude (no AI was
        # called here, but the GSC quota was). Log + continue.
        print(f"[content_freshness] persist failed: {e}")

    return payload


def get_decaying_pages() -> Optional[dict]:
    """UI helper — return the cached freshness report or None if not run yet."""
    return st.session_state.get(DECAYING_CACHE_KEY)


def find_decay_for_url(url: str) -> Optional[dict]:
    """Look up the decay record for a single URL. Used by the AI prompt
    formatter to inject "this page is decaying" context into the regen
    prompt for just the URL being regenerated."""
    payload = get_decaying_pages()
    if not payload:
        return None
    norm = normalize_url(url)
    for entry in payload.get("decaying", []):
        if normalize_url(entry.get("url", "")) == norm:
            return entry
    return None


def format_freshness_signal_for_prompt(url: str) -> str:
    """Return a short prompt fragment about THIS page's traffic decay,
    or empty string when the page isn't flagged as decaying.

    Called from the AI generation functions (mirrors how
    _format_cluster_health_insights is called from ai_generator.py) so
    Claude actually targets the decay angle instead of generating a
    generic refresh.
    """
    entry = find_decay_for_url(url)
    if not entry:
        return ""

    parts = [
        "",
        "## CONTENT FRESHNESS SIGNAL — this page is losing traffic",
        f"- Impressions dropped {entry['impression_drop_pct']}% "
        f"({entry['prior_impressions']:,} → {entry['recent_impressions']:,}) "
        f"between the two 30-day windows.",
        f"- Clicks lost in this period: {entry['lost_clicks']:,}",
    ]
    if entry.get("position_drop") is not None and entry["position_drop"] > 0:
        parts.append(
            f"- Average position worsened by {entry['position_drop']} "
            f"({entry['prior_position']} → {entry['recent_position']})."
        )
    parts.extend([
        "",
        "REFRESH FOCUS — when rewriting this page, prioritize:",
        "1. Update any time-sensitive references (years, prices, model versions, statistics).",
        "2. Add 2-3 fresh, 2026-specific examples or product mentions.",
        "3. Strengthen the intro hook — the existing one is no longer attracting clicks.",
        "4. Check if newer competitor pages are ranking — if so, add the angle they cover.",
        "5. Add or refresh the FAQ section to capture long-tail / AI-Overview queries.",
        "",
    ])
    return "\n".join(parts)
