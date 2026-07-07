"""Bulk page audit — framework-free port of views/run_pipeline._run_bulk_audit.

Single source of truth for scraping the site's live pages into
``audit_results``. Same behaviour as the proven Streamlit runner: URL source
is the Mshop Admin API active-pages list (categories + CMS + filterpages),
falling back to GSC pages; results are checkpointed to disk every 5 pages and
the in-memory batch is cleared so memory plateaus regardless of page count
(resumability across crashes / redeploys). Reports through a Progress object
instead of st.* so it runs under NiceGUI, Streamlit, or headless.
"""

from __future__ import annotations

import json
import os

from utils.state import state
from utils.progress import Progress, NULL
from utils.persistence import save_key, _volume_available, _file_path

CHECKPOINT_INTERVAL = 5


def _canonicalize_existing(existing, audit_path, norm, classify_page_type):
    """Dedup www/non-www + backfill page_type on already-scraped rows (no network)."""
    if not existing:
        return existing
    by_norm = {}
    for r in existing:
        nu = norm(r.get("url", ""))
        if not nu:
            continue
        r["url"] = nu
        prev = by_norm.get(nu)
        if prev is None or len(r.get("body_text") or "") > len(prev.get("body_text") or ""):
            by_norm[nu] = r
    removed = len(existing) - len(by_norm)
    if removed > 0:
        existing = list(by_norm.values())
    backfilled = 0
    for r in existing:
        current = r.get("page_type") or ""
        if current in ("", "unknown", "missing"):
            pt = classify_page_type(r.get("url", "")).get("page_type", "unknown")
            if pt and pt != current:
                r["page_type"] = pt
                backfilled += 1
    if (backfilled or removed) and audit_path:
        try:
            with open(audit_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=1, default=str)
        except Exception:
            pass
    return existing


def _target_urls(progress: Progress):
    """Resolve the authoritative URL list: Mshop active pages, else GSC."""
    s = state()
    mshop_active = s.get("mshop_active_pages") or {}
    mshop_lookup = (mshop_active or {}).get("lookup") or {}

    # Validate cached list belongs to this shop; discard if not.
    if mshop_lookup:
        try:
            from utils.mshop_admin_api import validate_active_pages_match_site
            is_valid, _reason = validate_active_pages_match_site(mshop_active)
        except Exception:
            is_valid = True
        if not is_valid:
            s.pop("mshop_active_pages", None)
            mshop_active, mshop_lookup = {}, {}

    # Auto-sync when empty/invalid.
    if not mshop_lookup:
        try:
            from utils.mshop_admin_api import fetch_active_pages_all
            progress.step("Syncing Mshop active-pages list…")
            mshop_active = fetch_active_pages_all()
            if mshop_active.get("status") in ("success", "partial"):
                s["mshop_active_pages"] = mshop_active
                try:
                    save_key("mshop_active_pages")
                except Exception:
                    pass
                mshop_lookup = mshop_active.get("lookup") or {}
        except Exception as e:
            print(f"[audit_runner] Mshop sync failed: {e}")

    if mshop_lookup:
        seen, urls = set(), []
        for meta in mshop_lookup.values():
            u = meta.get("url", "")
            if u and u not in seen:
                seen.add(u)
                urls.append(u)
        counts = mshop_active.get("counts", {}) or {}
        label = (f"Mshop Admin API ({len(urls)} pages: "
                 f"{counts.get('category', 0)} cat + {counts.get('cms', 0)} CMS + "
                 f"{counts.get('filterpage', 0)} filter)")
        return urls, label

    # GSC fallback
    gsc = s.get("gsc_data")
    if gsc is None or not hasattr(gsc, "page"):
        raise ValueError(
            "No URL source available. Sync the Mshop Admin API (Setup) or "
            "connect GSC — bulk audit needs one of these to know which pages to scrape."
        )
    urls = list(gsc["page"].unique())
    return urls, f"GSC pages (fallback, {len(urls)} URLs)"


def run_bulk_audit(progress: Progress = NULL) -> dict:
    """Scrape every new live page into audit_results. Returns a summary dict.

    Idempotent + resumable: pages already in audit_results are skipped, and
    results are flushed to disk every CHECKPOINT_INTERVAL pages so an
    interrupted run resumes without re-scraping.
    """
    from utils.page_scraper import scrape_page
    from utils.category_analyzer import classify_page_type, deep_scrape_category
    from utils.ui_helpers import normalize_url as norm

    s = state()
    audit_path = _file_path("audit_results", "json") if _volume_available() else ""

    # ── existing results (disk is source of truth) ───────────────
    existing = []
    if audit_path and os.path.exists(audit_path):
        try:
            with open(audit_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = s.get("audit_results", []) or []
    else:
        existing = s.get("audit_results", []) or []
    existing = _canonicalize_existing(existing, audit_path, norm, classify_page_type)
    if existing:
        s["audit_results"] = existing

    # ── URL set ──────────────────────────────────────────────────
    target_urls, source_label = _target_urls(progress)
    existing_urls = set(norm(r.get("url", "")) for r in existing)
    to_scrape = [p for p in target_urls if norm(p) not in existing_urls]

    if not to_scrape:
        return {"scraped": 0, "ok": 0, "failed": 0, "total": 0,
                "already": len(existing_urls), "source": source_label,
                "message": "Nothing new to scrape — every page from this source "
                           "is already audited."}

    # ── scrape loop with disk checkpoints ────────────────────────
    n_total = len(to_scrape)
    n_ok = n_fail = 0
    pending = []

    def _flush(batch):
        if not batch or not audit_path:
            return
        try:
            on_disk = []
            if os.path.exists(audit_path):
                with open(audit_path, "r", encoding="utf-8") as f:
                    on_disk = json.load(f)
            fresh = set(norm(r.get("url", "")) for r in batch)
            kept = [r for r in on_disk if norm(r.get("url", "")) not in fresh]
            with open(audit_path, "w", encoding="utf-8") as f:
                json.dump(kept + batch, f, ensure_ascii=False, indent=1, default=str)
        except Exception as e:
            print(f"[audit_runner] checkpoint failed: {e}")

    for i, url in enumerate(to_scrape):
        progress.step(f"Scraping {i + 1}/{n_total} — {url[:70]}",
                      pct=(i + 1) / n_total)
        try:
            classified = classify_page_type(url).get("page_type", "unknown")
            if classified == "category":
                page_data = deep_scrape_category(url, timeout=30)
            else:
                page_data = scrape_page(url, timeout=30)
            page_data["url"] = norm(url)
            page_data["page_type"] = classified
            pending.append(page_data)
            n_ok += 1
        except Exception as e:
            pending.append({"url": norm(url), "success": False,
                            "error": str(e), "page_type": "unknown"})
            n_fail += 1
        if (i + 1) % CHECKPOINT_INTERVAL == 0:
            _flush(pending)
            pending = []   # free memory between checkpoints

    if pending:
        _flush(pending)

    # Rehydrate from disk (source of truth after checkpointed writes).
    if audit_path and os.path.exists(audit_path):
        try:
            with open(audit_path, "r", encoding="utf-8") as f:
                s["audit_results"] = json.load(f)
        except Exception as e:
            print(f"[audit_runner] final rehydrate failed: {e}")
    else:
        # No volume (local/dev): keep results in memory at least.
        merged = {norm(r.get("url", "")): r for r in existing}
        merged.update({norm(r.get("url", "")): r for r in pending})
        s["audit_results"] = list(merged.values())

    progress.done(f"Audited {n_ok} ok, {n_fail} failed of {n_total}")
    return {"scraped": n_total, "ok": n_ok, "failed": n_fail, "total": n_total,
            "already": len(existing_urls), "source": source_label}
