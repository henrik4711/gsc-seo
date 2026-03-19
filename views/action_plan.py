"""
Action Plan — AI-Powered Implementation Guide
Each page gets a complete, AI-verified implementation plan.
No rule-based guessing — Claude evaluates all data and creates precise steps.
"""

import streamlit as st
import json
import pandas as pd
from config import get_anthropic_key, has_anthropic_key
from utils.ui_helpers import shorten_url


def _sort_pages_by_impact(audit_results):
    """Sort audited pages by potential impact (lost clicks)."""
    pages = []
    for r in audit_results:
        if not r.get("url"):
            continue
        pages.append({
            "url": r["url"],
            "page_type": r.get("page_type", "unknown"),
            "impressions": r.get("impressions", 0),
            "lost_clicks": r.get("lost_clicks_estimate", 0),
            "meta_score": r.get("meta_score"),
            "content_score": r.get("content_score"),
        })
    pages.sort(key=lambda p: -p["lost_clicks"])
    return pages


def render():
    st.markdown("## Implementation Guide")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1.5rem;'>"
        "AI-verified step-by-step plan for every page. Sorted by impact — work from the top. "
        "Click a page to generate its plan.</p>",
        unsafe_allow_html=True,
    )

    has_audit = "audit_results" in st.session_state and st.session_state["audit_results"]
    has_gaps = "ctr_gaps" in st.session_state

    if not has_audit:
        st.warning("Run **6. Page Auditor** first (bulk audit recommended)")
        if has_gaps:
            _show_ctr_only_plan()
        return

    if not has_anthropic_key():
        st.warning("Add Anthropic API key in **1. Setup** — needed for AI implementation plans")
        return

    audit_results = st.session_state["audit_results"]
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")

    # Build site URL list for AI to reference real URLs
    all_site_urls = sorted(set(r["url"] for r in audit_results if r.get("url")))
    gsc = st.session_state.get("gsc_data")
    if gsc is not None and hasattr(gsc, "page"):
        all_site_urls = sorted(set(all_site_urls + gsc["page"].unique().tolist()))

    pages = _sort_pages_by_impact(audit_results)

    if not pages:
        st.info("No audited pages found")
        return

    # ── Summary ───────────────────────────────────────────────────
    total_lost = sum(p["lost_clicks"] for p in pages)
    c1, c2, c3 = st.columns(3)
    c1.metric("Pages audited", len(pages))
    c2.metric("Total lost clicks", f"{total_lost:,.0f}")
    c3.metric("Pages with plan", sum(1 for p in pages if f"_ai_plan_{hash(p['url']) & 0xFFFFFF}" in st.session_state))

    st.markdown("---")

    # ── Generate all plans button ─────────────────────────────────
    col_gen, col_info = st.columns([1, 2])
    with col_gen:
        gen_top = st.button("Generate plans for top 10 pages", type="primary")
    with col_info:
        st.markdown(
            "<span style='font-size:0.75rem; color:#6b6b8a;'>"
            "~20 seconds per page. Plans are cached — you only pay once per page.</span>",
            unsafe_allow_html=True,
        )

    if gen_top:
        from utils.ai_generator import get_client, generate_page_implementation_plan
        client = get_client(get_anthropic_key())

        with st.status(f"Generating AI plans for top 10 pages...", expanded=True) as status:
            progress = st.progress(0)
            log = st.empty()

            top_pages = pages[:10]
            for i, p in enumerate(top_pages):
                plan_key = f"_ai_plan_{hash(p['url']) & 0xFFFFFF}"
                if plan_key in st.session_state:
                    log.write(f"[{i+1}/10] {p['url']} — already cached")
                    progress.progress((i + 1) / 10)
                    continue

                log.write(f"[{i+1}/10] {p['url']}...")
                try:
                    page_r = next((r for r in audit_results if r["url"] == p["url"]), {})
                    result = generate_page_implementation_plan(
                        client, page_r, site_context, all_site_urls, language,
                    )
                    st.session_state[plan_key] = result
                except Exception as e:
                    st.session_state[plan_key] = {"error": str(e), "steps": []}
                progress.progress((i + 1) / 10)

            status.update(label="Plans generated", state="complete", expanded=False)
        st.rerun()

    # ── Pagination ────────────────────────────────────────────────
    PAGES_PER_VIEW = 10
    total_count = len(pages)
    max_page = max(1, (total_count + PAGES_PER_VIEW - 1) // PAGES_PER_VIEW)
    current_page = st.number_input("Page", min_value=1, max_value=max_page, value=1, key="impl_page")
    start = (current_page - 1) * PAGES_PER_VIEW
    visible = pages[start:start + PAGES_PER_VIEW]

    st.markdown(f"**Showing {start+1}-{min(start+PAGES_PER_VIEW, total_count)} of {total_count} pages**")

    # ── Page cards ────────────────────────────────────────────────
    for p in visible:
        url = p["url"]
        plan_key = f"_ai_plan_{hash(url) & 0xFFFFFF}"
        has_plan = plan_key in st.session_state
        ptype = p["page_type"].upper()
        lost = p["lost_clicks"]
        impr = p["impressions"]
        meta_s = p["meta_score"]
        content_s = p["content_score"]

        border = "#ff4455" if lost > 1000 else "#ffaa33" if lost > 200 else "#2a2a40"
        plan_badge = "<span style='color:#33dd88; font-size:0.65rem;'>PLAN READY</span>" if has_plan else "<span style='color:#6b6b8a; font-size:0.65rem;'>NO PLAN YET</span>"

        # Card header
        st.markdown(
            f"<div style='background:#12121f; border:1px solid {border}; border-left:4px solid {border}; "
            f"border-radius:6px; padding:1rem; margin-bottom:0.3rem;'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;'>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:{border}; "
            f"text-transform:uppercase;'>{ptype}</span>"
            f"<div>{plan_badge} · "
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#6b6b8a;'>"
            f"{impr:,} impr · {lost:,.0f} lost clicks</span></div>"
            f"</div>"
            f"<div style='font-size:1rem; color:#e8e8f0; font-weight:600;'>{url}</div>"
            f"<div style='font-size:0.72rem; color:#6b6b8a; margin-top:0.2rem;'>"
            f"Meta: {meta_s if meta_s is not None else '?'}/100 · Content: {content_s if content_s is not None else '?'}/100"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        url_hash = hash(url) & 0xFFFFFF

        with st.expander(f"Implementation plan for {shorten_url(url)}", expanded=False):
            # Generate plan button (per page)
            if not has_plan:
                if st.button(f"Generate AI plan", key=f"btn_gen_plan_{url_hash}", type="primary"):
                    with st.spinner(f"AI analyzing {url}..."):
                        try:
                            from utils.ai_generator import get_client, generate_page_implementation_plan
                            client = get_client(get_anthropic_key())
                            page_r = next((r for r in audit_results if r["url"] == url), {})
                            result = generate_page_implementation_plan(
                                client, page_r, site_context, language,
                            )
                            st.session_state[plan_key] = result
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
            else:
                plan = st.session_state[plan_key]

                if plan.get("error"):
                    st.error(f"Plan generation failed: {plan['error']}")
                    if st.button("Retry", key=f"btn_retry_{url_hash}"):
                        del st.session_state[plan_key]
                        st.rerun()
                    continue

                # Overall assessment
                assessment = plan.get("overall_assessment", "")
                primary_kw = plan.get("primary_keyword", "")
                if assessment:
                    st.markdown(
                        f"<div style='background:#0d0d15; border-left:3px solid #5533ff; padding:0.8rem; "
                        f"border-radius:0 6px 6px 0; margin-bottom:1rem;'>"
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#5533ff; "
                        f"margin-bottom:0.3rem;'>AI ASSESSMENT · Primary keyword: {primary_kw}</div>"
                        f"<div style='font-size:0.85rem; color:#c8b4ff;'>{assessment}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                # Steps
                steps = plan.get("steps", [])
                if not steps:
                    st.success("No issues found — this page looks good!")
                    continue

                total_time = sum(s.get("time_minutes", 0) for s in steps)
                st.markdown(f"**{len(steps)} steps · ~{total_time} minutes total**")

                for step_idx, step in enumerate(steps, 1):
                    time_str = f"{step.get('time_minutes', 0)} min"
                    step_type = step.get("type", "content")
                    type_colors = {
                        "meta": "#c8b4ff",
                        "content": "#5533ff",
                        "links": "#ffaa33",
                        "schema": "#33dd88",
                        "structure": "#6b6baa",
                    }
                    type_color = type_colors.get(step_type, "#6b6b8a")

                    st.markdown(
                        f"<div style='background:#0d0d15; border-left:3px solid {type_color}; padding:0.7rem 1rem; "
                        f"border-radius:0 6px 6px 0; margin-bottom:0.6rem;'>"
                        f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.3rem;'>"
                        f"<span style='color:{type_color}; font-weight:700; font-size:0.95rem;'>"
                        f"Step {step_idx}: {step.get('action', '')}</span>"
                        f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#6b6b8a;'>"
                        f"{step_type.upper()} · ~{time_str}</span>"
                        f"</div>"
                        f"<div style='font-size:0.82rem; color:#9b9bb8; margin-bottom:0.4rem;'>"
                        f"{step.get('detail', '')}</div>"
                        f"<div style='font-size:0.85rem; color:#c8b4ff; line-height:1.5;'>"
                        f"{step.get('instruction', '')}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                    # AI generate buttons for content/meta/links steps
                    ai_result_key = f"impl_ai_{url_hash}_{step_idx}"

                    if step_type == "meta":
                        if st.button("AI: Generate meta", key=f"btn_ai_meta_{url_hash}_{step_idx}"):
                            with st.spinner("Generating..."):
                                try:
                                    from utils.ai_generator import get_client, generate_meta_suggestions
                                    client = get_client(get_anthropic_key())
                                    page_r = next((r for r in audit_results if r["url"] == url), {})
                                    result = generate_meta_suggestions(
                                        client, page_r,
                                        page_r.get("target_keywords", []),
                                        site_context, language, 2,
                                    )
                                    st.session_state[ai_result_key] = ("meta", result)
                                except Exception as e:
                                    st.error(f"Error: {e}")

                    elif step_type == "content":
                        if st.button("AI: Generate text", key=f"btn_ai_content_{url_hash}_{step_idx}"):
                            with st.spinner("Generating..."):
                                try:
                                    from utils.ai_generator import get_client, generate_keyword_text
                                    client = get_client(get_anthropic_key())
                                    page_r = next((r for r in audit_results if r["url"] == url), {})
                                    kw_list = page_r.get("target_keywords", [])[:10]
                                    body = (page_r.get("body_text") or "")[:800]
                                    result = generate_keyword_text(
                                        client, kw_list, body,
                                        page_r.get("page_type", "unknown"),
                                        site_context, language,
                                    )
                                    st.session_state[ai_result_key] = ("content", result)
                                except Exception as e:
                                    st.error(f"Error: {e}")

                    elif step_type == "links":
                        if st.button("AI: Generate link text", key=f"btn_ai_links_{url_hash}_{step_idx}"):
                            with st.spinner("Generating..."):
                                try:
                                    from utils.ai_generator import get_client, generate_link_text
                                    client = get_client(get_anthropic_key())
                                    # Extract target URL from instruction text
                                    import re
                                    target_match = re.search(r'https?://[^\s"<>]+', step.get("instruction", ""))
                                    if target_match:
                                        target = target_match.group(0).rstrip(".,)")
                                        result = generate_link_text(
                                            client, url, target,
                                            target.split("/")[-1].replace("-", " "),
                                            "page text",
                                            [primary_kw] if primary_kw else [],
                                            site_context, language,
                                        )
                                        st.session_state[ai_result_key] = ("links", result)
                                    else:
                                        st.warning("Could not extract target URL from instruction")
                                except Exception as e:
                                    st.error(f"Error: {e}")

                    elif step_type == "schema":
                        if st.button("Generate schema", key=f"btn_ai_schema_{url_hash}_{step_idx}"):
                            try:
                                from utils.ai_generator import generate_schema_markup
                                page_r = next((r for r in audit_results if r["url"] == url), {})
                                result = generate_schema_markup(
                                    page_type=page_r.get("page_type", "unknown"),
                                    url=url,
                                    title=page_r.get("title", ""),
                                    description=page_r.get("meta_description", ""),
                                    h1=page_r.get("h1", ""),
                                    site_name=site_context,
                                    site_url=st.session_state.get("gsc_site", ""),
                                )
                                st.session_state[ai_result_key] = ("schema", result)
                            except Exception as e:
                                st.error(f"Error: {e}")

                    # Display AI results
                    if ai_result_key in st.session_state:
                        ai_type, res = st.session_state[ai_result_key]
                        st.markdown(
                            "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#33dd88; "
                            "margin:0.3rem 0;'>COPY THIS INTO YOUR CMS</div>",
                            unsafe_allow_html=True,
                        )

                        if ai_type == "meta" and isinstance(res, dict):
                            for i, v in enumerate(res.get("variants", []), 1):
                                st.code(f"Title: {v.get('title','')}\nDescription: {v.get('description','')}", language="text")

                        elif ai_type == "content" and isinstance(res, dict):
                            st.code(res.get("optimized_text", ""), language="text")

                        elif ai_type == "links" and isinstance(res, dict):
                            st.markdown(f"<div style='color:#e8e8f0;'>{res.get('paragraph','')}</div>", unsafe_allow_html=True)
                            st.code(res.get("html", ""), language="html")

                        elif ai_type == "schema" and isinstance(res, dict):
                            st.code(res.get("json_ld", ""), language="html")

                # Regenerate plan button
                if st.button("Regenerate plan", key=f"btn_regen_{url_hash}"):
                    del st.session_state[plan_key]
                    st.rerun()

    # ── Download ──────────────────────────────────────────────────
    st.markdown("---")
    all_plans = {}
    for p in pages:
        pk = f"_ai_plan_{hash(p['url']) & 0xFFFFFF}"
        if pk in st.session_state:
            plan = st.session_state[pk]
            if not plan.get("error"):
                all_plans[p["url"]] = plan

    if all_plans:
        st.download_button(
            f"Download all plans ({len(all_plans)} pages)",
            json.dumps(all_plans, ensure_ascii=False, indent=2).encode("utf-8"),
            "implementation_plans.json",
            "application/json",
        )

    st.session_state["action_plan"] = True


def _show_ctr_only_plan():
    """Simple action plan from CTR gaps only"""
    gaps = st.session_state["ctr_gaps"]

    page_summary = (
        gaps.groupby("page")
        .agg(
            lost_clicks=("lost_clicks_estimate", "sum"),
            avg_pos=("position", "mean"),
            avg_gap=("ctr_gap_pct", "mean"),
            top_kws=("query", lambda x: ", ".join(x.head(3)))
        )
        .reset_index()
        .sort_values("lost_clicks", ascending=False)
        .head(20)
    )

    st.markdown("### Top Pages with CTR Gap (run Page Auditor for full implementation plan)")

    for _, row in page_summary.iterrows():
        url_short = shorten_url(row["page"])
        priority = "CRITICAL" if row["lost_clicks"] > 50 else "MEDIUM" if row["lost_clicks"] > 20 else "LOW"
        pri_color = {"CRITICAL": "#ff4455", "MEDIUM": "#ffaa33", "LOW": "#33dd88"}[priority]

        st.markdown(f"""
        <div style="background:#12121f; border-left:3px solid {pri_color}; border-radius:6px; padding:0.8rem; margin-bottom:0.5rem;">
            <div style="display:flex; justify-content:space-between;">
                <div>
                    <span style="font-size:0.85rem; color:#e8e8f0; font-weight:500;">{url_short}</span><br>
                    <span style="font-size:0.75rem; color:#6b6b8a; font-family:'IBM Plex Mono',monospace;">Keywords: {row['top_kws']}</span>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:0.7rem; color:{pri_color}; font-weight:600;">{priority}</div>
                    <div style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#ff4455;">
                        -{row['lost_clicks']:.0f} clicks/mo
                    </div>
                    <div style="font-size:0.7rem; color:#6b6b8a;">Pos. {row['avg_pos']:.1f}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
