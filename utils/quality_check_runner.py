"""
Single source of truth for the AI Content Quality check.

Both views/page_auditor.py (interactive button) and views/run_pipeline.py
(Step 7 in the orchestrator) import from this module. Do NOT re-implement
the batching, hashing, eligibility, or saving anywhere else — extend this
module instead.
"""

import hashlib
import streamlit as st

from utils.ui_helpers import stable_hash


QUALITY_KEY_PREFIX = "_quality_"
# Category only: the AI prompt is built around editorial copy
# (intro_text + bottom_text). Product / blog / faq pages don't have that
# editorial structure — running the same prompt on them produces false
# negatives. Blogs and FAQs need their own evaluators with content-specific
# criteria. Discussed and confirmed with Henrik 2026-05-09.
ELIGIBLE_PAGE_TYPES = ("category",)
MIN_WORD_COUNT = 50
BATCH_SIZE = 5
MAX_PAGES_PER_CALL = 50  # how many pages one run_quality_batches() call processes


def quality_input_hash(audit_row: dict) -> str:
    """Hash of the inputs the AI sees. If unchanged, the cached verdict is still valid."""
    text = (
        (audit_row.get("body_text") or "")[:3000]
        + (audit_row.get("intro_text") or "")
        + (audit_row.get("bottom_text") or "")
        + (audit_row.get("page_type") or "")
    )
    return hashlib.md5(text.encode()).hexdigest()[:12]


def quality_key(url: str) -> str:
    """Session-state / cache-file key for a URL's verdict."""
    return f"{QUALITY_KEY_PREFIX}{stable_hash(url)}"


def quality_key_from_hash(url_hash: str) -> str:
    """Same key but when the caller already has the hash precomputed."""
    return f"{QUALITY_KEY_PREFIX}{url_hash}"


def eligible_pages(audit_results: list) -> list:
    """Pages that qualify for the quality check.

    Skips:
      - pages whose page_type isn't in ELIGIBLE_PAGE_TYPES
      - pages with word_count <= MIN_WORD_COUNT
      - pages in the user's _fix_skip_list (also used by Fix ALL).
        Single source of truth: a URL in that list is "do not touch
        with AI" — neither assess nor rewrite. This matches the
        intuition that if you don't want AI to rewrite a page, you
        probably don't want to pay for assessing it either.
    """
    skip_set = set(st.session_state.get("_fix_skip_list") or [])
    return [
        r for r in (audit_results or [])
        if r.get("page_type") in ELIGIBLE_PAGE_TYPES
        and (r.get("word_count") or 0) > MIN_WORD_COUNT
        and r.get("url", "") not in skip_set
    ]


def pages_needing_check(eligible: list) -> list:
    """Eligible pages that have no verdict OR a stale verdict (input hash mismatch)."""
    pending = []
    for r in eligible:
        existing = st.session_state.get(quality_key(r.get("url", "")))
        if existing is None:
            pending.append(r)
        elif isinstance(existing, dict) and existing.get("_input_hash") != quality_input_hash(r):
            pending.append(r)
    return pending


def already_checked_count(eligible: list) -> int:
    """How many eligible pages have an up-to-date verdict."""
    n = 0
    for r in eligible:
        existing = st.session_state.get(quality_key(r.get("url", "")))
        if isinstance(existing, dict) and existing.get("_input_hash") == quality_input_hash(r):
            n += 1
    return n


# ── Empty / thin categories: GENERATE text, don't ASSESS it ──────────
# A category with <=MIN_WORD_COUNT words has no editorial copy to judge —
# the AI assessment prompt would just say "REWRITE" trivially. These are
# the pages that need text written FROM SCRATCH. We give them a
# deterministic REWRITE verdict (no paid AI call) so they flow straight
# into the Fix ALL generate+push pipeline. Scope lets the operator run
# real categories and Mshop filterpages in separate rounds.
EMPTY_VERDICT_MARKER = "_synthetic_empty"


def _is_filterpage(url: str) -> bool:
    """True if the Mshop active-pages cache records this URL as a filterpage
    (filtered product view), as opposed to a real category. The audit
    page_type collapses both to 'category', so we consult the cache."""
    try:
        from utils.mshop_admin_api import lookup_url
        active = st.session_state.get("mshop_active_pages") or {}
        info = lookup_url(active, url) if active else None
        return bool(info) and (info.get("type") or "").lower() == "filterpage"
    except Exception:
        return False


def empty_category_pages(audit_results: list, scope: str = "all") -> list:
    """Category pages too thin to assess (<=MIN_WORD_COUNT words) — they
    need text generated.

    scope:
      - "categories"  → real categories only (exclude Mshop filterpages)
      - "filterpages" → Mshop filterpages only
      - "all"         → both
    Honours the AI skip-list, same as eligible_pages().
    """
    skip_set = set(st.session_state.get("_fix_skip_list") or [])
    out = []
    for r in (audit_results or []):
        if r.get("page_type") not in ELIGIBLE_PAGE_TYPES:
            continue
        if (r.get("word_count") or 0) > MIN_WORD_COUNT:
            continue  # has text → assessed by the AI path, not here
        url = r.get("url", "")
        if not url or url in skip_set:
            continue
        if scope in ("categories", "filterpages"):
            is_fp = _is_filterpage(url)
            if scope == "categories" and is_fp:
                continue
            if scope == "filterpages" and not is_fp:
                continue
        out.append(r)
    return out


def flag_empty_categories(audit_results: list, scope: str = "all") -> int:
    """Write a deterministic REWRITE verdict (NO AI call) for every empty
    category in scope, so it appears in the quality results and flows into
    Fix ALL's generate+push batch. Returns the number flagged."""
    from utils.persistence import save_ai_cache

    pages = empty_category_pages(audit_results, scope)
    n = 0
    for r in pages:
        url = r.get("url", "")
        st.session_state[quality_key(url)] = {
            "verdict": "REWRITE",
            "score": 0,
            "summary": (
                "Empty/thin category — no editorial text on the page. "
                "Needs intro + bottom text generated from scratch."
            ),
            "main_issues": ["No editorial copy on the page"],
            "specific_fixes": ["Generate a full intro + bottom text for this category"],
            "_input_hash": quality_input_hash(r),
            EMPTY_VERDICT_MARKER: True,
        }
        n += 1
    if n:
        try:
            save_ai_cache()
        except Exception:
            pass
    return n


def flagged_empty_pages(audit_results: list) -> list:
    """Category rows that currently carry a synthetic-empty verdict — used
    to fold them into the quality-results display + Fix ALL list, which
    otherwise only consider eligible_pages() (>MIN_WORD_COUNT)."""
    out = []
    for r in (audit_results or []):
        if r.get("page_type") not in ELIGIBLE_PAGE_TYPES:
            continue
        v = st.session_state.get(quality_key(r.get("url", "")))
        if isinstance(v, dict) and v.get(EMPTY_VERDICT_MARKER):
            out.append(r)
    return out


def run_quality_batches(
    pages_to_check: list,
    *,
    on_batch_start=None,
    on_progress=None,
    cap: int = MAX_PAGES_PER_CALL,
) -> list:
    """Run the AI quality check for the given pages, in batches of BATCH_SIZE.

    - on_batch_start(batch_num, total_batches, batch) — optional UI callback
    - on_progress(fraction_0_to_1)                    — optional UI callback
    - cap                                             — max pages to process this call

    Returns a list of (batch_num, error_str) for any batch that failed.
    Verdicts are written into st.session_state and persisted via save_ai_cache()
    after each successful batch, so partial progress is never lost.
    """
    from config import get_anthropic_key, has_anthropic_key
    from utils.ai_generator import get_client, assess_content_quality_batch
    from utils.persistence import save_ai_cache

    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing — set ANTHROPIC_API_KEY in Setup.")

    pages = (pages_to_check or [])[:cap]
    if not pages:
        return []

    client = get_client(get_anthropic_key())
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")
    topic_clusters = st.session_state.get("topic_clusters")

    errors = []
    batches = [
        (bs // BATCH_SIZE + 1, pages[bs:bs + BATCH_SIZE])
        for bs in range(0, len(pages), BATCH_SIZE)
    ]
    total_batches = len(batches)

    import concurrent.futures as _cf

    def _assess(item):
        # PURE worker — runs in a thread, MUST NOT touch st.session_state.
        # assess_content_quality_batch is verified free of session_state.
        _bn, _batch = item
        try:
            return (_bn, _batch, assess_content_quality_batch(
                client, _batch, site_context, language, topic_clusters), None)
        except Exception as e:
            return (_bn, _batch, None, str(e))

    # Run the per-batch AI calls CONCURRENTLY (each is pure network I/O),
    # capped so we don't hammer the rate limit. Verdict writes + cache save
    # happen here on the MAIN thread as each batch completes.
    PARALLEL = 5
    completed = 0
    with _cf.ThreadPoolExecutor(max_workers=min(PARALLEL, total_batches)) as ex:
        _futures = [ex.submit(_assess, b) for b in batches]
        for _fut in _cf.as_completed(_futures):
            _bn, _batch, assessments, err = _fut.result()
            if err is not None:
                errors.append((_bn, err))
            else:
                for idx, assessment in enumerate(assessments or []):
                    if idx >= len(_batch):
                        break
                    r = _batch[idx]
                    if isinstance(assessment, dict):
                        assessment["_input_hash"] = quality_input_hash(r)
                    st.session_state[quality_key(r.get("url", ""))] = assessment
            completed += 1
            # Persist periodically so an interruption never loses much.
            if completed % 3 == 0:
                try:
                    save_ai_cache()
                except Exception:
                    pass
            if on_batch_start:
                try:
                    on_batch_start(completed, total_batches, _batch)
                except Exception:
                    pass
            if on_progress:
                try:
                    on_progress(min(1.0, completed / max(total_batches, 1)))
                except Exception:
                    pass

    try:
        save_ai_cache()
    except Exception:
        pass
    return errors


def eligibility_diagnosis(audit_results: list) -> str:
    """Human-readable explanation of WHY there are 0 eligible pages.

    Step 7 only runs on category pages with >MIN_WORD_COUNT words (see
    eligible_pages). When that set is empty the runner has nothing to do
    and would otherwise return silently — which looks to the operator
    like "the step started and stopped, nothing happened". This builds a
    concrete diagnostic pointing at the actual cause so the fix is
    obvious (almost always: re-run Step 6 with the correct Mshop
    active-pages cache for THIS shop).
    """
    from collections import Counter

    audit = audit_results or []
    if not audit:
        return (
            "Step 7 has nothing to assess: audit_results is empty. "
            "Run Step 6 (Bulk Audit Pages) first."
        )

    type_counts = Counter((r.get("page_type") or "missing") for r in audit)
    type_str = ", ".join(f"{t}: {n}" for t, n in type_counts.most_common())

    categories = [r for r in audit if r.get("page_type") in ELIGIBLE_PAGE_TYPES]
    skip_set = set(st.session_state.get("_fix_skip_list") or [])
    cats_over_words = [
        r for r in categories if (r.get("word_count") or 0) > MIN_WORD_COUNT
    ]
    cats_skipped = [r for r in cats_over_words if r.get("url", "") in skip_set]

    # Active-pages cache state — the gate that turns categories into
    # "product" during Step 6 when it's empty / for the wrong shop.
    active = st.session_state.get("mshop_active_pages") or {}
    lookup = active.get("lookup") or {} if isinstance(active, dict) else {}
    cache_cats = sum(
        1 for m in lookup.values()
        if isinstance(m, dict) and (m.get("type") or "").lower() in ("category", "filterpage")
    )

    lines = [
        f"Step 7 found 0 eligible pages (needs page_type in "
        f"{'/'.join(ELIGIBLE_PAGE_TYPES)} with >{MIN_WORD_COUNT} words).",
        f"Audit has {len(audit)} pages. Type breakdown: {type_str}.",
        f"Categories: {len(categories)} total, "
        f"{len(cats_over_words)} with >{MIN_WORD_COUNT} words, "
        f"{len(cats_skipped)} of those on the skip-list.",
        f"Mshop active-pages cache: {len(lookup)} URLs, {cache_cats} categories/filterpages.",
    ]

    # Targeted next-action
    if len(categories) == 0:
        if cache_cats == 0:
            lines.append(
                "→ ROOT CAUSE: no categories in the active-pages cache, so Step 6 "
                "classified every page as product/other. The cache is empty or was "
                "synced for the WRONG shop. Fix: in Setup (or Bulk Audit) click "
                "'Sync Mshop active pages now' for THIS shop, then RE-RUN Step 6, "
                "then Step 7."
            )
        else:
            lines.append(
                "→ The cache HAS categories but the audit produced none — Step 6 ran "
                "against a stale/empty cache. Fix: RE-RUN Step 6 (Bulk Audit) now that "
                "the cache is correct, then Step 7."
            )
    elif len(cats_over_words) == 0:
        lines.append(
            f"→ All categories have <={MIN_WORD_COUNT} words — likely thin pages or a "
            "parser issue. Check Step 6 word_count extraction."
        )
    elif len(cats_skipped) == len(cats_over_words):
        lines.append(
            "→ Every eligible category is on your skip-list. Remove URLs from the "
            "skip-list editor above to assess them."
        )
    return "\n".join(lines)


def run_until_done(
    audit_results: list,
    max_iterations: int = 100,
    on_progress=None,
    on_batch_start=None,
) -> None:
    """Loop run_quality_batches() until every eligible page has an up-to-date verdict.

    Raises on any underlying error or no-progress condition. Used by the
    pipeline orchestrator (Step 7), which displays the exception in the UI.

    Optional UI callbacks (so a 5-25 min run doesn't look frozen):
      - on_progress(checked_count, total) — called after every batch with
        GLOBAL counts across all eligible pages (not per-call fractions).
      - on_batch_start(batch_num, total_batches, batch) — forwarded to
        run_quality_batches for per-batch status text.
    """
    eligible = eligible_pages(audit_results)
    if not eligible:
        return
    total = len(eligible)
    if on_progress:
        on_progress(already_checked_count(eligible), total)

    for _ in range(max_iterations):
        pending = pages_needing_check(eligible)
        if not pending:
            if on_progress:
                on_progress(total, total)
            return

        before = already_checked_count(eligible)

        # Forward per-batch progress as GLOBAL counts so the bar advances
        # smoothly across the whole eligible set, not 0→1 per 50-page call.
        def _fwd_progress(frac, _before=before, _n=min(len(pending), MAX_PAGES_PER_CALL)):
            if on_progress:
                on_progress(min(_before + int(frac * _n), total), total)

        errors = run_quality_batches(
            pending, cap=MAX_PAGES_PER_CALL,
            on_progress=_fwd_progress, on_batch_start=on_batch_start,
        )
        after = already_checked_count(eligible)
        if on_progress:
            on_progress(after, total)

        if errors and after <= before:
            first_batch, first_err = errors[0]
            raise RuntimeError(
                f"Quality check failed: batch {first_batch} error: {first_err}"
                + (f" (and {len(errors) - 1} more batch error(s))" if len(errors) > 1 else "")
            )
        if after <= before:
            raise RuntimeError(
                f"Quality check made no progress on {len(pending)} pending pages — "
                "AI returned no parseable assessments."
            )

    raise RuntimeError(
        f"Quality check did not complete within {max_iterations} iterations — "
        f"{len(pages_needing_check(eligible))} pages still pending."
    )
