"""
Streamlit rendering helpers for action items with done/pending status.

Used by every Site Cleanup tab so the look + behavior is identical:
- Top toolbar: "Show completed" toggle + counter
- Per-row: gray-out + ✓ DONE badge + Undo button when marked done
- Bottom: "Mark all visible as done" bulk action

All persistence goes through utils.action_status, which is the single
source of truth.
"""

import streamlit as st

from utils import action_status as _as


def filter_toolbar(action_type: str, total: int, key_prefix: str = "") -> bool:
    """Render top-of-tab counter + 'Show completed' toggle.
    Returns True if completed items should be shown.
    """
    n_done = _as.done_count(action_type)
    n_pending = max(0, total - n_done)
    cols = st.columns([3, 2])
    with cols[0]:
        st.markdown(
            f"<div style='font-size:0.85rem; color:#9b9bb8; padding-top:0.4rem;'>"
            f"<span style='color:#ffaa33; font-weight:600;'>{n_pending}</span> to do · "
            f"<span style='color:#33dd88; font-weight:600;'>{n_done}</span> done · "
            f"{total} total</div>",
            unsafe_allow_html=True,
        )
    with cols[1]:
        return st.checkbox(
            "Show completed",
            value=False,
            key=f"{key_prefix}show_done_{action_type}",
        )


def filter_visible(items: list, action_type: str, id_fn, show_completed: bool) -> list:
    """Filter items list — hide completed unless show_completed is True.
    id_fn(item) -> action_id string."""
    if show_completed:
        return list(items)
    done = _as.done_ids(action_type)
    return [it for it in items if id_fn(it) not in done]


def done_badge_html(action_type: str, action_id: str) -> str:
    """Returns HTML for an inline ✓ DONE badge if marked, empty string otherwise."""
    info = _as.done_info(action_type, action_id)
    if info is None:
        return ""
    return (
        f"<span style='background:#0d2818; color:#33dd88; padding:0.1rem 0.4rem; "
        f"border-radius:3px; font-size:0.7rem; font-weight:600; margin-left:0.5rem;'>"
        f"✓ DONE {info.get('done_at', '')[:10]}</span>"
    )


def mark_button(action_type: str, action_id: str, key_suffix: str = "") -> bool:
    """Render the per-row Mark done / Undo button. Triggers st.rerun on click.
    Returns True if state changed this render (rare; usually rerun fires first).
    """
    is_done = _as.is_done(action_type, action_id)
    btn_key = f"actbtn_{action_type}_{action_id}{key_suffix}"
    if is_done:
        if st.button("↶ Undo", key=btn_key, help="Mark as still pending"):
            _as.mark_pending(action_type, action_id)
            st.rerun()
    else:
        if st.button("✓ Mark done", key=btn_key, type="primary",
                     help="Hide from this list — your task is complete"):
            _as.mark_done(action_type, action_id)
            st.rerun()
    return False


def render_action_row(action_type: str, action_id: str, content_html: str, key_suffix: str = ""):
    """Render a single action item: content on the left, mark/undo button on the right.
    If item is done, content is grayed out and a ✓ DONE badge is appended."""
    is_done = _as.is_done(action_type, action_id)
    cols = st.columns([8, 2])
    with cols[0]:
        if is_done:
            badge = done_badge_html(action_type, action_id)
            st.markdown(
                f"<div style='opacity:0.55; padding:0.4rem 0;'>{badge}<br>{content_html}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(content_html, unsafe_allow_html=True)
    with cols[1]:
        mark_button(action_type, action_id, key_suffix)


def bulk_done_button(action_type: str, all_ids: list, key_suffix: str = ""):
    """Render a 'Mark all N pending as done' button. Skips already-done items."""
    pending = [aid for aid in all_ids if not _as.is_done(action_type, aid)]
    if not pending:
        return
    btn_key = f"bulkdone_{action_type}{key_suffix}"
    if st.button(
        f"✓ Mark all {len(pending)} pending in this view as done",
        key=btn_key,
        help="Bulk-mark every currently-visible pending item as done",
    ):
        n = _as.mark_many_done(action_type, pending)
        st.success(f"Marked {n} as done")
        st.rerun()
