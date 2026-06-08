"""
Client for the Mshop Admin API — fetch active pages and update meta /
intro / description fields on categories, CMS pages, and filter pages.

SHOP SELECTION — IMPORTANT (verified empirically 2026-06-03):
  The API selects the shop PURELY BY DOMAIN, not by a storeId param.
    https://www.mshop.se/public-api/...  → SE pages
    https://www.mshop.dk/public-api/...  → DK pages
    https://www.mshop.eu/public-api/...  → EU pages
  The list endpoints IGNORE ?storeId entirely (storeId none/1/2/3 all
  return the same per-domain result). So each Railway service must point
  MSHOP_ADMIN_API_BASE at ITS OWN shop domain. The path is 'public-api'
  with a HYPHEN — 'public_api' with an underscore returns 404.

Required Railway env vars (same credentials as bottom-text push):
  FOOTER_TEXT_API_USER  — Basic auth username
  FOOTER_TEXT_API_PASS  — Basic auth password
  MSHOP_ADMIN_API_BASE  — this shop's OWN domain + /public-api, e.g.
                         https://www.mshop.eu/public-api for the EU
                         service. PER-DOMAIN, not shared. (Optional —
                         derived from FOOTER_TEXT_API's host + /public-api
                         if absent.)
  FOOTER_TEXT_STORE_ID  — integer store ID, used ONLY by the UPDATE/push
                         endpoints (carried in the JSON payload):
                           1 = mshop.se, 2 = mshop.dk, 3 = mshop.eu,
                           4 = mshop.de (future).
                         NOT used by the list endpoints (domain decides).

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


# Maps SITE_CODE env-var value → expected URL domain substring. Used by
# validate_active_pages_match_site() below to detect when a cached
# mshop_active_pages dict on /data was synced before a multi-site fix
# and contains URLs for the wrong shop.
_SITE_CODE_TO_DOMAIN = {
    "se": "mshop.se",
    "dk": "mshop.dk",
    "eu": "mshop.eu",
    "de": "mshop.de",  # future shop
}


def validate_active_pages_match_site(cache: dict | None) -> tuple[bool, str]:
    """Check whether a cached mshop_active_pages dict contains URLs that
    match this service's SITE_CODE.

    Without this, a /data cache synced when FOOTER_TEXT_STORE_ID was
    wrong (or before storeId was being sent to list endpoints) keeps
    returning the wrong shop's URLs even after the env var or code is
    fixed — because run_pipeline's bulk audit auto-syncs only when the
    cache is empty (see views/run_pipeline.py:419-435).

    Returns (is_valid, reason). reason is empty if valid, otherwise a
    short human-readable diagnostic the caller can surface to the UI.

    Cases that return (True, ""):
      - cache is empty / None / has no lookup (caller will trigger
        fresh sync naturally)
      - SITE_CODE not set (we can't validate; assume operator knows)
      - SITE_CODE not in our domain map (forward-compat: don't reject)

    Case that returns (False, reason):
      - cache has URLs and >=50% don't contain the expected domain
        substring for this SITE_CODE
    """
    if not isinstance(cache, dict):
        return True, ""
    lookup = cache.get("lookup") or {}
    if not isinstance(lookup, dict) or not lookup:
        return True, ""

    from utils.persistence import _site_code  # late import to avoid cycle
    site = _site_code()
    if not site:
        return True, ""
    expected_domain = _SITE_CODE_TO_DOMAIN.get(site)
    if not expected_domain:
        return True, ""

    # Sample up to first 20 URLs from the cache; if fewer than half
    # contain the expected domain, consider the cache contaminated.
    sample_urls = []
    for meta in lookup.values():
        if isinstance(meta, dict):
            u = meta.get("url", "")
            if u:
                sample_urls.append(u)
                if len(sample_urls) >= 20:
                    break

    if not sample_urls:
        return True, ""

    matching = sum(1 for u in sample_urls if expected_domain in u.lower())
    match_rate = matching / len(sample_urls)
    if match_rate >= 0.5:
        return True, ""

    # Find an example of the wrong-domain URL to surface in the diagnostic
    wrong_example = next((u for u in sample_urls if expected_domain not in u.lower()), "")
    return False, (
        f"Cached mshop_active_pages contains {matching}/{len(sample_urls)} "
        f"URLs matching expected domain '{expected_domain}' for "
        f"SITE_CODE={site}. Example wrong-domain URL: {wrong_example!r}. "
        f"This is a stale cache from a previous boot when storeId was "
        f"wrong — discarding so the next bulk audit triggers a fresh "
        f"sync against the correct shop."
    )


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

    # The LIST endpoints select the shop PURELY BY DOMAIN, not by storeId.
    # Proven empirically (probe_admin_api_variants, 2026-06-03): hitting
    # www.mshop.{se,dk,eu}/public-api/... returns that shop's own pages,
    # and the ?storeId param makes NO difference (storeId none/1/2/3 all
    # returned identical results per domain). So each service must point
    # MSHOP_ADMIN_API_BASE at its OWN shop domain (with the 'public-api'
    # hyphen path). We do NOT send storeId here — it's ignored by the list
    # API, and the old hard-fail-on-missing was based on a wrong
    # assumption. (storeId is still required for the UPDATE/push endpoints,
    # which carry it in the JSON payload — see _post_update.)
    # The validate_active_pages_match_site() guard catches a base pointed
    # at the wrong domain by checking returned URLs against SITE_CODE.
    base = _api_base()
    user, pwd = _credentials()
    url = f"{base}/{endpoint.lstrip('/')}"
    # Full target shown in every error so the operator can SEE the exact
    # URL that was hit instead of guessing whether a 404 means a wrong
    # base URL, wrong path spelling (public_api vs public-api), or the
    # env var hasn't redeployed. Don't guess from "HTTP 404" — show it.
    called = url
    try:
        resp = requests.get(
            url,
            auth=(user, pwd),
            timeout=TIMEOUT_SECONDS,
        )
    except requests.Timeout:
        return {"status": "timeout", "error": f"Timeout after {TIMEOUT_SECONDS}s calling {called}", "items": []}
    except Exception as e:
        return {"status": "network_error", "error": f"{e} (calling {called})", "items": []}
    if resp.status_code != 200:
        return {
            "status": "http_error",
            "error": f"HTTP {resp.status_code} for {called}",
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


def probe_admin_api_variants(endpoint: str = "catalog/category/list") -> list:
    """Diagnostic probe: hit the list endpoint several ways and report what
    each returns, so we can determine the API's ACTUAL shop-selection
    mechanism (one shared domain + ?storeId=N, vs one endpoint per shop
    domain with no storeId) WITHOUT guessing.

    Uses the shared Basic-auth credentials (same user/pass across all
    shops per MULTISITE_SETUP.md), so from any one service we can probe
    all three shop domains. The first returned URL reveals WHICH shop the
    response actually belongs to — the key signal.

    Returns a list of {base, store_id, http, n_items, sample_url[, error]}.
    store_id None means the storeId param was NOT sent at all.
    """
    user, pwd = _credentials()
    # Try BOTH path spellings (the env var has 'public_api' with an
    # underscore, but the code's own fallback + docstring use 'public-api'
    # with a hyphen) AND the base actually derived from the configured
    # env, so we discover which base+path is really live.
    domains = ["www.mshop.se", "www.mshop.dk", "www.mshop.eu"]
    spellings = ["public_api", "public-api"]
    bases = [f"https://{d}/{s}" for d in domains for s in spellings]
    # Also include whatever the running config resolves to, in case the
    # real working host is something else entirely (e.g. FOOTER_TEXT_API).
    configured = _api_base()
    if configured and configured not in bases:
        bases.append(configured)
    store_variants = [None, 1, 2, 3]
    ep = endpoint.lstrip("/")
    results = []
    for base in bases:
        url = f"{base}/{ep}"
        for sid in store_variants:
            params = {} if sid is None else {"storeId": sid}
            row = {"base": base, "store_id": sid, "http": None,
                   "n_items": 0, "sample_url": ""}
            try:
                resp = requests.get(url, auth=(user, pwd), params=params, timeout=15)
                row["http"] = resp.status_code
                if resp.status_code == 200:
                    try:
                        items = resp.json().get("payload") or []
                        if isinstance(items, list):
                            row["n_items"] = len(items)
                            if items and isinstance(items[0], dict):
                                row["sample_url"] = items[0].get("url", "") or ""
                    except Exception as e:
                        row["sample_url"] = f"(200 but unparseable JSON: {e})"
            except Exception as e:
                row["http"] = "ERR"
                row["error"] = str(e)[:140]
            results.append(row)
    return results


def probe_env_snapshot() -> dict:
    """Return the admin-API-relevant env values the RUNNING service sees,
    so the operator can verify config without shell access. Secrets
    (password) are masked to just a length."""
    base = os.environ.get("MSHOP_ADMIN_API_BASE", "").strip()
    footer = os.environ.get("FOOTER_TEXT_API", "").strip()
    user = os.environ.get("FOOTER_TEXT_API_USER", "").strip()
    pwd = os.environ.get("FOOTER_TEXT_API_PASS", "").strip()
    return {
        "MSHOP_ADMIN_API_BASE": base or "(unset)",
        "FOOTER_TEXT_API": footer or "(unset)",
        "resolved _api_base()": _api_base() or "(empty)",
        "FOOTER_TEXT_STORE_ID": os.environ.get("FOOTER_TEXT_STORE_ID", "").strip() or "(unset)",
        "SITE_CODE": os.environ.get("SITE_CODE", "").strip() or "(unset)",
        "FOOTER_TEXT_API_USER": user or "(unset)",
        "FOOTER_TEXT_API_PASS": f"(set, {len(pwd)} chars)" if pwd else "(unset)",
    }


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

    # Defensive central check: every update payload MUST include a
    # positive storeId. The Mshop API silently defaults to store 1
    # (mshop.se) when storeId is missing or zero, so a forgotten
    # field doesn't fail the API call — it just lands on the wrong
    # shop. We've already been bitten by this twice
    # (update_cms_page_texts, update_filterpage_texts). Enforce
    # storeId at the central poster so the next added endpoint
    # can't repeat the pattern, and surface the failure via the
    # central errors system so the operator sees it in the UI.
    incoming_store_id = payload.get("storeId") if isinstance(payload, dict) else None
    try:
        incoming_store_id_int = int(incoming_store_id) if incoming_store_id is not None else 0
    except (TypeError, ValueError):
        incoming_store_id_int = 0
    if incoming_store_id_int <= 0:
        msg = (
            f"Push to {endpoint} blocked: payload has no positive storeId "
            f"(got {incoming_store_id!r}). Without it the Mshop API "
            f"silently routes the request to store 1 (mshop.se). Set "
            f"FOOTER_TEXT_STORE_ID on the Railway service (1=SE, 2=DK, "
            f"3=EU, 4=DE) and verify the calling function includes "
            f'"storeId": _store_id() in its payload dict.'
        )
        try:
            from utils.errors import report_error
            report_error(stage="mshop_admin_post", key=endpoint,
                         message=msg, severity="error")
        except Exception:
            pass
        return {"status": "error", "error": msg, "payload": payload}

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
    # storeId is REQUIRED — without it the Mshop API silently defaults
    # to store 1 (mshop.se) and DK/EU pushes land on the wrong shop.
    payload = {
        "cmsPageId": int(cms_page_id),
        "storeId": _store_id(),
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
    # storeId is REQUIRED — without it the Mshop API silently defaults
    # to store 1 (mshop.se) and DK/EU pushes land on the wrong shop.
    payload = {
        "filterPageId": int(filter_page_id),
        "storeId": _store_id(),
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
    # FINAL boundary clean: strip em/en-dashes from EVERY field before it
    # reaches the live shop, no matter which generator or push path produced
    # it. Single chokepoint — see utils/text_clean.strip_ai_dashes.
    from utils.text_clean import strip_ai_dashes
    if description:
        description = strip_ai_dashes(description)
        # Same-site absolute links must use the www host
        # (https://www.mshop.eu/…), matching the footer/bottom-text path.
        # The admin API (intro/description) previously skipped this, so
        # intro links could go live as non-www. Mirror the bottom rewrite.
        try:
            from utils.footer_text_api import add_www_to_href_attrs, _host_without_www
            _host = _host_without_www(page_info.get("url", "") or "")
            if _host:
                description = add_www_to_href_attrs(description, _host)
        except Exception:
            pass
    if meta_title:
        meta_title = strip_ai_dashes(meta_title)
    if meta_description:
        meta_description = strip_ai_dashes(meta_description)
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
