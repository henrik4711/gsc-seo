"""
Category page analyzer.
Understands e-commerce page types and validates content against keyword clusters.
"""

import re
from urllib.parse import urlparse
from typing import Optional

try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SEOBot/1.0; +https://mshop.se)"
}


def classify_page_type(url: str, page_data: dict = None) -> dict:
    """
    Classify a page as category, product, blog, or other.
    Uses URL patterns + page structure.
    """
    url_lower = url.lower()
    path = urlparse(url_lower).path.rstrip("/")
    segments = [s for s in path.split("/") if s]

    result = {
        "page_type": "unknown",
        "confidence": "low",
        "signals": [],
    }

    # URL pattern signals
    product_patterns = ["/products/", "/produkt/", "/product/", "/p/"]
    category_patterns = ["/kategori/", "/category/", "/collections/", "/c/"]
    blog_patterns = ["/blog/", "/blogg/", "/artikel/", "/guide/", "/tips/"]

    # Check URL patterns
    if any(p in url_lower for p in product_patterns):
        result["page_type"] = "product"
        result["signals"].append("URL contains product path")
    elif any(p in url_lower for p in blog_patterns):
        result["page_type"] = "blog"
        result["signals"].append("URL contains blog/guide path")
    elif any(p in url_lower for p in category_patterns):
        result["page_type"] = "category"
        result["signals"].append("URL contains category path")

    # For mshop.se specific patterns
    if "mshop.se" in url_lower:
        if len(segments) >= 2 and segments[0] == "sexleksaker":
            result["page_type"] = "category"
            result["signals"].append("mshop.se category URL pattern")
        elif len(segments) == 1 and segments[0] not in ("blog", "om-oss", "kontakt", "kundservice"):
            result["page_type"] = "category"
            result["signals"].append("mshop.se top-level category")

    # Use page data if available
    if page_data:
        schema_types = page_data.get("schema_types", [])
        if any("Product" in str(s) for s in schema_types):
            result["page_type"] = "product"
            result["signals"].append("Product schema detected")
        elif any("Collection" in str(s) or "ItemList" in str(s) for s in schema_types):
            result["page_type"] = "category"
            result["signals"].append("Collection/ItemList schema detected")
        elif any("Article" in str(s) or "BlogPosting" in str(s) for s in schema_types):
            result["page_type"] = "blog"
            result["signals"].append("Article/Blog schema detected")

        # Product count signals (many product links = category page)
        body = page_data.get("body_text", "")
        h2_count = len(page_data.get("h2s", []))
        internal_links = page_data.get("internal_links", 0)

        if internal_links > 20 and h2_count <= 3:
            if result["page_type"] == "unknown":
                result["page_type"] = "category"
            result["signals"].append(f"Many links ({internal_links}) with few headings = product grid")

    if result["page_type"] != "unknown":
        result["confidence"] = "high" if len(result["signals"]) >= 2 else "medium"

    return result


def deep_scrape_category(url: str, timeout: int = 15) -> dict:
    """
    Deep scrape specifically designed for category pages.
    Separates editorial content from product listings.
    """
    if not SCRAPING_AVAILABLE:
        return {"url": url, "error": "scraping not available"}

    result = {
        "url": url,
        "success": False,
        "page_type": "unknown",
        # Editorial content (what we care about for SEO)
        "intro_text": "",
        "intro_word_count": 0,
        "bottom_text": "",
        "bottom_word_count": 0,
        "total_editorial_words": 0,
        # Structure
        "h1": None,
        "h2s": [],
        "h3s": [],
        "has_faq": False,
        "has_buying_guide": False,
        "faq_count": 0,
        # Products
        "product_count": 0,
        "product_names": [],
        # Meta
        "title": None,
        "meta_description": None,
        "canonical": None,
        "schema_types": [],
        # Links
        "internal_links": [],
        "internal_link_count": 0,
        "external_link_count": 0,
        # Images
        "images_total": 0,
        "images_without_alt": 0,
        # Raw
        "full_body_text": "",
    }

    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        result["success"] = True

        # Meta
        title_tag = soup.find("title")
        if title_tag:
            result["title"] = title_tag.get_text(strip=True)

        meta_desc = soup.find("meta", attrs={"name": re.compile("description", re.I)})
        if meta_desc:
            result["meta_description"] = meta_desc.get("content", "").strip()

        canonical = soup.find("link", attrs={"rel": "canonical"})
        if canonical:
            result["canonical"] = canonical.get("href", "")

        # Schema
        for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                import json
                data = json.loads(tag.string or "{}")
                if "@type" in data:
                    result["schema_types"].append(data["@type"])
                if isinstance(data, dict) and data.get("@type") == "FAQPage":
                    result["has_faq"] = True
                    entities = data.get("mainEntity", [])
                    result["faq_count"] = len(entities) if isinstance(entities, list) else 0
            except Exception:
                pass

        # Headings
        h1 = soup.find("h1")
        if h1:
            result["h1"] = h1.get_text(strip=True)
        result["h2s"] = [h.get_text(strip=True) for h in soup.find_all("h2")]
        result["h3s"] = [h.get_text(strip=True) for h in soup.find_all("h3")]

        # Find product grid items (common patterns)
        product_selectors = [
            {"class": re.compile(r"product[-_]?card|product[-_]?item|product[-_]?tile", re.I)},
            {"class": re.compile(r"grid[-_]?item|collection[-_]?item", re.I)},
            {"data-product-id": True},
            {"class": re.compile(r"ProductCard|productCard", re.I)},
        ]
        product_elements = []
        for selector in product_selectors:
            found = soup.find_all(["div", "li", "article", "a"], attrs=selector)
            if found:
                product_elements = found
                break

        if not product_elements:
            # Fallback: count links that look like product links
            domain = urlparse(url).netloc
            product_links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if domain in href or href.startswith("/"):
                    # Deeper URLs with product-like patterns
                    if re.search(r"/products?/|/produkt/|/p/", href, re.I):
                        product_links.append(a)
            product_elements = product_links

        result["product_count"] = len(product_elements)
        for elem in product_elements[:30]:
            name = elem.get_text(strip=True)[:80]
            if name and len(name) > 3:
                result["product_names"].append(name)

        # Remove non-content elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()

        # Try to find editorial text ABOVE the product grid
        main = soup.find("main") or soup.body
        if main:
            # Get all text blocks that appear before product cards
            all_paragraphs = main.find_all(["p", "div"], recursive=True)
            intro_parts = []
            bottom_parts = []
            found_products = False

            for p in all_paragraphs:
                text = p.get_text(strip=True)
                if len(text) < 20:
                    continue
                # Skip if this is inside a product card
                if p.find_parent(attrs={"class": re.compile(r"product|card|grid|item", re.I)}):
                    found_products = True
                    continue
                # Skip navigation-like text
                if p.find_parent(["nav", "footer", "header"]):
                    continue

                if not found_products:
                    intro_parts.append(text)
                else:
                    bottom_parts.append(text)

            result["intro_text"] = " ".join(intro_parts)[:3000]
            result["intro_word_count"] = len(result["intro_text"].split()) if result["intro_text"] else 0
            result["bottom_text"] = " ".join(bottom_parts)[:3000]
            result["bottom_word_count"] = len(result["bottom_text"].split()) if result["bottom_text"] else 0
            result["total_editorial_words"] = result["intro_word_count"] + result["bottom_word_count"]

            # Full body text for keyword analysis
            full_text = main.get_text(separator=" ", strip=True)
            result["full_body_text"] = re.sub(r'\s+', ' ', full_text)[:8000]

        # Check for FAQ section
        faq_headings = [h for h in result["h2s"] + result["h3s"]
                        if re.search(r"faq|frågor|vanliga frågor|sp.rgsm.l", h, re.I)]
        if faq_headings:
            result["has_faq"] = True

        # Check for buying guide
        guide_headings = [h for h in result["h2s"] + result["h3s"]
                          if re.search(r"guide|k.pguide|v.lj|hur väljer|tips|råd", h, re.I)]
        result["has_buying_guide"] = bool(guide_headings)

        # Link analysis
        domain = urlparse(url).netloc
        for a in soup.find_all("a", href=True):
            href = a["href"]
            anchor = a.get_text(strip=True)[:100]
            if href.startswith("http"):
                if domain in href:
                    result["internal_links"].append({"url": href, "anchor": anchor})
                    result["internal_link_count"] += 1
                else:
                    result["external_link_count"] += 1
            elif href.startswith("/"):
                result["internal_links"].append({"url": href, "anchor": anchor})
                result["internal_link_count"] += 1

        # Images
        all_imgs = soup.find_all("img")
        result["images_total"] = len(all_imgs)
        result["images_without_alt"] = sum(1 for img in all_imgs if not img.get("alt", "").strip())

        # Page type classification
        classification = classify_page_type(url, {
            "schema_types": result["schema_types"],
            "body_text": result["full_body_text"],
            "h2s": result["h2s"],
            "internal_links": result["internal_link_count"],
        })
        result["page_type"] = classification["page_type"]

    except Exception as e:
        result["error"] = str(e)

    return result


def audit_category_content(
    page_data: dict,
    cluster_keywords: list,
    gsc_queries: list = None,
) -> dict:
    """
    Audit a category page's content against its keyword cluster.
    Returns detailed assessment with specific issues and recommendations.
    """
    issues = []
    score = 100
    recommendations = []

    page_type = page_data.get("page_type", "unknown")
    intro_words = page_data.get("intro_word_count", 0)
    bottom_words = page_data.get("bottom_word_count", 0)
    total_editorial = page_data.get("total_editorial_words", 0)
    h2s = page_data.get("h2s", [])
    h3s = page_data.get("h3s", [])
    has_faq = page_data.get("has_faq", False)
    has_guide = page_data.get("has_buying_guide", False)
    product_count = page_data.get("product_count", 0)
    full_text = page_data.get("full_body_text", "").lower()

    # ── 1. Editorial content volume ───────────────────────────
    if page_type == "category":
        if total_editorial < 50:
            issues.append({
                "severity": "critical",
                "area": "content",
                "msg": f"Naesten ingen redaktionel tekst ({total_editorial} ord). Kategorisider SKAL have intro + bundtekst.",
            })
            score -= 35
            recommendations.append("Tilfoej 150-300 ord intro-tekst OVER produktgrid")
            recommendations.append("Tilfoej 300-500 ord bundtekst med koepguide/FAQ UNDER produktgrid")
        elif total_editorial < 150:
            issues.append({
                "severity": "warn",
                "area": "content",
                "msg": f"For lidt redaktionel tekst ({total_editorial} ord). Anbefalet: 300-800 ord total.",
            })
            score -= 20
            recommendations.append("Udvid intro og tilfoej bundtekst")
        elif total_editorial < 300:
            issues.append({
                "severity": "info",
                "area": "content",
                "msg": f"Acceptabelt indhold ({total_editorial} ord) men kunne vaere dybere.",
            })
            score -= 5

        # Intro specifically
        if intro_words < 30:
            issues.append({
                "severity": "warn",
                "area": "intro",
                "msg": "Ingen/minimal intro-tekst over produktgrid.",
            })
            score -= 15
            recommendations.append("Tilfoej 80-150 ord intro der forklarer kategorien og hjaelper kunden")

    # ── 2. Keyword coverage ───────────────────────────────────
    all_keywords = list(set((cluster_keywords or []) + (gsc_queries or [])))
    if all_keywords and full_text:
        covered = []
        missing = []
        for kw in all_keywords[:30]:
            kw_lower = kw.lower().strip()
            if not kw_lower:
                continue
            # Check if keyword or its parts appear in text
            kw_parts = kw_lower.split()
            if kw_lower in full_text:
                covered.append(kw)
            elif len(kw_parts) > 1 and all(part in full_text for part in kw_parts):
                covered.append(kw)
            else:
                missing.append(kw)

        coverage_pct = len(covered) / max(len(all_keywords[:30]), 1) * 100

        if coverage_pct < 30:
            issues.append({
                "severity": "critical",
                "area": "keywords",
                "msg": f"Kun {coverage_pct:.0f}% af cluster-keywords daekkes i sidens indhold ({len(covered)}/{len(all_keywords[:30])})",
            })
            score -= 25
        elif coverage_pct < 60:
            issues.append({
                "severity": "warn",
                "area": "keywords",
                "msg": f"{coverage_pct:.0f}% keyword-daekning ({len(covered)}/{len(all_keywords[:30])})",
            })
            score -= 10

        if missing:
            recommendations.append(f"Integrer disse keywords i teksten: {', '.join(missing[:10])}")
    else:
        covered = []
        missing = []
        coverage_pct = 0

    # ── 3. Structure ──────────────────────────────────────────
    editorial_h2s = [h for h in h2s if not re.search(r"produkt|vara|pris|^kr\s", h, re.I)]
    if len(editorial_h2s) < 2 and page_type == "category":
        issues.append({
            "severity": "warn",
            "area": "structure",
            "msg": f"For faa redaktionelle H2-overskrifter ({len(editorial_h2s)}). Brug H2 til at strukturere koepguide/FAQ.",
        })
        score -= 10
        recommendations.append("Tilfoej H2-sektioner: Koepguide, Populaere typer, FAQ")

    # ── 4. FAQ ────────────────────────────────────────────────
    if not has_faq and page_type == "category":
        issues.append({
            "severity": "info",
            "area": "faq",
            "msg": "Ingen FAQ-sektion. FAQ er vaerdifuldt for featured snippets og long-tail keywords.",
        })
        score -= 5
        recommendations.append("Tilfoej 4-6 FAQ spoergsmaal baseret paa GSC-queries")

    # ── 5. Buying guide ───────────────────────────────────────
    if not has_guide and page_type == "category":
        issues.append({
            "severity": "info",
            "area": "guide",
            "msg": "Ingen koepguide. Hjaelper baade konvertering og SEO.",
        })
        score -= 5
        recommendations.append("Tilfoej kort koepguide (Hvad skal man kigge efter? Forskelle mellem typer?)")

    # ── 6. Internal linking ───────────────────────────────────
    internal_links = page_data.get("internal_links", [])
    if len(internal_links) < 5 and page_type != "product":
        issues.append({
            "severity": "warn",
            "area": "links",
            "msg": f"Faa interne links ({len(internal_links)}). Kategorisider boer linke til relaterede kategorier.",
        })
        score -= 5

    return {
        "score": max(0, score),
        "page_type": page_type,
        "issues": issues,
        "recommendations": recommendations,
        "content_stats": {
            "intro_words": intro_words,
            "bottom_words": bottom_words,
            "total_editorial": total_editorial,
            "product_count": product_count,
            "h2_count": len(h2s),
            "editorial_h2_count": len(editorial_h2s) if page_type == "category" else len(h2s),
            "has_faq": has_faq,
            "has_buying_guide": has_guide,
        },
        "keyword_coverage": {
            "total_checked": len(all_keywords[:30]),
            "covered": len(covered),
            "missing": missing[:15],
            "coverage_pct": round(coverage_pct, 1),
        },
    }
