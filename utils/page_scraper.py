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
_playwright_failed = False
_playwright_fail_count = 0
_PLAYWRIGHT_MAX_RETRIES = 3  # Retry browser restart up to 3 times before giving up


def _get_browser():
    """Get or create a shared Playwright browser instance. Restarts if crashed."""
    global _browser, _playwright, _playwright_failed, _playwright_fail_count
    if _playwright_failed:
        return None
    if _browser:
        try:
            if _browser.is_connected():
                return _browser
        except Exception:
            pass
        # Browser died — clean up and restart
        _playwright_fail_count += 1
        print(f"[scraper] Browser crashed (attempt {_playwright_fail_count}/{_PLAYWRIGHT_MAX_RETRIES}), restarting...")
        try:
            _browser.close()
        except Exception:
            pass
        try:
            _playwright.stop()
        except Exception:
            pass
        _browser = None
        _playwright = None
        if _playwright_fail_count >= _PLAYWRIGHT_MAX_RETRIES:
            print(f"[scraper] Playwright crashed {_playwright_fail_count} times — giving up for this session")
            _playwright_failed = True
            return None
        # Brief pause before restart to let resources free
        import time
        time.sleep(1)
    try:
        from playwright.sync_api import sync_playwright
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-extensions",
                "--disable-background-networking",
            ],
        )
        # Reset fail count on successful launch
        _playwright_fail_count = 0
        return _browser
    except Exception as e:
        import traceback
        _playwright_fail_count += 1
        print(f"[scraper] Playwright launch failed (attempt {_playwright_fail_count}/{_PLAYWRIGHT_MAX_RETRIES}): {e}")
        if _playwright_fail_count >= _PLAYWRIGHT_MAX_RETRIES:
            print(f"[scraper] Playwright permanently unavailable after {_playwright_fail_count} failures")
            _playwright_failed = True
            import streamlit as _st
            _st.session_state["_playwright_error"] = f"{e}\n{traceback.format_exc()}"
        return None


def reset_playwright():
    """Reset Playwright state so it can be retried. Call before batch operations."""
    global _browser, _playwright, _playwright_failed, _playwright_fail_count
    try:
        if _browser:
            _browser.close()
    except Exception:
        pass
    try:
        if _playwright:
            _playwright.stop()
    except Exception:
        pass
    _browser = None
    _playwright = None
    _playwright_failed = False
    _playwright_fail_count = 0
    print("[scraper] Playwright state reset — will retry on next scrape")


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
        result["_scraper"] = "requests (Playwright unavailable)"
        return _scrape_with_requests(url, timeout, result)

    result["_scraper"] = "playwright"

    page = None
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
            pass

        # Wait for main content
        try:
            page.wait_for_selector("div.xmx-page-content, main, article, [role='main']", timeout=5000)
        except Exception:
            pass

        # Get rendered HTML
        html = page.content()
        page.close()

    except Exception as e:
        if page:
            try:
                page.close()
            except Exception:
                pass
        # If browser crashed, force restart and retry once
        if "closed" in str(e).lower() or "crashed" in str(e).lower() or "target" in str(e).lower():
            global _browser
            import traceback
            print(f"[scraper] Browser crash on {url}: {type(e).__name__}: {e}")
            print(f"[scraper] Traceback: {traceback.format_exc()}")
            _browser = None
            browser = _get_browser()
            if browser:
                try:
                    page = browser.new_page(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    )
                    page.set_default_timeout(timeout * 1000)
                    page.goto(url, wait_until="domcontentloaded")
                    try:
                        page.wait_for_selector("div.xmx-page-content, main, article, [role='main']", timeout=5000)
                    except Exception:
                        pass
                    html = page.content()
                    page.close()
                    # Success on retry — continue to parsing below
                    soup = BeautifulSoup(html, "html.parser")
                    result["success"] = True
                    result["_scraper"] = "playwright (retry)"
                    # Jump to parsing (duplicated to avoid goto)
                    return _parse_html(result, soup, html, url)
                except Exception as e2:
                    print(f"[scraper] Retry also failed on {url}: {type(e2).__name__}: {e2}")
                    result["error"] = f"Retry also failed: {e2}"
                    try:
                        page.close()
                    except Exception:
                        pass
                    return result
        result["error"] = str(e)
        print(f"[scraper] Non-crash error on {url}: {type(e).__name__}: {e}")
        return result

    # Parse rendered HTML
    result["success"] = True
    return _parse_html(result, BeautifulSoup(html, "html.parser"), html, url)


def _parse_html(result: dict, soup, html: str, url: str) -> dict:
    """Parse HTML into result dict. Shared by normal scrape and retry."""
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

    # ── Template detection (Magento 1.9 + generic e-commerce) ──
    # Body class is the strongest signal — CMS platforms set it per page type
    body_tag = soup.find("body")
    body_classes = " ".join(body_tag.get("class", [])).lower() if body_tag else ""
    template_type = ""

    if body_classes:
        # Magento 1.9 body class patterns
        if "catalog-category-view" in body_classes or "category-" in body_classes:
            template_type = "category"
        elif "catalog-product-view" in body_classes or "product-" in body_classes:
            template_type = "product"
        elif "cms-" in body_classes or "page-cms" in body_classes:
            template_type = "cms"  # Could be category landing or info page
        elif "blog-" in body_classes or "post-" in body_classes:
            template_type = "blog"
        # Generic e-commerce platforms
        elif "category" in body_classes and "product" not in body_classes:
            template_type = "category"
        elif "single-product" in body_classes or "type-product" in body_classes:
            template_type = "product"
        elif "single-post" in body_classes or "type-post" in body_classes or "blog-post" in body_classes:
            template_type = "blog"

    # Container-based detection (Magento 1.9 specific)
    if not template_type:
        if soup.find("div", class_=re.compile(r"category-products?|products-grid|category-view", re.I)):
            template_type = "category"
        elif soup.find("div", class_=re.compile(r"product-essential|product-shop|product-view", re.I)):
            template_type = "product"
        elif soup.find("div", class_=re.compile(r"post-content|blog-post-view|article-body", re.I)):
            template_type = "blog"

    # ── Mshop/XMX-specific product accordion detection ──────
    # If page has accordion-highlights + accordion-description +
    # accordion-specifications → definitive PRODUCT page signal.
    has_accordion_product = False
    accordion_inputs = soup.find_all("input", attrs={"name": re.compile(r"accordion-", re.I)})
    accordion_names = {inp.get("name", "").lower() for inp in accordion_inputs}
    if {"accordion-highlights", "accordion-specifications"} & accordion_names:
        has_accordion_product = True
    # Also check for accordion labels (alternative detection)
    if not has_accordion_product:
        accordion_labels = soup.find_all("label", class_=re.compile(r"xmx-accordion-button", re.I))
        if len(accordion_labels) >= 2:
            has_accordion_product = True

    if has_accordion_product:
        template_type = "product"

    # ── ld+json BreadcrumbList = strong category signal ──────
    # Category pages typically have BreadcrumbList + ItemList schema.
    # Pure BreadcrumbList (without Product schema) = category.
    has_breadcrumb_schema = False
    has_product_schema = False
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            ld_text = tag.string or ""
            if '"BreadcrumbList"' in ld_text:
                has_breadcrumb_schema = True
            if '"Product"' in ld_text and '"ItemList"' not in ld_text:
                has_product_schema = True
        except Exception:
            pass

    # BreadcrumbList + NO Product schema + NO accordion = category
    if has_breadcrumb_schema and not has_product_schema and not has_accordion_product:
        if not template_type or template_type == "cms":
            template_type = "category"

    result["template_type"] = template_type
    result["has_accordion_product"] = has_accordion_product
    result["has_breadcrumb_schema"] = has_breadcrumb_schema
    result["body_classes"] = body_classes[:200]  # Store for debugging

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
        result["body_text"] = body_text[:20000]  # Full page text, not truncated
        result["word_count"] = len(body_text.split())

        # ── Editorial text separation (intro + bottom, excluding product grid)
        # Same logic as deep_scrape_category: split text at product grid boundary.
        # Paragraphs BEFORE product elements = intro_text (top)
        # Paragraphs AFTER product elements = bottom_text (footer)
        all_paragraphs = main_content.find_all(["p", "div", "h2", "h3"], recursive=True)
        intro_parts = []
        bottom_parts = []
        found_products = False

        for p_tag in all_paragraphs:
            text = p_tag.get_text(strip=True)
            if len(text) < 15:
                continue
            # Skip elements inside product cards/grid
            if p_tag.find_parent(attrs={"class": re.compile(r"product|card|grid|item|price|swiper", re.I)}):
                found_products = True
                continue
            # Skip navigation, menus, footer
            if p_tag.find_parent(["nav", "footer", "header"]):
                continue
            if not found_products:
                intro_parts.append(text)
            else:
                bottom_parts.append(text)

        result["intro_text"] = " ".join(intro_parts)[:5000]
        result["intro_word_count"] = len(result["intro_text"].split()) if result["intro_text"] else 0
        result["bottom_text"] = " ".join(bottom_parts)[:15000]  # Category pages can have 2000+ words
        result["bottom_word_count"] = len(result["bottom_text"].split()) if result["bottom_text"] else 0
        result["total_editorial_words"] = result["intro_word_count"] + result["bottom_word_count"]

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
                    from utils.ui_helpers import normalize_url
                    norm = normalize_url(href)
                    if norm not in seen_urls:
                        seen_urls.add(norm)
                        internal_links.append({"url": norm, "anchor": anchor})
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

        # Canonical
        canonical = soup.find("link", attrs={"rel": "canonical"})
        if canonical:
            result["canonical"] = canonical.get("href", "")

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
                if isinstance(data, dict) and "@graph" in data:
                    for item in data["@graph"]:
                        if isinstance(item, dict) and "@type" in item:
                            result["schema_types"].append(item["@type"])
            except Exception:
                pass

        # Links from content area (before decomposing nav)
        content_for_links = (
            BeautifulSoup(resp.text, "html.parser").find("div", class_="xmx-page-content")
            or soup.find("main")
            or soup.body
        )
        domain = urlparse(url).netloc
        seen_urls = set()
        if content_for_links:
            for a in content_for_links.find_all("a", href=True):
                href = a["href"]
                anchor = a.get_text(strip=True)[:80]
                if href.startswith("/") and not href.startswith("//"):
                    href = f"https://{domain}{href}"
                if href.startswith("http") and domain in href:
                    from utils.ui_helpers import normalize_url
                    norm = normalize_url(href)
                    if norm not in seen_urls:
                        seen_urls.add(norm)
                        result["internal_links"].append({"url": norm, "anchor": anchor})
                elif href.startswith("http"):
                    result["external_links"] += 1
        result["internal_link_count"] = len(result["internal_links"])

        # Body text from content area
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        main = soup.find("div", class_="xmx-page-content") or soup.find("main") or soup.body
        if main:
            raw = re.sub(r'\s+', ' ', main.get_text(separator=" ", strip=True))
            result["body_text"] = raw[:8000]
            result["word_count"] = len(raw.split())

        # Images
        if main:
            result["images_without_alt"] = sum(
                1 for img in main.find_all("img") if not img.get("alt", "").strip()
            )

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

    import unicodedata
    import html as html_mod
    def _nt(s):
        """Normalize text for keyword matching: NFC + HTML decode + lowercase."""
        return unicodedata.normalize("NFC", html_mod.unescape(s)).lower() if s else ""

    title_norm = _nt(title)
    desc_norm = _nt(desc)
    kw_in_title = sum(1 for kw in target_keywords if _nt(kw) in title_norm)
    kw_in_desc = sum(1 for kw in target_keywords if _nt(kw) in desc_norm)

    if target_keywords and kw_in_title == 0:
        issues.append({"type": "warn", "field": "title", "msg": "Primary keywords not in title"})
        score -= 15

    if target_keywords and kw_in_desc == 0:
        issues.append({"type": "warn", "field": "description", "msg": "Primary keywords not in description"})
        score -= 10

    cta_words = ["köp", "beställ", "bestall", "se", "hitta", "bäst", "billig", "fri frakt", "snabb",
                  "køb", "bestil", "bedst", "gratis fragt",
                  "top", "test", "buy", "order", "shop", "find", "best", "cheap",
                  "free shipping", "fast", "deal", "save", "discount", "offer"]
    has_cta_title = any(w in title_norm for w in cta_words)
    has_cta_desc = any(w in desc_norm for w in cta_words)

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
