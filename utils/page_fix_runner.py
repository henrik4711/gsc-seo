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


def generate_all_fixes_for_page(page: dict, force: bool = False, batch_mode: bool = False) -> dict:
    """Run the FULL AI-fix sequence for one page in one shot:
      1. Implementation plan (meta suggestions, action steps, links)
      2. Bottom text (FAQ + E-E-A-T body) — category pages only
      3. Intro rewrite — category pages only, only if intro is thin

    Each step is skipped when already cached (and `force` is False), so
    re-clicking the button is safe and cheap. Errors in one step don't
    block subsequent steps.

    `batch_mode=True` reduces retries for speed/reliability during Fix
    ALL: bottom text gets 1 attempt instead of 3 (worst-case time per
    page drops from ~5 min to ~90s — fits within Streamlit's WebSocket
    timeout window).

    Returns a status dict {plan, bottom_text, intro} with values:
      "generated" | "cached" | "skipped" | "error: <message>"
    """
    import streamlit as _st
    from utils.ui_helpers import stable_hash, show_ai_error
    from utils.persistence import save_ai_cache
    # Disk log mirroring Fix ALL's outer log so we can see WHICH step
    # inside this function actually hangs (was previously a black box).
    def _gflog(msg: str) -> None:
        try:
            from datetime import datetime as _dt
            with open("/data/fix_all_log.txt", "a", encoding="utf-8") as f:
                f.write(f"[{_dt.utcnow().isoformat()}Z]     {msg}\n")
        except Exception:
            pass

    url = page.get("url", "")
    if not url:
        return {"plan": "skipped", "bottom_text": "skipped", "intro": "skipped"}
    url_hash = stable_hash(url)
    page_type = page.get("page_type", "unknown")
    audit = page.get("audit") or {}
    status = {}
    _gflog(f"runner.start url={url} page_type={page_type} batch={batch_mode}")

    # ── Step 1: Plan ────────────────────────────────────────────
    plan_key = f"_ai_plan_{url_hash}"
    plan_existing = _st.session_state.get(plan_key)
    plan_errored = isinstance(plan_existing, dict) and bool(plan_existing.get("error"))
    if force or plan_existing is None or plan_errored:
        _gflog(f"runner.plan_start url={url}")
        result = generate_ai_fixes_for_page(page)
        if result is None:
            status["plan"] = "error"
            _gflog(f"runner.plan_err url={url}")
        else:
            status["plan"] = "generated"
            _gflog(f"runner.plan_done url={url}")
    else:
        status["plan"] = "cached"
        _gflog(f"runner.plan_cached url={url}")

    # ── Step 2: Bottom text (category only) ─────────────────────
    text_key = f"_bottom_text_{url_hash}"
    text_existing = _st.session_state.get(text_key)
    text_errored = isinstance(text_existing, dict) and bool(text_existing.get("error"))
    if page_type != "category":
        status["bottom_text"] = "skipped"
        _gflog(f"runner.bottom_skip url={url} (not category, type={page_type})")
    elif force or text_existing is None or text_errored:
        try:
            from utils.ai_generator import generate_page_content
            _bottom_max = 1 if batch_mode else 3
            _gflog(f"runner.bottom_start url={url} max_attempts={_bottom_max}")
            result = generate_page_content(url, _max_attempts=_bottom_max)
            _st.session_state[text_key] = result
            save_ai_cache()
            status["bottom_text"] = "generated"
            _gflog(f"runner.bottom_done url={url} chars={len((result or {}).get('bottom_html','') or '')}")
        except Exception as e:
            import traceback as _tb
            _gflog(f"runner.bottom_err url={url} {type(e).__name__}: {e}")
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
        _gflog(f"runner.bottom_cached url={url}")

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
            _gflog(f"runner.intro_start url={url}")
            from config import get_anthropic_key
            from utils.ai_generator import get_client, generate_intro_rewrite
            client = get_client(get_anthropic_key())
            content_audit = audit.get("content_audit") or {}
            kw_coverage = content_audit.get("keyword_coverage") or {}
            missing_kws = (kw_coverage.get("missing", []) or [])[:8]
            if not missing_kws:
                missing_kws = audit.get("target_keywords", [])[:8]
            _intro_max = 1 if batch_mode else 2
            result = generate_intro_rewrite(
                client,
                missing_keywords=missing_kws,
                existing_intro=audit.get("intro_text", "") or "",
                page_type=page_type,
                url=url,
                site_context=_st.session_state.get("site_context", ""),
                language=_st.session_state.get("content_language", "Swedish"),
                _max_attempts=_intro_max,
            )
            _st.session_state[intro_key] = result
            save_ai_cache()
            status["intro"] = "generated"
            _gflog(f"runner.intro_done url={url}")
        except Exception as e:
            import traceback as _tb
            _gflog(f"runner.intro_err url={url} {type(e).__name__}: {e}")
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

    _gflog(f"runner.end url={url} status={status}")
    return status
