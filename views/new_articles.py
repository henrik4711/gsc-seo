"""
New Articles — action-first view
Every card = one article to create, with clear instructions and AI generation
"""

import streamlit as st
import json
from config import get_anthropic_key, has_anthropic_key


def render():
    st.markdown("## New Articles — Action List")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1.5rem;'>"
        "Every card = one article you should write. Click the AI buttons to generate the full article, ready to publish.</p>",
        unsafe_allow_html=True,
    )

    if not has_anthropic_key():
        st.warning("Go to **1. Setup & Connect** and add Anthropic API key.")
        return

    content_roadmap = st.session_state.get("content_roadmap")
    if not content_roadmap:
        st.warning("Go to **5. Topic Clusters** first — the content roadmap is generated there.")
        return

    articles = content_roadmap.get("articles_needed", [])
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")

    if not articles:
        st.success("No new articles needed — content coverage looks good!")
        st.session_state["new_articles"] = True
        return

    # ── Summary ───────────────────────────────────────────────────
    total_impr = content_roadmap.get("total_opportunity_impressions", 0)
    high = sum(1 for a in articles if a.get("priority") == "high")
    med = sum(1 for a in articles if a.get("priority") == "medium")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Articles to write", len(articles))
    c2.metric("High priority", high)
    c3.metric("Medium priority", med)
    c4.metric("Traffic opportunity", f"{total_impr:,} impr.")

    st.markdown("---")

    # ── Filter ────────────────────────────────────────────────────
    pri_filter = st.multiselect(
        "Show priority",
        ["high", "medium", "low"],
        default=["high", "medium"],
        key="art_pri_filter",
    )
    filtered = [a for a in articles if a.get("priority", "medium") in pri_filter]
    st.markdown(f"**Showing {len(filtered)} of {len(articles)} articles**")

    # ── Article cards ─────────────────────────────────────────────
    for idx, article in enumerate(filtered):
        # Use index in the ORIGINAL (unfiltered) list for stable session keys
        orig_idx = articles.index(article) if article in articles else idx
        title = article.get("suggested_title", f"Article {orig_idx+1}")
        priority = article.get("priority", "medium")
        content_type = article.get("content_type", "article")
        est_impressions = article.get("estimated_impressions", 0)
        keywords = article.get("target_keywords", [])
        hub_page = article.get("supporting_page", "")
        cluster = article.get("cluster_topic", "")
        subtopic = article.get("subtopic", "")
        linking_plan = article.get("internal_linking_plan", [])

        pri_color = {"high": "#ff4455", "medium": "#ffaa33", "low": "#33dd88"}.get(priority, "#6b6b8a")
        border_color = {"high": "#ff4455", "medium": "#2a2a40", "low": "#1e1e2e"}.get(priority, "#1e1e2e")
        type_label = content_type.upper().replace("-", " ")

        # ── Card header ──────────────────────────────────────
        kw_html = " ".join([
            f"<span style='background:#12121f; border:1px solid #5533ff; border-radius:3px; padding:2px 6px; "
            f"font-family:\"IBM Plex Mono\",monospace; font-size:0.68rem; color:#c8b4ff; margin:1px; display:inline-block;'>{kw}</span>"
            for kw in keywords[:6]
        ])

        st.markdown(
            f"<div style='background:#12121f; border:1px solid {border_color}; border-left:4px solid {pri_color}; "
            f"border-radius:6px; padding:1rem; margin-bottom:0.3rem;'>"
            # Header
            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;'>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:{pri_color}; "
            f"text-transform:uppercase; letter-spacing:0.1em;'>{priority.upper()} · {type_label}</span>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#6b6b8a;'>"
            f"~{est_impressions:,} potential impressions</span>"
            f"</div>"
            # Title
            f"<div style='font-size:1.1rem; color:#e8e8f0; font-weight:700; margin-bottom:0.5rem;'>{title}</div>"
            # Keywords
            f"<div style='margin-bottom:0.5rem;'>{kw_html}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        with st.expander(f"Instructions & AI generation for: {title}", expanded=(idx == 0)):

            # ── Clear instructions ────────────────────────────
            st.markdown("#### What to do")

            step = 1
            st.markdown(
                f"<div style='background:#0d0d15; border-left:3px solid #5533ff; padding:0.5rem 0.8rem; "
                f"border-radius:0 4px 4px 0; margin-bottom:0.4rem; line-height:1.5;'>"
                f"<span style='color:#5533ff; font-weight:700;'>{step}.</span> "
                f"<span style='color:#e8e8f0; font-size:0.85rem;'>Create a new **{content_type}** article with the title: **\"{title}\"**</span></div>",
                unsafe_allow_html=True,
            )
            step += 1

            if keywords:
                kw_str = ", ".join(keywords[:6])
                st.markdown(
                    f"<div style='background:#0d0d15; border-left:3px solid #5533ff; padding:0.5rem 0.8rem; "
                    f"border-radius:0 4px 4px 0; margin-bottom:0.4rem; line-height:1.5;'>"
                    f"<span style='color:#5533ff; font-weight:700;'>{step}.</span> "
                    f"<span style='color:#e8e8f0; font-size:0.85rem;'>Target these keywords: **{kw_str}**</span></div>",
                    unsafe_allow_html=True,
                )
                step += 1

            if hub_page:
                st.markdown(
                    f"<div style='background:#0d0d15; border-left:3px solid #5533ff; padding:0.5rem 0.8rem; "
                    f"border-radius:0 4px 4px 0; margin-bottom:0.4rem; line-height:1.5;'>"
                    f"<span style='color:#5533ff; font-weight:700;'>{step}.</span> "
                    f"<span style='color:#e8e8f0; font-size:0.85rem;'>Link FROM the hub page **{hub_page}** TO this new article, and link BACK from the article to the hub.</span></div>",
                    unsafe_allow_html=True,
                )
                step += 1

            # Linking plan details
            if linking_plan:
                st.markdown("#### Internal linking to set up")
                for link in linking_plan:
                    from_url = link.get("from", "")
                    to_url = link.get("to", "")
                    anchor = link.get("anchor", "")
                    direction = link.get("direction", "")
                    st.markdown(
                        f"<div style='background:#12121f; border:1px solid #1e1e2e; border-radius:4px; padding:0.5rem; margin-bottom:0.3rem;'>"
                        f"<span style='font-size:0.82rem; color:#e8e8f0;'>{from_url}</span> "
                        f"<span style='color:#5533ff;'>→</span> "
                        f"<span style='font-size:0.82rem; color:#e8e8f0;'>{to_url}</span><br>"
                        f"<span style='font-size:0.72rem; color:#9b9bb8;'>Anchor: \"{anchor}\" · {direction}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

            st.markdown("---")

            # ── AI buttons ────────────────────────────────────
            st.markdown("#### Let AI write it")
            col_a, col_b, col_c = st.columns(3)

            with col_a:
                res_outline_key = f"art_outline_{orig_idx}"
                if st.button("1. Generate outline", key=f"btn_outline_{orig_idx}", type="primary"):
                    with st.spinner("AI creating outline..."):
                        try:
                            from utils.ai_generator import get_client, generate_article_outline
                            client = get_client(get_anthropic_key())
                            result = generate_article_outline(
                                client, title, keywords, content_type,
                                hub_page, site_context, language,
                            )
                            st.session_state[res_outline_key] = result
                        except Exception as e:
                            st.error(f"Error: {e}")

            with col_b:
                res_full_key = f"art_full_{orig_idx}"
                if st.button("2. Generate full article", key=f"btn_full_{orig_idx}"):
                    with st.spinner("AI writing full article... (~60 sec)"):
                        try:
                            from utils.ai_generator import get_client, generate_article_full
                            client = get_client(get_anthropic_key())
                            outline = st.session_state.get(res_outline_key)
                            result = generate_article_full(
                                client, title, keywords, outline,
                                content_type, site_context, language,
                            )
                            st.session_state[res_full_key] = result
                        except Exception as e:
                            st.error(f"Error: {e}")

            with col_c:
                res_meta_key = f"art_meta_{orig_idx}"
                if st.button("3. Generate meta tags", key=f"btn_meta_{orig_idx}"):
                    with st.spinner("AI generating meta..."):
                        try:
                            from utils.ai_generator import get_client, generate_article_meta
                            client = get_client(get_anthropic_key())
                            result = generate_article_meta(
                                client, title, keywords, site_context, language,
                            )
                            st.session_state[res_meta_key] = result
                        except Exception as e:
                            st.error(f"Error: {e}")

            # ── AI results ────────────────────────────────────

            # Outline
            if res_outline_key in st.session_state:
                res = st.session_state[res_outline_key]
                outline_data = res.get("outline", res)
                total_words = res.get("total_word_target", 0)

                st.markdown(
                    f"<div style='background:#0d1a0d; border-left:3px solid #33dd88; padding:0.8rem; "
                    f"border-radius:0 6px 6px 0; margin:0.5rem 0;'>"
                    f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#33dd88; "
                    f"margin-bottom:0.4rem;'>ARTICLE OUTLINE · {total_words:,} words target</div>"
                    f"<div style='font-size:1rem; color:#e8e8f0; font-weight:600; margin-bottom:0.5rem;'>"
                    f"H1: {outline_data.get('h1', title)}</div>",
                    unsafe_allow_html=True,
                )

                for sec in outline_data.get("sections", []):
                    h2 = sec.get("h2", "")
                    wt = sec.get("word_target", 0)
                    kws = ", ".join(sec.get("keywords_to_include", []))
                    h3_text = " → ".join(sec.get("h3s", []))
                    st.markdown(
                        f"<div style='padding:0.3rem 0 0.3rem 1rem; border-left:2px solid #2a2a40;'>"
                        f"<span style='color:#c8b4ff; font-weight:600;'>H2: {h2}</span> "
                        f"<span style='color:#6b6b8a; font-size:0.72rem;'>~{wt} words</span><br>"
                        f"{'<span style=\"color:#9b9bb8; font-size:0.75rem;\">H3: ' + h3_text + '</span><br>' if h3_text else ''}"
                        f"{'<span style=\"font-size:0.68rem; color:#5533ff;\">Keywords: ' + kws + '</span>' if kws else ''}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                st.markdown("</div>", unsafe_allow_html=True)

            # Full article
            if res_full_key in st.session_state:
                res = st.session_state[res_full_key]
                wc = res.get("word_count", 0)

                st.markdown(
                    f"<div style='background:#0d1a0d; border-left:3px solid #33dd88; padding:0.8rem; "
                    f"border-radius:0 6px 6px 0; margin:0.5rem 0;'>"
                    f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#33dd88; "
                    f"margin-bottom:0.4rem;'>FULL ARTICLE · {wc:,} words — COPY & PUBLISH</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                md = res.get("markdown", "")
                st.markdown(md)

                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    st.download_button(
                        "Download article (.md)",
                        md.encode("utf-8"),
                        f"article_{idx+1}_{content_type}.md",
                        "text/markdown",
                        key=f"dl_art_{orig_idx}",
                    )
                with col_dl2:
                    st.code(md, language="markdown")

            # Meta
            if res_meta_key in st.session_state:
                res = st.session_state[res_meta_key]
                mt = res.get("meta_title", "")
                md_desc = res.get("meta_description", "")
                st.markdown(
                    f"<div style='background:#0d1a0d; border-left:3px solid #33dd88; padding:0.8rem; "
                    f"border-radius:0 6px 6px 0; margin:0.5rem 0;'>"
                    f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#33dd88; "
                    f"margin-bottom:0.4rem;'>META TAGS — PASTE INTO CMS</div>"
                    f"<div style='margin-bottom:0.3rem;'>"
                    f"<span style='font-size:0.7rem; color:#5533ff;'>TITLE ({len(mt)} chars):</span> "
                    f"<span style='color:#e8e8f0;'>{mt}</span></div>"
                    f"<div>"
                    f"<span style='font-size:0.7rem; color:#5533ff;'>DESCRIPTION ({len(md_desc)} chars):</span> "
                    f"<span style='color:#b8b8d0;'>{md_desc}</span></div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")
    st.session_state["new_articles"] = True

    # ── Download all ──────────────────────────────────────────────
    export_data = [{
        "title": a.get("suggested_title", ""),
        "priority": a.get("priority", ""),
        "content_type": a.get("content_type", ""),
        "keywords": a.get("target_keywords", []),
        "hub_page": a.get("supporting_page", ""),
        "estimated_impressions": a.get("estimated_impressions", 0),
        "linking_plan": a.get("internal_linking_plan", []),
    } for a in articles]
    st.download_button(
        "Download all article plans (JSON)",
        json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8"),
        "new_articles_plan.json",
        "application/json",
    )
