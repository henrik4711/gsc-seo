"""
Category page analyzer.
Deep validation of e-commerce page content against keyword clusters,
internal linking structure, and E-E-A-T trust signals.
"""

import re
import json
from urllib.parse import urlparse
from typing import Optional
from collections import Counter

try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SEOBot/1.0; +https://mshop.se)"
}


# ══════════════════════════════════════════════════════════════════
# 1. PAGE TYPE CLASSIFICATION
# ══════════════════════════════════════════════════════════════════

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

    product_patterns = ["/products/", "/produkt/", "/product/", "/p/"]
    category_patterns = ["/kategori/", "/category/", "/collections/", "/c/"]
    blog_patterns = ["/blog/", "/blogg/", "/artikel/", "/guide/", "/tips/"]

    if any(p in url_lower for p in product_patterns):
        result["page_type"] = "product"
        result["signals"].append("URL contains product path")
    elif any(p in url_lower for p in blog_patterns):
        result["page_type"] = "blog"
        result["signals"].append("URL contains blog/guide path")
    elif any(p in url_lower for p in category_patterns):
        result["page_type"] = "category"
        result["signals"].append("URL contains category path")

    if "mshop.se" in url_lower:
        if len(segments) >= 2 and segments[0] == "sexleksaker":
            result["page_type"] = "category"
            result["signals"].append("mshop.se category URL pattern")
        elif len(segments) == 1 and segments[0] not in ("blog", "om-oss", "kontakt", "kundservice"):
            result["page_type"] = "category"
            result["signals"].append("mshop.se top-level category")

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

        internal_links = page_data.get("internal_links", 0)
        if isinstance(internal_links, list):
            internal_links = len(internal_links)
        h2_count = len(page_data.get("h2s", []))
        if internal_links > 20 and h2_count <= 3:
            if result["page_type"] == "unknown":
                result["page_type"] = "category"
            result["signals"].append(f"Many links ({internal_links}) with few headings = product grid")

    if result["page_type"] != "unknown":
        result["confidence"] = "high" if len(result["signals"]) >= 2 else "medium"

    return result


# ══════════════════════════════════════════════════════════════════
# 2. DEEP CATEGORY SCRAPER
# ══════════════════════════════════════════════════════════════════

def deep_scrape_category(url: str, timeout: int = 15) -> dict:
    """
    Deep scrape for category pages. Extracts editorial content, product grid,
    internal link structure with anchors, trust signals, and structured data.
    """
    if not SCRAPING_AVAILABLE:
        return {"url": url, "error": "scraping not available", "success": False}

    result = {
        "url": url,
        "success": False,
        "page_type": "unknown",
        # Editorial content
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
        "schema_raw": [],
        # Links — detailed
        "internal_links": [],
        "internal_link_count": 0,
        "external_link_count": 0,
        "category_links": [],       # links to other category-like URLs
        "product_links_on_page": [], # links to product pages
        # Trust / E-E-A-T signals
        "has_reviews": False,
        "review_count": 0,
        "has_author": False,
        "has_last_modified": False,
        "last_modified": None,
        "has_breadcrumb": False,
        "has_organization_schema": False,
        "has_aggregate_rating": False,
        "trust_signals": [],
        # Images
        "images_total": 0,
        "images_without_alt": 0,
        # Raw
        "full_body_text": "",
    }

    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        result["success"] = True
        domain = urlparse(url).netloc

        # ── Meta ──────────────────────────────────────────────
        title_tag = soup.find("title")
        if title_tag:
            result["title"] = title_tag.get_text(strip=True)

        meta_desc = soup.find("meta", attrs={"name": re.compile("description", re.I)})
        if meta_desc:
            result["meta_description"] = meta_desc.get("content", "").strip()

        canonical = soup.find("link", attrs={"rel": "canonical"})
        if canonical:
            result["canonical"] = canonical.get("href", "")

        # Last-modified
        last_mod = resp.headers.get("Last-Modified")
        if last_mod:
            result["has_last_modified"] = True
            result["last_modified"] = last_mod
            result["trust_signals"].append(f"Last-Modified header: {last_mod}")

        meta_date = soup.find("meta", attrs={"property": re.compile("modified_time|updated_time", re.I)})
        if meta_date:
            result["has_last_modified"] = True
            result["last_modified"] = meta_date.get("content", "")
            result["trust_signals"].append(f"Article modified: {result['last_modified']}")

        # ── Structured Data (thorough) ────────────────────────
        for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(tag.string or "{}")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    stype = item.get("@type", "")
                    if stype:
                        result["schema_types"].append(stype)
                    result["schema_raw"].append(item)

                    # FAQ schema
                    if stype == "FAQPage":
                        result["has_faq"] = True
                        entities = item.get("mainEntity", [])
                        result["faq_count"] = len(entities) if isinstance(entities, list) else 0
                        result["trust_signals"].append(f"FAQPage schema med {result['faq_count']} spoergsmaal")

                    # Review / Rating
                    if stype in ("Review", "AggregateRating") or "aggregateRating" in item:
                        result["has_aggregate_rating"] = True
                        result["has_reviews"] = True
                        agg = item.get("aggregateRating", item)
                        rc = agg.get("reviewCount") or agg.get("ratingCount", 0)
                        result["review_count"] = max(result["review_count"], int(rc) if rc else 0)
                        result["trust_signals"].append(f"AggregateRating: {rc} reviews")

                    # Breadcrumb
                    if stype == "BreadcrumbList":
                        result["has_breadcrumb"] = True
                        result["trust_signals"].append("BreadcrumbList schema")

                    # Organization
                    if stype in ("Organization", "LocalBusiness", "Store"):
                        result["has_organization_schema"] = True
                        result["trust_signals"].append(f"{stype} schema")

                    # Product with review
                    if stype == "Product" and "aggregateRating" in item:
                        result["has_aggregate_rating"] = True
                        result["has_reviews"] = True

                    # ItemList (category signal)
                    if stype == "ItemList":
                        items_in_list = item.get("itemListElement", [])
                        result["trust_signals"].append(f"ItemList schema med {len(items_in_list)} items")

            except Exception:
                pass

        # ── Headings ──────────────────────────────────────────
        h1 = soup.find("h1")
        if h1:
            result["h1"] = h1.get_text(strip=True)
        result["h2s"] = [h.get_text(strip=True) for h in soup.find_all("h2")]
        result["h3s"] = [h.get_text(strip=True) for h in soup.find_all("h3")]

        # ── Review signals in HTML (not just schema) ──────────
        review_patterns = re.compile(
            r"review|recension|omdöme|betyg|stjärn|rating|stars?[\s-]?rating",
            re.I
        )
        review_elements = soup.find_all(
            ["div", "section", "span"],
            attrs={"class": review_patterns}
        )
        if review_elements:
            result["has_reviews"] = True
            result["trust_signals"].append(f"{len(review_elements)} review-element i HTML")

        # Author signals
        author_el = soup.find(attrs={"class": re.compile(r"author|byline|writer", re.I)})
        if author_el:
            result["has_author"] = True
            result["trust_signals"].append(f"Forfatterinfo: {author_el.get_text(strip=True)[:60]}")
        author_meta = soup.find("meta", attrs={"name": "author"})
        if author_meta:
            result["has_author"] = True
            result["trust_signals"].append(f"Meta author: {author_meta.get('content', '')}")

        # ── Product grid detection ────────────────────────────
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
            product_links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if (domain in href or href.startswith("/")) and re.search(r"/products?/|/produkt/|/p/", href, re.I):
                    product_links.append(a)
            product_elements = product_links

        result["product_count"] = len(product_elements)
        for elem in product_elements[:30]:
            name = elem.get_text(strip=True)[:80]
            if name and len(name) > 3:
                result["product_names"].append(name)

        # ── Remove non-content for text extraction ────────────
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()

        # ── Editorial text separation ─────────────────────────
        main = soup.find("main") or soup.body
        if main:
            all_paragraphs = main.find_all(["p", "div"], recursive=True)
            intro_parts = []
            bottom_parts = []
            found_products = False

            for p in all_paragraphs:
                text = p.get_text(strip=True)
                if len(text) < 20:
                    continue
                if p.find_parent(attrs={"class": re.compile(r"product|card|grid|item", re.I)}):
                    found_products = True
                    continue
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

            full_text = main.get_text(separator=" ", strip=True)
            result["full_body_text"] = re.sub(r'\s+', ' ', full_text)[:8000]

        # ── FAQ / Guide detection ─────────────────────────────
        faq_headings = [h for h in result["h2s"] + result["h3s"]
                        if re.search(r"faq|frågor|vanliga frågor|sp.rgsm.l", h, re.I)]
        if faq_headings:
            result["has_faq"] = True

        guide_headings = [h for h in result["h2s"] + result["h3s"]
                          if re.search(r"guide|k.pguide|v.lj|hur väljer|tips|råd", h, re.I)]
        result["has_buying_guide"] = bool(guide_headings)

        # ── Link analysis — detailed with classification ──────
        for a in soup.find_all("a", href=True):
            href = a["href"]
            anchor = a.get_text(strip=True)[:100]
            is_internal = False

            if href.startswith("http"):
                if domain in href:
                    is_internal = True
                else:
                    result["external_link_count"] += 1
            elif href.startswith("/"):
                is_internal = True

            if is_internal:
                link_info = {"url": href, "anchor": anchor}
                result["internal_links"].append(link_info)
                result["internal_link_count"] += 1

                # Classify: is this a category link or product link?
                href_lower = href.lower()
                if re.search(r"/products?/|/produkt/|/p/", href_lower):
                    result["product_links_on_page"].append(link_info)
                elif (re.search(r"/kategori/|/category/|/collections?/|/sexleksaker", href_lower)
                      or (href.count("/") <= 3 and not re.search(r"\.\w{2,4}$", href))):
                    # Category-like: short paths, no file extension
                    result["category_links"].append(link_info)

        # Images
        all_imgs = soup.find_all("img")
        result["images_total"] = len(all_imgs)
        result["images_without_alt"] = sum(1 for img in all_imgs if not img.get("alt", "").strip())

        # Page type
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


# ══════════════════════════════════════════════════════════════════
# 3. TOPIC-CLUSTER CONTENT VALIDATION
# ══════════════════════════════════════════════════════════════════

def _group_queries_into_subtopics(queries: list) -> list:
    """
    Group a flat list of queries into semantic sub-topics based on
    shared terms. Returns list of {"topic": str, "queries": list}.
    """
    if not queries:
        return []

    # Extract significant terms (2+ chars, not stopwords)
    stopwords = {"i", "och", "för", "med", "på", "av", "en", "ett", "den",
                 "det", "de", "till", "som", "är", "att", "the", "and",
                 "for", "with", "in", "of", "to", "a", "an", "best",
                 "bra", "billig", "billiga", "bäst", "bästa", "köp",
                 "online", "pris", "sex"}

    query_terms = {}
    for q in queries:
        terms = set(t for t in q.lower().split() if len(t) > 2 and t not in stopwords)
        query_terms[q] = terms

    # Find common term pairs/singles that define sub-topics
    term_pairs = Counter()
    for q, terms in query_terms.items():
        tlist = sorted(terms)
        for t in tlist:
            term_pairs[t] += 1
        for i, t1 in enumerate(tlist):
            for t2 in tlist[i+1:]:
                term_pairs[f"{t1}+{t2}"] += 1

    # Pick top sub-topic anchors (terms appearing in 2+ queries)
    anchors = [(term, count) for term, count in term_pairs.items()
               if count >= 2 and "+" in term]
    anchors.sort(key=lambda x: -x[1])

    # Assign queries to sub-topics
    used = set()
    subtopics = []
    for anchor, _ in anchors[:10]:
        parts = set(anchor.split("+"))
        matching = [q for q in queries if q not in used
                    and parts.issubset(query_terms.get(q, set()))]
        if matching:
            subtopics.append({
                "topic": anchor.replace("+", " "),
                "queries": matching,
                "terms": parts,
            })
            used.update(matching)

    # Remaining queries as individual sub-topics
    remaining = [q for q in queries if q not in used]
    if remaining:
        # Group remaining by single dominant term
        single_terms = Counter()
        for q in remaining:
            for t in query_terms.get(q, set()):
                single_terms[t] += 1
        for term, count in single_terms.most_common(5):
            if count >= 2:
                matching = [q for q in remaining if q not in used
                            and term in query_terms.get(q, set())]
                if matching:
                    subtopics.append({
                        "topic": term,
                        "queries": matching,
                        "terms": {term},
                    })
                    used.update(matching)

    # Truly orphan queries
    orphans = [q for q in queries if q not in used]
    if orphans:
        subtopics.append({
            "topic": "(oevrige)",
            "queries": orphans,
            "terms": set(),
        })

    return subtopics


def audit_category_content(
    page_data: dict,
    cluster_keywords: list,
    gsc_queries: list = None,
    topic_clusters: dict = None,
    page_authority: object = None,
) -> dict:
    """
    Deep audit of category page content against keyword cluster.
    Checks: topic coverage, keyword placement, internal linking,
    trust signals, content structure, and gives specific recommendations.
    """
    issues = []
    score = 100
    recommendations = []

    page_type = page_data.get("page_type", "unknown")
    url = page_data.get("url", "")
    intro_text = page_data.get("intro_text", "")
    intro_words = page_data.get("intro_word_count", 0)
    bottom_text = page_data.get("bottom_text", "")
    bottom_words = page_data.get("bottom_word_count", 0)
    total_editorial = page_data.get("total_editorial_words", 0)
    h1 = (page_data.get("h1") or "").lower()
    h2s = page_data.get("h2s", [])
    h3s = page_data.get("h3s", [])
    has_faq = page_data.get("has_faq", False)
    has_guide = page_data.get("has_buying_guide", False)
    product_count = page_data.get("product_count", 0)
    full_text = page_data.get("full_body_text", "").lower()
    editorial_text = (intro_text + " " + bottom_text).lower()

    all_keywords = list(set((cluster_keywords or []) + (gsc_queries or [])))

    # ═══════════════════════════════════════════════════════════
    # A. EDITORIAL CONTENT VOLUME
    # ═══════════════════════════════════════════════════════════
    if page_type == "category":
        if total_editorial < 50:
            issues.append({
                "severity": "critical", "area": "content_volume",
                "msg": f"Naesten ingen redaktionel tekst ({total_editorial} ord). Kategorisider SKAL have intro + bundtekst.",
            })
            score -= 30
            recommendations.append("Tilfoej 150-300 ord intro-tekst OVER produktgrid")
            recommendations.append("Tilfoej 300-500 ord bundtekst med koepguide/FAQ UNDER produktgrid")
        elif total_editorial < 150:
            issues.append({
                "severity": "warn", "area": "content_volume",
                "msg": f"For lidt redaktionel tekst ({total_editorial} ord). Anbefalet: 300-800 ord total.",
            })
            score -= 15
        elif total_editorial < 300:
            issues.append({
                "severity": "info", "area": "content_volume",
                "msg": f"Acceptabelt indhold ({total_editorial} ord) men kan vaere dybere.",
            })
            score -= 5

        if intro_words < 30:
            issues.append({
                "severity": "warn", "area": "intro",
                "msg": "Ingen/minimal intro-tekst over produktgrid. Google og brugere ser dette foerst.",
            })
            score -= 10
            recommendations.append("Tilfoej 80-150 ord intro der forklarer kategorien og hjaelper kunden vaelge")

    # ═══════════════════════════════════════════════════════════
    # B. TOPIC-LEVEL COVERAGE (not just keywords)
    # ═══════════════════════════════════════════════════════════
    subtopics = _group_queries_into_subtopics(all_keywords)
    subtopic_results = []
    covered_topics = 0
    total_topics = len([s for s in subtopics if s["topic"] != "(oevrige)"])

    for st_item in subtopics:
        if st_item["topic"] == "(oevrige)":
            continue
        # Check if ANY of the sub-topic's terms appear in editorial text
        terms = st_item["terms"]
        term_hits = sum(1 for t in terms if t in editorial_text)
        query_hits = sum(1 for q in st_item["queries"] if q.lower() in full_text)
        partial_hits = sum(1 for q in st_item["queries"]
                          if all(part in full_text for part in q.lower().split()))

        if term_hits == len(terms) or query_hits > 0 or partial_hits > 0:
            status = "covered"
            covered_topics += 1
        elif term_hits > 0:
            status = "partial"
            covered_topics += 0.5
        else:
            status = "missing"

        subtopic_results.append({
            "topic": st_item["topic"],
            "queries": st_item["queries"][:5],
            "query_count": len(st_item["queries"]),
            "status": status,
            "terms_found": term_hits,
            "terms_total": len(terms),
        })

    topic_coverage_pct = (covered_topics / max(total_topics, 1)) * 100

    if total_topics > 0:
        if topic_coverage_pct < 30:
            issues.append({
                "severity": "critical", "area": "topic_coverage",
                "msg": f"Kun {topic_coverage_pct:.0f}% af cluster-emner daekkes i sidens tekst ({covered_topics:.0f}/{total_topics} emner)",
            })
            score -= 25
        elif topic_coverage_pct < 60:
            issues.append({
                "severity": "warn", "area": "topic_coverage",
                "msg": f"{topic_coverage_pct:.0f}% af cluster-emner daekkes ({covered_topics:.0f}/{total_topics})",
            })
            score -= 12

        missing_topics = [s for s in subtopic_results if s["status"] == "missing"]
        if missing_topics:
            topic_names = [s["topic"] for s in missing_topics[:5]]
            recommendations.append(
                f"Tilfoej indhold om disse emner: {', '.join(topic_names)}"
            )
            for mt in missing_topics[:3]:
                recommendations.append(
                    f"  -> Emne '{mt['topic']}' mangler helt ({mt['query_count']} queries: {', '.join(mt['queries'][:3])})"
                )

    # ═══════════════════════════════════════════════════════════
    # C. KEYWORD PLACEMENT QUALITY
    # ═══════════════════════════════════════════════════════════
    covered_kws = []
    missing_kws = []
    kw_in_h1 = 0
    kw_in_h2 = 0
    kw_in_intro = 0

    h2_text = " ".join(h2s).lower()

    for kw in all_keywords[:30]:
        kw_lower = kw.lower().strip()
        if not kw_lower:
            continue
        kw_parts = kw_lower.split()
        found = (kw_lower in full_text or
                 (len(kw_parts) > 1 and all(part in full_text for part in kw_parts)))
        if found:
            covered_kws.append(kw)
            if kw_lower in h1 or all(p in h1 for p in kw_parts):
                kw_in_h1 += 1
            if kw_lower in h2_text or all(p in h2_text for p in kw_parts):
                kw_in_h2 += 1
            if kw_lower in intro_text.lower():
                kw_in_intro += 1
        else:
            missing_kws.append(kw)

    kw_coverage_pct = len(covered_kws) / max(len(all_keywords[:30]), 1) * 100

    if kw_coverage_pct < 30:
        issues.append({
            "severity": "critical", "area": "keyword_coverage",
            "msg": f"Kun {kw_coverage_pct:.0f}% af keywords i sidens tekst ({len(covered_kws)}/{len(all_keywords[:30])})",
        })
        score -= 15
    elif kw_coverage_pct < 60:
        issues.append({
            "severity": "warn", "area": "keyword_coverage",
            "msg": f"{kw_coverage_pct:.0f}% keyword-daekning ({len(covered_kws)}/{len(all_keywords[:30])})",
        })
        score -= 8

    # Keyword in H1
    if all_keywords and kw_in_h1 == 0:
        issues.append({
            "severity": "warn", "area": "keyword_placement",
            "msg": "Intet primaert keyword i H1. H1 skal indeholde hoved-keyword.",
        })
        score -= 5

    # Keyword in first paragraph
    if all_keywords and kw_in_intro == 0 and intro_text:
        issues.append({
            "severity": "warn", "area": "keyword_placement",
            "msg": "Intet keyword i intro-teksten. Foerste afsnit skal indeholde hoved-keyword.",
        })
        score -= 3

    if missing_kws:
        recommendations.append(f"Integrer disse keywords naturligt: {', '.join(missing_kws[:8])}")

    # ═══════════════════════════════════════════════════════════
    # D. CONTENT STRUCTURE
    # ═══════════════════════════════════════════════════════════
    editorial_h2s = [h for h in h2s if not re.search(r"produkt|vara|pris|^kr\s", h, re.I)]
    if len(editorial_h2s) < 2 and page_type == "category":
        issues.append({
            "severity": "warn", "area": "structure",
            "msg": f"For faa redaktionelle H2-overskrifter ({len(editorial_h2s)}). Strukturer med H2 for koepguide/FAQ/typer.",
        })
        score -= 8
        recommendations.append("Tilfoej H2-sektioner: 'Typer af [kategori]', 'Saadan vaelger du', 'FAQ'")

    if not has_faq and page_type == "category":
        issues.append({
            "severity": "warn", "area": "faq",
            "msg": "Ingen FAQ. FAQ er vaerdifuldt for featured snippets og long-tail keywords.",
        })
        score -= 5
        recommendations.append("Tilfoej 4-6 FAQ baseret paa GSC long-tail queries")

    if not has_guide and page_type == "category":
        issues.append({
            "severity": "info", "area": "guide",
            "msg": "Ingen koepguide-sektion.",
        })
        score -= 3
        recommendations.append("Tilfoej koepguide: 'Hvad skal man kigge efter?', 'Forskelle mellem typer'")

    # ═══════════════════════════════════════════════════════════
    # E. INTERNAL LINKING ANALYSIS
    # ═══════════════════════════════════════════════════════════
    internal_links = page_data.get("internal_links", [])
    link_count = internal_links if isinstance(internal_links, int) else len(internal_links)
    category_links = page_data.get("category_links", [])
    product_links_on_page = page_data.get("product_links_on_page", [])

    linking_issues = _audit_internal_linking(
        url, internal_links, category_links, product_links_on_page,
        all_keywords, page_type, topic_clusters
    )
    for li in linking_issues["issues"]:
        issues.append(li)
    score -= linking_issues["penalty"]
    recommendations.extend(linking_issues["recommendations"])

    # ═══════════════════════════════════════════════════════════
    # F. TRUST & E-E-A-T SIGNALS
    # ═══════════════════════════════════════════════════════════
    trust_result = _audit_trust_signals(page_data, page_type)
    for ti in trust_result["issues"]:
        issues.append(ti)
    score -= trust_result["penalty"]
    recommendations.extend(trust_result["recommendations"])

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
            "covered": len(covered_kws),
            "missing": missing_kws[:15],
            "coverage_pct": round(kw_coverage_pct, 1),
            "in_h1": kw_in_h1,
            "in_h2": kw_in_h2,
            "in_intro": kw_in_intro,
        },
        "topic_coverage": {
            "subtopics": subtopic_results,
            "total_topics": total_topics,
            "covered_topics": round(covered_topics, 1),
            "coverage_pct": round(topic_coverage_pct, 1),
        },
        "linking": linking_issues["details"],
        "trust": trust_result["details"],
    }


# ══════════════════════════════════════════════════════════════════
# 4. INTERNAL LINKING AUDIT
# ══════════════════════════════════════════════════════════════════

def _audit_internal_linking(
    url, internal_links, category_links, product_links_on_page,
    keywords, page_type, topic_clusters=None,
) -> dict:
    """
    Validate internal linking:
    - Does the page link to related categories (sibling/child)?
    - Are anchor texts keyword-rich?
    - Are there enough cross-links?
    - Does the cluster data show pages that SHOULD be linked?
    """
    issues = []
    recommendations = []
    penalty = 0

    link_count = internal_links if isinstance(internal_links, int) else len(internal_links)
    cat_link_count = len(category_links) if isinstance(category_links, list) else 0
    prod_link_count = len(product_links_on_page) if isinstance(product_links_on_page, list) else 0

    # Basic link count
    if link_count < 5 and page_type == "category":
        issues.append({
            "severity": "warn", "area": "internal_links",
            "msg": f"Faa interne links ({link_count}). Kategorisider boer linke til relaterede kategorier og guides.",
        })
        penalty += 5

    # Category cross-links
    if page_type == "category" and cat_link_count < 2:
        issues.append({
            "severity": "warn", "area": "category_links",
            "msg": f"Kun {cat_link_count} links til andre kategorier. Tilfoej links til relaterede/underkategorier.",
        })
        penalty += 5
        recommendations.append("Tilfoej links til relaterede kategorier i bundteksten (f.eks. 'Se ogsaa: [relateret kategori]')")

    # Anchor text quality
    if isinstance(internal_links, list) and internal_links:
        anchors = [l.get("anchor", "") for l in internal_links if l.get("anchor")]
        empty_anchors = sum(1 for a in anchors if not a.strip() or a.strip() in (".", ">", "Læs mere", "Klik her", "Se mere"))
        keyword_anchors = 0
        if keywords:
            kw_lower = set(k.lower() for k in keywords[:10])
            for anchor in anchors:
                if any(kw in anchor.lower() for kw in kw_lower):
                    keyword_anchors += 1

        if len(anchors) > 0 and empty_anchors / len(anchors) > 0.5:
            issues.append({
                "severity": "info", "area": "anchor_text",
                "msg": f"{empty_anchors}/{len(anchors)} interne links har tom/generisk anchor-tekst.",
            })
            penalty += 2

        if len(anchors) > 5 and keyword_anchors == 0:
            issues.append({
                "severity": "info", "area": "anchor_text",
                "msg": "Ingen interne link-anchors indeholder target keywords.",
            })
            penalty += 2
            recommendations.append("Brug keyword-rige anchor-tekster i interne links (ikke 'klik her')")

    # Cross-reference with topic clusters — find pages that SHOULD be linked
    missing_links = []
    if topic_clusters and isinstance(internal_links, list):
        linked_urls = set()
        for l in internal_links:
            u = l.get("url", "")
            if u.startswith("/"):
                domain = urlparse(url).netloc
                u = f"https://{domain}{u}"
            linked_urls.add(u.rstrip("/").lower())

        # Find pages in same clusters that we don't link to
        page_topics = topic_clusters.get("page_topics", {})
        my_topics = page_topics.get(url, [])
        my_topic_names = set(t.get("topic", "") for t in my_topics)

        for other_url, other_topics in page_topics.items():
            if other_url.rstrip("/").lower() == url.rstrip("/").lower():
                continue
            other_topic_names = set(t.get("topic", "") for t in other_topics)
            shared = my_topic_names & other_topic_names
            if shared and other_url.rstrip("/").lower() not in linked_urls:
                missing_links.append({
                    "url": other_url,
                    "shared_topics": list(shared)[:3],
                    "shared_count": len(shared),
                })

    if missing_links:
        missing_links.sort(key=lambda x: -x["shared_count"])
        top_missing = missing_links[:5]
        issues.append({
            "severity": "warn", "area": "missing_crosslinks",
            "msg": f"{len(missing_links)} relaterede sider i samme topic-cluster er IKKE linket fra denne side.",
        })
        penalty += min(len(missing_links), 5)
        for ml in top_missing:
            short_url = ml["url"].replace("https://", "").replace("http://", "")
            recommendations.append(
                f"Mangler link til: {short_url} (faelles topics: {', '.join(ml['shared_topics'][:2])})"
            )

    return {
        "issues": issues,
        "recommendations": recommendations,
        "penalty": penalty,
        "details": {
            "total_internal": link_count,
            "category_links": cat_link_count,
            "product_links": prod_link_count,
            "missing_crosslinks": missing_links[:10],
            "anchor_quality": "checked" if isinstance(internal_links, list) else "not_available",
        },
    }


# ══════════════════════════════════════════════════════════════════
# 5. TRUST & E-E-A-T AUDIT
# ══════════════════════════════════════════════════════════════════

def _audit_trust_signals(page_data: dict, page_type: str) -> dict:
    """
    Check E-E-A-T trust signals:
    - Schema markup (BreadcrumbList, FAQ, Organization, AggregateRating)
    - Reviews/ratings
    - Author information
    - Date/freshness
    - Structured data completeness
    """
    issues = []
    recommendations = []
    penalty = 0

    has_reviews = page_data.get("has_reviews", False)
    has_breadcrumb = page_data.get("has_breadcrumb", False)
    has_faq_schema = any("FAQPage" in str(s) for s in page_data.get("schema_types", []))
    has_org_schema = page_data.get("has_organization_schema", False)
    has_aggregate_rating = page_data.get("has_aggregate_rating", False)
    has_last_modified = page_data.get("has_last_modified", False)
    has_author = page_data.get("has_author", False)
    schema_types = page_data.get("schema_types", [])
    trust_signals = page_data.get("trust_signals", [])

    trust_score = 0
    trust_max = 0

    # Breadcrumb schema (important for category pages)
    trust_max += 1
    if has_breadcrumb:
        trust_score += 1
    else:
        if page_type == "category":
            issues.append({
                "severity": "warn", "area": "schema",
                "msg": "Mangler BreadcrumbList schema. Vigtigt for Google's forstaaelse af site-hierarki.",
            })
            penalty += 3
            recommendations.append("Tilfoej BreadcrumbList structured data")

    # FAQ schema (if page has FAQ content)
    has_faq_content = page_data.get("has_faq", False)
    if has_faq_content:
        trust_max += 1
        if has_faq_schema:
            trust_score += 1
        else:
            issues.append({
                "severity": "info", "area": "schema",
                "msg": "Siden har FAQ-indhold men mangler FAQPage schema markup.",
            })
            penalty += 2
            recommendations.append("Tilfoej FAQPage schema for at faa FAQ rich snippets i Google")

    # AggregateRating / Reviews
    trust_max += 1
    if has_reviews or has_aggregate_rating:
        trust_score += 1
    else:
        if page_type == "category":
            issues.append({
                "severity": "info", "area": "trust",
                "msg": "Ingen reviews eller ratings synlige paa kategorisiden.",
            })
            penalty += 2
            recommendations.append("Vis aggregerede produkt-ratings paa kategorisiden for social proof")

    # Organization schema (site-wide trust)
    trust_max += 1
    if has_org_schema:
        trust_score += 1
    else:
        issues.append({
            "severity": "info", "area": "schema",
            "msg": "Mangler Organization/Store schema. Signalerer trovaerdighed til Google.",
        })
        penalty += 1

    # Freshness / Last modified
    trust_max += 1
    if has_last_modified:
        trust_score += 1
    else:
        issues.append({
            "severity": "info", "area": "freshness",
            "msg": "Ingen synlig opdateringsdato. Friskhed er et ranking-signal.",
        })
        penalty += 1
        recommendations.append("Tilfoej 'Sidst opdateret' dato paa kategorisider")

    # Canonical
    canonical = page_data.get("canonical", "")
    url = page_data.get("url", "")
    trust_max += 1
    if canonical:
        trust_score += 1
        if canonical.rstrip("/").lower() != url.rstrip("/").lower():
            issues.append({
                "severity": "warn", "area": "canonical",
                "msg": f"Canonical peger paa en anden URL: {canonical}",
            })
            penalty += 3
    else:
        issues.append({
            "severity": "warn", "area": "canonical",
            "msg": "Mangler canonical tag. Risiko for duplicate content.",
        })
        penalty += 3

    # Images without alt (accessibility + SEO)
    images_without_alt = page_data.get("images_without_alt", 0)
    images_total = page_data.get("images_total", 0)
    if images_total > 0 and images_without_alt > images_total * 0.3:
        issues.append({
            "severity": "warn", "area": "images",
            "msg": f"{images_without_alt}/{images_total} billeder mangler alt-tekst.",
        })
        penalty += 2
        recommendations.append("Tilfoej beskrivende alt-tekst med keywords til produkt-billeder")

    trust_pct = (trust_score / max(trust_max, 1)) * 100

    return {
        "issues": issues,
        "recommendations": recommendations,
        "penalty": penalty,
        "details": {
            "trust_score": trust_score,
            "trust_max": trust_max,
            "trust_pct": round(trust_pct, 1),
            "has_reviews": has_reviews,
            "review_count": page_data.get("review_count", 0),
            "has_breadcrumb": has_breadcrumb,
            "has_faq_schema": has_faq_schema,
            "has_org_schema": has_org_schema,
            "has_aggregate_rating": has_aggregate_rating,
            "has_last_modified": has_last_modified,
            "has_author": has_author,
            "schema_types": schema_types,
            "signals_found": trust_signals,
        },
    }
