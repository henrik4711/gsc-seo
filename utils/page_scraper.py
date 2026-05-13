"""
Page scraper: fetches landing pages using requests + BeautifulSoup.

NO Playwright — Magento (and most e-commerce platforms) serve fully
rendered HTML on first request, no JS execution needed. Removing
Playwright eliminated repeated browser-launch failures on Railway,
removes a heavy dependency, and makes scrapes ~10x faster.
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


def reset_playwright():
    """No-op kept for backward compat — Playwright was removed."""
    pass


def scrape_page(url: str, timeout: int = 30, bypass_cache: bool = False) -> dict:
    """
    Scrape a URL via requests + BeautifulSoup. Returns dict with
    title, meta, h1/h2/h3, body, links, images, schema, structural
    signals, editorial_images, etc. (full _parse_html output).

    When bypass_cache=True, the request asks intermediaries (Magento
    full-page cache, CDNs) to skip cache:
      - Cache-Control: no-cache, no-store, must-revalidate
      - Pragma: no-cache
      - cache-busting query parameter ?_cb=<timestamp> (most reliable)
    Used by the "Re-scrape + re-check" flow in Page Auditor so the
    user sees the actual current HTML, not a cached snapshot. Off by
    default because normal scrapes benefit from CDN/edge caching.
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
        "_scraper": "requests",
    }
    if not BS4_AVAILABLE:
        result["error"] = "beautifulsoup4 not installed"
        return result
    out = _scrape_with_requests(url, timeout, result, bypass_cache=bypass_cache)
    # Lightweight log event — one line per scraped page (not a full run)
    try:
        from utils.diagnostics import log_event
        log_event(
            "scrape_page",
            url=url,
            success=out.get("success"),
            error=out.get("error"),
            word_count=out.get("word_count"),
            intro_words=out.get("intro_word_count", 0),
            bottom_words=out.get("bottom_word_count", 0),
            editorial_images=out.get("editorial_image_count", 0),
            page_type=out.get("page_type") or out.get("template_type", ""),
        )
    except Exception:
        pass
    return out


def extract_editorial_content(html: str, url: str) -> dict:
    """
    SINGLE SOURCE OF TRUTH for editorial-content extraction across the codebase.

    Used by both _parse_html (scrape_page path, all non-category pages)
    and deep_scrape_category (the category-specific deep-scrape path).
    Eliminates the prior fragmentation where each path had its own
    editorial parser with different rules.

    Returns dict with:
      - intro_text, intro_word_count
      - bottom_text, bottom_word_count, total_editorial_words
      - editorial_images (list of dicts), editorial_image_count, editorial_image_diag
      - editorial_container_candidates (diagnostic)
      - structural_signals (used by classify_page_type)
    """
    out = {
        "intro_text": "", "intro_word_count": 0,
        "bottom_text": "", "bottom_word_count": 0, "total_editorial_words": 0,
        "editorial_images": [], "editorial_image_count": 0,
        "editorial_image_diag": {},
        "editorial_container_candidates": [],
        "structural_signals": {
            "found_intro_classes": [], "found_bottom_classes": [],
            "has_category_description_id": False, "body_classes": [],
        },
    }

    soup = BeautifulSoup(html, "html.parser")
    main_content = (
        soup.find("div", class_="xmx-page-content")
        or soup.find("main")
        or soup.find("article")
        or soup.find("div", role="main")
        or soup.find("div", class_=re.compile(r"^(main|page-content|content-area)", re.I))
        or soup.body
    )

    _PRODUCT_RE = re.compile(
        r"product-card|product-item|products-grid|product-list-item|"
        r"card-product|price-box|swiper-slide|category-product|"
        r"xmx-category-product|xmx-category-grid|xmx-product-grid|"
        r"xmx-products-list|xmx-product-list|xmx-product-tile",
        re.I,
    )

    # EXACT class names — substring match would catch unrelated classes
    # like xmx-short-description, xmx-info-popup-text etc.
    _BOTTOM_EXACT = {
        "xmx-seo-footer-section",
        "xmx-blog-post-content",
        "xmx-description",
        "xmx-help-layout-content",
    }
    _INTRO_EXACT = {
        "xmx-blog-post-head",
    }

    def _has_exact(tag, allowed):
        return bool(set(tag.get("class") or []) & allowed)

    def _text_from_exact(allowed):
        parts = []
        for c in soup.find_all(["div", "section", "article"]):
            if not _has_exact(c, allowed):
                continue
            if c.find_parent(attrs={"class": _PRODUCT_RE}):
                continue
            local = []
            for p_tag in c.find_all(["p", "h1", "h2", "h3", "h4", "li"], recursive=True):
                if p_tag.find_parent(attrs={"class": _PRODUCT_RE}):
                    continue
                t = p_tag.get_text(strip=True)
                if len(t) >= 15:
                    local.append(t)
            if local:
                parts.extend(local)
            else:
                t = c.get_text(separator=" ", strip=True)
                if len(t) >= 50:
                    parts.append(t)
        return parts

    # Structural signals (used by classify_page_type — single source of truth)
    if soup.body:
        out["structural_signals"]["body_classes"] = list(soup.body.get("class") or [])
    for c in soup.find_all(["div", "section", "article"]):
        cls_set = set(c.get("class") or [])
        hit_intro = cls_set & _INTRO_EXACT
        hit_bottom = cls_set & _BOTTOM_EXACT
        if hit_intro:
            out["structural_signals"]["found_intro_classes"].extend(sorted(hit_intro))
        if hit_bottom:
            out["structural_signals"]["found_bottom_classes"].extend(sorted(hit_bottom))
    out["structural_signals"]["found_intro_classes"] = sorted(set(out["structural_signals"]["found_intro_classes"]))
    out["structural_signals"]["found_bottom_classes"] = sorted(set(out["structural_signals"]["found_bottom_classes"]))
    if soup.find(id="category-description"):
        out["structural_signals"]["has_category_description_id"] = True

    # Container-based editorial extraction
    intro_parts = _text_from_exact(_INTRO_EXACT)
    bottom_parts = _text_from_exact(_BOTTOM_EXACT)

    # Category intro: <p id="category-description">
    if not intro_parts:
        for tag in soup.find_all(id="category-description"):
            t = tag.get_text(separator=" ", strip=True)
            if len(t) >= 15:
                intro_parts.append(t)

    # Fallback intro: pre-grid paragraphs in main_content
    if not intro_parts and main_content:
        for p_tag in main_content.find_all(["p", "h1", "h2", "h3"], recursive=True):
            if p_tag.find_parent(attrs={"class": _PRODUCT_RE}):
                break
            if p_tag.find_parent(["nav", "footer", "header"]):
                continue
            t = p_tag.get_text(strip=True)
            if len(t) >= 15:
                intro_parts.append(t)

    # Fallback bottom: post-grid paragraphs
    if not bottom_parts and main_content:
        found_products = False
        for p_tag in main_content.find_all(["p", "h2", "h3"], recursive=True):
            if p_tag.find_parent(attrs={"class": _PRODUCT_RE}):
                found_products = True
                continue
            if p_tag.find_parent(["nav", "footer", "header"]):
                continue
            t = p_tag.get_text(strip=True)
            if len(t) < 15:
                continue
            if found_products:
                bottom_parts.append(t)

    out["intro_text"] = " ".join(intro_parts)[:5000]
    out["intro_word_count"] = len(out["intro_text"].split()) if out["intro_text"] else 0
    out["bottom_text"] = " ".join(bottom_parts)[:25000]
    out["bottom_word_count"] = len(out["bottom_text"].split()) if out["bottom_text"] else 0
    out["total_editorial_words"] = out["intro_word_count"] + out["bottom_word_count"]

    # Editorial images — only from dedicated containers (not product grid)
    _BOTTOM_IMG_RE = re.compile(
        r"xmx-seo-footer-section|xmx-seo-footer-group-content|xmx-seo-footer|"
        r"xmx-blog-post-content|xmx-description|xmx-help-layout-content|"
        r"seo-footer|seo-content|seo-text|category-seo|footer-seo",
        re.I,
    )
    _INTRO_IMG_RE = re.compile(
        r"xmx-blog-post-head|"
        r"category-description|category-intro|xmx-category-description|"
        r"xmx-category-top|xmx-page-top-content|cms-block",
        re.I,
    )
    intro_containers = soup.find_all(["div", "section"], class_=_INTRO_IMG_RE)
    bottom_containers = soup.find_all(["div", "section"], class_=_BOTTOM_IMG_RE)
    # Also try id="category-description" container for intro
    cat_id = soup.find(id="category-description")
    if cat_id and cat_id not in intro_containers:
        intro_containers = list(intro_containers) + [cat_id]

    editorial_images = []
    seen_src = set()
    diag = {"intro_containers": len(intro_containers), "bottom_containers": len(bottom_containers),
            "total": 0, "skipped_product": 0, "skipped_nav": 0,
            "skipped_no_src": 0, "skipped_dupe": 0, "kept": 0}

    def _capture(container, section):
        for img in container.find_all("img"):
            diag["total"] += 1
            if img.find_parent(attrs={"class": _PRODUCT_RE}):
                diag["skipped_product"] += 1; continue
            if img.find_parent(["nav", "header"]):
                diag["skipped_nav"] += 1; continue
            cands = [
                img.get("src") or "", img.get("data-src") or "",
                img.get("data-lazy-src") or "", img.get("data-original") or "",
                (img.get("data-srcset", "") or "").split(" ")[0],
                (img.get("srcset", "") or "").split(" ")[0],
            ]
            src = next((c for c in cands if c and not c.startswith("data:")), "")
            if not src:
                diag["skipped_no_src"] += 1; continue
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = f"https://{urlparse(url).netloc}{src}"
            if src in seen_src:
                diag["skipped_dupe"] += 1; continue
            seen_src.add(src)
            diag["kept"] += 1
            wrap = img.find_parent("a")
            fig = img.find_parent("figure")
            cap = ""
            if fig:
                ct = fig.find("figcaption")
                if ct:
                    cap = ct.get_text(strip=True)
            editorial_images.append({
                "src": src,
                "alt": (img.get("alt") or "").strip(),
                "width": img.get("width", ""),
                "link_href": wrap.get("href", "") if wrap else "",
                "caption": cap,
                "section": section,
            })

    for c in intro_containers:
        _capture(c, "intro")
    for c in bottom_containers:
        _capture(c, "bottom")

    out["editorial_images"] = editorial_images
    out["editorial_image_count"] = len(editorial_images)
    out["editorial_image_diag"] = diag

    # Container candidates diagnostic
    cand = []
    skip = re.compile(
        r"product-card|product-item|card-product|price-box|swiper-slide|"
        r"category-product|product-list-item",
        re.I,
    )
    for d in soup.find_all(["div", "section"]):
        cls = " ".join(d.get("class") or [])
        if not cls or skip.search(cls):
            continue
        imgs = d.find_all("img", recursive=True)
        ps = d.find_all(["p", "h2", "h3"], recursive=True)
        tl = sum(len(p.get_text(strip=True)) for p in ps)
        if imgs and 100 < tl < 20000:
            cand.append({"classes": cls[:200], "text_chars": tl, "imgs": len(imgs)})
    seen = set()
    dedup = []
    for c in sorted(cand, key=lambda x: -x["imgs"]):
        if c["classes"] in seen: continue
        seen.add(c["classes"])
        dedup.append(c)
    out["editorial_container_candidates"] = dedup[:15]

    return out


def _parse_html(result: dict, soup, html: str, url: str) -> dict:
    """Parse HTML into result dict. Shared by normal scrape and retry."""
    # Meta + headings + schema — all from utils.html_extractors (single source)
    from utils.html_extractors import (
        extract_meta, extract_headings, extract_schema_types,
        extract_internal_links, count_images_without_alt,
        find_main_content,
    )
    meta = extract_meta(soup)
    result["title"] = meta["title"]
    result["title_length"] = meta["title_length"]
    result["meta_description"] = meta["meta_description"]
    result["description_length"] = meta["description_length"]
    result["canonical"] = meta["canonical"]

    headings = extract_headings(soup)
    result["h1"] = headings["h1"]
    result["h2s"] = headings["h2s"]
    result["h3s"] = headings["h3s"]

    result["schema_types"] = extract_schema_types(soup)

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

    # Capture SEO footer BEFORE decomposing footer elements
    seo_footer_pw = text_soup.find("div", class_=re.compile(r"seo-footer|seo-content|seo-text|category-seo|footer-seo", re.I))
    seo_footer_text_pw = ""
    seo_footer_parts_pw = []
    if seo_footer_pw:
        seo_footer_text_pw = seo_footer_pw.get_text(separator=" ", strip=True)
        for p_tag in seo_footer_pw.find_all(["p", "h2", "h3", "div"], recursive=True):
            text = p_tag.get_text(strip=True)
            if len(text) >= 15:
                seo_footer_parts_pw.append(text)

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
        # Also include SEO footer text (captured before decompose)
        if seo_footer_text_pw:
            raw_text += " " + seo_footer_text_pw
        body_text = re.sub(r'\s+', ' ', raw_text).strip()
        result["body_text"] = body_text[:20000]
        result["word_count"] = len(body_text.split())

        # ── Editorial extraction — DELEGATED to single source of truth ──
        # All editorial fields (intro_text, bottom_text, editorial_images,
        # structural_signals, container candidates) come from the shared
        # extract_editorial_content() function used by both this path AND
        # deep_scrape_category() — no parallel implementations to drift apart.
        try:
            ed = extract_editorial_content(html, url)
            for k, v in ed.items():
                result[k] = v
        except Exception as _ed_err:
            print(f"[scraper] editorial extraction failed: {_ed_err}")

    # ── Links: extract from content area ──────────────────────
    # Internal/external links — single source of truth
    link_soup = BeautifulSoup(html, "html.parser")
    links = extract_internal_links(link_soup, url)
    result["internal_links"] = links["internal_links"]
    result["internal_link_count"] = links["internal_link_count"]
    result["external_links"] = links["external_link_count"]

    # Images without alt — single source of truth
    if main_content:
        img_stats = count_images_without_alt(main_content)
        result["images_without_alt"] = img_stats["images_without_alt"]

    return result


def _scrape_with_requests(url: str, timeout: int = 30, result: dict = None, bypass_cache: bool = False) -> dict:
    """Fetch HTML with requests and parse via shared _parse_html.

    bypass_cache=True asks Magento full-page cache / CDNs to skip the
    cached copy. Done both via headers (no-cache, no-store) AND a
    cache-busting query parameter (?_cb=<timestamp>) — the query param
    is the most reliable defeater because most edge caches treat the
    URL+querystring as the cache key.
    """
    if result is None:
        result = {"url": url, "success": False, "error": None,
                  "title": None, "meta_description": None, "h1": None,
                  "h2s": [], "h3s": [], "body_text": "", "word_count": 0,
                  "canonical": None, "schema_types": [],
                  "internal_links": [], "internal_link_count": 0,
                  "external_links": 0, "images_without_alt": 0,
                  "title_length": 0, "description_length": 0}
    try:
        import requests
        # Build the request URL — append a cache-busting query param
        # when bypass_cache is True. Done before sending so the param
        # appears in the URL the cache keys on.
        request_url = url
        if bypass_cache:
            import time as _t
            sep = "&" if ("?" in url) else "?"
            request_url = f"{url}{sep}_cb={int(_t.time())}"

        # Build headers — add no-cache directives only when bypassing.
        # Non-bypass scrapes leave headers minimal so CDNs serve cached
        # responses (faster batch scraping).
        _headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        if bypass_cache:
            _headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            _headers["Pragma"] = "no-cache"
            _headers["Expires"] = "0"

        resp = requests.get(request_url, headers=_headers,
                            timeout=max(timeout, 30), allow_redirects=True)
        if resp.status_code == 403:
            result["error"] = f"HTTP 403 Forbidden (bot-blocked)"
            return result
        if resp.status_code >= 400:
            result["error"] = f"HTTP {resp.status_code} from {url}"
            return result
        html = resp.text
        if not html or len(html) < 500:
            result["error"] = f"Response too short ({len(html)} bytes)"
            return result
        result["success"] = True
        # Cache raw HTML to disk so we can re-parse later without re-fetching
        try:
            from utils.html_cache import save_html
            save_html(url, html)
        except Exception:
            pass
        # Delegate ALL parsing to shared _parse_html — same logic as
        # the Playwright path: title, meta, editorial containers,
        # editorial images, structural signals, container candidates.
        return _parse_html(result, BeautifulSoup(html, "html.parser"), html, url)
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
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
