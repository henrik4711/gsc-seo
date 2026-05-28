"""
Content Freshness view — surface pages whose impressions are decaying,
and let the user refresh them with AI in one click.

UI-only: all detection + persistence lives in utils/content_freshness.py.
Refresh action reuses the existing single-source-of-truth pipeline
(_invalidate_ai_plan_cache → generate_all_fixes_for_page(force=True))
so behavior matches the Cluster Health "regenerate flagged" button.

Why this view exists:
A page that ranked steady for months and is now bleeding impressions is
almost always cheaper to refresh than to rebuild. The 2-window GSC
comparison (last 30 days vs. prior 30 days) flags exactly those pages,
and the AI regen prompt picks up a freshness signal so the rewrite
actually targets the decay angle rather than producing generic prose.
"""

import streamlit as st

from utils.content_freshness import (
    DEFAULT_MIN_PRIOR_IMPRESSIONS,
    DEFAULT_DROP_PCT_THRESHOLD,
    refresh_decaying_pages_data,
    get_decaying_pages,
)
from utils.ui_helpers import shorten_url, stable_hash


_SEVERITY_STYLE = {
    "critical": ("#ff5577", "CRITICAL"),
    "warn":     ("#ffaa44", "WARN"),
    "watch":    ("#c8b4ff", "WATCH"),
}


def _render_header():
    st.markdown("## Content Freshness")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1.5rem;'>"
        "Detect pages that are losing impressions month-over-month, then refresh them with AI. "
        "Refreshing a decaying page is almost always cheaper than ranking a new one — "
        "and the AI prompt automatically picks up the decay angle so the rewrite targets it."
        "</p>",
        unsafe_allow_html=True,
    )


def _render_setup_warning() -> bool:
    """Return True when GSC is not configured — caller should stop."""
    if not st.session_state.get("gsc_credentials"):
        st.warning("Connect Google Search Console first in **1. Setup & Connect**.")
        return True
    if not (st.session_state.get("gsc_site") or st.session_state.get("gsc_site_url")):
        st.warning("Select a GSC site in **1. Setup & Connect** first.")
        return True
    return False


def _render_detection_controls():
    """Top row: thresholds + Detect button. Returns True when user clicks it."""
    with st.expander("Detection settings", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        recent_days = c1.number_input(
            "Recent window (days)",
            min_value=7, max_value=90, value=30, step=1, key="cf_recent_days",
            help="Compared against the equally-sized prior window.",
        )
        prior_days = c2.number_input(
            "Prior window (days)",
            min_value=7, max_value=90, value=30, step=1, key="cf_prior_days",
            help="Days immediately before the recent window. Same length = clean apples-to-apples.",
        )
        min_prior = c3.number_input(
            "Min prior impressions",
            min_value=10, max_value=10000,
            value=DEFAULT_MIN_PRIOR_IMPRESSIONS, step=10, key="cf_min_prior",
            help="Ignore pages that didn't have meaningful traffic in the prior window — a drop from 5 → 2 isn't actionable.",
        )
        drop_pct = c4.number_input(
            "Drop % threshold",
            min_value=5.0, max_value=95.0,
            value=DEFAULT_DROP_PCT_THRESHOLD, step=5.0, key="cf_drop_pct",
            help="Flag pages whose impressions dropped at least this much.",
        )

    col_btn, col_info = st.columns([1, 3])
    detect = col_btn.button("🔄 Detect decaying pages", type="primary")
    col_info.markdown(
        "<span style='font-size:0.75rem; color:#6b6b8a;'>"
        "Makes 2 GSC API calls (one per window). No Claude calls here — cheap and fast.</span>",
        unsafe_allow_html=True,
    )

    if detect:
        with st.spinner("Fetching GSC windows + computing decay…"):
            try:
                refresh_decaying_pages_data(
                    recent_days=int(recent_days),
                    prior_days=int(prior_days),
                    min_prior_impressions=int(min_prior),
                    drop_pct_threshold=float(drop_pct),
                )
                st.rerun()
            except Exception as e:
                st.error(f"Detection failed: {type(e).__name__}: {e}")


def _render_summary(payload: dict):
    """Stats grid + window dates."""
    decaying = payload.get("decaying", [])
    severity_counts = {"critical": 0, "warn": 0, "watch": 0}
    for d in decaying:
        sev = d.get("severity", "watch")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Decaying pages", payload.get("decaying_count", 0))
    c2.metric("Critical", severity_counts["critical"])
    c3.metric("Warn", severity_counts["warn"])
    c4.metric("Watch", severity_counts["watch"])

    recent = payload.get("recent_window") or ("?", "?")
    prior = payload.get("prior_window") or ("?", "?")
    st.markdown(
        f"<p style='font-size:0.78rem; color:#6b6b8a; margin-top:0.5rem;'>"
        f"Recent: <strong>{recent[0]} → {recent[1]}</strong> · "
        f"Prior: <strong>{prior[0]} → {prior[1]}</strong> · "
        f"Pages with traffic in prior window: {payload.get('total_pages_with_traffic', 0):,}"
        f"</p>",
        unsafe_allow_html=True,
    )


def _refresh_page_via_ai(url: str) -> dict:
    """Run the AI fix pipeline for ONE decaying URL. Mirrors the
    Cluster Health 'regenerate flagged' logic so behavior is identical:
    drop cache → generate all fixes with force=True. The freshness
    signal is picked up inside the AI prompts via
    utils.content_freshness.format_freshness_signal_for_prompt (wired
    into ai_generator).
    """
    from utils.audit_refresh import _invalidate_ai_plan_cache
    from utils.page_fix_runner import (
        generate_all_fixes_for_page,
        page_audit_to_page_dict,
    )
    from utils.ui_helpers import normalize_url

    audit_results = st.session_state.get("audit_results", []) or []
    audit_by_url = {normalize_url(r.get("url", "")): r for r in audit_results if isinstance(r, dict)}
    row = audit_by_url.get(normalize_url(url))
    if not row:
        return {"error": "no audit row — run Step 6 (Bulk Audit) first so the page has profile data"}

    _invalidate_ai_plan_cache(url)
    page = page_audit_to_page_dict(row)
    try:
        return generate_all_fixes_for_page(page, force=True, batch_mode=False)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _render_decay_table(payload: dict):
    decaying = payload.get("decaying", [])
    if not decaying:
        st.success("No decaying pages above thresholds — content stability looks healthy.")
        return

    st.markdown("### Decaying pages")
    st.markdown(
        "<p style='font-size:0.78rem; color:#6b6b8a;'>"
        "Sorted by lost clicks. Click <strong>Refresh with AI</strong> to regenerate the page's "
        "implementation plan + bottom text + intro with the decay angle baked into the prompt."
        "</p>",
        unsafe_allow_html=True,
    )

    for entry in decaying[:50]:  # cap rendering — anything past 50 is unlikely to be acted on in one session
        url = entry["url"]
        sev_color, sev_label = _SEVERITY_STYLE.get(entry.get("severity", "watch"), _SEVERITY_STYLE["watch"])
        row_key = stable_hash(url)

        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([0.5, 4, 1, 1.2, 1.5])
            c1.markdown(
                f"<div style='color:{sev_color}; font-family:\"IBM Plex Mono\",monospace; "
                f"font-size:0.7rem; padding-top:0.4rem;'>{sev_label}</div>",
                unsafe_allow_html=True,
            )
            c2.markdown(
                f"<div style='padding-top:0.3rem;'>"
                f"<a href='{url}' target='_blank' style='color:#c8b4ff; text-decoration:none;'>"
                f"{shorten_url(url)}</a></div>",
                unsafe_allow_html=True,
            )
            c3.markdown(
                f"<div style='text-align:right; padding-top:0.3rem;'>"
                f"<div style='font-size:1rem; color:#ff5577;'>↓ {entry['impression_drop_pct']}%</div>"
                f"<div style='font-size:0.65rem; color:#6b6b8a;'>impressions</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            c4.markdown(
                f"<div style='text-align:right; padding-top:0.3rem;'>"
                f"<div style='font-size:0.85rem; color:#e8e8f0;'>"
                f"{entry['prior_impressions']:,} → {entry['recent_impressions']:,}</div>"
                f"<div style='font-size:0.65rem; color:#6b6b8a;'>"
                f"−{entry['lost_clicks']} clicks</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            with c5:
                if st.button("🔄 Refresh with AI", key=f"cf_refresh_{row_key}"):
                    with st.spinner(f"AI regenerating {shorten_url(url)}…"):
                        status = _refresh_page_via_ai(url)
                    if "error" in status:
                        st.error(status["error"])
                    else:
                        st.success(f"Done — plan: {status.get('plan', '?')}, bottom: {status.get('bottom_text', '?')}, intro: {status.get('intro', '?')}")
                        st.markdown(
                            "<span style='font-size:0.7rem; color:#6b6b8a;'>"
                            "Review + push the result from <strong>Action Plan</strong> or <strong>Quick Wins</strong>."
                            "</span>",
                            unsafe_allow_html=True,
                        )


def render():
    _render_header()
    if _render_setup_warning():
        return
    _render_detection_controls()

    payload = get_decaying_pages()
    if not payload:
        st.info(
            "No detection has been run yet. Click **Detect decaying pages** above to fetch "
            "the two GSC windows and identify pages losing impressions."
        )
        return

    st.markdown("---")
    _render_summary(payload)
    st.markdown("---")
    _render_decay_table(payload)
