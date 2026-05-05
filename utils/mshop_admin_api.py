"""
Client for the Mshop Admin API — fetch active pages and update meta /
intro / description fields on categories, CMS pages, and filter pages.

Required Railway env vars (same credentials as bottom-text push):
  FOOTER_TEXT_API_USER  — Basic auth username
  FOOTER_TEXT_API_PASS  — Basic auth password
  FOOTER_TEXT_STORE_ID  — integer store ID (used for category texts updates)
  MSHOP_ADMIN_API_BASE  — base URL, e.g. https://www.mshop.se/public-api
                         (optional — derived from FOOTER_TEXT_API if absent)

The three list endpoints return all currently active and editable pages.
We fetch them once and cache the URL → (type, id, …) mapping in
session_state and on disk so per-page push buttons can resolve a URL
to its internal id without a fresh round-trip every click.
"""

import os
import json
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import requests

TIMEOUT_SECONDS = 30
DATA_DIR = "/data"
SYNC_LOG_PATH = os.path.join(DATA_DIR, "mshop_admin_sync_log.json")
PUSH_LOG_PATH = os.path.join(DATA_DIR, "mshop_admin_push_log.json")


# ── Config ─────────────────────────────────────────────────────────

def _api_base() -> str:
    """Resolve the admin API base URL.
    Prefers MSHOP_ADMIN_API_BASE; falls back to deriving from FOOTER_TEXT_API
    by stripping the path suffix and inserting /public-api."""
    base = os.environ.get("MSHOP_ADMIN_API_BASE", "").strip().rstrip("/")
    if base:
        return base
    footer = os.environ.get("FOOTER_TEXT_API", "").strip()
    if footer:
        try:
            p = urlparse(footer)
            return f"{p.scheme}://{p.netloc}/public-api"
        except Exception:
            pass
    return ""


def _credentials() -> tuple[str, str]:
    return (
        os.environ.get("FOOTER_TEXT_API_USER", "").strip(),
        os.environ.get("FOOTER_TEXT_API_PASS", "").strip(),
    )


def _store_id() -> int:
    raw = os.environ.get("FOOTER_TEXT_STORE_ID", "").strip()
    try:
        return int(raw) if raw else 0
    except ValueError:
        return 0


def _config_check() -> Optional[str]:
    """Return an error string if config is incomplete, None if OK."""
    base = _api_base()
    user, pwd = _credentials()
    if not base:
        return "MSHOP_ADMIN_API_BASE not set (or FOOTER_TEXT_API not set to derive from)."
    if not user or not pwd:
        return "FOOTER_TEXT_API_USER / FOOTER_TEXT_API_PASS env vars not set."
    return None


# ── URL normalisation ──────────────────────────────────────────────

def _normalize_for_lookup(u: str) -> str:
    """Drop scheme, www, query, fragment, trailing slash; lowercase. Used
    so 'https://www.mshop.se/foo/' and 'https://mshop.se/foo' both resolve
    to the same key in the cached lookup map."""
    if not u:
        return ""
    s = str(u).strip().lower()
    if s.startswith("http://"):
        s = s[7:]
    elif s.startswith("https://"):
        s = s[8:]
    if s.startswith("www."):
        s = s[4:]
    s = s.split("?", 1)[0].split("#", 1)[0]
    return s.rstrip("/")


# ── List fetchers ──────────────────────────────────────────────────

def _get_list(endpoint: str) -> dict:
    err = _config_check()
    if err:
        return {"status": "error", "error": err, "items": []}
    base = _api_base()
    user, pwd = _credentials()
    url = f"{base}/{endpoint.lstrip('/')}"
    try:
        resp = requests.get(url, auth=(user, pwd), timeout=TIMEOUT_SECONDS)
    except requests.Timeout:
        return {"status": "timeout", "error": f"Timeout after {TIMEOUT_SECONDS}s", "items": []}
    except Exception as e:
        return {"status": "network_error", "error": str(e), "items": []}
    if resp.status_code != 200:
        return {
            "status": "http_error",
            "error": f"HTTP {resp.status_code}",
            "http_code": resp.status_code,
            "response_body": (resp.text or "")[:2000],
            "items": [],
        }
    try:
        body = resp.json()
    except Exception as e:
        return {"status": "error", "error": f"Invalid JSON: {e}", "items": []}
    items = body.get("payload") or []
    if not isinstance(items, list):
        items = []
    return {
        "status": "success",
        "http_code": resp.status_code,
        "items": items,
    }


def fetch_categories() -> dict:
    return _get_list("catalog/category/list")


def fetch_cms_pages() -> dict:
    return _get_list("cms/page/list")


def fetch_filter_pages() -> dict:
    return _get_list("catalog/filterpage/list")


def fetch_active_pages_all() -> dict:
    """Fetch all three lists and return a combined lookup dict.

    Returns:
        {
          "status": "success" | "partial" | "error",
          "errors": [...],
          "lookup": {normalized_url: {"type": "category|cms|filterpage",
                                       "id": int, "name": str,
                                       "url": str, "metaTitle": str,
                                       "metaDescription": str,
                                       "description": str (cat/filterpage),
                                       "categoryId": int (filterpage),
                                       "parentId": int (category)}},
          "counts": {"category": N, "cms": N, "filterpage": N},
          "fetched_at": iso8601 string,
        }
    """
    cats = fetch_categories()
    cms = fetch_cms_pages()
    fps = fetch_filter_pages()
    errors = []
    lookup: dict = {}

    if cats.get("status") == "success":
        for c in cats.get("items", []):
            u = _normalize_for_lookup(c.get("url", ""))
            if not u:
                continue
            lookup[u] = {
                "type": "category",
                "id": c.get("id"),
                "name": c.get("name", ""),
                "url": c.get("url", ""),
                "metaTitle": c.get("metaTitle", "") or "",
                "metaDescription": c.get("metaDescription", "") or "",
                "description": c.get("description", "") or "",
                "parentId": c.get("parentId"),
                "path": c.get("path", ""),
            }
    else:
        errors.append(f"categories: {cats.get('error')}")

    if cms.get("status") == "success":
        for p in cms.get("items", []):
            u = _normalize_for_lookup(p.get("url", ""))
            if not u:
                continue
            # Don't overwrite if a category already claimed this URL —
            # categories take precedence.
            if u in lookup:
                continue
            lookup[u] = {
                "type": "cms",
                "id": p.get("id"),
                "name": p.get("name", "") or p.get("url", ""),
                "url": p.get("url", ""),
                "metaTitle": p.get("metaTitle", "") or "",
                "metaDescription": p.get("metaDescription", "") or "",
            }
    else:
        errors.append(f"cms pages: {cms.get('error')}")

    if fps.get("status") == "success":
        for f in fps.get("items", []):
            u = _normalize_for_lookup(f.get("url", ""))
            if not u or u in lookup:
                continue
            lookup[u] = {
                "type": "filterpage",
                "id": f.get("id"),
                "name": f.get("name", ""),
                "url": f.get("url", ""),
                "metaTitle": f.get("metaTitle", "") or "",
                "metaDescription": f.get("metaDescription", "") or "",
                "description": f.get("description", "") or "",
                "categoryId": f.get("categoryId"),
            }
    else:
        errors.append(f"filter pages: {fps.get('error')}")

    counts = {
        "category": sum(1 for v in lookup.values() if v["type"] == "category"),
        "cms": sum(1 for v in lookup.values() if v["type"] == "cms"),
        "filterpage": sum(1 for v in lookup.values() if v["type"] == "filterpage"),
    }
    if errors and not lookup:
        status = "error"
    elif errors:
        status = "partial"
    else:
        status = "success"
    result = {
        "status": status,
        "errors": errors,
        "lookup": lookup,
        "counts": counts,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
    }
    _append_log(SYNC_LOG_PATH, {
        "timestamp": result["fetched_at"],
        "status": status,
        "counts": counts,
        "errors": errors,
    })
    return result


def lookup_url(active_pages: dict, url: str) -> Optional[dict]:
    """Resolve a URL against a previously-fetched active pages lookup."""
    if not active_pages or not url:
        return None
    table = active_pages.get("lookup") if isinstance(active_pages, dict) else None
    if not isinstance(table, dict):
        return None
    return table.get(_normalize_for_lookup(url))


# ── Update endpoints ───────────────────────────────────────────────

def _post_update(endpoint: str, payload: dict) -> dict:
    err = _config_check()
    if err:
        return {"status": "error", "error": err, "payload": payload}
    base = _api_base()
    user, pwd = _credentials()
    url = f"{base}/{endpoint.lstrip('/')}"
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "endpoint": endpoint,
        "payload": payload,
        "status": None,
        "http_code": None,
        "response_body": None,
        "error": None,
    }
    try:
        resp = requests.post(
            url,
            json=payload,
            auth=(user, pwd),
            timeout=TIMEOUT_SECONDS,
            headers={"Content-Type": "application/json"},
        )
        entry["http_code"] = resp.status_code
        entry["response_body"] = (resp.text or "")[:5000]
        if 200 <= resp.status_code < 300:
            entry["status"] = "success"
            result = {
                "status": "success",
                "http_code": resp.status_code,
                "response_body": resp.text,
                "payload": payload,
                "error": None,
            }
        else:
            entry["status"] = "http_error"
            entry["error"] = f"HTTP {resp.status_code}"
            result = {
                "status": "http_error",
                "http_code": resp.status_code,
                "response_body": resp.text,
                "payload": payload,
                "error": entry["error"],
            }
    except requests.Timeout:
        entry["status"] = "timeout"
        entry["error"] = f"Timeout after {TIMEOUT_SECONDS}s"
        result = {"status": "timeout", "error": entry["error"], "payload": payload}
    except Exception as e:
        entry["status"] = "network_error"
        entry["error"] = str(e)
        result = {"status": "network_error", "error": str(e), "payload": payload}
    _append_log(PUSH_LOG_PATH, entry)
    return result


def update_category_texts(
    category_id: int,
    description: Optional[str] = None,
    meta_title: Optional[str] = None,
    meta_description: Optional[str] = None,
) -> dict:
    payload = {
        "categoryId": int(category_id),
        "storeId": _store_id(),
        "description": description,
        "metaTitle": meta_title,
        "metaDescription": meta_description,
    }
    return _post_update("catalog/category/texts", payload)


def update_cms_page_texts(
    cms_page_id: int,
    meta_title: Optional[str] = None,
    meta_description: Optional[str] = None,
) -> dict:
    # CMS pages do NOT take a description field per the API spec.
    payload = {
        "cmsPageId": int(cms_page_id),
        "metaTitle": meta_title,
        "metaDescription": meta_description,
    }
    return _post_update("cms/page/texts", payload)


def update_filterpage_texts(
    filter_page_id: int,
    description: Optional[str] = None,
    meta_title: Optional[str] = None,
    meta_description: Optional[str] = None,
) -> dict:
    payload = {
        "filterPageId": int(filter_page_id),
        "description": description,
        "metaTitle": meta_title,
        "metaDescription": meta_description,
    }
    return _post_update("catalog/filterpage/texts", payload)


def update_for_page(
    page_info: dict,
    description: Optional[str] = None,
    meta_title: Optional[str] = None,
    meta_description: Optional[str] = None,
) -> dict:
    """Dispatch to the correct endpoint based on the page's type.
    page_info is a value from the fetched lookup table (has 'type' + 'id').
    For CMS pages, description is silently ignored (the API rejects it)."""
    if not isinstance(page_info, dict):
        return {"status": "error", "error": "page_info missing", "payload": None}
    t = page_info.get("type")
    pid = page_info.get("id")
    if not pid:
        return {"status": "error", "error": "page id missing", "payload": None}
    if t == "category":
        return update_category_texts(pid, description, meta_title, meta_description)
    if t == "cms":
        return update_cms_page_texts(pid, meta_title, meta_description)
    if t == "filterpage":
        return update_filterpage_texts(pid, description, meta_title, meta_description)
    return {"status": "error", "error": f"unknown page type: {t}", "payload": None}


# ── Logging ────────────────────────────────────────────────────────

def _append_log(path: str, entry: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        return
    log = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                log = json.load(f) or []
        except Exception:
            log = []
    log.append(entry)
    # Keep only the last 500 entries to avoid unbounded growth.
    log = log[-500:]
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def read_push_log(limit: int = 30) -> list:
    if not os.path.exists(PUSH_LOG_PATH):
        return []
    try:
        with open(PUSH_LOG_PATH, "r", encoding="utf-8") as f:
            log = json.load(f) or []
    except Exception:
        return []
    return log[-limit:][::-1]


def last_successful_admin_push(endpoint: str, page_id: int) -> Optional[dict]:
    """Most recent successful entry for a given endpoint + page_id."""
    if not os.path.exists(PUSH_LOG_PATH):
        return None
    try:
        with open(PUSH_LOG_PATH, "r", encoding="utf-8") as f:
            log = json.load(f) or []
    except Exception:
        return None
    target_id_keys = ("categoryId", "cmsPageId", "filterPageId")
    for e in reversed(log):
        if e.get("status") != "success":
            continue
        if endpoint and e.get("endpoint") != endpoint:
            continue
        p = e.get("payload") or {}
        for k in target_id_keys:
            if p.get(k) == page_id:
                return e
    return None
