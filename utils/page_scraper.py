"""
Page auditor: fetches landing pages, extracts meta tags, and analyses content
"""

import re
import streamlit as st
from urllib.parse import urlparse
from typing import Optional

try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SEOBot/1.0)"
    )
}


def scrape_page(url: str, timeout: int = 10) -> dict:
    """
    Scrape a URL and return structured page data
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
        "internal_links": 0,
        "external_links": 0,
        "images_without_alt": 0,
        "title_length": 0,
        "description_length": 0,
    }
    
    if not SCRAPING_AVAILABLE:
        result["error"] = "requests and beautifulsoup4 not installed"
        return result
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
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
        
        result["h2s"] = [h.get_text(strip=True) for h in soup.find_all("h2")][:10]
        result["h3s"] = [h.get_text(strip=True) for h in soup.find_all("h3")][:10]
        
        # Body text (remove script, style, nav, footer)
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        
        main_content = soup.find("main") or soup.find("article") or soup.find("div", class_=re.compile("content|product|description", re.I)) or soup.body
        if main_content:
            raw_text = main_content.get_text(separator=" ", strip=True)
            # Clean whitespace
            body_text = re.sub(r'\s+', ' ', raw_text).strip()
            result["body_text"] = body_text[:8000]  # Cap at 8k chars for AI
            result["word_count"] = len(body_text.split())
        
        # Schema types
        schema_tags = soup.find_all("script", attrs={"type": "application/ld+json"})
        for tag in schema_tags:
            try:
                import json
                data = json.loads(tag.string or "{}")
                if "@type" in data:
                    result["schema_types"].append(data["@type"])
            except Exception:
                pass
        
        # Link analysis
        domain = urlparse(url).netloc
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http"):
                if domain in href:
                    result["internal_links"] += 1
                else:
                    result["external_links"] += 1
        
        # Images without alt
        result["images_without_alt"] = sum(
            1 for img in soup.find_all("img")
            if not img.get("alt", "").strip()
        )
        
    except requests.exceptions.RequestException as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = f"Parse error: {e}"
    
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
    
    # Title checks
    if not title:
        issues.append({"type": "critical", "field": "title", "msg": "Missing meta title"})
        score -= 30
    elif title_len < 30:
        issues.append({"type": "warn", "field": "title", "msg": f"Title too short ({title_len} chars, recommended 50-60)"})
        score -= 10
    elif title_len > 65:
        issues.append({"type": "warn", "field": "title", "msg": f"Title too long ({title_len} chars, max ~60)"})
        score -= 8
    
    # Description checks
    if not desc:
        issues.append({"type": "critical", "field": "description", "msg": "Missing meta description"})
        score -= 25
    elif desc_len < 80:
        issues.append({"type": "warn", "field": "description", "msg": f"Description too short ({desc_len} chars, recommended 140-160)"})
        score -= 10
    elif desc_len > 165:
        issues.append({"type": "warn", "field": "description", "msg": f"Description truncated in SERP ({desc_len} chars, max ~160)"})
        score -= 5
    
    # Keyword presence
    kw_in_title = sum(1 for kw in target_keywords if kw.lower() in title.lower())
    kw_in_desc = sum(1 for kw in target_keywords if kw.lower() in desc.lower())
    
    if target_keywords and kw_in_title == 0:
        issues.append({"type": "warn", "field": "title", "msg": "Primary keywords not in title"})
        score -= 15
    
    if target_keywords and kw_in_desc == 0:
        issues.append({"type": "warn", "field": "description", "msg": "Primary keywords not in description"})
        score -= 10
    
    # CTR-optimization signals
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
