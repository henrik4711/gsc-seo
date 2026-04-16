"""
Single source of truth for HTML extraction helpers.

ONE function per logical task. Used by page_scraper.py,
category_analyzer.py, and any other module that needs to pull
data out of a parsed BeautifulSoup tree.

If you find yourself writing soup.find("title")... or
soup.find_all("script", type="application/ld+json")... in another
file — STOP and use the helper from here instead.
"""

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup


# ─────────────────────────────────────────────────────────────────────
# MAIN CONTENT CONTAINER
# ─────────────────────────────────────────────────────────────────────

def find_main_content(soup):
    """
    Find the page's main content container. Tries multiple known
    wrappers in priority order. Returns the soup tag (or None).
    """
    return (
        soup.find("div", class_="xmx-page-content")
        or soup.find("main")
        or soup.find("article")
        or soup.find("div", role="main")
        or soup.find("div", class_=re.compile(r"^(main|page-content|content-area)", re.I))
        or soup.body
    )


# ─────────────────────────────────────────────────────────────────────
# META — title, description, canonical, last-modified
# ─────────────────────────────────────────────────────────────────────

def extract_meta(soup) -> dict:
    """
    Extract <title>, <meta name=description>, <link rel=canonical>,
    plus length stats. Returns dict.
    """
    out = {
        "title": None,
        "title_length": 0,
        "meta_description": None,
        "description_length": 0,
        "canonical": None,
        "last_modified_meta": None,
    }
    title_tag = soup.find("title")
    if title_tag:
        t = title_tag.get_text(strip=True)
        out["title"] = t
        out["title_length"] = len(t)

    meta_desc = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    if meta_desc:
        d = (meta_desc.get("content", "") or "").strip()
        out["meta_description"] = d
        out["description_length"] = len(d)

    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical:
        out["canonical"] = canonical.get("href", "")

    meta_date = soup.find("meta", attrs={"property": re.compile("modified_time|updated_time", re.I)})
    if meta_date:
        out["last_modified_meta"] = meta_date.get("content", "")

    return out


# ─────────────────────────────────────────────────────────────────────
# HEADINGS — h1, h2, h3
# ─────────────────────────────────────────────────────────────────────

def extract_headings(soup, h2_limit: int = 15, h3_limit: int = 15) -> dict:
    """Return dict with h1 (str or None), h2s (list), h3s (list)."""
    h1_tag = soup.find("h1")
    return {
        "h1": h1_tag.get_text(strip=True) if h1_tag else None,
        "h2s": [h.get_text(strip=True) for h in soup.find_all("h2")][:h2_limit],
        "h3s": [h.get_text(strip=True) for h in soup.find_all("h3")][:h3_limit],
    }


# ─────────────────────────────────────────────────────────────────────
# SCHEMA — ld+json @type extraction
# ─────────────────────────────────────────────────────────────────────

def extract_schema_types(soup) -> list:
    """
    Walk all <script type="application/ld+json"> blocks and return
    the union of @type values. Handles arrays and @graph nesting.
    """
    types = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "{}")
        except Exception:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "@type" in item:
                    types.append(item["@type"])
        elif isinstance(data, dict):
            if "@type" in data:
                types.append(data["@type"])
            if "@graph" in data:
                for item in data["@graph"]:
                    if isinstance(item, dict) and "@type" in item:
                        types.append(item["@type"])
    return types


def extract_schema_raw(soup) -> list:
    """Return the raw parsed ld+json blocks (for downstream inspection)."""
    blocks = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            blocks.append(json.loads(tag.string or "{}"))
        except Exception:
            continue
    return blocks


# ─────────────────────────────────────────────────────────────────────
# INTERNAL LINKS — with anchors, deduplicated, absolute URLs
# ─────────────────────────────────────────────────────────────────────

def extract_internal_links(soup, page_url: str) -> dict:
    """
    Extract internal links from main content area. Returns dict with:
      - internal_links: list of {url, anchor}
      - internal_link_count: int
      - external_link_count: int

    URLs are absolute and deduplicated (one entry per unique URL).
    """
    from utils.ui_helpers import normalize_url

    domain = urlparse(page_url).netloc
    main = find_main_content(soup)
    if not main:
        return {"internal_links": [], "internal_link_count": 0, "external_link_count": 0}

    internal = []
    seen = set()
    ext_count = 0
    for a in main.find_all("a", href=True):
        href = a["href"]
        anchor = a.get_text(strip=True)[:80]
        if href.startswith("/") and not href.startswith("//"):
            href = f"https://{domain}{href}"
        if not href.startswith("http"):
            continue
        if domain in href:
            norm = normalize_url(href)
            if norm not in seen:
                seen.add(norm)
                internal.append({"url": norm, "anchor": anchor})
        else:
            ext_count += 1
    return {
        "internal_links": internal,
        "internal_link_count": len(internal),
        "external_link_count": ext_count,
    }


# ─────────────────────────────────────────────────────────────────────
# IMAGES — alt-text counting
# ─────────────────────────────────────────────────────────────────────

def count_images_without_alt(soup_or_main) -> dict:
    """
    Count images in the given element (typically main_content) that
    are missing alt text. Returns {images_total, images_without_alt}.
    """
    if soup_or_main is None:
        return {"images_total": 0, "images_without_alt": 0}
    imgs = soup_or_main.find_all("img")
    return {
        "images_total": len(imgs),
        "images_without_alt": sum(1 for img in imgs if not (img.get("alt", "") or "").strip()),
    }


# ─────────────────────────────────────────────────────────────────────
# BODY TEXT — cleaned full text from main content
# ─────────────────────────────────────────────────────────────────────

def extract_body_text(soup_or_main, max_chars: int = 20000) -> dict:
    """
    Get cleaned full body text from main_content area. Returns
    {body_text, word_count}. Whitespace-normalised.
    """
    if soup_or_main is None:
        return {"body_text": "", "word_count": 0}
    raw = soup_or_main.get_text(separator=" ", strip=True)
    cleaned = re.sub(r"\s+", " ", raw).strip()
    return {
        "body_text": cleaned[:max_chars],
        "word_count": len(cleaned.split()),
    }


# ─────────────────────────────────────────────────────────────────────
# COOKIE / NAV / FOOTER stripping (for text extraction)
# ─────────────────────────────────────────────────────────────────────

def strip_non_content(soup) -> None:
    """
    In-place: decompose script/style/nav/footer/header/aside/noscript +
    cookie/GDPR banners. Use on a COPY of the soup if you still need the
    full DOM elsewhere.
    """
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]):
        tag.decompose()
    for sel in [
        {"class_": re.compile(r"cookie|consent|gdpr|cc-|privacy-banner", re.I)},
        {"id": re.compile(r"cookie|consent|gdpr", re.I)},
    ]:
        for tag in soup.find_all(["div", "section"], sel):
            tag.decompose()
