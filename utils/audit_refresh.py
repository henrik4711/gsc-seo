"""
Audit row refresh after a successful push to mshop.

PROBLEM
We have a long-standing bug where AI bulk re-runs (Action Plan, Quick Wins
batch fixes) keep flagging the SAME content gaps for pages whose intro /
bottom / meta we just pushed minutes ago. Cause: audit_results is the
single source of truth for "what's on this page", and it's only refreshed
by a live re-scrape. The push flow never touched it, so audit was always
stale until the next bulk re-scrape.

WHY NOT JUST RE-SCRAPE
Magento full-page cache typically holds 1-15 min after a push, so an
immediate re-scrape often captures the OLD HTML again. We'd burn AI
tokens recomputing on stale data twice — once before push, once after.

WHAT THIS DOES
We already have the pushed content in hand. Write it straight into
audit_results[url], recompute the derived fields (meta_score,
content_score, keyword_coverage, missing_keywords, total_editorial_words),
persist to disk, then drop the cached AI implementation plan so the next
run uses fresh state. Zero network calls, zero AI tokens, zero
Magento-cache delay.

CALLERS
- utils/mshop_admin_push_ui.py — after update_for_page() returns success
- utils/footer_push_ui.py — after push_footer_text() returns success
"""

import os
from datetime import datetime
from typing import Optional

import streamlit as st

from utils.ui_helpers import normalize_url, stable_hash


def _strip_html(html: str) -> str:
    """Cheap HTML→text for word counting. Avoids importing BeautifulSoup
    on every push — text from intro/bottom is short enough that a regex
    pass is fine for the word-count signal."""
    import re
    if not html:
        return ""
    # Drop script/style blocks first
    txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    # Replace tags with spaces so "<p>foo</p><p>bar</p>" becomes "foo bar"
    txt = re.sub(r"<[^>]+>", " ", txt)
    # Collapse whitespace
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _find_audit_row(url: str) -> Optional[dict]:
    """Find the audit_results entry for a URL, matched on the canonical
    normalised form. Returns the row dict (mutable — caller can update
    in place) or None if no audit exists for this URL yet."""
    target = normalize_url(url)
    rows = st.session_state.get("audit_results") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_url = row.get("url", "")
        if row_url and normalize_url(row_url) == target:
            return row
    return None


def _target_keywords_for(url: str, limit: int = 20) -> list:
    """Re-derive the per-page target_keywords list the same way
    page_auditor.py does, so the recomputed scores match what a fresh
    audit would produce. Falls back to whatever the audit row already
    has if GSC data is unavailable in this session."""
    gsc = st.session_state.get("gsc_data")
    if gsc is None or not hasattr(gsc, "loc"):
        row = _find_audit_row(url)
        if row:
            return list(row.get("target_keywords") or [])[:limit]
        return []
    norm = normalize_url(url)
    try:
        page_rows = gsc[gsc["page"].apply(normalize_url) == norm]
    except Exception:
        return []
    if page_rows.empty:
        return []
    sorted_rows = page_rows.sort_values("impressions", ascending=False)
    return sorted_rows["query"].head(limit).tolist()


def _cluster_keywords_for(url: str) -> list:
    """Same shape as views.page_auditor._get_cluster_keywords — needed so
    audit_category_content sees the full keyword universe for the page."""
    tc = st.session_state.get("topic_clusters") or {}
    if not isinstance(tc, dict):
        return []
    norm = normalize_url(url)
    out = []
    for cluster in tc.get("clusters", []):
        pages = cluster.get("pages", []) or []
        belongs = any(
            normalize_url(p.get("page", "")) == norm for p in pages if isinstance(p, dict)
        )
        if belongs:
            out.extend(cluster.get("queries", []) or [])
    # Dedupe while keeping order
    seen = set()
    uniq = []
    for kw in out:
        if kw not in seen:
            seen.add(kw)
            uniq.append(kw)
    return uniq[:50]


def _invalidate_ai_plan_cache(url: str) -> None:
    """Drop the cached AI implementation plan for this URL — both from
    session_state and from /data/ai_cache/ on disk — so the next AI run
    starts fresh against the updated audit row.

    Also drops the cached quality verdict (_quality_<hash>) so a page
    that was previously marked REWRITE doesn't keep that verdict in the
    Dashboard's "Top pages by impact" list after the user has actually
    fixed it.
    """
    url_hash = stable_hash(url)
    keys_to_drop = [
        f"_ai_plan_{url_hash}",
        f"_quality_{url_hash}",
        f"_bottom_text_{url_hash}",
        f"_intro_text_{url_hash}",
    ]

    # Session state
    for k in keys_to_drop:
        st.session_state.pop(k, None)

    # Disk — only if /data exists (Railway). Best-effort: missing files
    # are not an error.
    cache_dir = "/data/ai_cache"
    if not os.path.isdir(cache_dir):
        return
    for k in keys_to_drop:
        path = os.path.join(cache_dir, f"{k}.json")
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def _recompute_meta_score(row: dict) -> None:
    """Re-run evaluate_meta with the updated title/meta_description and
    write the new score + issues into the row. Safe if the page has no
    GSC data — evaluate_meta accepts an empty target_keywords list."""
    try:
        from utils.page_scraper import evaluate_meta
    except Exception:
        return
    target_kws = _target_keywords_for(row.get("url", ""))
    try:
        meta_eval = evaluate_meta(row, target_kws)
    except Exception:
        return
    row["meta_score"] = meta_eval.get("score")
    row["meta_eval"] = meta_eval
    # Replace the META-related issues only; preserve content/structure
    # issues that aren't affected by a title/desc change. Issues from
    # evaluate_meta come from the "issues" key of its return dict.
    new_meta_issues = meta_eval.get("issues", []) or []
    existing = row.get("issues", []) or []
    # Filter out old meta issues (field "title" or "meta_description")
    META_FIELDS = {"title", "meta_description"}
    non_meta = [
        i for i in existing
        if not (isinstance(i, dict) and i.get("field") in META_FIELDS)
    ]
    row["issues"] = non_meta + new_meta_issues


def _recompute_content_score(row: dict) -> None:
    """Re-run audit_category_content with the updated intro/bottom text.
    Only applies to pages where category content audit makes sense
    (category / blog / faq). For other types we just refresh word counts."""
    page_type = row.get("page_type") or ""
    if page_type not in ("category", "blog", "faq", "filterpage", "pillar"):
        # Still update word_count + total_editorial_words below; nothing
        # else to recompute for product/info/unknown pages.
        return
    try:
        from utils.category_analyzer import audit_category_content
    except Exception:
        return
    url = row.get("url", "")
    target_kws = _target_keywords_for(url)
    cluster_kws = _cluster_keywords_for(url)
    try:
        cat_audit = audit_category_content(
            row,
            cluster_kws,
            target_kws,
            topic_clusters=st.session_state.get("topic_clusters"),
            page_authority=st.session_state.get("page_authority"),
        )
    except Exception:
        return
    row["content_score"] = cat_audit.get("score")
    row["content_audit"] = cat_audit
    # Replace content-area issues; keep meta/structure issues.
    CONTENT_AREAS = {
        "content_volume", "intro", "bottom", "keyword_coverage",
        "topic_coverage", "subtopics", "linking", "trust", "structure",
    }
    existing = row.get("issues", []) or []
    non_content = [
        i for i in existing
        if not (isinstance(i, dict) and i.get("area") in CONTENT_AREAS)
    ]
    new_content_issues = [
        {"type": i.get("severity"), "field": i.get("area"), "msg": i.get("msg")}
        for i in (cat_audit.get("issues") or [])
        if isinstance(i, dict)
    ]
    row["issues"] = non_content + new_content_issues


def update_audit_after_push(
    url: str,
    *,
    intro_text: Optional[str] = None,
    bottom_text: Optional[str] = None,
    meta_title: Optional[str] = None,
    meta_description: Optional[str] = None,
) -> bool:
    """Apply pushed content to the local audit row so the next AI run
    sees fresh state.

    Pass only the fields that were actually pushed — anything left as
    None is preserved as-is on the audit row.

    Returns True if the row was found and updated, False otherwise. A
    False return is not an error: it just means we never had an audit
    for this URL, so there's nothing local to keep in sync.
    """
    row = _find_audit_row(url)
    if row is None:
        return False

    changed_meta = False
    changed_content = False

    # ── Meta title ──────────────────────────────────────────────
    if meta_title is not None:
        clean_title = str(meta_title).strip()
        row["title"] = clean_title
        row["title_length"] = len(clean_title)
        changed_meta = True

    # ── Meta description ───────────────────────────────────────
    if meta_description is not None:
        clean_desc = str(meta_description).strip()
        row["meta_description"] = clean_desc
        row["description_length"] = len(clean_desc)
        changed_meta = True

    # ── Intro (description field on category/filterpage) ───────
    if intro_text is not None:
        row["intro_text"] = intro_text
        intro_words = len(_strip_html(intro_text).split())
        row["intro_word_count"] = intro_words
        changed_content = True

    # ── Bottom text ─────────────────────────────────────────────
    if bottom_text is not None:
        row["bottom_text"] = bottom_text
        bot_words = len(_strip_html(bottom_text).split())
        row["bottom_word_count"] = bot_words
        changed_content = True

    if not (changed_meta or changed_content):
        return False  # caller passed all-None — nothing to do

    # ── Derived fields ──────────────────────────────────────────
    if changed_content:
        intro_w = int(row.get("intro_word_count") or 0)
        bottom_w = int(row.get("bottom_word_count") or 0)
        row["total_editorial_words"] = intro_w + bottom_w
        # Refresh body_text as the concatenation of editorial sections so
        # downstream consumers that read body_text (AI plan prompts, etc.)
        # see the pushed content. If a middle/full text was scraped, we
        # can't reconstruct it perfectly — better to set body_text to the
        # editorial sum than to leave the stale full-page text in place.
        body = " ".join(
            _strip_html(row.get(k) or "")
            for k in ("intro_text", "bottom_text")
            if row.get(k)
        ).strip()
        if body:
            row["body_text"] = body
            row["word_count"] = len(body.split())

    if changed_meta:
        _recompute_meta_score(row)
    if changed_content:
        _recompute_content_score(row)

    # ── Stamp + persist ────────────────────────────────────────
    row["_last_push_at"] = datetime.utcnow().isoformat() + "Z"
    pushed_fields = []
    if intro_text is not None:
        pushed_fields.append("intro_text")
    if bottom_text is not None:
        pushed_fields.append("bottom_text")
    if meta_title is not None:
        pushed_fields.append("meta_title")
    if meta_description is not None:
        pushed_fields.append("meta_description")
    row["_last_push_fields"] = pushed_fields

    try:
        from utils.persistence import save
        save("audit_results")
    except Exception as e:
        # Persistence is best-effort here — the in-memory update is what
        # the current session needs. Show in the Streamlit log only.
        print(f"[audit_refresh] persist failed for {url}: {e}")

    _invalidate_ai_plan_cache(url)
    return True


def last_push_caption(url: str) -> str:
    """One-line UI caption showing 'audit refreshed locally after push at X'
    so the user can see the loop closed without going to the audit table."""
    row = _find_audit_row(url)
    if not row:
        return ""
    ts = row.get("_last_push_at") or ""
    fields = row.get("_last_push_fields") or []
    if not ts:
        return ""
    fields_str = ", ".join(fields) if fields else "fields"
    return f"Audit refreshed locally after push: {ts} · {fields_str}"
