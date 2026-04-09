"""
Dashboard — ONE page that tells you exactly what to do next.
Shows: site health, current phase, next action, progress.
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
    has_validation = "_site_validation" in st.session_state
    has_ideal = "_ideal_structure" in st.session_state

    phase0_tasks = [
        ("Connect GSC data", has_gsc, "1. Setup & Connect"),
        ("Upload Ahrefs data", has_ahrefs, "2. Upload Data"),
        ("Build AI clusters", has_clusters, "5. Topic Clusters → Build AI Clusters"),
        ("Run bulk audit", has_audit, "6. Page Auditor → Bulk Audit"),
        ("Run AI quality check", any(k.startswith("_quality_") for k in st.session_state), "6. Page Auditor → AI Quality Check"),
        ("Run site validation", has_validation, "12. Site Map → Validate"),
        ("Generate ideal structure", has_ideal, "12. Site Map → Generate Ideal"),
    ]
    phase0_done = sum(1 for _, done, _ in phase0_tasks if done)
    phases.append({
        "name": "Data & Analysis",
        "tasks": phase0_tasks,
        "done": phase0_done,
        "total": len(phase0_tasks),
        "complete": phase0_done == len(phase0_tasks),
    })

    # ── Phase 1: Infrastructure fixes ─────────────────────────
    # Homepage — derive from GSC site URL (not hardcoded)
    site_url = st.session_state.get("gsc_site", "")
    homepage_url = site_url.rstrip("/") + "/" if site_url else ""
    homepage_plan = st.session_state.get(f"_ai_plan_{stable_hash(homepage_url)}") if homepage_url else None
    homepage_done = homepage_plan is not None and not homepage_plan.get("error")
    homepage_text = st.session_state.get(f"_bottom_text_{stable_hash(homepage_url)}") if homepage_url else None

    phase1_tasks = [
        ("Generate homepage plan", homepage_done, "14. Implementation → / → Generate AI plan"),
        ("Generate homepage text", homepage_text is not None, "14. Implementation → / → Generate Complete Page Text"),
        ("Copy homepage text to CMS", False, "Manual: paste generated HTML into CMS"),
    ]
    phase1_done = sum(1 for _, done, _ in phase1_tasks if done)
    phases.append({
        "name": "Fix Homepage (highest impact)",
        "tasks": phase1_tasks,
        "done": phase1_done,
        "total": len(phase1_tasks),
        "complete": phase1_done == len(phase1_tasks),
    })

    # ── Phase 2: Top 10 pages ─────────────────────────────────
    top_pages = sorted(audit_results, key=lambda r: -r.get("lost_clicks_estimate", 0))[:10]
    plans_done = 0
    texts_done = 0
    for r in top_pages:
        url = r.get("url", "")
        from utils.ui_helpers import normalize_url as _nu
        if homepage_url and _nu(url) == _nu(homepage_url):
            continue  # homepage handled in phase 1
        plan_key = f"_ai_plan_{stable_hash(url)}"
        if plan_key in st.session_state and not st.session_state[plan_key].get("error"):
            plans_done += 1
        text_key = f"_bottom_text_{stable_hash(url)}"
        if text_key in st.session_state:
            texts_done += 1

    phase2_tasks = [
        (f"Generate plans for top 10 pages", plans_done >= 9, "14. Implementation → Generate plans for top 10"),
        (f"Generate text for top 10 pages ({texts_done}/10 done)", texts_done >= 9, "14. Implementation → per page → Generate Complete Page Text"),
        ("Copy texts to CMS", False, "Manual: paste generated HTML for each page"),
    ]
    phase2_done = sum(1 for _, done, _ in phase2_tasks if done)
    phases.append({
        "name": "Fix Top 10 Pages",
        "tasks": phase2_tasks,
        "done": phase2_done,
        "total": len(phase2_tasks),
        "complete": phase2_done == len(phase2_tasks),
    })

    # ── Phase 3: Next batch ───────────────────────────────────
    next_pages = sorted(audit_results, key=lambda r: -r.get("lost_clicks_estimate", 0))[10:20]
    next_plans = sum(1 for r in next_pages if f"_ai_plan_{stable_hash(r.get('url', ''))}" in st.session_state)

    phase3_tasks = [
        (f"Generate plans for pages 11-20 ({next_plans}/10)", next_plans >= 10, "14. Implementation → page 2 → Generate plans"),
        ("Generate text for pages 11-20", False, "14. Implementation → per page → Generate Complete Page Text"),
        ("Copy texts to CMS", False, "Manual"),
    ]
    phase3_done = sum(1 for _, done, _ in phase3_tasks if done)
    phases.append({
        "name": "Fix Pages 11-20",
        "tasks": phase3_tasks,
        "done": phase3_done,
        "total": len(phase3_tasks),
        "complete": phase3_done == len(phase3_tasks),
    })

    # ── Phase 4: Measure results ──────────────────────────────
    phases.append({
        "name": "Measure Results (after 4 weeks)",
        "tasks": [
            ("Refresh GSC data", False, "1. Setup → Refresh GSC Data"),
            ("Re-run analysis", False, "Re-run steps 3-6"),
            ("Compare scores", False, "12. Site Map → Validate → compare with previous"),
        ],
        "done": 0,
        "total": 3,
        "complete": False,
    })

    return phases


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

        # Show tasks for current/incomplete phases
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

    # ── Top pages status ──────────────────────────────────────
    st.markdown("---")
    st.markdown("### Top Pages by Impact")

    audit_results = st.session_state.get("audit_results", [])
    top = sorted(audit_results, key=lambda r: -r.get("lost_clicks_estimate", 0))[:20]

    for i, r in enumerate(top, 1):
        url = r.get("url", "")
        lost = r.get("lost_clicks_estimate", 0)
        impr = r.get("impressions", 0)
        site_origin = st.session_state.get("gsc_site", "").rstrip("/")
        url_short = url.replace(site_origin, "") if site_origin else url

        has_plan = f"_ai_plan_{stable_hash(url)}" in st.session_state
        has_text = f"_bottom_text_{stable_hash(url)}" in st.session_state

        if has_text:
            status = "<span style='color:#33dd88;'>TEXT READY</span>"
        elif has_plan:
            status = "<span style='color:#ffaa33;'>PLAN READY</span>"
        else:
            status = "<span style='color:#6b6b8a;'>NOT STARTED</span>"

        st.markdown(
            f"<div style='display:flex; justify-content:space-between; padding:0.3rem 0; border-bottom:1px solid #1e1e2e; font-size:0.82rem;'>"
            f"<span style='color:#e8e8f0;'>{i}. {url_short}</span>"
            f"<span>{status} · <span style='color:#6b6b8a;'>{impr:,} impr · {lost:,.0f} lost</span></span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Debug: what's in cache
    st.markdown("---")
    st.markdown("#### Cache Status")
    import os
    cache_dir = "/data/ai_cache"
    if os.path.isdir(cache_dir):
        files = os.listdir(cache_dir)
        site_files = [f for f in files if f.startswith("_site") or f.startswith("_ideal") or f.startswith("_gap") or f.startswith("_plan_v")]
        st.markdown(f"AI cache: **{len(files)} files** total, **{len(site_files)} site analysis files**")
        for sf in site_files:
            size = os.path.getsize(os.path.join(cache_dir, sf))
            in_session = sf[:-5] in st.session_state
            st.markdown(f"<span style='color:{'#33dd88' if in_session else '#ff4455'}; font-size:0.75rem;'>{'IN SESSION' if in_session else 'ON DISK ONLY'} — {sf} ({size} bytes)</span>", unsafe_allow_html=True)
    else:
        st.markdown("<span style='color:#ff4455;'>Cache dir not found!</span>", unsafe_allow_html=True)

    st.session_state["dashboard_viewed"] = True
