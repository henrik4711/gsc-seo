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


def _get_cluster_breakdown():
    """Break down the cluster-assignment state of all audited pages.

    The dashboard's "X unclustered pages" stat is computed from a single
    column (Cluster(s) == ""). When the number feels wrong, users need to
    see WHERE the count comes from — manual assignments, AI clustering,
    🚫-marks, or truly nothing. Returns a dict with counts so the dashboard
    can render a breakdown card.
    """
    from utils.ui_helpers import normalize_url

    audit_results = st.session_state.get("audit_results", [])
    if not audit_results:
        return None

    topic_clusters = st.session_state.get("topic_clusters", {}) or {}
    page_topics = topic_clusters.get("page_topics", {}) or {}
    no_cluster_needed = {
        normalize_url(u) for u in (st.session_state.get("_no_cluster_needed") or [])
    }

    # Build per-URL classification. Manual assignments are saved by
    # structure_fix.py with queries_in_topic == 0; AI clustering writes
    # rows with queries_in_topic > 0 (the queries belonging to the topic).
    # Products are EXCLUDED from the universe — they're not expected to
    # belong to a topic cluster (structure_fix.py:36 already filters them
    # out of the Unclustered list). Tracked separately so the user sees
    # what was excluded.
    by_url = {}  # norm → page_type
    for r in audit_results:
        url = r.get("url", "")
        if not url:
            continue
        by_url[normalize_url(url)] = r.get("page_type") or "unknown"

    manual = 0
    ai_assigned = 0
    marked_no_cluster = 0
    truly_unassigned = 0
    products_excluded = 0
    for norm, page_type in by_url.items():
        if page_type == "product":
            products_excluded += 1
            continue
        if norm in no_cluster_needed:
            marked_no_cluster += 1
            continue
        topics = page_topics.get(norm) or []
        if not topics:
            truly_unassigned += 1
            continue
        # If ANY topic entry has queries_in_topic > 0, treat as AI-assigned;
        # otherwise it was added manually via Site Cleanup → Unclustered.
        is_ai = any(
            isinstance(t, dict) and (t.get("queries_in_topic") or 0) > 0
            for t in topics
        )
        if is_ai:
            ai_assigned += 1
        else:
            manual += 1

    total_clusterable = manual + ai_assigned + marked_no_cluster + truly_unassigned
    return {
        "total": total_clusterable,
        "manual": manual,
        "ai": ai_assigned,
        "no_cluster_needed": marked_no_cluster,
        "truly_unassigned": truly_unassigned,
        "products_excluded": products_excluded,
        "audited_total": len(by_url),
    }


def _render_freshness_panel():
    """Render the Data Freshness panel: per-dataset timestamps + status +
    refresh hints, plus a 7-day push summary. The whole point is that the
    user shouldn't have to remember when they last ran anything."""
    try:
        from utils.freshness import get_freshness_report
        report = get_freshness_report()
    except Exception as e:
        st.caption(f"Freshness panel unavailable: {e}")
        return

    STATUS_STYLE = {
        "fresh":   ("#33dd88", "FRESH"),
        "aging":   ("#ffaa33", "AGING"),
        "stale":   ("#ff4455", "STALE"),
        "missing": ("#6b6b8a", "MISSING"),
    }

    # Header
    st.markdown(
        "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; "
        "color:#5533ff; text-transform:uppercase; letter-spacing:0.1em; "
        "margin: 0 0 0.5rem 0;'>DATA FRESHNESS</div>",
        unsafe_allow_html=True,
    )

    # ── Persisted datasets ──────────────────────────────────────
    rows_html = []
    for d in report["datasets"]:
        color, badge_text = STATUS_STYLE.get(d["status"], STATUS_STYLE["missing"])
        count_str = f"{d['row_count']:,}" if isinstance(d["row_count"], int) else "—"
        hint = d["hint"] if d["status"] in ("stale", "missing") else ""
        hint_html = (
            f"<span style='color:#6b6b8a; margin-left:0.5rem;'>→ {hint}</span>"
            if hint else ""
        )
        rows_html.append(
            f"<div style='display:flex; justify-content:space-between; align-items:center; "
            f"padding:0.35rem 0; border-bottom:1px solid #1e1e2e; font-size:0.8rem;'>"
            f"<div style='flex:2;'>"
            f"<span style='color:#e8e8f0;'>{d['label']}</span>"
            f"<span style='color:#6b6b8a; font-size:0.72rem; margin-left:0.5rem;'>"
            f"{count_str} items</span>"
            f"</div>"
            f"<div style='flex:2; color:#9b9bb8; font-family:\"IBM Plex Mono\",monospace; font-size:0.72rem;'>"
            f"{d['age_human']}{hint_html}"
            f"</div>"
            f"<div style='flex:0 0 70px; text-align:right;'>"
            f"<span style='color:{color}; font-family:\"IBM Plex Mono\",monospace; "
            f"font-size:0.65rem; font-weight:600;'>{badge_text}</span>"
            f"</div>"
            f"</div>"
        )

    for s in report["ai_singles"]:
        color, badge_text = STATUS_STYLE.get(s["status"], STATUS_STYLE["missing"])
        hint = s["hint"] if s["status"] in ("stale", "missing") else ""
        hint_html = (
            f"<span style='color:#6b6b8a; margin-left:0.5rem;'>→ {hint}</span>"
            if hint else ""
        )
        rows_html.append(
            f"<div style='display:flex; justify-content:space-between; align-items:center; "
            f"padding:0.35rem 0; border-bottom:1px solid #1e1e2e; font-size:0.8rem;'>"
            f"<div style='flex:2;'>"
            f"<span style='color:#e8e8f0;'>{s['label']}</span>"
            f"<span style='color:#6b6b8a; font-size:0.72rem; margin-left:0.5rem;'>(AI)</span>"
            f"</div>"
            f"<div style='flex:2; color:#9b9bb8; font-family:\"IBM Plex Mono\",monospace; font-size:0.72rem;'>"
            f"{s['age_human']}{hint_html}"
            f"</div>"
            f"<div style='flex:0 0 70px; text-align:right;'>"
            f"<span style='color:{color}; font-family:\"IBM Plex Mono\",monospace; "
            f"font-size:0.65rem; font-weight:600;'>{badge_text}</span>"
            f"</div>"
            f"</div>"
        )

    # AI batches — show count + oldest age, no traffic light (a single
    # batch can mix fresh + stale items so a single status is misleading).
    for b in report["ai_batches"]:
        if b["count"] == 0:
            age_text = "<span style='color:#6b6b8a;'>none cached</span>"
        else:
            age_text = (
                f"newest {b['newest_age_human']} · oldest {b['oldest_age_human']}"
            )
        hint_html = (
            f"<span style='color:#6b6b8a; margin-left:0.5rem;'>→ {b['hint']}</span>"
            if b["count"] == 0 else ""
        )
        rows_html.append(
            f"<div style='display:flex; justify-content:space-between; align-items:center; "
            f"padding:0.35rem 0; border-bottom:1px solid #1e1e2e; font-size:0.8rem;'>"
            f"<div style='flex:2;'>"
            f"<span style='color:#e8e8f0;'>{b['label']}</span>"
            f"<span style='color:#6b6b8a; font-size:0.72rem; margin-left:0.5rem;'>"
            f"{b['count']:,} cached</span>"
            f"</div>"
            f"<div style='flex:2; color:#9b9bb8; font-family:\"IBM Plex Mono\",monospace; font-size:0.72rem;'>"
            f"{age_text}{hint_html}"
            f"</div>"
            f"<div style='flex:0 0 70px; text-align:right;'>"
            f"<span style='color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace; "
            f"font-size:0.65rem;'>BATCH</span>"
            f"</div>"
            f"</div>"
        )

    st.markdown(
        f"<div style='background:#0d0d15; border:1px solid #2a2a40; border-radius:6px; "
        f"padding:0.5rem 1rem 0.8rem; margin-bottom:1rem;'>"
        f"{''.join(rows_html)}"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Push summary (last 7 days) ──────────────────────────────
    ps = report["push_summary"]
    total = ps.get("total", 0)
    if total > 0:
        latest_str = ps["latest_ts_human"]
        latest_url = ps.get("latest_url") or ""
        latest_url_short = latest_url if len(latest_url) <= 60 else "…" + latest_url[-60:]
        st.markdown(
            f"<div style='background:#0d0d15; border:1px solid #2a2a40; border-radius:6px; "
            f"padding:0.7rem 1rem; margin-bottom:1rem;'>"
            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; "
            f"color:#33dd88; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.4rem;'>"
            f"PUSHED TO MSHOP (LAST {ps['days']} DAYS)</div>"
            f"<div style='font-size:0.82rem; color:#e8e8f0;'>"
            f"<strong>{total}</strong> successful pushes · "
            f"<span style='color:#9b9bb8;'>"
            f"{ps['intro']} intro · {ps['bottom_text']} bottom · "
            f"{ps['meta_title']} meta titles · {ps['meta_description']} meta descriptions"
            f"</span></div>"
            f"<div style='font-size:0.72rem; color:#6b6b8a; margin-top:0.3rem;'>"
            f"Latest: {latest_str} · {latest_url_short}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("No successful pushes to mshop in the last 7 days.")


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

    # ── Data Freshness panel ────────────────────────────────────
    # The single biggest pain point: user cannot tell at a glance which
    # data is fresh, which is stale, and where to refresh it. This panel
    # shows mtime + row count + status for every major dataset plus a
    # summary of recent pushes to mshop. Source: utils/freshness.py.
    _render_freshness_panel()

    # ── Cluster-assignment breakdown ─────────────────────────────
    # Shows WHERE the "X unclustered pages" stat comes from, so the user
    # can verify it matches reality (e.g. "I assigned 200 manually — why
    # does it still say 454?"). Manual / AI / 🚫 / truly-unassigned.
    breakdown = _get_cluster_breakdown()
    if breakdown and breakdown["audited_total"] > 0:
        clusterable = breakdown["total"]
        audited_total = breakdown["audited_total"]
        unassigned_pct = (
            breakdown["truly_unassigned"] / clusterable * 100 if clusterable else 0
        )
        excluded = breakdown["products_excluded"]
        excluded_html = (
            f"<div><span style='color:#6b6b8a;'>Products (excluded):</span> "
            f"<strong style='color:#6b6b8a;'>{excluded:,}</strong></div>"
        ) if excluded else ""
        st.markdown(
            "<div style='background:#0d0d15; border:1px solid #2a2a40; border-radius:6px; "
            "padding:0.8rem; margin-bottom:1rem;'>"
            "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; "
            "color:#5533ff; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.5rem;'>"
            "CLUSTER ASSIGNMENT BREAKDOWN</div>"
            f"<div style='display:flex; gap:1.5rem; flex-wrap:wrap; font-size:0.82rem;'>"
            f"<div><span style='color:#6b6b8a;'>Audited total:</span> "
            f"<strong style='color:#e8e8f0;'>{audited_total:,}</strong></div>"
            f"{excluded_html}"
            f"<div><span style='color:#6b6b8a;'>Clusterable (non-product):</span> "
            f"<strong style='color:#e8e8f0;'>{clusterable:,}</strong></div>"
            f"<div><span style='color:#6b6b8a;'>AI clustered:</span> "
            f"<strong style='color:#33dd88;'>{breakdown['ai']:,}</strong></div>"
            f"<div><span style='color:#6b6b8a;'>Manually assigned:</span> "
            f"<strong style='color:#33dd88;'>{breakdown['manual']:,}</strong></div>"
            f"<div><span style='color:#6b6b8a;'>🚫 no-cluster-needed:</span> "
            f"<strong style='color:#c8b4ff;'>{breakdown['no_cluster_needed']:,}</strong></div>"
            f"<div><span style='color:#6b6b8a;'>Truly unassigned:</span> "
            f"<strong style='color:#ff4455;'>{breakdown['truly_unassigned']:,}</strong> "
            f"<span style='color:#6b6b8a;'>({unassigned_pct:.1f}%)</span></div>"
            f"</div>"
            "<div style='font-size:0.72rem; color:#6b6b8a; margin-top:0.4rem;'>"
            "Products are excluded — they're not expected to belong to a topic cluster. "
            "If the 'critical issues' text above shows a different number, it's cached "
            "from the last Site Validation run (Run Pipeline → Step 9) which used the old "
            "product-inclusive count.</div>"
            "</div>",
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
