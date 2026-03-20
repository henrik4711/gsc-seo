"""
Page scraper: fetches landing pages using Playwright (headless Chrome),
extracts meta tags, content, links, and schema markup.
Renders JavaScript — gets the REAL page content, not raw HTML.
"""

import re
import json
from urllib.parse import urlparse
from typing import Optional

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

# Playwright browser instance — created on-demand, not at import
_browser = None
_playwright = None
_playwright_failed = False  # Don't retry if it failed once


def _get_browser():
    """Get or create a shared Playwright browser instance. Returns None if unavailable."""
    global _browser, _playwright, _playwright_failed
    if _playwright_failed:
        return None
    if _browser:
        try:
            if _browser.is_connected():
                return _browser
        except Exception:
            pass
    try:
        from playwright.sync_api import sync_playwright
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--single-process",
            ],
        )
        return _browser
    except Exception as e:
        import traceback
        _playwright_error = str(e)
        print(f"[scraper] Playwright unavailable: {e}")
        print(traceback.format_exc())
        _playwright_failed = True
        # Store error for debug display
        import streamlit as _st
        _st.session_state["_playwright_error"] = f"{e}\n{traceback.format_exc()}"
        return None


def scrape_page(url: str, timeout: int = 15) -> dict:
    """
    Scrape a URL using Playwright (headless Chrome).
    Returns: dict with title, description, h1, h2s, body_text, word_count, etc.
    """
    result = {
        "url": url,
        "success": False,
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
    }

    if not BS4_AVAILABLE:
        result["error"] = "beautifulsoup4 not installed"
        return result

    browser = _get_browser()
    if not browser:
        # Fallback to requests if Playwright not available
        result["_scraper"] = "requests (Playwright unavailable)"
        return _scrape_with_requests(url, timeout, result)

    result["_scraper"] = "playwright"

    try:
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page.set_default_timeout(timeout * 1000)

        # Navigate and wait for content to load
        page.goto(url, wait_until="domcontentloaded")

        # Dismiss cookie consent if present
        try:
            for selector in [
                "button:has-text('Acceptera')", "button:has-text('Accept')",
                "button:has-text('Godkänn')", "button:has-text('OK')",
                "[class*='cookie'] button", "[class*='consent'] button",
            ]:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    page.wait_for_timeout(500)
                    break
        except Exception:
            pass  # No cookie popup or couldn't dismiss

        # Wait for main content
        try:
            page.wait_for_selector("div.xmx-page-content, main, article, [role='main']", timeout=5000)
        except Exception:
            pass  # Content might already be there

        # Get rendered HTML
        html = page.content()
        page.close()

    except Exception as e:
        result["error"] = str(e)
        try:
            page.close()
        except Exception:
            pass
        return result

    # Parse rendered HTML with BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    result["success"] = True

    # Title
    title_tag = soup.find("title")
    if title_tag:
        result["title"] = title_tag.get_text(strip=True)
        result["title_length"] = len(result["title"])

    # Meta description
    meta_desc = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    if meta_desc:
        result["meta_description"] = meta_desc.get("content", "").strip()
        result["description_length"] = len(result["meta_description"])

    # Canonical
    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical:
        result["canonical"] = canonical.get("href", "")

    # Headings
    h1 = soup.find("h1")
    if h1:
        result["h1"] = h1.get_text(strip=True)

    result["h2s"] = [h.get_text(strip=True) for h in soup.find_all("h2")][:15]
    result["h3s"] = [h.get_text(strip=True) for h in soup.find_all("h3")][:15]

    # Schema types
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "{}")
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "@type" in item:
                        result["schema_types"].append(item["@type"])
            elif "@type" in data:
                result["schema_types"].append(data["@type"])
            if "@graph" in data:
                for item in data["@graph"]:
                    if isinstance(item, dict) and "@type" in item:
                        result["schema_types"].append(item["@type"])
        except Exception:
            pass

    # ── Body text: extract from content area ──────────────────
    # Work on a copy for text extraction
    text_soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in text_soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]):
        tag.decompose()

    # Remove cookie/GDPR
    for sel in [
        {"class_": re.compile(r"cookie|consent|gdpr|cc-|privacy-banner", re.I)},
        {"id": re.compile(r"cookie|consent|gdpr", re.I)},
    ]:
        for tag in text_soup.find_all(["div", "section"], sel):
            tag.decompose()

    # Find main content container
    main_content = (
        text_soup.find("div", class_="xmx-page-content")
        or text_soup.find("main")
        or text_soup.find("article")
        or text_soup.find("div", role="main")
        or text_soup.find("div", class_=re.compile(r"^(main|page-content|content-area)", re.I))
        or text_soup.body
    )

    if main_content:
        raw_text = main_content.get_text(separator=" ", strip=True)
        body_text = re.sub(r'\s+', ' ', raw_text).strip()
        result["body_text"] = body_text[:8000]
        result["word_count"] = len(body_text.split())

    # ── Links: extract from content area ──────────────────────
    link_soup = BeautifulSoup(html, "html.parser")
    content_for_links = (
        link_soup.find("div", class_="xmx-page-content")
        or link_soup.find("main")
        or link_soup.body
    )

    domain = urlparse(url).netloc
    internal_links = []
    seen_urls = set()
    ext_count = 0

    if content_for_links:
        for a in content_for_links.find_all("a", href=True):
            href = a["href"]
            anchor = a.get_text(strip=True)[:80]
            if href.startswith("/") and not href.startswith("//"):
                href = f"https://{domain}{href}"
            if href.startswith("http"):
                if domain in href:
                    norm = href.rstrip("/").lower().split("?")[0].split("#")[0]
                    if norm not in seen_urls:
                        seen_urls.add(norm)
                        internal_links.append({"url": href, "anchor": anchor})
                else:
                    ext_count += 1

    result["internal_links"] = internal_links
    result["internal_link_count"] = len(internal_links)
    result["external_links"] = ext_count

    # Images without alt
    if main_content:
        result["images_without_alt"] = sum(
            1 for img in main_content.find_all("img")
            if not img.get("alt", "").strip()
        )

    return result


def _scrape_with_requests(url: str, timeout: int, result: dict) -> dict:
    """Fallback scraper using requests (no JS rendering)."""
    try:
        import requests
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; SEOBot/1.0)"
        }, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        result["success"] = True

        title_tag = soup.find("title")
        if title_tag:
            result["title"] = title_tag.get_text(strip=True)
            result["title_length"] = len(result["title"])

        meta_desc = soup.find("meta", attrs={"name": re.compile("description", re.I)})
        if meta_desc:
            result["meta_description"] = meta_desc.get("content", "").strip()
            result["description_length"] = len(result["meta_description"])

        h1 = soup.find("h1")
        if h1:
            result["h1"] = h1.get_text(strip=True)

        result["h2s"] = [h.get_text(strip=True) for h in soup.find_all("h2")][:15]
        result["h3s"] = [h.get_text(strip=True) for h in soup.find_all("h3")][:15]

        # Body text from content area
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        main = soup.find("div", class_="xmx-page-content") or soup.find("main") or soup.body
        if main:
            raw = re.sub(r'\s+', ' ', main.get_text(separator=" ", strip=True))
            result["body_text"] = raw[:8000]
            result["word_count"] = len(raw.split())

    except Exception as e:
        result["error"] = str(e)

    return result


def evaluate_meta(page_data: dict, target_keywords: list) -> dict:
    """
    Evaluate meta title and description quality
    Returns scores and specific issues
    """
    issues = []
    score = 100

    title = page_data.get("title") or ""
    desc = page_data.get("meta_description") or ""
    title_len = len(title)
    desc_len = len(desc)

    if not title:
        issues.append({"type": "critical", "field": "title", "msg": "Missing meta title"})
        score -= 30
    elif title_len < 30:
        issues.append({"type": "warn", "field": "title", "msg": f"Title too short ({title_len} chars, recommended 50-60)"})
        score -= 10
    elif title_len > 65:
        issues.append({"type": "warn", "field": "title", "msg": f"Title too long ({title_len} chars, max ~60)"})
        score -= 8

    if not desc:
        issues.append({"type": "critical", "field": "description", "msg": "Missing meta description"})
        score -= 25
    elif desc_len < 80:
        issues.append({"type": "warn", "field": "description", "msg": f"Description too short ({desc_len} chars, recommended 140-160)"})
        score -= 10
    elif desc_len > 165:
        issues.append({"type": "warn", "field": "description", "msg": f"Description truncated in SERP ({desc_len} chars, max ~160)"})
        score -= 5

    kw_in_title = sum(1 for kw in target_keywords if kw.lower() in title.lower())
    kw_in_desc = sum(1 for kw in target_keywords if kw.lower() in desc.lower())

    if target_keywords and kw_in_title == 0:
        issues.append({"type": "warn", "field": "title", "msg": "Primary keywords not in title"})
        score -= 15

    if target_keywords and kw_in_desc == 0:
        issues.append({"type": "warn", "field": "description", "msg": "Primary keywords not in description"})
        score -= 10

    cta_words = ["köp", "beställ", "bestall", "se", "hitta", "bäst", "billig", "fri frakt", "snabb",
                  "kob", "bestil", "bedst", "gratis fragt",
                  "top", "test", "buy", "order", "shop", "find", "best", "cheap",
                  "free shipping", "fast", "deal", "save", "discount", "offer"]
    has_cta_title = any(w in title.lower() for w in cta_words)
    has_cta_desc = any(w in desc.lower() for w in cta_words)

    if not has_cta_title:
        issues.append({"type": "info", "field": "title", "msg": "No call-to-action signals in title"})
        score -= 5

    if not has_cta_desc:
        issues.append({"type": "info", "field": "description", "msg": "No USP/CTA in description (free shipping, fast delivery, etc.)"})
        score -= 5

    return {
        "score": max(0, score),
        "issues": issues,
        "keywords_in_title": kw_in_title,
        "keywords_in_desc": kw_in_desc,
        "has_cta_title": has_cta_title,
        "has_cta_desc": has_cta_desc,
        "title_length": title_len,
        "desc_length": desc_len,
    }
