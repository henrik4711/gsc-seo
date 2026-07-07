"""
Persist ALL session state data to Railway volume (/data).
Simple approach: auto-save everything, auto-load on start.

AI results stored as individual files in /data/ai_cache/ directory
so we never lose partial results on crash.
"""

import os
import json
import pandas as pd

# Phase 1 of the NiceGUI migration: read/write the in-memory store through
# the framework-agnostic accessor instead of the Streamlit session directly.
# In Streamlit, state() returns the very same session object (app.py binds it
# at startup) so behaviour is identical; under NiceGUI it returns the
# per-client store. See NICEGUI_MIGRATION_PLAN.md.
from utils.state import state

DATA_DIR = "/data"
AI_CACHE_DIR = os.path.join(DATA_DIR, "ai_cache")

# Keys to persist and their types
PERSIST_KEYS = {
    # GSC foundation data
    "gsc_data": "dataframe",
    "gsc_site": "setting",
    "site_context": "setting",
    "content_language": "setting",
    "site_patterns": "json",  # per-site URL pattern overrides
    # Analysis results
    "ctr_gaps": "dataframe",
    "cannibalization": "dataframe_json",  # DataFrame with nested list cols → records JSON
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
    "ahrefs_organic_keywords": "dataframe",  # mshop's OWN organic keywords
    # Competitor keyword import + the unified keyword universe built from
    # GSC + own Ahrefs + brand-stripped competitor keywords. See
    # utils/keyword_universe.py. Raw upload is kept so the universe can be
    # rebuilt when GSC refreshes (resumable). competitor_meta records what
    # was uploaded (domain, brand terms, count) for the import screen.
    "ahrefs_competitor_keywords": "dataframe",   # flat, tagged (source/competitor)
    "competitor_meta": "json",
    "keyword_universe": "dataframe_json",        # nested list cols (competitors/sources)
    # AI generated
    "generated_content": "json",
    "action_plan": "json",
    # Cluster-based internal link recommendations (vertical + horizontal)
    "cluster_link_recommendations": "json",
    # Mshop admin API: which categories / CMS pages / filter pages are
    # active and editable, plus the URL→internal-id lookup needed for
    # per-page push of intro text + meta title + meta description.
    "mshop_active_pages": "json",
    # User-managed "I've handled this" flags per Site Cleanup action item.
    # Owned by utils/action_status.py — see that module for shape.
    "action_status": "json",
    # Re-check history: set of URLs already re-checked via "Re-check ALL
    # flagged pages" button. Stored as a list on disk (sorted), reloaded
    # as a list and converted to a set in the UI. Lets the button skip
    # work the user has already done — survives Railway redeploys that
    # would otherwise wipe session_state and force re-doing everything.
    "_recheck_history": "json",
    # Fix history: same idea but for the "Fix ALL flagged pages" batch
    # which generates AND pushes for every flagged URL. Persisted so a
    # Railway restart mid-run doesn't replay 300 already-fixed pages.
    "_fix_history": "json",
    # Per-URL failure counter for Fix ALL. Persisted so a page that
    # repeatedly crashes the batch (e.g. content too big, AI timeout)
    # gets auto-skipped after N failures instead of blocking the queue
    # forever. {url: count}. User can clear via the "🗑 Clear fix
    # history" button which also wipes failure counts.
    "_fix_failure_count": "json",
    # User-managed permanent skip list — URLs the user explicitly
    # never wants Fix ALL to touch (e.g. legacy pages they prefer to
    # keep as-is, manually-curated content). Persisted as a list,
    # used as a set in the UI for fast membership tests. Toggled per
    # page via the 🚫 Skip button on each AI Content Quality row.
    "_fix_skip_list": "json",
    # URLs the user explicitly says "don't need a cluster" — typically
    # blog/FAQ/help pages that don't fit any topic cluster. Removes
    # them from the Unclustered tab so the user only sees pages that
    # ACTUALLY need a cluster decision. Persisted as a list.
    "_no_cluster_needed": "json",
}

# Prefixes for dynamic AI cache keys — stored as individual files
AI_CACHE_PREFIXES = (
    "_quality_", "_ai_plan_", "_cluster_health_", "_kw_filter_",
    "impl_ai_", "link_ai_", "_gen_article_", "_rewrite_",
    "_bottom_text_", "_intro_text_", "art_outline_", "art_full_",
    "art_meta_", "kw_text_", "kw_intro_", "kw_faq_", "link_result_",
    "_site_validation", "_ideal_structure", "_gap_analysis", "_plan_validation",
    "_impl_plans_", "_structure_fix",
    # Content Freshness — single-file payload (one per run) with the
    # list of decaying pages + their decay metrics. Loaded at startup so
    # the view doesn't show "never run" after a Railway restart.
    "_decaying_pages",
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


def _read_csv_with_encoding_fallback(path: str) -> pd.DataFrame:
    """Read a CSV by auto-detecting BOTH encoding AND separator.

    Why: Ahrefs CSV exports default to UTF-16 with BOM and a TAB
    separator (Excel-friendly). SF Internal HTML / All Inlinks exports
    are UTF-8 with comma. Some Excel exports use semicolon. pandas
    defaults are UTF-8 + comma which fails on the Ahrefs case in two
    different ways:
      1. UnicodeDecodeError on 0xff (the UTF-16 BOM byte)
      2. After fixing encoding: ParserError because pandas reads the
         whole tab-separated line as a single field, then sees an
         unexpected delimiter further down

    Strategy:
      1. Iterate encodings, decode the first line to determine the
         likely separator (tab > semicolon-majority > comma)
      2. For each encoding × separator combo, try pd.read_csv with
         on_bad_lines='skip' and check the result has >1 column
      3. Return the first valid result. If none, re-raise the last
         exception so the caller sees a meaningful traceback.

    Order chosen so the cheapest correct match wins: SF/our own
    outputs are UTF-8 already, so try that first. utf-16 / utf-16-le
    catch Ahrefs. latin-1 / cp1252 catch the rare Windows-localized
    export.
    """
    encodings = ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "latin-1", "cp1252")
    last_err: Exception | None = None

    for enc in encodings:
        # Phase 1: decode the first line to detect a likely separator
        try:
            with open(path, "r", encoding=enc) as f:
                first_line = f.readline().lstrip("﻿")
        except (UnicodeDecodeError, UnicodeError) as e:
            last_err = e
            continue

        # Reorder the separator priority based on what the header
        # tells us (cheap heuristic — but if it's wrong we still
        # fall back to trying the others).
        if "\t" in first_line:
            sep_priority = ("\t", ",", ";")
        elif ";" in first_line and first_line.count(";") >= first_line.count(","):
            sep_priority = (";", ",", "\t")
        else:
            sep_priority = (",", "\t", ";")

        # Phase 2: try each separator with this encoding
        for sep in sep_priority:
            try:
                df = pd.read_csv(
                    path,
                    encoding=enc,
                    sep=sep,
                    on_bad_lines="skip",
                    engine="python",  # tolerates more variation than C engine
                )
                if len(df.columns) > 1:
                    return df
                # Single-column result almost always means we picked
                # the wrong separator. Don't return — try next sep.
            except (pd.errors.ParserError, UnicodeDecodeError, UnicodeError) as e:
                last_err = e
                continue

    raise last_err or ValueError(
        f"Could not parse {path} as CSV with any encoding × separator combo "
        f"({', '.join(encodings)} × tab/comma/semicolon)"
    )


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

# Map: logical key -> (gz basename, csv basename, persist session key, data type)
#
# Naming convention: each bundled file MUST be suffixed with the site code
# (se/dk/eu/...) so multi-shop deployments load only their own crawl +
# backlink data. Example: bundled_data/sf_pages_se.csv.gz, NOT
# bundled_data/sf_pages.csv.gz. The site code comes from the SITE_CODE
# env var on each Railway service (set it to 'se', 'dk', 'eu', etc.).
#
# Without SITE_CODE set, _unpack_bundled_data() falls back to the legacy
# unsuffixed filenames for backwards compatibility, but emits a warning.
# Once all services have SITE_CODE configured, the legacy filenames can
# be removed.
BUNDLED_FILES = {
    "sf_inlinks":              ("sf_inlinks",          ".csv.gz",  "sf_inlinks.csv",          "sf_inlinks",              "dataframe"),
    "sf_link_map":             ("sf_link_map",         ".json.gz", "sf_link_map.json",        "sf_link_map",             "json"),
    "sf_pages":                ("sf_pages",            ".csv.gz",  "sf_pages.csv",            "sf_pages",                "dataframe"),
    "ahrefs_best_by_links":    ("ahrefs_best_by_links",".csv.gz",  "ahrefs_best_by_links.csv","ahrefs_best_by_links",    "dataframe"),
    "ahrefs_backlinks":        ("ahrefs_backlinks",    ".csv.gz",  "ahrefs_backlinks.csv",    "ahrefs_backlinks",        "dataframe"),
    "ahrefs_organic_keywords": ("ahrefs_organic_keywords",".csv.gz","ahrefs_organic_keywords.csv","ahrefs_organic_keywords","dataframe"),
}


# For raw vendor CSV exports (Ahrefs, SF), generic pd.read_csv loads
# data but leaves column names in vendor format ("Target URL",
# "Referring page URL", "Address", "H1-1" etc.). Downstream consumers
# like build_page_authority expect canonical names ("target_url",
# "source_url", "url", "h1") — produced by the specific parsers below.
#
# Maps each logical bundled-file key to its parser function. When set,
# _unpack_bundled_data routes the file through the parser instead of
# the generic CSV reader. The parser handles encoding + separator
# detection AND column normalization in one pass.
#
# sf_inlinks is intentionally absent: prepare_inlinks.py already runs
# parse_all_inlinks during prep, so the bundled CSV is canonical and
# re-parsing would just waste 30+s of dedup work.
BUNDLED_DATAFRAME_PARSERS: dict = {
    "sf_pages":                "ahrefs_import._sf_pages",  # placeholder; resolved below
    "ahrefs_best_by_links":    "ahrefs_best_by_links",
    "ahrefs_backlinks":        "ahrefs_backlinks",
    "ahrefs_organic_keywords": "ahrefs_organic_keywords",
}


def _resolve_bundled_parser(logical_key: str):
    """Lazily import and return the parser callable for a bundled-file
    logical key, or None if no parser is registered.

    Lazy import keeps utils.persistence from carrying screaming_frog +
    ahrefs imports at module load time — those modules pull in pandas
    + bs4 + regex chains that aren't needed when persistence is just
    saving JSON or settings.
    """
    if logical_key == "sf_pages":
        from utils.screaming_frog_import import parse_all_pages
        return parse_all_pages
    if logical_key == "ahrefs_best_by_links":
        from utils.ahrefs_import import parse_best_by_links
        return parse_best_by_links
    if logical_key == "ahrefs_backlinks":
        from utils.ahrefs_import import parse_backlinks
        return parse_backlinks
    if logical_key == "ahrefs_organic_keywords":
        from utils.ahrefs_import import parse_organic_keywords
        return parse_organic_keywords
    return None


def _site_code() -> str:
    """Resolve current shop's site code from env var. Returns lowercase
    string ('se', 'dk', 'eu'...) or '' if unset."""
    return os.environ.get("SITE_CODE", "").strip().lower()


def _resolve_bundled_path(stem: str, ext: str) -> str | None:
    """Return the path to the bundled file this service should load, or
    None if no suitable file exists.

    Resolution:
    1. SITE_CODE env var picks the suffix. If unset, defaults to 'se'
       so existing mshop.se deploys (which haven't yet had SITE_CODE
       added in Railway) keep working — with a one-line warning so the
       user notices and sets it explicitly.
    2. Look for bundled_data/<stem>_<site_code><ext> — that's the shop-
       specific file.
    3. SE-only fallback to legacy unsuffixed name bundled_data/<stem><ext>
       so any deploy still pointing at the pre-rename files keeps loading
       them. Other shops get NO fallback — they refuse to load SE-suffixed
       or unsuffixed files to prevent contamination.
    """
    site = _site_code()
    if not site:
        print(
            "[bundled] WARN: SITE_CODE env var not set — defaulting to 'se'. "
            "Set SITE_CODE=se|dk|eu|... explicitly on each Railway service."
        )
        site = "se"

    # Primary: shop-specific suffix
    site_path = os.path.join(BUNDLED_DIR, f"{stem}_{site}{ext}")
    if os.path.exists(site_path):
        return site_path

    # SE-only legacy fallback for the pre-rename world. Anything else
    # finding only unsuffixed files means the dataset is wrong for this
    # site — refuse to load (SE data contamination risk).
    if site == "se":
        legacy_path = os.path.join(BUNDLED_DIR, f"{stem}{ext}")
        if os.path.exists(legacy_path):
            print(f"[bundled] Loading legacy {stem}{ext} — rename to {stem}_se{ext} to silence.")
            return legacy_path

    return None


def _load_bundled_dataframe(logical_key: str, target_path: str) -> pd.DataFrame:
    """Load a bundled-data CSV into a canonical-column DataFrame.

    Routes raw vendor CSV exports (Ahrefs, SF) through their specific
    parsers so column names come out in the canonical form downstream
    consumers expect ("target_url", "source_url", "url", "h1" etc.).
    Falls back to the generic encoding+sep-aware reader for files
    that are already canonical (sf_inlinks output from prepare_inlinks).

    The parser dispatch is what build_page_authority needed: without
    it, ahrefs_backlinks loaded with "Target URL" column and the
    derivation crashed with KeyError: 'target_url'.

    Pass file BYTES to the parser (it accepts either bytes or a file-
    like with .read()). We read the file fresh each call rather than
    pass the path because the parsers don't accept paths directly.
    """
    parser = _resolve_bundled_parser(logical_key)
    if parser is None:
        # No parser registered — file is already canonical (e.g.
        # sf_inlinks deduped output from prepare_inlinks.py).
        return _read_csv_with_encoding_fallback(target_path)

    with open(target_path, "rb") as f:
        file_bytes = f.read()
    df = parser(file_bytes)
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _unpack_bundled_data():
    """Decompress bundled .gz files to /data volume on first run.

    Multi-shop aware: only loads files matching this service's SITE_CODE
    env var (see _resolve_bundled_path for resolution rules).

    Returns a result dict so the caller (e.g. the Refresh-bundled-data
    button in views/setup.py) can surface per-file errors to the UI
    instead of relying on Railway logs:

        {
          "loaded":  ["sf_inlinks", "sf_link_map", ...],
          "errors":  [{"key": "...", "stage": "unpack|load",
                       "msg": "..."}],
          "skipped": [{"key": "...", "reason": "..."}],
        }

    Existing callers that ignore the return value (load_all) keep
    working unchanged.
    """
    result = {"loaded": [], "errors": [], "skipped": []}

    if not _volume_available() or not os.path.isdir(BUNDLED_DIR):
        result["skipped"].append({"key": "(all)",
                                    "reason": "no /data volume or bundled dir"})
        return result

    import gzip
    import traceback as _tb
    for logical_key, (stem, ext, target_name, key, dtype) in BUNDLED_FILES.items():
        gz_path = _resolve_bundled_path(stem, ext)
        target_path = os.path.join(DATA_DIR, target_name)

        # Skip if already unpacked or already loaded
        if os.path.exists(target_path) and key in state():
            result["skipped"].append({"key": logical_key,
                                        "reason": "already unpacked + in session"})
            continue
        if os.path.exists(target_path) and key not in state():
            # Stale unpack from a previous boot — load it into session
            # without re-unpacking, then fall through to next iteration.
            try:
                if dtype == "dataframe":
                    df = _load_bundled_dataframe(logical_key, target_path)
                    if not df.empty:
                        df = _normalize_df_urls(df)
                        state()[key] = df
                        result["loaded"].append(logical_key)
                        print(f"[bundled] Loaded stale unpack {target_name}")
                elif dtype == "json":
                    with open(target_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data:
                        state()[key] = data
                        result["loaded"].append(logical_key)
                        print(f"[bundled] Loaded stale unpack {target_name}")
                continue
            except Exception as e:
                # Stale file is corrupt — delete and fall through to
                # re-unpack below.
                print(f"[bundled] Stale {target_name} corrupt, removing: {e}")
                try:
                    os.remove(target_path)
                except Exception:
                    pass
                # do NOT continue — fall through to fresh unpack
        if gz_path is None or not os.path.exists(gz_path):
            result["skipped"].append({"key": logical_key,
                                        "reason": "no bundled .gz for this SITE_CODE"})
            continue

        # ── Fresh unpack ────────────────────────────────────────
        try:
            print(f"[bundled] Unpacking {logical_key} from {os.path.basename(gz_path)}...")
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
        except Exception as e:
            err = f"unpack: {type(e).__name__}: {e}"
            print(f"[bundled] Failed {logical_key} during unpack: {err}")
            print(_tb.format_exc())
            result["errors"].append({"key": logical_key, "stage": "unpack",
                                        "msg": err})
            # Also report via the central errors system so the failure
            # appears in the global System Messages panel — important
            # because load_all() runs at boot and bypasses the Refresh
            # button's result dict surfacing.
            try:
                from utils.errors import report_error
                report_error(stage="bundled_unpack", key=logical_key, error=e)
            except Exception:
                pass
            # Remove partial target so retry can start clean
            try:
                if os.path.exists(target_path):
                    os.remove(target_path)
            except Exception:
                pass
            continue

        # ── Load into session state ─────────────────────────────
        try:
            if dtype == "dataframe":
                df = _load_bundled_dataframe(logical_key, target_path)
                if not df.empty:
                    df = _normalize_df_urls(df)
                    state()[key] = df
                    result["loaded"].append(logical_key)
                else:
                    result["errors"].append({"key": logical_key, "stage": "load",
                                                "msg": "CSV parsed as empty DataFrame"})
            elif dtype == "json":
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    state()[key] = data
                    result["loaded"].append(logical_key)
                else:
                    result["errors"].append({"key": logical_key, "stage": "load",
                                                "msg": "JSON parsed as empty"})
        except MemoryError as e:
            err = f"load: MemoryError reading {target_name} ({os.path.getsize(target_path) / (1024 * 1024):.0f} MB CSV/JSON) — Railway memory tier too small for this dataset"
            print(f"[bundled] Failed {logical_key} during load: {err}")
            result["errors"].append({"key": logical_key, "stage": "load", "msg": err})
            try:
                from utils.errors import report_error
                report_error(stage="bundled_load", key=logical_key, error=e,
                             message=err)
            except Exception:
                pass
            # Keep the unpacked file on disk; the issue is memory not data
        except Exception as e:
            err = f"load: {type(e).__name__}: {e}"
            print(f"[bundled] Failed {logical_key} during load: {err}")
            print(_tb.format_exc())
            result["errors"].append({"key": logical_key, "stage": "load",
                                        "msg": err})
            try:
                from utils.errors import report_error
                report_error(stage="bundled_load", key=logical_key, error=e)
            except Exception:
                pass
            # Remove the corrupt unpack so retry can start clean
            try:
                if os.path.exists(target_path):
                    os.remove(target_path)
            except Exception:
                pass

    if result["loaded"]:
        print(f"[bundled] Loaded from bundled data: {', '.join(result['loaded'])}")

        # If we loaded Ahrefs raw data, build page_authority
        if any(k.startswith("ahrefs_") for k in result["loaded"]) and "page_authority" not in state():
            try:
                from utils.ahrefs_import import build_page_authority
                authority = build_page_authority(
                    best_by_links_df=state().get("ahrefs_best_by_links"),
                    backlinks_df=state().get("ahrefs_backlinks"),
                )
                state()["page_authority"] = authority
                save("page_authority")
                print(f"[bundled] Built page_authority ({len(authority)} pages)")
            except Exception as e:
                print(f"[bundled] Failed to build authority: {e}")
                result["errors"].append({"key": "page_authority", "stage": "derive",
                                            "msg": f"{type(e).__name__}: {e}"})

    return result


def _file_path(key: str, data_type: str) -> str:
    if data_type == "dataframe":
        ext = "csv"
    elif data_type == "setting":
        ext = "txt"
    else:  # "json" or "dataframe_json"
        ext = "json"
    return os.path.join(DATA_DIR, f"{key}.{ext}")


def _is_ai_key(key: str) -> bool:
    return any(key.startswith(p) for p in AI_CACHE_PREFIXES)


# ── SAVE functions ────────────────────────────────────────────────

def save(key: str, value=None):
    """Save a single key to session state + disk. The ONE function to use everywhere."""
    if value is not None:
        state()[key] = value
    elif key not in state():
        return

    if not _volume_available():
        return

    data = state()[key]

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
    elif data_type == "dataframe_json":
        # DataFrame with nested list/dict columns — preserve them via records JSON
        if isinstance(data, pd.DataFrame):
            records = data.to_dict("records")
        else:
            records = data
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=1, default=_json_convert)
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
    for key in list(state().keys()):
        if _is_ai_key(key) and state()[key] is not None:
            try:
                _save_ai_key(key, state()[key])
                count += 1
            except Exception as e:
                # Was a silent pass — now surfaces in the UI so the
                # operator knows their cached AI work isn't safely on
                # disk. Without this, a successful "Bulk audit complete"
                # toast can be followed by losing N AI verdicts on the
                # next Railway restart with zero indication.
                try:
                    from utils.errors import report_error
                    report_error(stage="save_ai_cache", key=key, error=e)
                except Exception:
                    print(f"[save_ai_cache] Failed {key}: {e}", file=__import__("sys").stderr)
    if count:
        print(f"[persistence] AI cache saved: {count} items")


def save_all():
    """Save everything to disk."""
    if not _volume_available():
        return
    for key in PERSIST_KEYS:
        if key in state():
            try:
                _save_persist_key(key, state()[key])
            except Exception as e:
                # Was stdout-only; now goes to the central reporter so
                # the operator sees disk-write failures in the UI. Losing
                # gsc_data or audit_results on save is silent corruption
                # otherwise — operator restarts Railway and the work is gone.
                try:
                    from utils.errors import report_error
                    report_error(stage="save_all", key=key, error=e)
                except Exception:
                    print(f"[save_all] Failed {key}: {e}", file=__import__("sys").stderr)
    save_ai_cache()


# ── LOAD functions ────────────────────────────────────────────────

def load_all():
    """Load everything from disk into session state."""
    if not _volume_available():
        return
    if state().get("_persistence_loaded"):
        return

    loaded = []

    # Load regular persist keys
    for key, data_type in PERSIST_KEYS.items():
        if key in state():
            continue
        path = _file_path(key, data_type)
        if not os.path.exists(path):
            continue
        try:
            if data_type == "setting":
                with open(path, "r", encoding="utf-8") as f:
                    val = f.read().strip()
                if val:
                    state()[key] = val
                    loaded.append(key)
            elif data_type == "dataframe":
                # Use the encoding+separator-aware reader so legacy
                # files saved in non-UTF-8 / non-comma formats load
                # without silently failing.
                df = _read_csv_with_encoding_fallback(path)
                if not df.empty:
                    # Normalize URL columns loaded from disk
                    df = _normalize_df_urls(df)
                    state()[key] = df
                    loaded.append(key)
            elif data_type == "dataframe_json":
                with open(path, "r", encoding="utf-8") as f:
                    records = json.load(f)
                if records:
                    df = pd.DataFrame(records)
                    if not df.empty:
                        df = _normalize_df_urls(df)
                        state()[key] = df
                        loaded.append(key)
            elif data_type == "json":
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    data = _normalize_json_urls(key, data)
                    state()[key] = data
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
            if key in state():
                continue
            try:
                path = os.path.join(AI_CACHE_DIR, fname)
                with open(path, "r", encoding="utf-8") as f:
                    state()[key] = json.load(f)
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
                if key not in state():
                    state()[key] = val
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

    # ── Auto-invalidate stale shop-specific caches ───────────────
    # mshop_active_pages can carry URLs for the WRONG shop if it was
    # synced before the storeId fix landed. Self-heal by discarding
    # any cache whose URLs don't match SITE_CODE — the next bulk audit
    # will then auto-sync against the correct shop.
    _validate_and_clean_shop_caches()

    state()["_persistence_loaded"] = True
    if loaded:
        print(f"[persistence] Loaded: {', '.join(loaded)}")
    if ai_loaded:
        print(f"[persistence] AI cache loaded: {ai_loaded} items")


# ── Shop-specific cache validation ────────────────────────────────


def _validate_and_clean_shop_caches() -> None:
    """Discard cached shop-specific data that doesn't match this service's
    SITE_CODE. Called during load_all so stale cross-shop contamination
    self-heals at boot — no manual RESET ALL DATA required.

    Currently covers:
      - mshop_active_pages: 50% of URLs must contain the expected domain
        for SITE_CODE; otherwise the cache is wiped from session_state
        AND from /data, and the operator is notified via report_error.

    audit_results is NOT validated here because it can legitimately
    contain URLs from various sources (manual audits of specific pages,
    legacy imports). If audit_results contamination becomes an issue
    we'll add a similar check that flags rather than auto-wipes.
    """
    cache = state().get("mshop_active_pages")
    if not cache:
        return
    try:
        from utils.mshop_admin_api import validate_active_pages_match_site
    except Exception:
        return  # mshop_admin_api not importable — skip silently
    is_valid, reason = validate_active_pages_match_site(cache)
    if is_valid:
        return

    # Surface in the System Messages panel so the operator knows the
    # cache was auto-wiped and why
    try:
        from utils.errors import report_error
        report_error(
            stage="mshop_active_pages_validation",
            key="mshop_active_pages",
            message=reason,
            severity="warning",
        )
    except Exception:
        pass

    # Wipe from session and disk so next bulk audit triggers a fresh
    # sync against the correct shop
    state().pop("mshop_active_pages", None)
    target_path = _file_path("mshop_active_pages", "json") if _volume_available() else ""
    if target_path and os.path.exists(target_path):
        try:
            os.remove(target_path)
        except Exception as e:
            try:
                from utils.errors import report_error
                report_error(
                    stage="mshop_active_pages_validation",
                    key="mshop_active_pages",
                    error=e,
                    message=f"Could not delete stale {target_path}: {e}",
                )
            except Exception:
                pass


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
