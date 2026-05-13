"""
Single source of truth for "generate ALL AI fixes for a page".

Used by:
- views/quick_wins.py (the main per-page workflow)
- views/page_auditor.py (the per-row "🤖 Generate AI fixes" button on the
  audit overview, so users can act directly from the issue list)

Generates an implementation plan via Claude (which itself bundles meta
suggestions, internal-link recommendations, action steps, and supporting
article ideas). Bottom-text and intro rewrites are kicked off later, on
demand, by the per-section buttons in Quick Wins.
"""

import streamlit as st

from utils.ui_helpers import stable_hash, show_ai_error


def generate_ai_fixes_for_page(page: dict) -> dict | None:
    """Generate the AI implementation plan for one page.
    Returns the plan dict on success, None if the AI call errored (the
    error is shown via show_ai_error and the cache key is stamped with
    the error so the user sees it on next render of Quick Wins).

    `page` must have at least: 'url', 'audit', and 'page_type'. Use the
    same shape Quick Wins builds via _get_top_pages, OR call
    page_audit_to_page_dict() below to construct one from a raw audit
    row.
    """
    from config import get_anthropic_key, has_anthropic_key
    from utils.ai_generator import (
        get_client,
        generate_page_implementation_plan,
    )
    from utils.page_profile import build_page_profile
    from utils.persistence import save_ai_cache

    url = page["url"]
    url_hash = stable_hash(url)
    audit = page["audit"]

    if not has_anthropic_key():
        st.error("Anthropic API key missing — set ANTHROPIC_API_KEY in Setup.")
        return None

    client = get_client(get_anthropic_key())
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")
    topic_clusters = st.session_state.get("topic_clusters", {})

    # Build site URLs (used for internal-link recommendations)
    audit_results = st.session_state.get("audit_results", [])
    raw_urls = set(r["url"] for r in audit_results if r.get("url"))
    gsc = st.session_state.get("gsc_data")
    if gsc is not None and hasattr(gsc, "page"):
        raw_urls.update(gsc["page"].unique().tolist())
    all_site_urls = sorted(raw_urls)

    # Build the page profile once — single source for derived signals
    profile = build_page_profile(url)

    plan_key = f"_ai_plan_{url_hash}"
    existing_plan = st.session_state.get(plan_key)
    plan_is_errored = isinstance(existing_plan, dict) and bool(existing_plan.get("error"))
    if plan_key in st.session_state and not plan_is_errored:
        return existing_plan  # already generated; nothing to do

    with st.spinner(
        f"AI is reviewing this page (~30-60 sec): meta + intro + bottom + "
        f"link suggestions + action steps for {url[-40:]}…"
    ):
        try:
            result = generate_page_implementation_plan(
                client, audit, site_context, all_site_urls, language, topic_clusters,
                ctr_gaps_for_page=profile.get("ctr_gaps") or [],
                cannibal_link_targets=profile.get("cannibal_link_targets") or [],
                cluster_link_outgoing=profile.get("cluster_link_outgoing") or [],
                structural_signals=profile.get("structural_signals") or {},
                editorial_images=profile.get("editorial_images") or [],
            )
            st.session_state[plan_key] = result
            save_ai_cache()
            return result
        except Exception as e:
            import traceback as _tb
            show_ai_error(
                "Implementation plan generation",
                e,
                context={
                    "url": url,
                    "page_type": page.get("page_type"),
                    "site_urls_count": len(all_site_urls),
                    "language": language,
                },
            )
            st.session_state[plan_key] = {
                "error": str(e),
                "error_class": type(e).__name__,
                "error_status_code": getattr(e, "status_code", None),
                "error_request_id": getattr(e, "request_id", None),
                "error_traceback": _tb.format_exc()[-3000:],
                "steps": [],
            }
            save_ai_cache()
            return None


def page_audit_to_page_dict(audit_row: dict) -> dict:
    """Build the dict shape generate_ai_fixes_for_page() expects from a
    raw audit_results entry. Used when the caller is iterating
    audit_results directly (e.g. Page Auditor) rather than Quick Wins'
    pre-sorted page list."""
    return {
        "url": audit_row.get("url", ""),
        "page_type": audit_row.get("page_type", "unknown"),
        "audit": audit_row,
    }


def generate_all_fixes_for_page(page: dict, force: bool = False) -> dict:
    """Run the FULL AI-fix sequence for one page in one shot:
      1. Implementation plan (meta suggestions, action steps, links)
      2. Bottom text (FAQ + E-E-A-T body) — category pages only
      3. Intro rewrite — category pages only, only if intro is thin

    Each step is skipped when already cached (and `force` is False), so
    re-clicking the button is safe and cheap. Errors in one step don't
    block subsequent steps.

    Returns a status dict {plan, bottom_text, intro} with values:
      "generated" | "cached" | "skipped" | "error: <message>"
    Used by callers that want to show a per-step result summary.
    """
    import streamlit as _st
    from utils.ui_helpers import stable_hash, show_ai_error
    from utils.persistence import save_ai_cache

    url = page.get("url", "")
    if not url:
        return {"plan": "skipped", "bottom_text": "skipped", "intro": "skipped"}
    url_hash = stable_hash(url)
    page_type = page.get("page_type", "unknown")
    audit = page.get("audit") or {}
    status = {}

    # ── Step 1: Plan ────────────────────────────────────────────
    plan_key = f"_ai_plan_{url_hash}"
    plan_existing = _st.session_state.get(plan_key)
    plan_errored = isinstance(plan_existing, dict) and bool(plan_existing.get("error"))
    if force or plan_existing is None or plan_errored:
        result = generate_ai_fixes_for_page(page)
        if result is None:
            status["plan"] = "error"
        else:
            status["plan"] = "generated"
    else:
        status["plan"] = "cached"

    # ── Step 2: Bottom text (category only) ─────────────────────
    text_key = f"_bottom_text_{url_hash}"
    text_existing = _st.session_state.get(text_key)
    text_errored = isinstance(text_existing, dict) and bool(text_existing.get("error"))
    if page_type != "category":
        status["bottom_text"] = "skipped"
    elif force or text_existing is None or text_errored:
        try:
            from utils.ai_generator import generate_page_content
            result = generate_page_content(url)
            _st.session_state[text_key] = result
            save_ai_cache()
            status["bottom_text"] = "generated"
        except Exception as e:
            import traceback as _tb
            show_ai_error(
                "Bottom text generation",
                e,
                context={"url": url, "page_type": page_type, "step": "all_fixes"},
            )
            _st.session_state[text_key] = {
                "error": str(e),
                "error_class": type(e).__name__,
                "error_traceback": _tb.format_exc()[-3000:],
            }
            save_ai_cache()
            status["bottom_text"] = f"error: {type(e).__name__}"
    else:
        status["bottom_text"] = "cached"

    # ── Step 3: Intro rewrite (category, only if intro is thin) ─
    intro_key = f"_intro_text_{url_hash}"
    intro_existing = _st.session_state.get(intro_key)
    intro_errored = isinstance(intro_existing, dict) and bool(intro_existing.get("error"))
    intro_words = audit.get("intro_word_count", 0) or 0
    intro_too_thin = intro_words < 50
    if page_type != "category":
        status["intro"] = "skipped"
    elif not intro_too_thin and not force and intro_existing is None:
        # Existing intro is fine and user hasn't forced regen — skip.
        status["intro"] = "skipped (existing intro OK)"
    elif force or intro_existing is None or intro_errored:
        try:
            from config import get_anthropic_key
            from utils.ai_generator import get_client, generate_intro_rewrite
            client = get_client(get_anthropic_key())
            content_audit = audit.get("content_audit") or {}
            kw_coverage = content_audit.get("keyword_coverage") or {}
            missing_kws = (kw_coverage.get("missing", []) or [])[:8]
            if not missing_kws:
                missing_kws = audit.get("target_keywords", [])[:8]
            result = generate_intro_rewrite(
                client,
                missing_keywords=missing_kws,
                existing_intro=audit.get("intro_text", "") or "",
                page_type=page_type,
                url=url,
                site_context=_st.session_state.get("site_context", ""),
                language=_st.session_state.get("content_language", "Swedish"),
            )
            _st.session_state[intro_key] = result
            save_ai_cache()
            status["intro"] = "generated"
        except Exception as e:
            import traceback as _tb
            show_ai_error(
                "Intro text generation",
                e,
                context={"url": url, "page_type": page_type, "step": "all_fixes"},
            )
            _st.session_state[intro_key] = {
                "error": str(e),
                "error_class": type(e).__name__,
                "error_traceback": _tb.format_exc()[-3000:],
            }
            save_ai_cache()
            status["intro"] = f"error: {type(e).__name__}"
    else:
        status["intro"] = "cached"

    return status
