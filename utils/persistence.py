"""
Persist ALL session state data to Railway volume (/data).
Simple approach: auto-save everything, auto-load on start.

AI results stored as individual files in /data/ai_cache/ directory
so we never lose partial results on crash.
"""

import os
import json
import streamlit as st
import pandas as pd

DATA_DIR = "/data"
AI_CACHE_DIR = os.path.join(DATA_DIR, "ai_cache")

# Keys to persist and their types
PERSIST_KEYS = {
    # GSC foundation data
    "gsc_data": "dataframe",
    "gsc_site": "setting",
    "site_context": "setting",
    "content_language": "setting",
    # Analysis results
    "ctr_gaps": "dataframe",
    "cannibalization": "json",
    "topic_clusters": "json",
    "content_roadmap": "json",
    "content_gaps": "json",
    # Audit
    "audit_results": "json",
    # Screaming Frog
    "sf_pages": "dataframe",
    "sf_inlinks": "dataframe",
    "sf_link_map": "json",
    "sf_crawl_issues": "json",
    # Ahrefs
    "page_authority": "dataframe",
    "ahrefs_best_by_links": "dataframe",
    "ahrefs_backlinks": "dataframe",
    "ahrefs_organic_keywords": "dataframe",
    # AI generated
    "generated_content": "json",
    "action_plan": "json",
}

# Prefixes for dynamic AI cache keys — stored as individual files
AI_CACHE_PREFIXES = (
    "_quality_", "_ai_plan_", "_cluster_health_", "_kw_filter_",
    "impl_ai_", "link_ai_", "_gen_article_", "_rewrite_",
    "_bottom_text_", "_intro_text_", "art_outline_", "art_full_",
    "art_meta_", "kw_text_", "kw_intro_", "kw_faq_", "link_result_",
    "_site_validation", "_ideal_structure", "_gap_analysis", "_plan_validation",
    "_impl_plans_",
)


def _json_convert(obj):
    """Convert non-serializable types for JSON."""
    if hasattr(obj, 'item'):
        return obj.item()
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    raise TypeError(f"Type {type(obj)}")


def _volume_available() -> bool:
    return os.path.isdir(DATA_DIR)


def _file_path(key: str, data_type: str) -> str:
    ext = "csv" if data_type == "dataframe" else ("txt" if data_type == "setting" else "json")
    return os.path.join(DATA_DIR, f"{key}.{ext}")


def _is_ai_key(key: str) -> bool:
    return any(key.startswith(p) for p in AI_CACHE_PREFIXES)


# ── SAVE functions ────────────────────────────────────────────────

def save(key: str, value=None):
    """Save a single key to session state + disk. The ONE function to use everywhere."""
    if value is not None:
        st.session_state[key] = value
    elif key not in st.session_state:
        return

    if not _volume_available():
        return

    data = st.session_state[key]

    try:
        if _is_ai_key(key):
            _save_ai_key(key, data)
        elif key in PERSIST_KEYS:
            _save_persist_key(key, data)
    except Exception as e:
        print(f"[save] Failed {key}: {e}")


def _save_persist_key(key: str, data):
    """Save a regular persist key to disk."""
    data_type = PERSIST_KEYS[key]
    path = _file_path(key, data_type)

    if data_type == "setting":
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(data))
    elif data_type == "dataframe" and isinstance(data, pd.DataFrame):
        data.to_csv(path, index=False)
    elif data_type == "json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, default=_json_convert)


def _save_ai_key(key: str, data):
    """Save a single AI result as individual file."""
    os.makedirs(AI_CACHE_DIR, exist_ok=True)
    path = os.path.join(AI_CACHE_DIR, f"{key}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, default=_json_convert)


# ── Backwards compatible aliases ──────────────────────────────────

def save_key(key: str):
    """Save a single persist key. Alias for save()."""
    save(key)


def save_ai_cache():
    """Save all AI results to individual files."""
    if not _volume_available():
        return
    os.makedirs(AI_CACHE_DIR, exist_ok=True)
    count = 0
    for key in list(st.session_state.keys()):
        if _is_ai_key(key) and st.session_state[key] is not None:
            try:
                _save_ai_key(key, st.session_state[key])
                count += 1
            except Exception:
                pass
    if count:
        print(f"[persistence] AI cache saved: {count} items")


def save_all():
    """Save everything to disk."""
    if not _volume_available():
        return
    for key in PERSIST_KEYS:
        if key in st.session_state:
            try:
                _save_persist_key(key, st.session_state[key])
            except Exception as e:
                print(f"[save_all] Failed {key}: {e}")
    save_ai_cache()


# ── LOAD functions ────────────────────────────────────────────────

def load_all():
    """Load everything from disk into session state."""
    if not _volume_available():
        return
    if st.session_state.get("_persistence_loaded"):
        return

    loaded = []

    # Load regular persist keys
    for key, data_type in PERSIST_KEYS.items():
        if key in st.session_state:
            continue
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
            print(f"[load] Failed {key}: {e}")

    # Load AI cache — individual files
    ai_loaded = 0
    if os.path.isdir(AI_CACHE_DIR):
        for fname in os.listdir(AI_CACHE_DIR):
            if not fname.endswith(".json"):
                continue
            key = fname[:-5]  # remove .json
            if key in st.session_state:
                continue
            try:
                path = os.path.join(AI_CACHE_DIR, fname)
                with open(path, "r", encoding="utf-8") as f:
                    st.session_state[key] = json.load(f)
                ai_loaded += 1
            except Exception:
                pass

    # Backwards compat: load old single ai_cache.json if it exists
    old_cache = os.path.join(DATA_DIR, "ai_cache.json")
    if os.path.exists(old_cache):
        try:
            with open(old_cache, "r", encoding="utf-8") as f:
                cache = json.load(f)
            for key, val in cache.items():
                if key not in st.session_state:
                    st.session_state[key] = val
                    # Migrate to individual file
                    try:
                        _save_ai_key(key, val)
                    except Exception:
                        pass
                    ai_loaded += 1
            # Remove old file after migration
            os.remove(old_cache)
            print("[persistence] Migrated ai_cache.json to individual files")
        except Exception:
            pass

    st.session_state["_persistence_loaded"] = True
    if loaded:
        print(f"[persistence] Loaded: {', '.join(loaded)}")
    if ai_loaded:
        print(f"[persistence] AI cache loaded: {ai_loaded} items")


# ── Utility ───────────────────────────────────────────────────────

def get_storage_info() -> dict:
    """Get info about what's stored on disk."""
    if not _volume_available():
        return {"available": False}

    files = {}
    total_size = 0

    for key, data_type in PERSIST_KEYS.items():
        path = _file_path(key, data_type)
        if os.path.exists(path):
            size = os.path.getsize(path)
            files[key] = {"size_mb": round(size / 1024 / 1024, 2)}
            total_size += size

    # AI cache files
    ai_count = 0
    ai_size = 0
    if os.path.isdir(AI_CACHE_DIR):
        for fname in os.listdir(AI_CACHE_DIR):
            fpath = os.path.join(AI_CACHE_DIR, fname)
            ai_count += 1
            ai_size += os.path.getsize(fpath)

    files["ai_cache"] = {"size_mb": round(ai_size / 1024 / 1024, 2), "count": ai_count}
    total_size += ai_size

    return {
        "available": True,
        "files": files,
        "total_mb": round(total_size / 1024 / 1024, 2),
    }
