"""
Client for pushing footer (bottom) text to the Magento bottom-text API.

Required Railway env vars:
  FOOTER_TEXT_API       — full URL to POST endpoint (e.g. https://.../footer/text)
  FOOTER_TEXT_API_USER  — Basic auth username
  FOOTER_TEXT_API_PASS  — Basic auth password
  FOOTER_TEXT_STORE_ID  — integer store ID

Behavior:
  - disableExistingTexts is ALWAYS True (full replace)
  - 50s timeout, no automatic retries (a stale retry could wipe live text)
  - Full payload + response snapshot logged to /data/footer_push_log.json
"""

import os
import re
import json
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, NavigableString

TIMEOUT_SECONDS = 50
DATA_DIR = "/data"
LOG_PATH = os.path.join(DATA_DIR, "footer_push_log.json")

# h2 text fallback patterns when the schema.org FAQPage marker is absent
_FAQ_H2_PATTERNS = [
    "faq",
    "vanliga frågor",
    "vanliga fragor",
    "ofte stillede spørgsmål",
    "ofte stillede spoergsmaal",
    "spørgsmål og svar",
    "spoergsmaal og svar",
    "ofte stilte spørsmål",
    "usein kysytyt kysymykset",
    "frequently asked",
]


# ── URL helpers ────────────────────────────────────────────────────

def add_www_to_url(url: str) -> str:
    """Return url with https://www. prefix (normalises http→https and adds www)."""
    if not url:
        return url
    u = str(url).strip()
    if u.startswith("http://"):
        u = "https://" + u[7:]
    elif not u.startswith("https://"):
        u = "https://" + u.lstrip("/")
    if "://www." in u.lower():
        return u
    return u.replace("://", "://www.", 1)


def _host_without_www(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def add_www_to_href_attrs(html: str, site_host: str) -> str:
    """
    Rewrite absolute href attributes pointing to our site so they include www.
    Leaves relative links ('/path') untouched. Normalises http→https for our host.
    """
    if not html or not site_host:
        return html
    host = site_host.lower().removeprefix("www.")
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        h = a["href"].strip()
        if not h:
            continue
        if h.lower().startswith("http://"):
            h = "https://" + h[7:]
        lower = h.lower()
        if lower.startswith(f"https://{host}/") or lower == f"https://{host}":
            h = "https://www." + host + h[len(f"https://{host}"):]
        a["href"] = h
    return str(soup)


# ── HTML → sections parser ─────────────────────────────────────────

def parse_bottom_html_to_sections(bottom_html: str) -> list[dict]:
    """
    Split bottom_html into API sections.

    Returns a list of {headline, content, sortOrder, tagAsFaq}.

    Rules:
      - Split on <h2>: each h2 starts a new section.
      - FAQ region identified by first element with itemtype containing
        "FAQPage" (schema marker). Fallback: h2 whose text matches
        _FAQ_H2_PATTERNS.
      - FAQ sections: one per Q/A pair. Q = h3 text (or itemprop=name).
        Answer = following content up to next h3 (or itemprop=text).
      - Non-FAQ sections are tagAsFaq=False. FAQ Q/A sections are tagAsFaq=True.
      - sortOrder: 1, 2, 3, ... in document order.
    """
    if not bottom_html or not bottom_html.strip():
        return []

    soup = BeautifulSoup(bottom_html, "html.parser")
    root = soup.body or soup

    faq_h2 = _find_faq_h2_in(root)

    children = [c for c in root.children if not (isinstance(c, NavigableString) and not c.strip())]

    pre_faq_nodes = []
    faq_nodes = []
    faq_reached = False
    for c in children:
        if c is faq_h2:
            faq_reached = True
        if faq_reached:
            faq_nodes.append(c)
        else:
            pre_faq_nodes.append(c)

    sections: list[dict] = []
    sort_order = 1

    # Non-FAQ sections — split on h2
    current_headline = None
    current_parts: list = []

    def _flush_regular():
        nonlocal current_headline, current_parts, sort_order
        if current_headline is None:
            current_parts = []
            return
        content = "".join(str(n) for n in current_parts).strip()
        if content:
            sections.append({
                "headline": current_headline,
                "content": content,
                "sortOrder": sort_order,
                "tagAsFaq": False,
            })
            sort_order += 1
        current_headline = None
        current_parts = []

    for node in pre_faq_nodes:
        if getattr(node, "name", None) == "h2":
            _flush_regular()
            current_headline = node.get_text(strip=True)
        else:
            if current_headline is not None:
                current_parts.append(node)
    _flush_regular()

    # FAQ sections — one section per Q/A pair
    for q, a_html in _extract_faq_qa_pairs(faq_nodes):
        if not q or not a_html:
            continue
        sections.append({
            "headline": q,
            "content": a_html,
            "sortOrder": sort_order,
            "tagAsFaq": True,
        })
        sort_order += 1

    return sections


def _find_faq_h2_in(root) -> Optional[object]:
    """Return the <h2> that begins the FAQ section, or None."""
    # Primary: schema marker
    faq_el = root.find(attrs={"itemtype": re.compile(r"FAQPage", re.I)})
    if faq_el:
        # Find nearest preceding h2 in document order
        for prev in faq_el.find_all_previous("h2"):
            return prev  # first = nearest
        return faq_el  # no preceding h2 → use the schema element itself as boundary
    # Fallback: h2 text match
    for h2 in root.find_all("h2"):
        text = h2.get_text(strip=True).lower()
        if any(p in text for p in _FAQ_H2_PATTERNS):
            return h2
    return None


def _extract_faq_qa_pairs(faq_nodes: list) -> list[tuple[str, str]]:
    """Extract (question_text, answer_html) pairs from the FAQ region."""
    if not faq_nodes:
        return []
    faq_html = "".join(str(n) for n in faq_nodes)
    soup = BeautifulSoup(faq_html, "html.parser")

    # Primary: schema.org Question items
    questions = soup.find_all(attrs={"itemtype": re.compile(r"/Question\b", re.I)})
    if questions:
        pairs: list[tuple[str, str]] = []
        for q_el in questions:
            name_el = q_el.find(attrs={"itemprop": "name"})
            q_text = name_el.get_text(strip=True) if name_el else ""
            answer_el = q_el.find(attrs={"itemtype": re.compile(r"/Answer\b", re.I)})
            if not answer_el:
                continue
            text_el = answer_el.find(attrs={"itemprop": "text"})
            a_html = (text_el.decode_contents() if text_el else answer_el.decode_contents()).strip()
            if q_text and a_html:
                pairs.append((q_text, a_html))
        if pairs:
            return pairs

    # Fallback: h3 with following p/ul/ol/div siblings, walked at the parent level
    first_h3 = soup.find("h3")
    if not first_h3:
        return []
    parent = first_h3.parent
    pairs = []
    current_q = None
    current_parts: list = []

    def _flush():
        nonlocal current_q, current_parts
        if current_q:
            a = "".join(str(n) for n in current_parts).strip()
            if a:
                pairs.append((current_q, a))
        current_q = None
        current_parts = []

    for sib in parent.children:
        if isinstance(sib, NavigableString):
            continue
        name = getattr(sib, "name", None)
        if name == "h3":
            _flush()
            current_q = sib.get_text(strip=True)
        elif name in ("p", "ul", "ol", "div", "blockquote"):
            if current_q:
                current_parts.append(sib)
    _flush()
    return pairs


# ── Validation ─────────────────────────────────────────────────────

def validate_before_push(bottom_html: str) -> tuple[bool, str]:
    """Return (ok, error_message). Blocks push if no <h2> structure."""
    if not bottom_html or not bottom_html.strip():
        return False, "No bottom text content — generate content first."
    soup = BeautifulSoup(bottom_html, "html.parser")
    if not soup.find("h2"):
        return False, "No <h2> headings found in generated text. Regenerate content to get proper section structure."
    return True, ""


def is_url_audited(url: str, audit_results: Optional[list]) -> bool:
    """Check if URL is present in audit_results (soft check)."""
    if not audit_results:
        return True  # no audit data loaded → don't block
    try:
        from utils.ui_helpers import normalize_url
    except Exception:
        return True
    target = normalize_url(url)
    for r in audit_results:
        if normalize_url(r.get("url", "")) == target:
            return True
    return False


# ── Payload + push ─────────────────────────────────────────────────

def build_payload(url: str, bottom_html: str, store_id: int) -> dict:
    """Build the footer/text API payload (adds www to URL + internal hrefs)."""
    site_host = _host_without_www(url)
    www_url = add_www_to_url(url)
    html_with_www = add_www_to_href_attrs(bottom_html, site_host)
    sections = parse_bottom_html_to_sections(html_with_www)
    return {
        "storeId": store_id,
        "url": www_url,
        "disableExistingTexts": True,
        "texts": sections,
    }


def push_footer_text(url: str, bottom_html: str) -> dict:
    """
    Push footer text to the API for this URL.

    Returns a result dict:
      {status: "success"|"http_error"|"timeout"|"network_error"|"error",
       http_code: int|None, response_body: str|None, error: str|None,
       payload: dict|None}
    """
    api_url = os.environ.get("FOOTER_TEXT_API", "").strip()
    api_user = os.environ.get("FOOTER_TEXT_API_USER", "").strip()
    api_pass = os.environ.get("FOOTER_TEXT_API_PASS", "").strip()
    store_id_str = os.environ.get("FOOTER_TEXT_STORE_ID", "").strip()

    if not api_url:
        return {"status": "error", "error": "FOOTER_TEXT_API env var not set on Railway", "payload": None}
    if not api_user or not api_pass:
        return {"status": "error", "error": "FOOTER_TEXT_API_USER / FOOTER_TEXT_API_PASS env vars not set", "payload": None}
    if not store_id_str:
        return {"status": "error", "error": "FOOTER_TEXT_STORE_ID env var not set", "payload": None}
    try:
        store_id = int(store_id_str)
    except ValueError:
        return {"status": "error", "error": f"FOOTER_TEXT_STORE_ID is not a valid integer: {store_id_str!r}", "payload": None}

    payload = build_payload(url, bottom_html, store_id)
    if not payload.get("texts"):
        return {"status": "error", "error": "No sections parsed from generated HTML — cannot push.", "payload": payload}

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "url": url,
        "payload_url": payload["url"],
        "store_id": store_id,
        "section_count": len(payload["texts"]),
        "payload": payload,
        "status": None,
        "http_code": None,
        "response_body": None,
        "error": None,
    }

    try:
        resp = requests.post(
            api_url,
            json=payload,
            auth=(api_user, api_pass),
            timeout=TIMEOUT_SECONDS,
            headers={"Content-Type": "application/json"},
        )
        entry["http_code"] = resp.status_code
        body = resp.text or ""
        entry["response_body"] = body[:5000]
        if 200 <= resp.status_code < 300:
            entry["status"] = "success"
            result = {"status": "success", "http_code": resp.status_code, "response_body": body, "payload": payload, "error": None}
        else:
            entry["status"] = "http_error"
            entry["error"] = f"HTTP {resp.status_code}"
            result = {"status": "http_error", "http_code": resp.status_code, "response_body": body, "error": f"HTTP {resp.status_code}", "payload": payload}
    except requests.Timeout:
        entry["status"] = "timeout"
        entry["error"] = f"Timeout after {TIMEOUT_SECONDS}s"
        result = {"status": "timeout", "http_code": None, "response_body": None, "error": entry["error"], "payload": payload}
    except Exception as e:
        entry["status"] = "network_error"
        entry["error"] = str(e)
        result = {"status": "network_error", "http_code": None, "response_body": None, "error": str(e), "payload": payload}

    _append_push_log(entry)
    return result


# ── Audit log ──────────────────────────────────────────────────────

def _append_push_log(entry: dict) -> None:
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        log = []
        if os.path.exists(LOG_PATH):
            try:
                with open(LOG_PATH, "r", encoding="utf-8") as f:
                    log = json.load(f)
            except Exception:
                log = []
        log.append(entry)
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # never let logging break the push flow


def read_push_log(url: Optional[str] = None) -> list:
    if not os.path.exists(LOG_PATH):
        return []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            log = json.load(f)
    except Exception:
        return []
    if url:
        try:
            from utils.ui_helpers import normalize_url
            target = normalize_url(url)
            return [e for e in log if normalize_url(e.get("url", "")) == target]
        except Exception:
            return [e for e in log if e.get("url") == url]
    return log


def last_successful_push(url: str) -> Optional[dict]:
    for e in reversed(read_push_log(url)):
        if e.get("status") == "success":
            return e
    return None
