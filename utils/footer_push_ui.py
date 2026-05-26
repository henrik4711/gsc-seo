"""
Streamlit UI block for pushing footer text to Magento.
Used by views/quick_wins.py and views/action_plan.py.

UX:
- @st.fragment scopes reruns to just this block — no full-page reload.
- @st.dialog opens the preview as a true modal.
- After Confirm, the dialog stays open and shows the raw Magento response
  (HTTP code + body) so the user can verify the push actually took effect.
- Successful push caches content_hash so the parent fragment shows the
  "PUSHED" banner; regenerating bottom text invalidates that automatically.
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
    read_push_log,
)


def _content_hash(html: str) -> str:
    return hashlib.md5((html or "").encode("utf-8")).hexdigest()


def _store_id() -> int:
    raw = os.environ.get("FOOTER_TEXT_STORE_ID", "").strip()
    try:
        return int(raw) if raw else 0
    except ValueError:
        return 0


def _section_counts(payload: dict) -> tuple[int, int]:
    texts = payload.get("texts", []) or []
    faq = sum(1 for t in texts if t.get("tagAsFaq"))
    return len(texts) - faq, faq


@st.fragment
def render_footer_push_block(url: str, bottom_html: str, key_prefix: str) -> None:
    """Render the push block for a single URL. Reruns scoped to this fragment."""
    ok, err = validate_before_push(bottom_html)
    if not ok:
        st.warning(f"Cannot push to Magento — {err}")
        return

    content_hash = _content_hash(bottom_html)
    pushed_hash_key = f"{key_prefix}_pushed_hash"
    pushed_at_key = f"{key_prefix}_pushed_at"
    last_error_key = f"{key_prefix}_last_error"

    last = last_successful_push(url)
    if last:
        reg, faq = _section_counts(last.get("payload", {}))
        st.markdown(
            f"<div style='background:#0d1a0d; border:1px solid #33dd88; border-radius:6px; "
            f"padding:0.5rem 0.7rem; margin:0.5rem 0; font-size:0.75rem;'>"
            f"<strong style='color:#33dd88;'>Last successful push:</strong> "
            f"<span style='color:#c8b4ff;'>{last.get('timestamp','')} · "
            f"HTTP {last.get('http_code')} · {reg} regular + {faq} FAQ sections · "
            f"store {last.get('store_id')}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        with st.popover("Show last Magento response"):
            st.markdown(f"**HTTP {last.get('http_code')}** · `{last.get('timestamp','')}`")
            body = last.get("response_body") or "(empty body)"
            st.code(body, language="json")
            st.markdown("**Payload that was sent:**")
            st.code(json.dumps(last.get("payload", {}), ensure_ascii=False, indent=2), language="json")

    # Locked state — current content was pushed already
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

    audit_results = st.session_state.get("audit_results", [])
    if audit_results and not is_url_audited(url, audit_results):
        st.warning(f"URL not found in audit data: `{url}` — you can still push, but double-check it's correct.")

    if not os.environ.get("FOOTER_TEXT_API"):
        st.info("Push disabled: `FOOTER_TEXT_API` env var is not set on this deployment.")
        return
    if _store_id() <= 0:
        st.info("Push disabled: `FOOTER_TEXT_STORE_ID` env var is not set / invalid.")
        return

    if st.session_state.get(last_error_key):
        st.error(st.session_state[last_error_key])

    if st.button(
        "Preview payload for push to Magento",
        key=f"{key_prefix}_open_dialog_btn",
        use_container_width=True,
    ):
        _push_preview_dialog(url, bottom_html, key_prefix, content_hash)


@st.dialog("Preview — push to Magento", width="large")
def _push_preview_dialog(url: str, bottom_html: str, key_prefix: str, content_hash: str) -> None:
    result_key = f"{key_prefix}_dlg_result"

    # If Confirm already ran, we're now in the "show response" view
    result = st.session_state.get(result_key)
    if result:
        _render_push_result(result, key_prefix)
        return

    # Preview view
    payload = build_payload(url, bottom_html, _store_id())
    reg_count, faq_count = _section_counts(payload)
    sec_count = reg_count + faq_count

    if sec_count == 0:
        st.error("Payload builder produced 0 sections — generated HTML cannot be parsed.")
        if st.button("Close", key=f"{key_prefix}_dlg_close_empty"):
            st.rerun()
        return

    st.markdown(
        f"<div style='font-size:0.8rem; color:#c8b4ff; margin-bottom:0.5rem;'>"
        f"<strong>URL:</strong> <code>{payload['url']}</code><br>"
        f"<strong>storeId:</strong> {payload['storeId']} · "
        f"<strong>Replace existing:</strong> {payload['disableExistingTexts']} · "
        f"<strong>Sections:</strong> {reg_count} regular + {faq_count} FAQ"
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
            key=f"{key_prefix}_dlg_confirm",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Pushing to Magento…"):
                result = push_footer_text(url, bottom_html)
            st.session_state[result_key] = result
            if result.get("status") == "success":
                st.session_state[f"{key_prefix}_pushed_hash"] = content_hash
                st.session_state[f"{key_prefix}_pushed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.session_state.pop(f"{key_prefix}_last_error", None)
                # Reflect the pushed bottom-text in audit_results so the
                # next AI bulk run doesn't keep flagging the same "no
                # bottom text" / "missing keywords" gaps the user just
                # filled. See utils/audit_refresh.py for the full story.
                try:
                    from utils.audit_refresh import update_audit_after_push
                    update_audit_after_push(url, bottom_text=bottom_html)
                except Exception as _e:
                    print(f"[footer_push_ui] audit refresh failed for {url}: {_e}")
            st.rerun()  # re-renders dialog in result view
    with col_cancel:
        if st.button("Cancel", key=f"{key_prefix}_dlg_cancel", use_container_width=True):
            st.rerun()  # closes dialog


def _render_push_result(result: dict, key_prefix: str) -> None:
    """Inside the dialog, show the raw Magento response after Confirm."""
    status = result.get("status", "error")
    http_code = result.get("http_code")
    body = result.get("response_body") or ""
    payload = result.get("payload", {}) or {}

    if status == "success":
        st.success(f"Push succeeded — HTTP {http_code}")
    else:
        st.error(f"Push failed — {status} · HTTP {http_code or 'n/a'}")
        if result.get("error"):
            st.markdown(f"**Error:** `{result['error']}`")

    st.markdown("##### Raw response from Magento")
    if body.strip():
        # Show as JSON if it parses, else as plain text
        try:
            parsed = json.loads(body)
            st.code(json.dumps(parsed, ensure_ascii=False, indent=2), language="json")
        except Exception:
            st.code(body, language="text")
    else:
        st.info("Response body was empty.")

    reg, faq = _section_counts(payload)
    st.markdown(
        f"<div style='font-size:0.75rem; color:#9b9bb8; margin-top:0.5rem;'>"
        f"Sent {reg} regular + {faq} FAQ sections · "
        f"<code>disableExistingTexts={payload.get('disableExistingTexts')}</code> · "
        f"storeId={payload.get('storeId')}"
        f"</div>",
        unsafe_allow_html=True,
    )

    with st.popover("Show full payload that was sent"):
        st.code(json.dumps(payload, ensure_ascii=False, indent=2), language="json")

    col_close, col_back = st.columns([2, 1])
    with col_close:
        if st.button(
            "Close",
            key=f"{key_prefix}_dlg_result_close",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.pop(f"{key_prefix}_dlg_result", None)
            st.rerun()
    with col_back:
        if st.button(
            "Back to preview",
            key=f"{key_prefix}_dlg_result_back",
            use_container_width=True,
        ):
            st.session_state.pop(f"{key_prefix}_dlg_result", None)
            st.rerun()
