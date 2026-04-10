"""
Unified Task List — ONE view of ALL actions across the entire platform
Pulls from: Internal Linking, Missing Keywords, New Articles, Crawl Issues, Audit
Sorted by impact so you always work on the highest-value task first.
"""

import streamlit as st
import json


def _gather_all_tasks():
    """Collect tasks from all sources into one unified, prioritized list."""
    tasks = []

    # ── Source 1: Crawl issues (SF) ───────────────────────────────
    crawl_issues = st.session_state.get("sf_crawl_issues", {})
    for issue_type, items in crawl_issues.items():
        for item in items:
            # Map issue type to priority
            if issue_type == "broken_links":
                priority = "high"
                category = "Technical"
            elif issue_type == "orphan_pages":
                sev = item.get("severity", "HIGH")
                priority = "high" if sev in ("CRITICAL", "HIGH") else "medium" if sev == "MEDIUM" else "low"
                category = "Technical"
            elif issue_type in ("redirect_chains", "missing_meta"):
                priority = "medium"
                category = "Technical"
            elif issue_type in ("deep_pages", "thin_pages", "slow_pages"):
                priority = "medium"
                category = "Technical"
            else:
                priority = "low"
                category = "Technical"

            label = {
                "broken_links": "Fix broken link",
                "redirect_chains": "Fix redirect",
                "orphan_pages": "Fix orphan page",
                "deep_pages": "Reduce crawl depth",
                "thin_pages": "Add content to thin page",
                "missing_meta": "Add missing meta",
                "non_indexable": "Check indexability",
                "slow_pages": "Improve page speed",
            }.get(issue_type, issue_type)

            tasks.append({
                "url": item.get("url", ""),
                "priority": priority,
                "category": category,
                "type": label,
                "action": item.get("action", ""),
                "source": "Screaming Frog",
                "impressions": 0,
            })

    # ── Source 2: Audit issues (meta + content) ───────────────────
    for r in st.session_state.get("audit_results", []):
        url = r.get("url", "")
        impressions = r.get("impressions", 0)

        # Meta issues
        meta_score = r.get("meta_score")
        if meta_score is not None and meta_score < 60:
            tasks.append({
                "url": url,
                "priority": "high" if impressions > 500 else "medium",
                "category": "Meta",
                "type": "Fix meta tags",
                "action": f"Meta score {meta_score}/100 — title and/or description need optimization. Go to Content Generator to generate new meta.",
                "source": "Page Audit",
                "impressions": impressions,
            })

        # Content issues
        content_score = r.get("content_score")
        if content_score is not None and content_score < 50:
            tasks.append({
                "url": url,
                "priority": "high" if impressions > 500 else "medium",
                "category": "Content",
                "type": "Improve content",
                "action": f"Content score {content_score}/100 — page needs better content, keyword coverage, or structure. Go to Missing Keywords view.",
                "source": "Page Audit",
                "impressions": impressions,
            })

    # ── Source 3: Linking actions ─────────────────────────────────
    # Re-use the internal linking builder
    audit_results = st.session_state.get("audit_results", [])
    topic_clusters = st.session_state.get("topic_clusters", {})
    sf_link_map = st.session_state.get("sf_link_map")

    if audit_results and topic_clusters:
        from views.internal_linking import _build_action_list as build_link_actions
        link_actions = build_link_actions(audit_results, topic_clusters, sf_link_map)
        for a in link_actions:
            tasks.append({
                "url": a["page_url"],
                "priority": a["priority"],
                "category": "Linking",
                "type": a.get("type", "add_link").replace("_", " ").title(),
                "action": a["instruction"],
                "source": "Internal Linking",
                "impressions": a.get("impressions", 0),
            })

    # ── Source 4: Missing keywords ────────────────────────────────
    for r in st.session_state.get("audit_results", []):
        content_audit = r.get("content_audit") or {}
        kw_cov = content_audit.get("keyword_coverage") or {}
        missing = kw_cov.get("missing", [])
        coverage_pct = kw_cov.get("coverage_pct", 100)
        impressions = r.get("impressions", 0)

        if missing and coverage_pct < 70:
            kw_list = ", ".join(missing[:5])
            tasks.append({
                "url": r.get("url", ""),
                "priority": "high" if impressions > 500 and coverage_pct < 50 else "medium",
                "category": "Keywords",
                "type": "Add missing keywords",
                "action": f"Coverage {coverage_pct:.0f}% — missing: {kw_list}. Go to Missing Keywords view for AI-generated text.",
                "source": "Page Audit",
                "impressions": impressions,
            })

    # ── Source 5: New articles (check existing pages first) ─────────
    roadmap = st.session_state.get("content_roadmap", {})
    audit_results = st.session_state.get("audit_results", [])
    existing_url_paths = set()
    for r in audit_results:
        u = r.get("url", "")
        if u:
            from urllib.parse import urlparse
            existing_url_paths.add(urlparse(u.lower().rstrip("/")).path.rstrip("/"))
    for article in roadmap.get("articles_needed", []):
        title = article.get("suggested_title", "")
        # Check if a page already covers this topic (by keyword in URL)
        topic_slug = title.lower().replace(" ", "-").replace(":", "").replace("?", "")
        already_covered = any(topic_slug[:20] in ep for ep in existing_url_paths if len(topic_slug) > 5)
        prefix = "[MAY EXIST] " if already_covered else ""
        tasks.append({
            "url": article.get("supporting_page", ""),
            "priority": article.get("priority", "medium"),
            "category": "New Content",
            "type": "Write new article",
            "action": f"{prefix}Write: \"{title}\" ({article.get('content_type', 'article')}). Go to New Articles view for AI generation.",
            "source": "Content Roadmap",
            "impressions": article.get("estimated_impressions", 0),
        })

    # ── Deduplicate by (url + type) keeping highest priority ─────
    seen = {}
    pri_rank = {"high": 0, "medium": 1, "low": 2}
    for t in tasks:
        key = (t["url"], t["type"])
        if key not in seen or pri_rank.get(t["priority"], 1) < pri_rank.get(seen[key]["priority"], 1):
            seen[key] = t
    tasks = list(seen.values())

    # Sort: high first, then by impressions
    tasks.sort(key=lambda t: (pri_rank.get(t["priority"], 1), -t["impressions"]))
    return tasks


def render():
    st.markdown("## All Tasks — Unified Priority List")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1.5rem;'>"
        "Every task from every analysis in one place, sorted by impact. Work from the top down.</p>",
        unsafe_allow_html=True,
    )

    # Cache tasks
    audit_len = len(st.session_state.get("audit_results", []))
    cache_key = f"_unified_tasks_{audit_len}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = _gather_all_tasks()
    tasks = st.session_state[cache_key]

    if not tasks:
        st.info("Run the pipeline steps first (Audit, Topic Clusters, etc.) to generate tasks.")
        return

    # ── Summary ───────────────────────────────────────────────────
    high = sum(1 for t in tasks if t["priority"] == "high")
    categories = {}
    for t in tasks:
        categories[t["category"]] = categories.get(t["category"], 0) + 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total tasks", len(tasks))
    c2.metric("High priority", high)
    c3.metric("Categories", len(categories))
    c4.metric("Pages affected", len(set(t["url"] for t in tasks)))

    # Category breakdown
    cat_html = " ".join([
        f"<span style='background:#12121f; border:1px solid #5533ff; border-radius:4px; padding:3px 10px; "
        f"font-family:\"IBM Plex Mono\",monospace; font-size:0.72rem; color:#c8b4ff; margin:2px; display:inline-block;'>"
        f"{cat}: {count}</span>"
        for cat, count in sorted(categories.items(), key=lambda x: -x[1])
    ])
    st.markdown(cat_html, unsafe_allow_html=True)

    st.markdown("---")

    # ── Filters ───────────────────────────────────────────────────
    f1, f2 = st.columns(2)
    with f1:
        pri_filter = st.multiselect(
            "Priority", ["high", "medium", "low"],
            default=["high", "medium"],
            key="unified_pri",
        )
    with f2:
        cat_filter = st.multiselect(
            "Category", list(categories.keys()),
            default=list(categories.keys()),
            key="unified_cat",
        )

    filtered = [t for t in tasks if t["priority"] in pri_filter and t["category"] in cat_filter]
    st.markdown(f"**Showing {len(filtered)} of {len(tasks)} tasks**")

    # Pagination
    ITEMS_PER_PAGE = 25
    total_items = len(filtered)
    max_pg = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    pg = st.number_input("Page", min_value=1, max_value=max_pg, value=1, key="tasks_page")
    start_i = (pg - 1) * ITEMS_PER_PAGE
    visible = filtered[start_i:start_i + ITEMS_PER_PAGE]
    st.markdown(f"**Showing {start_i+1}-{min(start_i+ITEMS_PER_PAGE, total_items)} of {total_items} tasks**")

    # ── Task cards ────────────────────────────────────────────────
    for t in visible:
        pri = t["priority"]
        pri_color = {"high": "#ff4455", "medium": "#ffaa33", "low": "#33dd88"}[pri]
        cat_color = {
            "Technical": "#ff4455",
            "Meta": "#c8b4ff",
            "Content": "#5533ff",
            "Linking": "#ffaa33",
            "Keywords": "#33dd88",
            "New Content": "#c8b4ff",
        }.get(t["category"], "#6b6b8a")

        st.markdown(
            f"<div style='background:#12121f; border-left:4px solid {pri_color}; "
            f"border-radius:6px; padding:0.8rem 1rem; margin-bottom:0.5rem;'>"
            # Header
            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;'>"
            f"<div>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:{pri_color}; "
            f"text-transform:uppercase; letter-spacing:0.08em;'>{pri.upper()}</span>"
            f"<span style='background:{cat_color}22; border:1px solid {cat_color}; border-radius:3px; "
            f"padding:1px 6px; font-size:0.6rem; color:{cat_color}; margin-left:0.5rem;'>{t['category']}</span>"
            f"<span style='font-size:0.65rem; color:#6b6b8a; margin-left:0.5rem;'>{t['type']}</span>"
            f"</div>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#6b6b8a;'>"
            f"{t['source']}"
            f"{'  ·  ' + str(t['impressions']) + ' impr' if t['impressions'] else ''}"
            f"</span>"
            f"</div>"
            # URL
            f"<div style='font-size:0.88rem; color:#e8e8f0; margin-bottom:0.3rem;'>{t['url']}</div>"
            # Action
            f"<div style='font-size:0.8rem; color:#9b9bb8;'>{t['action']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    if total_items > ITEMS_PER_PAGE:
        st.markdown(f"<div style='color:#6b6b8a;'>Page {pg} of {max_pg}</div>", unsafe_allow_html=True)

    # ── Download ──────────────────────────────────────────────────
    st.markdown("---")
    export = [{
        "url": t["url"],
        "priority": t["priority"],
        "category": t["category"],
        "type": t["type"],
        "action": t["action"],
        "source": t["source"],
        "impressions": t["impressions"],
    } for t in tasks]
    st.download_button(
        "Download all tasks (JSON)",
        json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8"),
        "all_seo_tasks.json",
        "application/json",
    )
