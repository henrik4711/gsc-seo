"""
Cluster-suggestion helper: given a page URL + title, score each existing
topic cluster by how well its terms overlap with the page's URL/title
tokens, and return the best match(es).

Used by:
  - views/quick_wins.py for the priority-action drilldown (assign_clusters)
  - views/structure_fix.py to pre-fill the Unclustered Pages dropdown
    with the AI's best guess so the user doesn't have to read every URL
    and find the matching cluster manually

Shared logic lives here (not in views/) per the project's shared-logic
rule — duplicating tokenization and scoring across views was the source
of subtle bugs (one view filtered the brand token, the other didn't,
producing different suggestions for the same page).
"""

import re
import streamlit as st


_MATCH_TOKEN_RE = re.compile(r"[a-zåäöæøéèà0-9]+")

# Tokens that appear in many queries/titles and would otherwise dominate
# cluster matching. Universal stop words + Scandinavian common words.
# Site-specific brand tokens (mshop, etc.) are added dynamically via
# _site_brand_tokens() so this list stays portable across sites.
_MATCH_STOP_BASE = {
    "and", "the", "for", "with", "this", "that", "from", "are", "was",
    "och", "att", "som", "med", "till", "kop", "kopa", "kob",
    "html", "www", "com", "https", "http",
}


def site_brand_tokens() -> set:
    """Tokens derived from the configured site's own domain name
    (e.g. www.mshop.se → {"mshop"}, www.mshop.dk → {"mshop"}).

    These appear in nearly every page title because of the "| <Brand>"
    suffix many e-commerce CMSes add automatically. Filtered out so they
    don't drown the real topic signal — otherwise every page would
    "match" a noise cluster called brand_<sitename>.

    Returns an empty set if no GSC site is configured yet."""
    site = (st.session_state.get("gsc_site") or "").lower()
    if not site:
        return set()
    try:
        from urllib.parse import urlparse
        netloc = urlparse(site).netloc or site
    except Exception:
        netloc = site
    netloc = netloc.replace("https://", "").replace("http://", "")
    if netloc.startswith("www."):
        netloc = netloc[4:]
    stem = netloc.split(".")[0] if netloc else ""
    if not stem or len(stem) < 3:
        return set()
    return {stem}


def tokenize_for_match(text: str) -> set:
    """Lowercase tokenization with stop-word + brand-token filtering.
    Used for both page-side tokens and cluster-signature tokens so the
    overlap computation is symmetric."""
    if not text:
        return set()
    stop = _MATCH_STOP_BASE | site_brand_tokens()
    return {t for t in _MATCH_TOKEN_RE.findall(text.lower())
            if len(t) >= 3 and t not in stop}


def is_site_brand_cluster(cluster_topic: str) -> bool:
    """True if the cluster is just the site's own brand (e.g. 'brand_mshop').
    These are noise — visitors searching the site name should land on the
    homepage, not need their own topical cluster. Filtered from suggestions."""
    if not cluster_topic:
        return False
    t = cluster_topic.lower().strip()
    brands = site_brand_tokens()
    if not brands:
        return False
    for b in brands:
        if t == b or t == f"brand_{b}":
            return True
    return False


def suggest_cluster_for_page(
    url: str,
    title: str,
    clusters: list,
    top_n: int = 1,
) -> list:
    """Score each cluster against URL/title tokens; return top matches
    with their overlap terms.

    Returns a list of dicts: [{"cluster": topic, "score": float, "match_terms": [...]}]
    Empty list if no cluster has any overlapping token.

    Score formula: overlap_size × 100 / max(8, cluster_signature_size).
    This favors specific clusters (smaller signatures) over broad ones,
    so a page whose URL contains "vibrator" matches a "vibratorer"
    cluster more strongly than a "sexleksaker" cluster that also
    happens to mention vibrators.
    """
    page_tokens = tokenize_for_match(f"{url} {title}")
    if not page_tokens:
        return []
    scored = []
    for c in clusters:
        topic = c.get("topic", "") or ""
        if is_site_brand_cluster(topic):
            continue
        core_terms = c.get("core_terms", []) or []
        queries = c.get("queries", []) or []
        sig_text = topic + " " + " ".join(core_terms) + " " + " ".join(queries[:30])
        sig = tokenize_for_match(sig_text)
        if not sig:
            continue
        overlap = page_tokens & sig
        if not overlap:
            continue
        score = len(overlap) * 100 / max(8, len(sig))
        scored.append((score, len(overlap), topic, sorted(overlap)[:4]))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [
        {"cluster": t[2], "score": round(t[0], 1), "match_terms": t[3]}
        for t in scored[:top_n]
    ]
