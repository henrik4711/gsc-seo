"""
Site Map Export — Complete overview of site structure, clusters, links, and actions.
Excel export + AI validation.
"""

import streamlit as st
import pandas as pd
import json
import io
from urllib.parse import urlparse
from config import get_anthropic_key, has_anthropic_key
from utils.ui_helpers import stable_hash


def _check_prerequisites():
    """Check which analyses have been run."""
    checks = {
        "gsc_data": ("GSC Data", "1. Setup"),
        "topic_clusters": ("Topic Clusters", "5. Topic Clusters"),
        "audit_results": ("Page Audit", "6. Page Auditor"),
    }
    optional = {
        "page_authority": ("Ahrefs Backlinks", "2. Upload Data"),
        "sf_pages": ("Screaming Frog", "2. Upload Data"),
        "ctr_gaps": ("CTR Analysis", "3. CTR Analysis"),
        "cannibalization": ("Cannibalization", "4. Cannibalization"),
        "content_roadmap": ("Content Roadmap", "5. Topic Clusters"),
    }
    missing = []
    for key, (name, step) in checks.items():
        if key not in st.session_state:
            missing.append(f"**{name}** — run {step}")
    return missing, checks, optional


def _build_site_structure(audit_results, gsc_data, topic_clusters, page_authority=None):
    """Build Sheet 1: Site Structure — every page with all metrics."""
    rows = []
    tc = topic_clusters or {}
    page_topics = tc.get("page_topics", {})
    audit_by_url = {r["url"]: r for r in audit_results}

    # Get all unique URLs
    all_urls = set(r["url"] for r in audit_results)
    if gsc_data is not None and hasattr(gsc_data, "page"):
        all_urls.update(gsc_data["page"].unique().tolist())

    for url in sorted(all_urls):
        parsed = urlparse(url)
        path = parsed.path.rstrip("/") or "/"
        depth = len([p for p in path.split("/") if p])
        parent_parts = path.strip("/").split("/")[:-1]
        parent_url = f"https://{parsed.netloc}/{'/'.join(parent_parts)}" if parent_parts else ""

        # Audit data
        audit = audit_by_url.get(url, {})

        # Cluster data
        topics = page_topics.get(url, [])
        cluster_names = [t.get("topic", "") for t in topics[:3]]

        # GSC data
        if gsc_data is not None and hasattr(gsc_data, "page"):
            page_gsc = gsc_data[gsc_data["page"] == url]
            impressions = int(page_gsc["impressions"].sum()) if not page_gsc.empty else 0
            clicks = int(page_gsc["clicks"].sum()) if not page_gsc.empty else 0
            avg_pos = round(page_gsc["position"].mean(), 1) if not page_gsc.empty else None
        else:
            impressions = audit.get("impressions", 0)
            clicks = audit.get("clicks", 0)
            avg_pos = audit.get("position")

        # Internal links
        il = audit.get("internal_links", [])
        links_out = len(il) if isinstance(il, list) else (il if isinstance(il, int) else 0)

        # Links in (count how many other pages link to this one)
        links_in = 0
        for other_r in audit_results:
            other_links = other_r.get("internal_links", [])
            if isinstance(other_links, list):
                for l in other_links:
                    if l.get("url", "").rstrip("/").lower() == url.rstrip("/").lower():
                        links_in += 1
                        break

        # AI quality
        qkey = f"_quality_{stable_hash(url)}"
        ai_q = st.session_state.get(qkey, {})
        ai_verdict = ai_q.get("verdict", "") if ai_q else ""
        ai_score = ai_q.get("score", "") if ai_q else ""

        rows.append({
            "URL": url,
            "Path": path,
            "Depth": depth,
            "Page Type": audit.get("page_type", "unknown"),
            "Parent URL": parent_url,
            "Cluster(s)": " | ".join(cluster_names) if cluster_names else "",
            "Primary Keyword": audit.get("target_keywords", [""])[0] if audit.get("target_keywords") else "",
            "Impressions": impressions,
            "Clicks": clicks,
            "Avg Position": avg_pos,
            "Backlinks (domains)": audit.get("referring_domains", 0),
            "Meta Score": audit.get("meta_score", ""),
            "Content Score": audit.get("content_score", ""),
            "AI Quality": f"{ai_score}/10 {ai_verdict}" if ai_verdict else "",
            "Word Count": audit.get("word_count", 0),
            "Links Out": links_out,
            "Links In": links_in,
            "Title": (audit.get("title") or "")[:80],
            "H1": (audit.get("h1") or "")[:80],
        })

    return pd.DataFrame(rows).sort_values(["Depth", "URL"])


def _build_cluster_detail(topic_clusters, audit_results, gsc_data):
    """Build Sheet 2: Cluster Detail — every keyword-cluster-page combo."""
    rows = []
    tc = topic_clusters or {}
    audit_by_url = {r["url"]: r for r in audit_results}

    for cluster in tc.get("clusters", []):
        topic = cluster.get("topic", "")
        queries = cluster.get("queries", [])
        pages = cluster.get("pages", [])

        # Determine hub (shallowest URL)
        hub_url = ""
        hub_depth = 999
        for p in pages:
            depth = len(urlparse(p["page"]).path.strip("/").split("/"))
            if depth < hub_depth:
                hub_depth = depth
                hub_url = p["page"]

        for p in pages:
            purl = p["page"]
            role = "HUB" if purl == hub_url else "SPOKE"
            audit = audit_by_url.get(purl, {})

            # Keywords this page covers
            kw_cov = (audit.get("content_audit") or {}).get("keyword_coverage") or {}
            covered = kw_cov.get("covered", 0)
            missing = kw_cov.get("missing", [])

            # Check hub-spoke links
            il = audit.get("internal_links", [])
            links_to_hub = False
            links_from_hub = False
            if isinstance(il, list):
                for l in il:
                    if l.get("url", "").rstrip("/").lower() == hub_url.rstrip("/").lower():
                        links_to_hub = True

            hub_audit = audit_by_url.get(hub_url, {})
            hub_links = hub_audit.get("internal_links", [])
            if isinstance(hub_links, list):
                for l in hub_links:
                    if l.get("url", "").rstrip("/").lower() == purl.rstrip("/").lower():
                        links_from_hub = True

            rows.append({
                "Cluster": topic,
                "Cluster Queries": cluster.get("query_count", 0),
                "Cluster Impressions": cluster.get("total_impressions", 0),
                "URL": purl,
                "Role": role,
                "Page Type": audit.get("page_type", "?"),
                "Page Impressions": p.get("total_impressions", 0),
                "Page Clicks": p.get("total_clicks", 0),
                "Keywords Covered": covered,
                "Keywords Missing": ", ".join(missing[:5]),
                "Links to Hub": "YES" if links_to_hub or role == "HUB" else "NO",
                "Links from Hub": "YES" if links_from_hub or role == "HUB" else "NO",
            })

    return pd.DataFrame(rows).sort_values(["Cluster", "Role", "URL"])


def _build_link_matrix(audit_results, topic_clusters):
    """Build Sheet 3: Link Matrix — all internal links with cluster context."""
    rows = []
    tc = topic_clusters or {}
    page_topics = tc.get("page_topics", {})

    for r in audit_results:
        url = r.get("url", "")
        il = r.get("internal_links", [])
        if not isinstance(il, list):
            continue

        source_topics = set(t.get("topic", "") for t in page_topics.get(url, []))

        for link in il:
            target = link.get("url", "")
            anchor = link.get("anchor", "")
            target_topics = set(t.get("topic", "") for t in page_topics.get(target, []))

            shared = source_topics & target_topics
            same_cluster = bool(shared)

            # Check if link is in same URL hierarchy
            source_path = urlparse(url).path.lower().strip("/")
            target_path = urlparse(target).path.lower().strip("/")
            is_parent_child = (
                target_path.startswith(source_path + "/") or
                source_path.startswith(target_path + "/")
            )
            is_sibling = False
            if "/" in source_path and "/" in target_path:
                is_sibling = source_path.rsplit("/", 1)[0] == target_path.rsplit("/", 1)[0]

            relationship = "parent/child" if is_parent_child else ("sibling" if is_sibling else "cross")

            rows.append({
                "From": url,
                "To": target,
                "Anchor": anchor[:60],
                "Same Cluster": "YES" if same_cluster else "NO",
                "Shared Topics": ", ".join(shared) if shared else "",
                "Relationship": relationship,
            })

    return pd.DataFrame(rows)


def _build_action_items(audit_results, topic_clusters):
    """Build Sheet 4: Action Items — everything that needs fixing."""
    rows = []

    for r in audit_results:
        url = r.get("url", "")
        impressions = r.get("impressions", 0)

        # Meta issues
        meta_score = r.get("meta_score")
        if meta_score is not None and meta_score < 70:
            rows.append({
                "Priority": "HIGH" if impressions > 1000 else "MEDIUM",
                "URL": url,
                "Action": f"Fix meta tags (score {meta_score}/100)",
                "Type": "Meta",
                "Impressions": impressions,
                "Backlinks Needed": "",
            })

        # Content issues
        qkey = f"_quality_{stable_hash(url)}"
        ai_q = st.session_state.get(qkey, {})
        if ai_q and ai_q.get("verdict") == "REWRITE":
            rows.append({
                "Priority": "HIGH",
                "URL": url,
                "Action": f"Rewrite content: {ai_q.get('summary', '')}",
                "Type": "Content",
                "Impressions": impressions,
                "Backlinks Needed": "",
            })
        elif ai_q and ai_q.get("verdict") == "IMPROVE":
            rows.append({
                "Priority": "MEDIUM",
                "URL": url,
                "Action": f"Improve content: {ai_q.get('summary', '')}",
                "Type": "Content",
                "Impressions": impressions,
                "Backlinks Needed": "",
            })

        # Backlink issues
        rd = r.get("referring_domains", 0)
        if impressions > 1000 and rd < 3:
            rows.append({
                "Priority": "HIGH",
                "URL": url,
                "Action": f"Build backlinks — {impressions:,} impressions but only {rd} referring domains",
                "Type": "Backlinks",
                "Impressions": impressions,
                "Backlinks Needed": "YES",
            })

    return pd.DataFrame(rows).sort_values(["Priority", "Impressions"], ascending=[True, False])


def _build_new_content(content_roadmap):
    """Build Sheet 5: New Content Needed."""
    if not content_roadmap:
        return pd.DataFrame()

    rows = []
    for article in content_roadmap.get("articles_needed", []):
        rows.append({
            "Title": article.get("suggested_title", ""),
            "Type": article.get("content_type", ""),
            "Target Keywords": ", ".join(article.get("target_keywords", [])),
            "Hub Page": article.get("supporting_page", ""),
            "Priority": article.get("priority", ""),
            "Est. Impressions": article.get("estimated_impressions", 0),
            "Cluster": article.get("cluster_topic", ""),
        })

    return pd.DataFrame(rows).sort_values("Est. Impressions", ascending=False)


def render():
    st.markdown("## Site Map & Cluster Export")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1.5rem;'>"
        "Complete overview of site structure, clusters, links, and actions. "
        "Export to Excel or let AI validate the entire structure.</p>",
        unsafe_allow_html=True,
    )

    # ── Check prerequisites ───────────────────────────────────────
    missing, checks, optional = _check_prerequisites()

    if missing:
        st.warning("Required analyses not yet run:")
        for m in missing:
            st.markdown(f"- {m}")
        return

    # Show what's available
    st.markdown("**Data available:**")
    for key, (name, _) in {**checks, **optional}.items():
        if key in st.session_state:
            data = st.session_state[key]
            count = len(data) if hasattr(data, '__len__') else "loaded"
            st.markdown(
                f"<span style='color:#33dd88; font-size:0.8rem;'>+ {name}: {count}</span>",
                unsafe_allow_html=True,
            )

    audit_results = st.session_state["audit_results"]
    gsc_data = st.session_state.get("gsc_data")
    topic_clusters = st.session_state.get("topic_clusters", {})
    content_roadmap = st.session_state.get("content_roadmap")

    st.markdown("---")

    # ── Build data ────────────────────────────────────────────────
    with st.spinner("Building site map..."):
        df_structure = _build_site_structure(audit_results, gsc_data, topic_clusters)
        df_clusters = _build_cluster_detail(topic_clusters, audit_results, gsc_data)
        df_links = _build_link_matrix(audit_results, topic_clusters)
        df_actions = _build_action_items(audit_results, topic_clusters)
        df_new_content = _build_new_content(content_roadmap)

    # ── Summary metrics ───────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Pages", len(df_structure))
    c2.metric("Clusters", len(topic_clusters.get("clusters", [])))
    c3.metric("Internal Links", len(df_links))
    c4.metric("Action Items", len(df_actions))
    c5.metric("New Content", len(df_new_content))

    # Quick health indicators
    orphans = len(df_structure[df_structure["Links In"] == 0]) if "Links In" in df_structure.columns else 0
    no_cluster = len(df_structure[df_structure["Cluster(s)"] == ""]) if "Cluster(s)" in df_structure.columns else 0
    thin = len(df_structure[(df_structure["Word Count"] < 100) & (df_structure["Word Count"] > 0)]) if "Word Count" in df_structure.columns else 0

    c6, c7, c8 = st.columns(3)
    c6.metric("Orphan Pages (0 links in)", orphans)
    c7.metric("Pages without Cluster", no_cluster)
    c8.metric("Thin Pages (<100 words)", thin)

    st.markdown("---")

    # ── Excel Export ──────────────────────────────────────────────
    st.markdown("### Export to Excel")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_structure.to_excel(writer, sheet_name="Site Structure", index=False)
        if not df_clusters.empty:
            df_clusters.to_excel(writer, sheet_name="Cluster Detail", index=False)
        if not df_links.empty:
            # Limit links to keep file manageable
            df_links.head(5000).to_excel(writer, sheet_name="Link Matrix", index=False)
        if not df_actions.empty:
            df_actions.to_excel(writer, sheet_name="Action Items", index=False)
        if not df_new_content.empty:
            df_new_content.to_excel(writer, sheet_name="New Content", index=False)
    output.seek(0)

    st.download_button(
        f"Download Excel ({len(df_structure)} pages, 5 sheets)",
        output.getvalue(),
        "site_map_export.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

    # ── Preview tabs ──────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        f"Site Structure ({len(df_structure)})",
        f"Clusters ({len(df_clusters)})",
        f"Links ({len(df_links)})",
        f"Actions ({len(df_actions)})",
        f"New Content ({len(df_new_content)})",
    ])

    with tab1:
        st.dataframe(df_structure.head(50), use_container_width=True, hide_index=True)
    with tab2:
        st.dataframe(df_clusters.head(50), use_container_width=True, hide_index=True)
    with tab3:
        st.dataframe(df_links.head(50), use_container_width=True, hide_index=True)
    with tab4:
        st.dataframe(df_actions.head(50), use_container_width=True, hide_index=True)
    with tab5:
        st.dataframe(df_new_content.head(50), use_container_width=True, hide_index=True)

    # ── AI Validation ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### AI Structure Validation")
    st.markdown(
        "<p style='color:#9b9bb8; font-size:0.85rem;'>"
        "AI reviews the complete site structure and identifies systemic issues: "
        "broken cluster hierarchies, orphan pages, keyword cannibalization patterns, "
        "link structure problems.</p>",
        unsafe_allow_html=True,
    )

    validation_key = "_site_validation"
    if st.button("Validate entire site structure with AI", type="primary"):
        if not has_anthropic_key():
            st.warning("Add Anthropic API key")
        else:
            with st.spinner("AI analyzing complete site structure... (~30 sec)"):
                try:
                    from utils.ai_generator import get_client, _parse_ai_json

                    client = get_client(get_anthropic_key())

                    # Build summary for AI
                    summary = {
                        "total_pages": len(df_structure),
                        "total_clusters": len(topic_clusters.get("clusters", [])),
                        "orphan_pages": int(orphans),
                        "pages_without_cluster": int(no_cluster),
                        "thin_pages": int(thin),
                        "total_impressions": int(df_structure["Impressions"].sum()),
                        "total_clicks": int(df_structure["Clicks"].sum()),
                        "page_types": df_structure["Page Type"].value_counts().to_dict(),
                        "top_10_pages": df_structure.nlargest(10, "Impressions")[["URL", "Page Type", "Cluster(s)", "Impressions", "Backlinks (domains)", "AI Quality", "Links Out", "Links In"]].to_dict("records"),
                        "clusters_summary": [
                            {"topic": c.get("topic", ""), "pages": c.get("page_count", 0), "impressions": c.get("total_impressions", 0)}
                            for c in topic_clusters.get("clusters", [])[:20]
                        ],
                        "cross_cluster_links": int(len(df_links[df_links["Same Cluster"] == "NO"])) if not df_links.empty else 0,
                        "same_cluster_links": int(len(df_links[df_links["Same Cluster"] == "YES"])) if not df_links.empty else 0,
                        "action_items_count": len(df_actions),
                        "new_content_needed": len(df_new_content),
                    }

                    prompt = f"""You are a senior SEO architect. Review this complete site structure and identify SYSTEMIC issues.

## SITE SUMMARY
{json.dumps(summary, ensure_ascii=False, indent=2)}

## YOUR ANALYSIS
Evaluate the OVERALL site health. Focus on:
1. **Cluster completeness**: Are topic clusters well-formed? Do they have hubs + spokes?
2. **Orphan pages**: {orphans} pages have 0 inbound links — is this a problem?
3. **Pages without clusters**: {no_cluster} pages aren't in any cluster — what should happen to them?
4. **Link structure**: {summary.get('cross_cluster_links', 0)} cross-cluster links vs {summary.get('same_cluster_links', 0)} same-cluster links — is the ratio healthy?
5. **Content gaps**: Where are the biggest opportunities?
6. **Keyword cannibalization**: Any patterns visible in the cluster data?
7. **Backlink distribution**: Are backlinks concentrated on the right pages?

## OUTPUT (JSON):
{{
  "overall_health_score": 0,
  "summary": "3-4 sentences about the site's overall SEO architecture health",
  "critical_issues": ["issue 1", "issue 2"],
  "structural_problems": ["problem 1", "problem 2"],
  "cluster_issues": ["cluster issue 1"],
  "link_issues": ["link issue 1"],
  "opportunities": ["opportunity 1", "opportunity 2"],
  "priority_actions": [
    {{"action": "what to do", "impact": "high/medium/low", "pages_affected": 0}}
  ]
}}"""

                    message = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=3000,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    result = _parse_ai_json(message)
                    st.session_state[validation_key] = result
                    from utils.persistence import save_ai_cache
                    save_ai_cache()
                except Exception as e:
                    st.error(f"Error: {e}")

    if validation_key in st.session_state:
        v = st.session_state[validation_key]
        score = v.get("overall_health_score", 0)
        score_color = "#33dd88" if score >= 70 else "#ffaa33" if score >= 40 else "#ff4455"

        st.markdown(
            f"<div style='background:#0d0d15; border:2px solid {score_color}; border-radius:8px; padding:1rem; margin:0.5rem 0;'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
            f"<div style='font-size:0.9rem; color:#e8e8f0;'>{v.get('summary', '')}</div>"
            f"<div style='font-size:2.5rem; font-weight:800; color:{score_color};'>{score}/100</div>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

        for section, title, color in [
            ("critical_issues", "Critical Issues", "#ff4455"),
            ("structural_problems", "Structural Problems", "#ffaa33"),
            ("cluster_issues", "Cluster Issues", "#c8b4ff"),
            ("link_issues", "Link Issues", "#ffaa33"),
            ("opportunities", "Opportunities", "#33dd88"),
        ]:
            items = v.get(section, [])
            if items:
                st.markdown(f"**{title}:**")
                for item in items:
                    st.markdown(
                        f"<div style='font-size:0.85rem; color:{color}; padding:2px 0;'>{'✗' if 'issue' in section or 'problem' in section else '+'} {item}</div>",
                        unsafe_allow_html=True,
                    )

        actions = v.get("priority_actions", [])
        if actions:
            st.markdown("**Priority Actions:**")
            for a in actions:
                impact_color = {"high": "#ff4455", "medium": "#ffaa33", "low": "#33dd88"}.get(a.get("impact", ""), "#6b6b8a")
                st.markdown(
                    f"<div style='background:#12121f; border-left:3px solid {impact_color}; padding:0.4rem 0.8rem; margin:0.3rem 0; border-radius:0 4px 4px 0;'>"
                    f"<span style='color:{impact_color}; font-size:0.7rem; text-transform:uppercase;'>{a.get('impact', '')}</span> "
                    f"<span style='color:#e8e8f0; font-size:0.85rem;'>{a.get('action', '')}</span>"
                    f"<span style='color:#6b6b8a; font-size:0.72rem; margin-left:0.5rem;'>({a.get('pages_affected', 0)} pages)</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # ── AI Plan Validation ────────────────────────────────────────
    st.markdown("---")
    st.markdown("### AI Plan Validation")
    st.markdown(
        "<p style='color:#9b9bb8; font-size:0.85rem;'>"
        "AI reviews ALL generated implementation plans against the site issues found above. "
        "Checks: Will these plans actually fix the problems? Is anything missing? "
        "Do any plans conflict with each other? Is the priority order correct?</p>",
        unsafe_allow_html=True,
    )

    # Check how many plans exist
    plan_count = sum(1 for k in st.session_state if k.startswith("_ai_plan_"))
    plans_data = {}
    for k, v in st.session_state.items():
        if k.startswith("_ai_plan_") and isinstance(v, dict) and not v.get("error"):
            # Find the URL for this plan
            for r in audit_results:
                if f"_ai_plan_{stable_hash(r['url'])}" == k:
                    plans_data[r["url"]] = v
                    break

    st.markdown(f"**{len(plans_data)} implementation plans generated** ({plan_count} total including errors)")

    if len(plans_data) == 0:
        st.info("Generate implementation plans first in **14. Implementation** → then come back here to validate.")
    elif validation_key not in st.session_state:
        st.info("Run **AI Structure Validation** above first — the plan validation needs the site issues to check against.")
    else:
        plan_validation_key = "_plan_validation"

        if st.button("Validate all implementation plans against site issues", type="primary", key="btn_validate_plans"):
            with st.spinner("AI cross-checking all plans against site issues... (~30 sec)"):
                try:
                    from utils.ai_generator import get_client, _parse_ai_json
                    client = get_client(get_anthropic_key())

                    # Collect site issues from validation
                    site_issues = st.session_state.get(validation_key, {})

                    # Summarize all plans
                    plan_summaries = []
                    for url, plan in list(plans_data.items())[:20]:
                        steps_summary = []
                        for s in plan.get("steps", []):
                            steps_summary.append(f"- [{s.get('type','')}] {s.get('action','')}")
                        new_content = [nc.get("suggested_title", "") for nc in plan.get("new_content_suggestions", [])]
                        rewrites = [rw.get("section", "") for rw in plan.get("text_rewrites", [])]

                        plan_summaries.append({
                            "url": url,
                            "primary_keyword": plan.get("primary_keyword", ""),
                            "steps": steps_summary[:6],
                            "new_content": new_content,
                            "rewrites": rewrites,
                            "meta_changed": plan.get("meta_changed", False),
                        })

                    prompt = f"""You are a senior SEO strategist doing a final review.

## SITE ISSUES FOUND (from site structure analysis)
Health score: {site_issues.get('overall_health_score', '?')}/100
Critical issues: {json.dumps(site_issues.get('critical_issues', []))}
Structural problems: {json.dumps(site_issues.get('structural_problems', []))}
Cluster issues: {json.dumps(site_issues.get('cluster_issues', []))}
Link issues: {json.dumps(site_issues.get('link_issues', []))}
Priority actions recommended: {json.dumps([a.get('action','') for a in site_issues.get('priority_actions', [])])}

## IMPLEMENTATION PLANS GENERATED ({len(plan_summaries)} pages)
{json.dumps(plan_summaries, ensure_ascii=False, indent=1)}

## YOUR TASK
Cross-check the implementation plans against the site issues. Answer:

1. **Coverage**: Do the plans address ALL critical issues? Which critical issues are NOT covered by any plan?
2. **Conflicts**: Do any plans conflict with each other? (e.g., two plans adding the same keyword, competing links)
3. **Priority**: Is the order correct? Should any page be fixed before others?
4. **Missing**: What actions are needed that NO plan includes? (e.g., orphan page integration, cluster consolidation)
5. **Risks**: Will any recommended change potentially hurt rankings?
6. **Sequence**: What is the correct order to implement these changes?

## OUTPUT (JSON):
{{
    "plans_cover_issues": true/false,
    "coverage_score": 0,
    "uncovered_issues": ["critical issue not addressed by any plan"],
    "conflicts": [{{"plan_a": "url", "plan_b": "url", "conflict": "description"}}],
    "priority_corrections": ["plan X should be done before plan Y because..."],
    "missing_actions": ["action needed but not in any plan"],
    "risks": ["potential risk from recommended changes"],
    "recommended_sequence": [
        {{"order": 1, "action": "what to do first", "urls": ["url1"], "reason": "why first"}}
    ],
    "overall_verdict": "2-3 sentences: are these plans correct and complete?",
    "confidence": 0
}}"""

                    message = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=3000,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    result = _parse_ai_json(message)
                    st.session_state[plan_validation_key] = result
                    from utils.persistence import save_ai_cache
                    save_ai_cache()
                except Exception as e:
                    st.error(f"Error: {e}")

        if plan_validation_key in st.session_state:
            pv = st.session_state[plan_validation_key]
            conf = pv.get("confidence", 0)
            cov = pv.get("coverage_score", 0)
            covers = pv.get("plans_cover_issues", False)

            cov_color = "#33dd88" if cov >= 70 else "#ffaa33" if cov >= 40 else "#ff4455"
            verdict_border = "#33dd88" if covers else "#ff4455"

            # Verdict
            st.markdown(
                f"<div style='background:#0d0d15; border:2px solid {verdict_border}; border-radius:8px; padding:1rem; margin:0.5rem 0;'>"
                f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
                f"<div>"
                f"<div style='font-size:0.95rem; color:#e8e8f0; font-weight:600; margin-bottom:0.3rem;'>"
                f"{'PLANS ARE CORRECT' if covers else 'PLANS HAVE GAPS'}</div>"
                f"<div style='font-size:0.85rem; color:#9b9bb8;'>{pv.get('overall_verdict', '')}</div>"
                f"</div>"
                f"<div style='text-align:center;'>"
                f"<div style='font-size:2rem; font-weight:800; color:{cov_color};'>{cov}%</div>"
                f"<div style='font-size:0.6rem; color:#6b6b8a;'>COVERAGE</div>"
                f"</div>"
                f"</div></div>",
                unsafe_allow_html=True,
            )

            # Uncovered issues
            uncovered = pv.get("uncovered_issues", [])
            if uncovered:
                st.markdown("**Issues NOT covered by any plan:**")
                for u in uncovered:
                    st.markdown(f"<div style='color:#ff4455; font-size:0.85rem;'>✗ {u}</div>", unsafe_allow_html=True)

            # Conflicts
            conflicts = pv.get("conflicts", [])
            if conflicts:
                st.markdown("**Plan conflicts:**")
                for c in conflicts:
                    st.markdown(
                        f"<div style='color:#ffaa33; font-size:0.85rem;'>"
                        f"⚠ {c.get('plan_a','')} vs {c.get('plan_b','')}: {c.get('conflict','')}</div>",
                        unsafe_allow_html=True,
                    )

            # Missing actions
            missing = pv.get("missing_actions", [])
            if missing:
                st.markdown("**Missing actions (not in any plan):**")
                for m in missing:
                    st.markdown(f"<div style='color:#c8b4ff; font-size:0.85rem;'>+ {m}</div>", unsafe_allow_html=True)

            # Risks
            risks = pv.get("risks", [])
            if risks:
                st.markdown("**Risks:**")
                for r in risks:
                    st.markdown(f"<div style='color:#ffaa33; font-size:0.85rem;'>⚠ {r}</div>", unsafe_allow_html=True)

            # Recommended sequence
            sequence = pv.get("recommended_sequence", [])
            if sequence:
                st.markdown("**Recommended implementation sequence:**")
                for s in sequence:
                    urls = ", ".join(s.get("urls", [])[:3])
                    st.markdown(
                        f"<div style='background:#12121f; border-left:3px solid #5533ff; padding:0.4rem 0.8rem; "
                        f"margin:0.3rem 0; border-radius:0 4px 4px 0;'>"
                        f"<span style='color:#5533ff; font-weight:700;'>Step {s.get('order', '?')}:</span> "
                        f"<span style='color:#e8e8f0; font-size:0.85rem;'>{s.get('action', '')}</span><br>"
                        f"<span style='color:#6b6b8a; font-size:0.72rem;'>{urls} — {s.get('reason', '')}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

            # Priority corrections
            corrections = pv.get("priority_corrections", [])
            if corrections:
                st.markdown("**Priority corrections:**")
                for c in corrections:
                    st.markdown(f"<div style='color:#ffaa33; font-size:0.85rem;'>→ {c}</div>", unsafe_allow_html=True)
