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
        "<p style='color:#6b6b8a; margin-bottom:2rem;'>Generate AI-optimized meta texts and landing page content</p>",
        unsafe_allow_html=True
    )

    if not has_anthropic_key():
        st.warning("Go to **1. Setup & Connect** and add Anthropic API key (or set ANTHROPIC_API_KEY in Railway)")
        return

    if "gsc_data" not in st.session_state:
        st.warning("Go to **1. Setup & Connect** and connect GSC first.")
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

        selected_url = st.selectbox("Select URL", url_options, index=default_idx)

    with col2:
        n_variants = st.number_input("Meta variants", min_value=1, max_value=5, value=3)

    # Load page data from audit if available
    page_data = {}
    from utils.ui_helpers import normalize_url as _nu
    selected_audit = next((r for r in audit_results if _nu(r["url"]) == _nu(selected_url)), None)
    if selected_audit:
        page_data = selected_audit

    # Show page type if known
    page_type = page_data.get("page_type", "unknown")
    if page_type != "unknown":
        type_labels = {"category": ("CATEGORY", "#c8b4ff"), "product": ("PRODUCT", "#33dd88"), "blog": ("BLOG/GUIDE", "#ffaa33")}
        label, color = type_labels.get(page_type, ("UNKNOWN", "#6b6b8a"))
        st.markdown(
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:{color}; "
            f"background:#0d0d15; padding:3px 10px; border:1px solid {color}; border-radius:4px;'>{label} PAGE</span>",
            unsafe_allow_html=True
        )
        if page_type == "category":
            cat_audit = page_data.get("content_audit")
            if cat_audit:
                cov = cat_audit.get("keyword_coverage", {}).get("coverage_pct", 0)
                ed_words = cat_audit.get("content_stats", {}).get("total_editorial", 0)
                st.markdown(
                    f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.72rem; color:#6b6b8a; margin-top:0.3rem;'>"
                    f"Editorial: {ed_words} words | KW coverage: {cov:.0f}% | "
                    f"FAQ: {'OK' if cat_audit.get('content_stats',{}).get('has_faq') else 'Missing'} | "
                    f"Guide: {'OK' if cat_audit.get('content_stats',{}).get('has_buying_guide') else 'Missing'}</div>",
                    unsafe_allow_html=True
                )

    # Keywords for selected URL — filter out brand keywords
    page_queries = df[df["page"] == selected_url].sort_values("impressions", ascending=False)

    # Detect brand keywords (appear on 30%+ of pages)
    if "_brand_keywords" not in st.session_state:
        total_pages = df["page"].nunique()
        kw_page_counts = df.groupby("query")["page"].nunique()
        st.session_state["_brand_keywords"] = set(kw_page_counts[kw_page_counts >= total_pages * 0.3].index)
    brand_kws = st.session_state["_brand_keywords"]

    non_brand = page_queries[~page_queries["query"].isin(brand_kws)]
    auto_keywords = non_brand["query"].head(10).tolist()

    # GSC keyword display
    if auto_keywords:
        kw_html = " ".join([
            f"<span style='background:#12121f; border:1px solid #5533ff; border-radius:4px; padding:2px 8px; font-family:\"IBM Plex Mono\",monospace; font-size:0.72rem; color:#c8b4ff; margin:2px; display:inline-block;'>{kw}</span>"
            for kw in auto_keywords
        ])
        st.markdown(f"**GSC Keywords for this page:**<br>{kw_html}", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    # Custom keywords override
    custom_kw = st.text_input(
        "Custom keywords (comma-separated, overrides auto)",
        placeholder="e.g. wireless headphones, best budget laptop, running shoes",
        help="Leave empty to use GSC keywords automatically"
    )

    target_keywords = (
        [k.strip() for k in custom_kw.split(",") if k.strip()]
        if custom_kw else auto_keywords
    )

    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")

    # ── Current Meta Preview ──────────────────────────────────────
    if page_data.get("title") or page_data.get("meta_description"):
        with st.expander("Current meta (from audit)", expanded=False):
            st.markdown(f"**Title ({page_data.get('title_length',0)} chars):** {page_data.get('title','–')}")
            st.markdown(f"**Description ({page_data.get('description_length',0)} chars):** {page_data.get('meta_description','–')}")

    st.markdown("---")

    # ── Generation Controls ───────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["🏷️ META TITLE + DESCRIPTION", "📝 KEYWORD GAP ANALYSIS", "📄 LANDING PAGE TEXT"])

    with tab1:
        if st.button("🤖 Generate meta suggestions", type="primary", key="gen_meta"):
            if not target_keywords:
                st.warning("No keywords available for this page")
                return

            with st.spinner(f"Claude generating {n_variants} meta variants..."):
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
                    st.error(f"❌ Error: {e}")

        # Display meta results
        meta_result = st.session_state.get("generated_content", {}).get(selected_url, {}).get("meta")

        if meta_result:
            st.markdown(f"""
            <div style="background:#0d0d15; border-left:3px solid #5533ff; padding:1rem; border-radius:0 6px 6px 0; margin-bottom:1rem;">
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#5533ff; text-transform:uppercase; margin-bottom:0.4rem;">AI ANALYSIS</div>
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
                        <span style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:{t_color}; text-transform:uppercase;">TITLE · {t_len} chars</span><br>
                        <span style="font-size:0.95rem; color:#e8e8f0; font-weight:500;">{title}</span>
                    </div>
                    <div>
                        <span style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:{d_color}; text-transform:uppercase;">DESCRIPTION · {d_len} chars</span><br>
                        <span style="font-size:0.85rem; color:#b8b8d0;">{desc}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # Copy-ready export
            with st.expander("📋 Copy-ready text"):
                for i, v in enumerate(meta_result.get("variants", []), 1):
                    st.text(f"=== VARIANT {i} ===")
                    st.text(f"Title: {v.get('title','')}")
                    st.text(f"Description: {v.get('description','')}")
                    st.text("")

    with tab2:
        if st.button("🔍 Analyze keyword gaps", type="primary", key="gen_gaps"):
            if not page_data.get("body_text"):
                st.warning("⚠️ No page content available. Run Page Auditor with scraping enabled first.")
                return

            with st.spinner("Analyzing keyword coverage..."):
                try:
                    from utils.ai_generator import get_client, generate_content_audit
                    client = get_client(get_anthropic_key())

                    result = generate_content_audit(
                        client, page_data, target_keywords,
                        non_brand["query"].tolist()
                    )

                    if "generated_content" not in st.session_state:
                        st.session_state["generated_content"] = {}
                    st.session_state["generated_content"].setdefault(selected_url, {})["gap_analysis"] = result

                except Exception as e:
                    st.error(f"❌ Error: {e}")

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
                st.markdown(f"**Summary:** {gap_result.get('summary','')}")
                if gap_result.get("thin_content"):
                    st.error("⚠️ THIN CONTENT - The page has too little relevant text")

            # Keyword coverage table
            st.markdown("#### Keyword Coverage")
            kw_cov = gap_result.get("keyword_coverage", [])
            if kw_cov:
                cov_df = pd.DataFrame(kw_cov)
                cov_df["Status"] = cov_df["present"].map({True: "✅ Present", False: "❌ Missing"})
                st.dataframe(
                    cov_df[["keyword", "Status", "context"]].rename(columns={
                        "keyword": "Keyword", "context": "Details"
                    }),
                    use_container_width=True, hide_index=True
                )

            col_l, col_r = st.columns(2)
            with col_l:
                st.markdown("#### Missing Topics")
                for topic in gap_result.get("missing_topics", []):
                    st.markdown(f"<div style='color:#ff4455; font-size:0.85rem; padding:2px 0;'>❌ {topic}</div>", unsafe_allow_html=True)

            with col_r:
                st.markdown("#### Recommended Structure")
                rec = gap_result.get("recommended_structure", {})
                if rec.get("suggested_h1"):
                    st.markdown(f"**Suggested H1:** {rec['suggested_h1']}")
                for sec in rec.get("suggested_sections", []):
                    st.markdown(f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.8rem; color:#c8b4ff; padding:2px 0;'>→ {sec}</div>", unsafe_allow_html=True)

        import pandas as pd

    with tab3:
        tone = st.selectbox(
            "Tone of voice",
            ["Professional but accessible", "Discreet and respectful", "Energetic and direct", "Informative and guiding"],
            index=0
        )

        if st.button("📝 Generate landing page text", type="primary", key="gen_content"):
            with st.spinner("Claude writing optimized content... (~30 sec)"):
                try:
                    from utils.ai_generator import get_client, generate_landing_page_text
                    client = get_client(get_anthropic_key())

                    pdata = dict(page_data)
                    pdata["url"] = selected_url

                    result = generate_landing_page_text(
                        client, pdata, target_keywords,
                        non_brand["query"].tolist(),
                        site_context, language, tone
                    )

                    if "generated_content" not in st.session_state:
                        st.session_state["generated_content"] = {}
                    st.session_state["generated_content"].setdefault(selected_url, {})["landing_text"] = result

                except Exception as e:
                    st.error(f"❌ Error: {e}")

        lp_result = st.session_state.get("generated_content", {}).get(selected_url, {}).get("landing_text")

        if lp_result:
            # Display formatted content
            if lp_result.get("intro_paragraph"):
                st.markdown("#### Intro Text")
                st.markdown(f"""
                <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1rem; line-height:1.7; color:#e8e8f0;">
                    {lp_result['intro_paragraph']}
                </div>
                """, unsafe_allow_html=True)

            st.markdown("#### Sections")
            for sec in lp_result.get("sections", []):
                with st.expander(f"H2: {sec.get('h2','')}", expanded=True):
                    st.markdown(sec.get("content", ""))
                    for sub in sec.get("h3_subsections", []):
                        st.markdown(f"**{sub.get('h3','')}**")
                        st.markdown(sub.get("content", ""))

            if lp_result.get("buying_guide_snippet"):
                st.markdown("#### Buying Guide")
                st.markdown(lp_result["buying_guide_snippet"])

            if lp_result.get("faq_items"):
                st.markdown("#### FAQ")
                for faq in lp_result["faq_items"]:
                    with st.expander(f"❓ {faq.get('question','')}"):
                        st.markdown(faq.get("answer", ""))

            if lp_result.get("seo_notes"):
                st.info(f"📌 **SEO notes for the editor:** {lp_result['seo_notes']}")

            # Full export
            with st.expander("📋 Export all content"):
                full_text = f"# {selected_url}\n\n"
                full_text += f"## Intro\n{lp_result.get('intro_paragraph','')}\n\n"
                for sec in lp_result.get("sections", []):
                    full_text += f"## {sec.get('h2','')}\n{sec.get('content','')}\n\n"
                    for sub in sec.get("h3_subsections", []):
                        full_text += f"### {sub.get('h3','')}\n{sub.get('content','')}\n\n"
                if lp_result.get("buying_guide_snippet"):
                    full_text += f"## BuyingGuide\n{lp_result['buying_guide_snippet']}\n\n"

                st.text_area("Markdown format", full_text, height=300)
                st.download_button(
                    "⬇️ Download text (MD)",
                    full_text.encode("utf-8"),
                    f"content_{selected_url.split('/')[-2]}.md",
                    "text/markdown"
                )
