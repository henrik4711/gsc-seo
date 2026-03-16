"""
Action Plan page
Generates and displays prioritized SEO action list
"""

import streamlit as st
import pandas as pd
from config import get_anthropic_key, has_anthropic_key
from utils.ui_helpers import shorten_url


def render():
    st.markdown("## 📋 Action Plan")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:2rem;'>Prioritized action plan based on CTR gaps and audit results</p>",
        unsafe_allow_html=True
    )

    has_audit = "audit_results" in st.session_state and st.session_state["audit_results"]
    has_gaps = "ctr_gaps" in st.session_state

    if not has_audit and not has_gaps:
        st.warning("⚠️ Run CTR Analysis and/or Page Auditor to generate an action plan")
        return

    # ── Manual quick plan from CTR gaps ──────────────────────────
    if has_gaps and not has_audit:
        st.info("Only CTR data available. Run Page Auditor for a more precise plan.")
        _show_ctr_only_plan()
        return

    # ── AI Action Plan ────────────────────────────────────────────
    audit_results = st.session_state.get("audit_results", [])
    site_url = st.session_state.get("gsc_site", "your webshop")

    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🤖 Generate AI Action Plan", type="primary", use_container_width=True):
            if not has_anthropic_key():
                st.error("Add Anthropic API key in Setup or set ANTHROPIC_API_KEY env var")
            else:
                with st.spinner("Claude is analyzing all results and prioritizing..."):
                    try:
                        from utils.ai_generator import get_client, generate_action_plan
                        client = get_client(get_anthropic_key())
                        result = generate_action_plan(client, audit_results, site_url)
                        st.session_state["action_plan"] = result
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

    # ── Display action plan ───────────────────────────────────────
    action_plan = st.session_state.get("action_plan")

    if action_plan:
        # Executive summary
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #12121f 0%, #0f0f1a 100%);
                    border:1px solid #5533ff; border-radius:10px; padding:1.5rem; margin-bottom:2rem;">
            <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#5533ff;
                        text-transform:uppercase; letter-spacing:0.15em; margin-bottom:0.5rem;">
                EXECUTIVE SUMMARY
            </div>
            <div style="font-size:0.95rem; color:#e8e8f0; line-height:1.7;">
                {action_plan.get('executive_summary', '')}
            </div>
            <div style="margin-top:1rem; font-family:'Syne',sans-serif; font-size:1.5rem; font-weight:700; color:#33dd88;">
                +{action_plan.get('estimated_monthly_clicks_gain', 0):,} clicks/mo
            </div>
            <div style="font-size:0.75rem; color:#6b6b8a; font-family:'IBM Plex Mono',monospace;">
                ESTIMATED MONTHLY CLICK GAIN
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Quick wins
        quick_wins = action_plan.get("quick_wins", [])
        if quick_wins:
            st.markdown("### ⚡ Quick Wins (under 30 min)")
            for win in quick_wins:
                st.markdown(
                    f"<div style='padding:6px 0; color:#33dd88; font-size:0.85rem;'>✅ {win}</div>",
                    unsafe_allow_html=True
                )
            st.markdown("---")

        # Priority actions
        st.markdown("### 🎯 Priority Actions")

        actions = action_plan.get("priority_actions", [])

        # Type filter
        type_filter = st.multiselect(
            "Filter by type",
            ["meta", "content", "technical"],
            default=["meta", "content", "technical"],
        )

        filtered_actions = [a for a in actions if a.get("type", "meta") in type_filter]

        for action in filtered_actions:
            priority = action.get("priority", "?")
            effort = action.get("effort", "Medium")
            a_type = action.get("type", "meta")
            impact = action.get("estimated_impact", "")
            url = action.get("url", "")

            effort_colors = {
                "Low": "#33dd88",
                "Medium": "#ffaa33",
                "High": "#ff4455",
            }
            type_icons = {"meta": "🏷️", "content": "📝", "technical": "⚙️"}
            effort_color = effort_colors.get(effort, "#6b6b8a")
            type_icon = type_icons.get(a_type, "📌")

            url_short = shorten_url(url) if url else ""

            st.markdown(f"""
            <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px;
                        padding:1rem; margin-bottom:0.75rem;
                        border-left:4px solid {'#5533ff' if priority <= 3 else '#2a2a4a'};">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
                    <div style="display:flex; align-items:center; gap:0.5rem;">
                        <span style="font-family:'Syne',sans-serif; font-weight:800; font-size:1.1rem;
                                     color:{'#c8b4ff' if priority <= 3 else '#6b6b8a'};">#{priority}</span>
                        <span style="font-size:1rem;">{type_icon}</span>
                        <span style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#6b6b8a;">
                            {url_short[:50]}
                        </span>
                    </div>
                    <div style="display:flex; gap:0.5rem; align-items:center;">
                        <span style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem;
                                     color:{effort_color}; border:1px solid {effort_color};
                                     border-radius:3px; padding:1px 6px;">
                            EFFORT: {effort.upper()}
                        </span>
                        <span style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem;
                                     color:#33dd88;">
                            {impact}
                        </span>
                    </div>
                </div>
                <div style="font-size:0.9rem; color:#e8e8f0; font-weight:500; margin-bottom:0.3rem;">
                    {action.get('action', '')}
                </div>
                <div style="font-size:0.8rem; color:#6b6b8a;">
                    {action.get('reason', '')}
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Strategic recommendations
        strategic = action_plan.get("strategic_recommendations", [])
        if strategic:
            st.markdown("---")
            st.markdown("### 🔭 Strategic Recommendations (1-3 months)")
            for rec in strategic:
                st.markdown(f"<div style='padding:6px 0; color:#c8b4ff; font-size:0.85rem;'>→ {rec}</div>", unsafe_allow_html=True)

        # Export
        st.markdown("---")
        if st.button("⬇️ Export Action Plan (CSV)"):
            actions_df = pd.DataFrame(actions)
            csv = actions_df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv, "action_plan.csv", "text/csv")

    else:
        # Fallback: show audit summary without AI
        _show_audit_summary(audit_results)


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

    st.markdown("### Top Pages with CTR Gap (without audit)")

    for _, row in page_summary.iterrows():
        url_short = shorten_url(row["page"])
        priority = "🔴 CRITICAL" if row["lost_clicks"] > 50 else "🟡 MEDIUM" if row["lost_clicks"] > 20 else "🟢 LOW"

        st.markdown(f"""
        <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1rem; margin-bottom:0.5rem;">
            <div style="display:flex; justify-content:space-between;">
                <div>
                    <span style="font-size:0.85rem; color:#c8b4ff; font-weight:500;">{url_short}</span><br>
                    <span style="font-size:0.75rem; color:#6b6b8a; font-family:'IBM Plex Mono',monospace;">Keywords: {row['top_kws']}</span>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:0.75rem; color:#e8e8f0;">{priority}</div>
                    <div style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#ff4455;">
                        -{row['lost_clicks']:.0f} clicks/mo
                    </div>
                    <div style="font-size:0.7rem; color:#6b6b8a;">Pos. {row['avg_pos']:.1f}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)


def _show_audit_summary(audit_results: list):
    """Show audit results as action table"""
    if not audit_results:
        return

    st.markdown("### Audit-based prioritization (click 'Generate AI Action Plan' for full analysis)")

    rows = []
    for r in sorted(audit_results, key=lambda x: x.get("lost_clicks_estimate", 0), reverse=True):
        rows.append({
            "Page": shorten_url(r["url"]),
            "Meta Score": r.get("meta_score"),
            "Lost Clicks": r.get("lost_clicks_estimate", 0),
            "Issues": len(r.get("issues", [])),
            "Top Keywords": ", ".join(r.get("target_keywords", [])[:2]),
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
