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
ELIGIBLE_PAGE_TYPES = ("category", "blog", "faq")
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
    """Pages that qualify for the quality check."""
    return [
        r for r in (audit_results or [])
        if r.get("page_type") in ELIGIBLE_PAGE_TYPES
        and (r.get("word_count") or 0) > MIN_WORD_COUNT
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
    total_batches = (len(pages) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_start in range(0, len(pages), BATCH_SIZE):
        batch = pages[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1

        if on_batch_start:
            try:
                on_batch_start(batch_num, total_batches, batch)
            except Exception:
                pass

        try:
            assessments = assess_content_quality_batch(
                client, batch, site_context, language, topic_clusters,
            )
            for idx, assessment in enumerate(assessments):
                if idx >= len(batch):
                    break
                r = batch[idx]
                if isinstance(assessment, dict):
                    assessment["_input_hash"] = quality_input_hash(r)
                st.session_state[quality_key(r.get("url", ""))] = assessment
            save_ai_cache()
        except Exception as e:
            errors.append((batch_num, str(e)))

        if on_progress:
            try:
                on_progress(min(1.0, (batch_start + BATCH_SIZE) / len(pages)))
            except Exception:
                pass

    return errors


def run_until_done(audit_results: list, max_iterations: int = 100) -> None:
    """Loop run_quality_batches() until every eligible page has an up-to-date verdict.

    Raises on any underlying error or no-progress condition. Used by the
    pipeline orchestrator (Step 7), which displays the exception in the UI.
    """
    eligible = eligible_pages(audit_results)
    if not eligible:
        return

    for _ in range(max_iterations):
        pending = pages_needing_check(eligible)
        if not pending:
            return

        before = already_checked_count(eligible)
        errors = run_quality_batches(pending, cap=MAX_PAGES_PER_CALL)
        after = already_checked_count(eligible)

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
