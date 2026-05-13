"""
Cross-view deep-link utility: focus Quick Wins on a specific URL from
anywhere else in the app (Page Auditor, Action Plan, Site Cleanup, …).

Identity model: the focus is the URL itself, NOT a list-position index.
Earlier index-based jumps were broken by Streamlit's widget lifecycle
(the "Go to page" number_input persisted its previous value and
overwrote programmatic index updates after every deep link, so users
landed on the page they had last manually selected). They were also
wrong-by-design: the Quick Wins page list is sorted by lost_clicks +
quality boost, so the same URL might be at idx 5 today and idx 12
tomorrow — making a deep link's index meaningless.

Usage in any view:
    from utils.page_deeplink import open_in_quick_wins
    if st.button("🚀 Open in Quick Wins"):
        open_in_quick_wins(url)
        st.rerun()

Quick Wins reads the focus via current_focus_url() at the start of its
per-page tab and renders the card for that URL directly, regardless of
where the URL sits in the sorted list (or whether it sits there at
all). A "← Back to opportunity list" button clears the focus.
"""

import streamlit as st


_FOCUS_KEY = "_qw_focus_url"


def open_in_quick_wins(url: str) -> None:
    """Navigate to Quick Wins and focus on the given URL. Caller should
    call st.rerun() right after.

    Sets selected_page (the persisted nav-state key). The sidebar code
    in app.py bridges selected_page → nav_radio BEFORE the radio widget
    renders, so Streamlit doesn't error out from setting widget state
    after instantiation. Don't set nav_radio here directly — that
    raises StreamlitAPIException because by the time this function
    runs (button-click handler) the sidebar radio has already rendered
    on the current frame.
    """
    st.session_state[_FOCUS_KEY] = url
    st.session_state["selected_page"] = "⚡ Quick Wins"


def current_focus_url() -> str | None:
    """Return the URL Quick Wins should currently be focused on, or None
    to fall back to the paginated list. Does NOT clear the focus —
    that's done explicitly via clear_focus() when the user goes back."""
    val = st.session_state.get(_FOCUS_KEY)
    return val if val else None


def clear_focus() -> None:
    """Drop the current focus so Quick Wins resumes paginated browsing."""
    st.session_state.pop(_FOCUS_KEY, None)


def find_page_index(pages: list, url: str) -> int | None:
    """Find the position of `url` in Quick Wins' sorted `pages` list.
    Returns None if not found. Used for "you are here" hints; not the
    primary navigation mechanism. Comparison goes through normalize_url."""
    if not url or not pages:
        return None
    from utils.ui_helpers import normalize_url
    target = normalize_url(url)
    for i, p in enumerate(pages):
        if normalize_url(p.get("url", "")) == target:
            return i
    return None


# ── Backwards compat shim: keep old API alive for one release so any
# external code that hasn't been updated yet doesn't break. Both shims
# delegate to the new focus-based flow.
def consume_jump_request() -> str | None:
    """Deprecated. Use current_focus_url() in render and clear_focus()
    when leaving the focused view. Kept so older Quick Wins builds in
    rolling deploys don't crash on import."""
    return current_focus_url()
