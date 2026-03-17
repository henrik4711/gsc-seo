"""
Page Auditor
Scrapes landing pages, extracts meta data, evaluates quality vs. keywords.
Now with page-type detection and deep category analysis.
"""

import streamlit as st
import pandas as pd
import time
from utils.ui_helpers import shorten_url


def score_badge(score: int) -> str:
    if score >= 80:
        color, label = "#33dd88", "Good"
    elif score >= 50:
        color, label = "#ffaa33", "Issues"
    else:
        color, label = "#ff4455", "Critical"
    return f"<span style='color:{color}; font-family:\"IBM Plex Mono\",monospace; font-weight:600;'>{score}/100 · {label}</span>"


def issue_badge(issue_type: str) -> str:
    colors = {"critical": "#ff4455", "warn": "#ffaa33", "info": "#6b6baa"}
    labels = {"critical": "CRITICAL", "warn": "WARNING", "info": "INFO"}
    color = colors.get(issue_type, "#6b6b8a")
    label = labels.get(issue_type, issue_type.upper())
    return f"<span style='color:{color}; font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; font-weight:600;'>[{label}]</span>"


def severity_badge(severity: str) -> str:
    colors = {"critical": "#ff4455", "warn": "#ffaa33", "info": "#6b6baa"}
    labels = {"critical": "CRITICAL", "warn": "WARNING", "info": "INFO"}
    color = colors.get(severity, "#6b6b8a")
    label = labels.get(severity, severity.upper())
    return f"<span style='color:{color}; font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; font-weight:600;'>[{label}]</span>"


PAGE_TYPE_LABELS = {
    "category": ("CATEGORY", "#c8b4ff"),
    "product": ("PRODUCT", "#33dd88"),
    "blog": ("BLOG/GUIDE", "#ffaa33"),
    "unknown": ("UNKNOWN", "#6b6b8a"),
}


def _get_cluster_keywords(url: str) -> list:
    """Get keywords from topic clusters for this URL."""
    tc = st.session_state.get("topic_clusters")
    if not tc:
        return []
    keywords = []
    for cluster in tc.get("clusters", []):
        for page in cluster.get("pages", []):
            if page.get("page", "").rstrip("/").lower() == url.rstrip("/").lower():
                keywords.extend(cluster.get("queries", []))
    return list(set(keywords))[:50]


def render():
    st.markdown("## Page Auditor")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:2rem;'>Analyze meta title, description and content - with deep analysis of category pages</p>",
        unsafe_allow_html=True
    )

    if "gsc_data" not in st.session_state:
        st.warning("Go to **1. Setup & Connect** and connect GSC first.")
        return

    df = st.session_state["gsc_data"]

    # ── URL Input ─────────────────────────────────────────────────
    col1, col2 = st.columns([2, 1])

    with col1:
        # Pre-fill from audit queue if available
        default_urls = "\n".join(st.session_state.get("audit_queue", []))

        if not default_urls and "ctr_gaps" in st.session_state:
            top = (
                st.session_state["ctr_gaps"]
                .groupby("page")["lost_clicks_estimate"]
                .sum()
                .sort_values(ascending=False)
                .head(5)
                .index.tolist()
            )
            default_urls = "\n".join(top)

        urls_input = st.text_area(
            "URLs to analyze (one per line)",
            value=default_urls,
            height=150,
            help="Enter the URLs you want to audit"
        )

    with col2:
        st.markdown("#### Settings")
        scrape_live = st.toggle("Scrape live pages", value=True, help="Fetch current content from the website")
        deep_category = st.toggle("Deep category analysis", value=True, help="Separates editorial content from product grid on category pages")
        show_keywords = st.number_input("Top N keywords per page", min_value=3, max_value=15, value=5)

        st.markdown("<br>", unsafe_allow_html=True)
        run_audit = st.button("Run Audit", type="primary", use_container_width=True)

    urls = [u.strip() for u in urls_input.split("\n") if u.strip()]

    if not urls:
        st.info("Enter URLs above to start audit")
        return

    # ── Run Audit ─────────────────────────────────────────────────
    if run_audit:
        audit_results = []
        progress = st.progress(0)
        status_text = st.empty()

        for i, url in enumerate(urls):
            status_text.markdown(
                f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.8rem; color:#c8b4ff;'>Analyzing: {url}</div>",
                unsafe_allow_html=True
            )

            # Get keywords for this page from GSC
            page_queries = df[df["page"] == url].sort_values("impressions", ascending=False)
            target_keywords = page_queries["query"].head(show_keywords).tolist()

            # Also get cluster keywords for deeper validation
            cluster_keywords = _get_cluster_keywords(url)

            result = {
                "url": url,
                "target_keywords": target_keywords,
                "cluster_keywords": cluster_keywords,
                "lost_clicks_estimate": page_queries["lost_clicks_estimate"].sum() if "lost_clicks_estimate" in page_queries.columns else 0,
                "position": page_queries["position"].mean() if len(page_queries) > 0 else None,
                "ctr_gap_pct": page_queries["ctr_gap_pct"].mean() if "ctr_gap_pct" in page_queries.columns and len(page_queries) > 0 else 0,
                "impressions": page_queries["impressions"].sum(),
                "clicks": page_queries["clicks"].sum(),
            }

            if scrape_live:
                from utils.page_scraper import scrape_page, evaluate_meta
                from utils.category_analyzer import classify_page_type, deep_scrape_category, audit_category_content

                # Step 1: Quick classify from URL
                quick_class = classify_page_type(url)
                is_likely_category = quick_class["page_type"] == "category"

                # Step 2: Scrape (deep for categories, basic for others)
                if deep_category and is_likely_category:
                    page_data = deep_scrape_category(url)
                    result.update(page_data)
                    # Map fields for compatibility
                    result["body_text"] = page_data.get("full_body_text", "")
                    result["word_count"] = len(result["body_text"].split()) if result["body_text"] else 0
                    result["title_length"] = len(page_data.get("title") or "")
                    result["description_length"] = len(page_data.get("meta_description") or "")
                    result["internal_links"] = page_data.get("internal_link_count", 0)
                    result["images_without_alt"] = page_data.get("images_without_alt", 0)
                else:
                    page_data = scrape_page(url)
                    result.update(page_data)
                    # Classify with page data
                    classification = classify_page_type(url, page_data)
                    result["page_type"] = classification["page_type"]

                if result.get("success", page_data.get("success")):
                    # Meta evaluation (always)
                    meta_eval = evaluate_meta(result, target_keywords)
                    result["meta_score"] = meta_eval["score"]
                    result["issues"] = meta_eval["issues"]
                    result["meta_eval"] = meta_eval

                    # Content audit (deep for categories, standard for all page types)
                    cat_audit = audit_category_content(
                        result, cluster_keywords, target_keywords,
                        topic_clusters=st.session_state.get("topic_clusters"),
                        page_authority=st.session_state.get("page_authority"),
                    )
                    result["content_score"] = cat_audit["score"]
                    result["content_audit"] = cat_audit
                    # Merge content issues into main issues
                    for issue in cat_audit.get("issues", []):
                        result["issues"].append({
                            "type": issue["severity"],
                            "field": issue["area"],
                            "msg": issue["msg"],
                        })
                else:
                    result["meta_score"] = None
                    result["issues"] = [{"type": "critical", "field": "url", "msg": f"Could not fetch the page: {result.get('error', page_data.get('error'))}"}]
            else:
                result["success"] = True
                result["title"] = "(not fetched - scraping disabled)"
                result["meta_description"] = "(not fetched)"
                result["meta_score"] = None
                result["page_type"] = "unknown"
                result["issues"] = []

            audit_results.append(result)
            progress.progress((i + 1) / len(urls))
            time.sleep(0.3)

        st.session_state["audit_results"] = audit_results
        status_text.empty()
        progress.empty()
        st.success(f"Audit complete for {len(audit_results)} pages")

    # ── Display Results ───────────────────────────────────────────
    if "audit_results" not in st.session_state:
        return

    results = st.session_state["audit_results"]

    # Summary table
    st.markdown("### Overview")

    summary_rows = []
    for r in results:
        ptype = r.get("page_type", "unknown")
        label, _ = PAGE_TYPE_LABELS.get(ptype, ("?", "#6b6b8a"))
        summary_rows.append({
            "Page": shorten_url(r["url"]),
            "Type": label,
            "Meta Score": r.get("meta_score"),
            "Content Score": r.get("content_score"),
            "Title": (r.get("title") or "")[:60],
            "Title Lgd": r.get("title_length", 0),
            "Desc Lgd": r.get("description_length", 0),
            "Lost Clicks": r.get("lost_clicks_estimate", 0),
            "Top Keywords": ", ".join(r.get("target_keywords", [])[:3]),
        })

    summary_df = pd.DataFrame(summary_rows)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Detailed per-page view
    st.markdown("### Detailed Audit")

    for r in results:
        url_short = r["url"].replace("https://", "").replace("http://", "")
        meta_score = r.get("meta_score")
        content_score = r.get("content_score")
        lost = r.get("lost_clicks_estimate", 0)
        ptype = r.get("page_type", "unknown")
        type_label, type_color = PAGE_TYPE_LABELS.get(ptype, ("?", "#6b6b8a"))

        expander_label = f"{url_short}  |  {type_label}  |  Meta: {meta_score or '?'}/100"
        if content_score is not None:
            expander_label += f"  |  Content: {content_score}/100"
        expander_label += f"  |  Lost clicks: {lost:,}"

        with st.expander(expander_label):

            # Page type badge
            st.markdown(
                f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:{type_color}; "
                f"background:#0d0d15; display:inline-block; padding:3px 10px; border:1px solid {type_color}; "
                f"border-radius:4px; margin-bottom:1rem;'>{type_label} PAGE</div>",
                unsafe_allow_html=True
            )

            left, right = st.columns([3, 2])

            with left:
                # Current meta
                st.markdown("#### Current Meta")

                title = r.get("title") or "_(not found)_"
                desc = r.get("meta_description") or "_(not found)_"
                t_len = r.get("title_length", 0)
                d_len = r.get("description_length", 0)

                t_color = "#33dd88" if 50 <= t_len <= 60 else "#ffaa33" if 30 <= t_len < 50 else "#ff4455"
                d_color = "#33dd88" if 140 <= d_len <= 165 else "#ffaa33" if 80 <= d_len < 140 else "#ff4455"

                st.markdown(f"""
                <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1rem; margin-bottom:0.5rem;">
                    <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#5533ff; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.3rem;">
                        TITLE <span style="color:{t_color};">({t_len} chars)</span>
                    </div>
                    <div style="font-size:0.9rem; color:#e8e8f0;">{title}</div>
                </div>
                <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1rem;">
                    <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#5533ff; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.3rem;">
                        META DESCRIPTION <span style="color:{d_color};">({d_len} chars)</span>
                    </div>
                    <div style="font-size:0.85rem; color:#e8e8f0;">{desc}</div>
                </div>
                """, unsafe_allow_html=True)

                # H1 and headings
                if r.get("h1"):
                    st.markdown(f"""
                    <div style="margin-top:0.5rem; background:#0f0f1a; border:1px solid #1a1a2e; border-radius:6px; padding:0.7rem;">
                        <span style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#6b6b8a; text-transform:uppercase;">H1: </span>
                        <span style="font-size:0.85rem;">{r.get('h1')}</span>
                    </div>
                    """, unsafe_allow_html=True)

                if r.get("h2s"):
                    h2_list = " ".join(r["h2s"][:5])
                    st.markdown(f"<div style='font-size:0.75rem; color:#6b6b8a; margin-top:0.5rem; font-family:\"IBM Plex Mono\",monospace;'>H2: {h2_list}</div>", unsafe_allow_html=True)

                # ── Content deep audit ─────────────────────────────
                cat_audit = r.get("content_audit")
                if cat_audit:
                    st.markdown("---")
                    st.markdown("#### Deep Content Analysis")

                    stats = cat_audit.get("content_stats", {})
                    kw_cov = cat_audit.get("keyword_coverage", {})
                    topic_cov = cat_audit.get("topic_coverage", {})
                    linking = cat_audit.get("linking", {})
                    trust = cat_audit.get("trust", {})

                    # ── Score overview ──
                    s1, s2, s3, s4, s5 = st.columns(5)
                    with s1:
                        intro_w = stats.get("intro_words", 0)
                        intro_color = "#33dd88" if intro_w >= 80 else "#ffaa33" if intro_w >= 30 else "#ff4455"
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.4rem; font-weight:700; color:{intro_color};'>{intro_w}</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>INTRO WORDS</div></div>", unsafe_allow_html=True)
                    with s2:
                        bottom_w = stats.get("bottom_words", 0)
                        bottom_color = "#33dd88" if bottom_w >= 150 else "#ffaa33" if bottom_w >= 50 else "#ff4455"
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.4rem; font-weight:700; color:{bottom_color};'>{bottom_w}</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>BOTTOM WORDS</div></div>", unsafe_allow_html=True)
                    with s3:
                        tp = topic_cov.get("coverage_pct", 0)
                        tp_color = "#33dd88" if tp >= 60 else "#ffaa33" if tp >= 30 else "#ff4455"
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.4rem; font-weight:700; color:{tp_color};'>{tp:.0f}%</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>TOPIC MATCH</div></div>", unsafe_allow_html=True)
                    with s4:
                        kp = kw_cov.get("coverage_pct", 0)
                        kp_color = "#33dd88" if kp >= 60 else "#ffaa33" if kp >= 30 else "#ff4455"
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.4rem; font-weight:700; color:{kp_color};'>{kp:.0f}%</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>KW COVERAGE</div></div>", unsafe_allow_html=True)
                    with s5:
                        tpct = trust.get("trust_pct", 0)
                        t_color = "#33dd88" if tpct >= 60 else "#ffaa33" if tpct >= 30 else "#ff4455"
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.4rem; font-weight:700; color:{t_color};'>{tpct:.0f}%</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>TRUST/E-E-A-T</div></div>", unsafe_allow_html=True)

                    # ── Feature flags row ──
                    has_faq = stats.get("has_faq", False)
                    has_guide = stats.get("has_buying_guide", False)
                    faq_c = "#33dd88" if has_faq else "#ff4455"
                    guide_c = "#33dd88" if has_guide else "#ff4455"
                    bc_c = "#33dd88" if trust.get("has_breadcrumb") else "#ff4455"
                    rev_c = "#33dd88" if trust.get("has_reviews") else "#ff4455"
                    st.markdown(
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; margin:0.5rem 0; padding:0.5rem; background:#0d0d15; border-radius:4px;'>"
                        f"FAQ: <span style='color:{faq_c};'>{'OK' if has_faq else 'MISSING'}</span> &nbsp;|&nbsp; "
                        f"Buying guide: <span style='color:{guide_c};'>{'OK' if has_guide else 'MISSING'}</span> &nbsp;|&nbsp; "
                        f"Breadcrumb: <span style='color:{bc_c};'>{'OK' if trust.get('has_breadcrumb') else 'MISSING'}</span> &nbsp;|&nbsp; "
                        f"Reviews: <span style='color:{rev_c};'>{'OK' if trust.get('has_reviews') else 'MISSING'}</span> &nbsp;|&nbsp; "
                        f"H2: {stats.get('editorial_h2_count', 0)} &nbsp;|&nbsp; "
                        f"Products: {stats.get('product_count', 0)}</div>",
                        unsafe_allow_html=True
                    )

                    # ── Topic coverage detail ──
                    subtopics = topic_cov.get("subtopics", [])
                    if subtopics:
                        st.markdown(
                            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                            f"text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                            f"TOPIC CLUSTER COVERAGE ({topic_cov.get('covered_topics',0)}/{topic_cov.get('total_topics',0)} topics)</div>",
                            unsafe_allow_html=True
                        )
                        for sub in subtopics:
                            status = sub["status"]
                            if status == "covered":
                                icon, scolor = "OK", "#33dd88"
                            elif status == "partial":
                                icon, scolor = "PARTIAL", "#ffaa33"
                            else:
                                icon, scolor = "MISSING", "#ff4455"
                            queries_str = ", ".join(sub["queries"][:3])
                            if sub["query_count"] > 3:
                                queries_str += f" +{sub['query_count']-3} more"
                            st.markdown(
                                f"<div style='padding:3px 0; font-size:0.8rem;'>"
                                f"<span style='color:{scolor}; font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; font-weight:600; min-width:70px; display:inline-block;'>[{icon}]</span> "
                                f"<span style='color:#e8e8f0; font-weight:500;'>{sub['topic']}</span> "
                                f"<span style='color:#6b6b8a; font-size:0.72rem;'>({queries_str})</span></div>",
                                unsafe_allow_html=True
                            )

                    # ── KW placement quality ──
                    kw_h1 = kw_cov.get("in_h1", 0)
                    kw_h2 = kw_cov.get("in_h2", 0)
                    kw_intro = kw_cov.get("in_intro", 0)
                    st.markdown(
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#6b6b8a; margin:0.3rem 0;'>"
                        f"KW in H1: <span style='color:{'#33dd88' if kw_h1 > 0 else '#ff4455'};'>{kw_h1}</span> &nbsp; "
                        f"KW in H2: <span style='color:{'#33dd88' if kw_h2 > 0 else '#ffaa33'};'>{kw_h2}</span> &nbsp; "
                        f"KW in intro: <span style='color:{'#33dd88' if kw_intro > 0 else '#ff4455'};'>{kw_intro}</span></div>",
                        unsafe_allow_html=True
                    )

                    # ── Internal linking detail ──
                    missing_crosslinks = linking.get("missing_crosslinks", [])
                    if missing_crosslinks or linking.get("category_links", 0) < 2:
                        st.markdown(
                            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                            f"text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                            f"INTERNAL LINKING ({linking.get('total_internal',0)} links, {linking.get('category_links',0)} to categories)</div>",
                            unsafe_allow_html=True
                        )
                        if missing_crosslinks:
                            st.markdown(f"**{len(missing_crosslinks)} related pages missing link:**")
                            for ml in missing_crosslinks[:5]:
                                short = ml["url"].replace("https://", "").replace("http://", "")
                                shared = ", ".join(ml["shared_topics"][:2])
                                st.markdown(
                                    f"<div style='font-size:0.8rem; padding:2px 0;'>"
                                    f"<span style='color:#ff8888;'>Missing:</span> <code>{short}</code> "
                                    f"<span style='color:#6b6b8a;'>(shared: {shared})</span></div>",
                                    unsafe_allow_html=True
                                )

                    # ── Link fix suggestions (WP1) ──
                    link_fixes = linking.get("link_fix_suggestions", [])
                    if link_fixes:
                        st.markdown(
                            "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                            "text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                            "LINK FIX SUGGESTIONS</div>",
                            unsafe_allow_html=True
                        )
                        for lf in link_fixes[:5]:
                            pri = lf.get("priority", "medium").upper()
                            pri_color = "#ff4455" if pri == "HIGH" else "#ffaa33" if pri == "MEDIUM" else "#6b6b8a"
                            target_short = lf["target_url"].replace("https://", "").replace("http://", "")
                            placement = lf.get("placement_detail") or lf.get("placement", "bottom_text")
                            st.markdown(
                                f"<div style='background:#0d0d15; border:1px solid #1e1e2e; border-radius:6px; padding:0.6rem; margin-bottom:0.4rem; font-size:0.8rem;'>"
                                f"<span style='color:{pri_color}; font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem;'>[{pri}]</span> "
                                f"Add link to: <code>{target_short}</code><br>"
                                f"<span style='color:#6b6b8a;'>Anchor:</span> <span style='color:#33dd88;'>\"{lf['suggested_anchor']}\"</span><br>"
                                f"<span style='color:#6b6b8a;'>Place in:</span> {placement}<br>"
                                f"<span style='color:#6b6b8a;'>Reason:</span> {lf['reason']}</div>",
                                unsafe_allow_html=True
                            )

                    # ── Anchor text issues (WP1) ──
                    sem_val = linking.get("semantic_validation", {})
                    anchor_mismatches = sem_val.get("anchor_mismatches", [])
                    if anchor_mismatches:
                        st.markdown(
                            "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                            "text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                            "ANCHOR TEXT OPTIMIZATION</div>",
                            unsafe_allow_html=True
                        )
                        for am in anchor_mismatches[:5]:
                            st.markdown(
                                f"<div style='font-size:0.8rem; padding:3px 0;'>"
                                f"<code>{am['url'][:50]}</code><br>"
                                f"<span style='color:#ff8888;'>Current:</span> \"{am['current_anchor']}\" "
                                f"<span style='color:#33dd88;'>Suggested:</span> \"{am['suggested_anchor']}\"</div>",
                                unsafe_allow_html=True
                            )

                    # ── Product alignment (WP2) ──
                    prod_align = cat_audit.get("product_alignment", {})
                    if prod_align and prod_align.get("alignment_pct") is not None:
                        apct = prod_align["alignment_pct"]
                        a_color = "#33dd88" if apct >= 70 else "#ffaa33" if apct >= 40 else "#ff4455"
                        st.markdown(
                            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                            f"text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                            f"PRODUCT-CLUSTER ALIGNMENT "
                            f"<span style='color:{a_color};'>{apct:.0f}%</span> "
                            f"({prod_align.get('total_checked', 0)} products checked)</div>",
                            unsafe_allow_html=True
                        )
                        misplaced = prod_align.get("misplaced", [])
                        if misplaced:
                            for mp in misplaced[:5]:
                                st.markdown(
                                    f"<div style='font-size:0.8rem; padding:2px 0;'>"
                                    f"<span style='color:#ff8888;'>Misplaced:</span> {mp['name'][:50]} "
                                    f"<span style='color:#6b6b8a;'>({mp['reason']})</span></div>",
                                    unsafe_allow_html=True
                                )

                    # ── Trust signals detail ──
                    trust_signals_found = trust.get("signals_found", [])
                    schema_types = trust.get("schema_types", [])
                    st.markdown(
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                        f"text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                        f"TRUST & E-E-A-T ({trust.get('trust_score',0)}/{trust.get('trust_max',0)} signals)</div>",
                        unsafe_allow_html=True
                    )
                    if schema_types:
                        st.markdown(f"**Schema types:** {', '.join(schema_types)}")
                    else:
                        st.markdown("<span style='color:#ff4455;'>No structured data found</span>", unsafe_allow_html=True)
                    if trust_signals_found:
                        for sig in trust_signals_found:
                            st.markdown(f"<div style='font-size:0.8rem; color:#33dd88; padding:1px 0;'>+ {sig}</div>", unsafe_allow_html=True)
                    missing_trust = []
                    if not trust.get("has_breadcrumb"):
                        missing_trust.append("BreadcrumbList schema")
                    if not trust.get("has_reviews"):
                        missing_trust.append("Reviews/ratings")
                    if not trust.get("has_last_modified"):
                        missing_trust.append("Update date")
                    if not trust.get("has_org_schema"):
                        missing_trust.append("Organization schema")
                    for mt in missing_trust:
                        st.markdown(f"<div style='font-size:0.8rem; color:#ff4455; padding:1px 0;'>- {mt}</div>", unsafe_allow_html=True)

                    # ── E-E-A-T depth (WP3) ──
                    eeat = cat_audit.get("eeat_depth", {})
                    if eeat:
                        st.markdown(
                            "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                            "text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                            "E-E-A-T DEPTH ANALYSIS</div>",
                            unsafe_allow_html=True
                        )
                        e_cols = st.columns(3)
                        # Credibility
                        cred = eeat.get("credibility", {})
                        with e_cols[0]:
                            cp = cred.get("credibility_pct", 0)
                            c_color = "#33dd88" if cp >= 50 else "#ffaa33" if cp >= 25 else "#ff4455"
                            st.markdown(f"<div style='text-align:center;'><div style='font-size:1.2rem; font-weight:700; color:{c_color};'>{cp}%</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>CREDIBILITY</div></div>", unsafe_allow_html=True)
                        # Topical authority
                        ta = eeat.get("topical_authority", {})
                        with e_cols[1]:
                            ta_score = ta.get("authority_score", 0)
                            ta_max = ta.get("authority_max", 3)
                            pages_in = ta.get("pages_in_cluster", 0)
                            ta_color = "#33dd88" if ta_score >= 2 else "#ffaa33" if ta_score >= 1 else "#ff4455"
                            st.markdown(f"<div style='text-align:center;'><div style='font-size:1.2rem; font-weight:700; color:{ta_color};'>{ta_score}/{ta_max}</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>AUTHORITY ({pages_in} pages)</div></div>", unsafe_allow_html=True)
                        # Trust flow
                        tf = eeat.get("trust_flow", {})
                        with e_cols[2]:
                            rd = tf.get("referring_domains", 0)
                            tf_score = tf.get("trust_flow_score", 0)
                            tf_color = "#33dd88" if tf_score >= 2 else "#ffaa33" if tf_score >= 1 else "#ff4455"
                            st.markdown(f"<div style='text-align:center;'><div style='font-size:1.2rem; font-weight:700; color:{tf_color};'>{rd}</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>REFERRING DOMAINS</div></div>", unsafe_allow_html=True)

                        # Detail signals
                        all_eeat_signals = cred.get("signals", []) + ta.get("signals", []) + tf.get("signals", [])
                        for sig in all_eeat_signals:
                            st.markdown(f"<div style='font-size:0.78rem; color:#9b9bb8; padding:1px 0;'>  {sig}</div>", unsafe_allow_html=True)

                    # ── Missing keywords ──
                    missing_kws = kw_cov.get("missing", [])
                    if missing_kws:
                        kw_badges = " ".join([
                            f"<span style='background:#1a0a0a; border:1px solid #ff4455; border-radius:4px; padding:2px 6px; font-size:0.7rem; color:#ff8888; margin:2px; display:inline-block;'>{kw}</span>"
                            for kw in missing_kws[:10]
                        ])
                        st.markdown(f"<div style='margin-top:0.5rem;'><span style='font-size:0.7rem; color:#6b6b8a;'>Missing keywords:</span><br>{kw_badges}</div>", unsafe_allow_html=True)

                    # ── Recommendations ──
                    recs = cat_audit.get("recommendations", [])
                    if recs:
                        st.markdown("**Recommendations:**")
                        for rec in recs:
                            st.markdown(f"<div style='font-size:0.82rem; color:#c8b4ff; padding:2px 0;'>-> {rec}</div>", unsafe_allow_html=True)

            with right:
                st.markdown("#### Issues")
                issues = r.get("issues", [])
                if not issues:
                    st.markdown("<div style='color:#33dd88; font-size:0.85rem;'>No critical issues</div>", unsafe_allow_html=True)
                else:
                    for issue in issues:
                        st.markdown(
                            f"{issue_badge(issue['type'])} <span style='font-size:0.82rem; color:#c8b4ff;'>[{issue['field']}]</span> "
                            f"<span style='font-size:0.82rem; color:#e8e8f0;'>{issue['msg']}</span>",
                            unsafe_allow_html=True
                        )

                st.markdown("#### GSC Keywords")
                kws = r.get("target_keywords", [])
                for kw in kws:
                    st.markdown(
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.75rem; color:#c8b4ff; padding:2px 0;'>-> {kw}</div>",
                        unsafe_allow_html=True
                    )

                # Show cluster keywords if different from GSC keywords
                cluster_kws = r.get("cluster_keywords", [])
                extra_cluster = [k for k in cluster_kws if k not in kws][:5]
                if extra_cluster:
                    st.markdown("#### Cluster Keywords")
                    for kw in extra_cluster:
                        st.markdown(
                            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.75rem; color:#9b9bb8; padding:2px 0;'>-> {kw}</div>",
                            unsafe_allow_html=True
                        )

                st.markdown("#### Page Statistics")
                st.markdown(f"""
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.72rem; color:#6b6b8a; line-height:1.9;">
                    Words on page: {r.get('word_count', '?')}<br>
                    Internal links: {r.get('internal_links', '?')}<br>
                    Images w/o alt: {r.get('images_without_alt', '?')}<br>
                    Schema: {', '.join(r.get('schema_types', [])) or 'None'}<br>
                    Impressions: {r.get('impressions', 0):,}<br>
                    Clicks: {r.get('clicks', 0):,}
                </div>
                """, unsafe_allow_html=True)

                # Authority warning for high-value pages
                if "page_authority" in st.session_state:
                    auth = st.session_state["page_authority"]
                    page_auth = auth[auth["page"].str.rstrip("/").str.lower() == r["url"].rstrip("/").lower()]
                    if not page_auth.empty:
                        rd = page_auth.iloc[0].get("referring_domains", 0)
                        risk = page_auth.iloc[0].get("change_risk", "Unknown")
                        if rd > 5:
                            risk_color = "#ff4455" if risk == "HIGH" else "#ffaa33" if risk == "MEDIUM" else "#33dd88"
                            st.markdown(
                                f"<div style='margin-top:0.5rem; padding:0.5rem; background:#1a0a0a; border:1px solid {risk_color}; border-radius:6px;'>"
                                f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:{risk_color};'>BACKLINK RISK: {risk}</div>"
                                f"<div style='font-size:0.75rem; color:#e8e8f0;'>{rd} referring domains - be careful with URL changes</div></div>",
                                unsafe_allow_html=True
                            )

            # Send to content generator button
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(f"Generate optimized content for this page", key=f"gen_{r['url']}"):
                st.session_state["generate_for_url"] = r["url"]
                st.session_state["selected_audit"] = r
                st.info("-> Go to Content Generator to generate content")
