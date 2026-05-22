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


def _tokens_overlap_prefix(a: set, b: set, min_len: int = 4) -> set:
    """Return the set of tokens from `a` that either exactly match a
    token in `b` OR are a prefix of (or share a prefix with) a token
    in `b` — provided the shorter token is at least `min_len` characters.

    Catches cases like "vibrator" (core term) vs "vibratorer" (in URL)
    where Scandinavian plural / definite-article suffixes make the two
    tokens look different to an exact-equality match but they're
    semantically the same word. The min_len floor avoids false matches
    like "ana" matching "anal", "anatomi", etc.
    """
    if not a or not b:
        return set()
    matched = set()
    for ta in a:
        if ta in b:
            matched.add(ta)
            continue
        # Prefix match — try ta as a prefix of any b-token (or vice versa)
        for tb in b:
            shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
            if len(shorter) >= min_len and longer.startswith(shorter):
                matched.add(ta)
                break
    return matched


def _url_segment_tokens(url: str) -> list:
    """Return tokenized URL path segments in order. Used to compute the
    'depth' at which a cluster matches — a topic that matches a deeper
    segment is more specific than one that matches a top-level segment.

    E.g. for /sexleksaker/vibratorer/vibratorer-med-varmefunktion this
    returns [{'sexleksaker'}, {'vibratorer'}, {'vibratorer', 'varmefunktion'}]
    so a "vibratorer" cluster gets depth=2 (most specific match) and a
    "sexleksaker" cluster gets depth=0 (parent category)."""
    try:
        from urllib.parse import urlparse
        path = urlparse(url).path or url
    except Exception:
        path = url
    segments = [s for s in path.strip("/").split("/") if s]
    return [tokenize_for_match(s) for s in segments]


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

    Scoring (higher = stronger match):
      • BASE (0-100): overlap_size × 100 / max(8, signature_size).
        Favors specific clusters with concentrated signatures.
      • TOPIC BONUS (+40): any topic token appears in page tokens, with
        prefix matching so "vibrator" ↔ "vibratorer" matches.
      • CORE-TERM BONUS (+15 each, max +30): tokens from cluster.core_terms
        appear in page tokens (also with prefix matching).
      • DEPTH BONUS (+10 × deepest URL-segment index where topic or
        core-term token appears): prefers /sexleksaker/vibratorer/X
        matching "vibratorer" cluster (depth 2) over "sexleksaker"
        cluster (depth 0). Critical for hierarchical category URLs
        where the parent category is itself a valid cluster.

    Example: /sexleksaker/vibratorer/vibratorer-med-varmefunktion
      vibratorer cluster: base ~12 + topic +40 + core +15 + depth(2) +20 = 87
      sexleksaker cluster: base ~12 + topic +40 + core +15 + depth(0) +0  = 67
      → vibratorer wins, which is the topically-correct answer.
    """
    page_tokens = tokenize_for_match(f"{url} {title}")
    if not page_tokens:
        return []
    seg_tokens_list = _url_segment_tokens(url)
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

        # Use prefix-aware overlap. Exact match still counts; the prefix
        # path catches plural/definite-article variants like vibrator↔vibratorer.
        overlap = _tokens_overlap_prefix(page_tokens, sig)
        if not overlap:
            continue

        # Base score — concentration-based, favors specific clusters
        score = len(overlap) * 100 / max(8, len(sig))

        topic_tokens = tokenize_for_match(topic)
        core_term_tokens = tokenize_for_match(" ".join(core_terms))

        # Topic bonus (with prefix matching too)
        if _tokens_overlap_prefix(topic_tokens, page_tokens):
            score += 40

        # Core-term bonus (with prefix matching), capped
        core_matches = len(_tokens_overlap_prefix(core_term_tokens, page_tokens))
        score += min(30, core_matches * 15)

        # Depth bonus — encourage matches at deeper URL segments, which
        # are more specific than top-level path matches.
        topic_or_core = topic_tokens | core_term_tokens
        deepest = -1
        for i, seg_t in enumerate(seg_tokens_list):
            if _tokens_overlap_prefix(topic_or_core, seg_t):
                deepest = i
        if deepest >= 0:
            score += deepest * 10

        scored.append((score, len(overlap), topic, sorted(overlap)[:4]))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [
        {"cluster": t[2], "score": round(t[0], 1), "match_terms": t[3]}
        for t in scored[:top_n]
    ]
