"""
Streamlit UI block for pushing footer text to Magento.
Used by views/quick_wins.py and views/action_plan.py.

Flow: Preview → Confirm. Locks after successful push until content changes
(content_hash mismatch → unlocks automatically when user regenerates).
"""

import os
import json
import hashlib
from datetime import datetime

import streamlit as st

from utils.footer_text_api import (
    validate_before_push,
    is_url_audited,
    build_payload,
    push_footer_text,
    last_successful_push,
)


def _content_hash(html: str) -> str:
    return hashlib.md5((html or "").encode("utf-8")).hexdigest()


def _store_id() -> int:
    raw = os.environ.get("FOOTER_TEXT_STORE_ID", "").strip()
    try:
        return int(raw) if raw else 0
    except ValueError:
        return 0


def render_footer_push_block(url: str, bottom_html: str, key_prefix: str) -> None:
    """Render the Preview → Confirm push block for a single URL's bottom text."""
    # Hard validation — no <h2> means we can't push at all
    ok, err = validate_before_push(bottom_html)
    if not ok:
        st.warning(f"Cannot push to Magento — {err}")
        return

    content_hash = _content_hash(bottom_html)
    pushed_hash_key = f"{key_prefix}_pushed_hash"
    pushed_at_key = f"{key_prefix}_pushed_at"
    preview_key = f"{key_prefix}_preview_open"
    last_error_key = f"{key_prefix}_last_error"

    # Show previous-push banner from persistent log
    last = last_successful_push(url)
    if last:
        st.markdown(
            f"<div style='background:#0d1a0d; border:1px solid #33dd88; border-radius:6px; "
            f"padding:0.5rem 0.7rem; margin:0.5rem 0; font-size:0.75rem;'>"
            f"<strong style='color:#33dd88;'>Last successful push:</strong> "
            f"<span style='color:#c8b4ff;'>{last.get('timestamp','')} · "
            f"{last.get('section_count', 0)} sections to store {last.get('store_id')}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Locked state — content we're looking at was already pushed this session
    if st.session_state.get(pushed_hash_key) == content_hash:
        pushed_at = st.session_state.get(pushed_at_key, "")
        st.markdown(
            f"<div style='background:#0d1a0d; border:2px solid #33dd88; border-radius:8px; "
            f"padding:0.8rem; margin:0.5rem 0;'>"
            f"<div style='font-family:IBM Plex Mono,monospace; font-size:0.65rem; color:#33dd88;'>"
            f"PUSHED TO MAGENTO · {pushed_at}</div>"
            f"<div style='font-size:0.8rem; color:#c8b4ff; margin-top:0.2rem;'>"
            f"Click Regenerate above to create new content and push again.</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    # Soft URL validation
    audit_results = st.session_state.get("audit_results", [])
    if audit_results and not is_url_audited(url, audit_results):
        st.warning(f"URL not found in audit data: `{url}` — you can still push, but double-check it's correct.")

    # Env-var readiness
    if not os.environ.get("FOOTER_TEXT_API"):
        st.info("Push disabled: `FOOTER_TEXT_API` env var is not set on this deployment.")
        return
    if _store_id() <= 0:
        st.info("Push disabled: `FOOTER_TEXT_STORE_ID` env var is not set / invalid.")
        return

    # Idle state: show Preview button
    if not st.session_state.get(preview_key):
        if st.button(
            "Preview payload for push to Magento",
            key=f"{key_prefix}_prev_btn",
            use_container_width=True,
        ):
            st.session_state[preview_key] = True
            st.rerun()
        # Show last error if any (from previous attempt in this session)
        if st.session_state.get(last_error_key):
            st.error(st.session_state[last_error_key])
        return

    # Preview state: show payload + Confirm/Cancel buttons
    payload = build_payload(url, bottom_html, _store_id())
    sec_count = len(payload.get("texts", []))

    if sec_count == 0:
        st.error("Payload builder produced 0 sections — generated HTML cannot be parsed into sections.")
        if st.button("Back", key=f"{key_prefix}_back_btn"):
            st.session_state[preview_key] = False
            st.rerun()
        return

    st.markdown("##### Preview — what will be sent to Magento")
    st.markdown(
        f"<div style='font-size:0.8rem; color:#c8b4ff; margin-bottom:0.5rem;'>"
        f"<strong>URL:</strong> <code>{payload['url']}</code> · "
        f"<strong>storeId:</strong> {payload['storeId']} · "
        f"<strong>Replace existing:</strong> {payload['disableExistingTexts']} · "
        f"<strong>Sections:</strong> {sec_count}"
        f"</div>",
        unsafe_allow_html=True,
    )

    tab_rendered, tab_json = st.tabs(["Rendered", "JSON payload"])
    with tab_rendered:
        for t in payload["texts"]:
            faq_badge = (
                "<span style='background:#3a2a00; color:#ffaa33; padding:1px 6px; border-radius:3px; "
                "font-size:0.6rem; margin-left:0.5rem;'>FAQ</span>"
                if t["tagAsFaq"] else ""
            )
            st.markdown(
                f"<div style='margin-top:0.8rem; margin-bottom:0.2rem;'>"
                f"<span style='font-family:IBM Plex Mono,monospace; font-size:0.6rem; color:#5533ff;'>"
                f"#{t['sortOrder']}</span>{faq_badge}"
                f"</div>"
                f"<div style='font-size:1rem; font-weight:600; color:#f0f0ff; margin-bottom:0.3rem;'>"
                f"{t['headline']}</div>",
                unsafe_allow_html=True,
            )
            st.markdown(t["content"], unsafe_allow_html=True)
            st.markdown("<hr style='border-color:#1e1e2e; margin:0.5rem 0;' />", unsafe_allow_html=True)
    with tab_json:
        st.code(json.dumps(payload, ensure_ascii=False, indent=2), language="json")

    col_confirm, col_cancel = st.columns([2, 1])
    with col_confirm:
        if st.button(
            "Confirm push to Magento",
            key=f"{key_prefix}_confirm_btn",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Pushing to Magento…"):
                result = push_footer_text(url, bottom_html)
            if result.get("status") == "success":
                st.session_state[pushed_hash_key] = content_hash
                st.session_state[pushed_at_key] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.session_state[preview_key] = False
                st.session_state.pop(last_error_key, None)
                st.rerun()
            else:
                status = result.get("status", "error")
                err_msg = result.get("error") or "Unknown error"
                http_code = result.get("http_code")
                body = (result.get("response_body") or "")[:2000]
                msg = f"Push failed ({status}): {err_msg}"
                if http_code:
                    msg += f" · HTTP {http_code}"
                if body:
                    msg += f"\n\nResponse body:\n{body}"
                st.session_state[last_error_key] = msg
                st.error(msg)
    with col_cancel:
        if st.button("Cancel", key=f"{key_prefix}_cancel_btn", use_container_width=True):
            st.session_state[preview_key] = False
            st.rerun()
