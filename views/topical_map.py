"""
Topical Map — total architecture overview.

For each topic cluster:
  - which URLs belong to it
  - which keywords each URL should own (top 3, from topical_scope)
  - which vertical-up / vertical-down / horizontal links the cluster's
    architecture requires, AND which of those already exist on the site
    vs. which are still missing (color-coded diff in the diagram)

Subgraph grouping kicks in when a cluster has many spokes — sibling
spokes that share a URL second-segment prefix collapse into a labelled
subgraph so the diagram stays readable.
"""

import re
from collections import defaultdict

import streamlit as st

from utils.ui_helpers import normalize_url, shorten_url, stable_hash
from utils.url_helpers import url_path, url_segments
from utils.cluster_linking import (
    detect_pillar,
    generate_cluster_link_recommendations,
)
from utils.topical_scope import get_topical_scope, _slug_match_score


# ── DOT helpers ────────────────────────────────────────────────────────

def _dot_id(url: str) -> str:
    """Stable graphviz-safe node id derived from URL."""
    return "n_" + stable_hash(normalize_url(url))[:10]


def _dot_escape(s: str) -> str:
    """Escape a string for use inside a DOT label (double-quoted)."""
    if s is None:
        return ""
    return (
        str(s)
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
        .replace("\n", "\\n")
    )


def _slug_of(url: str) -> str:
    """Last URL segment, hyphen-separated."""
    parts = [p for p in url_path(url).strip("/").split("/") if p]
    return parts[-1] if parts else "/"


def _link_exists(sf_link_map: dict, from_url: str, to_url: str) -> bool:
    if not sf_link_map:
        return False
    links_from = sf_link_map.get("links_from", {}) or {}
    targets = links_from.get(normalize_url(from_url), []) or []
    target_urls = set()
    for t in targets:
        u = t.get("url", "") if isinstance(t, dict) else str(t)
        if u:
            target_urls.add(normalize_url(u))
    return normalize_url(to_url) in target_urls


# ── Per-URL keyword resolution ─────────────────────────────────────────

def _top_keywords_for_url(url: str, cluster: dict, hub_url: str,
                          topic_clusters_state: dict) -> list:
    """
    Return up to 3 keywords this URL should own, drawn from the cluster's
    queries and filtered by slug-match.

    For the hub: head terms (queries that match the hub's slug perfectly).
    For a spoke: queries where this spoke is the better slug-match than
    the hub.
    """
    queries = cluster.get("queries", []) or []
    is_hub = (normalize_url(url) == normalize_url(hub_url)) if hub_url else False

    candidates = []
    for q in queries:
        url_score = _slug_match_score(url, q)
        hub_score = _slug_match_score(hub_url, q) if hub_url else 0.0
        if is_hub:
            # Hub owns queries where its slug-match is near-perfect
            if url_score >= 0.95:
                candidates.append((q, url_score))
        else:
            # Spoke owns queries where IT slug-matches better than hub
            # OR queries the spoke matches near-perfectly that hub doesn't.
            if url_score >= 0.95 and url_score > hub_score:
                candidates.append((q, url_score))

    # Sort by score desc, then by length asc (shorter = more head-term-y)
    candidates.sort(key=lambda x: (-x[1], len(x[0])))
    seen = set()
    out = []
    for q, _ in candidates:
        ql = q.lower()
        if ql in seen:
            continue
        seen.add(ql)
        out.append(q)
        if len(out) >= 3:
            break
    return out


# ── Spoke grouping ─────────────────────────────────────────────────────

def _group_spokes_by_prefix(spokes: list, hub_url: str) -> dict:
    """
    Group spokes by URL second-segment-after-hub prefix.

    Example: hub=/dildos, spokes=[/dildos/klassisk-silikon-dildo,
    /dildos/klassisk-glas-dildo, /dildos/strap-on-dildo, /dildos/realistisk]
    → groups = {
        "klassisk-*": [/klassisk-silikon-dildo, /klassisk-glas-dildo],
        "strap-on": [/strap-on-dildo],     # singleton, kept flat
        "realistisk": [/realistisk],       # singleton, kept flat
      }

    Singleton groups are returned with their own slug as the key. Groups
    of >= 2 spokes get a "prefix-*" key.
    """
    if not hub_url or len(spokes) < 5:
        # Not worth grouping — render flat
        return {_slug_of(s): [s] for s in spokes}

    hub_path = url_path(hub_url).rstrip("/")
    by_first_token = defaultdict(list)
    for s in spokes:
        s_path = url_path(s).rstrip("/")
        # Strip hub prefix
        relative = s_path[len(hub_path):].lstrip("/") if s_path.startswith(hub_path) else s_path.strip("/")
        first_seg = relative.split("/")[0] if relative else ""
        # The "first token" of the spoke segment, hyphen-split
        first_tok = first_seg.split("-")[0] if first_seg else _slug_of(s)
        if not first_tok:
            first_tok = _slug_of(s)
        by_first_token[first_tok].append(s)

    groups = {}
    for tok, members in by_first_token.items():
        if len(members) >= 2:
            groups[f"{tok}-*"] = members
        else:
            groups[_slug_of(members[0])] = members
    return groups


# ── Edge enumeration (pure architecture, no filtering) ─────────────────

def _ideal_links_for_cluster(cluster: dict, audit_lookup: dict) -> list:
    """All vertical-up / vertical-down / horizontal links the cluster's
    architecture WANTS, regardless of what currently exists. Reuses the
    canonical generator with sf_link_map=None so no existing-link
    filtering happens — we'll diff against existence ourselves."""
    return generate_cluster_link_recommendations(
        clusters=[cluster],
        audit_results=list(audit_lookup.values()),
        sf_link_map=None,
    )


# ── DOT builder ────────────────────────────────────────────────────────

_HUB_COLOR = "#33dd88"
_HUB_FILL = "#0d2d1a"
_SPOKE_COLOR = "#5bb4d4"
_SPOKE_FILL = "#0d1a2d"
_FLAT_FILL = "#12121f"
_EXIST_COLOR = "#33dd88"   # link exists
_MISS_COLOR = "#ff4455"    # link recommended but missing
_GROUP_COLOR = "#5533ff"


def _build_cluster_dot(cluster: dict,
                       audit_lookup: dict,
                       sf_link_map: dict,
                       topic_clusters_state: dict,
                       diff_mode: str = "all") -> str:
    """
    Build a Graphviz DOT source for a single cluster.

    diff_mode:
      - "all"          show both existing (green) and missing (red) edges
      - "missing_only" only show recommended-but-missing edges
      - "existing_only" only show existing architectural edges
    """
    pages = cluster.get("pages", []) or []
    page_urls = [normalize_url(p.get("page", "")) for p in pages if p.get("page")]
    page_urls = [u for u in page_urls if u]
    if not page_urls:
        return "digraph G { label=\"empty cluster\"; }"

    hub = detect_pillar(cluster, audit_lookup=audit_lookup) or ""
    spokes = [u for u in page_urls if u != hub] if hub else page_urls

    lines = ["digraph G {",
             "  rankdir=TB;",
             "  bgcolor=\"transparent\";",
             "  node [fontname=\"Arial\", fontsize=11, margin=\"0.18,0.10\"];",
             "  edge [fontname=\"Arial\", fontsize=9];",
             "  splines=ortho;",
             "  nodesep=0.45;",
             "  ranksep=0.7;"]

    # ── Hub node ─────────────────────────────────────────────────
    if hub:
        kws = _top_keywords_for_url(hub, cluster, hub, topic_clusters_state)
        kw_line = " · ".join(kws) if kws else "(no head terms detected)"
        label = f"📌 {_dot_escape(_slug_of(hub))}\\n{_dot_escape(kw_line)}"
        lines.append(
            f"  \"{_dot_id(hub)}\" [label=\"{label}\", shape=box, "
            f"style=\"rounded,filled,bold\", "
            f"fillcolor=\"{_HUB_FILL}\", color=\"{_HUB_COLOR}\", "
            f"fontcolor=\"{_HUB_COLOR}\", penwidth=2];"
        )

    # ── Spokes — grouped if many ─────────────────────────────────
    groups = _group_spokes_by_prefix(spokes, hub) if spokes else {}
    for grp_key, members in groups.items():
        is_real_group = len(members) >= 2 and grp_key.endswith("-*")
        if is_real_group:
            # subgraph cluster_<token>
            cluster_id = f"cluster_grp_{re.sub(r'[^a-zA-Z0-9]', '_', grp_key)}"
            lines.append(f"  subgraph {cluster_id} {{")
            lines.append(f"    label=\"{_dot_escape(grp_key)} · {len(members)} pages\";")
            lines.append(f"    style=\"dashed,rounded\"; color=\"{_GROUP_COLOR}\"; "
                         f"fontcolor=\"{_GROUP_COLOR}\"; fontsize=10;")
        for m in members:
            kws = _top_keywords_for_url(m, cluster, hub, topic_clusters_state)
            kw_line = " · ".join(kws) if kws else "(no slug-matched keyword)"
            label = f"{_dot_escape(_slug_of(m))}\\n{_dot_escape(kw_line)}"
            indent = "    " if is_real_group else "  "
            lines.append(
                f"{indent}\"{_dot_id(m)}\" [label=\"{label}\", shape=box, "
                f"style=\"rounded,filled\", fillcolor=\"{_SPOKE_FILL}\", "
                f"color=\"{_SPOKE_COLOR}\", fontcolor=\"{_SPOKE_COLOR}\"];"
            )
        if is_real_group:
            lines.append("  }")

    # ── Edges: ideal architecture, color by existence ─────────────
    ideal = _ideal_links_for_cluster(cluster, audit_lookup)
    edge_lines = []
    for rec in ideal:
        f_url, t_url = rec["from_url"], rec["to_url"]
        exists = _link_exists(sf_link_map, f_url, t_url)
        if diff_mode == "missing_only" and exists:
            continue
        if diff_mode == "existing_only" and not exists:
            continue
        color = _EXIST_COLOR if exists else _MISS_COLOR
        style = "solid" if exists else "dashed"
        anchor = _dot_escape(rec.get("anchor", ""))[:40]
        edge_attrs = (
            f"label=\"{anchor}\", color=\"{color}\", "
            f"fontcolor=\"{color}\", style=\"{style}\""
        )
        if rec["type"] == "horizontal":
            edge_attrs += ", constraint=false, arrowhead=vee, dir=both"
        edge_lines.append(
            f"  \"{_dot_id(f_url)}\" -> \"{_dot_id(t_url)}\" [{edge_attrs}];"
        )
    lines.extend(edge_lines)
    lines.append("}")
    return "\n".join(lines)


# ── Side table ─────────────────────────────────────────────────────────

def _render_cluster_side_table(cluster: dict,
                               audit_lookup: dict,
                               sf_link_map: dict,
                               topic_clusters_state: dict):
    """Tabular detail under the diagram: each URL with role, owned kws,
    do-not-compete, link counts (existing vs. recommended)."""
    import pandas as pd

    pages = cluster.get("pages", []) or []
    page_urls = [normalize_url(p.get("page", "")) for p in pages if p.get("page")]
    page_urls = [u for u in page_urls if u]
    hub = detect_pillar(cluster, audit_lookup=audit_lookup) or ""
    ideal = _ideal_links_for_cluster(cluster, audit_lookup)

    # Per-URL: count outbound recommended + outbound existing-of-recommended
    out_rec = defaultdict(int)
    out_exists = defaultdict(int)
    in_rec = defaultdict(int)
    in_exists = defaultdict(int)
    for rec in ideal:
        f, t = normalize_url(rec["from_url"]), normalize_url(rec["to_url"])
        out_rec[f] += 1
        in_rec[t] += 1
        if _link_exists(sf_link_map, f, t):
            out_exists[f] += 1
            in_exists[t] += 1

    rows = []
    for u in page_urls:
        scope = get_topical_scope(u, topic_clusters_state) or {}
        owned = scope.get("owned", []) or []
        dnc = scope.get("do_not_compete", []) or []
        role = "🟢 HUB" if normalize_url(u) == normalize_url(hub) else "SPOKE"
        rows.append({
            "URL": shorten_url(u),
            "Role": role,
            "Owns (top 3)": " · ".join(owned[:3]),
            "Do not compete": " · ".join(dnc[:3]),
            "Out: exists / total": f"{out_exists.get(normalize_url(u), 0)} / {out_rec.get(normalize_url(u), 0)}",
            "In: exists / total": f"{in_exists.get(normalize_url(u), 0)} / {in_rec.get(normalize_url(u), 0)}",
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


# ── Markdown export ────────────────────────────────────────────────────

def _cluster_to_markdown(cluster: dict,
                         audit_lookup: dict,
                         sf_link_map: dict,
                         topic_clusters_state: dict) -> str:
    pages = cluster.get("pages", []) or []
    page_urls = [normalize_url(p.get("page", "")) for p in pages if p.get("page")]
    page_urls = [u for u in page_urls if u]
    hub = detect_pillar(cluster, audit_lookup=audit_lookup) or ""
    topic = cluster.get("topic", "(unnamed)")
    ideal = _ideal_links_for_cluster(cluster, audit_lookup)

    lines = [f"## Cluster: {topic}\n"]
    if hub:
        lines.append(f"**Hub:** {hub}\n")
    else:
        lines.append("**Hub:** _none detected (cluster has no URL-hierarchy parent)_\n")
    lines.append(f"**Pages:** {len(page_urls)} · **Recommended links:** {len(ideal)}\n")

    lines.append("\n### URLs and owned keywords\n")
    for u in page_urls:
        scope = get_topical_scope(u, topic_clusters_state) or {}
        owned = scope.get("owned", []) or []
        dnc = scope.get("do_not_compete", []) or []
        role = "**HUB**" if normalize_url(u) == normalize_url(hub) else "spoke"
        lines.append(f"- {role}: `{u}`")
        if owned:
            lines.append(f"    - owns: {', '.join(owned[:5])}")
        if dnc:
            lines.append(f"    - do-not-compete: {', '.join(dnc[:5])}")

    lines.append("\n### Internal-link architecture\n")
    by_type = defaultdict(list)
    for rec in ideal:
        by_type[rec["type"]].append(rec)
    for t in ("vertical-up", "vertical-down", "horizontal"):
        recs = by_type.get(t, [])
        if not recs:
            continue
        lines.append(f"\n**{t}** ({len(recs)} link(s)):\n")
        for rec in recs:
            exists = _link_exists(sf_link_map, rec["from_url"], rec["to_url"])
            mark = "✓" if exists else "✗"
            lines.append(f"- {mark} `{rec['from_url']}` → `{rec['to_url']}` "
                         f"_(anchor: \"{rec.get('anchor', '')}\")_")
    return "\n".join(lines) + "\n"


def _all_clusters_to_markdown(clusters, audit_lookup, sf_link_map,
                              topic_clusters_state) -> str:
    parts = ["# Topical Map — full architecture report\n"]
    parts.append(f"_Total clusters: **{len(clusters)}**_\n")
    for c in clusters:
        parts.append(_cluster_to_markdown(c, audit_lookup, sf_link_map, topic_clusters_state))
        parts.append("\n---\n")
    return "\n".join(parts)


# ── Overview metrics ───────────────────────────────────────────────────

def _render_overview(clusters, audit_results, sf_link_map):
    audit_lookup = {normalize_url(r.get("url", "")): r for r in audit_results
                    if r.get("url")}
    page_urls_clustered = set()
    clusters_with_hub = 0
    clusters_without_hub = 0
    total_pages_in_clusters = 0
    for c in clusters:
        hub = detect_pillar(c, audit_lookup=audit_lookup)
        if hub:
            clusters_with_hub += 1
        else:
            clusters_without_hub += 1
        for p in c.get("pages", []) or []:
            u = normalize_url(p.get("page", ""))
            if u:
                page_urls_clustered.add(u)
                total_pages_in_clusters += 1

    all_audit_urls = {normalize_url(r.get("url", "")) for r in audit_results
                      if r.get("url")}
    orphans = all_audit_urls - page_urls_clustered

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clusters", f"{len(clusters)}", help="Topic clusters detected")
    c2.metric("Clusters with hub", f"{clusters_with_hub}",
              delta=f"-{clusters_without_hub} flat" if clusters_without_hub else None,
              delta_color="inverse",
              help="Clusters with a clear URL-hierarchy hub")
    c3.metric("Pages in clusters", f"{len(page_urls_clustered):,}")
    c4.metric("Orphan pages", f"{len(orphans):,}",
              help="Pages not in any cluster — flagged for cluster assignment")


# ── Issues panel ───────────────────────────────────────────────────────

def _render_issues(clusters, audit_results, sf_link_map):
    flat_clusters = []
    weak_hubs = []  # hubs missing >50% of recommended vertical-up
    multi_cluster_pages = defaultdict(set)  # page → set of cluster topics

    audit_lookup = {normalize_url(r.get("url", "")): r for r in audit_results}

    for c in clusters:
        topic = c.get("topic", "(unnamed)")
        hub = detect_pillar(c, audit_lookup=audit_lookup)
        page_urls = [normalize_url(p.get("page", "")) for p in c.get("pages", []) or []
                     if p.get("page")]
        page_urls = [u for u in page_urls if u]

        for u in page_urls:
            multi_cluster_pages[u].add(topic)

        if not hub and len(page_urls) >= 3:
            flat_clusters.append({"topic": topic, "size": len(page_urls)})
            continue
        if not hub:
            continue

        # Count vertical-up coverage
        spokes = [u for u in page_urls if u != hub]
        if not spokes:
            continue
        existing_up = sum(1 for s in spokes if _link_exists(sf_link_map, s, hub))
        coverage = existing_up / len(spokes)
        if coverage < 0.5:
            weak_hubs.append({
                "hub": hub, "topic": topic,
                "covered": existing_up, "total": len(spokes),
                "pct": int(coverage * 100),
            })

    cross_cluster = {u: list(topics) for u, topics in multi_cluster_pages.items()
                     if len(topics) >= 2}

    st.markdown("### 🚨 Issues to investigate")

    issue_cols = st.columns(3)
    with issue_cols[0]:
        st.markdown(
            f"<div style='background:#0d0d15; border:1px solid #2a2a3a; "
            f"border-left:4px solid #ffaa33; border-radius:0 6px 6px 0; "
            f"padding:0.7rem 0.9rem;'>"
            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; "
            f"color:#ffaa33; letter-spacing:0.06em;'>FLAT CLUSTERS (NO HUB)</div>"
            f"<div style='font-size:1.4rem; color:#e8e8f0; font-weight:700;'>"
            f"{len(flat_clusters)}</div>"
            f"<div style='font-size:0.7rem; color:#9b9bb8;'>Clusters of 3+ pages with no "
            f"URL-hierarchy parent. Re-evaluate cluster definitions or pick a hub manually.</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if flat_clusters:
            with st.expander("Show list", expanded=False):
                for fc in flat_clusters[:30]:
                    st.markdown(f"- **{fc['topic']}** ({fc['size']} pages)")

    with issue_cols[1]:
        st.markdown(
            f"<div style='background:#0d0d15; border:1px solid #2a2a3a; "
            f"border-left:4px solid #ff4455; border-radius:0 6px 6px 0; "
            f"padding:0.7rem 0.9rem;'>"
            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; "
            f"color:#ff4455; letter-spacing:0.06em;'>WEAK HUBS (&lt;50% UP-LINKED)</div>"
            f"<div style='font-size:1.4rem; color:#e8e8f0; font-weight:700;'>"
            f"{len(weak_hubs)}</div>"
            f"<div style='font-size:0.7rem; color:#9b9bb8;'>Hubs where less than half the "
            f"spokes link up. Largest topical-authority gap.</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if weak_hubs:
            with st.expander("Show list", expanded=False):
                for wh in sorted(weak_hubs, key=lambda x: x["pct"])[:30]:
                    st.markdown(
                        f"- **{wh['topic']}** · `{shorten_url(wh['hub'])}` · "
                        f"{wh['covered']}/{wh['total']} ({wh['pct']}%)"
                    )

    with issue_cols[2]:
        st.markdown(
            f"<div style='background:#0d0d15; border:1px solid #2a2a3a; "
            f"border-left:4px solid #5bb4d4; border-radius:0 6px 6px 0; "
            f"padding:0.7rem 0.9rem;'>"
            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; "
            f"color:#5bb4d4; letter-spacing:0.06em;'>PAGES IN MULTIPLE CLUSTERS</div>"
            f"<div style='font-size:1.4rem; color:#e8e8f0; font-weight:700;'>"
            f"{len(cross_cluster)}</div>"
            f"<div style='font-size:0.7rem; color:#9b9bb8;'>Pages flagged as belonging "
            f"to 2+ clusters — potential topical confusion. Either narrow scope or split into separate pages.</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if cross_cluster:
            with st.expander("Show list", expanded=False):
                for u, topics in list(cross_cluster.items())[:30]:
                    st.markdown(
                        f"- `{shorten_url(u)}` · clusters: {', '.join(topics[:4])}"
                    )


# ── Main render ────────────────────────────────────────────────────────

def render():
    st.markdown("## 🗺 Topical Map")
    st.markdown(
        "<p style='color:#9b9bb8; font-size:0.9rem; margin-bottom:1rem;'>"
        "Visualises how the tool sees your site's topical architecture: clusters, "
        "hubs, spokes, owned keywords per URL, and the diff between recommended "
        "and currently-existing internal links.</p>",
        unsafe_allow_html=True,
    )

    if "topic_clusters" not in st.session_state:
        st.warning(
            "Topic clusters not yet computed. Go to **⚡ Run Pipeline → Step 5: Topic Clusters** first."
        )
        return

    topic_clusters_state = st.session_state["topic_clusters"] or {}
    clusters = topic_clusters_state.get("clusters", []) or []
    if not clusters:
        st.info("No clusters detected. Run the pipeline so the GSC data is grouped into clusters.")
        return

    audit_results = st.session_state.get("audit_results", []) or []
    sf_link_map = st.session_state.get("sf_link_map") or {}
    audit_lookup = {normalize_url(r.get("url", "")): r for r in audit_results}

    # ── Panel 1: overview ─────────────────────────────────────────
    _render_overview(clusters, audit_results, sf_link_map)

    st.markdown("---")

    # ── Panel 2: cluster picker + diagram ─────────────────────────
    st.markdown("### 🎯 Cluster focus")

    # Sort clusters by size desc for the picker
    sorted_clusters = sorted(
        clusters,
        key=lambda c: -len(c.get("pages", []) or []),
    )
    cluster_options = []
    for c in sorted_clusters:
        topic = c.get("topic", "(unnamed)")
        n = len(c.get("pages", []) or [])
        hub = detect_pillar(c, audit_lookup=audit_lookup)
        marker = "🟢" if hub else "⚠"
        cluster_options.append(f"{marker} {topic} · {n} pages")
    cluster_idx_by_label = {label: i for i, label in enumerate(cluster_options)}

    pick_col, diff_col, exp_col = st.columns([3, 2, 1])
    with pick_col:
        chosen_label = st.selectbox(
            "Cluster",
            cluster_options,
            key="_topical_map_cluster_pick",
            label_visibility="collapsed",
        )
    with diff_col:
        diff_mode_label = st.radio(
            "Show",
            ["All edges", "Missing only", "Existing only"],
            horizontal=True,
            key="_topical_map_diff_mode",
            label_visibility="collapsed",
        )
    diff_mode_map = {"All edges": "all", "Missing only": "missing_only",
                     "Existing only": "existing_only"}
    diff_mode = diff_mode_map.get(diff_mode_label, "all")

    chosen_idx = cluster_idx_by_label.get(chosen_label, 0)
    chosen_cluster = sorted_clusters[chosen_idx]

    with exp_col:
        md = _cluster_to_markdown(chosen_cluster, audit_lookup, sf_link_map,
                                  topic_clusters_state)
        st.download_button(
            "📄 Cluster",
            data=md,
            file_name=f"cluster_{chosen_cluster.get('topic', 'unknown')}.md",
            mime="text/markdown",
            key="_topical_map_dl_cluster",
            use_container_width=True,
        )

    # Legend
    st.markdown(
        "<div style='font-size:0.75rem; color:#9b9bb8; margin:0.4rem 0 0.6rem 0;'>"
        "Legend: <span style='color:#33dd88;'>━━ green</span> = link exists · "
        "<span style='color:#ff4455;'>┅┅ red dashed</span> = recommended, missing · "
        "<span style='color:#5533ff;'>┄┄ purple dashed box</span> = sibling sub-group"
        "</div>",
        unsafe_allow_html=True,
    )

    dot = _build_cluster_dot(chosen_cluster, audit_lookup, sf_link_map,
                             topic_clusters_state, diff_mode=diff_mode)
    try:
        st.graphviz_chart(dot, use_container_width=True)
    except Exception as e:
        st.error(f"Could not render diagram: {e}")
        with st.expander("Raw DOT source", expanded=False):
            st.code(dot, language="dot")

    with st.expander("📋 Detailed table — URLs · keywords · link counts", expanded=True):
        _render_cluster_side_table(chosen_cluster, audit_lookup, sf_link_map,
                                   topic_clusters_state)

    st.markdown("---")

    # ── Panel 3: issues ───────────────────────────────────────────
    _render_issues(clusters, audit_results, sf_link_map)

    st.markdown("---")

    # ── Full-site export ──────────────────────────────────────────
    st.markdown("### 📦 Export")
    full_md = _all_clusters_to_markdown(clusters, audit_lookup, sf_link_map,
                                        topic_clusters_state)
    st.download_button(
        "📄 Download full architecture report (markdown)",
        data=full_md,
        file_name="topical_architecture.md",
        mime="text/markdown",
        key="_topical_map_dl_full",
    )
