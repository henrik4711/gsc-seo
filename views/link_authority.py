"""
Link Authority & Ahrefs Data view.
Upload Ahrefs CSV exports to see page authority, backlinks, and risk levels.
"""

import streamlit as st
import pandas as pd


def render():
    st.markdown("## Link Authority & Backlinks")
    st.markdown(
        "<p style='color:#9b9bb8; margin-bottom:2rem;'>"
        "Upload Ahrefs data to see page authority, backlink profile and change risk</p>",
        unsafe_allow_html=True
    )

    tab1, tab2, tab3, tab4 = st.tabs([
        "Upload Ahrefs Data",
        "Page Authority",
        "Backlink Overview",
        "Risk Map",
    ])

    with tab1:
        _render_upload()

    with tab2:
        _render_authority()

    with tab3:
        _render_backlinks()

    with tab4:
        _render_risk_map()


def _render_upload():
    st.markdown("### Upload Ahrefs CSV Exports")

    st.markdown("""
    <div style="background:#12121f; border:1px solid #2a2a40; border-radius:8px; padding:1rem; margin-bottom:1.5rem; color:#c0c0d8;">
        <div style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#5533ff; margin-bottom:0.5rem;">HOW TO EXPORT FROM AHREFS</div>
        <div style="font-size:0.85rem; line-height:1.8;">
            <strong>1. Best by Links</strong> (most important): Site Explorer &rarr; Best by links &rarr; Export CSV<br>
            <strong>2. Backlinks</strong>: Site Explorer &rarr; Backlinks &rarr; Filter: Live + Dofollow &rarr; Export CSV<br>
            <strong>3. Organic Keywords</strong> (optional): Site Explorer &rarr; Organic keywords &rarr; Export CSV
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### Best by Links")
        best_file = st.file_uploader(
            "Upload Best by Links CSV",
            type=["csv", "tsv"],
            key="upload_ahrefs_best",
            help="Page-level data with referring domains and backlinks"
        )
        if best_file:
            try:
                from utils.ahrefs_import import parse_best_by_links
                df = parse_best_by_links(best_file.read())
                if not df.empty:
                    st.session_state["ahrefs_best_by_links"] = df
                    st.success(f"{len(df)} pages imported")
                    st.dataframe(df.head(5), use_container_width=True, hide_index=True)
                else:
                    st.error("No data found in the file. Check that it is an Ahrefs Best by Links CSV.")
            except Exception as e:
                st.error(f"Error parsing: {e}")

    with col2:
        st.markdown("#### Backlinks")
        bl_file = st.file_uploader(
            "Upload Backlinks CSV",
            type=["csv", "tsv"],
            key="upload_ahrefs_backlinks",
            help="Individual backlinks with anchor text and DR"
        )
        if bl_file:
            try:
                from utils.ahrefs_import import parse_backlinks
                df = parse_backlinks(bl_file.read())
                if not df.empty:
                    st.session_state["ahrefs_backlinks"] = df
                    st.success(f"{len(df)} backlinks imported")
                    st.dataframe(df.head(5), use_container_width=True, hide_index=True)
                else:
                    st.error("No data found. Check that it is an Ahrefs Backlinks CSV.")
            except Exception as e:
                st.error(f"Error parsing: {e}")

    with col3:
        st.markdown("#### Organic Keywords")
        kw_file = st.file_uploader(
            "Upload Organic Keywords CSV",
            type=["csv", "tsv"],
            key="upload_ahrefs_keywords",
            help="Search volume and keyword difficulty (supplement to GSC)"
        )
        if kw_file:
            try:
                from utils.ahrefs_import import parse_organic_keywords
                df = parse_organic_keywords(kw_file.read())
                if not df.empty:
                    st.session_state["ahrefs_organic_keywords"] = df
                    st.success(f"{len(df)} keywords imported")
                    st.dataframe(df.head(5), use_container_width=True, hide_index=True)
                else:
                    st.error("No data found. Check that it is an Ahrefs Organic Keywords CSV.")
            except Exception as e:
                st.error(f"Error parsing: {e}")

    # Build authority after upload
    has_best = "ahrefs_best_by_links" in st.session_state
    has_bl = "ahrefs_backlinks" in st.session_state

    if has_best or has_bl:
        if st.button("Build Page Authority", type="primary"):
            from utils.ahrefs_import import build_page_authority
            authority = build_page_authority(
                best_by_links_df=st.session_state.get("ahrefs_best_by_links"),
                backlinks_df=st.session_state.get("ahrefs_backlinks"),
            )
            st.session_state["page_authority"] = authority

            # Auto-merge with GSC if available
            if "gsc_data" in st.session_state:
                from utils.ahrefs_import import merge_authority_with_gsc
                enriched = merge_authority_with_gsc(
                    st.session_state["gsc_data"], authority
                )
                st.session_state["gsc_data_enriched"] = enriched
                st.session_state["gsc_data"] = enriched

            st.success(f"Authority calculated for {len(authority)} pages")
            st.rerun()

    # Status
    st.markdown("---")
    st.markdown("### Import Status")
    datasets = {
        "Best by Links": "ahrefs_best_by_links",
        "Backlinks": "ahrefs_backlinks",
        "Organic Keywords": "ahrefs_organic_keywords",
        "Page Authority": "page_authority",
    }
    for name, key in datasets.items():
        data = st.session_state.get(key)
        if data is not None and hasattr(data, '__len__') and not hasattr(data, 'read'):
            st.markdown(f"+ **{name}**: {len(data):,} rows loaded")
        else:
            st.markdown(f"X **{name}**: Not loaded")


def _render_authority():
    if "page_authority" not in st.session_state:
        st.info("Upload Ahrefs data and click 'Build Page Authority' first")
        return

    auth = st.session_state["page_authority"]

    st.markdown("### Page Authority Ranking")

    # Metrics
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Pages with data", len(auth))
    with m2:
        high_auth = len(auth[auth.get("authority_score", pd.Series(dtype=int)) >= 60])
        st.metric("High authority pages", high_auth)
    with m3:
        total_rd = auth["referring_domains"].sum() if "referring_domains" in auth.columns else 0
        st.metric("Total referring domains", f"{total_rd:,}")

    # Table
    display_cols = [c for c in ["page", "referring_domains", "backlinks", "authority_score",
                                 "ahrefs_traffic", "change_risk", "high_dr_links", "avg_source_dr"]
                    if c in auth.columns]

    st.dataframe(
        auth[display_cols].rename(columns={
            "page": "Page",
            "referring_domains": "Ref. Domains",
            "backlinks": "Backlinks",
            "authority_score": "Authority",
            "ahrefs_traffic": "Ahrefs Traffic",
            "change_risk": "Change Risk",
            "high_dr_links": "DR50+ links",
            "avg_source_dr": "Avg. DR",
        }),
        use_container_width=True,
        hide_index=True,
    )


def _render_backlinks():
    if "ahrefs_backlinks" not in st.session_state:
        st.info("Upload Backlinks CSV first")
        return

    bl = st.session_state["ahrefs_backlinks"]

    st.markdown("### Backlink Overview")

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Total backlinks", f"{len(bl):,}")
    with m2:
        if "source_domain" in bl.columns:
            st.metric("Unique Domains", f"{bl['source_domain'].nunique():,}")
    with m3:
        if "source_dr" in bl.columns:
            st.metric("Avg. DR", f"{bl['source_dr'].mean():.0f}")

    # Top backlinks by DR
    if "source_dr" in bl.columns:
        st.markdown("#### Top Backlinks (highest DR)")
        top = bl.sort_values("source_dr", ascending=False).head(30)
        display_cols = [c for c in ["source_url", "target_url", "anchor", "source_dr", "source_traffic"]
                        if c in top.columns]
        st.dataframe(
            top[display_cols].rename(columns={
                "source_url": "From",
                "target_url": "To",
                "anchor": "Anchor text",
                "source_dr": "DR",
                "source_traffic": "Traffic",
            }),
            use_container_width=True,
            hide_index=True,
        )

    # Anchor text distribution
    if "anchor" in bl.columns:
        st.markdown("#### Anchor Text Distribution")
        anchor_dist = bl["anchor"].value_counts().head(20).reset_index()
        anchor_dist.columns = ["Anchor text", "Count"]
        st.dataframe(anchor_dist, use_container_width=True, hide_index=True)

    # Links per target page
    if "target_url" in bl.columns:
        st.markdown("#### Links per Page")
        per_page = bl.groupby("target_url").agg(
            links=("source_url", "count"),
            domains=("source_domain", "nunique"),
            avg_dr=("source_dr", "mean"),
        ).reset_index().sort_values("domains", ascending=False)
        per_page.columns = ["Page", "Links", "Domains", "Avg. DR"]
        per_page["Avg. DR"] = per_page["Avg. DR"].round(0)
        st.dataframe(per_page.head(30), use_container_width=True, hide_index=True)


def _render_risk_map():
    if "page_authority" not in st.session_state:
        st.info("Build Page Authority first")
        return

    auth = st.session_state["page_authority"]
    gsc_available = "gsc_data" in st.session_state

    st.markdown("### Risk Map: Pages that should NOT be changed")
    st.markdown(
        "<p style='color:#9b9bb8;'>"
        "Pages with high authority have many backlinks. Changing URL, title or structure "
        "can destroy link equity and cost rankings.</p>",
        unsafe_allow_html=True,
    )

    if "change_risk" not in auth.columns:
        st.warning("No risk data available")
        return

    # Risk categories
    for risk_level, color in [
        ("HIGH - do not change URL/structure", "#ff4455"),
        ("MEDIUM - change with care", "#ffaa33"),
        ("LOW - safe to optimize", "#33dd88"),
    ]:
        pages = auth[auth["change_risk"] == risk_level]
        if pages.empty:
            continue

        st.markdown(
            f"<div style='color:{color}; font-weight:600; margin-top:1rem;'>"
            f"{risk_level} ({len(pages)} pages)</div>",
            unsafe_allow_html=True,
        )

        for _, row in pages.iterrows():
            rd = row.get("referring_domains", 0)
            score = row.get("authority_score", 0)
            page = row["page"]

            detail = f"Authority: {score} | Ref domains: {rd}"

            # Add GSC data if available
            if gsc_available:
                gsc = st.session_state["gsc_data"]
                page_gsc = gsc[gsc["page"] == page]
                if not page_gsc.empty:
                    clicks = page_gsc["clicks"].sum()
                    impressions = page_gsc["impressions"].sum()
                    detail += f" | GSC: {clicks} clicks, {impressions:,} impr"

            st.markdown(
                f"<div style='padding:0.3rem 0; font-size:0.85rem; border-bottom:1px solid #1e1e2e;'>"
                f"<code>{page}</code><br>"
                f"<span style='color:#9b9bb8; font-size:0.75rem;'>{detail}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
