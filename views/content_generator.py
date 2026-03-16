"""
Content Generator
AI-powered generation of meta title, description, and landing page text
"""

import streamlit as st
import json
from config import get_anthropic_key, has_anthropic_key


def render():
    st.markdown("## Content Generator")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:2rem;'>Generer AI-optimerede meta-tekster og landingpage-indhold</p>",
        unsafe_allow_html=True
    )

    if not has_anthropic_key():
        st.warning("Gaa til **1. Setup & Connect** og tilfoej Anthropic API-noegle (eller saet ANTHROPIC_API_KEY i Railway)")
        return

    if "gsc_data" not in st.session_state:
        st.warning("Gaa til **1. Setup & Connect** og forbind GSC foerst.")
        return
    
    df = st.session_state["gsc_data"]
    audit_results = st.session_state.get("audit_results", [])
    
    # ── URL Selection ─────────────────────────────────────────────
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Determine URL options
        if audit_results:
            url_options = [r["url"] for r in audit_results]
        elif "ctr_gaps" in st.session_state:
            url_options = (
                st.session_state["ctr_gaps"]
                .groupby("page")["lost_clicks_estimate"]
                .sum()
                .sort_values(ascending=False)
                .head(20)
                .index.tolist()
            )
        else:
            url_options = df["page"].unique().tolist()[:20]
        
        # Pre-select if coming from auditor
        default_idx = 0
        preselected = st.session_state.get("generate_for_url")
        if preselected and preselected in url_options:
            default_idx = url_options.index(preselected)
        
        selected_url = st.selectbox("Vælg URL", url_options, index=default_idx)
    
    with col2:
        n_variants = st.number_input("Meta-varianter", min_value=1, max_value=5, value=3)
    
    # Load page data from audit if available
    page_data = {}
    selected_audit = next((r for r in audit_results if r["url"] == selected_url), None)
    if selected_audit:
        page_data = selected_audit
    
    # Keywords for selected URL
    page_queries = df[df["page"] == selected_url].sort_values("impressions", ascending=False)
    auto_keywords = page_queries["query"].head(10).tolist()
    
    # GSC keyword display
    if auto_keywords:
        kw_html = " ".join([
            f"<span style='background:#12121f; border:1px solid #5533ff; border-radius:4px; padding:2px 8px; font-family:\"IBM Plex Mono\",monospace; font-size:0.72rem; color:#c8b4ff; margin:2px; display:inline-block;'>{kw}</span>"
            for kw in auto_keywords
        ])
        st.markdown(f"**GSC Keywords for denne side:**<br>{kw_html}", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
    
    # Custom keywords override
    custom_kw = st.text_input(
        "Tilpas keywords (komma-separeret, overskriver auto)",
        placeholder="f.eks. vibrator, vibratorer billiga, bästa vibratorn",
        help="Lad tom for at bruge GSC-keywords automatisk"
    )
    
    target_keywords = (
        [k.strip() for k in custom_kw.split(",") if k.strip()]
        if custom_kw else auto_keywords
    )
    
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")
    
    # ── Current Meta Preview ──────────────────────────────────────
    if page_data.get("title") or page_data.get("meta_description"):
        with st.expander("📄 Nuværende meta (fra audit)", expanded=False):
            st.markdown(f"**Title ({page_data.get('title_length',0)} tegn):** {page_data.get('title','–')}")
            st.markdown(f"**Description ({page_data.get('description_length',0)} tegn):** {page_data.get('meta_description','–')}")
    
    st.markdown("---")
    
    # ── Generation Controls ───────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["🏷️ META TITLE + DESCRIPTION", "📝 KEYWORD GAP ANALYSE", "📄 LANDINGPAGE TEKST"])
    
    with tab1:
        if st.button("🤖 Generer meta-forslag", type="primary", key="gen_meta"):
            if not target_keywords:
                st.warning("Ingen keywords tilgængelige for denne side")
                return
            
            with st.spinner(f"Claude genererer {n_variants} meta-varianter..."):
                try:
                    from utils.ai_generator import get_client, generate_meta_suggestions
                    client = get_client(get_anthropic_key())
                    
                    # Ensure page_data has url
                    pdata = dict(page_data)
                    pdata["url"] = selected_url
                    
                    result = generate_meta_suggestions(
                        client, pdata, target_keywords, site_context, language, n_variants
                    )
                    
                    if "generated_content" not in st.session_state:
                        st.session_state["generated_content"] = {}
                    st.session_state["generated_content"][selected_url] = st.session_state["generated_content"].get(selected_url, {})
                    st.session_state["generated_content"][selected_url]["meta"] = result
                    
                except Exception as e:
                    st.error(f"❌ AI fejl: {e}")
        
        # Display meta results
        meta_result = st.session_state.get("generated_content", {}).get(selected_url, {}).get("meta")
        
        if meta_result:
            st.markdown(f"""
            <div style="background:#0d0d15; border-left:3px solid #5533ff; padding:1rem; border-radius:0 6px 6px 0; margin-bottom:1rem;">
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#5533ff; text-transform:uppercase; margin-bottom:0.4rem;">AI ANALYSE</div>
                <div style="font-size:0.85rem; color:#c8b4ff;">{meta_result.get('analysis','')}</div>
            </div>
            """, unsafe_allow_html=True)
            
            for i, variant in enumerate(meta_result.get("variants", []), 1):
                title = variant.get("title", "")
                desc = variant.get("description", "")
                t_len = len(title)
                d_len = len(desc)
                t_color = "#33dd88" if 50 <= t_len <= 60 else "#ffaa33" if t_len > 0 else "#ff4455"
                d_color = "#33dd88" if 140 <= d_len <= 165 else "#ffaa33" if d_len > 0 else "#ff4455"
                strategy = variant.get("strategy", "")
                
                st.markdown(f"""
                <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1.2rem; margin-bottom:1rem;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.8rem;">
                        <span style="font-family:'Syne',sans-serif; font-weight:700; font-size:1rem; color:#c8b4ff;">Variant {i}</span>
                        <span style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#6b6b8a; font-style:italic;">{strategy}</span>
                    </div>
                    <div style="margin-bottom:0.6rem;">
                        <span style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:{t_color}; text-transform:uppercase;">TITLE · {t_len} tegn</span><br>
                        <span style="font-size:0.95rem; color:#e8e8f0; font-weight:500;">{title}</span>
                    </div>
                    <div>
                        <span style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:{d_color}; text-transform:uppercase;">DESCRIPTION · {d_len} tegn</span><br>
                        <span style="font-size:0.85rem; color:#b8b8d0;">{desc}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # Copy-ready export
            with st.expander("📋 Copy-ready tekst"):
                for i, v in enumerate(meta_result.get("variants", []), 1):
                    st.text(f"=== VARIANT {i} ===")
                    st.text(f"Title: {v.get('title','')}")
                    st.text(f"Description: {v.get('description','')}")
                    st.text("")
    
    with tab2:
        if st.button("🔍 Analysér keyword gaps", type="primary", key="gen_gaps"):
            if not page_data.get("body_text"):
                st.warning("⚠️ Ingen side-indhold tilgængeligt. Kør Page Auditor med scraping aktiveret først.")
                return
            
            with st.spinner("Analyserer keyword-dækning..."):
                try:
                    from utils.ai_generator import get_client, generate_content_audit
                    client = get_client(get_anthropic_key())
                    
                    result = generate_content_audit(
                        client, page_data, target_keywords,
                        page_queries["query"].tolist()
                    )
                    
                    if "generated_content" not in st.session_state:
                        st.session_state["generated_content"] = {}
                    st.session_state["generated_content"].setdefault(selected_url, {})["gap_analysis"] = result
                    
                except Exception as e:
                    st.error(f"❌ Fejl: {e}")
        
        gap_result = st.session_state.get("generated_content", {}).get(selected_url, {}).get("gap_analysis")
        
        if gap_result:
            # Summary
            score = gap_result.get("overall_score", 0)
            score_color = "#33dd88" if score >= 70 else "#ffaa33" if score >= 40 else "#ff4455"
            
            c1, c2 = st.columns([1, 3])
            with c1:
                st.markdown(f"""
                <div style="text-align:center; padding:1rem; background:#12121f; border-radius:8px; border:1px solid #1e1e2e;">
                    <div style="font-size:2.5rem; font-family:'Syne',sans-serif; font-weight:800; color:{score_color};">{score}</div>
                    <div style="font-size:0.7rem; font-family:'IBM Plex Mono',monospace; color:#6b6b8a; text-transform:uppercase;">Content Score</div>
                </div>
                """, unsafe_allow_html=True)
            with c2:
                st.markdown(f"**Sammenfatning:** {gap_result.get('summary','')}")
                if gap_result.get("thin_content"):
                    st.error("⚠️ TYNDT INDHOLD - Siden har for lidt relevant tekst")
            
            # Keyword coverage table
            st.markdown("#### Keyword-dækning")
            kw_cov = gap_result.get("keyword_coverage", [])
            if kw_cov:
                cov_df = pd.DataFrame(kw_cov)
                cov_df["Status"] = cov_df["present"].map({True: "✅ Til stede", False: "❌ Mangler"})
                st.dataframe(
                    cov_df[["keyword", "Status", "context"]].rename(columns={
                        "keyword": "Keyword", "context": "Detaljer"
                    }),
                    use_container_width=True, hide_index=True
                )
            
            col_l, col_r = st.columns(2)
            with col_l:
                st.markdown("#### Manglende emner")
                for topic in gap_result.get("missing_topics", []):
                    st.markdown(f"<div style='color:#ff4455; font-size:0.85rem; padding:2px 0;'>❌ {topic}</div>", unsafe_allow_html=True)
            
            with col_r:
                st.markdown("#### Anbefalet struktur")
                rec = gap_result.get("recommended_structure", {})
                if rec.get("suggested_h1"):
                    st.markdown(f"**Foreslået H1:** {rec['suggested_h1']}")
                for sec in rec.get("suggested_sections", []):
                    st.markdown(f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.8rem; color:#c8b4ff; padding:2px 0;'>→ {sec}</div>", unsafe_allow_html=True)
        
        import pandas as pd
    
    with tab3:
        tone = st.selectbox(
            "Tone of voice",
            ["Professionel men tilgængelig", "Discret og respektfuld", "Energisk og direkte", "Informativ og guidende"],
            index=0
        )
        
        if st.button("📝 Generer landingpage tekst", type="primary", key="gen_content"):
            with st.spinner("Claude skriver optimeret indhold... (ca. 30 sek)"):
                try:
                    from utils.ai_generator import get_client, generate_landing_page_text
                    client = get_client(get_anthropic_key())
                    
                    pdata = dict(page_data)
                    pdata["url"] = selected_url
                    
                    result = generate_landing_page_text(
                        client, pdata, target_keywords,
                        page_queries["query"].tolist(),
                        site_context, language, tone
                    )
                    
                    if "generated_content" not in st.session_state:
                        st.session_state["generated_content"] = {}
                    st.session_state["generated_content"].setdefault(selected_url, {})["landing_text"] = result
                    
                except Exception as e:
                    st.error(f"❌ Fejl: {e}")
        
        lp_result = st.session_state.get("generated_content", {}).get(selected_url, {}).get("landing_text")
        
        if lp_result:
            # Display formatted content
            if lp_result.get("intro_paragraph"):
                st.markdown("#### Intro-tekst")
                st.markdown(f"""
                <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1rem; line-height:1.7; color:#e8e8f0;">
                    {lp_result['intro_paragraph']}
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown("#### Sektioner")
            for sec in lp_result.get("sections", []):
                with st.expander(f"H2: {sec.get('h2','')}", expanded=True):
                    st.markdown(sec.get("content", ""))
                    for sub in sec.get("h3_subsections", []):
                        st.markdown(f"**{sub.get('h3','')}**")
                        st.markdown(sub.get("content", ""))
            
            if lp_result.get("buying_guide_snippet"):
                st.markdown("#### Købe-guide")
                st.markdown(lp_result["buying_guide_snippet"])
            
            if lp_result.get("faq_items"):
                st.markdown("#### FAQ")
                for faq in lp_result["faq_items"]:
                    with st.expander(f"❓ {faq.get('question','')}"):
                        st.markdown(faq.get("answer", ""))
            
            if lp_result.get("seo_notes"):
                st.info(f"📌 **SEO noter til redaktøren:** {lp_result['seo_notes']}")
            
            # Full export
            with st.expander("📋 Eksportér alt indhold"):
                full_text = f"# {selected_url}\n\n"
                full_text += f"## Intro\n{lp_result.get('intro_paragraph','')}\n\n"
                for sec in lp_result.get("sections", []):
                    full_text += f"## {sec.get('h2','')}\n{sec.get('content','')}\n\n"
                    for sub in sec.get("h3_subsections", []):
                        full_text += f"### {sub.get('h3','')}\n{sub.get('content','')}\n\n"
                if lp_result.get("buying_guide_snippet"):
                    full_text += f"## KøbeGuide\n{lp_result['buying_guide_snippet']}\n\n"
                
                st.text_area("Markdown format", full_text, height=300)
                st.download_button(
                    "⬇️ Download tekst (MD)",
                    full_text.encode("utf-8"),
                    f"content_{selected_url.split('/')[-2]}.md",
                    "text/markdown"
                )
