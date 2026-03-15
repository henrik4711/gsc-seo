"""
Page Auditor
Scrapes landing pages, extracts meta data, evaluates quality vs. keywords
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


def render():
    st.markdown("## 🔬 Page Auditor")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:2rem;'>Analysér meta title, description og indhold på udvalgte landingpages</p>",
        unsafe_allow_html=True
    )
    
    if "gsc_data" not in st.session_state:
        st.warning("⚠️ Hent GSC data først (Setup & Connect)")
        return
    
    df = st.session_state["gsc_data"]
    
    # ── URL Input ─────────────────────────────────────────────────
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Pre-fill from audit queue if available
        default_urls = "\n".join(st.session_state.get("audit_queue", []))
        
        if not default_urls and "ctr_gaps" in st.session_state:
            # Auto-suggest top pages from CTR analysis
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
            "URLs til analyse (én per linje)",
            value=default_urls,
            height=150,
            help="Indsæt de URLs du vil auditere"
        )
    
    with col2:
        st.markdown("#### Indstillinger")
        scrape_live = st.toggle("Scrape live sider", value=True, help="Hent nuværende indhold fra websitet")
        show_keywords = st.number_input("Top N keywords per side", min_value=3, max_value=15, value=5)
        
        st.markdown("<br>", unsafe_allow_html=True)
        run_audit = st.button("🔬 Kør Audit", type="primary", use_container_width=True)
    
    urls = [u.strip() for u in urls_input.split("\n") if u.strip()]
    
    if not urls:
        st.info("Indsæt URLs ovenfor for at starte audit")
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
            
            result = {
                "url": url,
                "target_keywords": target_keywords,
                "lost_clicks_estimate": page_queries["lost_clicks_estimate"].sum() if "lost_clicks_estimate" in page_queries.columns else 0,
                "position": page_queries["position"].mean() if len(page_queries) > 0 else None,
                "ctr_gap_pct": page_queries["ctr_gap_pct"].mean() if "ctr_gap_pct" in page_queries.columns and len(page_queries) > 0 else 0,
                "impressions": page_queries["impressions"].sum(),
                "clicks": page_queries["clicks"].sum(),
            }
            
            if scrape_live:
                from utils.page_scraper import scrape_page, evaluate_meta
                page_data = scrape_page(url)
                result.update(page_data)
                
                if page_data["success"]:
                    meta_eval = evaluate_meta(page_data, target_keywords)
                    result["meta_score"] = meta_eval["score"]
                    result["issues"] = meta_eval["issues"]
                    result["meta_eval"] = meta_eval
                else:
                    result["meta_score"] = None
                    result["issues"] = [{"type": "critical", "field": "url", "msg": f"Kunne ikke hente siden: {page_data.get('error')}"}]
            else:
                result["success"] = True
                result["title"] = "(ikke hentet - scraping deaktiveret)"
                result["meta_description"] = "(ikke hentet)"
                result["meta_score"] = None
                result["issues"] = []
            
            audit_results.append(result)
            progress.progress((i + 1) / len(urls))
            time.sleep(0.3)  # Be polite
        
        st.session_state["audit_results"] = audit_results
        status_text.empty()
        progress.empty()
        st.success(f"✅ Audit komplet for {len(audit_results)} sider")
    
    # ── Display Results ───────────────────────────────────────────
    if "audit_results" not in st.session_state:
        return
    
    results = st.session_state["audit_results"]
    
    # Summary table
    st.markdown("### Oversigt")
    
    summary_rows = []
    for r in results:
        summary_rows.append({
            "Side": r["url"].replace("https://mshop.se", ""),
            "Meta Score": r.get("meta_score"),
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
        score = r.get("meta_score")
        score_html = score_badge(score) if score is not None else "<span style='color:#6b6b8a'>N/A</span>"
        lost = r.get("lost_clicks_estimate", 0)
        
        with st.expander(f"📄 {url_short}   |   Meta: {score or '?'}/100   |   Tabte klik: {lost:,}"):
            
            left, right = st.columns([3, 2])
            
            with left:
                # Current meta
                st.markdown("#### Nuværende Meta")
                
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
                    h2_list = " · ".join(r["h2s"][:5])
                    st.markdown(f"<div style='font-size:0.75rem; color:#6b6b8a; margin-top:0.5rem; font-family:\"IBM Plex Mono\",monospace;'>H2: {h2_list}</div>", unsafe_allow_html=True)
            
            with right:
                st.markdown("#### Issues")
                issues = r.get("issues", [])
                if not issues:
                    st.markdown("<div style='color:#33dd88; font-size:0.85rem;'>✅ Ingen kritiske issues</div>", unsafe_allow_html=True)
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
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.75rem; color:#c8b4ff; padding:2px 0;'>→ {kw}</div>",
                        unsafe_allow_html=True
                    )
                
                st.markdown("#### Side-statistik")
                st.markdown(f"""
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.72rem; color:#6b6b8a; line-height:1.9;">
                    Ord på siden: {r.get('word_count', '?')}<br>
                    Interne links: {r.get('internal_links', '?')}<br>
                    Billeder u/alt: {r.get('images_without_alt', '?')}<br>
                    Schema: {', '.join(r.get('schema_types', [])) or 'Ingen'}<br>
                    Impressions: {r.get('impressions', 0):,}<br>
                    Klik: {r.get('clicks', 0):,}
                </div>
                """, unsafe_allow_html=True)
            
            # Send to content generator button
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(f"✍️ Generer optimeret indhold for denne side", key=f"gen_{r['url']}"):
                st.session_state["generate_for_url"] = r["url"]
                st.session_state["selected_audit"] = r
                st.info("→ Gå til Content Generator for at generere indhold")
