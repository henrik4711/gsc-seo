"""
Missing Keywords — action-first view
Every item = one page to fix, with exact keywords to add and AI to write the text
"""

import streamlit as st
import json
from config import get_anthropic_key, has_anthropic_key


def _get_clean_snippet(r, max_chars=800):
    """Get clean editorial text, avoiding nav/menu pollution."""
    intro = r.get("intro_text") or ""
    bottom = r.get("bottom_text") or ""
    if intro or bottom:
        return (intro + "\n" + bottom).strip()[:max_chars]
    body = r.get("body_text") or ""
    h1 = r.get("h1") or ""
    if h1 and h1 in body:
        start = body.index(h1)
        return body[start:start + max_chars]
    skip = min(300, len(body) // 4)
    return body[skip:skip + max_chars]


def _build_action_list(audit_results):
    """Build a flat, prioritized action list from keyword gaps."""
    actions = []

    for r in audit_results:
        url = r.get("url", "")
        impressions = r.get("impressions", 0)
        lost_clicks = r.get("lost_clicks_estimate", 0)
        content_audit = r.get("content_audit") or {}
        kw_cov = content_audit.get("keyword_coverage") or {}
        topic_cov = content_audit.get("topic_coverage") or {}
        recommendations = content_audit.get("recommendations") or []
        issues = content_audit.get("issues") or []

        missing_kws_raw = kw_cov.get("missing", [])
        coverage_pct = kw_cov.get("coverage_pct", 100)

        # Use AI to filter keywords by relevance (cached per page)
        ai_filter_key = f"_kw_filter_{hash(url) & 0xFFFFFF}"
        if missing_kws_raw and ai_filter_key not in st.session_state:
            try:
                from utils.ai_generator import get_client, filter_relevant_keywords
                from config import get_anthropic_key, has_anthropic_key
                if has_anthropic_key():
                    client = get_client(get_anthropic_key())
                    h1 = (r.get("h1") or "")
                    ai_filter = filter_relevant_keywords(
                        client, url, r.get("title") or "", h1,
                        missing_kws_raw[:40], r.get("page_type", ""),
                    )
                    st.session_state[ai_filter_key] = ai_filter
            except Exception:
                st.session_state[ai_filter_key] = None

        ai_result = st.session_state.get(ai_filter_key)
        if ai_result and isinstance(ai_result, dict):
            missing_kws = ai_result.get("relevant", missing_kws_raw)
        else:
            missing_kws = missing_kws_raw

        # Missing/partial subtopics
        missing_subtopics = [
            s for s in (topic_cov.get("subtopics") or [])
            if s.get("status") in ("missing", "partial")
        ]

        has_keyword_gaps = bool(missing_kws or missing_subtopics)

        # Include ALL pages — even those with good coverage may have bad text quality
        if not has_keyword_gaps and not (r.get("body_text") or r.get("intro_text")):
            continue

        # Build specific instructions from the audit recommendations + issues
        specific_actions = []
        for rec in recommendations:
            if any(kw_word in rec.lower() for kw_word in ["keyword", "integrate", "add content", "add text", "intro", "bottom text", "h2"]):
                specific_actions.append(rec)
        for iss in issues:
            msg = iss.get("msg", "") if isinstance(iss, dict) else str(iss)
            if any(kw_word in msg.lower() for kw_word in ["keyword", "missing", "thin", "intro", "no primary"]):
                specific_actions.append(msg)

        # Determine priority based on impressions + coverage
        if impressions > 1000 and coverage_pct < 50:
            priority = "high"
        elif impressions > 500 or coverage_pct < 40:
            priority = "high"
        elif coverage_pct < 60:
            priority = "medium"
        else:
            priority = "low"

        # Determine the PRIMARY keyword for this page — the one with most
        # impressions from GSC, NOT just the first missing keyword
        target_kws = r.get("target_keywords", [])  # sorted by impressions desc
        primary_keyword = target_kws[0] if target_kws else (missing_kws[0] if missing_kws else "")

        # Build clear instruction
        kw_list = ", ".join(missing_kws[:8])
        subtopic_list = ", ".join([s["topic"] for s in missing_subtopics[:5]])

        instruction_parts = []
        if missing_kws:
            instruction_parts.append(
                f"Add these missing keywords naturally into the page text: **{kw_list}**"
            )
        if kw_cov.get("in_h1", 0) == 0 and primary_keyword:
            instruction_parts.append(
                f"Make sure the H1 heading contains the primary keyword (**{primary_keyword}**)"
            )
        if kw_cov.get("in_intro", 0) == 0:
            instruction_parts.append(
                "Add keywords to the intro paragraph — Google gives extra weight to early text"
            )
        if missing_subtopics:
            instruction_parts.append(
                f"Add content sections about these missing topics: **{subtopic_list}**"
            )

        actions.append({
            "url": url,
            "page_type": r.get("page_type", "unknown"),
            "priority": priority,
            "has_keyword_gaps": has_keyword_gaps,
            "impressions": impressions,
            "lost_clicks": lost_clicks,
            "coverage_pct": coverage_pct,
            "missing_keywords": missing_kws,
            "missing_subtopics": missing_subtopics,
            "instructions": instruction_parts,
            "audit_actions": specific_actions,
            "primary_keyword": primary_keyword,
            "body_text": (r.get("intro_text") or r.get("bottom_text") or r.get("body_text") or ""),
            "body_text_snippet": _get_clean_snippet(r),
            "target_keywords": target_kws,
            "in_h1": kw_cov.get("in_h1", 0),
            "in_h2": kw_cov.get("in_h2", 0),
            "in_intro": kw_cov.get("in_intro", 0),
            "covered": kw_cov.get("covered", 0),
            "total_checked": kw_cov.get("total_checked", 0),
        })

    # Sort: high priority first, then most impressions
    pri_order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(key=lambda a: (pri_order.get(a["priority"], 1), -a["impressions"]))
    return actions


def render():
    st.markdown("## Missing Keywords & Content Quality")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1.5rem;'>"
        "Every card = one page to review. Check keyword gaps AND text quality — "
        "click <strong>Review existing text quality</strong> to see if the text is worth keeping or needs rewriting.</p>",
        unsafe_allow_html=True,
    )

    if not has_anthropic_key():
        st.warning("Go to **1. Setup & Connect** and add Anthropic API key.")
        return

    if "audit_results" not in st.session_state:
        st.warning("Go to **6. Page Auditor** and run an audit first.")
        return

    audit_results = st.session_state["audit_results"]
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")

    # Cache action list
    cache_key = f"_kw_actions_v7_{len(audit_results)}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = _build_action_list(audit_results)
    actions = st.session_state[cache_key]

    if not actions:
        st.success("All audited pages have good keyword coverage!")
        st.session_state["keyword_fixes"] = True
        return

    # ── Summary ───────────────────────────────────────────────────
    high = sum(1 for a in actions if a["priority"] == "high")
    total_missing = sum(len(a["missing_keywords"]) for a in actions)
    total_topics = sum(len(a["missing_subtopics"]) for a in actions)
    avg_cov = sum(a["coverage_pct"] for a in actions) / len(actions)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pages to fix", len(actions))
    c2.metric("High priority", high)
    c3.metric("Missing keywords", total_missing)
    c4.metric("Avg coverage", f"{avg_cov:.0f}%")

    st.markdown("---")

    # ── Filter ────────────────────────────────────────────────────
    pri_filter = st.multiselect(
        "Show priority",
        ["high", "medium", "low"],
        default=["high", "medium"],
    )
    filtered = [a for a in actions if a["priority"] in pri_filter]

    # Pagination
    ITEMS_PER_PAGE = 10
    total_items = len(filtered)
    max_pg = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    pg = st.number_input("Page", min_value=1, max_value=max_pg, value=1, key="kw_page")
    start_i = (pg - 1) * ITEMS_PER_PAGE
    visible = filtered[start_i:start_i + ITEMS_PER_PAGE]
    st.markdown(f"**Showing {start_i+1}-{min(start_i+ITEMS_PER_PAGE, total_items)} of {total_items} pages**")

    # ── Action cards ──────────────────────────────────────────────
    for idx, a in enumerate(visible):
        # Use a stable key based on URL hash, not filtered index
        url_hash = hash(a["url"]) & 0xFFFFFF  # 6-digit stable ID
        url = a["url"]
        pri = a["priority"]
        pri_color = {"high": "#ff4455", "medium": "#ffaa33", "low": "#33dd88"}[pri]
        border_color = {"high": "#ff4455", "medium": "#2a2a40", "low": "#1e1e2e"}[pri]
        ptype = a["page_type"].upper()
        cov = a["coverage_pct"]
        cov_color = "#ff4455" if cov < 40 else "#ffaa33" if cov < 70 else "#33dd88"

        # ── Card header ──────────────────────────────────────
        st.markdown(
            f"<div style='background:#12121f; border:1px solid {border_color}; border-left:4px solid {pri_color}; "
            f"border-radius:6px; padding:1rem; margin-bottom:0.3rem;'>"
            # Header
            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;'>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:{pri_color}; "
            f"text-transform:uppercase; letter-spacing:0.1em;'>{pri.upper()} · {ptype}</span>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#6b6b8a;'>"
            f"{a['impressions']:,} impr · {a['lost_clicks']:.0f} lost clicks</span>"
            f"</div>"
            # URL + primary keyword
            f"<div style='font-size:1rem; color:#e8e8f0; font-weight:600; margin-bottom:0.3rem;'>{url}</div>"
            f"<div style='font-size:0.8rem; color:#9b9bb8; margin-bottom:0.5rem;'>"
            f"Primary keyword (by impressions): <span style='color:#c8b4ff; font-weight:600;'>{a.get('primary_keyword', '?')}</span></div>"
            # Coverage bar
            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.72rem; margin-bottom:0.6rem;'>"
            f"Keyword coverage: <span style='color:{cov_color};'>{cov:.0f}%</span> "
            f"({a['covered']}/{a['total_checked']}) · "
            f"In H1: {a['in_h1']} · In H2: {a['in_h2']} · In intro: {a['in_intro']}"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        with st.expander(f"View details & AI actions for {url}", expanded=(idx == 0)):
            # ── Missing keywords as badges ────────────────────
            if a["missing_keywords"]:
                kw_html = " ".join([
                    f"<span style='background:#1a0d0d; border:1px solid #ff4455; border-radius:4px; padding:3px 10px; "
                    f"font-family:\"IBM Plex Mono\",monospace; font-size:0.75rem; color:#ff4455; margin:2px; display:inline-block;'>{kw}</span>"
                    for kw in a["missing_keywords"]
                ])
                st.markdown(f"**Missing keywords:** {kw_html}", unsafe_allow_html=True)

            # ── Step-by-step instructions ─────────────────────
            st.markdown("#### What to do")
            for step_num, instruction in enumerate(a["instructions"], 1):
                st.markdown(
                    f"<div style='background:#0d0d15; border-left:3px solid #5533ff; padding:0.5rem 0.8rem; "
                    f"border-radius:0 4px 4px 0; margin-bottom:0.4rem; line-height:1.5;'>"
                    f"<span style='color:#5533ff; font-weight:700;'>{step_num}.</span> "
                    f"<span style='color:#e8e8f0; font-size:0.85rem;'>{instruction}</span></div>",
                    unsafe_allow_html=True,
                )

            # ── Audit-detected issues ─────────────────────────
            if a["audit_actions"]:
                st.markdown("#### From page audit")
                for aa in a["audit_actions"][:5]:
                    st.markdown(f"<div style='font-size:0.8rem; color:#ffaa33; padding:2px 0;'>→ {aa}</div>", unsafe_allow_html=True)

            # ── Missing subtopics ─────────────────────────────
            if a["missing_subtopics"]:
                st.markdown("#### Missing topic sections")
                for sub in a["missing_subtopics"]:
                    status_color = "#ff4455" if sub["status"] == "missing" else "#ffaa33"
                    queries = ", ".join(sub.get("queries", [])[:5])
                    st.markdown(
                        f"<div style='background:#12121f; border:1px solid #1e1e2e; border-radius:4px; padding:0.5rem; margin-bottom:0.3rem;'>"
                        f"<span style='color:{status_color}; font-size:0.75rem; font-weight:600;'>{sub['status'].upper()}</span> "
                        f"<span style='color:#e8e8f0; font-size:0.85rem;'>{sub['topic']}</span><br>"
                        f"<span style='font-size:0.72rem; color:#6b6b8a;'>Queries: {queries}</span></div>",
                        unsafe_allow_html=True,
                    )

            st.markdown("---")

            # ── Content quality review ─────────────────────────
            st.markdown("#### Content quality review")
            res_quality_key = f"quality_{url_hash}"
            if st.button("Review existing text quality", key=f"btn_quality_{url_hash}"):
                with st.spinner("AI reviewing content quality..."):
                    try:
                        from utils.ai_generator import get_client, assess_content_quality
                        client = get_client(get_anthropic_key())
                        result = assess_content_quality(
                            client, url, _get_clean_snippet(a, 3000),
                            a["page_type"], a["target_keywords"],
                            site_context, language,
                        )
                        st.session_state[res_quality_key] = result
                    except Exception as e:
                        st.error(f"Error: {e}")

            if res_quality_key in st.session_state:
                qr = st.session_state[res_quality_key]
                verdict = qr.get("verdict", "?")
                verdict_color = {"KEEP": "#33dd88", "IMPROVE": "#ffaa33", "REWRITE": "#ff4455"}.get(verdict, "#6b6b8a")
                overall = qr.get("overall_score", 0)

                # Verdict banner
                st.markdown(
                    f"<div style='background:#0d0d15; border:2px solid {verdict_color}; border-radius:8px; padding:1rem; margin:0.5rem 0;'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
                    f"<div>"
                    f"<span style='font-family:\"Syne\",sans-serif; font-size:1.5rem; font-weight:800; color:{verdict_color};'>{verdict}</span>"
                    f"<span style='font-size:0.85rem; color:#e8e8f0; margin-left:1rem;'>{qr.get('verdict_reason', '')}</span>"
                    f"</div>"
                    f"<span style='font-family:\"Syne\",sans-serif; font-size:2rem; font-weight:800; color:{verdict_color};'>{overall}/10</span>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # Score breakdown
                scores = qr.get("scores", {})
                score_cols = st.columns(6)
                score_labels = [
                    ("user_value", "User Value"),
                    ("readability", "Readability"),
                    ("conversion", "Conversion"),
                    ("google_quality", "Google/E-E-A-T"),
                    ("seo_integration", "SEO Integration"),
                    ("structure", "Structure"),
                ]
                for col, (key, label) in zip(score_cols, score_labels):
                    s = scores.get(key, {})
                    sc = s.get("score", 0)
                    sc_color = "#33dd88" if sc >= 7 else "#ffaa33" if sc >= 4 else "#ff4455"
                    with col:
                        st.markdown(
                            f"<div style='text-align:center; background:#12121f; border-radius:6px; padding:0.5rem;'>"
                            f"<div style='font-size:1.2rem; font-weight:700; color:{sc_color};'>{sc}</div>"
                            f"<div style='font-size:0.6rem; color:#6b6b8a; text-transform:uppercase;'>{label}</div>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                # Detailed comments
                with st.expander("Detailed score comments"):
                    for key, label in score_labels:
                        s = scores.get(key, {})
                        st.markdown(f"**{label}** ({s.get('score', 0)}/10): {s.get('comment', '')}")

                # Biggest problems
                problems = qr.get("biggest_problems", [])
                if problems:
                    st.markdown("**Biggest problems:**")
                    for p in problems:
                        st.markdown(
                            f"<div style='color:#ff4455; font-size:0.85rem; padding:2px 0;'>✗ {p}</div>",
                            unsafe_allow_html=True,
                        )

                # Specific fixes
                fixes = qr.get("specific_fixes", [])
                if fixes:
                    st.markdown("**What to fix:**")
                    for i, fix in enumerate(fixes, 1):
                        st.markdown(
                            f"<div style='background:#0d0d15; border-left:3px solid #5533ff; padding:0.4rem 0.8rem; "
                            f"border-radius:0 4px 4px 0; margin-bottom:0.3rem;'>"
                            f"<span style='color:#5533ff; font-weight:700;'>{i}.</span> "
                            f"<span style='color:#e8e8f0; font-size:0.85rem;'>{fix}</span></div>",
                            unsafe_allow_html=True,
                        )

                # Sections to rewrite
                rewrite = qr.get("rewrite_sections", [])
                if rewrite:
                    st.markdown("**Sections to rewrite:**")
                    for rw in rewrite:
                        st.markdown(f"<div style='color:#ffaa33; font-size:0.85rem; padding:2px 0;'>→ {rw}</div>", unsafe_allow_html=True)

            st.markdown("---")

            # ── AI action buttons ─────────────────────────────
            st.markdown("#### Let AI write the fix")
            col_a, col_b, col_c = st.columns(3)

            with col_a:
                res_text_key = f"kw_text_{url_hash}"
                if st.button("Write optimized text", key=f"btn_kw_text_{url_hash}", type="primary"):
                    with st.spinner("AI writing keyword-optimized text..."):
                        try:
                            from utils.ai_generator import get_client, generate_keyword_text
                            client = get_client(get_anthropic_key())
                            result = generate_keyword_text(
                                client, a["missing_keywords"], a["body_text_snippet"],
                                a["page_type"], site_context, language,
                            )
                            st.session_state[res_text_key] = result
                        except Exception as e:
                            st.error(f"Error: {e}")

            with col_b:
                res_intro_key = f"kw_intro_{url_hash}"
                if st.button("Rewrite intro", key=f"btn_kw_intro_{url_hash}"):
                    with st.spinner("AI rewriting intro with keywords..."):
                        try:
                            from utils.ai_generator import get_client, generate_intro_rewrite
                            client = get_client(get_anthropic_key())
                            result = generate_intro_rewrite(
                                client, a["missing_keywords"], a["body_text_snippet"],
                                a["page_type"], a["url"], site_context, language,
                            )
                            st.session_state[res_intro_key] = result
                        except Exception as e:
                            st.error(f"Error: {e}")

            with col_c:
                res_faq_key = f"kw_faq_{url_hash}"
                if a["missing_subtopics"] and st.button("Generate FAQ", key=f"btn_kw_faq_{url_hash}"):
                    with st.spinner("AI generating FAQ..."):
                        try:
                            from utils.ai_generator import get_client, generate_keyword_faq
                            client = get_client(get_anthropic_key())
                            subtopic_names = [s["topic"] for s in a["missing_subtopics"]]
                            result = generate_keyword_faq(
                                client, subtopic_names, a["missing_keywords"],
                                site_context, language,
                            )
                            st.session_state[res_faq_key] = result
                        except Exception as e:
                            st.error(f"Error: {e}")

            # ── AI results ────────────────────────────────────
            for rkey, label in [(f"kw_text_{url_hash}", "Optimized Text"), (f"kw_intro_{url_hash}", "Rewritten Intro")]:
                if rkey in st.session_state:
                    res = st.session_state[rkey]
                    st.markdown(
                        f"<div style='background:#0d1a0d; border-left:3px solid #33dd88; padding:0.8rem; "
                        f"border-radius:0 6px 6px 0; margin:0.5rem 0;'>"
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#33dd88; "
                        f"margin-bottom:0.4rem;'>COPY THIS — {label.upper()}</div>"
                        f"<div style='color:#e8e8f0; line-height:1.6;'>{res.get('optimized_text', '')}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    integrated = res.get("keywords_integrated", [])
                    if integrated:
                        st.markdown(
                            f"<span style='font-size:0.72rem; color:#33dd88;'>Keywords integrated: {', '.join(integrated)}</span>",
                            unsafe_allow_html=True,
                        )
                    st.code(res.get("optimized_text", ""), language="text")

            if f"kw_faq_{url_hash}" in st.session_state:
                res = st.session_state[f"kw_faq_{url_hash}"]
                st.markdown(
                    "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#33dd88; "
                    "margin:0.5rem 0 0.3rem 0;'>COPY THIS — FAQ SECTION</div>",
                    unsafe_allow_html=True,
                )
                faq_md = ""
                for faq in res.get("faq_items", []):
                    q = faq.get("question", "")
                    ans = faq.get("answer", "")
                    st.markdown(f"**Q: {q}**")
                    st.markdown(f"{ans}")
                    faq_md += f"**Q: {q}**\n{ans}\n\n"
                st.code(faq_md, language="text")

    st.markdown("---")
    st.session_state["keyword_fixes"] = True

    # ── Download ──────────────────────────────────────────────────
    export_data = [{
        "page": a["url"],
        "priority": a["priority"],
        "coverage": f"{a['coverage_pct']:.0f}%",
        "missing_keywords": a["missing_keywords"],
        "instructions": a["instructions"],
    } for a in actions]
    st.download_button(
        "Download action list (JSON)",
        json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8"),
        "missing_keywords_actions.json",
        "application/json",
    )
