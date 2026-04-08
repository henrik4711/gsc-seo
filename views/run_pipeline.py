"""
Run Pipeline — One-page control center for running all SEO analysis steps.
Each step has a Run button and shows status. "Run All" runs everything sequentially.
"""

import streamlit as st
from utils.persistence import save_key
from config import get_anthropic_key, has_anthropic_key


def _step_status(state_key):
    """Returns status icon + label with smart count display."""
    if state_key in st.session_state and st.session_state[state_key] is not None:
        data = st.session_state[state_key]
        try:
            # DataFrames need .empty check, not just len()
            import pandas as pd
            if isinstance(data, pd.DataFrame):
                if data.empty:
                    return "✗", "Not run", "#6b6b8a"
                labels = {
                    "gsc_data": "queries",
                    "ctr_gaps": "gaps",
                    "cannibalization": "conflicts",
                    "page_authority": "pages",
                }
                label = labels.get(state_key, "rows")
                return "✓", f"Done ({len(data):,} {label})", "#33dd88"
            # Special handling for topic_clusters dict
            if state_key == "topic_clusters" and isinstance(data, dict):
                clusters = data.get("clusters", [])
                if not clusters:
                    return "✗", "Not run", "#6b6b8a"
                return "✓", f"Done ({len(clusters):,} clusters)", "#33dd88"
            # Special handling for crawl issues dict
            if state_key == "sf_crawl_issues" and isinstance(data, dict):
                total = sum(len(v) for v in data.values() if hasattr(v, "__len__"))
                if total == 0:
                    return "✗", "Not run", "#6b6b8a"
                return "✓", f"Done ({total:,} issues)", "#33dd88"
            # Lists
            if isinstance(data, list):
                if not data:
                    return "✗", "Not run", "#6b6b8a"
                return "✓", f"Done ({len(data):,} items)", "#33dd88"
            # Other dicts
            if isinstance(data, dict) and data:
                return "✓", "Done", "#33dd88"
        except Exception:
            pass
        return "✓", "Done", "#33dd88"
    return "✗", "Not run", "#6b6b8a"


def _run_step_card(num, title, description, state_key, run_fn, button_key):
    """Render one step card with status + Run button."""
    icon, status_label, color = _step_status(state_key)

    col1, col2, col3 = st.columns([1, 6, 2])
    with col1:
        st.markdown(
            f"<div style='font-size:1.5rem; color:{color}; text-align:center; padding-top:0.5rem;'>{icon}</div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"<div style='font-weight:600; color:#e8e8f0;'>{num}. {title}</div>"
            f"<div style='font-size:0.8rem; color:#9b9bb8;'>{description}</div>"
            f"<div style='font-size:0.7rem; color:{color}; margin-top:0.2rem;'>{status_label}</div>",
            unsafe_allow_html=True,
        )
    with col3:
        if st.button("Run", key=button_key, use_container_width=True):
            try:
                with st.spinner(f"Running {title}..."):
                    run_fn()
                st.success(f"{title} done")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
                import traceback
                st.code(traceback.format_exc())

    st.markdown("<hr style='margin:0.5rem 0; border:none; border-top:1px solid #1e1e2e;'>", unsafe_allow_html=True)


# ── Run functions for each step ─────────────────────────────────

def _run_fetch_gsc():
    from utils.gsc_client import fetch_gsc_data, build_gsc_service
    creds = st.session_state.get("gsc_credentials")
    site = st.session_state.get("gsc_site_url") or st.session_state.get("gsc_site")
    if not creds or not site:
        raise ValueError("GSC credentials or site URL missing — go to 1. Setup & Connect first")
    if "gsc_service" not in st.session_state:
        st.session_state["gsc_service"] = build_gsc_service(creds)
    df = fetch_gsc_data(st.session_state["gsc_service"], site)
    st.session_state["gsc_data"] = df
    st.session_state["gsc_site"] = site
    save_key("gsc_data")


def _run_build_authority():
    from utils.ahrefs_import import build_page_authority
    bbl = st.session_state.get("ahrefs_best_by_links")
    bl = st.session_state.get("ahrefs_backlinks")
    if bbl is None or bbl.empty:
        raise ValueError("Ahrefs Best by Links not loaded — check 2. Upload Ahrefs")
    authority = build_page_authority(best_by_links_df=bbl, backlinks_df=bl)
    st.session_state["page_authority"] = authority
    save_key("page_authority")


def _run_crawl_analysis():
    import pandas as pd
    from utils.screaming_frog_import import analyze_crawl_data
    sf_pages = st.session_state.get("sf_pages")
    sf_inlinks = st.session_state.get("sf_inlinks")
    if sf_pages is None or sf_pages.empty:
        raise ValueError("Screaming Frog pages not loaded")
    site_domain = ""
    if "gsc_site" in st.session_state:
        site_domain = st.session_state["gsc_site"].replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
    issues = analyze_crawl_data(
        sf_pages,
        sf_inlinks if sf_inlinks is not None else pd.DataFrame(),
        site_domain,
        gsc_data=st.session_state.get("gsc_data"),
        page_authority=st.session_state.get("page_authority"),
        sf_all_pages=sf_pages,
    )
    st.session_state["sf_crawl_issues"] = issues
    save_key("sf_crawl_issues")


def _run_ctr_analysis():
    from utils.gsc_client import identify_ctr_gaps
    df = st.session_state.get("gsc_data")
    if df is None or df.empty:
        raise ValueError("GSC data not loaded")
    gaps = identify_ctr_gaps(df, gap_threshold=-5)
    st.session_state["ctr_gaps"] = gaps
    save_key("ctr_gaps")


def _run_cannibalization():
    from utils.cannibalization import detect_cannibalization, get_page_cannibalization_summary, get_cannibalization_clusters
    df = st.session_state.get("gsc_data")
    if df is None or df.empty:
        raise ValueError("GSC data not loaded")
    cannibal_df = detect_cannibalization(df, min_impressions=10)
    st.session_state["cannibalization"] = cannibal_df
    st.session_state["cannibal_page_summary"] = get_page_cannibalization_summary(cannibal_df)
    st.session_state["cannibal_clusters"] = get_cannibalization_clusters(cannibal_df)
    save_key("cannibalization")


def _run_topic_clusters():
    from utils.ai_generator import get_client, ai_generate_clusters
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    df = st.session_state.get("gsc_data")
    if df is None or df.empty:
        raise ValueError("GSC data not loaded")
    client = get_client(get_anthropic_key())
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")

    # Prepare keyword data
    kw_summary = df.groupby("query").agg(
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        position=("position", "mean"),
    ).sort_values("impressions", ascending=False).head(250).reset_index()
    keywords_data = []
    for _, row in kw_summary.iterrows():
        pages = df[df["query"] == row["query"]]["page"].unique().tolist()[:3]
        keywords_data.append({
            "keyword": row["query"],
            "impressions": int(row["impressions"]),
            "clicks": int(row["clicks"]),
            "position": round(row["position"], 1),
            "pages": pages,
        })

    result = ai_generate_clusters(client, keywords_data, site_context=site_context, language=language)

    # Build topic_clusters structure compatible with rest of system
    from utils.topic_clusters import build_topic_clusters
    fallback = build_topic_clusters(df, min_cluster_size=2)
    if result and result.get("clusters"):
        # Use AI clusters but keep page_topics from algorithmic for completeness
        ai_clusters = result["clusters"]
        # Enrich with page data from GSC
        for c in ai_clusters:
            cluster_queries = c.get("queries", [])
            cluster_pages = df[df["query"].isin(cluster_queries)]["page"].unique().tolist()
            c["pages"] = [{"page": p, "query_count": 0, "total_clicks": 0, "total_impressions": 0, "avg_position": 0} for p in cluster_pages[:20]]
            c["page_count"] = len(cluster_pages)
        fallback["clusters"] = ai_clusters
        fallback["summary"] = result.get("summary", "")

    st.session_state["topic_clusters"] = fallback
    save_key("topic_clusters")

    # Also generate content_gaps and content_roadmap
    from utils.topic_clusters import identify_content_gaps, generate_content_roadmap
    auth = st.session_state.get("page_authority")
    try:
        gaps = identify_content_gaps(fallback.get("clusters", []), auth)
        st.session_state["content_gaps"] = gaps
        save_key("content_gaps")
    except Exception as e:
        print(f"[pipeline] content_gaps failed: {e}")

    try:
        roadmap = generate_content_roadmap(
            fallback.get("clusters", []),
            df,
            auth,
            language=language,
        )
        st.session_state["content_roadmap"] = roadmap
        save_key("content_roadmap")
    except Exception as e:
        print(f"[pipeline] content_roadmap failed: {e}")


def _run_bulk_audit():
    """Trigger the bulk audit. This is the slowest step."""
    raise NotImplementedError("Bulk audit must be run from 6. Page Auditor — too long for this page")


def _run_quality_check():
    from utils.ai_generator import get_client, assess_content_quality_batch
    from utils.ui_helpers import stable_hash
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    audit_results = st.session_state.get("audit_results", [])
    if not audit_results:
        raise ValueError("Run bulk audit first")
    # Check pages not yet assessed
    candidates = [r for r in audit_results
                  if r.get("page_type") in ("category", "blog", "faq")
                  and r.get("word_count", 0) > 50
                  and f"_quality_{stable_hash(r['url'])}" not in st.session_state]
    if not candidates:
        return
    client = get_client(get_anthropic_key())
    # Process in batches of 5
    for i in range(0, min(len(candidates), 50), 5):  # Max 50 pages per click
        batch = candidates[i:i+5]
        results = assess_content_quality_batch(
            client, batch,
            site_context=st.session_state.get("site_context", ""),
            language=st.session_state.get("content_language", "Swedish"),
            topic_clusters=st.session_state.get("topic_clusters"),
        )
        for r in results:
            url = r.get("url", "")
            st.session_state[f"_quality_{stable_hash(url)}"] = r
    from utils.persistence import save_ai_cache
    save_ai_cache()


def _run_site_validation():
    """Run AI site structure validation."""
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    if "audit_results" not in st.session_state:
        raise ValueError("Run bulk audit first")
    if "topic_clusters" not in st.session_state:
        raise ValueError("Run topic clusters first")

    import json
    from utils.ai_generator import get_client, _parse_ai_json
    from views.site_map_export import _build_site_structure

    audit_results = st.session_state["audit_results"]
    gsc_data = st.session_state.get("gsc_data")
    topic_clusters = st.session_state.get("topic_clusters", {})
    page_authority = st.session_state.get("page_authority")

    df_structure = _build_site_structure(audit_results, gsc_data, topic_clusters, page_authority)
    if df_structure.empty:
        raise ValueError("No site structure data")

    orphans = len(df_structure[df_structure["Links In"] == 0]) if "Links In" in df_structure.columns else 0
    no_cluster = len(df_structure[df_structure["Cluster(s)"] == ""]) if "Cluster(s)" in df_structure.columns else 0
    thin = len(df_structure[df_structure.get("Word Count", 0) < 300]) if "Word Count" in df_structure.columns else 0

    summary = {
        "total_pages": len(df_structure),
        "total_clusters": len(topic_clusters.get("clusters", [])),
        "orphan_pages": int(orphans),
        "pages_without_cluster": int(no_cluster),
        "thin_pages": int(thin),
        "total_impressions": int(df_structure["Impressions"].sum()) if "Impressions" in df_structure.columns else 0,
        "total_clicks": int(df_structure["Clicks"].sum()) if "Clicks" in df_structure.columns else 0,
        "page_types": df_structure["Page Type"].value_counts().to_dict() if "Page Type" in df_structure.columns else {},
        "clusters_summary": [
            {"topic": c.get("topic", ""), "pages": c.get("page_count", 0), "impressions": c.get("total_impressions", 0)}
            for c in topic_clusters.get("clusters", [])[:20]
        ],
    }

    client = get_client(get_anthropic_key())
    prompt = f"""You are a senior SEO architect. Review this site structure and identify SYSTEMIC issues.

## SITE SUMMARY
{json.dumps(summary, ensure_ascii=False, indent=2)}

## YOUR ANALYSIS
Evaluate the OVERALL site health. Focus on:
1. Cluster completeness
2. Orphan pages ({orphans} found)
3. Pages without clusters ({no_cluster})
4. Content gaps
5. Cannibalization patterns

## OUTPUT (JSON):
{{
  "overall_health_score": 0,
  "summary": "3-4 sentences about site SEO health",
  "critical_issues": ["issue 1", "issue 2"],
  "structural_problems": ["problem 1"],
  "cluster_issues": ["cluster issue 1"],
  "opportunities": ["opportunity 1"],
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
    st.session_state["_site_validation"] = result
    from utils.persistence import _save_ai_key, _volume_available
    if _volume_available():
        _save_ai_key("_site_validation", result)


# ── Main render ────────────────────────────────────────────────

def render():
    st.markdown("## ⚡ Run Pipeline")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1rem;'>"
        "Run all SEO analysis steps from one page. Click each step's Run button, "
        "or use Run All Remaining at the bottom.</p>",
        unsafe_allow_html=True,
    )

    if "gsc_data" not in st.session_state:
        st.warning("**First time?** Go to **1. Setup & Connect** in the menu and connect GSC. Then come back here.")
        return

    st.markdown("---")

    # ── Steps ───────────────────────────────────────────────
    _run_step_card(
        1, "Fetch GSC data",
        "Pull queries, pages, clicks, impressions from Google Search Console (90 days)",
        "gsc_data", _run_fetch_gsc, "rp_gsc"
    )

    _run_step_card(
        2, "Build Page Authority",
        "Combine Ahrefs Best by Links + Backlinks → per-page authority scores",
        "page_authority", _run_build_authority, "rp_authority"
    )

    _run_step_card(
        3, "Analyze Crawl Issues",
        "Detect orphans, broken links, canonicals, faceted URLs, near-duplicates from SF data",
        "sf_crawl_issues", _run_crawl_analysis, "rp_crawl"
    )

    _run_step_card(
        4, "CTR Gap Analysis",
        "Find pages where CTR underperforms vs position benchmarks",
        "ctr_gaps", _run_ctr_analysis, "rp_ctr"
    )

    _run_step_card(
        5, "Cannibalization Detection",
        "Find queries where multiple pages compete (with brand keyword filter)",
        "cannibalization", _run_cannibalization, "rp_cannibal"
    )

    _run_step_card(
        6, "Build Topic Clusters",
        "AI groups GSC queries into 30-50 topic clusters (~30 sec)",
        "topic_clusters", _run_topic_clusters, "rp_clusters"
    )

    # Bulk audit — special case (long running)
    icon, status, color = _step_status("audit_results")
    col1, col2, col3 = st.columns([1, 6, 2])
    with col1:
        st.markdown(
            f"<div style='font-size:1.5rem; color:{color}; text-align:center; padding-top:0.5rem;'>{icon}</div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"<div style='font-weight:600; color:#e8e8f0;'>7. Bulk Audit Pages</div>"
            f"<div style='font-size:0.8rem; color:#9b9bb8;'>Scrape + audit all pages from GSC (~20 min for 1000+ pages)</div>"
            f"<div style='font-size:0.7rem; color:{color}; margin-top:0.2rem;'>{status}</div>",
            unsafe_allow_html=True,
        )
    with col3:
        if st.button("Open →", key="rp_audit_link", use_container_width=True):
            st.session_state["selected_page"] = "6. Page Auditor"
            st.rerun()
    st.markdown("<hr style='margin:0.5rem 0; border:none; border-top:1px solid #1e1e2e;'>", unsafe_allow_html=True)

    # AI Quality (only if audit is done)
    if "audit_results" in st.session_state:
        from utils.ui_helpers import stable_hash
        audit_results = st.session_state.get("audit_results", [])
        candidates = [r for r in audit_results
                      if r.get("page_type") in ("category", "blog", "faq")
                      and r.get("word_count", 0) > 50]
        checked = sum(1 for r in candidates if f"_quality_{stable_hash(r['url'])}" in st.session_state)

        col1, col2, col3 = st.columns([1, 6, 2])
        with col1:
            done = checked == len(candidates) and len(candidates) > 0
            icon = "✓" if done else "⏳" if checked > 0 else "✗"
            color = "#33dd88" if done else "#ffaa33" if checked > 0 else "#6b6b8a"
            st.markdown(
                f"<div style='font-size:1.5rem; color:{color}; text-align:center; padding-top:0.5rem;'>{icon}</div>",
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                f"<div style='font-weight:600; color:#e8e8f0;'>8. AI Content Quality Check</div>"
                f"<div style='font-size:0.8rem; color:#9b9bb8;'>AI evaluates text quality on category + blog pages (50 per click)</div>"
                f"<div style='font-size:0.7rem; color:{color}; margin-top:0.2rem;'>{checked}/{len(candidates)} checked</div>",
                unsafe_allow_html=True,
            )
        with col3:
            remaining = len(candidates) - checked
            run_label = f"Run {min(50, remaining)}" if remaining > 0 else "Done"
            if st.button(run_label, key="rp_quality", use_container_width=True, disabled=remaining == 0):
                try:
                    with st.spinner(f"AI checking quality of {min(50, remaining)} pages..."):
                        _run_quality_check()
                    st.success("Quality check done")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        st.markdown("<hr style='margin:0.5rem 0; border:none; border-top:1px solid #1e1e2e;'>", unsafe_allow_html=True)

    # ── Site Validation (step 9) ────────────────────────────
    icon, status, color = _step_status("_site_validation")
    val_data = st.session_state.get("_site_validation", {})
    if isinstance(val_data, dict) and val_data.get("overall_health_score") is not None:
        score = val_data.get("overall_health_score", 0)
        status = f"Done (health score: {score}/100)"
        color = "#33dd88" if score >= 70 else "#ffaa33" if score >= 40 else "#ff4455"
        icon = "✓"
    col1, col2, col3 = st.columns([1, 6, 2])
    with col1:
        st.markdown(
            f"<div style='font-size:1.5rem; color:{color}; text-align:center; padding-top:0.5rem;'>{icon}</div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"<div style='font-weight:600; color:#e8e8f0;'>9. Site Validation</div>"
            f"<div style='font-size:0.8rem; color:#9b9bb8;'>AI evaluates entire site architecture and gives health score</div>"
            f"<div style='font-size:0.7rem; color:{color}; margin-top:0.2rem;'>{status}</div>",
            unsafe_allow_html=True,
        )
    with col3:
        if st.button("Run", key="rp_validation", use_container_width=True):
            try:
                with st.spinner("AI evaluating site architecture..."):
                    _run_site_validation()
                st.success("Validation done")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
                import traceback
                st.code(traceback.format_exc())
    st.markdown("<hr style='margin:0.5rem 0; border:none; border-top:1px solid #1e1e2e;'>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Maintenance")

    # Re-classify all audit results without re-scraping
    if "audit_results" in st.session_state:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(
                "<div style='font-size:0.85rem; color:#9b9bb8;'>"
                "<strong>Re-classify all pages</strong><br>"
                "Run new page type classifier on existing audit data without re-scraping. "
                "Use this after fixing classification rules.</div>",
                unsafe_allow_html=True,
            )
        with col2:
            if st.button("Re-classify", key="rp_reclassify", use_container_width=True):
                from utils.category_analyzer import classify_page_type
                results = st.session_state["audit_results"]
                changed = 0
                for r in results:
                    old_type = r.get("page_type", "unknown")
                    new_class = classify_page_type(r.get("url", ""), r)
                    new_type = new_class.get("page_type", "unknown")
                    if new_type != old_type:
                        r["page_type"] = new_type
                        changed += 1
                save_key("audit_results")
                st.success(f"Re-classified {changed}/{len(results)} pages")
                st.rerun()

    st.markdown("---")
    st.markdown(
        "<div style='background:#0d0d15; border:1px solid #5533ff; border-radius:6px; padding:0.8rem;'>"
        "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#5533ff; margin-bottom:0.3rem;'>NEXT</div>"
        "<div style='font-size:0.85rem; color:#c8b4ff;'>Once all steps are done, go to <strong>🎯 Action Center</strong> "
        "to see prioritized recommendations and generate content.</div>"
        "</div>",
        unsafe_allow_html=True,
    )
