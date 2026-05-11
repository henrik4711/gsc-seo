"""
Action status registry — single source of truth for "has the user marked
this recommendation as done?" across all Site Cleanup tabs (and elsewhere).

Per-tab namespacing: same URL can be marked done under "delete" but not
under "redirect", because they are separate decisions.

Persisted to /data/action_status.json via utils.persistence.save().
"""

from datetime import datetime
from typing import Optional

import streamlit as st


ACTION_STATUS_KEY = "action_status"

# Recognized action types. Adding more is fine — this list is just for
# discoverability; nothing enforces it.
ACTION_TYPES = (
    "merge",          # cannibalization merges
    "create",         # create-new-page recommendations
    "redirect",       # 301-redirect broken pages or duplicates
    "noindex",        # add noindex meta
    "robots",         # block in robots.txt
    "delete",         # delete the page entirely
    "reconnect",      # add internal link from category to orphaned page
    "needs_content",  # product page needs description
    "blog_review",    # rewrite or remove weak blog post
    "topic_gap",      # create new content to fill a topical gap
)


def _store() -> dict:
    """Get the action status dict from session state, creating if missing."""
    return st.session_state.setdefault(ACTION_STATUS_KEY, {})


def _save_to_disk() -> None:
    try:
        from utils.persistence import save
        save(ACTION_STATUS_KEY)
    except Exception as e:
        # Persistence shouldn't be a hard dependency in tests / local dev
        print(f"[action_status] save failed: {e}")


# ── Read API ──────────────────────────────────────────────────────────

def is_done(action_type: str, action_id: str) -> bool:
    return action_id in _store().get(action_type, {})


def done_info(action_type: str, action_id: str) -> Optional[dict]:
    return _store().get(action_type, {}).get(action_id)


def done_count(action_type: str) -> int:
    return len(_store().get(action_type, {}))


def done_ids(action_type: str) -> set:
    return set(_store().get(action_type, {}).keys())


# ── Write API ─────────────────────────────────────────────────────────

def mark_done(action_type: str, action_id: str, note: str = "") -> None:
    _store().setdefault(action_type, {})[action_id] = {
        "done_at": datetime.now().isoformat(timespec="seconds"),
        "note": note,
    }
    _save_to_disk()


def mark_pending(action_type: str, action_id: str) -> None:
    bucket = _store().get(action_type, {})
    if action_id in bucket:
        del bucket[action_id]
        _save_to_disk()


def mark_many_done(action_type: str, action_ids, note: str = "") -> int:
    bucket = _store().setdefault(action_type, {})
    now = datetime.now().isoformat(timespec="seconds")
    n = 0
    for aid in action_ids:
        if aid not in bucket:
            bucket[aid] = {"done_at": now, "note": note}
            n += 1
    if n:
        _save_to_disk()
    return n


def mark_many_pending(action_type: str, action_ids) -> int:
    bucket = _store().get(action_type, {})
    n = 0
    for aid in action_ids:
        if aid in bucket:
            del bucket[aid]
            n += 1
    if n:
        _save_to_disk()
    return n
