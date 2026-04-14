"""
Structure Fix — Actionable view for site-wide structural changes.
Makes merge/delete/create, unclustered pages, and cluster balance
manageable step by step.
"""

import streamlit as st
from utils.ui_helpers import normalize_url, stable_hash


def _audit_lookup():
    """Build normalized URL → audit result dict."""
    lookup = {}
    for r in st.session_state.get("audit_results", []):
        url = r.get("url", "")
        if url:
            lookup[normalize_url(url)] = r
    return lookup


def _get_unclustered(audit_lookup, page_topics):
    """Find pages not in any cluster, sorted by impressions."""
    clustered = {normalize_url(u) for u in page_topics.keys()}
    unclustered = []
    for norm, r in audit_lookup.items():
        if norm not in clustered and r.get("page_type") not in ("product",):
            unclustered.append({
                "url": r["url"],
                "norm": norm,
                "page_type": r.get("page_type", "unknown"),
                "impressions": r.get("impressions", 0) or 0,
                "clicks": r.get("clicks", 0) or 0,
                "word_count": r.get("word_count", 0) or 0,
                "title": r.get("title", ""),
            })
    unclustered.sort(key=lambda p: -p["impressions"])
    return unclustered


def _shorten(url, max_len=55):
    """Shorten URL for display."""
    path = url.split("//")[-1]
    if len(path) > max_len:
        return path[:max_len] + "..."
    return path


def _render_structure_actions(ideal, audit_lookup):
    """Tab 1: Merge / Delete / Create actions from ideal structure."""
    merges = ideal.get("merge", []) or []
    deletes = ideal.get("delete", []) or []
    creates = ideal.get("create", []) or []

    if not merges and not deletes and not creates:
        st.info("No structural actions found. Run Step 10 (Generate Ideal Structure) first.")
        return

    # Summary metrics
    merge_approved = sum(1 for m in merges if st.session_state.get(f"sf_merge_{stable_hash(m.get('to', ''))}"))
    delete_approved = sum(1 for d in deletes if st.session_state.get(f"sf_delete_{stable_hash(d.get('url', ''))}"))
    create_approved = sum(1 for c in creates if st.session_state.get(f"sf_create_{stable_hash(c.get('url', ''))}"))

    c1, c2, c3 = st.columns(3)
    c1.metric("Merges", f"{merge_approved}/{len(merges)} approved")
    c2.metric("Deletes", f"{delete_approved}/{len(deletes)} approved")
    c3.metric("Creates", f"{create_approved}/{len(creates)} approved")

    st.markdown("---")

    # ── Merges ──
    if merges:
        st.markdown("### Merge pages")
        st.markdown("<p style='color:#9b9bb8; font-size:0.85rem;'>Combine these pages to consolidate authority. Set up 301 redirects from the 'from' URLs to the 'to' URL.</p>", unsafe_allow_html=True)

        for m in merges:
            to_url = m.get("to", "")
            from_urls = m.get("from", [])
            why = m.get("why", "")
            to_audit = audit_lookup.get(normalize_url(to_url), {})
            to_impr = to_audit.get("impressions", 0) or 0

            # Card
            from_lines = ""
            for fu in from_urls:
                fa = audit_lookup.get(normalize_url(fu), {})
                fi = fa.get("impressions", 0) or 0
                from_lines += f"<div style='color:#ff6644; font-size:0.8rem;'>FROM: {_shorten(fu)} <span style='color:#6b6b8a;'>({fi:,} impr)</span></div>"

            st.markdown(
                f"<div style='background:#12121f; border-left:3px solid #ffaa33; padding:0.8rem; margin-bottom:0.5rem; border-radius:0 6px 6px 0;'>"
                f"{from_lines}"
                f"<div style='color:#33dd88; font-size:0.8rem; margin-top:0.3rem;'>TO: {_shorten(to_url)} <span style='color:#6b6b8a;'>({to_impr:,} impr)</span></div>"
                f"<div style='color:#9b9bb8; font-size:0.75rem; margin-top:0.3rem;'>{why}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.checkbox("Approved", key=f"sf_merge_{stable_hash(to_url)}")

    # ── Deletes ──
    if deletes:
        st.markdown("### Delete pages")
        st.markdown("<p style='color:#9b9bb8; font-size:0.85rem;'>Remove low-value pages that dilute site authority. Redirect to nearest relevant page.</p>", unsafe_allow_html=True)

        for d in deletes:
            url = d.get("url", "")
            why = d.get("why", "")
            da = audit_lookup.get(normalize_url(url), {})
            impr = da.get("impressions", 0) or 0

            border_color = "#ff4455" if impr > 100 else "#2a2a40"
            warning = f"<div style='color:#ff4455; font-size:0.7rem;'>WARNING: {impr:,} impressions — verify before deleting</div>" if impr > 100 else ""

            st.markdown(
                f"<div style='background:#12121f; border-left:3px solid {border_color}; padding:0.8rem; margin-bottom:0.5rem; border-radius:0 6px 6px 0;'>"
                f"<div style='color:#e8e8f0; font-size:0.85rem;'>{_shorten(url)} <span style='color:#6b6b8a;'>({impr:,} impr)</span></div>"
                f"{warning}"
                f"<div style='color:#9b9bb8; font-size:0.75rem; margin-top:0.3rem;'>{why}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.checkbox("Approved", key=f"sf_delete_{stable_hash(url)}")

    # ── Creates ──
    if creates:
        st.markdown("### Create new pages")
        st.markdown("<p style='color:#9b9bb8; font-size:0.85rem;'>New pages needed to fill content gaps and strengthen cluster coverage.</p>", unsafe_allow_html=True)

        for c in creates:
            url = c.get("url", "")
            kw = c.get("kw", "")
            ctype = c.get("type", "")
            why = c.get("why", "")

            st.markdown(
                f"<div style='background:#12121f; border-left:3px solid #5bb4d4; padding:0.8rem; margin-bottom:0.5rem; border-radius:0 6px 6px 0;'>"
                f"<div style='color:#e8e8f0; font-size:0.85rem;'>{_shorten(url)} <span style='color:#5bb4d4; font-size:0.7rem;'>[{ctype}]</span></div>"
                f"<div style='color:#c8b4ff; font-size:0.8rem; margin-top:0.2rem;'>Target keyword: {kw}</div>"
                f"<div style='color:#9b9bb8; font-size:0.75rem; margin-top:0.3rem;'>{why}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.checkbox("Approved", key=f"sf_create_{stable_hash(url)}")


def _render_unclustered(unclustered, cluster_names):
    """Tab 2: Assign unclustered pages to clusters."""
    total = len(unclustered)

    if total == 0:
        st.success("All non-product pages are assigned to clusters!")
        return

    # Count assigned
    assigned = sum(1 for p in unclustered if st.session_state.get(f"sf_assign_{stable_hash(p['url'])}", ""))
    st.progress(assigned / max(1, total), text=f"{assigned}/{total} assigned to clusters")

    # Filter controls
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        type_filter = st.selectbox("Filter by type", ["All"] + sorted(set(p["page_type"] for p in unclustered)), key="sf_type_filter")
    with col_f2:
        show_assigned = st.checkbox("Hide already assigned", value=True, key="sf_hide_assigned")

    filtered = unclustered
    if type_filter != "All":
        filtered = [p for p in filtered if p["page_type"] == type_filter]
    if show_assigned:
        filtered = [p for p in filtered if not st.session_state.get(f"sf_assign_{stable_hash(p['url'])}", "")]

    # Pagination
    per_page = 25
    total_filtered = len(filtered)
    max_page = max(1, (total_filtered + per_page - 1) // per_page)
    current_page = st.number_input("Page", 1, max_page, 1, key="sf_unclust_page")
    start = (current_page - 1) * per_page
    visible = filtered[start:start + per_page]

    st.markdown(f"**Showing {start+1}-{min(start+per_page, total_filtered)} of {total_filtered} unclustered pages**")

    options = [""] + cluster_names

    for p in visible:
        url = p["url"]
        col1, col2, col3, col4 = st.columns([4, 1, 1, 3])
        with col1:
            st.markdown(
                f"<div style='font-size:0.8rem; color:#e8e8f0; padding-top:0.5rem;'>{_shorten(url)}</div>"
                f"<div style='font-size:0.65rem; color:#6b6b8a;'>{p['page_type']} · {p['word_count']} words</div>",
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(f"<div style='font-size:0.8rem; color:#9b9bb8; padding-top:0.5rem;'>{p['impressions']:,} impr</div>", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<div style='font-size:0.8rem; color:#9b9bb8; padding-top:0.5rem;'>{p['clicks']:,} clicks</div>", unsafe_allow_html=True)
        with col4:
            st.selectbox("Cluster", options, key=f"sf_assign_{stable_hash(url)}", label_visibility="collapsed")

    st.markdown("---")

    # Save button
    if st.button("Save cluster assignments", type="primary", key="sf_save_assign"):
        topic_clusters = st.session_state.get("topic_clusters", {})
        page_topics = topic_clusters.get("page_topics", {})
        clusters_list = topic_clusters.get("clusters", [])

        # Build cluster name → cluster data lookup
        cluster_by_name = {c["topic"]: c for c in clusters_list}

        saved = 0
        for p in unclustered:
            chosen = st.session_state.get(f"sf_assign_{stable_hash(p['url'])}", "")
            if not chosen:
                continue
            norm = normalize_url(p["url"])
            if norm in page_topics:
                continue  # Already assigned

            # Add to page_topics
            page_topics[norm] = [{"topic": chosen, "queries_in_topic": 0, "clicks": p["clicks"]}]

            # Add to cluster's pages list
            cluster = cluster_by_name.get(chosen)
            if cluster:
                cluster["pages"].append({
                    "page": norm,
                    "query_count": 0,
                    "total_clicks": p["clicks"],
                    "total_impressions": p["impressions"],
                    "avg_position": 0,
                })
                cluster["page_count"] = len(cluster["pages"])

            saved += 1

        if saved:
            topic_clusters["page_topics"] = page_topics
            st.session_state["topic_clusters"] = topic_clusters
            from utils.persistence import save
            save("topic_clusters")
            st.success(f"Saved {saved} cluster assignments")
            st.rerun()
        else:
            st.info("No new assignments to save")


def _render_cluster_balance(clusters, audit_lookup):
    """Tab 3: Show cluster sizes and flag imbalances."""
    if not clusters:
        st.info("No clusters available. Run Step 5 (Topic Clusters) first.")
        return

    # Classify clusters
    red = []  # 1-2 pages, high impressions
    yellow = []  # 15+ pages
    green = []  # 3-14 pages
    grey = []  # 1-2 pages, low impressions

    median_impr = sorted(c.get("total_impressions", 0) for c in clusters)[len(clusters) // 2] if clusters else 0

    for c in clusters:
        pc = c.get("page_count", 0)
        impr = c.get("total_impressions", 0)
        if pc <= 2 and impr >= max(200, median_impr * 0.5):
            red.append(c)
        elif pc >= 15:
            yellow.append(c)
        elif pc <= 2:
            grey.append(c)
        else:
            green.append(c)

    # Summary
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Needs expansion", len(red), help="1-2 pages with significant traffic")
    c2.metric("Oversaturated", len(yellow), help="15+ pages, consider consolidating")
    c3.metric("Healthy", len(green), help="3-14 pages")
    c4.metric("Low priority", len(grey), help="1-2 pages, low traffic")

    st.markdown("---")

    # Render all clusters sorted: red first, then yellow, then grey, then green
    all_sorted = (
        [(c, "#ff4455", "NEEDS EXPANSION") for c in sorted(red, key=lambda x: -x.get("total_impressions", 0))]
        + [(c, "#ffaa33", "OVERSATURATED") for c in sorted(yellow, key=lambda x: -x.get("page_count", 0))]
        + [(c, "#6b6b8a", "LOW PRIORITY") for c in sorted(grey, key=lambda x: -x.get("total_impressions", 0))]
        + [(c, "#33dd88", "HEALTHY") for c in sorted(green, key=lambda x: -x.get("total_impressions", 0))]
    )

    for cluster, color, label in all_sorted:
        topic = cluster.get("topic", "?")
        pc = cluster.get("page_count", 0)
        qc = cluster.get("query_count", 0)
        impr = cluster.get("total_impressions", 0)
        clicks = cluster.get("total_clicks", 0)
        pages = cluster.get("pages", [])

        suggestion = ""
        if label == "NEEDS EXPANSION":
            suggestion = (
                "<div style='color:#ffaa33; font-size:0.75rem; margin-top:0.3rem;'>"
                f"This cluster has {impr:,} impressions but only {pc} pages. "
                "Add 3-5 supporting pages: blog posts, guides, or comparison articles targeting subtopics.</div>"
            )
        elif label == "OVERSATURATED":
            suggestion = (
                "<div style='color:#ffaa33; font-size:0.75rem; margin-top:0.3rem;'>"
                f"{pc} pages compete for the same topic. Consider merging similar pages or splitting into sub-clusters.</div>"
            )

        # Page list for expander
        page_lines = []
        for p in sorted(pages, key=lambda x: -(x.get("total_impressions", 0) or 0)):
            p_url = p.get("page", "")
            p_impr = p.get("total_impressions", 0) or 0
            p_clicks = p.get("total_clicks", 0) or 0
            page_lines.append(f"- `{_shorten(p_url, 60)}` — {p_impr:,} impr, {p_clicks:,} clicks")

        st.markdown(
            f"<div style='background:#12121f; border-left:3px solid {color}; padding:0.8rem; margin-bottom:0.4rem; border-radius:0 6px 6px 0;'>"
            f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
            f"<div style='font-size:0.9rem; font-weight:600; color:#e8e8f0;'>{topic}</div>"
            f"<span style='font-size:0.6rem; color:{color}; background:{color}22; padding:0.1rem 0.4rem; border-radius:3px;'>{label}</span>"
            f"</div>"
            f"<div style='font-size:0.75rem; color:#9b9bb8; margin-top:0.2rem;'>"
            f"{pc} pages · {qc} keywords · {impr:,} impressions · {clicks:,} clicks</div>"
            f"{suggestion}"
            f"</div>",
            unsafe_allow_html=True,
        )

        if pages:
            with st.expander(f"Show {len(pages)} pages in '{topic}'", expanded=False):
                st.markdown("\n".join(page_lines))


def render():
    st.markdown("## Structure Fix")
    st.markdown(
        "<p style='color:#9b9bb8; margin-bottom:1.5rem;'>"
        "Fix site-wide structural issues before optimizing individual pages. "
        "Work through the tabs left to right.</p>",
        unsafe_allow_html=True,
    )

    # Guard: need data
    if "audit_results" not in st.session_state:
        st.warning("Run **Step 6 (Page Auditor)** first")
        return
    if "topic_clusters" not in st.session_state:
        st.warning("Run **Step 5 (Topic Clusters)** first")
        return

    audit_lookup = _audit_lookup()
    topic_clusters = st.session_state.get("topic_clusters", {})
    page_topics = topic_clusters.get("page_topics", {})
    clusters = topic_clusters.get("clusters", [])
    ideal = st.session_state.get("_ideal_structure", {})

    # Count unclustered for tab label
    unclustered = _get_unclustered(audit_lookup, page_topics)

    tab1, tab2, tab3 = st.tabs([
        f"Structure Actions ({len(ideal.get('merge', []))} merge, {len(ideal.get('delete', []))} delete, {len(ideal.get('create', []))} create)",
        f"Unclustered Pages ({len(unclustered)})",
        f"Cluster Balance ({len(clusters)} clusters)",
    ])

    with tab1:
        _render_structure_actions(ideal, audit_lookup)
    with tab2:
        cluster_names = sorted(set(c.get("topic", "") for c in clusters if c.get("topic")))
        _render_unclustered(unclustered, cluster_names)
    with tab3:
        _render_cluster_balance(clusters, audit_lookup)

    st.session_state["_structure_fix_viewed"] = True
