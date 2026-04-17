"""
Raw HTML cache — saves fetched HTML to disk so we can re-parse
without re-scraping from the network.

ONE module used everywhere. Two operations:
  save_html(url, html)     — called by scrape_page after fetch
  parse_from_cache(url)    — re-runs full parsing on cached HTML

Use cases:
  - Parser/classifier bug fixed → re-parse cached HTML (~2 min for 1130 pages)
  - Network down / site blocking → still have data to work with
  - Debug: inspect what HTML the scraper actually saw
"""

import os
import hashlib

HTML_CACHE_DIR = "/data/html_cache"


def _cache_path(url: str) -> str:
    """Deterministic file path for a URL's cached HTML."""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(HTML_CACHE_DIR, f"{url_hash}.html")


def save_html(url: str, html: str) -> bool:
    """Save raw HTML to disk. Called once per successful scrape."""
    try:
        os.makedirs(HTML_CACHE_DIR, exist_ok=True)
        path = _cache_path(url)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return True
    except Exception as e:
        print(f"[html_cache] save failed for {url}: {e}")
        return False


def has_cached(url: str) -> bool:
    """Check if we have cached HTML for this URL."""
    return os.path.exists(_cache_path(url))


def load_html(url: str) -> str:
    """Load cached raw HTML. Returns empty string if not found."""
    path = _cache_path(url)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"[html_cache] load failed for {url}: {e}")
        return ""


def parse_from_cache(url: str) -> dict:
    """
    Re-parse cached HTML through the full pipeline:
      _parse_html → extract_editorial_content → classify_page_type

    Returns the same dict as scrape_page() — identical output,
    just sourced from disk instead of network.

    Returns None if no cached HTML exists.
    """
    html = load_html(url)
    if not html:
        return None

    from bs4 import BeautifulSoup
    from utils.page_scraper import _parse_html

    result = {
        "url": url,
        "success": True,
        "error": None,
        "title": None,
        "meta_description": None,
        "h1": None,
        "h2s": [],
        "h3s": [],
        "body_text": "",
        "word_count": 0,
        "canonical": None,
        "schema_types": [],
        "internal_links": [],
        "internal_link_count": 0,
        "external_links": 0,
        "images_without_alt": 0,
        "title_length": 0,
        "description_length": 0,
        "_scraper": "cached_html",
    }

    soup = BeautifulSoup(html, "html.parser")
    result = _parse_html(result, soup, html, url)

    # Run classifier with full data (structural_signals included)
    from utils.category_analyzer import classify_page_type
    classification = classify_page_type(url, result)
    result["page_type"] = classification["page_type"]

    return result


def cache_stats() -> dict:
    """Return cache statistics for UI display."""
    if not os.path.isdir(HTML_CACHE_DIR):
        return {"count": 0, "size_mb": 0}
    files = [f for f in os.listdir(HTML_CACHE_DIR) if f.endswith(".html")]
    total_bytes = sum(
        os.path.getsize(os.path.join(HTML_CACHE_DIR, f))
        for f in files
    )
    return {
        "count": len(files),
        "size_mb": round(total_bytes / (1024 * 1024), 1),
    }


def clear_cache() -> int:
    """Delete all cached HTML files. Returns count deleted."""
    if not os.path.isdir(HTML_CACHE_DIR):
        return 0
    n = 0
    for f in os.listdir(HTML_CACHE_DIR):
        if f.endswith(".html"):
            try:
                os.remove(os.path.join(HTML_CACHE_DIR, f))
                n += 1
            except Exception:
                pass
    return n
