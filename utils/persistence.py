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


def _normalize_json_urls(key: str, data):
    """Normalize URLs in JSON data loaded from disk."""
    from utils.ui_helpers import normalize_url
    # audit_results: list of dicts with "url" key
    if key == "audit_results" and isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "url" in item:
                item["url"] = normalize_url(item["url"])
    # topic_clusters: dict with "page_topics" keyed by URL
    elif key == "topic_clusters" and isinstance(data, dict):
        pt = data.get("page_topics", {})
        if pt:
            data["page_topics"] = {normalize_url(k): v for k, v in pt.items()}
        for cluster in data.get("clusters", []):
            for page in cluster.get("pages", []):
                if "page" in page:
                    page["page"] = normalize_url(page["page"])
    # sf_link_map: dict with URL-keyed sub-dicts
    elif key == "sf_link_map" and isinstance(data, dict):
        for sub_key in ("links_from", "links_to", "anchor_quality"):
            sub = data.get(sub_key, {})
            if sub and isinstance(sub, dict):
                data[sub_key] = {normalize_url(k): v for k, v in sub.items()}
    return data


def _normalize_df_urls(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize URL columns in DataFrames loaded from disk.
    Ensures old data (saved before normalization was added) is consistent."""
    from utils.ui_helpers import normalize_url
    url_cols = [c for c in df.columns if c in ("page", "url", "source", "target", "source_url", "target_url", "prev_page")]
    for col in url_cols:
        if df[col].dtype == object:  # Only string columns
            df[col] = df[col].apply(lambda x: normalize_url(str(x)) if pd.notna(x) else x)
    return df


# ── Bundled data: shipped as .gz in git, unpacked to /data on first run ──

BUNDLED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bundled_data")

# Map: gz filename -> (target path in /data, persist key, data type)
BUNDLED_FILES = {
    "sf_inlinks.csv.gz": ("sf_inlinks.csv", "sf_inlinks", "dataframe"),
    "sf_link_map.json.gz": ("sf_link_map.json", "sf_link_map", "json"),
    "sf_pages.csv.gz": ("sf_pages.csv", "sf_pages", "dataframe"),
    "ahrefs_best_by_links.csv.gz": ("ahrefs_best_by_links.csv", "ahrefs_best_by_links", "dataframe"),
    "ahrefs_backlinks.csv.gz": ("ahrefs_backlinks.csv", "ahrefs_backlinks", "dataframe"),
    "ahrefs_organic_keywords.csv.gz": ("ahrefs_organic_keywords.csv", "ahrefs_organic_keywords", "dataframe"),
}


def _unpack_bundled_data():
    """Decompress bundled .gz files to /data volume on first run."""
    if not _volume_available() or not os.path.isdir(BUNDLED_DIR):
        return

    import gzip
    unpacked = []
    for gz_name, (target_name, key, dtype) in BUNDLED_FILES.items():
        gz_path = os.path.join(BUNDLED_DIR, gz_name)
        target_path = os.path.join(DATA_DIR, target_name)

        # Skip if already unpacked or already loaded
        if os.path.exists(target_path) or key in st.session_state:
            continue
        if not os.path.exists(gz_path):
            continue

        try:
            print(f"[bundled] Unpacking {gz_name}...")
            with gzip.open(gz_path, "rb") as f_in:
                with open(target_path, "wb") as f_out:
                    # Stream in chunks to avoid memory spike
                    while True:
                        chunk = f_in.read(8 * 1024 * 1024)  # 8MB chunks
                        if not chunk:
                            break
                        f_out.write(chunk)

            size_mb = os.path.getsize(target_path) / (1024 * 1024)
            print(f"[bundled] Unpacked {target_name} ({size_mb:.1f} MB)")

            # Load into session state
            if dtype == "dataframe":
                df = pd.read_csv(target_path)
                if not df.empty:
                    df = _normalize_df_urls(df)
                    st.session_state[key] = df
                    unpacked.append(key)
            elif dtype == "json":
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    st.session_state[key] = data
                    unpacked.append(key)

        except Exception as e:
            print(f"[bundled] Failed {gz_name}: {e}")

    if unpacked:
        print(f"[bundled] Loaded from bundled data: {', '.join(unpacked)}")

        # If we loaded Ahrefs raw data, build page_authority
        if any(k.startswith("ahrefs_") for k in unpacked) and "page_authority" not in st.session_state:
            try:
                from utils.ahrefs_import import build_page_authority
                authority = build_page_authority(
                    best_by_links_df=st.session_state.get("ahrefs_best_by_links"),
                    backlinks_df=st.session_state.get("ahrefs_backlinks"),
                )
                st.session_state["page_authority"] = authority
                save("page_authority")
                print(f"[bundled] Built page_authority ({len(authority)} pages)")
            except Exception as e:
                print(f"[bundled] Failed to build authority: {e}")


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
    if key.startswith("_site") or key.startswith("_ideal") or key.startswith("_gap") or key.startswith("_plan_v"):
        print(f"[persistence] SAVED key={key} to {path} ({os.path.getsize(path)} bytes)")


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
                    # Normalize URL columns loaded from disk
                    df = _normalize_df_urls(df)
                    st.session_state[key] = df
                    loaded.append(key)
            elif data_type == "json":
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    data = _normalize_json_urls(key, data)
                    st.session_state[key] = data
                    loaded.append(key)
        except Exception as e:
            print(f"[load] Failed {key}: {e}")

    # Load AI cache — individual files
    ai_loaded = 0
    ai_keys_loaded = []
    if os.path.isdir(AI_CACHE_DIR):
        all_files = [f for f in os.listdir(AI_CACHE_DIR) if f.endswith(".json")]
        print(f"[persistence] AI cache dir has {len(all_files)} files")
        for fname in all_files:
            key = fname[:-5]  # remove .json
            if key in st.session_state:
                continue
            try:
                path = os.path.join(AI_CACHE_DIR, fname)
                with open(path, "r", encoding="utf-8") as f:
                    st.session_state[key] = json.load(f)
                ai_loaded += 1
                if key.startswith("_site") or key.startswith("_ideal") or key.startswith("_gap") or key.startswith("_plan_v"):
                    ai_keys_loaded.append(key)
            except Exception as e:
                print(f"[persistence] Failed to load {fname}: {e}")
    else:
        print(f"[persistence] AI cache dir does NOT exist: {AI_CACHE_DIR}")

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

    # ── Unpack bundled data (shipped in git as .gz) ─────────────
    _unpack_bundled_data()

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
