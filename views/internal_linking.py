"""
Internal Linking — action-first view
Every item = one clear task: what to change, where, and AI to write it for you
"""

import streamlit as st
import json
from config import get_anthropic_key, has_anthropic_key


def _build_action_list(audit_results, topic_clusters):
    """Flatten all linking issues into a single prioritized action list."""
    actions = []
    action_id = 0

    for r in audit_results:
        url = r.get("url", "")
        impressions = r.get("impressions", 0)
        lost_clicks = r.get("lost_clicks_estimate", 0)
        content_audit = r.get("content_audit") or {}
        linking = content_audit.get("linking") or {}
        keywords = r.get("target_keywords", [])

        # 1. Link fix suggestions → "ADD LINK" actions
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
                "priority": priority,
                "page_url": url,
                "impressions": impressions,
                "action_title": f"Add link to {target}",
                "instruction": f"Open **{url}** in your CMS. Go to **{where}**. Add a link to `{target}` with anchor text **\"{anchor}\"**.",
                "why": reason or f"These pages share topics ({', '.join(shared[:3])}), but there is no link between them.",
                "target_url": target,
                "anchor_text": anchor,
                "placement": where,
                "keywords": keywords,
            })
            action_id += 1

        # 2. Anchor mismatches → "FIX ANCHOR" actions
        for am in ((linking.get("semantic_validation") or {}).get("anchor_mismatches") or []):
            actions.append({
                "id": action_id,
                "type": "fix_anchor",
                "priority": "medium",
                "page_url": url,
                "impressions": impressions,
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
                "keywords": keywords,
            })
            action_id += 1

        # 3. Missing crosslinks → "ADD CROSSLINK" actions
        for cl in (linking.get("missing_crosslinks") or []):
            shared = cl.get("shared_topics", [])
            actions.append({
                "id": action_id,
                "type": "add_crosslink",
                "priority": "low" if cl.get("shared_count", 0) < 3 else "medium",
                "page_url": url,
                "impressions": impressions,
                "action_title": f"Add crosslink to {cl.get('url', '')}",
                "instruction": (
                    f"Open **{url}** in your CMS. Add a link to `{cl.get('url', '')}` "
                    f"somewhere in the page content. Suggested anchor: one of the shared topics below."
                ),
                "why": f"These pages share {cl.get('shared_count', 0)} topics ({', '.join(shared[:4])}) but are not linked.",
                "target_url": cl.get("url", ""),
                "anchor_text": shared[0] if shared else "",
                "placement": "bottom text or a related section",
                "keywords": keywords,
            })
            action_id += 1

    # Sort: high first, then by impressions descending
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

    actions = _build_action_list(audit_results, topic_clusters)

    if not actions:
        st.success("No linking issues found. Internal linking looks good!")
        st.session_state["linking_fixes"] = True
        return

    # ── Summary ───────────────────────────────────────────────────
    high = sum(1 for a in actions if a["priority"] == "high")
    med = sum(1 for a in actions if a["priority"] == "medium")
    add_links = sum(1 for a in actions if a["type"] in ("add_link", "add_crosslink"))
    fix_anchors = sum(1 for a in actions if a["type"] == "fix_anchor")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total actions", len(actions))
    c2.metric("High priority", high)
    c3.metric("Links to add", add_links)
    c4.metric("Anchors to fix", fix_anchors)

    st.markdown("---")

    # ── Filter ────────────────────────────────────────────────────
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        type_filter = st.multiselect(
            "Filter by type",
            ["add_link", "fix_anchor", "add_crosslink"],
            default=["add_link", "fix_anchor", "add_crosslink"],
            format_func=lambda x: {"add_link": "Add link", "fix_anchor": "Fix anchor", "add_crosslink": "Add crosslink"}[x],
        )
    with filter_col2:
        pri_filter = st.multiselect(
            "Filter by priority",
            ["high", "medium", "low"],
            default=["high", "medium"],
        )

    filtered = [a for a in actions if a["type"] in type_filter and a["priority"] in pri_filter]

    st.markdown(f"**Showing {len(filtered)} of {len(actions)} actions**")

    # ── Action cards ──────────────────────────────────────────────
    for a in filtered:
        pri = a["priority"]
        pri_color = {"high": "#ff4455", "medium": "#ffaa33", "low": "#33dd88"}[pri]
        type_label = {"add_link": "ADD LINK", "fix_anchor": "FIX ANCHOR", "add_crosslink": "ADD CROSSLINK"}[a["type"]]
        type_icon = {"add_link": "+", "fix_anchor": "~", "add_crosslink": "+"}[a["type"]]
        border_color = {"high": "#ff4455", "medium": "#2a2a40", "low": "#1e1e2e"}[pri]

        st.markdown(
            f"<div style='background:#12121f; border:1px solid {border_color}; border-left:4px solid {pri_color}; "
            f"border-radius:6px; padding:1rem; margin-bottom:0.8rem;'>"
            # Header row
            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.6rem;'>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:{pri_color}; "
            f"text-transform:uppercase; letter-spacing:0.1em;'>{type_label} · {pri.upper()}</span>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#6b6b8a;'>"
            f"{a['impressions']:,} impressions</span>"
            f"</div>"
            # Action title
            f"<div style='font-size:1rem; color:#e8e8f0; font-weight:600; margin-bottom:0.6rem;'>"
            f"{type_icon} {a['action_title']}</div>"
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
        if a["type"] in ("add_link", "add_crosslink"):
            result_key = f"link_ai_{a['id']}"
            if st.button(f"Generate link paragraph for AI", key=f"btn_link_{a['id']}", type="primary"):
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
        "target": a["target_url"],
        "anchor": a["anchor_text"],
        "priority": a["priority"],
        "type": a["type"],
    } for a in actions]
    st.download_button(
        "Download action list (JSON)",
        json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8"),
        "internal_linking_actions.json",
        "application/json",
    )
