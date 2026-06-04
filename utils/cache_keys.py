"""Single source of truth for the per-page AI cache keys + reading them.

The generated artifacts for a page are cached in session_state under:
    _ai_plan_<h>      → implementation plan (has meta_title, meta_description)
    _bottom_text_<h>  → bottom text (has bottom_html)
    _intro_text_<h>   → intro rewrite (has optimized_text)
where <h> = stable_hash(url).

Readers used to inline `st.session_state.get(f"_bottom_text_{hash}")...` in
5+ places with subtly different hashing, which is exactly how the
"generated under one url-form, read under another" push bug crept in. Use
THESE helpers everywhere so the key derivation lives in one place.
"""

from utils.ui_helpers import stable_hash


def ai_plan_key(url: str) -> str:
    return f"_ai_plan_{stable_hash(url)}"


def bottom_text_key(url: str) -> str:
    return f"_bottom_text_{stable_hash(url)}"


def intro_text_key(url: str) -> str:
    return f"_intro_text_{stable_hash(url)}"


def _get(key: str) -> dict:
    import streamlit as st
    v = st.session_state.get(key)
    return v if isinstance(v, dict) else {}


def get_generated_content(url: str) -> dict:
    """Return the page's generated, pushable fields in one shape:
        {"bottom_html", "intro_html", "meta_title", "meta_description"}
    Empty strings for anything not generated. This is the single reader the
    push paths use, so they can never disagree on key names or hashing."""
    plan = _get(ai_plan_key(url))
    return {
        "bottom_html": _get(bottom_text_key(url)).get("bottom_html") or "",
        "intro_html": _get(intro_text_key(url)).get("optimized_text") or "",
        "meta_title": plan.get("meta_title") or "",
        "meta_description": plan.get("meta_description") or "",
    }
