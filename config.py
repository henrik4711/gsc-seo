"""
Load configuration from environment variables (Railway) with session_state fallback.
"""

import os
import json
import streamlit as st


def init_from_env():
    """Load env vars into session_state on first run."""
    if st.session_state.get("_env_loaded"):
        return

    # Anthropic API key
    if "anthropic_key" not in st.session_state:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            st.session_state["anthropic_key"] = key

    # Site context
    if "site_context" not in st.session_state:
        ctx = os.environ.get("SITE_CONTEXT", "")
        if ctx:
            st.session_state["site_context"] = ctx

    # Content language
    if "content_language" not in st.session_state:
        lang = os.environ.get("CONTENT_LANGUAGE", "")
        if lang:
            st.session_state["content_language"] = lang

    # GSC credentials JSON
    if "gsc_credentials" not in st.session_state:
        raw = os.environ.get("GSC_CREDENTIALS_JSON", "")
        if raw:
            try:
                st.session_state["gsc_credentials"] = json.loads(raw)
            except json.JSONDecodeError:
                pass

    # GSC site URL
    if "gsc_site_url" not in st.session_state:
        url = os.environ.get("GSC_SITE_URL", "")
        if url:
            st.session_state["gsc_site_url"] = url

    st.session_state["_env_loaded"] = True


def get_anthropic_key() -> str:
    """Get Anthropic API key from session_state or env."""
    return st.session_state.get("anthropic_key", os.environ.get("ANTHROPIC_API_KEY", ""))


def has_anthropic_key() -> bool:
    return bool(get_anthropic_key())
