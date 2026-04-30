"""
Cluster-based internal linking recommendations.

Generates concrete "page X should link to page Y with anchor Z"
recommendations based on the topic cluster topology:

- VERTICAL-UP:   spoke → pillar (every spoke must link up to its pillar)
- VERTICAL-DOWN: pillar → spoke (pillar should link down to all its spokes)
- HORIZONTAL:    spoke ↔ sibling spoke (spokes in same cluster link to each other)

Reads existing links from sf_link_map and only recommends links that
are MISSING. Used by Internal Linking view + AI plans.
"""

from utils.ui_helpers import normalize_url
from utils.url_helpers import url_path


def _url_hierarchy_pillar(pages: list) -> str:
    """
    Pick the cluster page that is a URL-parent of one or more other
    cluster pages. Among candidates with descendants in the cluster,
    prefer the LONGEST path — i.e. the most specific common parent.

    Example: cluster contains /sexleksaker, /sexleksaker/dildos,
    /sexleksaker/dildos/klassisk-dildo, /sexleksaker/dildos/strap-on.
    Both /sexleksaker (3 descendants) and /sexleksaker/dildos (2
    descendants) qualify — we pick /sexleksaker/dildos because it is
    the topical hub, not the broader category root.
    """
    page_urls = [normalize_url(p.get("page", "")) for p in pages]
    page_urls = [u for u in page_urls if u]
    if len(page_urls) < 2:
        return ""

    candidates = []
    for u in page_urls:
        u_path = url_path(u).rstrip("/")
        if not u_path or u_path == "/":
            continue
        descendants = sum(
            1 for other in page_urls
            if other != u and url_path(other).rstrip("/").startswith(u_path + "/")
        )
        if descendants > 0:
            candidates.append((u, descendants, len(u_path)))

    if not candidates:
        return ""
    # Longest path first (most specific hub), then most descendants as tiebreak.
    candidates.sort(key=lambda x: (-x[2], -x[1]))
    return candidates[0][0]


def detect_pillar(cluster: dict) -> str:
    """
    Identify the pillar page in a cluster.

    Priority:
    1. URL-hierarchy pillar — a cluster page that is a URL-parent of
       other cluster pages (e.g. /dildos when /dildos/klassisk-dildo,
       /dildos/strap-on are also in the cluster). This preserves the
       site architecture even when Google currently ranks a sub-page
       for the broad cluster query.
    2. Fallback — page with the most queries in the cluster (>1 query),
       tie-broken by most clicks.

    Returns normalized URL or empty string.
    """
    pages = cluster.get("pages", []) or []
    if len(pages) < 3:
        return ""  # too small to have a meaningful pillar

    hierarchy_pillar = _url_hierarchy_pillar(pages)
    if hierarchy_pillar:
        return hierarchy_pillar

    candidates = [p for p in pages if p.get("query_count", 0) > 1]
    if not candidates:
        return ""
    pillar = max(candidates, key=lambda p: (p.get("query_count", 0), p.get("total_clicks", 0)))
    return normalize_url(pillar.get("page", ""))


def _existing_outbound_links(sf_link_map: dict, page_url: str) -> set:
    """Set of normalized URLs that page_url already links TO."""
    if not sf_link_map or not isinstance(sf_link_map, dict):
        return set()
    links_from = sf_link_map.get("links_from", {}) or {}
    outlinks = links_from.get(normalize_url(page_url), []) or []
    out = set()
    for item in outlinks:
        target = item.get("url", "") if isinstance(item, dict) else str(item)
        if target:
            out.add(normalize_url(target))
    return out


def anchor_for_url(page_url: str, audit_lookup: dict | None = None, default: str = "") -> str:
    """
    Pick a sensible anchor text for linking TO the given page.

    Title-based fallback used when no cluster context is available. For
    cluster-aware diverse anchor selection use ``pick_diverse_anchor``.
    """
    audit_lookup = audit_lookup or {}
    audit = audit_lookup.get(normalize_url(page_url), {}) or {}
    title = (audit.get("title") or "").strip()
    if title:
        import re as _re
        first = _re.split(r"[|–—\-»]", title)[0].strip()
        if 3 <= len(first) <= 60:
            return first
    # fallback: last URL segment
    last = url_path(page_url).split("/")[-1].replace("-", " ").strip()
    return last or default


# Back-compat alias — old name was private with underscore.
_anchor_for = anchor_for_url


def _spoke_primary_kw(page_url: str, audit_lookup: dict | None = None,
                      default: str = "") -> str:
    """
    Best single keyword phrase to describe a spoke page — used as anchor
    when linking TO that spoke. Tries the page's actual primary GSC
    query first (most authentic), falls back to title-derived anchor.
    """
    try:
        from utils.page_profile import build_page_profile
        prof = build_page_profile(page_url) or {}
        pq = (prof.get("primary_query") or "").strip()
        if 3 <= len(pq) <= 60:
            return pq
    except Exception:
        pass
    return anchor_for_url(page_url, audit_lookup, default=default)


def _hub_anchor_pool(cluster: dict, hub_url: str,
                     audit_lookup: dict | None = None) -> list:
    """
    Build an ordered, deduplicated pool of anchor variants for linking
    UP to a cluster hub.

    Order of preference (Google rewards anchor diversity — uniform anchor
    profiles look unnatural since Penguin):
      1. Top GSC queries the cluster ranks for (real user phrasings)
      2. Hub's title-derived anchor (single-token canonical)
      3. Cluster topic name (last-resort generic)
    """
    pool: list = []
    seen: set = set()

    def _add(candidate: str):
        c = (candidate or "").strip()
        if not c or len(c) < 3 or len(c) > 60:
            return
        key = c.lower()
        if key in seen:
            return
        seen.add(key)
        pool.append(c)

    # 1. Cluster's actual GSC queries — naturally varied by user phrasing
    queries = cluster.get("queries", []) or []
    for q in queries[:20]:  # cap pool to keep diversity meaningful
        _add(q)

    # 2. Hub's title-derived anchor
    if hub_url:
        _add(anchor_for_url(hub_url, audit_lookup))

    # 3. Cluster topic as final fallback
    _add(cluster.get("topic", ""))

    return pool


def pick_diverse_anchor(target_url: str,
                        source_url: str,
                        cluster: dict | None,
                        audit_lookup: dict | None,
                        used_anchors_for_target: set,
                        link_type: str = "vertical-up") -> str:
    """
    Pick an anchor text for ``source_url -> target_url`` that:

    - Reads naturally given target's topical profile
    - Differs from anchors already used to point to the same target
      (Google detects exact-match anchor saturation as spam since 2012)

    ``link_type`` selects the anchor pool:
      - ``vertical-up``   (spoke → hub):        rotate through cluster.queries
      - ``vertical-down`` (hub → spoke):        spoke's primary kw
      - ``horizontal``    (spoke → sibling):    target spoke's primary kw

    ``used_anchors_for_target`` is mutated — pass the same set across
    calls for the same target so different sources get different anchors.
    """
    audit_lookup = audit_lookup or {}
    used_lower = {a.lower() for a in used_anchors_for_target}

    if link_type == "vertical-up" and cluster:
        pool = _hub_anchor_pool(cluster, target_url, audit_lookup)
    elif link_type == "vertical-down":
        primary = _spoke_primary_kw(target_url, audit_lookup,
                                    default=anchor_for_url(target_url, audit_lookup))
        pool = [primary] if primary else []
        # Add secondary variants from cluster (but only those that match the spoke)
        if cluster:
            spoke_path = url_path(target_url).rstrip("/").lower()
            spoke_tail = spoke_path.split("/")[-1] if spoke_path else ""
            for q in (cluster.get("queries", []) or [])[:15]:
                if not q or len(q) < 3 or len(q) > 60:
                    continue
                # Keep cluster queries that contain the spoke's tail token
                # (= they're modifier variants of this specific spoke)
                if spoke_tail and any(tok in q.lower() for tok in spoke_tail.split("-") if len(tok) >= 3):
                    if q.lower() not in {p.lower() for p in pool}:
                        pool.append(q)
    elif link_type == "horizontal":
        primary = _spoke_primary_kw(target_url, audit_lookup,
                                    default=anchor_for_url(target_url, audit_lookup))
        pool = [primary] if primary else []
    else:
        pool = []

    # Always include title fallback so we never return empty
    title_anchor = anchor_for_url(target_url, audit_lookup)
    if title_anchor and title_anchor.lower() not in {p.lower() for p in pool}:
        pool.append(title_anchor)

    # Pick first unused; if all used, cycle (rare — only when clusters
    # are tiny + many spokes share one target).
    for a in pool:
        if a.lower() not in used_lower:
            used_anchors_for_target.add(a)
            return a
    if pool:
        used_anchors_for_target.add(pool[0])
        return pool[0]
    return target_url.rsplit("/", 1)[-1].replace("-", " ")


def generate_cluster_link_recommendations(
    clusters: list,
    audit_results: list,
    sf_link_map: dict | None,
) -> list:
    """
    Walk every cluster + emit missing link recommendations.

    Returns list of dicts:
      {
        "from_url": ..., "to_url": ..., "anchor": ...,
        "type": "vertical-up" | "vertical-down" | "horizontal",
        "cluster_topic": ...,
        "priority": 1-3,
        "reason": ...,
      }
    """
    audit_lookup = {normalize_url(r.get("url", "")): r for r in (audit_results or [])}
    recommendations = []
    seen_pairs = set()
    # Tracks which anchors we've already used pointing to each target so
    # the rec set hands out diverse anchors (Google flags uniform anchor
    # profiles as unnatural).
    used_anchors_per_target: dict[str, set] = {}

    def _used(target: str) -> set:
        return used_anchors_per_target.setdefault(target, set())

    for cluster in (clusters or []):
        topic = cluster.get("topic", "")
        pages = cluster.get("pages", []) or []
        if len(pages) < 2:
            continue

        page_urls = [normalize_url(p.get("page", "")) for p in pages if p.get("page")]
        page_urls = [u for u in page_urls if u]
        pillar = detect_pillar(cluster)
        spokes = [u for u in page_urls if u != pillar] if pillar else page_urls

        # ── 1. VERTICAL-UP: every spoke must link to pillar ─────
        # Each spoke gets a DIFFERENT anchor variant from the cluster's
        # query pool — no two spokes link up with the same exact anchor.
        if pillar:
            for spoke in spokes:
                pair = (spoke, pillar)
                if pair in seen_pairs:
                    continue
                existing_out = _existing_outbound_links(sf_link_map, spoke)
                if pillar in existing_out:
                    continue  # already linked
                seen_pairs.add(pair)
                anchor = pick_diverse_anchor(
                    target_url=pillar,
                    source_url=spoke,
                    cluster=cluster,
                    audit_lookup=audit_lookup,
                    used_anchors_for_target=_used(pillar),
                    link_type="vertical-up",
                )
                recommendations.append({
                    "from_url": spoke,
                    "to_url": pillar,
                    "anchor": anchor,
                    "type": "vertical-up",
                    "cluster_topic": topic,
                    "priority": 1,
                    "reason": f"Spoke → pillar (cluster: {topic}). Strengthens pillar's topical authority.",
                })

        # ── 2. VERTICAL-DOWN: pillar links down to top spokes ───
        if pillar and spokes:
            existing_out = _existing_outbound_links(sf_link_map, pillar)
            # Only top 5 spokes by clicks — don't spam pillar with 50 links
            spoke_with_clicks = []
            for s in spokes:
                a = audit_lookup.get(s, {}) or {}
                spoke_with_clicks.append((s, a.get("clicks", 0) or 0))
            spoke_with_clicks.sort(key=lambda x: -x[1])
            top_spokes = [s for s, _ in spoke_with_clicks[:5]]
            for spoke in top_spokes:
                pair = (pillar, spoke)
                if pair in seen_pairs:
                    continue
                if spoke in existing_out:
                    continue
                seen_pairs.add(pair)
                anchor = pick_diverse_anchor(
                    target_url=spoke,
                    source_url=pillar,
                    cluster=cluster,
                    audit_lookup=audit_lookup,
                    used_anchors_for_target=_used(spoke),
                    link_type="vertical-down",
                )
                recommendations.append({
                    "from_url": pillar,
                    "to_url": spoke,
                    "anchor": anchor,
                    "type": "vertical-down",
                    "cluster_topic": topic,
                    "priority": 2,
                    "reason": f"Pillar → top spoke (cluster: {topic}). Helps Google find spokes.",
                })

        # ── 3. HORIZONTAL: top spokes link to each other ────────
        # Only top 5 spokes (avoid N×N explosion). Each links to ONE
        # other top spoke (the next-best by clicks) — chain pattern.
        if len(spokes) >= 2:
            spoke_with_clicks = []
            for s in spokes:
                a = audit_lookup.get(s, {}) or {}
                spoke_with_clicks.append((s, a.get("clicks", 0) or 0))
            spoke_with_clicks.sort(key=lambda x: -x[1])
            top = [s for s, _ in spoke_with_clicks[:5]]
            for i, s_from in enumerate(top):
                # Link to next spoke in the ranked list
                for s_to in top[i + 1:i + 2]:
                    pair = (s_from, s_to)
                    if pair in seen_pairs:
                        continue
                    existing_out = _existing_outbound_links(sf_link_map, s_from)
                    if s_to in existing_out:
                        continue
                    seen_pairs.add(pair)
                    anchor = pick_diverse_anchor(
                        target_url=s_to,
                        source_url=s_from,
                        cluster=cluster,
                        audit_lookup=audit_lookup,
                        used_anchors_for_target=_used(s_to),
                        link_type="horizontal",
                    )
                    recommendations.append({
                        "from_url": s_from,
                        "to_url": s_to,
                        "anchor": anchor,
                        "type": "horizontal",
                        "cluster_topic": topic,
                        "priority": 3,
                        "reason": f"Sibling spoke → spoke (cluster: {topic}). Distributes link equity within cluster.",
                    })

    # Sort by priority then by from_url for stable output
    recommendations.sort(key=lambda r: (r["priority"], r["from_url"]))
    return recommendations


def summarize_recommendations(recommendations: list) -> dict:
    """Aggregate counts for UI display."""
    by_type = {"vertical-up": 0, "vertical-down": 0, "horizontal": 0}
    by_cluster = {}
    pages_affected = set()
    for r in recommendations:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
        by_cluster[r["cluster_topic"]] = by_cluster.get(r["cluster_topic"], 0) + 1
        pages_affected.add(r["from_url"])
    return {
        "total": len(recommendations),
        "by_type": by_type,
        "by_cluster": by_cluster,
        "pages_affected": len(pages_affected),
    }
