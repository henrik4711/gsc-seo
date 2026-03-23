"""
Internal Linking — action-first view
Every item = one clear task: what to change, where, and AI to write it for you.
Generates linking recommendations from BOTH audit data AND topic cluster overlap.
"""

import streamlit as st
import json
from urllib.parse import urlparse
from config import get_anthropic_key, has_anthropic_key
from utils.ui_helpers import normalize_url as _nu


def _build_action_list(audit_results, topic_clusters, sf_link_map=None):
    """
    Build linking actions from multiple sources:
    1. Audit data (link_fix_suggestions, anchor_mismatches, missing_crosslinks)
    2. Topic cluster overlap — find pages sharing topics but not linking to each other
    3. Screaming Frog link map (if available) — complete internal link data
    """
    actions = []
    action_id = 0

    # Index: which URLs each page already links to (from audit scrape data)
    known_links_by_page = {}
    page_impressions = {}
    page_keywords = {}
    page_types = {}
    audited_urls = set()

    for r in audit_results:
        url = r.get("url", "")
        audited_urls.add(url)
        page_impressions[url] = r.get("impressions", 0)
        page_keywords[url] = r.get("target_keywords", [])
        page_types[url] = r.get("page_type", "unknown")

        # Build set of URLs this page already links to
        internal_links = r.get("internal_links", r.get("content_audit", {}).get("linking", {}).get("total_internal", 0))
        linked_urls = set()
        if isinstance(internal_links, list):
            for l in internal_links:
                u = l.get("url", "")
                if u.startswith("/"):
                    domain = urlparse(url).netloc
                    u = f"https://{domain}{u}"
                linked_urls.add(_nu(u))
        # Enrich with SF link map if available
        if sf_link_map:
            sf_links = sf_link_map.get("links_from", {}).get(url, [])
            for sl in sf_links:
                t = sl.get("target", "")
                linked_urls.add(_nu(t))

        known_links_by_page[url] = linked_urls

        # Source 1: Existing audit link_fix_suggestions
        content_audit = r.get("content_audit") or {}
        linking = content_audit.get("linking") or {}

        for fix in (linking.get("link_fix_suggestions") or []):
            target = fix.get("target_url", "")
            anchor = fix.get("suggested_anchor", "")
            placement = fix.get("placement", "")
            placement_detail = fix.get("placement_detail", "")
            priority = fix.get("priority", "medium")
            reason = fix.get("reason", "")
            shared = fix.get("shared_topics", [])

            where = placement_detail or placement
            if placement == "bottom_text":
                where = "the bottom text section"
            elif placement == "intro_text":
                where = "the intro paragraph"
            elif placement == "h2_section":
                where = f"the '{placement_detail}' section" if placement_detail else "an H2 section"

            actions.append({
                "id": action_id,
                "type": "add_link",
                "source": "audit",
                "priority": priority,
                "page_url": url,
                "impressions": page_impressions.get(url, 0),
                "action_title": f"Add link to {target}",
                "instruction": f"Open **{url}** in your CMS. Go to **{where}**. Add a link to `{target}` with anchor text **\"{anchor}\"**.",
                "why": reason or f"These pages share topics ({', '.join(shared[:3])}), but there is no link between them.",
                "target_url": target,
                "anchor_text": anchor,
                "placement": where,
                "keywords": page_keywords.get(url, []),
            })
            action_id += 1

        # Source 1b: Anchor mismatches
        for am in ((linking.get("semantic_validation") or {}).get("anchor_mismatches") or []):
            actions.append({
                "id": action_id,
                "type": "fix_anchor",
                "source": "audit",
                "priority": "medium",
                "page_url": url,
                "impressions": page_impressions.get(url, 0),
                "action_title": f"Fix anchor text for link to {am.get('url', '')}",
                "instruction": (
                    f"Open **{url}** in your CMS. Find the link to `{am.get('url', '')}`. "
                    f"Change the anchor text from **\"{am.get('current_anchor', '')}\"** to **\"{am.get('suggested_anchor', '')}\"**."
                ),
                "why": am.get("reason", "The current anchor text doesn't describe the target page well."),
                "target_url": am.get("url", ""),
                "anchor_text": am.get("suggested_anchor", ""),
                "old_anchor": am.get("current_anchor", ""),
                "placement": "",
                "keywords": page_keywords.get(url, []),
            })
            action_id += 1

    # ── Source 2: Topic cluster overlap analysis ──────────────────
    # Find pages that share topics but DON'T link to each other
    # This works for ALL pages, not just deep-scraped categories
    if topic_clusters:
        page_topics = topic_clusters.get("page_topics", {})
        overlap = topic_clusters.get("overlap_matrix", [])

        # Filter out "junk" topics that appear on too many pages (brand topics)
        # These create false overlap between unrelated pages
        topic_page_count = {}
        for url_t, topics_list in page_topics.items():
            for t in topics_list:
                tn = t.get("topic", "")
                topic_page_count[tn] = topic_page_count.get(tn, 0) + 1
        total_topic_pages = len(page_topics)
        junk_topics = {tn for tn, cnt in topic_page_count.items() if cnt >= total_topic_pages * 0.3}

        # Also build overlap from page_topics if overlap_matrix is empty
        if not overlap:
            urls_with_topics = list(page_topics.keys())
            for i, url_a in enumerate(urls_with_topics):
                topics_a = set(t.get("topic", "") for t in page_topics[url_a]) - junk_topics
                for url_b in urls_with_topics[i+1:]:
                    topics_b = set(t.get("topic", "") for t in page_topics[url_b]) - junk_topics
                    shared = topics_a & topics_b
                    if shared:
                        overlap.append({
                            "page_1": url_a,
                            "page_2": url_b,
                            "shared_topics": len(shared),
                            "topic_names": list(shared),
                        })

        # Filter overlap_matrix too — remove junk topic overlap
        if junk_topics:
            filtered_overlap = []
            for ov in overlap:
                clean_topics = [t for t in ov.get("topic_names", []) if t not in junk_topics]
                if clean_topics:
                    filtered_overlap.append({
                        **ov,
                        "shared_topics": len(clean_topics),
                        "topic_names": clean_topics,
                    })
            overlap = filtered_overlap

        # Deduplicate: track which (source, target) pairs we already have
        existing_pairs = set()
        for a in actions:
            existing_pairs.add((_nu(a["page_url"]), _nu(a.get("target_url", ""))))

        for ov in overlap:
            p1 = ov.get("page_1", "")
            p2 = ov.get("page_2", "")
            shared_count = ov.get("shared_topics", 0)
            topic_names = ov.get("topic_names", [])

            if shared_count < 1:
                continue

            # Only include if at least one page was audited
            if p1 not in audited_urls and p2 not in audited_urls:
                continue

            # Check both directions — but only between RELATED pages
            for source_url, target_url in [(p1, p2), (p2, p1)]:
                if source_url not in audited_urls:
                    continue

                pair_key = (_nu(source_url), _nu(target_url))
                if pair_key in existing_pairs:
                    continue

                # Check if we KNOW the page already links there
                known = known_links_by_page.get(source_url, set())
                if _nu(target_url) in known:
                    continue

                # Filter: only suggest links between related pages
                # Related = same URL hierarchy, OR share topic clusters
                src_parts = urlparse(source_url).path.lower().strip("/").split("/")
                tgt_parts = urlparse(target_url).path.lower().strip("/").split("/")
                is_sibling = (len(src_parts) >= 2 and len(tgt_parts) >= 2
                              and src_parts[0] == tgt_parts[0])
                is_parent_child = (
                    _nu(target_url).startswith(_nu(source_url) + "/") or
                    _nu(source_url).startswith(_nu(target_url) + "/")
                )
                shares_topic = shared_count >= 2  # They share 2+ topic clusters = related
                if not is_sibling and not is_parent_child and not shares_topic:
                    continue

                # Determine priority from shared topic count + impressions
                impr = page_impressions.get(source_url, 0)
                if shared_count >= 3 or impr > 1000:
                    priority = "high"
                elif shared_count >= 2 or impr > 500:
                    priority = "medium"
                else:
                    priority = "low"

                # Generate NATURAL anchor text from the TARGET page's URL slug
                target_slug = tgt_parts[-1] if tgt_parts else ""
                suggested_anchor = target_slug.replace("-", " ").replace("_", " ")
                if not suggested_anchor:
                    suggested_anchor = "related page"

                actions.append({
                    "id": action_id,
                    "type": "add_link",
                    "source": "cluster_overlap",
                    "priority": priority,
                    "page_url": source_url,
                    "impressions": impr,
                    "action_title": f"Add link to {target_url}",
                    "instruction": (
                        f"Open **{source_url}** in your CMS. "
                        f"Add a link to `{target_url}` with anchor text **\"{suggested_anchor}\"**. "
                        f"Place it in the intro, bottom text, or a relevant section."
                    ),
                    "why": (
                        f"These pages share {shared_count} topic(s): {', '.join(topic_names[:4])}. "
                        f"Linking them helps Google understand your topic authority and helps users navigate."
                    ),
                    "target_url": target_url,
                    "anchor_text": suggested_anchor,
                    "placement": "intro, bottom text, or a relevant H2 section",
                    "keywords": page_keywords.get(source_url, []),
                })
                existing_pairs.add(pair_key)
                action_id += 1

    # ── Source 3: Pages with very few internal links ──────────────
    for r in audit_results:
        url = r.get("url", "")
        internal_links = r.get("internal_links", 0)
        link_count = internal_links if isinstance(internal_links, int) else len(internal_links)
        content_audit = r.get("content_audit") or {}
        linking = content_audit.get("linking") or {}
        total = linking.get("total_internal", link_count)

        if total < 3 and r.get("impressions", 0) > 100:
            # Check we haven't already flagged this page
            already_has_actions = any(a["page_url"] == url for a in actions)
            if not already_has_actions:
                actions.append({
                    "id": action_id,
                    "type": "low_links",
                    "source": "link_count",
                    "priority": "medium",
                    "page_url": url,
                    "impressions": r.get("impressions", 0),
                    "action_title": f"Page has only {total} internal links — add more",
                    "instruction": (
                        f"Open **{url}** in your CMS. This page only has **{total} internal links**. "
                        f"Add links to related pages to help Google discover and understand your content structure. "
                        f"Aim for at least 5-10 internal links per page."
                    ),
                    "why": "Pages with very few internal links are harder for Google to crawl and rank. They also provide a poor user experience.",
                    "target_url": "",
                    "anchor_text": "",
                    "placement": "throughout the page",
                    "keywords": page_keywords.get(url, []),
                })
                action_id += 1

    # Sort: high first, then by impressions
    pri_order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(key=lambda a: (pri_order.get(a["priority"], 1), -a["impressions"]))
    return actions


def render():
    st.markdown("## Internal Linking — Action List")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1.5rem;'>"
        "Every card below = one change to make. Click <strong>Generate text</strong> and AI writes the exact paragraph to paste into your CMS.</p>",
        unsafe_allow_html=True,
    )

    if not has_anthropic_key():
        st.warning("Go to **1. Setup & Connect** and add Anthropic API key.")
        return

    if "audit_results" not in st.session_state:
        st.warning("Go to **6. Page Auditor** and run an audit first.")
        return

    audit_results = st.session_state["audit_results"]
    topic_clusters = st.session_state.get("topic_clusters", {})
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")

    sf_link_map = st.session_state.get("sf_link_map")

    # Cache action list — only rebuild when data changes
    cache_key = f"_link_actions_v3_{len(audit_results)}_{bool(sf_link_map)}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = _build_action_list(audit_results, topic_clusters, sf_link_map)
    actions = st.session_state[cache_key]

    if not actions:
        st.success("No linking issues found. Internal linking looks good!")
        st.session_state["linking_fixes"] = True
        return

    # ── Summary ───────────────────────────────────────────────────
    high = sum(1 for a in actions if a["priority"] == "high")
    med = sum(1 for a in actions if a["priority"] == "medium")
    from_audit = sum(1 for a in actions if a["source"] == "audit")
    from_clusters = sum(1 for a in actions if a["source"] == "cluster_overlap")
    from_count = sum(1 for a in actions if a["source"] == "link_count")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total actions", len(actions))
    c2.metric("High priority", high)
    c3.metric("From topic analysis", from_clusters)
    c4.metric("From audit", from_audit + from_count)

    st.markdown("---")

    # ── Filter ────────────────────────────────────────────────────
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        pri_filter = st.multiselect(
            "Filter by priority",
            ["high", "medium", "low"],
            default=["high", "medium"],
        )
    with filter_col2:
        source_filter = st.multiselect(
            "Filter by source",
            ["audit", "cluster_overlap", "link_count"],
            default=["audit", "cluster_overlap", "link_count"],
            format_func=lambda x: {"audit": "Page audit", "cluster_overlap": "Topic cluster overlap", "link_count": "Low link count"}[x],
        )

    filtered = [a for a in actions if a["priority"] in pri_filter and a["source"] in source_filter]

    # Pagination
    ITEMS_PER_PAGE = 20
    total_items = len(filtered)
    max_pg = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    pg = st.number_input("Page", min_value=1, max_value=max_pg, value=1, key="link_page")
    start_i = (pg - 1) * ITEMS_PER_PAGE
    visible = filtered[start_i:start_i + ITEMS_PER_PAGE]
    st.markdown(f"**Showing {start_i+1}-{min(start_i+ITEMS_PER_PAGE, total_items)} of {total_items} actions**")

    # ── Action cards ──────────────────────────────────────────────
    for a in visible:
        pri = a["priority"]
        pri_color = {"high": "#ff4455", "medium": "#ffaa33", "low": "#33dd88"}[pri]
        border_color = {"high": "#ff4455", "medium": "#2a2a40", "low": "#1e1e2e"}[pri]
        type_label = {"add_link": "ADD LINK", "fix_anchor": "FIX ANCHOR", "low_links": "ADD MORE LINKS"}[a["type"]]
        source_label = {"audit": "PAGE AUDIT", "cluster_overlap": "TOPIC OVERLAP", "link_count": "LINK COUNT"}[a["source"]]

        st.markdown(
            f"<div style='background:#12121f; border:1px solid {border_color}; border-left:4px solid {pri_color}; "
            f"border-radius:6px; padding:1rem; margin-bottom:0.8rem;'>"
            # Header row
            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.6rem;'>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:{pri_color}; "
            f"text-transform:uppercase; letter-spacing:0.1em;'>{type_label} · {pri.upper()}</span>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#6b6b8a;'>"
            f"{source_label} · {a['impressions']:,} impressions</span>"
            f"</div>"
            # Action title
            f"<div style='font-size:1rem; color:#e8e8f0; font-weight:600; margin-bottom:0.6rem;'>"
            f"{a['action_title']}</div>"
            # Instruction
            f"<div style='font-size:0.85rem; color:#c8b4ff; background:#0d0d15; padding:0.6rem; "
            f"border-radius:4px; margin-bottom:0.5rem; line-height:1.5;'>"
            f"{a['instruction']}</div>"
            # Why
            f"<div style='font-size:0.75rem; color:#6b6b8a;'>Why: {a['why']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # ── AI Generate button ────────────────────────────────
        if a["type"] in ("add_link",) and a.get("target_url"):
            result_key = f"link_ai_{a['id']}"
            if st.button(f"Generate link paragraph", key=f"btn_link_{a['id']}", type="primary"):
                with st.spinner("AI writing paragraph with link..."):
                    try:
                        from utils.ai_generator import get_client, generate_link_text
                        client = get_client(get_anthropic_key())
                        result = generate_link_text(
                            client, a["page_url"], a["target_url"],
                            a["anchor_text"], a["placement"],
                            a["keywords"], site_context, language,
                        )
                        st.session_state[result_key] = result
                    except Exception as e:
                        st.error(f"Error: {e}")

            if result_key in st.session_state:
                res = st.session_state[result_key]
                st.markdown(
                    f"<div style='background:#0d1a0d; border-left:3px solid #33dd88; padding:0.8rem; "
                    f"border-radius:0 6px 6px 0; margin-bottom:0.5rem;'>"
                    f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#33dd88; "
                    f"margin-bottom:0.4rem;'>COPY THIS INTO YOUR CMS</div>"
                    f"<div style='color:#e8e8f0; line-height:1.6;'>{res.get('paragraph', '')}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                st.code(res.get("html", ""), language="html")

    st.markdown("---")
    st.session_state["linking_fixes"] = True

    # ── Download ──────────────────────────────────────────────────
    export_data = [{
        "action": a["instruction"],
        "page": a["page_url"],
        "target": a.get("target_url", ""),
        "anchor": a.get("anchor_text", ""),
        "priority": a["priority"],
        "type": a["type"],
        "source": a["source"],
    } for a in actions]
    st.download_button(
        "Download action list (JSON)",
        json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8"),
        "internal_linking_actions.json",
        "application/json",
    )
