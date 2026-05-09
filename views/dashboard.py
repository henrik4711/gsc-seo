"""
Dashboard — ONE page that tells you exactly what to do next.
Shows: site health, current phase, next action, progress.
All references point to the NEW views (Site Cleanup, Quick Wins, Run Pipeline).
"""

import streamlit as st
from utils.ui_helpers import stable_hash


def _get_site_health():
    """Get current and target health scores."""
    current = 0
    v = st.session_state.get("_site_validation")
    if v and isinstance(v, dict):
        current = v.get("overall_health_score", 0)

    target = 0
    ideal = st.session_state.get("_ideal_structure")
    if ideal and isinstance(ideal, dict):
        target = ideal.get("estimated_new_score", 78)

    return current, target


def _get_phase_status():
    """Determine which phase the user is in and what's done."""
    audit_results = st.session_state.get("audit_results", [])
    topic_clusters = st.session_state.get("topic_clusters", {})
    gsc_data = st.session_state.get("gsc_data")

    phases = []

    # ── Phase 0: Data collection ──────────────────────────────
    has_gsc = gsc_data is not None
    has_audit = len(audit_results) > 0
    has_clusters = len(topic_clusters.get("clusters", [])) > 0
    has_ahrefs = "page_authority" in st.session_state
    from utils.quality_check_runner import QUALITY_KEY_PREFIX as _QPF
    has_quality = any(k.startswith(_QPF) for k in st.session_state)
    has_cannibal = st.session_state.get("cannibalization") is not None
    has_validation = "_site_validation" in st.session_state

    phase0_tasks = [
        ("Fetch GSC data", has_gsc, "Run Pipeline → Step 1"),
        ("Build page authority", has_ahrefs, "Run Pipeline → Step 2"),
        ("Analyze crawl issues", "sf_crawl_issues" in st.session_state, "Run Pipeline → Step 3"),
        ("Build topic clusters", has_clusters, "Run Pipeline → Step 5"),
        ("Bulk audit pages", has_audit, "Run Pipeline → Step 6"),
        ("AI quality check", has_quality, "Run Pipeline → Step 7"),
        ("Cannibalization detection", has_cannibal, "Run Pipeline → Step 8"),
        ("Site validation", has_validation, "Run Pipeline → Step 9"),
    ]
    phase0_done = sum(1 for _, done, _ in phase0_tasks if done)
    phases.append({
        "name": "Data & Analysis",
        "tasks": phase0_tasks,
        "done": phase0_done,
        "total": len(phase0_tasks),
        "complete": phase0_done == len(phase0_tasks),
    })

    # ── Phase 1: Site Cleanup ──────────────────────────────────
    cannibal_df = st.session_state.get("cannibalization")
    cannibal_count = 0
    if cannibal_df is not None and hasattr(cannibal_df, "shape"):
        cannibal_count = len(cannibal_df[cannibal_df.get("severity", "").isin(["severe", "moderate"])]) if "severity" in cannibal_df.columns else 0

    phase1_tasks = [
        ("Fix cannibalization conflicts", cannibal_count == 0, "Site Cleanup → Merge tab"),
        ("Handle orphan pages", True, "Site Cleanup → Delete tab"),  # already done
        ("Block faceted URLs", True, "Add to robots.txt (see Site Cleanup → Noindex tab)"),
    ]
    phase1_done = sum(1 for _, done, _ in phase1_tasks if done)
    phases.append({
        "name": "Site Cleanup (structural fixes)",
        "tasks": phase1_tasks,
        "done": phase1_done,
        "total": len(phase1_tasks),
        "complete": phase1_done == len(phase1_tasks),
    })

    # ── Phase 2: Content fixes (top 10) ────────────────────────
    # Use brand-filtered lost clicks
    from utils.page_profile import build_page_profile
    top_urls = _get_top_pages_filtered(audit_results, 10)
    texts_done = sum(1 for url in top_urls if f"_bottom_text_{stable_hash(url)}" in st.session_state)

    phase2_tasks = [
        (f"Generate + paste text for top 10 pages ({texts_done}/10)", texts_done >= 10, "Site Cleanup → Merge tab → Rewrite content"),
        ("Verify texts in Magento", False, "Manual: check each page renders correctly"),
    ]
    phase2_done = sum(1 for _, done, _ in phase2_tasks if done)
    phases.append({
        "name": "Fix Top 10 Pages (content rewrite)",
        "tasks": phase2_tasks,
        "done": phase2_done,
        "total": len(phase2_tasks),
        "complete": phase2_done == len(phase2_tasks),
    })

    # ── Phase 3: Measure results ───────────────────────────────
    phases.append({
        "name": "Measure Results (after 4 weeks)",
        "tasks": [
            ("Refresh GSC data", False, "Run Pipeline → Step 1"),
            ("Re-run quality + cannibalization", False, "Run Pipeline → Step 7 + Step 8"),
            ("Compare health score", False, "Dashboard → check score improvement"),
        ],
        "done": 0,
        "total": 3,
        "complete": False,
    })

    return phases


def _get_top_pages_filtered(audit_results, n=20):
    """Get top pages by brand-filtered lost clicks."""
    from utils.page_profile import build_page_profile
    pages = []
    for r in audit_results:
        url = r.get("url", "")
        if not url:
            continue
        profile = build_page_profile(url)
        filtered_lost = sum(g.get("lost_clicks", 0) for g in profile.get("ctr_gaps", []))
        if filtered_lost > 0:
            pages.append((url, filtered_lost, profile))
    pages.sort(key=lambda x: -x[1])
    return [url for url, _, _ in pages[:n]]


def _get_next_action(phases):
    """Find the first incomplete task across all phases."""
    for phase in phases:
        if phase["complete"]:
            continue
        for task_name, done, where in phase["tasks"]:
            if not done:
                return phase["name"], task_name, where
    return "All done!", "Everything is complete", ""


def render():
    st.markdown("## Dashboard")

    current_score, target_score = _get_site_health()
    phases = _get_phase_status()
    phase_name, next_task, next_where = _get_next_action(phases)

    # ── Health score ──────────────────────────────────────────
    score_color = "#ff4455" if current_score < 30 else "#ffaa33" if current_score < 60 else "#33dd88"

    st.markdown(
        f"<div style='background:#0d0d15; border:2px solid {score_color}; border-radius:10px; padding:1.5rem; margin-bottom:1.5rem;'>"
        f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
        f"<div>"
        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#5533ff; text-transform:uppercase; letter-spacing:0.1em;'>SITE HEALTH</div>"
        f"<div style='font-size:3rem; font-weight:800; color:{score_color};'>{current_score}/100</div>"
        f"<div style='font-size:0.85rem; color:#6b6b8a;'>Target: {target_score}/100</div>"
        f"</div>"
        f"<div style='text-align:right;'>"
        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#5533ff; text-transform:uppercase; letter-spacing:0.1em;'>CURRENT PHASE</div>"
        f"<div style='font-size:1.2rem; font-weight:700; color:#c8b4ff;'>{phase_name}</div>"
        f"</div>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Critical issues from site validation ────────────────────
    v = st.session_state.get("_site_validation")
    if v and isinstance(v, dict):
        critical_issues = v.get("critical_issues", [])
        if critical_issues:
            items_html = "".join(
                f"<li style='color:#e8e8f0; font-size:0.82rem; margin-bottom:0.2rem;'>{issue}</li>"
                for issue in critical_issues[:3]
            )
            st.markdown(
                f"<div style='background:#12121f; border-left:4px solid #ff4455; border-radius:0 6px 6px 0; padding:0.8rem; margin-bottom:1rem;'>"
                f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#ff4455; margin-bottom:0.3rem;'>CRITICAL ISSUES</div>"
                f"<ul style='margin:0; padding-left:1.2rem;'>{items_html}</ul>"
                f"<div style='font-size:0.72rem; color:#6b6b8a; margin-top:0.4rem;'>See details: Site Cleanup → all tabs</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── Next action ───────────────────────────────────────────
    st.markdown(
        f"<div style='background:#12121f; border:2px solid #5533ff; border-radius:8px; padding:1rem; margin-bottom:1.5rem;'>"
        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#5533ff; margin-bottom:0.3rem;'>NEXT ACTION</div>"
        f"<div style='font-size:1.1rem; color:#e8e8f0; font-weight:600;'>{next_task}</div>"
        f"<div style='font-size:0.85rem; color:#9b9bb8; margin-top:0.3rem;'>Go to: {next_where}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Phase progress ────────────────────────────────────────
    st.markdown("### Progress")

    for i, phase in enumerate(phases):
        done = phase["done"]
        total = phase["total"]
        complete = phase["complete"]
        pct = (done / total * 100) if total > 0 else 0

        if complete:
            phase_color = "#33dd88"
            phase_icon = "OK"
        elif done > 0:
            phase_color = "#ffaa33"
            phase_icon = ">>"
        else:
            phase_color = "#3a3a5c"
            phase_icon = "  "

        st.markdown(
            f"<div style='background:#12121f; border-left:4px solid {phase_color}; border-radius:0 6px 6px 0; "
            f"padding:0.8rem 1rem; margin-bottom:0.5rem;'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
            f"<div style='font-size:0.95rem; color:#e8e8f0; font-weight:600;'>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; color:{phase_color}; margin-right:0.5rem;'>{phase_icon}</span>"
            f"Phase {i}: {phase['name']}</div>"
            f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.75rem; color:{phase_color};'>"
            f"{done}/{total} · {pct:.0f}%</span>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if not complete:
            for task_name, done, where in phase["tasks"]:
                icon = "+" if done else "X"
                color = "#33dd88" if done else "#6b6b8a"
                st.markdown(
                    f"<div style='padding:0.2rem 0 0.2rem 2rem; font-size:0.82rem;'>"
                    f"<span style='color:{color};'>{icon}</span> "
                    f"<span style='color:{'#9b9bb8' if done else '#e8e8f0'};'>{task_name}</span>"
                    f"{'<span style=\"color:#6b6b8a; font-size:0.72rem;\"> — ' + where + '</span>' if not done else ''}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # ── Top pages by impact (brand-filtered) ──────────────────
    st.markdown("---")
    st.markdown("### Top Pages by Impact (brand queries excluded)")

    audit_results = st.session_state.get("audit_results", [])
    if audit_results:
        from utils.page_profile import build_page_profile
        page_data = []
        for r in audit_results:
            url = r.get("url", "")
            if not url:
                continue
            profile = build_page_profile(url)
            filtered_lost = sum(g.get("lost_clicks", 0) for g in profile.get("ctr_gaps", []))
            if filtered_lost <= 0:
                continue
            page_data.append({
                "url": url,
                "lost": filtered_lost,
                "impr": profile.get("total_impressions", 0),
                "verdict": profile.get("quality_verdict"),
                "has_plan": profile.get("has_plan"),
            })
        page_data.sort(key=lambda x: -x["lost"])

        site_origin = st.session_state.get("gsc_site", "").rstrip("/")

        for i, p in enumerate(page_data[:20], 1):
            url_short = p["url"].replace(site_origin, "") if site_origin else p["url"]
            has_text = f"_bottom_text_{stable_hash(p['url'])}" in st.session_state

            if has_text:
                status = "<span style='color:#33dd88;'>TEXT READY</span>"
            elif p["has_plan"]:
                status = "<span style='color:#ffaa33;'>PLAN READY</span>"
            else:
                status = "<span style='color:#6b6b8a;'>NOT STARTED</span>"

            verdict_badge = ""
            if p["verdict"] == "REWRITE":
                verdict_badge = " · <span style='color:#ff4455;'>REWRITE</span>"
            elif p["verdict"] == "IMPROVE":
                verdict_badge = " · <span style='color:#ffaa33;'>IMPROVE</span>"

            st.markdown(
                f"<div style='display:flex; justify-content:space-between; padding:0.3rem 0; border-bottom:1px solid #1e1e2e; font-size:0.82rem;'>"
                f"<span style='color:#e8e8f0;'>{i}. {url_short}</span>"
                f"<span>{status}{verdict_badge} · <span style='color:#6b6b8a;'>{p['impr']:,} impr · {p['lost']:,.0f} lost</span></span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        if not page_data:
            st.info("Run Pipeline steps 1-8 to see page impact data.")
