"""
Topical scope: which queries a page should OWN vs. DEFER to its hub.

When a topic cluster has a clear hub (URL-hierarchy parent), Google
ranks better when the hub owns the head term and each spoke owns its
own modifier-specific queries — with no cross-competition. This module
returns, for any spoke page, the keyword list it should target and the
keyword list it should NOT target (because the hub owns them).

Used by:
  - utils.cannibalization to emit per-page de-optimization recs
  - utils.ai_generator to brief AI generators with a "do not compete" list
  - views.quick_wins to show a Topical Scope panel on the per-page view
"""

import re as _re

from utils.ui_helpers import normalize_url
from utils.url_helpers import url_path
from utils.cluster_linking import detect_pillar


# ── Slug-match scoring (mirrors utils/cannibalization helpers) ─────────
# Kept local to avoid circular import. Same semantics: substring-tolerant
# token match, returns 0.0–1.0.

# Scandinavian/European umlaut → ASCII map (mirror of utils/cluster_linking
# and utils/cannibalization). URLs are typically transliterated, so we
# normalize both sides to ASCII before tokenizing.
_UMLAUT_MAP = str.maketrans({
    "ä": "a", "Ä": "A", "ö": "o", "Ö": "O",
    "å": "a", "Å": "A", "ø": "o", "Ø": "O",
    "æ": "a", "Æ": "A", "é": "e", "É": "E",
    "ü": "u", "Ü": "U",
})


def _normalize_chars(s: str) -> str:
    return s.translate(_UMLAUT_MAP) if s else s


def _slug_tokens(slug: str) -> set:
    if not slug:
        return set()
    raw = _re.split(r"[-_./]+", _normalize_chars(slug.lower()))
    return {t for t in raw if len(t) >= 3}


def _query_tokens(query: str) -> set:
    if not query:
        return set()
    return {t for t in _re.findall(r"\w+", _normalize_chars(query.lower())) if len(t) >= 3}


def _url_tail_segment(url: str) -> str:
    path = url_path(url).rstrip("/")
    if not path:
        return ""
    parts = [p for p in path.split("/") if p]
    return parts[-1] if parts else ""


def _slug_match_score(url: str, query: str) -> float:
    qtoks = _query_tokens(query)
    ttoks = _slug_tokens(_url_tail_segment(url))
    if not qtoks or not ttoks:
        return 0.0

    def _stem_match(a: str, b: str) -> bool:
        return a in b or b in a

    covered = sum(1 for q in qtoks if any(_stem_match(q, t) for t in ttoks))
    extras = sum(1 for t in ttoks if not any(_stem_match(t, q) for q in qtoks))
    coverage = covered / len(qtoks)
    if coverage < 1.0:
        return coverage * 0.5
    if extras == 0:
        return 1.0
    return max(0.5, 1.0 - extras * 0.2)


def synthesize_modifier_phrase(page_url: str, hub_url: str, topic: str) -> str:
    """
    Build the canonical modifier phrase from a spoke's URL slug.

    Used when GSC hasn't yet recorded the natural query for a spoke
    (low impressions / new page / dialect mismatch like 'dilde' vs
    'dildo'). The slug itself encodes the page's intended phrase —
    /sexleksaker/dildos/klassisk-dildo SHOULD own 'klassisk dildo'
    even if Google hasn't shown enough impressions for that exact
    string yet.

    Returns '' when the slug can't be safely converted:
      - no slug (homepage / single-segment URL)
      - slug doesn't include any cluster head-term token (then we
        don't know what cluster context it operates under — e.g.
        /amor-black in a dildos cluster: 'amor' isn't a dildo head
        term, so we can't claim it owns 'amor black')
      - slug has only head-term tokens with no modifier (the head
        term belongs to the hub, not the spoke).
    """
    spoke_slug = _url_tail_segment(page_url)
    if not spoke_slug:
        return ""
    spoke_tokens = _slug_tokens(spoke_slug)
    head_terms = _query_tokens(topic) | _slug_tokens(_url_tail_segment(hub_url))
    if not spoke_tokens or not head_terms:
        return ""

    def _stem(a: str, b: str) -> bool:
        return a in b or b in a

    has_head = any(_stem(s, h) for s in spoke_tokens for h in head_terms)
    has_modifier = any(
        not any(_stem(s, h) for h in head_terms)
        for s in spoke_tokens
    )
    if not (has_head and has_modifier):
        return ""
    return spoke_slug.replace("-", " ").replace("_", " ").lower().strip()


# ── Topical scope resolution ───────────────────────────────────────────

def get_topical_scope(page_url: str, topic_clusters: dict) -> dict | None:
    """
    For a SPOKE page in a cluster with a hub, return:

      {
        "is_hub": False,
        "hub_url": "...",
        "cluster_topic": "...",
        "owned": ["queries this spoke should target"],
        "do_not_compete": ["queries the hub owns — leave them alone"],
      }

    Returns None when the page is not in any cluster, or when its cluster
    has no hub (= no de-optimization required, all spokes are siblings).

    Returns ``{"is_hub": True, ...}`` when the page IS the hub of its
    cluster — used by the UI to render a "you own these queries" panel.
    """
    if not topic_clusters or not isinstance(topic_clusters, dict):
        return None
    page_norm = normalize_url(page_url)

    # Build audit_lookup for slug-match-aware hub detection. Reads from
    # session_state so callers don't have to thread audit_results through.
    audit_lookup = None
    try:
        import streamlit as _st
        _audit = _st.session_state.get("audit_results") or []
        if _audit:
            audit_lookup = {normalize_url(r.get("url", "")): r for r in _audit
                            if r.get("url")}
    except Exception:
        pass

    for cluster in topic_clusters.get("clusters", []) or []:
        page_urls = {normalize_url(p.get("page", ""))
                     for p in cluster.get("pages", []) or []}
        if page_norm not in page_urls and audit_lookup is None:
            continue
        # Allow page_norm to NOT be in cluster.pages if it's the slug-
        # match hub we're about to return — still relevant scope info.

        hub = detect_pillar(cluster, audit_lookup=audit_lookup)
        # Skip if neither this page nor the hub is in this cluster
        if page_norm not in page_urls and normalize_url(hub) != page_norm:
            continue
        cluster_queries = cluster.get("queries", []) or []
        topic = cluster.get("topic", "")

        if not hub:
            # No URL-hierarchy hub in this cluster — every page is a sibling,
            # nobody needs to defer to anybody. Skip de-opt.
            return None

        hub_norm = normalize_url(hub)
        is_hub = (page_norm == hub_norm)

        if is_hub:
            # The hub itself: it owns the head terms. Return the queries
            # it should keep and the spokes that defer to it.
            owned = []
            for q in cluster_queries:
                hub_score = _slug_match_score(hub, q)
                # Hub owns queries where it slug-matches well (head terms)
                if hub_score >= 0.95:
                    owned.append(q)
            return {
                "is_hub": True,
                "hub_url": hub,
                "cluster_topic": topic,
                "owned": owned[:20],
                "do_not_compete": [],
                "spoke_count": max(0, len(page_urls) - 1),
            }

        # Spoke case
        owned = []
        do_not_compete = []
        for q in cluster_queries:
            hub_score = _slug_match_score(hub, q)
            spoke_score = _slug_match_score(page_url, q)
            # Hub strictly beats spoke AND hub is a near-perfect match → hub owns it
            if hub_score >= 0.95 and hub_score > spoke_score:
                do_not_compete.append(q)
            # Spoke is a perfect match → spoke owns it
            elif spoke_score >= 0.95:
                owned.append(q)
            # Otherwise: ambiguous, leave out of both lists

        # Synthesize the spoke's canonical phrase from its slug if GSC hasn't
        # registered it yet. The slug encodes intent — /klassisk-dildo
        # should own 'klassisk dildo' even when Google hasn't recorded
        # impressions for that exact string. Add to owned if not already
        # there. Skip for slugs without a cluster head term (e.g. /amor-black
        # in a dildos cluster — we can't infer ownership).
        synth = synthesize_modifier_phrase(page_url, hub, topic)
        if synth:
            existing_lower = {o.lower() for o in owned}
            if synth.lower() not in existing_lower:
                owned.insert(0, synth)  # canonical phrase goes first

        return {
            "is_hub": False,
            "hub_url": hub,
            "cluster_topic": topic,
            "owned": owned[:15],
            "do_not_compete": do_not_compete[:15],
        }

    return None


def deoptimization_action_text(scope: dict, page_title: str = "",
                               page_h1: str = "",
                               page_meta_desc: str = "") -> str:
    """
    Build a concrete per-page action telling the user what to change so
    this spoke stops competing with its hub on the head term(s).
    """
    if not scope or scope.get("is_hub"):
        return ""
    owned = scope.get("owned", []) or []
    do_not_compete = scope.get("do_not_compete", []) or []
    hub_url = scope.get("hub_url", "")
    if not do_not_compete:
        return ""

    primary_owned = owned[0] if owned else ""
    primary_avoid = do_not_compete[0]

    bits = []
    bits.append(
        f"This page is competing with its hub (`{hub_url}`) on **{primary_avoid}**. "
        f"Hand that query to the hub and own **{primary_owned or '(your modifier-specific phrase)'}** instead."
    )

    title_l = (page_title or "").lower()
    if primary_avoid.lower() in title_l and (primary_owned and primary_owned.lower() not in title_l):
        bits.append(
            f"→ **Title:** rewrite so it leads with **\"{primary_owned}\"**, not bare \"{primary_avoid}\"."
        )

    h1_l = (page_h1 or "").lower()
    if primary_avoid.lower() in h1_l and (primary_owned and primary_owned.lower() not in h1_l):
        bits.append(
            f"→ **H1:** change to **\"{primary_owned}\"** — bare \"{primary_avoid}\" belongs on the hub."
        )

    desc_l = (page_meta_desc or "").lower()
    if primary_avoid.lower() in desc_l and (primary_owned and primary_owned.lower() not in desc_l):
        bits.append(
            f"→ **Meta description:** lead with **\"{primary_owned}\"**."
        )

    bits.append(
        f"→ **Body text:** keep \"{primary_avoid}\" mentions but reduce to ~30% density vs **\"{primary_owned}\"** "
        f"(don't strip it entirely — that breaks topical relevance)."
    )

    if len(do_not_compete) > 1:
        rest = ", ".join(f"\"{q}\"" for q in do_not_compete[1:6])
        bits.append(f"→ Other hub-owned queries to avoid as primary focus: {rest}.")

    return " ".join(bits)
