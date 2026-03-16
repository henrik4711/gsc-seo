"""
Page Auditor
Scrapes landing pages, extracts meta data, evaluates quality vs. keywords.
Now with page-type detection and deep category analysis.
"""

import streamlit as st
import pandas as pd
import time


def score_badge(score: int) -> str:
    if score >= 80:
        color, label = "#33dd88", "God"
    elif score >= 50:
        color, label = "#ffaa33", "Mangler"
    else:
        color, label = "#ff4455", "Kritisk"
    return f"<span style='color:{color}; font-family:\"IBM Plex Mono\",monospace; font-weight:600;'>{score}/100 · {label}</span>"


def issue_badge(issue_type: str) -> str:
    colors = {"critical": "#ff4455", "warn": "#ffaa33", "info": "#6b6baa"}
    labels = {"critical": "KRITISK", "warn": "ADVARSEL", "info": "INFO"}
    color = colors.get(issue_type, "#6b6b8a")
    label = labels.get(issue_type, issue_type.upper())
    return f"<span style='color:{color}; font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; font-weight:600;'>[{label}]</span>"


def severity_badge(severity: str) -> str:
    colors = {"critical": "#ff4455", "warn": "#ffaa33", "info": "#6b6baa"}
    labels = {"critical": "KRITISK", "warn": "ADVARSEL", "info": "INFO"}
    color = colors.get(severity, "#6b6b8a")
    label = labels.get(severity, severity.upper())
    return f"<span style='color:{color}; font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; font-weight:600;'>[{label}]</span>"


PAGE_TYPE_LABELS = {
    "category": ("KATEGORI", "#c8b4ff"),
    "product": ("PRODUKT", "#33dd88"),
    "blog": ("BLOG/GUIDE", "#ffaa33"),
    "unknown": ("UKENDT", "#6b6b8a"),
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
    return list(set(keywords))[:30]


def render():
    st.markdown("## Page Auditor")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:2rem;'>Analysér meta title, description og indhold - med dybdeanalyse af kategorisider</p>",
        unsafe_allow_html=True
    )

    if "gsc_data" not in st.session_state:
        st.warning("Gaa til **1. Setup & Connect** og forbind GSC foerst.")
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
            "URLs til analyse (en per linje)",
            value=default_urls,
            height=150,
            help="Indsaet de URLs du vil auditere"
        )

    with col2:
        st.markdown("#### Indstillinger")
        scrape_live = st.toggle("Scrape live sider", value=True, help="Hent nuvaerende indhold fra websitet")
        deep_category = st.toggle("Dyb kategori-analyse", value=True, help="Separerer redaktionelt indhold fra produktgrid paa kategorisider")
        show_keywords = st.number_input("Top N keywords per side", min_value=3, max_value=15, value=5)

        st.markdown("<br>", unsafe_allow_html=True)
        run_audit = st.button("Koer Audit", type="primary", use_container_width=True)

    urls = [u.strip() for u in urls_input.split("\n") if u.strip()]

    if not urls:
        st.info("Indsaet URLs ovenfor for at starte audit")
        return

    # ── Run Audit ─────────────────────────────────────────────────
    if run_audit:
        audit_results = []
        progress = st.progress(0)
        status_text = st.empty()

        for i, url in enumerate(urls):
            status_text.markdown(
                f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.8rem; color:#c8b4ff;'>Analyserer: {url}</div>",
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

                    # Category content audit (when applicable)
                    if result.get("page_type") == "category" and deep_category:
                        cat_audit = audit_category_content(
                            result, cluster_keywords, target_keywords
                        )
                        result["content_score"] = cat_audit["score"]
                        result["content_audit"] = cat_audit
                        # Merge category issues into main issues
                        for issue in cat_audit.get("issues", []):
                            result["issues"].append({
                                "type": issue["severity"],
                                "field": issue["area"],
                                "msg": issue["msg"],
                            })
                else:
                    result["meta_score"] = None
                    result["issues"] = [{"type": "critical", "field": "url", "msg": f"Kunne ikke hente siden: {result.get('error', page_data.get('error'))}"}]
            else:
                result["success"] = True
                result["title"] = "(ikke hentet - scraping deaktiveret)"
                result["meta_description"] = "(ikke hentet)"
                result["meta_score"] = None
                result["page_type"] = "unknown"
                result["issues"] = []

            audit_results.append(result)
            progress.progress((i + 1) / len(urls))
            time.sleep(0.3)

        st.session_state["audit_results"] = audit_results
        status_text.empty()
        progress.empty()
        st.success(f"Audit komplet for {len(audit_results)} sider")
    
    # ── Display Results ───────────────────────────────────────────
    if "audit_results" not in st.session_state:
        return
    
    results = st.session_state["audit_results"]
    
    # Summary table
    st.markdown("### Oversigt")

    summary_rows = []
    for r in results:
        ptype = r.get("page_type", "unknown")
        label, _ = PAGE_TYPE_LABELS.get(ptype, ("?", "#6b6b8a"))
        summary_rows.append({
            "Side": r["url"].replace("https://mshop.se", ""),
            "Type": label,
            "Meta Score": r.get("meta_score"),
            "Content Score": r.get("content_score"),
            "Title": (r.get("title") or "")[:60],
            "Title Lgd": r.get("title_length", 0),
            "Desc Lgd": r.get("description_length", 0),
            "Tabte klik": r.get("lost_clicks_estimate", 0),
            "Top keywords": ", ".join(r.get("target_keywords", [])[:3]),
        })

    summary_df = pd.DataFrame(summary_rows)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Detailed per-page view
    st.markdown("### Detaljeret Audit")
    
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
        expander_label += f"  |  Tabte klik: {lost:,}"

        with st.expander(expander_label):

            # Page type badge
            st.markdown(
                f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:{type_color}; "
                f"background:#0d0d15; display:inline-block; padding:3px 10px; border:1px solid {type_color}; "
                f"border-radius:4px; margin-bottom:1rem;'>{type_label} SIDE</div>",
                unsafe_allow_html=True
            )

            left, right = st.columns([3, 2])

            with left:
                # Current meta
                st.markdown("#### Nuvaerende Meta")

                title = r.get("title") or "_(ikke fundet)_"
                desc = r.get("meta_description") or "_(ikke fundet)_"
                t_len = r.get("title_length", 0)
                d_len = r.get("description_length", 0)

                t_color = "#33dd88" if 50 <= t_len <= 60 else "#ffaa33" if 30 <= t_len < 50 else "#ff4455"
                d_color = "#33dd88" if 140 <= d_len <= 165 else "#ffaa33" if 80 <= d_len < 140 else "#ff4455"

                st.markdown(f"""
                <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1rem; margin-bottom:0.5rem;">
                    <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#5533ff; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.3rem;">
                        TITLE <span style="color:{t_color};">({t_len} tegn)</span>
                    </div>
                    <div style="font-size:0.9rem; color:#e8e8f0;">{title}</div>
                </div>
                <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1rem;">
                    <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#5533ff; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.3rem;">
                        META DESCRIPTION <span style="color:{d_color};">({d_len} tegn)</span>
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

                # ── Category-specific content audit ────────────────
                cat_audit = r.get("content_audit")
                if cat_audit:
                    st.markdown("---")
                    st.markdown("#### Kategori-indholdsanalyse")

                    stats = cat_audit.get("content_stats", {})
                    kw_cov = cat_audit.get("keyword_coverage", {})

                    # Content stats
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        intro_w = stats.get("intro_words", 0)
                        intro_color = "#33dd88" if intro_w >= 80 else "#ffaa33" if intro_w >= 30 else "#ff4455"
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.5rem; font-weight:700; color:{intro_color};'>{intro_w}</div><div style='font-size:0.65rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>INTRO ORD</div></div>", unsafe_allow_html=True)
                    with c2:
                        bottom_w = stats.get("bottom_words", 0)
                        bottom_color = "#33dd88" if bottom_w >= 150 else "#ffaa33" if bottom_w >= 50 else "#ff4455"
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.5rem; font-weight:700; color:{bottom_color};'>{bottom_w}</div><div style='font-size:0.65rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>BUND ORD</div></div>", unsafe_allow_html=True)
                    with c3:
                        cov_pct = kw_cov.get("coverage_pct", 0)
                        cov_color = "#33dd88" if cov_pct >= 60 else "#ffaa33" if cov_pct >= 30 else "#ff4455"
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.5rem; font-weight:700; color:{cov_color};'>{cov_pct:.0f}%</div><div style='font-size:0.65rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>KW DAEKNING</div></div>", unsafe_allow_html=True)
                    with c4:
                        prod_count = stats.get("product_count", 0)
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.5rem; font-weight:700; color:#c8b4ff;'>{prod_count}</div><div style='font-size:0.65rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>PRODUKTER</div></div>", unsafe_allow_html=True)

                    # Feature flags
                    has_faq = stats.get("has_faq", False)
                    has_guide = stats.get("has_buying_guide", False)
                    faq_icon = "OK" if has_faq else "MANGLER"
                    faq_color = "#33dd88" if has_faq else "#ff4455"
                    guide_icon = "OK" if has_guide else "MANGLER"
                    guide_color = "#33dd88" if has_guide else "#ff4455"
                    st.markdown(
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.72rem; margin-top:0.5rem;'>"
                        f"FAQ: <span style='color:{faq_color};'>{faq_icon}</span> &nbsp; "
                        f"Koepguide: <span style='color:{guide_color};'>{guide_icon}</span> &nbsp; "
                        f"H2 sektioner: {stats.get('editorial_h2_count', 0)}</div>",
                        unsafe_allow_html=True
                    )

                    # Missing keywords
                    missing_kws = kw_cov.get("missing", [])
                    if missing_kws:
                        kw_badges = " ".join([
                            f"<span style='background:#1a0a0a; border:1px solid #ff4455; border-radius:4px; padding:2px 6px; font-size:0.7rem; color:#ff8888; margin:2px; display:inline-block;'>{kw}</span>"
                            for kw in missing_kws[:10]
                        ])
                        st.markdown(f"<div style='margin-top:0.5rem;'><span style='font-size:0.7rem; color:#6b6b8a;'>Manglende keywords:</span><br>{kw_badges}</div>", unsafe_allow_html=True)

                    # Recommendations
                    recs = cat_audit.get("recommendations", [])
                    if recs:
                        st.markdown("**Anbefalinger:**")
                        for rec in recs:
                            st.markdown(f"<div style='font-size:0.82rem; color:#c8b4ff; padding:2px 0;'>-> {rec}</div>", unsafe_allow_html=True)

            with right:
                st.markdown("#### Issues")
                issues = r.get("issues", [])
                if not issues:
                    st.markdown("<div style='color:#33dd88; font-size:0.85rem;'>Ingen kritiske issues</div>", unsafe_allow_html=True)
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

                st.markdown("#### Side-statistik")
                st.markdown(f"""
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.72rem; color:#6b6b8a; line-height:1.9;">
                    Ord paa siden: {r.get('word_count', '?')}<br>
                    Interne links: {r.get('internal_links', '?')}<br>
                    Billeder u/alt: {r.get('images_without_alt', '?')}<br>
                    Schema: {', '.join(r.get('schema_types', [])) or 'Ingen'}<br>
                    Impressions: {r.get('impressions', 0):,}<br>
                    Klik: {r.get('clicks', 0):,}
                </div>
                """, unsafe_allow_html=True)

                # Authority warning for high-value pages
                if "page_authority" in st.session_state:
                    auth = st.session_state["page_authority"]
                    page_auth = auth[auth["page"].str.rstrip("/").str.lower() == r["url"].rstrip("/").lower()]
                    if not page_auth.empty:
                        rd = page_auth.iloc[0].get("referring_domains", 0)
                        risk = page_auth.iloc[0].get("change_risk", "Ukendt")
                        if rd > 5:
                            risk_color = "#ff4455" if risk == "HIGH" else "#ffaa33" if risk == "MEDIUM" else "#33dd88"
                            st.markdown(
                                f"<div style='margin-top:0.5rem; padding:0.5rem; background:#1a0a0a; border:1px solid {risk_color}; border-radius:6px;'>"
                                f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:{risk_color};'>BACKLINK RISIKO: {risk}</div>"
                                f"<div style='font-size:0.75rem; color:#e8e8f0;'>{rd} referring domains - vaer forsigtig med URL-aendringer</div></div>",
                                unsafe_allow_html=True
                            )

            # Send to content generator button
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(f"Generer optimeret indhold for denne side", key=f"gen_{r['url']}"):
                st.session_state["generate_for_url"] = r["url"]
                st.session_state["selected_audit"] = r
                st.info("-> Gaa til Content Generator for at generere indhold")
