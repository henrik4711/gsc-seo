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
    "User-Agent": "Mozilla/5.0 (compatible; SEOBot/1.0)"
}


# ══════════════════════════════════════════════════════════════════
# 1. PAGE TYPE CLASSIFICATION
# ══════════════════════════════════════════════════════════════════

def classify_page_type(url: str, page_data: dict = None) -> dict:
    """
    Classify a page as category, product, blog, faq, or other.
    Uses URL patterns + schema + HTML structure signals.
    """
    url_lower = url.lower()
    path = urlparse(url_lower).path.rstrip("/")
    segments = [s for s in path.split("/") if s]

    result = {
        "page_type": "unknown",
        "confidence": "low",
        "signals": [],
    }

    # ── 1. URL pattern matching ───────────────────────────────
    product_patterns = ["/products/", "/produkt/", "/product/", "/p/"]
    category_patterns = ["/kategori/", "/category/", "/collections/", "/c/"]
    blog_patterns = ["/blog/", "/blogg/", "/artikel/", "/guide/", "/tips/", "/magazin/"]
    faq_patterns = ["/faq/", "/fragor/", "/hjalp/", "/help/", "/support/"]

    if any(p in url_lower for p in product_patterns):
        result["page_type"] = "product"
        result["signals"].append("URL contains product path")
    elif any(p in url_lower for p in faq_patterns):
        result["page_type"] = "faq"
        result["signals"].append("URL contains FAQ/help path")
    elif any(p in url_lower for p in blog_patterns):
        result["page_type"] = "blog"
        result["signals"].append("URL contains blog/guide path")
    elif any(p in url_lower for p in category_patterns):
        result["page_type"] = "category"
        result["signals"].append("URL contains category path")

    if page_data:
        schema_types = [str(s).lower() for s in page_data.get("schema_types", [])]
        h1 = (page_data.get("h1") or "").lower()
        h2s = [h.lower() for h in page_data.get("h2s", [])]
        body = (page_data.get("body_text") or page_data.get("full_body_text") or "").lower()
        word_count = page_data.get("word_count", 0) or len(body.split())
        internal_links = page_data.get("internal_links", 0)
        if isinstance(internal_links, list):
            internal_links = len(internal_links)
        h2_count = len(h2s)
        product_count = page_data.get("product_count", 0)
        has_price = "price" in body[:2000] or "kr" in body[:2000] or ":-" in body[:2000]

        # ── 2. Schema-based classification ────────────────────
        schema_str = " ".join(schema_types)
        if "product" in schema_str and "itemlist" not in schema_str:
            result["page_type"] = "product"
            result["signals"].append("Product schema detected")
        elif "itemlist" in schema_str or "collectionpage" in schema_str:
            result["page_type"] = "category"
            result["signals"].append("ItemList/Collection schema detected")
        elif "article" in schema_str or "blogposting" in schema_str or "newsarticle" in schema_str:
            result["page_type"] = "blog"
            result["signals"].append("Article/Blog schema detected")
        elif "faqpage" in schema_str:
            result["page_type"] = "faq"
            result["signals"].append("FAQPage schema detected")

        # ── 3. HTML structure signals ─────────────────────────
        # Order matters: check CATEGORY first (many links/products),
        # then BLOG (long text), then PRODUCT last (single item)

        filter_signals = ["filtrera", "sortera", "filter", "sort by", "visa alla", "show all"]
        has_filters = any(s in body[:3000] for s in filter_signals)
        add_to_cart_signals = ["lägg i varukorg", "add to cart", "buy now", "add to bag"]
        has_add_to_cart = any(s in body[:3000] for s in add_to_cart_signals)
        # "köp" is too generic for Swedish sites — used everywhere, not just product pages

        # Category page signals: many links, products, or filters
        if product_count >= 3:
            if result["page_type"] == "unknown":
                result["page_type"] = "category"
            result["signals"].append(f"Shows {product_count} products = category/listing page")
        elif internal_links > 20:
            if result["page_type"] == "unknown":
                result["page_type"] = "category"
            result["signals"].append(f"Many internal links ({internal_links}) = listing/hub page")
        elif has_filters and internal_links > 10:
            if result["page_type"] == "unknown":
                result["page_type"] = "category"
            result["signals"].append("Has filter/sort UI = listing page")

        # Blog/guide signals: long text, many headings
        if word_count > 500 and h2_count >= 3 and product_count == 0:
            if result["page_type"] == "unknown":
                result["page_type"] = "blog"
            result["signals"].append(f"Long text ({word_count} words) + {h2_count} H2s + no products = article/guide")

        # Product page signals: single item focus, add to cart, few links
        if has_add_to_cart and has_price and product_count <= 1 and internal_links < 30:
            if result["page_type"] == "unknown":
                result["page_type"] = "product"
            result["signals"].append("Has add-to-cart + price + few links = single product page")

        # FAQ signals: question patterns in headings
        # Only override to FAQ if not already classified by URL pattern
        question_h2s = sum(1 for h in h2s if h.startswith(("vad ", "hur ", "vilk", "när ", "var ", "what ", "how ", "why ", "when ", "?")) or "?" in h)
        if question_h2s >= 3:
            if result["page_type"] == "unknown":
                result["page_type"] = "faq"
            result["signals"].append(f"{question_h2s} question-style H2s")

        # ── 4. URL depth heuristic ────────────────────────────
        if result["page_type"] == "unknown":
            # Deep URLs (3+ segments) with no other signals → likely product
            if len(segments) >= 3 and has_price:
                result["page_type"] = "product"
                result["signals"].append("Deep URL + price mentions = likely product")
            # Shallow URLs (1 segment) → likely category or landing page
            elif len(segments) == 1:
                result["page_type"] = "category"
                result["signals"].append("Single URL segment = likely category/landing page")

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
                        result["trust_signals"].append(f"FAQPage schema with {result['faq_count']} questions")

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
                        result["trust_signals"].append(f"ItemList schema with {len(items_in_list)} items")

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
            result["trust_signals"].append(f"{len(review_elements)} review elements in HTML")

        # Author signals
        author_el = soup.find(attrs={"class": re.compile(r"author|byline|writer", re.I)})
        if author_el:
            result["has_author"] = True
            result["trust_signals"].append(f"Author info: {author_el.get_text(strip=True)[:60]}")
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
        main = soup.find("div", class_="xmx-page-content") or soup.find("main") or soup.body
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
            elif href.startswith("/") and not href.startswith("//"):
                is_internal = True
                href = f"https://{domain}{href}"  # Convert to absolute URL

            if is_internal:
                link_info = {"url": href, "anchor": anchor}
                result["internal_links"].append(link_info)
                result["internal_link_count"] += 1

                # Classify: is this a category link or product link?
                href_lower = href.lower()
                if re.search(r"/products?/|/produkt/|/p/", href_lower):
                    result["product_links_on_page"].append(link_info)
                elif (re.search(r"/kategori/|/category/|/collections?/", href_lower)
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
                 "online", "pris", "sex",
                 "og", "er", "af", "fra", "der", "et",
                 "kob", "bedst", "bedste",
                 "buy", "cheap", "price", "top", "how"}

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
            "topic": "(other)",
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
    # Fallback: if no editorial word count, use body_text word count
    if total_editorial == 0:
        total_editorial = page_data.get("word_count", 0) or len(full_text.split())
    h1 = (page_data.get("h1") or "").lower()
    h2s = page_data.get("h2s", [])
    h3s = page_data.get("h3s", [])
    has_faq = page_data.get("has_faq", False)
    has_guide = page_data.get("has_buying_guide", False)
    product_count = page_data.get("product_count", 0)
    full_text = (page_data.get("full_body_text") or page_data.get("body_text") or "").lower()
    editorial_text = (intro_text + " " + bottom_text).lower()
    # Fallback: if no editorial text, use full body text
    if not editorial_text.strip() and full_text:
        editorial_text = full_text

    # Filter keywords to only those relevant to this page's topic
    # Prevents "dildo" showing as missing on /sexleksaker-for-man
    # BUT: pillar pages (/sexleksaker) should include child-page keywords
    raw_keywords = list(set((cluster_keywords or []) + (gsc_queries or [])))

    # Extract topic words from URL slug
    from urllib.parse import urlparse as _urlparse
    page_path = _urlparse(url).path.lower().rstrip("/")
    slug_parts = set(page_path.replace("-", " ").replace("/", " ").split())
    slug_parts.discard("")

    # Detect if this is a PILLAR page (has child pages in the URL hierarchy)
    # e.g. /sexleksaker is pillar for /sexleksaker/vibratorer, /sexleksaker/dildos
    child_slug_words = set()
    if topic_clusters:
        all_urls = list(topic_clusters.get("page_topics", {}).keys())
    elif gsc_queries:
        # Fallback: use GSC pages
        all_urls = []
    else:
        all_urls = []

    for other_url in all_urls:
        other_path = _urlparse(other_url).path.lower().rstrip("/")
        # other_path starts with page_path + "/" → it's a child page
        if other_path != page_path and other_path.startswith(page_path + "/"):
            # Add child page slug words as relevant
            child_part = other_path[len(page_path):].replace("-", " ").replace("/", " ")
            child_slug_words.update(child_part.split())
    child_slug_words.discard("")

    is_pillar = len(child_slug_words) > 0

    # Get page's cluster topic names
    _page_topics = set()
    if topic_clusters:
        for t in topic_clusters.get("page_topics", {}).get(url, []):
            _page_topics.add(t.get("topic", "").lower())

    # H1 words as relevance signal
    h1_words = set(h1.lower().split()) if h1 else set()

    def _keyword_relevant(kw):
        kw_words = set(kw.lower().split())
        # Matches URL slug?
        if kw_words & slug_parts:
            return True
        # Pillar page: matches child page slugs?
        if is_pillar and kw_words & child_slug_words:
            return True
        # Matches cluster topics?
        for topic in _page_topics:
            if set(topic.split()) & kw_words:
                return True
        # Matches H1?
        if kw_words & h1_words:
            return True
        return False

    all_keywords = [kw for kw in raw_keywords if _keyword_relevant(kw)]
    # If filtering removed everything, keep cluster keywords at minimum
    if not all_keywords and cluster_keywords:
        all_keywords = cluster_keywords[:15]

    # ═══════════════════════════════════════════════════════════
    # A. EDITORIAL CONTENT VOLUME (Google 2026 best practices)
    # Pillar pages: 3000-5000 words, Cluster/category: 1500-3000,
    # Product: 300+, Blog: 1500-3000
    # ═══════════════════════════════════════════════════════════
    word_count = page_data.get("word_count", 0) or len(full_text.split())

    if is_pillar:
        # Pillar pages need comprehensive content
        if word_count < 500:
            issues.append({
                "severity": "critical", "area": "content_volume",
                "msg": f"PILLAR page has only {word_count} words. Pillar pages should have 3,000-5,000 words to establish topical authority.",
            })
            score -= 30
            recommendations.append("This is a PILLAR page (has sub-pages). Google expects 3,000-5,000 words covering all subtopics comprehensively.")
        elif word_count < 1500:
            issues.append({
                "severity": "warn", "area": "content_volume",
                "msg": f"PILLAR page has {word_count} words — aim for 3,000-5,000 to fully cover the topic.",
            })
            score -= 15
        elif word_count < 3000:
            issues.append({
                "severity": "info", "area": "content_volume",
                "msg": f"PILLAR page has {word_count} words — good, but 3,000+ is optimal for topical authority.",
            })
            score -= 5
    elif page_type == "category":
        if total_editorial < 50:
            issues.append({
                "severity": "critical", "area": "content_volume",
                "msg": f"Almost no editorial text ({total_editorial} words). Category pages need 1,500-3,000 words.",
            })
            score -= 30
            recommendations.append("Add 150-300 words of intro text ABOVE the product grid")
            recommendations.append("Add 300-500 words of bottom text with buying guide/FAQ BELOW the product grid")
        elif total_editorial < 150:
            issues.append({
                "severity": "warn", "area": "content_volume",
                "msg": f"Too little editorial text ({total_editorial} words). Category pages should have 1,500-3,000 words total.",
            })
            score -= 15
        elif total_editorial < 300:
            issues.append({
                "severity": "info", "area": "content_volume",
                "msg": f"Acceptable content ({total_editorial} words) but aim for 1,500+ for full topic coverage.",
            })
            score -= 5
    elif page_type == "blog":
        if word_count < 300:
            issues.append({
                "severity": "critical", "area": "content_volume",
                "msg": f"Blog/guide has only {word_count} words. Aim for 1,500-3,000 words for ranking potential.",
            })
            score -= 20
        elif word_count < 1500:
            issues.append({
                "severity": "warn", "area": "content_volume",
                "msg": f"Blog/guide has {word_count} words — 1,500-3,000 words is the sweet spot for cluster content.",
            })
            score -= 10

        if intro_words < 30:
            issues.append({
                "severity": "warn", "area": "intro",
                "msg": "No/minimal intro text above the product grid. Google and users see this first.",
            })
            score -= 10
            recommendations.append("Add 80-150 words of intro explaining the category and helping the customer choose")

    # ═══════════════════════════════════════════════════════════
    # B. TOPIC-LEVEL COVERAGE (not just keywords)
    # ═══════════════════════════════════════════════════════════
    subtopics = _group_queries_into_subtopics(all_keywords)
    subtopic_results = []
    covered_topics = 0
    total_topics = len([s for s in subtopics if s["topic"] != "(other)"])

    for st_item in subtopics:
        if st_item["topic"] == "(other)":
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
                "msg": f"Only {topic_coverage_pct:.0f}% of cluster topics are covered in the page text ({covered_topics:.0f}/{total_topics} topics)",
            })
            score -= 25
        elif topic_coverage_pct < 60:
            issues.append({
                "severity": "warn", "area": "topic_coverage",
                "msg": f"{topic_coverage_pct:.0f}% of cluster topics covered ({covered_topics:.0f}/{total_topics})",
            })
            score -= 12

        missing_topics = [s for s in subtopic_results if s["status"] == "missing"]
        if missing_topics:
            topic_names = [s["topic"] for s in missing_topics[:5]]
            recommendations.append(
                f"Add content about these topics: {', '.join(topic_names)}"
            )
            for mt in missing_topics[:3]:
                recommendations.append(
                    f"  -> Topic '{mt['topic']}' is completely missing ({mt['query_count']} queries: {', '.join(mt['queries'][:3])})"
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
            "msg": f"Only {kw_coverage_pct:.0f}% of keywords found in page text ({len(covered_kws)}/{len(all_keywords[:30])})",
        })
        score -= 15
    elif kw_coverage_pct < 60:
        issues.append({
            "severity": "warn", "area": "keyword_coverage",
            "msg": f"{kw_coverage_pct:.0f}% keyword coverage ({len(covered_kws)}/{len(all_keywords[:30])})",
        })
        score -= 8

    # Keyword in H1
    if all_keywords and kw_in_h1 == 0:
        issues.append({
            "severity": "warn", "area": "keyword_placement",
            "msg": "No primary keyword in H1. H1 should contain the main keyword.",
        })
        score -= 5

    # Keyword in first paragraph
    if all_keywords and kw_in_intro == 0 and intro_text:
        issues.append({
            "severity": "warn", "area": "keyword_placement",
            "msg": "No keyword in the intro text. The first paragraph should contain the main keyword.",
        })
        score -= 3

    if missing_kws:
        recommendations.append(f"Integrate these keywords naturally: {', '.join(missing_kws[:8])}")

    # ═══════════════════════════════════════════════════════════
    # D. CONTENT STRUCTURE
    # ═══════════════════════════════════════════════════════════
    editorial_h2s = [h for h in h2s if not re.search(r"produkt|vara|pris|^kr\s", h, re.I)]
    if len(editorial_h2s) < 2 and page_type == "category":
        issues.append({
            "severity": "warn", "area": "structure",
            "msg": f"Too few editorial H2 headings ({len(editorial_h2s)}). Structure with H2 for buying guide/FAQ/types.",
        })
        score -= 8
        recommendations.append("Add H2 sections: 'Types of [category]', 'How to choose', 'FAQ'")

    if not has_faq and page_type == "category":
        issues.append({
            "severity": "warn", "area": "faq",
            "msg": "No FAQ. FAQ is valuable for featured snippets and long-tail keywords.",
        })
        score -= 5
        recommendations.append("Add 4-6 FAQ based on GSC long-tail queries")

    if not has_guide and page_type == "category":
        issues.append({
            "severity": "info", "area": "guide",
            "msg": "No buying guide section.",
        })
        score -= 3
        recommendations.append("Add buying guide: 'What to look for?', 'Differences between types'")

    # ═══════════════════════════════════════════════════════════
    # E. INTERNAL LINKING ANALYSIS
    # ═══════════════════════════════════════════════════════════
    internal_links = page_data.get("internal_links", [])
    link_count = internal_links if isinstance(internal_links, int) else len(internal_links)
    category_links = page_data.get("category_links", [])
    product_links_on_page = page_data.get("product_links_on_page", [])

    linking_issues = _audit_internal_linking(
        url, internal_links, category_links, product_links_on_page,
        all_keywords, page_type, topic_clusters, page_data=page_data
    )
    for li in linking_issues["issues"]:
        issues.append(li)
    score -= linking_issues["penalty"]
    recommendations.extend(linking_issues["recommendations"])

    # ═══════════════════════════════════════════════════════════
    # F. PRODUCT-CLUSTER ALIGNMENT
    # ═══════════════════════════════════════════════════════════
    product_alignment = {}
    subcategory_alignment = {}
    if page_type == "category":
        product_names = page_data.get("product_names", [])
        product_links_list = page_data.get("product_links_on_page", [])
        product_alignment = _audit_product_alignment(
            product_names, product_links_list,
            all_keywords, topic_clusters, url
        )
        for pi in product_alignment.get("issues", []):
            issues.append(pi)
            score -= 5
        recommendations.extend(product_alignment.get("recommendations", []))

        subcategory_alignment = _audit_subcategory_alignment(
            category_links, topic_clusters, url
        )
        unrelated_subcats = subcategory_alignment.get("unrelated", [])
        if unrelated_subcats:
            issues.append({
                "severity": "info", "area": "subcategory_alignment",
                "msg": f"{len(unrelated_subcats)} linked subcategories are outside this topic cluster.",
            })

    # ═══════════════════════════════════════════════════════════
    # G. TRUST & E-E-A-T SIGNALS
    # ═══════════════════════════════════════════════════════════
    trust_result = _audit_trust_signals(page_data, page_type)
    for ti in trust_result["issues"]:
        issues.append(ti)
    score -= trust_result["penalty"]
    recommendations.extend(trust_result["recommendations"])

    # ═══════════════════════════════════════════════════════════
    # H. ENHANCED E-E-A-T DEPTH
    # ═══════════════════════════════════════════════════════════
    credibility = _check_content_credibility(
        full_text, page_data.get("external_link_count", 0)
    )
    topical_auth = _check_topical_authority(url, topic_clusters)
    trust_flow = _check_trust_flow(url, page_authority, topic_clusters)

    # Merge enhanced E-E-A-T issues
    for ci in topical_auth.get("issues", []):
        issues.append(ci)
        score -= 3
    for fi in trust_flow.get("issues", []):
        issues.append(fi)

    if credibility["credibility_score"] == 0 and page_type in ("blog", "category"):
        issues.append({
            "severity": "info", "area": "credibility",
            "msg": "No content credibility signals (citations, data, expert language). Consider adding authoritative references.",
        })
        recommendations.append("Add expert language, cite sources, or include specific data/statistics to boost credibility")

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
        "product_alignment": product_alignment,
        "subcategory_alignment": subcategory_alignment,
        "trust": trust_result["details"],
        "eeat_depth": {
            "credibility": credibility,
            "topical_authority": topical_auth,
            "trust_flow": trust_flow,
        },
    }


# ══════════════════════════════════════════════════════════════════
# 4. INTERNAL LINKING AUDIT
# ══════════════════════════════════════════════════════════════════

def _audit_internal_linking(
    url, internal_links, category_links, product_links_on_page,
    keywords, page_type, topic_clusters=None, page_data=None,
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
            "msg": f"Few internal links ({link_count}). Category pages should link to related categories and guides.",
        })
        penalty += 5

    # Category cross-links
    if page_type == "category" and cat_link_count < 2:
        issues.append({
            "severity": "warn", "area": "category_links",
            "msg": f"Only {cat_link_count} links to other categories. Add links to related/subcategories.",
        })
        penalty += 5
        recommendations.append("Add links to related categories in the bottom text (e.g. 'See also: [related category]')")

    # ── Spoke → Hub link check (Google 2026 requirement) ──────
    # Every spoke/cluster page MUST link back to its pillar/hub page
    if topic_clusters and isinstance(internal_links, list):
        from urllib.parse import urlparse as _up
        page_path = _up(url).path.lower().rstrip("/")
        linked_paths = set()
        for l in internal_links:
            u = l.get("url", "")
            linked_paths.add(_up(u).path.lower().rstrip("/"))

        # Find this page's parent/hub by URL hierarchy
        path_parts = page_path.strip("/").split("/")
        if len(path_parts) >= 2:
            # Try progressively shorter parent paths
            for depth in range(len(path_parts) - 1, 0, -1):
                parent_path = "/" + "/".join(path_parts[:depth])
                if parent_path in linked_paths:
                    break  # Found link to parent — good
            else:
                # No link to any parent page found
                parent_path = "/" + "/".join(path_parts[:len(path_parts) - 1])
                issues.append({
                    "severity": "warn", "area": "hub_link_missing",
                    "msg": f"This page does NOT link back to its hub/pillar page ({parent_path}). Google requires spoke→hub links for topic cluster authority.",
                })
                penalty += 5
                recommendations.append(
                    f"Add a link back to the hub page {parent_path} — this is critical for topic cluster SEO. "
                    f"Place it in the intro or bottom text with descriptive anchor text."
                )

    # Anchor text quality
    if isinstance(internal_links, list) and internal_links:
        anchors = [l.get("anchor", "") for l in internal_links if l.get("anchor")]
        empty_anchors = sum(1 for a in anchors if not a.strip() or a.strip() in (".", ">", "Read more", "Click here", "See more"))
        keyword_anchors = 0
        if keywords:
            kw_lower = set(k.lower() for k in keywords[:10])
            for anchor in anchors:
                if any(kw in anchor.lower() for kw in kw_lower):
                    keyword_anchors += 1

        if len(anchors) > 0 and empty_anchors / len(anchors) > 0.5:
            issues.append({
                "severity": "info", "area": "anchor_text",
                "msg": f"{empty_anchors}/{len(anchors)} internal links have empty/generic anchor text.",
            })
            penalty += 2

        if len(anchors) > 5 and keyword_anchors == 0:
            issues.append({
                "severity": "info", "area": "anchor_text",
                "msg": "No internal link anchors contain target keywords.",
            })
            penalty += 2
            recommendations.append("Use keyword-rich anchor texts in internal links (not 'click here')")

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
            "msg": f"{len(missing_links)} related pages in the same topic cluster are NOT linked from this page.",
        })
        penalty += min(len(missing_links), 5)
        for ml in top_missing:
            short_url = ml["url"].replace("https://", "").replace("http://", "")
            recommendations.append(
                f"Missing link to: {short_url} (shared topics: {', '.join(ml['shared_topics'][:2])})"
            )

    # Semantic validation of existing links (WP1)
    semantic_validation = _validate_existing_links(internal_links, url, topic_clusters)

    if semantic_validation["anchor_mismatches"]:
        mismatch_count = len(semantic_validation["anchor_mismatches"])
        issues.append({
            "severity": "info", "area": "anchor_optimization",
            "msg": f"{mismatch_count} internal links have anchor text that doesn't match cluster terms.",
        })
        penalty += min(mismatch_count, 3)
        for am in semantic_validation["anchor_mismatches"][:3]:
            recommendations.append(
                f"Improve anchor for {am['url'][:50]}: '{am['current_anchor']}' → '{am['suggested_anchor']}'"
            )

    non_semantic = semantic_validation["non_semantic_links"]
    if non_semantic and len(non_semantic) > link_count * 0.5 and link_count > 5:
        issues.append({
            "severity": "warn", "area": "link_relevance",
            "msg": f"{len(non_semantic)}/{link_count} internal links point to pages outside this topic cluster.",
        })
        penalty += 3

    # Generate specific fix suggestions for missing links (WP1)
    link_fix_suggestions = _generate_link_fix_suggestions(
        missing_links[:10], page_data=page_data or {},
        topic_clusters=topic_clusters,
    ) if missing_links else []

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
            "semantic_validation": semantic_validation,
            "link_fix_suggestions": link_fix_suggestions,
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
                "msg": "Missing BreadcrumbList schema. Important for Google's understanding of site hierarchy.",
            })
            penalty += 3
            recommendations.append("Add BreadcrumbList structured data")

    # FAQ schema (if page has FAQ content)
    has_faq_content = page_data.get("has_faq", False)
    if has_faq_content:
        trust_max += 1
        if has_faq_schema:
            trust_score += 1
        else:
            issues.append({
                "severity": "info", "area": "schema",
                "msg": "Page has FAQ content but is missing FAQPage schema markup.",
            })
            penalty += 2
            recommendations.append("Add FAQPage schema to get FAQ rich snippets in Google")

    # AggregateRating / Reviews
    trust_max += 1
    if has_reviews or has_aggregate_rating:
        trust_score += 1
    else:
        if page_type == "category":
            issues.append({
                "severity": "info", "area": "trust",
                "msg": "No reviews or ratings visible on the category page.",
            })
            penalty += 2
            recommendations.append("Show aggregated product ratings on the category page for social proof")

    # Organization schema (site-wide trust)
    trust_max += 1
    if has_org_schema:
        trust_score += 1
    else:
        issues.append({
            "severity": "info", "area": "schema",
            "msg": "Missing Organization/Store schema. Signals trustworthiness to Google.",
        })
        penalty += 1

    # Freshness / Last modified
    trust_max += 1
    if has_last_modified:
        trust_score += 1
    else:
        issues.append({
            "severity": "info", "area": "freshness",
            "msg": "No visible update date. Freshness is a ranking signal.",
        })
        penalty += 1
        recommendations.append("Add 'Last updated' date on category pages")

    # Canonical
    canonical = page_data.get("canonical", "")
    url = page_data.get("url", "")
    trust_max += 1
    if canonical:
        trust_score += 1
        if canonical.rstrip("/").lower() != url.rstrip("/").lower():
            issues.append({
                "severity": "warn", "area": "canonical",
                "msg": f"Canonical points to a different URL: {canonical}",
            })
            penalty += 3
    else:
        issues.append({
            "severity": "warn", "area": "canonical",
            "msg": "Missing canonical tag. Risk of duplicate content.",
        })
        penalty += 3

    # Images without alt (accessibility + SEO)
    images_without_alt = page_data.get("images_without_alt", 0)
    images_total = page_data.get("images_total", 0)
    if images_total > 0 and images_without_alt > images_total * 0.3:
        issues.append({
            "severity": "warn", "area": "images",
            "msg": f"{images_without_alt}/{images_total} images are missing alt text.",
        })
        penalty += 2
        recommendations.append("Add descriptive alt text with keywords to product images")

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


# ══════════════════════════════════════════════════════════════════
# 6. SEMANTIC LINK VALIDATION (WP1)
# ══════════════════════════════════════════════════════════════════

def _validate_existing_links(
    internal_links: list, current_url: str, topic_clusters: dict = None,
) -> dict:
    """
    Check if existing internal links point to semantically related pages.
    Validates anchor text against shared cluster terms.
    """
    result = {
        "semantic_links": [],
        "non_semantic_links": [],
        "anchor_mismatches": [],
    }

    if not topic_clusters or not isinstance(internal_links, list):
        return result

    page_topics = topic_clusters.get("page_topics", {})
    clusters = topic_clusters.get("clusters", [])

    # Build lookup: url -> set of core_terms from its clusters
    url_core_terms = {}
    for cluster in clusters:
        terms = set(cluster.get("core_terms", []))
        for p in cluster.get("pages", []):
            key = p["page"].rstrip("/").lower()
            url_core_terms.setdefault(key, set()).update(terms)

    my_topics = page_topics.get(current_url, [])
    my_topic_names = set(t.get("topic", "") for t in my_topics)
    my_terms = url_core_terms.get(current_url.rstrip("/").lower(), set())

    domain = urlparse(current_url).netloc

    for link in internal_links:
        link_url = link.get("url", "")
        anchor = link.get("anchor", "").strip()
        if not link_url:
            continue

        # Normalize URL
        if link_url.startswith("/"):
            link_url_full = f"https://{domain}{link_url}"
        else:
            link_url_full = link_url
        link_key = link_url_full.rstrip("/").lower()

        # Find target's topics
        target_topics = page_topics.get(link_url_full, [])
        if not target_topics:
            # Try without trailing slash variations
            for pt_url in page_topics:
                if pt_url.rstrip("/").lower() == link_key:
                    target_topics = page_topics[pt_url]
                    break

        target_topic_names = set(t.get("topic", "") for t in target_topics)
        shared = my_topic_names & target_topic_names
        target_terms = url_core_terms.get(link_key, set())

        if shared:
            result["semantic_links"].append({
                "url": link_url, "anchor": anchor,
                "shared_topics": list(shared)[:3],
            })
            # Check anchor text quality
            if anchor and target_terms:
                anchor_lower = anchor.lower()
                has_term = any(t.lower() in anchor_lower for t in target_terms)
                if not has_term and len(anchor) > 2:
                    suggested = " ".join(sorted(target_terms)[:3])
                    result["anchor_mismatches"].append({
                        "url": link_url,
                        "current_anchor": anchor,
                        "suggested_anchor": suggested,
                        "reason": f"Anchor '{anchor}' doesn't contain cluster terms ({suggested})",
                    })
        elif target_topics:
            result["non_semantic_links"].append({
                "url": link_url, "anchor": anchor,
                "target_topics": list(target_topic_names)[:2],
            })

    return result


def _generate_link_fix_suggestions(
    missing_crosslinks: list, page_data: dict, topic_clusters: dict = None,
) -> list:
    """
    Generate specific, actionable link fix suggestions for missing crosslinks.
    Includes suggested anchor text and placement section.
    """
    if not missing_crosslinks:
        return []

    clusters = (topic_clusters or {}).get("clusters", [])
    h2s = page_data.get("h2s", [])
    has_bottom = page_data.get("bottom_word_count", 0) > 30
    has_intro = page_data.get("intro_word_count", 0) > 30

    # Build url -> cluster core_terms lookup
    url_terms = {}
    for cluster in clusters:
        terms = cluster.get("core_terms", [])
        label = cluster.get("topic", "")
        for p in cluster.get("pages", []):
            key = p["page"].rstrip("/").lower()
            url_terms[key] = {"terms": terms, "topic": label,
                              "impressions": p.get("total_clicks", 0)}

    suggestions = []
    for ml in missing_crosslinks[:10]:
        target_url = ml["url"]
        target_key = target_url.rstrip("/").lower()
        shared_topics = ml.get("shared_topics", [])
        shared_count = ml.get("shared_count", 0)

        target_info = url_terms.get(target_key, {})
        terms = target_info.get("terms", [])
        target_impressions = target_info.get("impressions", 0)

        # Build suggested anchor from cluster terms + shared topics
        anchor_parts = terms[:2] if terms else shared_topics[:2]
        suggested_anchor = " ".join(anchor_parts) if anchor_parts else target_url.split("/")[-2] or "related page"

        # Find best placement section
        placement = "bottom_text" if has_bottom else "intro_text" if has_intro else "new_section"
        placement_detail = ""

        # Try to match against an H2 that relates to the shared topic
        for h2 in h2s:
            h2_lower = h2.lower()
            if any(t.lower() in h2_lower for t in anchor_parts):
                placement = "h2_section"
                placement_detail = h2
                break

        # Priority: shared_count * 2 + has_impressions
        priority_score = shared_count * 2 + (1 if target_impressions > 0 else 0)
        priority = "high" if priority_score >= 4 else "medium" if priority_score >= 2 else "low"

        suggestions.append({
            "target_url": target_url,
            "suggested_anchor": suggested_anchor,
            "placement": placement,
            "placement_detail": placement_detail,
            "priority": priority,
            "shared_topics": shared_topics[:3],
            "shared_count": shared_count,
            "reason": f"{shared_count} shared topic(s): {', '.join(shared_topics[:2])}",
        })

    suggestions.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["priority"], 3))
    return suggestions


# ══════════════════════════════════════════════════════════════════
# 7. PRODUCT-CLUSTER ALIGNMENT (WP2)
# ══════════════════════════════════════════════════════════════════

def _audit_product_alignment(
    product_names: list, product_links: list,
    cluster_keywords: list, topic_clusters: dict = None,
    current_url: str = "",
) -> dict:
    """
    Check if products on a category page match the cluster topic.
    """
    issues = []
    recommendations = []

    if not product_names and not product_links:
        return {"alignment_pct": None, "issues": issues, "recommendations": recommendations,
                "aligned": [], "misplaced": []}

    # Get core terms for this page's cluster
    clusters = (topic_clusters or {}).get("clusters", [])
    page_topics_map = (topic_clusters or {}).get("page_topics", {})

    my_topics = page_topics_map.get(current_url, [])
    my_topic_names = set(t.get("topic", "") for t in my_topics)

    # Collect all core terms from page's clusters
    my_core_terms = set()
    for cluster in clusters:
        cluster_topic = cluster.get("topic", "")
        if cluster_topic in my_topic_names:
            my_core_terms.update(t.lower() for t in cluster.get("core_terms", []))

    # Also add keywords as terms
    kw_terms = set()
    for kw in (cluster_keywords or [])[:20]:
        kw_terms.update(kw.lower().split())

    all_terms = my_core_terms | kw_terms

    # Check product names against cluster terms
    aligned = []
    misplaced = []

    for name in product_names[:30]:
        name_lower = name.lower()
        name_tokens = set(name_lower.split())
        overlap = name_tokens & all_terms
        if overlap:
            aligned.append({"name": name, "matching_terms": list(overlap)[:3]})
        else:
            misplaced.append({"name": name, "reason": "No cluster term match in product name"})

    # Check product links against page_topics
    for pl in (product_links or [])[:20]:
        pl_url = pl.get("url", "")
        if not pl_url:
            continue
        # Normalize
        if pl_url.startswith("/"):
            domain = urlparse(current_url).netloc
            pl_url_full = f"https://{domain}{pl_url}"
        else:
            pl_url_full = pl_url

        target_topics = page_topics_map.get(pl_url_full, [])
        if not target_topics:
            for pt_url in page_topics_map:
                if pt_url.rstrip("/").lower() == pl_url_full.rstrip("/").lower():
                    target_topics = page_topics_map[pt_url]
                    break

        if target_topics:
            target_topic_names = set(t.get("topic", "") for t in target_topics)
            shared = my_topic_names & target_topic_names
            if not shared and target_topic_names:
                anchor = pl.get("anchor", pl_url)[:60]
                misplaced.append({
                    "name": anchor,
                    "reason": f"Product belongs to different cluster ({', '.join(list(target_topic_names)[:2])})",
                    "url": pl_url,
                })

    total = len(product_names[:30]) if product_names else len(product_links[:20])
    aligned_count = len(aligned)
    alignment_pct = (aligned_count / max(total, 1)) * 100

    if alignment_pct < 40:
        issues.append({
            "severity": "critical", "area": "product_alignment",
            "msg": f"Only {alignment_pct:.0f}% of products match the cluster topic. Many products may be miscategorized.",
        })
    elif alignment_pct < 70:
        issues.append({
            "severity": "warn", "area": "product_alignment",
            "msg": f"{alignment_pct:.0f}% product-cluster alignment. Some products may not belong in this category.",
        })

    if misplaced:
        top_misplaced = [m["name"][:40] for m in misplaced[:3]]
        recommendations.append(
            f"Review these potentially misplaced products: {', '.join(top_misplaced)}"
        )

    return {
        "alignment_pct": round(alignment_pct, 1),
        "aligned": aligned[:10],
        "misplaced": misplaced[:10],
        "total_checked": total,
        "issues": issues,
        "recommendations": recommendations,
    }


def _audit_subcategory_alignment(
    category_links: list, topic_clusters: dict = None, current_url: str = "",
) -> dict:
    """Check if linked subcategories share the parent topic cluster."""
    aligned = []
    unrelated = []

    if not topic_clusters or not isinstance(category_links, list):
        return {"aligned": aligned, "unrelated": unrelated}

    page_topics_map = topic_clusters.get("page_topics", {})
    my_topics = page_topics_map.get(current_url, [])
    my_topic_names = set(t.get("topic", "") for t in my_topics)

    domain = urlparse(current_url).netloc

    for cl in category_links:
        cl_url = cl.get("url", "")
        anchor = cl.get("anchor", "")
        if not cl_url:
            continue

        if cl_url.startswith("/"):
            cl_url_full = f"https://{domain}{cl_url}"
        else:
            cl_url_full = cl_url

        target_topics = page_topics_map.get(cl_url_full, [])
        if not target_topics:
            for pt_url in page_topics_map:
                if pt_url.rstrip("/").lower() == cl_url_full.rstrip("/").lower():
                    target_topics = page_topics_map[pt_url]
                    break

        if target_topics:
            target_topic_names = set(t.get("topic", "") for t in target_topics)
            shared = my_topic_names & target_topic_names
            entry = {"url": cl_url, "anchor": anchor}
            if shared:
                entry["shared_topics"] = list(shared)[:3]
                aligned.append(entry)
            else:
                entry["target_topics"] = list(target_topic_names)[:2]
                unrelated.append(entry)

    return {"aligned": aligned, "unrelated": unrelated}


# ══════════════════════════════════════════════════════════════════
# 8. ENHANCED E-E-A-T DEPTH (WP3)
# ══════════════════════════════════════════════════════════════════

def _check_content_credibility(full_text: str, external_link_count: int = 0) -> dict:
    """
    Check for content credibility signals: citations, data, expert language.
    """
    signals = []
    score = 0
    max_score = 4

    text_lower = full_text.lower() if full_text else ""

    # Citation patterns (multilingual)
    citation_patterns = [
        r"according to", r"study shows?", r"research (shows?|indicates?|suggests?)",
        r"expert[s]?\s+(say|recommend|suggest)", r"data (shows?|indicates?)",
        r"enligt", r"forskning visar", r"studie",  # Swedish
        r"ifølge", r"undersøgelse", r"forskning",  # Danish
    ]
    has_citations = any(re.search(p, text_lower) for p in citation_patterns)
    if has_citations:
        signals.append("Content cites sources or research")
        score += 1

    # Statistics / specific data
    stat_patterns = [
        r"\d+\s*%", r"\d+\s*(users?|customers?|people|studies|reviews?)",
        r"\d{4}\s*(study|survey|report|data)",
    ]
    has_stats = any(re.search(p, text_lower) for p in stat_patterns)
    if has_stats:
        signals.append("Contains specific data or statistics")
        score += 1

    # External authoritative links
    if external_link_count >= 2:
        signals.append(f"{external_link_count} external links (potential source citations)")
        score += 1

    # Expert language signals
    expert_patterns = [
        r"(we recommend|our experts?|our team|years of experience)",
        r"(vi rekommenderar|våra experter|vår erfarenhet)",  # Swedish
        r"(vi anbefaler|vores eksperter|års erfaring)",  # Danish
    ]
    has_expert = any(re.search(p, text_lower) for p in expert_patterns)
    if has_expert:
        signals.append("Expert/authority language detected")
        score += 1

    return {
        "credibility_score": score,
        "credibility_max": max_score,
        "credibility_pct": round((score / max_score) * 100),
        "signals": signals,
    }


def _check_topical_authority(
    current_url: str, topic_clusters: dict = None,
) -> dict:
    """
    Check topical authority: how many pages does the site have in this topic cluster?
    Low authority = need supporting content.
    """
    issues = []
    signals = []

    if not topic_clusters:
        return {"authority_score": 0, "issues": issues, "signals": signals,
                "pages_in_cluster": 0, "has_informational_content": False}

    page_topics = topic_clusters.get("page_topics", {})
    clusters = topic_clusters.get("clusters", [])

    my_topics = page_topics.get(current_url, [])
    my_topic_names = set(t.get("topic", "") for t in my_topics)

    # Find clusters this page belongs to
    pages_in_cluster = set()
    total_queries = 0
    has_informational = False

    for cluster in clusters:
        if cluster.get("topic", "") in my_topic_names:
            total_queries += cluster.get("query_count", 0)
            for p in cluster.get("pages", []):
                pages_in_cluster.add(p["page"])
                # Check if any page looks informational (blog/guide)
                p_url = p["page"].lower()
                if any(pat in p_url for pat in ["/blog", "/guide", "/artikel", "/tips", "/how-to", "/faq"]):
                    has_informational = True

    page_count = len(pages_in_cluster)

    # Scoring
    if page_count >= 5:
        authority_score = 3
        signals.append(f"Strong: {page_count} pages cover this topic cluster")
    elif page_count >= 3:
        authority_score = 2
        signals.append(f"Moderate: {page_count} pages cover this topic cluster")
    elif page_count >= 2:
        authority_score = 1
        signals.append(f"Weak: only {page_count} pages for {total_queries} queries in this cluster")
        issues.append({
            "severity": "warn", "area": "topical_authority",
            "msg": f"Low topical authority: only {page_count} pages for {total_queries} queries. Add supporting content.",
        })
    else:
        authority_score = 0
        signals.append(f"Very weak: single page covering {total_queries} queries")
        if total_queries >= 10:
            issues.append({
                "severity": "critical", "area": "topical_authority",
                "msg": f"Single page covers {total_queries} queries. Need supporting articles/guides for topical depth.",
            })

    if not has_informational and total_queries > 5:
        issues.append({
            "severity": "info", "area": "topical_authority",
            "msg": "No informational content (blog/guide) in this topic cluster. Add a guide or FAQ article.",
        })

    return {
        "authority_score": authority_score,
        "authority_max": 3,
        "pages_in_cluster": page_count,
        "total_queries_in_cluster": total_queries,
        "has_informational_content": has_informational,
        "issues": issues,
        "signals": signals,
    }


def _check_trust_flow(
    current_url: str, page_authority=None, topic_clusters: dict = None,
) -> dict:
    """
    Check backlink trust flow: does this page receive external trust signals?
    Cross-references with page_authority data from Ahrefs.
    """
    import pandas as pd
    issues = []
    signals = []

    if page_authority is None or (isinstance(page_authority, pd.DataFrame) and page_authority.empty):
        return {"trust_flow_score": 0, "issues": issues, "signals": signals, "referring_domains": 0}

    # Find this page's authority
    page_auth = page_authority[
        page_authority["page"].str.rstrip("/").str.lower() == current_url.rstrip("/").lower()
    ]

    if page_auth.empty:
        issues.append({
            "severity": "info", "area": "trust_flow",
            "msg": "Page not found in Ahrefs data. May have zero external backlinks.",
        })
        return {"trust_flow_score": 0, "issues": issues, "signals": signals, "referring_domains": 0}

    rd = int(page_auth.iloc[0].get("referring_domains", 0))
    backlinks = int(page_auth.iloc[0].get("backlinks", 0))

    if rd >= 10:
        trust_flow_score = 3
        signals.append(f"Strong trust: {rd} referring domains, {backlinks} backlinks")
    elif rd >= 3:
        trust_flow_score = 2
        signals.append(f"Moderate trust: {rd} referring domains")
    elif rd >= 1:
        trust_flow_score = 1
        signals.append(f"Weak trust: only {rd} referring domain(s)")
        issues.append({
            "severity": "info", "area": "trust_flow",
            "msg": f"Only {rd} referring domain(s). Consider link building for this page.",
        })
    else:
        trust_flow_score = 0
        issues.append({
            "severity": "warn", "area": "trust_flow",
            "msg": "Zero external backlinks. This page has no external trust signals.",
        })

    # Compare with cluster peers
    if topic_clusters:
        page_topics_map = topic_clusters.get("page_topics", {})
        my_topics = page_topics_map.get(current_url, [])
        my_topic_names = set(t.get("topic", "") for t in my_topics)
        clusters = topic_clusters.get("clusters", [])

        peer_rds = []
        for cluster in clusters:
            if cluster.get("topic", "") in my_topic_names:
                for p in cluster.get("pages", []):
                    if p["page"].rstrip("/").lower() != current_url.rstrip("/").lower():
                        peer_auth = page_authority[
                            page_authority["page"].str.rstrip("/").str.lower() == p["page"].rstrip("/").lower()
                        ]
                        if not peer_auth.empty:
                            peer_rds.append(int(peer_auth.iloc[0].get("referring_domains", 0)))

        if peer_rds:
            avg_peer_rd = sum(peer_rds) / len(peer_rds)
            if rd < avg_peer_rd * 0.5 and avg_peer_rd > 2:
                issues.append({
                    "severity": "info", "area": "trust_flow",
                    "msg": f"Below cluster average: {rd} RDs vs {avg_peer_rd:.0f} avg for cluster peers.",
                })

    return {
        "trust_flow_score": trust_flow_score,
        "trust_flow_max": 3,
        "referring_domains": rd,
        "backlinks": backlinks,
        "issues": issues,
        "signals": signals,
    }
