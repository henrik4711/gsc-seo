"""
Streamlit UI block for pushing intro text / meta title / meta description
to the Mshop admin API.

Companion to footer_push_ui.py — the bottom-text push has its own
multi-section endpoint; this one wraps the simpler single-field
endpoints (catalog/category/texts, cms/page/texts, catalog/filterpage/texts).

UX:
- @st.fragment scopes reruns to just this block — clicking one button
  doesn't redraw the whole per-page view.
- Each push button is independent (intro / meta title / meta description).
- After a successful push, the response body is shown so the user can
  verify the change actually landed.
- If the page URL is not in the synced active-pages list, the block
  shows a hint to sync first instead of silently rendering disabled
  buttons.
"""

import json
import streamlit as st

from utils.mshop_admin_api import (
    lookup_url,
    update_for_page,
    last_successful_admin_push,
)
from utils.audit_refresh import update_audit_after_push, last_push_caption


_ENDPOINT_BY_TYPE = {
    "category": "catalog/category/texts",
    "cms": "cms/page/texts",
    "filterpage": "catalog/filterpage/texts",
}


def _fmt_response(result: dict) -> str:
    body = result.get("response_body") or ""
    if not body:
        return "(empty response body)"
    try:
        parsed = json.loads(body)
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception:
        return body[:3000]


def _last_push_caption(page_info: dict) -> str:
    """Compact one-liner showing 'last pushed at' for this page, if any."""
    endpoint = _ENDPOINT_BY_TYPE.get(page_info.get("type", ""), "")
    pid = page_info.get("id")
    if not endpoint or not pid:
        return ""
    last = last_successful_admin_push(endpoint, pid)
    if not last:
        return ""
    payload = last.get("payload") or {}
    fields = []
    if payload.get("description") is not None:
        fields.append("description")
    if payload.get("metaTitle") is not None:
        fields.append("metaTitle")
    if payload.get("metaDescription") is not None:
        fields.append("metaDescription")
    flds = ", ".join(fields) if fields else "(no fields)"
    return f"Last successful push: {last.get('timestamp', '')} · {flds}"


@st.fragment
def render_admin_push_block(
    url: str,
    intro_text_html: str,
    meta_title: str,
    meta_description: str,
    key_prefix: str,
) -> None:
    """Render the admin-API push block for a single URL.

    Parameters
    ----------
    url : str
        The page URL — used to look up the internal id from the synced
        active-pages cache.
    intro_text_html : str
        The HTML to push as the page's `description` field. For categories
        and filter pages this is the short intro/description shown above
        (or in place of) the auto-content. CMS pages don't accept a
        description and the button is hidden for them.
    meta_title : str
        New meta title; empty string disables the button.
    meta_description : str
        New meta description; empty string disables the button.
    key_prefix : str
        Unique prefix for Streamlit widget keys on this page.
    """
    active_pages = st.session_state.get("mshop_active_pages") or {}
    page_info = lookup_url(active_pages, url)

    st.markdown("##### Push to Mshop (Admin API)")
    if not page_info:
        st.warning(
            "This URL is not in the synced active-pages list. "
            "Sync the list first using the **🔌 Mshop Admin API** "
            "expander at the top of this tab, then return here. "
            "If the URL is correct and still missing, the page may "
            "not be active/editable in Mshop."
        )
        return

    page_type = page_info.get("type", "")
    page_id = page_info.get("id")
    page_name = page_info.get("name", "") or url
    st.markdown(
        f"<div style='background:#0d0d15; border-left:3px solid #5533ff; "
        f"padding:0.5rem 0.7rem; border-radius:0 4px 4px 0; "
        f"font-size:0.8rem; color:#c8b4ff;'>"
        f"Resolved to <strong>{page_type}</strong> id <code>{page_id}</code> "
        f"— {page_name}"
        f"</div>",
        unsafe_allow_html=True,
    )
    last_caption = _last_push_caption(page_info)
    if last_caption:
        st.caption(last_caption)

    # Three buttons side-by-side. Each one is independent — clicking
    # only sends THAT field; the other fields stay null on the API call.
    col_intro, col_title, col_desc = st.columns(3)

    # ── Push intro text (description field) ──────────────────────
    with col_intro:
        if page_type == "cms":
            st.caption("Intro: not supported for CMS pages")
        else:
            disabled = not (intro_text_html or "").strip()
            if st.button(
                "Push intro text",
                key=f"{key_prefix}_push_intro",
                disabled=disabled,
                use_container_width=True,
                help="Updates the page's `description` field via "
                     "category/texts or filterpage/texts.",
            ):
                with st.spinner("Pushing intro text to Mshop..."):
                    res = update_for_page(page_info, description=intro_text_html)
                if res.get("status") == "success":
                    update_audit_after_push(url, intro_text=intro_text_html)
                _show_result(res, "Intro text", key_prefix)

    # ── Push meta title ──────────────────────────────────────────
    with col_title:
        disabled = not (meta_title or "").strip()
        if st.button(
            "Push meta title",
            key=f"{key_prefix}_push_meta_title",
            disabled=disabled,
            use_container_width=True,
        ):
            with st.spinner("Pushing meta title to Mshop..."):
                res = update_for_page(page_info, meta_title=meta_title)
            if res.get("status") == "success":
                update_audit_after_push(url, meta_title=meta_title)
            _show_result(res, "Meta title", key_prefix)

    # ── Push meta description ────────────────────────────────────
    with col_desc:
        disabled = not (meta_description or "").strip()
        if st.button(
            "Push meta description",
            key=f"{key_prefix}_push_meta_desc",
            disabled=disabled,
            use_container_width=True,
        ):
            with st.spinner("Pushing meta description to Mshop..."):
                res = update_for_page(page_info, meta_description=meta_description)
            if res.get("status") == "success":
                update_audit_after_push(url, meta_description=meta_description)
            _show_result(res, "Meta description", key_prefix)

    # ── Push everything at once (convenience) ────────────────────
    has_any = any([
        (intro_text_html or "").strip() and page_type != "cms",
        (meta_title or "").strip(),
        (meta_description or "").strip(),
    ])
    if has_any:
        if st.button(
            "Push all available fields",
            key=f"{key_prefix}_push_all",
            help="Send intro + meta title + meta description in a "
                 "single API call.",
        ):
            kwargs = {}
            if (intro_text_html or "").strip() and page_type != "cms":
                kwargs["description"] = intro_text_html
            if (meta_title or "").strip():
                kwargs["meta_title"] = meta_title
            if (meta_description or "").strip():
                kwargs["meta_description"] = meta_description
            with st.spinner("Pushing all fields to Mshop..."):
                res = update_for_page(page_info, **kwargs)
            if res.get("status") == "success":
                # Mirror only the fields actually sent — keyword names on
                # update_audit_after_push are different from the API ones.
                update_audit_after_push(
                    url,
                    intro_text=kwargs.get("description"),
                    meta_title=kwargs.get("meta_title"),
                    meta_description=kwargs.get("meta_description"),
                )
            _show_result(res, "All fields", key_prefix)

    # Show the "audit refreshed locally" caption beneath the buttons
    # whenever a push has updated this URL's audit row.
    refresh_caption = last_push_caption(url)
    if refresh_caption:
        st.caption(f"✓ {refresh_caption}")


def _disabled_caption(reason: str) -> None:
    """Compact gray reason shown directly under a disabled button."""
    st.markdown(
        f"<div style='font-size:0.7rem; color:#9b6644; margin-top:-0.4rem; margin-bottom:0.5rem;'>"
        f"Button disabled: {reason}</div>",
        unsafe_allow_html=True,
    )


def _no_lookup_banner() -> None:
    active_pages = st.session_state.get("mshop_active_pages") or {}
    table = active_pages.get("lookup") if isinstance(active_pages, dict) else None
    if not table:
        st.caption(
            "🔌 Mshop active-pages cache is empty — click "
            "**🔌 Mshop Admin API → Sync active pages** at the top of the tab "
            "to enable direct push."
        )
    else:
        st.caption(
            f"🔌 This URL is not in the {len(table)}-page Mshop active-pages "
            "cache. Re-sync if the page was added recently, or check that the "
            "URL slug exists in Mshop."
        )


@st.fragment
def render_inline_intro_push(url: str, intro_text_html: str, key_prefix: str) -> None:
    """Inline push button for the intro/description field.

    Designed to live next to the generated intro text inside the per-page
    Intro card, so the user does not have to scroll to a separate "push"
    block. Independent fragment so reruns don't redraw the whole page.
    """
    active_pages = st.session_state.get("mshop_active_pages") or {}
    page_info = lookup_url(active_pages, url)
    if not page_info:
        _no_lookup_banner()
        return
    page_type = page_info.get("type", "")
    if page_type == "cms":
        st.caption("Intro: not supported for CMS pages.")
        return

    last = _last_push_caption(page_info)
    if last:
        st.caption(last)

    text_len = len((intro_text_html or "").strip())
    disabled = text_len == 0
    if st.button(
        "📤 Push intro to Mshop",
        key=f"{key_prefix}_inline_push_intro",
        disabled=disabled,
        use_container_width=True,
        help="Updates the page's `description` field via "
             "category/texts or filterpage/texts.",
    ):
        with st.spinner("Pushing intro text to Mshop..."):
            res = update_for_page(page_info, description=intro_text_html)
        if res.get("status") == "success":
            update_audit_after_push(url, intro_text=intro_text_html)
        _show_result(res, "Intro text", key_prefix)
        refresh_caption = last_push_caption(url)
        if refresh_caption:
            st.caption(f"✓ {refresh_caption}")
    if disabled:
        _disabled_caption(
            "intro text is empty (length 0). The intro generator returned "
            "no usable content — check the diff above and regenerate."
        )


@st.fragment
def render_inline_meta_title_push(url: str, meta_title: str, key_prefix: str, current_title: str = "") -> None:
    """Inline push button for the meta title field."""
    active_pages = st.session_state.get("mshop_active_pages") or {}
    page_info = lookup_url(active_pages, url)
    if not page_info:
        _no_lookup_banner()
        return

    title_len = len((meta_title or "").strip())
    disabled = title_len == 0
    if st.button(
        "📤 Push meta title to Mshop",
        key=f"{key_prefix}_inline_push_meta_title",
        disabled=disabled,
        use_container_width=True,
    ):
        with st.spinner("Pushing meta title to Mshop..."):
            res = update_for_page(page_info, meta_title=meta_title)
        if res.get("status") == "success":
            update_audit_after_push(url, meta_title=meta_title)
        _show_result(res, "Meta title", key_prefix)
        refresh_caption = last_push_caption(url)
        if refresh_caption:
            st.caption(f"✓ {refresh_caption}")
    if disabled:
        if current_title and (meta_title or "") == current_title:
            _disabled_caption("recommended title equals what's already live — nothing to push.")
        else:
            _disabled_caption(
                "no recommended meta title yet. Click **🤖 Generate meta "
                "title + description** above first."
            )


@st.fragment
def render_inline_meta_desc_push(url: str, meta_description: str, key_prefix: str, current_desc: str = "") -> None:
    """Inline push button for the meta description field."""
    active_pages = st.session_state.get("mshop_active_pages") or {}
    page_info = lookup_url(active_pages, url)
    if not page_info:
        _no_lookup_banner()
        return

    desc_len = len((meta_description or "").strip())
    disabled = desc_len == 0
    if st.button(
        "📤 Push meta description to Mshop",
        key=f"{key_prefix}_inline_push_meta_desc",
        disabled=disabled,
        use_container_width=True,
    ):
        with st.spinner("Pushing meta description to Mshop..."):
            res = update_for_page(page_info, meta_description=meta_description)
        if res.get("status") == "success":
            update_audit_after_push(url, meta_description=meta_description)
        _show_result(res, "Meta description", key_prefix)
        refresh_caption = last_push_caption(url)
        if refresh_caption:
            st.caption(f"✓ {refresh_caption}")
    if disabled:
        if current_desc and (meta_description or "") == current_desc:
            _disabled_caption("recommended description equals what's already live — nothing to push.")
        else:
            _disabled_caption(
                "no recommended meta description yet. Click **🤖 Generate "
                "meta title + description** above first."
            )


def render_push_resolution_banner(url: str) -> None:
    """Compact one-line banner showing whether this URL resolves to a Mshop
    page id (for direct push). Render once near the top of a per-page card
    so the user knows what's available without trying buttons one-by-one."""
    active_pages = st.session_state.get("mshop_active_pages") or {}
    table = active_pages.get("lookup") if isinstance(active_pages, dict) else None
    page_info = lookup_url(active_pages, url) if active_pages else None
    if not table:
        st.caption("🔌 Mshop sync: not done — push buttons will be hidden.")
        return
    if not page_info:
        st.caption(
            f"🔌 Mshop sync: ✓ ({len(table)} pages) but **this URL is not in "
            "the cache** — push buttons will be hidden. Re-sync or check the slug."
        )
        return
    st.caption(
        f"🔌 Mshop: resolved to **{page_info.get('type', '?')}** id "
        f"`{page_info.get('id', '?')}` — push buttons enabled."
    )


def _show_result(res: dict, label: str, key_prefix: str) -> None:
    status = res.get("status")
    if status == "success":
        st.success(
            f"{label} pushed — HTTP {res.get('http_code')}"
        )
    else:
        st.error(
            f"{label} push failed — {res.get('error') or status}"
            + (f" (HTTP {res.get('http_code')})" if res.get("http_code") else "")
        )
    # NOTE: cannot use st.expander here because this fragment is
    # invoked from inside an outer st.expander (the per-page card),
    # and Streamlit forbids nested expanders. Use st.popover instead,
    # which is allowed inside expanders.
    with st.popover(f"{label} — Mshop response"):
        st.markdown(f"**Status:** `{status}` · **HTTP:** {res.get('http_code', '?')}")
        if res.get("error"):
            st.markdown(f"**Error:** `{res.get('error')}`")
        st.markdown("**Response body:**")
        st.code(_fmt_response(res), language="json")
        st.markdown("**Payload sent:**")
        st.code(
            json.dumps(res.get("payload", {}), ensure_ascii=False, indent=2),
            language="json",
        )
