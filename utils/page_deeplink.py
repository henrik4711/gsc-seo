"""
Cross-view deep-link utility: jump straight to a specific URL in Quick Wins
from anywhere else in the app (Page Auditor, Action Plan, Site Cleanup, …).

Usage in any view:
    from utils.page_deeplink import open_in_quick_wins
    if st.button("🚀 Open in Quick Wins"):
        open_in_quick_wins(url)
        st.rerun()

Quick Wins picks up the request via consume_jump_request() at the start of
its render() and jumps to the right page index.
"""

import streamlit as st


_JUMP_KEY = "_qw_jump_to_url"


def open_in_quick_wins(url: str) -> None:
    """Navigate to Quick Wins and request a jump to the given URL on the
    next render. Call st.rerun() yourself afterwards."""
    st.session_state[_JUMP_KEY] = url
    st.session_state["selected_page"] = "⚡ Quick Wins"


def consume_jump_request() -> str | None:
    """Called by Quick Wins at the start of its render. Returns the URL the
    caller asked us to jump to (or None) and clears the request so the
    next render doesn't keep jumping."""
    url = st.session_state.pop(_JUMP_KEY, None)
    return url


def find_page_index(pages: list, url: str) -> int | None:
    """Find the position of `url` in Quick Wins' sorted `pages` list.
    Returns None if not found. Comparison is normalized via ui_helpers."""
    if not url or not pages:
        return None
    from utils.ui_helpers import normalize_url
    target = normalize_url(url)
    for i, p in enumerate(pages):
        if normalize_url(p.get("url", "")) == target:
            return i
    return None
