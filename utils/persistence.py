"""
Persist session state data to Railway volume (/data).
Auto-save after audits/imports, auto-load on app start.
"""

import os
import json
import streamlit as st
import pandas as pd

DATA_DIR = "/data"

# Keys to persist and their types
PERSIST_KEYS = {
    # GSC foundation data
    "gsc_data": "dataframe",          # All GSC query+page data — the foundation
    "gsc_site": "setting",            # Selected GSC property URL
    "site_context": "setting",        # Site context string
    "content_language": "setting",    # Content language
    # Analysis results
    "ctr_gaps": "dataframe",          # CTR gap analysis
    "cannibalization": "json",        # Cannibalization results
    "topic_clusters": "json",         # Topic cluster data
    "content_roadmap": "json",        # Content roadmap
    "content_gaps": "json",           # Content gaps
    # Audit
    "audit_results": "json",          # List of audit dicts
    # Screaming Frog
    "sf_pages": "dataframe",          # SF All Pages DataFrame
    "sf_inlinks": "dataframe",        # SF All Inlinks DataFrame
    "sf_link_map": "json",            # Processed link map dict
    "sf_crawl_issues": "json",        # Crawl analysis results
    # Ahrefs
    "page_authority": "dataframe",    # Ahrefs page authority
    "ahrefs_best_by_links": "dataframe",
    "ahrefs_backlinks": "dataframe",
    "ahrefs_organic_keywords": "dataframe",
    # AI generated
    "generated_content": "json",      # AI-generated meta/content per URL
    "action_plan": "json",            # AI-generated action plan
}


def _volume_available() -> bool:
    """Check if the Railway volume is mounted."""
    return os.path.isdir(DATA_DIR)


def _file_path(key: str, data_type: str) -> str:
    ext = "csv" if data_type == "dataframe" else "json"
    return os.path.join(DATA_DIR, f"{key}.{ext}")


def save_key(key: str):
    """Save a single session state key to disk."""
    if not _volume_available():
        return
    if key not in PERSIST_KEYS or key not in st.session_state:
        return

    data_type = PERSIST_KEYS[key]
    path = _file_path(key, data_type)
    data = st.session_state[key]

    try:
        if data_type == "setting":
            with open(path, "w", encoding="utf-8") as f:
                f.write(str(data))
        elif data_type == "dataframe" and isinstance(data, pd.DataFrame):
            data.to_csv(path, index=False)
        elif data_type == "json":
            # Convert numpy/pandas types to native Python
            def _convert(obj):
                if hasattr(obj, 'item'):
                    return obj.item()
                if isinstance(obj, pd.Timestamp):
                    return str(obj)
                if isinstance(obj, (set, frozenset)):
                    return list(obj)
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1, default=_convert)
    except Exception as e:
        print(f"[persistence] Failed to save {key}: {e}")


def save_all():
    """Save all persisted keys to disk."""
    if not _volume_available():
        return
    saved = []
    for key in PERSIST_KEYS:
        if key in st.session_state:
            save_key(key)
            saved.append(key)
    if saved:
        print(f"[persistence] Saved: {', '.join(saved)}")


def load_all():
    """Load all persisted data from disk into session state."""
    if not _volume_available():
        return
    if st.session_state.get("_persistence_loaded"):
        return

    loaded = []
    for key, data_type in PERSIST_KEYS.items():
        if key in st.session_state:
            continue  # Don't overwrite existing session data

        path = _file_path(key, data_type)
        if not os.path.exists(path):
            continue

        try:
            if data_type == "setting":
                with open(path, "r", encoding="utf-8") as f:
                    val = f.read().strip()
                if val:
                    st.session_state[key] = val
                    loaded.append(key)
            elif data_type == "dataframe":
                df = pd.read_csv(path)
                if not df.empty:
                    st.session_state[key] = df
                    loaded.append(key)
            elif data_type == "json":
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    st.session_state[key] = data
                    loaded.append(key)
        except Exception as e:
            print(f"[persistence] Failed to load {key}: {e}")

    st.session_state["_persistence_loaded"] = True
    if loaded:
        print(f"[persistence] Loaded: {', '.join(loaded)}")


def get_storage_info() -> dict:
    """Get info about what's stored on disk."""
    if not _volume_available():
        return {"available": False}

    files = {}
    for key, data_type in PERSIST_KEYS.items():
        path = _file_path(key, data_type)
        if os.path.exists(path):
            size = os.path.getsize(path)
            files[key] = {
                "size_mb": round(size / 1024 / 1024, 2),
                "path": path,
            }

    return {
        "available": True,
        "files": files,
        "total_mb": round(sum(f["size_mb"] for f in files.values()), 2),
    }
