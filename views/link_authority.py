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

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Upload Data",
        "Page Authority",
        "Backlink Overview",
        "Risk Map",
        "Crawl Data (SF)",
    ])

    with tab1:
        _render_upload()

    with tab2:
        _render_authority()

    with tab3:
        _render_backlinks()

    with tab4:
        _render_risk_map()

    with tab5:
        _render_crawl_data()


def _render_upload():
    st.markdown("### Upload Ahrefs CSV Exports")

    st.markdown("""
    <div style="background:#12121f; border:1px solid #2a2a40; border-radius:8px; padding:1rem; margin-bottom:1.5rem; color:#c0c0d8;">
        <div style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#5533ff; margin-bottom:0.5rem;">HOW TO EXPORT FROM AHREFS</div>
        <div style="font-size:0.85rem; line-height:1.8;">
            <strong>1. Best by Links</strong>: Site Explorer &rarr; Best by links &rarr; Export CSV<br>
            <strong>2. Backlinks</strong>: Site Explorer &rarr; Backlinks &rarr; Filter: Live + Dofollow &rarr; Export CSV<br>
            <strong>3. Organic Keywords</strong> (optional): Site Explorer &rarr; Organic keywords &rarr; Export CSV<br>
            <br><strong>Or place CSV files in <code>data/</code> folder</strong> — they are auto-detected below.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Auto-detect Ahrefs files in data/ folder ──────────────
    import os
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

    def _find_ahrefs_file(*patterns):
        if not os.path.isdir(DATA_DIR):
            return None
        for f in sorted(os.listdir(DATA_DIR), key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)), reverse=True):
            fl = f.lower()
            if any(p in fl for p in patterns) and fl.endswith((".csv", ".tsv")):
                return os.path.join(DATA_DIR, f)
        return None

    auto_bbl = _find_ahrefs_file("bbl", "best-by-links", "best_by_links")
    auto_bl = _find_ahrefs_file("backlink")
    auto_kw = _find_ahrefs_file("organic-keyword", "organic_keyword")

    auto_found = [f for f in [auto_bbl, auto_bl, auto_kw] if f]
    if auto_found:
        lines = []
        if auto_bbl:
            lines.append(f"Best by Links: <strong>{os.path.basename(auto_bbl)}</strong>")
        if auto_bl:
            lines.append(f"Backlinks: <strong>{os.path.basename(auto_bl)}</strong>")
        if auto_kw:
            lines.append(f"Organic Keywords: <strong>{os.path.basename(auto_kw)}</strong>")
        st.markdown(
            f"<div style='background:#0d0d15; border:1px solid #33dd88; border-radius:6px; padding:0.8rem; margin-bottom:1rem;'>"
            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#33dd88; margin-bottom:0.3rem;'>AHREFS FILES FOUND IN data/ FOLDER</div>"
            f"<div style='font-size:0.8rem; color:#c0c0d8;'>{'<br>'.join(lines)}</div></div>",
            unsafe_allow_html=True,
        )

        if st.button("Load all Ahrefs files from data/", type="primary", key="btn_auto_ahrefs"):
            from utils.ahrefs_import import parse_best_by_links, parse_backlinks, parse_organic_keywords
            from utils.persistence import save_key
            loaded = []
            if auto_bbl and "ahrefs_best_by_links" not in st.session_state:
                with st.spinner(f"Parsing {os.path.basename(auto_bbl)}..."):
                    with open(auto_bbl, "rb") as f:
                        df = parse_best_by_links(f.read())
                    if not df.empty:
                        st.session_state["ahrefs_best_by_links"] = df
                        save_key("ahrefs_best_by_links")
                        loaded.append(f"Best by Links: {len(df)} pages")
            if auto_bl and "ahrefs_backlinks" not in st.session_state:
                with st.spinner(f"Parsing {os.path.basename(auto_bl)}..."):
                    with open(auto_bl, "rb") as f:
                        df = parse_backlinks(f.read())
                    if not df.empty:
                        st.session_state["ahrefs_backlinks"] = df
                        save_key("ahrefs_backlinks")
                        loaded.append(f"Backlinks: {len(df)} links")
            if auto_kw and "ahrefs_organic_keywords" not in st.session_state:
                with st.spinner(f"Parsing {os.path.basename(auto_kw)}..."):
                    with open(auto_kw, "rb") as f:
                        df = parse_organic_keywords(f.read())
                    if not df.empty:
                        st.session_state["ahrefs_organic_keywords"] = df
                        save_key("ahrefs_organic_keywords")
                        loaded.append(f"Organic Keywords: {len(df)} keywords")
            if loaded:
                st.success("Loaded: " + " | ".join(loaded))
                st.rerun()
            else:
                st.info("All Ahrefs data already loaded.")

    # ── Manual upload fallback ────────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### Best by Links")
        if "ahrefs_best_by_links" not in st.session_state:
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
                        from utils.persistence import save_key
                        save_key("ahrefs_best_by_links")
                        st.success(f"{len(df)} pages imported")
                    else:
                        st.error("No data found. Check that it is an Ahrefs Best by Links CSV.")
                except Exception as e:
                    st.error(f"Error parsing: {e}")
        else:
            st.success(f"{len(st.session_state['ahrefs_best_by_links'])} pages loaded")

    with col2:
        st.markdown("#### Backlinks")
        if "ahrefs_backlinks" not in st.session_state:
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
                        from utils.persistence import save_key
                        save_key("ahrefs_backlinks")
                        st.success(f"{len(df)} backlinks imported")
                    else:
                        st.error("No data found. Check that it is an Ahrefs Backlinks CSV.")
                except Exception as e:
                    st.error(f"Error parsing: {e}")
        else:
            st.success(f"{len(st.session_state['ahrefs_backlinks'])} backlinks loaded")

    with col3:
        st.markdown("#### Organic Keywords")
        if "ahrefs_organic_keywords" not in st.session_state:
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
                        from utils.persistence import save_key
                        save_key("ahrefs_organic_keywords")
                        st.success(f"{len(df)} keywords imported")
                    else:
                        st.error("No data found. Check that it is an Ahrefs Organic Keywords CSV.")
                except Exception as e:
                    st.error(f"Error parsing: {e}")
        else:
            st.success(f"{len(st.session_state['ahrefs_organic_keywords'])} keywords loaded")

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

            from utils.persistence import save_all
            save_all()

            st.rerun()

    # ── Screaming Frog uploads ────────────────────────────────────
    st.markdown("---")
    st.markdown("### Screaming Frog Crawl Data")
    st.markdown("""
    <div style="background:#12121f; border:1px solid #2a2a40; border-radius:8px; padding:1rem; margin-bottom:1.5rem; color:#c0c0d8;">
        <div style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#5533ff; margin-bottom:0.5rem;">HOW TO EXPORT FROM SCREAMING FROG</div>
        <div style="font-size:0.85rem; line-height:1.8;">
            <strong>1. All Inlinks</strong> (most important): Bulk Export &rarr; All Inlinks &rarr; Save as CSV<br>
            <strong>2. All Pages</strong>: Internal tab &rarr; Filter: HTML &rarr; Export as CSV
        </div>
    </div>
    """, unsafe_allow_html=True)

    sf_col1, sf_col2 = st.columns(2)

    # ── Auto-detect files in data/ folder ────────────────────────
    import os
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

    def _find_data_file(*patterns):
        """Find first matching file in data/ folder."""
        if not os.path.isdir(DATA_DIR):
            return None
        for f in sorted(os.listdir(DATA_DIR), key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)), reverse=True):
            fl = f.lower()
            if any(p in fl for p in patterns) and fl.endswith((".csv", ".tsv")):
                return os.path.join(DATA_DIR, f)
        return None

    def _load_sf_file(file_path=None, file_bytes=None, parse_fn=None, key=None, post_fn=None):
        """Generic loader for SF files — from path or bytes. Passes path directly for large files."""
        if file_path:
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if size_mb > 50:
                # Large file: pass file path directly — parser streams in chunks
                with st.spinner(f"Streaming {os.path.basename(file_path)} ({size_mb:.0f} MB)..."):
                    df = parse_fn(file_path)
            else:
                with st.spinner(f"Reading {os.path.basename(file_path)} ({size_mb:.0f} MB)..."):
                    with open(file_path, "rb") as f:
                        file_bytes = f.read()
                    df = parse_fn(file_bytes)
        elif file_bytes:
            size_mb = len(file_bytes) / (1024 * 1024)
            with st.spinner(f"Parsing {size_mb:.0f} MB..."):
                df = parse_fn(file_bytes)
        else:
            st.error("No file provided.")
            return False
        if df.empty:
            st.error("No data found. Check that the file is the correct Screaming Frog export.")
            return False
        st.session_state[key] = df
        if post_fn:
            post_fn(df)
        from utils.persistence import save_key
        save_key(key)
        return True

    # Check for auto-detectable files
    auto_inlinks = _find_data_file("inlink")
    auto_pages = _find_data_file("all_pages", "internal_all", "internal_html")

    if auto_inlinks or auto_pages:
        st.markdown(
            f"<div style='background:#0d0d15; border:1px solid #33dd88; border-radius:6px; padding:0.8rem; margin-bottom:1rem;'>"
            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#33dd88; margin-bottom:0.3rem;'>FILES FOUND IN data/ FOLDER</div>"
            f"<div style='font-size:0.8rem; color:#c0c0d8;'>"
            f"{'All Inlinks: <strong>' + os.path.basename(auto_inlinks) + '</strong> (' + str(os.path.getsize(auto_inlinks) // (1024*1024)) + ' MB)<br>' if auto_inlinks else ''}"
            f"{'All Pages: <strong>' + os.path.basename(auto_pages) + '</strong> (' + str(os.path.getsize(auto_pages) // (1024*1024)) + ' MB)' if auto_pages else ''}"
            f"</div></div>",
            unsafe_allow_html=True,
        )

    with sf_col1:
        st.markdown("#### All Inlinks")

        from utils.screaming_frog_import import parse_all_inlinks, build_complete_link_map

        if auto_inlinks and "sf_inlinks" not in st.session_state:
            if st.button(f"Load {os.path.basename(auto_inlinks)}", type="primary", key="btn_auto_inlinks"):
                try:
                    def _post_inlinks(df):
                        lm = build_complete_link_map(df)
                        st.session_state["sf_link_map"] = lm
                        from utils.persistence import save_key
                        save_key("sf_link_map")
                        st.success(f"{len(df):,} links imported ({lm['unique_pages']:,} pages)")
                    _load_sf_file(file_path=auto_inlinks, parse_fn=parse_all_inlinks,
                                  key="sf_inlinks", post_fn=_post_inlinks)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            inlinks_file = st.file_uploader(
                "Upload All Inlinks CSV",
                type=["csv", "tsv"],
                key="upload_sf_inlinks",
                help="Or place file in data/ folder for large files"
            )
            if inlinks_file and "sf_inlinks" not in st.session_state:
                try:
                    def _post_inlinks(df):
                        lm = build_complete_link_map(df)
                        st.session_state["sf_link_map"] = lm
                        from utils.persistence import save_key
                        save_key("sf_link_map")
                        st.success(f"{len(df):,} links imported ({lm['unique_pages']:,} pages)")
                    _load_sf_file(file_bytes=inlinks_file.read(), parse_fn=parse_all_inlinks,
                                  key="sf_inlinks", post_fn=_post_inlinks)
                except Exception as e:
                    st.error(f"Error: {e}")

    with sf_col2:
        st.markdown("#### All Pages")

        from utils.screaming_frog_import import parse_all_pages

        if auto_pages and "sf_pages" not in st.session_state:
            if st.button(f"Load {os.path.basename(auto_pages)}", type="primary", key="btn_auto_pages"):
                try:
                    def _post_pages(df):
                        st.success(f"{len(df):,} pages imported")
                    _load_sf_file(file_path=auto_pages, parse_fn=parse_all_pages,
                                  key="sf_pages", post_fn=_post_pages)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            pages_file = st.file_uploader(
                "Upload All Pages / Internal HTML CSV",
                type=["csv", "tsv"],
                key="upload_sf_pages",
                help="Or place file in data/ folder for large files"
            )
            if pages_file and "sf_pages" not in st.session_state:
                try:
                    def _post_pages(df):
                        st.success(f"{len(df):,} pages imported")
                    _load_sf_file(file_bytes=pages_file.read(), parse_fn=parse_all_pages,
                                  key="sf_pages", post_fn=_post_pages)
                except Exception as e:
                    st.error(f"Error: {e}")

    # Show loaded SF data status + clear button
    has_sf_pages = "sf_pages" in st.session_state
    has_sf_inlinks = "sf_inlinks" in st.session_state

    if has_sf_pages or has_sf_inlinks:
        sf_status = []
        if has_sf_pages:
            sf_status.append(f"All Pages: {len(st.session_state['sf_pages']):,} rows")
        if has_sf_inlinks:
            sf_status.append(f"All Inlinks: {len(st.session_state['sf_inlinks']):,} rows")
        st.markdown(f"**Loaded:** {' · '.join(sf_status)}")

        if st.button("Clear SF data (re-upload)", key="btn_clear_sf"):
            for k in ["sf_pages", "sf_inlinks", "sf_link_map", "sf_crawl_issues"]:
                st.session_state.pop(k, None)
            st.rerun()

    if has_sf_pages or has_sf_inlinks:
        if st.button("Analyze Crawl Data", type="primary", key="btn_analyze_sf"):
            from utils.screaming_frog_import import analyze_crawl_data
            site_domain = ""
            if "gsc_site" in st.session_state:
                site_domain = st.session_state["gsc_site"].replace("https://", "").replace("http://", "").rstrip("/")
            issues = analyze_crawl_data(
                st.session_state.get("sf_pages", pd.DataFrame()),
                st.session_state.get("sf_inlinks", pd.DataFrame()),
                site_domain,
                gsc_data=st.session_state.get("gsc_data"),
                page_authority=st.session_state.get("page_authority"),
                sf_all_pages=st.session_state.get("sf_pages"),
            )
            st.session_state["sf_crawl_issues"] = issues
            total = sum(len(v) for v in issues.values())
            st.success(f"Analysis complete — {total} issues found")

            # Auto-save all imported data to volume
            from utils.persistence import save_all
            save_all()

            st.rerun()

    # Status
    st.markdown("---")
    st.markdown("### Import Status")
    datasets = {
        "Best by Links (Ahrefs)": "ahrefs_best_by_links",
        "Backlinks (Ahrefs)": "ahrefs_backlinks",
        "Organic Keywords (Ahrefs)": "ahrefs_organic_keywords",
        "Page Authority": "page_authority",
        "All Inlinks (SF)": "sf_inlinks",
        "All Pages (SF)": "sf_pages",
        "Link Map (SF)": "sf_link_map",
        "Crawl Issues (SF)": "sf_crawl_issues",
    }
    for name, key in datasets.items():
        data = st.session_state.get(key)
        if data is not None and hasattr(data, '__len__') and not hasattr(data, 'read'):
            st.markdown(f"+ **{name}**: {len(data):,} rows loaded")
        elif data is not None and isinstance(data, dict):
            total = sum(len(v) for v in data.values() if isinstance(v, list))
            st.markdown(f"+ **{name}**: {total} items")
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

        for _, row in pages.head(20).iterrows():
            rd = row.get("referring_domains", 0)
            score = row.get("authority_score", 0)
            page = row["page"]

            detail = f"Authority: {score} | Ref domains: {rd}"

            # Add GSC data if available
            if gsc_available:
                gsc = st.session_state["gsc_data"]
                from utils.ui_helpers import normalize_url as _nu
                page_gsc = gsc[gsc["page"].apply(_nu) == _nu(page)]
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


def _render_crawl_data():
    """Display Screaming Frog crawl analysis results."""
    issues = st.session_state.get("sf_crawl_issues")

    if not issues:
        st.info("Upload Screaming Frog data in the **Upload Data** tab and click **Analyze Crawl Data**.")
        return

    st.markdown("### Technical SEO Issues from Crawl Data")

    # Summary metrics
    broken = len(issues.get("broken_links", []))
    redirects = len(issues.get("redirect_chains", []))
    orphans = len(issues.get("orphan_pages", []))
    deep = len(issues.get("deep_pages", []))
    thin = len(issues.get("thin_pages", []))
    missing = len(issues.get("missing_meta", []))
    non_idx = len(issues.get("non_indexable", []))
    slow = len(issues.get("slow_pages", []))
    total = broken + redirects + orphans + deep + thin + missing + non_idx + slow

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total issues", total)
    c2.metric("Broken links", broken)
    c3.metric("Orphan pages", orphans)
    c4.metric("Deep pages", deep)

    st.markdown("---")

    # Issue sections
    issue_types = [
        ("broken_links", "Broken Links (4xx/5xx)", "#ff4455",
         "These pages return errors. Fix or redirect them."),
        ("orphan_pages", "Orphan Pages (cross-checked)", "#ff4455",
         "Pages with no content links — cross-checked with GSC impressions, Ahrefs backlinks, and SF inlinks to filter false positives."),
        ("redirect_chains", "Redirects", "#ffaa33",
         "Update internal links to point directly to the final URL."),
        ("deep_pages", "Deep Pages (>3 clicks from home)", "#ffaa33",
         "Move these closer to the homepage by adding links from higher-level pages."),
        ("thin_pages", "Thin Pages (<100 words)", "#ffaa33",
         "Add content or noindex pages with no SEO value."),
        ("missing_meta", "Missing Title / Description", "#ffaa33",
         "Add meta tags to improve click-through rate."),
        ("non_indexable", "Non-Indexable Pages", "#6b6b8a",
         "These pages are blocked from indexing. Verify this is intentional."),
        ("slow_pages", "Slow Pages (>2s response)", "#ffaa33",
         "Optimize server response time for better user experience and rankings."),
    ]

    for key, title, color, description in issue_types:
        items = issues.get(key, [])
        if not items:
            continue

        with st.expander(f"{title} ({len(items)} issues)", expanded=(key in ("broken_links", "orphan_pages"))):
            st.markdown(f"<p style='color:#9b9bb8; font-size:0.8rem;'>{description}</p>", unsafe_allow_html=True)

            for item in items[:50]:  # Cap display at 50
                url = item.get("url", "")
                action = item.get("action", "")
                extra = ""
                if "severity" in item:
                    sev = item["severity"]
                    sev_colors = {"CRITICAL": "#ff4455", "HIGH": "#ff6644", "MEDIUM": "#ffaa33", "LOW": "#6b6b8a"}
                    extra += f" | <span style='color:{sev_colors.get(sev, \"#6b6b8a\")};font-weight:600;'>{sev}</span>"
                if "in_google" in item:
                    extra += f" | Google: {'YES' if item['in_google'] else 'NO'}"
                if "has_backlinks" in item:
                    extra += f" | Backlinks: {'YES' if item['has_backlinks'] else 'NO'}"
                if "status_code" in item:
                    extra += f" | Status: {item['status_code']}"
                if "crawl_depth" in item:
                    extra += f" | Depth: {item['crawl_depth']}"
                if "word_count" in item:
                    extra += f" | Words: {item['word_count']}"
                if "response_time" in item:
                    extra += f" | Response: {item['response_time']}s"
                if "redirect_to" in item and item["redirect_to"]:
                    extra += f" | Redirects to: {item['redirect_to']}"

                st.markdown(
                    f"<div style='background:#12121f; border-left:3px solid {color}; padding:0.5rem 0.8rem; "
                    f"border-radius:0 4px 4px 0; margin-bottom:0.4rem;'>"
                    f"<div style='font-size:0.85rem; color:#e8e8f0;'>{url}</div>"
                    f"<div style='font-size:0.78rem; color:#c8b4ff;'>{action}</div>"
                    f"{'<div style=\"font-size:0.68rem; color:#6b6b8a;\">' + extra.lstrip(' |') + '</div>' if extra else ''}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            if len(items) > 50:
                st.markdown(f"<div style='color:#6b6b8a; font-size:0.8rem;'>...and {len(items) - 50} more</div>", unsafe_allow_html=True)
