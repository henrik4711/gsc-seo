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
        "Upload Ahrefs data for at se page authority, backlink-profil og aendringsrisiko</p>",
        unsafe_allow_html=True
    )

    tab1, tab2, tab3, tab4 = st.tabs([
        "Upload Ahrefs Data",
        "Page Authority",
        "Backlink Oversigt",
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
        <div style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#5533ff; margin-bottom:0.5rem;">SAADAN EKSPORTERER DU FRA AHREFS</div>
        <div style="font-size:0.85rem; line-height:1.8;">
            <strong>1. Best by Links</strong> (vigtigst): Site Explorer &rarr; Best by links &rarr; Export CSV<br>
            <strong>2. Backlinks</strong>: Site Explorer &rarr; Backlinks &rarr; Filter: Live + Dofollow &rarr; Export CSV<br>
            <strong>3. Organic Keywords</strong> (valgfri): Site Explorer &rarr; Organic keywords &rarr; Export CSV
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
            help="Side-niveau data med referring domains og backlinks"
        )
        if best_file:
            try:
                from utils.ahrefs_import import parse_best_by_links
                df = parse_best_by_links(best_file.read())
                if not df.empty:
                    st.session_state["ahrefs_best_by_links"] = df
                    st.success(f"{len(df)} sider importeret")
                    st.dataframe(df.head(5), use_container_width=True, hide_index=True)
                else:
                    st.error("Ingen data fundet i filen. Tjek at det er en Ahrefs Best by Links CSV.")
            except Exception as e:
                st.error(f"Fejl ved parsing: {e}")

    with col2:
        st.markdown("#### Backlinks")
        bl_file = st.file_uploader(
            "Upload Backlinks CSV",
            type=["csv", "tsv"],
            key="upload_ahrefs_backlinks",
            help="Individuelle backlinks med anchor text og DR"
        )
        if bl_file:
            try:
                from utils.ahrefs_import import parse_backlinks
                df = parse_backlinks(bl_file.read())
                if not df.empty:
                    st.session_state["ahrefs_backlinks"] = df
                    st.success(f"{len(df)} backlinks importeret")
                    st.dataframe(df.head(5), use_container_width=True, hide_index=True)
                else:
                    st.error("Ingen data fundet. Tjek at det er en Ahrefs Backlinks CSV.")
            except Exception as e:
                st.error(f"Fejl ved parsing: {e}")

    with col3:
        st.markdown("#### Organic Keywords")
        kw_file = st.file_uploader(
            "Upload Organic Keywords CSV",
            type=["csv", "tsv"],
            key="upload_ahrefs_keywords",
            help="Soegevolume og keyword difficulty (supplement til GSC)"
        )
        if kw_file:
            try:
                from utils.ahrefs_import import parse_organic_keywords
                df = parse_organic_keywords(kw_file.read())
                if not df.empty:
                    st.session_state["ahrefs_organic_keywords"] = df
                    st.success(f"{len(df)} keywords importeret")
                    st.dataframe(df.head(5), use_container_width=True, hide_index=True)
                else:
                    st.error("Ingen data fundet. Tjek at det er en Ahrefs Organic Keywords CSV.")
            except Exception as e:
                st.error(f"Fejl ved parsing: {e}")

    # Build authority after upload
    has_best = "ahrefs_best_by_links" in st.session_state
    has_bl = "ahrefs_backlinks" in st.session_state

    if has_best or has_bl:
        if st.button("Byg Page Authority", type="primary"):
            from utils.ahrefs_import import build_page_authority
            authority = build_page_authority(
                best_by_links_df=st.session_state.get("ahrefs_best_by_links"),
                backlinks_df=st.session_state.get("ahrefs_backlinks"),
            )
            st.session_state["page_authority"] = authority

            # Auto-merge with GSC if available
            if "gsc_data" in st.session_state:
                from utils.ahrefs_import import merge_authority_with_gsc
                st.session_state["gsc_data_enriched"] = merge_authority_with_gsc(
                    st.session_state["gsc_data"], authority
                )

            st.success(f"Authority beregnet for {len(authority)} sider")
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
        if key in st.session_state:
            count = len(st.session_state[key])
            st.markdown(f"+ **{name}**: {count:,} rows loaded")
        else:
            st.markdown(f"X **{name}**: Not loaded")


def _render_authority():
    if "page_authority" not in st.session_state:
        st.info("Upload Ahrefs data og klik 'Byg Page Authority' forst")
        return

    auth = st.session_state["page_authority"]

    st.markdown("### Page Authority Ranking")

    # Metrics
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Sider med data", len(auth))
    with m2:
        high_auth = len(auth[auth.get("authority_score", pd.Series(dtype=int)) >= 60])
        st.metric("High authority sider", high_auth)
    with m3:
        total_rd = auth["referring_domains"].sum() if "referring_domains" in auth.columns else 0
        st.metric("Total referring domains", f"{total_rd:,}")

    # Table
    display_cols = [c for c in ["page", "referring_domains", "backlinks", "authority_score",
                                 "ahrefs_traffic", "change_risk", "high_dr_links", "avg_source_dr"]
                    if c in auth.columns]

    st.dataframe(
        auth[display_cols].rename(columns={
            "page": "Side",
            "referring_domains": "Ref. Domains",
            "backlinks": "Backlinks",
            "authority_score": "Authority",
            "ahrefs_traffic": "Ahrefs Traffic",
            "change_risk": "Risiko ved aendring",
            "high_dr_links": "DR50+ links",
            "avg_source_dr": "Gns. DR",
        }),
        use_container_width=True,
        hide_index=True,
    )


def _render_backlinks():
    if "ahrefs_backlinks" not in st.session_state:
        st.info("Upload Backlinks CSV forst")
        return

    bl = st.session_state["ahrefs_backlinks"]

    st.markdown("### Backlink Oversigt")

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Total backlinks", f"{len(bl):,}")
    with m2:
        if "source_domain" in bl.columns:
            st.metric("Unikke domains", f"{bl['source_domain'].nunique():,}")
    with m3:
        if "source_dr" in bl.columns:
            st.metric("Gns. DR", f"{bl['source_dr'].mean():.0f}")

    # Top backlinks by DR
    if "source_dr" in bl.columns:
        st.markdown("#### Top backlinks (hoejest DR)")
        top = bl.sort_values("source_dr", ascending=False).head(30)
        display_cols = [c for c in ["source_url", "target_url", "anchor", "source_dr", "source_traffic"]
                        if c in top.columns]
        st.dataframe(
            top[display_cols].rename(columns={
                "source_url": "Fra",
                "target_url": "Til",
                "anchor": "Anchor text",
                "source_dr": "DR",
                "source_traffic": "Traffic",
            }),
            use_container_width=True,
            hide_index=True,
        )

    # Anchor text distribution
    if "anchor" in bl.columns:
        st.markdown("#### Anchor text fordeling")
        anchor_dist = bl["anchor"].value_counts().head(20).reset_index()
        anchor_dist.columns = ["Anchor text", "Antal"]
        st.dataframe(anchor_dist, use_container_width=True, hide_index=True)

    # Links per target page
    if "target_url" in bl.columns:
        st.markdown("#### Links per side")
        per_page = bl.groupby("target_url").agg(
            links=("source_url", "count"),
            domains=("source_domain", "nunique"),
            avg_dr=("source_dr", "mean"),
        ).reset_index().sort_values("domains", ascending=False)
        per_page.columns = ["Side", "Links", "Domains", "Gns. DR"]
        per_page["Gns. DR"] = per_page["Gns. DR"].round(0)
        st.dataframe(per_page.head(30), use_container_width=True, hide_index=True)


def _render_risk_map():
    if "page_authority" not in st.session_state:
        st.info("Byg Page Authority forst")
        return

    auth = st.session_state["page_authority"]
    gsc_available = "gsc_data" in st.session_state

    st.markdown("### Risk Map: Sider der IKKE boer aendres")
    st.markdown(
        "<p style='color:#9b9bb8;'>"
        "Sider med hoej authority har mange backlinks. Aendring af URL, title eller struktur "
        "kan oedelaegge link equity og koste rankings.</p>",
        unsafe_allow_html=True,
    )

    if "change_risk" not in auth.columns:
        st.warning("Ingen risikodata tilgaengelig")
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
            f"{risk_level} ({len(pages)} sider)</div>",
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
                    detail += f" | GSC: {clicks} klik, {impressions:,} impr"

            st.markdown(
                f"<div style='padding:0.3rem 0; font-size:0.85rem; border-bottom:1px solid #1e1e2e;'>"
                f"<code>{page}</code><br>"
                f"<span style='color:#9b9bb8; font-size:0.75rem;'>{detail}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
