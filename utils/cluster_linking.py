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

    Single source of truth — every view/util that needs to suggest an
    anchor for a target URL should call this. Uses the audit's title
    (first part before pipe/dash) when available, falls back to the
    URL's last segment with hyphens turned into spaces.
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
        if pillar:
            pillar_anchor = _anchor_for(pillar, audit_lookup, default=topic)
            for spoke in spokes:
                pair = (spoke, pillar)
                if pair in seen_pairs:
                    continue
                existing_out = _existing_outbound_links(sf_link_map, spoke)
                if pillar in existing_out:
                    continue  # already linked
                seen_pairs.add(pair)
                recommendations.append({
                    "from_url": spoke,
                    "to_url": pillar,
                    "anchor": pillar_anchor,
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
                recommendations.append({
                    "from_url": pillar,
                    "to_url": spoke,
                    "anchor": _anchor_for(spoke, audit_lookup),
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
                    recommendations.append({
                        "from_url": s_from,
                        "to_url": s_to,
                        "anchor": _anchor_for(s_to, audit_lookup),
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
