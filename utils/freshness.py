"""
Data freshness inspection for the Dashboard's "what's stale?" panel.

The system has 15+ persisted datasets (GSC, audit, clusters, SF, Ahrefs,
cannibalization, validation, etc.) plus hundreds of AI cache files. The
user previously had NO way to see WHEN each was last refreshed or WHAT
needed re-running — leading to "the dashboard says 454 unclustered but I
fixed them" frustration. This module computes the freshness signals so
the Dashboard can render a single-glance status grid.

We deliberately don't store our own timestamps for the persisted keys —
the filesystem mtime on /data/<key>.{csv,json} IS the source of truth
for "when did this last get saved". Adds zero coupling to the save path.
"""

import os
import json
import time
from datetime import datetime, timezone
from typing import Optional

import streamlit as st

from utils.persistence import (
    DATA_DIR,
    AI_CACHE_DIR,
    PERSIST_KEYS,
    _file_path,
    _is_ai_key,
)


# Push log paths — kept in sync with utils/mshop_admin_api.py and
# utils/footer_text_api.py (DRY would require a shared constants module
# but the value is repeated only here for read-only reporting).
MSHOP_ADMIN_LOG = os.path.join(DATA_DIR, "mshop_admin_push_log.json")
FOOTER_PUSH_LOG = os.path.join(DATA_DIR, "footer_push_log.json")


# Datasets shown in the freshness panel, in display order. The third
# tuple item is the "where to refresh" hint shown to the user when the
# dataset is stale/missing.
TRACKED_DATASETS = [
    # (session_key, label, refresh hint, freshness window in days)
    ("gsc_data",        "GSC data",          "Setup & Connect → Refresh GSC Data",   7),
    ("audit_results",   "Page audit",        "Page Auditor → Re-scrape ALL pages",   14),
    ("topic_clusters",  "Topic clusters",    "Run Pipeline → Step 5 (Topic Clusters)", 30),
    ("cannibalization", "Cannibalization",   "Run Pipeline → Step 4 (Cannibalization)", 14),
    ("ctr_gaps",        "CTR analysis",      "Run Pipeline → Step 3 (CTR Analysis)", 7),
    ("page_authority",  "Page authority",    "Upload Ahrefs → Build Page Authority", 90),
    ("sf_pages",        "Screaming Frog pages",  "Upload Ahrefs → SF section",       60),
    ("sf_crawl_issues", "Crawl issues",      "Run Pipeline → Step 3",                30),
]

# Single AI-cache keys (not prefixes — one file each).
TRACKED_AI_SINGLES = [
    ("_site_validation", "Site validation", "Run Pipeline → Step 9", 7),
    ("_ideal_structure", "Ideal structure", "Run Pipeline → Step 10", 30),
]

# AI-cache prefixes (each is many files; we report count + oldest).
TRACKED_AI_BATCHES = [
    ("_cluster_health_", "Cluster health",       "Cluster Health → Evaluate top 5"),
    ("_ai_plan_",        "AI implementation plans", "Implementation → Generate next 10"),
    ("_quality_",        "AI quality verdicts",  "Run Pipeline → Step 7"),
    ("_bottom_text_",    "Generated bottom texts","Quick Wins / Action Plan"),
    ("_intro_text_",     "Generated intro texts", "Quick Wins / Action Plan"),
]


def _file_mtime(path: str) -> Optional[float]:
    try:
        return os.path.getmtime(path) if os.path.exists(path) else None
    except OSError:
        return None


def _humanize_age(epoch_seconds: float) -> str:
    """Convert an mtime to "2h ago" / "3 days ago" / "5 weeks ago" form.
    Compact enough to fit in the freshness grid without wrapping."""
    delta = max(0, time.time() - epoch_seconds)
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta / 60)} min ago"
    if delta < 86400:
        return f"{int(delta / 3600)} h ago"
    days = delta / 86400
    if days < 14:
        return f"{int(days)} days ago"
    if days < 60:
        return f"{int(days / 7)} weeks ago"
    return f"{int(days / 30)} months ago"


def _status_for(age_days: float, threshold_days: int) -> str:
    """Map an age-in-days to a 3-level traffic-light status.
    green = within threshold, yellow = up to 2× threshold, red = older.
    Missing datasets are handled separately (status='missing')."""
    if age_days <= threshold_days:
        return "fresh"
    if age_days <= threshold_days * 2:
        return "aging"
    return "stale"


def _row_count_for(key: str) -> Optional[int]:
    """Best-effort row/item count from in-memory session_state. We don't
    re-read the file because that defeats the purpose of an at-a-glance
    panel — and session_state already has the value if the data is loaded."""
    val = st.session_state.get(key)
    if val is None:
        return None
    try:
        if hasattr(val, "shape"):  # DataFrame
            return int(val.shape[0])
        if isinstance(val, (list, dict)):
            # For dicts we report the top-level key count, which is the
            # right thing for topic_clusters (count of clusters via the
            # "clusters" sub-list) or sf_crawl_issues (count of issue
            # categories).
            if isinstance(val, dict) and "clusters" in val and isinstance(val["clusters"], list):
                return len(val["clusters"])
            return len(val)
    except Exception:
        pass
    return None


def _persisted_dataset_info(key: str, label: str, hint: str, fresh_days: int) -> dict:
    """Build the freshness row for a tracked persisted key. Resolves the
    on-disk path via _file_path so we stay in sync with how `save()` writes."""
    data_type = PERSIST_KEYS.get(key, "json")
    path = _file_path(key, data_type)
    mtime = _file_mtime(path)

    row = {
        "key": key,
        "label": label,
        "hint": hint,
        "fresh_days": fresh_days,
        "row_count": _row_count_for(key),
    }
    if mtime is None:
        row["status"] = "missing"
        row["age_human"] = "never"
        row["timestamp_iso"] = ""
        row["age_days"] = None
    else:
        age_days = (time.time() - mtime) / 86400
        row["status"] = _status_for(age_days, fresh_days)
        row["age_human"] = _humanize_age(mtime)
        row["timestamp_iso"] = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        row["age_days"] = round(age_days, 1)
    return row


def _ai_single_info(key: str, label: str, hint: str, fresh_days: int) -> dict:
    """Same as _persisted_dataset_info but for a single-file AI cache key."""
    path = os.path.join(AI_CACHE_DIR, f"{key}.json")
    mtime = _file_mtime(path)
    row = {
        "key": key,
        "label": label,
        "hint": hint,
        "fresh_days": fresh_days,
        "row_count": None,
    }
    if mtime is None:
        row["status"] = "missing"
        row["age_human"] = "never"
        row["timestamp_iso"] = ""
        row["age_days"] = None
    else:
        age_days = (time.time() - mtime) / 86400
        row["status"] = _status_for(age_days, fresh_days)
        row["age_human"] = _humanize_age(mtime)
        row["timestamp_iso"] = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        row["age_days"] = round(age_days, 1)
    return row


def _ai_batch_info(prefix: str, label: str, hint: str) -> dict:
    """Count cached files for a prefix + report oldest/newest. Useful for
    batches like _ai_plan_<hash> where there's no single timestamp — the
    user wants to know "how many plans have I generated, and is any of
    them stale?"."""
    row = {
        "prefix": prefix,
        "label": label,
        "hint": hint,
        "count": 0,
        "oldest_age_human": "",
        "newest_age_human": "",
    }
    if not os.path.isdir(AI_CACHE_DIR):
        return row
    mtimes = []
    try:
        for name in os.listdir(AI_CACHE_DIR):
            if not name.startswith(prefix):
                continue
            full = os.path.join(AI_CACHE_DIR, name)
            mt = _file_mtime(full)
            if mt is not None:
                mtimes.append(mt)
    except OSError:
        return row
    if not mtimes:
        return row
    row["count"] = len(mtimes)
    row["oldest_age_human"] = _humanize_age(min(mtimes))
    row["newest_age_human"] = _humanize_age(max(mtimes))
    return row


def _read_push_log(path: str, since_epoch: float) -> list:
    """Read entries from a push log filtered to those after a timestamp.
    Each log file is a JSON array (capped at 500 entries by the writer)
    so reading it is cheap. Returns [] if the log doesn't exist yet."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            entries = json.load(f) or []
    except (OSError, ValueError):
        return []
    if not isinstance(entries, list):
        return []
    recent = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        ts_str = e.get("timestamp", "")
        try:
            # Push logs use UTC ISO timestamps ending in 'Z'.
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.timestamp() >= since_epoch:
                recent.append(e)
        except (ValueError, TypeError):
            continue
    return recent


def _push_summary(days: int = 7) -> dict:
    """Aggregate push activity over the last N days from both push logs.
    Returns counts of successful pushes per field type + the latest URL."""
    since = time.time() - days * 86400
    admin_entries = _read_push_log(MSHOP_ADMIN_LOG, since)
    footer_entries = _read_push_log(FOOTER_PUSH_LOG, since)

    intro_count = 0
    meta_title_count = 0
    meta_desc_count = 0
    bottom_count = 0
    latest_ts = 0
    latest_url = ""

    for e in admin_entries:
        if e.get("status") != "success":
            continue
        payload = e.get("payload") or {}
        if payload.get("description") is not None:
            intro_count += 1
        if payload.get("metaTitle") is not None:
            meta_title_count += 1
        if payload.get("metaDescription") is not None:
            meta_desc_count += 1
        try:
            ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")).timestamp()
            if ts > latest_ts:
                latest_ts = ts
                # admin payloads carry the page id, not the URL — caller
                # can drill into the log file if they need the URL.
                latest_url = f"{payload.get('categoryId') or payload.get('cmsPageId') or payload.get('filterPageId') or '?'}"
        except (KeyError, ValueError):
            pass

    for e in footer_entries:
        if e.get("status") != "success":
            continue
        bottom_count += 1
        try:
            ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")).timestamp()
            if ts > latest_ts:
                latest_ts = ts
                payload = e.get("payload") or {}
                latest_url = payload.get("url", "") or latest_url
        except (KeyError, ValueError):
            pass

    return {
        "days": days,
        "intro": intro_count,
        "meta_title": meta_title_count,
        "meta_description": meta_desc_count,
        "bottom_text": bottom_count,
        "total": intro_count + meta_title_count + meta_desc_count + bottom_count,
        "latest_ts": latest_ts,
        "latest_ts_human": _humanize_age(latest_ts) if latest_ts else "",
        "latest_url": latest_url,
    }


def get_freshness_report() -> dict:
    """Top-level: build the full freshness report for Dashboard rendering.
    Single function so the view doesn't need to know about helpers."""
    return {
        "datasets": [
            _persisted_dataset_info(key, label, hint, days)
            for (key, label, hint, days) in TRACKED_DATASETS
        ],
        "ai_singles": [
            _ai_single_info(key, label, hint, days)
            for (key, label, hint, days) in TRACKED_AI_SINGLES
        ],
        "ai_batches": [
            _ai_batch_info(prefix, label, hint)
            for (prefix, label, hint) in TRACKED_AI_BATCHES
        ],
        "push_summary": _push_summary(days=7),
    }
