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
    """Find pages not in any cluster AND not user-marked as "no cluster
    needed", sorted by impressions."""
    clustered = {normalize_url(u) for u in page_topics.keys()}
    # User-flagged "this page doesn't need a cluster" — typically
    # blog/FAQ/help pages that don't fit any topical structure.
    # Persisted via _no_cluster_needed in PERSIST_KEYS.
    try:
        import streamlit as _st_nc
        _no_cluster = {normalize_url(u) for u in (_st_nc.session_state.get("_no_cluster_needed") or [])}
    except Exception:
        _no_cluster = set()
    unclustered = []
    for norm, r in audit_lookup.items():
        if (norm not in clustered
                and r.get("page_type") not in ("product",)
                and norm not in _no_cluster):
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


from utils.url_helpers import shorten_url_path as _shorten  # single source of truth


def _render_structure_actions(ideal, audit_lookup):
    """Merge / Delete / Create actions from AI ideal structure.
    Each item supports persistent ✓ Mark done / ↶ Undo via utils.action_status."""
    from utils import action_status as _as_sf
    from utils import action_ui as _aui_sf
    merges = ideal.get("merge", []) or []
    deletes = ideal.get("delete", []) or []
    creates = ideal.get("create", []) or []

    if not merges and not deletes and not creates:
        st.info("No structural actions found. Run Step 10 (Generate Ideal Structure) first.")
        return

    # Summary metrics — based on persistent action_status, not widget state
    merge_done = _as_sf.done_count("merge")
    delete_done = _as_sf.done_count("delete")
    create_done = _as_sf.done_count("create")

    c1, c2, c3 = st.columns(3)
    c1.metric("Merges", f"{merge_done}/{len(merges)} done")
    c2.metric("Deletes", f"{delete_done}/{len(deletes)} done")
    c3.metric("Creates", f"{create_done}/{len(creates)} done")

    st.markdown("---")

    # ── Merges ──
    if merges:
        st.markdown("### Merge pages")
        st.markdown(
            "<div style='background:#0d0d15; border:1px solid #2a2a40; border-radius:6px; padding:0.8rem; margin-bottom:1rem;'>"
            "<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600;'>What does this mean?</div>"
            "<div style='font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;'>"
            "These pages cover the same topic and compete with each other in Google. "
            "By merging them into one strong page, you consolidate all SEO authority in one place.</div>"
            "<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600; margin-top:0.5rem;'>How to do it:</div>"
            "<div style='font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;'>"
            "1. Copy any unique content from the FROM pages into the TO page<br>"
            "2. In Magento Admin: set up a <strong>301 redirect</strong> from each FROM URL to the TO URL "
            "(Catalog &rarr; URL Rewrites &rarr; Add URL Rewrite)<br>"
            "3. After verifying the redirects work, delete the old FROM pages</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        show_merge = _aui_sf.filter_toolbar("merge", len(merges), key_prefix="sf_")
        visible_merges = _aui_sf.filter_visible(merges, "merge", lambda m: stable_hash(m.get("to", "")), show_merge)
        for m in visible_merges:
            to_url = m.get("to", "")
            from_urls = m.get("from", [])
            why = m.get("why", "")
            to_audit = audit_lookup.get(normalize_url(to_url), {})
            to_impr = to_audit.get("impressions", 0) or 0

            from_lines = ""
            for fu in from_urls:
                fa = audit_lookup.get(normalize_url(fu), {})
                fi = fa.get("impressions", 0) or 0
                from_lines += f"<div style='color:#ff6644; font-size:0.8rem;'>FROM: {_shorten(fu)} <span style='color:#6b6b8a;'>({fi:,} impr)</span></div>"

            content = (
                f"<div style='background:#12121f; border-left:3px solid #ffaa33; padding:0.8rem; border-radius:0 6px 6px 0;'>"
                f"{from_lines}"
                f"<div style='color:#33dd88; font-size:0.8rem; margin-top:0.3rem;'>TO: {_shorten(to_url)} <span style='color:#6b6b8a;'>({to_impr:,} impr)</span></div>"
                f"<div style='color:#9b9bb8; font-size:0.75rem; margin-top:0.3rem;'>{why}</div>"
                f"</div>"
            )
            _aui_sf.render_action_row("merge", stable_hash(to_url), content, key_suffix="sf_m")
        _aui_sf.bulk_done_button("merge", [stable_hash(m.get("to", "")) for m in visible_merges], key_suffix="sf_m")

    # ── Deletes ──
    if deletes:
        st.markdown("### Remove or hide pages from Google")
        st.markdown(
            "<div style='background:#0d0d15; border:1px solid #2a2a40; border-radius:6px; padding:0.8rem; margin-bottom:1rem;'>"
            "<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600;'>What does this mean?</div>"
            "<div style='font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;'>"
            "These pages add no SEO value and dilute your site's quality signal to Google. "
            "But you have <strong>two options</strong> — you don't have to delete them:</div>"
            "<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600; margin-top:0.5rem;'>Option 1 — Block in robots.txt (best for most cases):</div>"
            "<div style='font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;'>"
            "Best for pages you still need (like /b2b) but don't want Google to crawl at all.<br>"
            "Add <code>Disallow: /b2b</code> (or the page path) to your <code>robots.txt</code> file. "
            "This saves crawl budget — Google won't even visit the page. "
            "The page stays live for visitors who have the direct link.</div>"
            "<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600; margin-top:0.5rem;'>Option 2 — Noindex (if page is linked from external sites):</div>"
            "<div style='font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;'>"
            "Use this if the page has backlinks from other websites that you want to preserve.<br>"
            "robots.txt blocks Google from reading the page, so it can't see the noindex tag. "
            "In that case: In Magento, open the page → Design tab → add <code>&lt;meta name=\"robots\" content=\"noindex,follow\"&gt;</code> "
            "to Custom Layout Update. Google still crawls it but won't show it in search results.</div>"
            "<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600; margin-top:0.5rem;'>Option 3 — Delete + redirect:</div>"
            "<div style='font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;'>"
            "Best for pages nobody needs anymore.<br>"
            "1. Set up a 301 redirect to the nearest relevant page<br>"
            "2. Then delete the page in Magento</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        # Note: this section uses the 'delete' action_type. The 3-option
        # checkboxes below (robots/noindex/delete) capture which approach
        # the user chose. Marking the row as DONE means "I handled it via
        # one of these methods — stop showing it".
        show_del = _aui_sf.filter_toolbar("delete", len(deletes), key_prefix="sf_del_")
        visible_deletes = _aui_sf.filter_visible(deletes, "delete", lambda d: stable_hash(d.get("url", "")), show_del)
        for d in visible_deletes:
            url = d.get("url", "")
            why = d.get("why", "")
            da = audit_lookup.get(normalize_url(url), {})
            impr = da.get("impressions", 0) or 0

            border_color = "#ff4455" if impr > 100 else "#2a2a40"
            warning = f"<div style='color:#ffaa33; font-size:0.7rem;'>This page has {impr:,} impressions — consider <strong>noindex</strong> instead of deleting</div>" if impr > 100 else ""

            content = (
                f"<div style='background:#12121f; border-left:3px solid {border_color}; padding:0.8rem; border-radius:0 6px 6px 0;'>"
                f"<div style='color:#e8e8f0; font-size:0.85rem;'>{_shorten(url)} <span style='color:#6b6b8a;'>({impr:,} impr)</span></div>"
                f"{warning}"
                f"<div style='color:#9b9bb8; font-size:0.75rem; margin-top:0.3rem;'>{why}</div>"
                f"</div>"
            )
            _aui_sf.render_action_row("delete", stable_hash(url), content, key_suffix="sf_d")
        _aui_sf.bulk_done_button("delete", [stable_hash(d.get("url", "")) for d in visible_deletes], key_suffix="sf_d")

    # ── Creates ──
    if creates:
        st.markdown("### Create new pages")
        st.markdown(
            "<div style='background:#0d0d15; border:1px solid #2a2a40; border-radius:6px; padding:0.8rem; margin-bottom:1rem;'>"
            "<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600;'>What does this mean?</div>"
            "<div style='font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;'>"
            "Google searches show demand for these topics, but your site has no page targeting them. "
            "Creating these pages captures traffic that currently goes to competitors.</div>"
            "<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600; margin-top:0.5rem;'>How to do it:</div>"
            "<div style='font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;'>"
            "1. Create the page in Magento (category or CMS page, depending on type)<br>"
            "2. Write quality content targeting the keyword shown below<br>"
            "3. Add internal links from related existing pages to the new page<br>"
            "4. Use the Content Generator in this tool to get AI-written text</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        show_cr = _aui_sf.filter_toolbar("create", len(creates), key_prefix="sf_cr_")
        visible_creates = _aui_sf.filter_visible(creates, "create", lambda c: stable_hash(c.get("url", "")), show_cr)
        for c in visible_creates:
            url = c.get("url", "")
            kw = c.get("kw", "")
            ctype = c.get("type", "")
            why = c.get("why", "")

            content = (
                f"<div style='background:#12121f; border-left:3px solid #5bb4d4; padding:0.8rem; border-radius:0 6px 6px 0;'>"
                f"<div style='color:#e8e8f0; font-size:0.85rem;'>{_shorten(url)} <span style='color:#5bb4d4; font-size:0.7rem;'>[{ctype}]</span></div>"
                f"<div style='color:#c8b4ff; font-size:0.8rem; margin-top:0.2rem;'>Target keyword: {kw}</div>"
                f"<div style='color:#9b9bb8; font-size:0.75rem; margin-top:0.3rem;'>{why}</div>"
                f"</div>"
            )
            _aui_sf.render_action_row("create", stable_hash(url), content, key_suffix="sf_c")
        _aui_sf.bulk_done_button("create", [stable_hash(c.get("url", "")) for c in visible_creates], key_suffix="sf_c")


def _render_unclustered(unclustered, cluster_names, clusters=None):
    """Tab 2: Assign unclustered pages to clusters.

    `clusters` is the full enriched cluster list (with topic + core_terms +
    queries). When provided, each unclustered page gets a pre-filled
    AI suggestion in its dropdown, scored by URL/title token overlap
    against each cluster's signature. The user can accept by clicking
    Save, or override by picking a different cluster from the dropdown.
    Without it, the dropdown is empty by default (legacy behavior).
    """
    from utils.cluster_suggest import suggest_cluster_for_page
    total = len(unclustered)

    if total == 0:
        st.success("All non-product pages are assigned to clusters!")
        return

    st.markdown(
        "<div style='background:#0d0d15; border:1px solid #2a2a40; border-radius:6px; padding:0.8rem; margin-bottom:1rem;'>"
        "<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600;'>What is this?</div>"
        "<div style='font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;'>"
        "A 'cluster' is a group of pages about the same topic (e.g. all dildo pages, all vibrator pages). "
        "Google rewards sites where related pages are clearly connected. "
        "These pages below don't belong to any topic group yet — they're invisible to Google's topic understanding.</div>"
        "<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600; margin-top:0.5rem;'>How to pick the right cluster:</div>"
        "<div style='font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;'>"
        "Look at the page URL — it usually tells you what the page is about. Then pick the cluster "
        "name that matches. Examples:<br>"
        "• <code>/bondage-bdsm/handklovar</code> → pick a cluster like 'bondage' or 'bdsm'<br>"
        "• <code>/sexleksaker/vibratorer/bullet</code> → pick a 'vibratorer' cluster<br>"
        "• <code>/blogg/guide-till-dildos</code> → pick a 'dildos' cluster<br><br>"
        "<strong>If no cluster fits:</strong> leave it blank. That's OK.<br>"
        "<strong>You don't need to do all at once:</strong> do 25, click Save, come back later for the next batch.</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Persistent assignment store — survives widget unmount.
    # Streamlit clears session_state[<widget_key>] when the widget is no
    # longer rendered (after pagination, filter change, or "Hide already
    # assigned" hiding the row). The selectbox itself is therefore NOT a
    # safe place to read the user's pick from at save time. We mirror
    # every pick into _cluster_assignment_picks where we control the
    # lifecycle, and the save handler reads from there.
    if "_cluster_assignment_picks" not in st.session_state:
        st.session_state["_cluster_assignment_picks"] = {}
    picks = st.session_state["_cluster_assignment_picks"]

    def _on_pick_change(url_hash: str):
        widget_val = st.session_state.get(f"sf_assign_widget_{url_hash}", "")
        if widget_val:
            st.session_state["_cluster_assignment_picks"][url_hash] = widget_val
        else:
            st.session_state["_cluster_assignment_picks"].pop(url_hash, None)

    # Count assigned (read from the persistent dict, NOT widget state)
    assigned = sum(1 for p in unclustered if picks.get(stable_hash(p["url"])))
    st.progress(assigned / max(1, total), text=f"{assigned}/{total} assigned to clusters")

    # Filter controls
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        type_filter = st.selectbox("Filter by type", ["All"] + sorted(set(p["page_type"] for p in unclustered)), key="sf_type_filter")
    with col_f2:
        show_assigned = st.checkbox("Hide already assigned", value=False, key="sf_hide_assigned")

    filtered = unclustered
    if type_filter != "All":
        filtered = [p for p in filtered if p["page_type"] == type_filter]
    if show_assigned:
        filtered = [p for p in filtered if not picks.get(stable_hash(p["url"]))]

    # ── Bulk "no cluster needed" actions ──
    # When the user has worked through all assignable pages and the
    # remainder is blogs/FAQs/help that don't fit any cluster, these
    # buttons let them mark the rest as permanently skipped — removed
    # from this list AND from the dashboard's "84.9% unclustered" stat.
    from utils.persistence import save_key as _sk_nc
    _no_cluster_now = list(st.session_state.get("_no_cluster_needed") or [])

    # ── Bulk "accept AI suggestions" action (Fix #4) ──
    # For pages with no GSC data (impressions=0), the cluster system used
    # to leave them stranded as "unclustered" with no help. Now each row
    # gets an AI suggestion based on URL/title token overlap. This bulk
    # button accepts all the suggestions on the currently filtered rows
    # at once, gated by a confidence threshold so low-confidence guesses
    # don't get auto-applied.
    #
    # Suggestions are cached per URL+cluster-set in session_state so
    # filter/pagination changes don't re-tokenize on every rerun.
    if clusters:
        _sugg_cache = st.session_state.setdefault("_sf_sugg_cache", {})
        # Cache key includes the clusters set so re-running clustering
        # invalidates stale suggestions. Length+first-topic is cheap
        # and good enough — there's no real risk of clusters being the
        # same length with different topics on a single session.
        _cache_key = (len(clusters), (clusters[0].get("topic", "") if clusters else ""))
        if _sugg_cache.get("_key") != _cache_key:
            _sugg_cache.clear()
            _sugg_cache["_key"] = _cache_key

        def _suggest_cached(p):
            k = p["url"]
            if k in _sugg_cache:
                return _sugg_cache[k]
            sugg = suggest_cluster_for_page(p["url"], p.get("title", ""), clusters, top_n=1)
            top = sugg[0] if sugg and sugg[0]["cluster"] in cluster_names else None
            _sugg_cache[k] = top
            return top

        suggestions_for_filtered = []
        for p in filtered:
            top = _suggest_cached(p)
            if top:
                suggestions_for_filtered.append((p, top))

        if suggestions_for_filtered:
            ai_col1, ai_col2, ai_col3 = st.columns([2, 1, 1])
            with ai_col2:
                min_score = st.number_input(
                    "Min confidence score",
                    min_value=5, max_value=50, value=15, step=5,
                    key="sf_min_sugg_score",
                    help="AI suggestion score required for bulk-accept. Higher = "
                         "more conservative (only obvious matches). Lower = more "
                         "pages auto-assigned but more chance of wrong cluster.",
                )
            above_threshold = [(p, s) for p, s in suggestions_for_filtered if s["score"] >= min_score]
            with ai_col1:
                if above_threshold and st.button(
                    f"🤖 Accept {len(above_threshold)} AI suggestions (score ≥ {min_score})",
                    key="sf_accept_ai_filtered",
                    help="Fills the dropdown for each filtered row whose AI "
                         "suggestion score is at or above the threshold. "
                         "You can still review and change any pick before "
                         "clicking Save below — nothing is committed until Save.",
                ):
                    _accepted = 0
                    for p, s in above_threshold:
                        url_hash = stable_hash(p["url"])
                        picks[url_hash] = s["cluster"]
                        # Update widget state too so the dropdown displays
                        # the accepted suggestion immediately on rerun.
                        st.session_state[f"sf_assign_widget_{url_hash}"] = s["cluster"]
                        _accepted += 1
                    st.success(
                        f"Pre-filled {_accepted} dropdowns with AI suggestions. "
                        f"Review the picks below and click Save when ready."
                    )
                    st.rerun()
            with ai_col3:
                st.caption(
                    f"{len(suggestions_for_filtered)} of {len(filtered)} filtered pages "
                    f"have AI suggestions"
                )

    bulk_col1, bulk_col2, bulk_col3 = st.columns([2, 2, 2])
    with bulk_col1:
        if filtered and st.button(
            f"🚫 Mark ALL {len(filtered)} (current filter) as 'no cluster needed'",
            key="sf_skip_filtered",
            help="Permanently removes every page in the current filtered "
                 "view from the unclustered list. Use after manually "
                 "assigning the ones that fit, when the remainder are "
                 "pages with no obvious cluster (blogs, FAQ, help).",
        ):
            _added = 0
            for p in filtered:
                if p["url"] not in _no_cluster_now:
                    _no_cluster_now.append(p["url"])
                    _added += 1
            st.session_state["_no_cluster_needed"] = _no_cluster_now
            try:
                _sk_nc("_no_cluster_needed")
            except Exception:
                pass
            st.success(f"Marked {_added} URLs as 'no cluster needed'.")
            st.rerun()
    with bulk_col2:
        # Bulk skip by page-type (any type, not just current filter)
        _types_in_list = sorted(set(p["page_type"] for p in unclustered))
        _skip_type = st.selectbox(
            "Skip ALL of type", ["—"] + _types_in_list,
            key="sf_skip_by_type",
            help="Bulk-mark every unclustered page of this type as "
                 "'no cluster needed'. Useful for blog/faq/info bulk-skip.",
        )
        if _skip_type != "—" and st.button(
            f"🚫 Apply: skip all {_skip_type}",
            key="sf_skip_by_type_apply",
        ):
            _added_t = 0
            for p in unclustered:
                if p["page_type"] == _skip_type and p["url"] not in _no_cluster_now:
                    _no_cluster_now.append(p["url"])
                    _added_t += 1
            st.session_state["_no_cluster_needed"] = _no_cluster_now
            try:
                _sk_nc("_no_cluster_needed")
            except Exception:
                pass
            st.success(f"Marked {_added_t} {_skip_type} URLs as 'no cluster needed'.")
            st.rerun()
    with bulk_col3:
        if _no_cluster_now:
            st.caption(f"Currently skipped: {len(_no_cluster_now)} URLs")
            if st.button(
                "↶ Restore all skipped to unclustered list",
                key="sf_restore_all_skipped",
                help="Clears the no-cluster-needed list — every previously "
                     "skipped page reappears in the unclustered list.",
            ):
                st.session_state["_no_cluster_needed"] = []
                try:
                    _sk_nc("_no_cluster_needed")
                except Exception:
                    pass
                st.rerun()

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
        url_hash = stable_hash(url)
        col1, col2, col3, col4, col5 = st.columns([4, 1, 1, 3, 1])

        # AI suggestion based on URL + title token overlap with each
        # cluster's signature. Reads from the same per-URL cache that
        # the bulk-accept button uses, so no double-computation.
        suggestion_meta = None
        if clusters:
            suggestion_meta = _suggest_cached(p)
        with col1:
            sugg_html = ""
            if suggestion_meta:
                _terms = ", ".join(suggestion_meta.get("match_terms", []))
                sugg_html = (
                    f"<div style='font-size:0.65rem; color:#5bb4d4; margin-top:0.15rem;'>"
                    f"AI suggests: <strong>{suggestion_meta['cluster']}</strong> "
                    f"(score {suggestion_meta['score']:.0f}, matched: {_terms})</div>"
                )
            st.markdown(
                f"<div style='font-size:0.8rem; color:#e8e8f0; padding-top:0.5rem;'>{_shorten(url)}</div>"
                f"<div style='font-size:0.65rem; color:#6b6b8a;'>{p['page_type']} · {p['word_count']} words</div>"
                f"{sugg_html}",
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(f"<div style='font-size:0.8rem; color:#9b9bb8; padding-top:0.5rem;'>{p['impressions']:,} impr</div>", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<div style='font-size:0.8rem; color:#9b9bb8; padding-top:0.5rem;'>{p['clicks']:,} clicks</div>", unsafe_allow_html=True)
        with col4:
            # Dropdown default = user's persisted pick if they've already
            # chosen one, else empty. We intentionally do NOT pre-fill the
            # widget with the AI suggestion here — that would let Save
            # commit AI guesses the user never actually approved
            # (destructive default). The suggestion text is shown as a
            # hint above, and there's a bulk "Accept all AI suggestions"
            # button below for explicit opt-in.
            existing = picks.get(url_hash, "")
            widget_key = f"sf_assign_widget_{url_hash}"
            if widget_key not in st.session_state:
                st.session_state[widget_key] = existing
            st.selectbox(
                "Cluster", options,
                key=widget_key,
                on_change=_on_pick_change,
                args=(url_hash,),
                label_visibility="collapsed",
            )
        with col5:
            # Per-row "this one doesn't need a cluster" toggle.
            if st.button(
                "🚫",
                key=f"sf_nc_{url_hash}",
                help="Mark this page as 'no cluster needed' — "
                     "removes it from the unclustered list permanently.",
            ):
                _ncl = list(st.session_state.get("_no_cluster_needed") or [])
                if url not in _ncl:
                    _ncl.append(url)
                    st.session_state["_no_cluster_needed"] = _ncl
                    try:
                        _sk_nc("_no_cluster_needed")
                    except Exception:
                        pass
                st.rerun()

    st.markdown("---")

    # Save button
    if st.button("Save cluster assignments", type="primary", key="sf_save_assign"):
        topic_clusters = st.session_state.get("topic_clusters", {})
        page_topics = topic_clusters.get("page_topics", {})
        clusters_list = topic_clusters.get("clusters", [])

        # Build cluster name → cluster data lookup
        cluster_by_name = {c["topic"]: c for c in clusters_list}

        saved = 0
        skipped_already = 0
        skipped_unknown_cluster = 0
        for p in unclustered:
            url_hash = stable_hash(p["url"])
            chosen = picks.get(url_hash, "")
            if not chosen:
                continue
            norm = normalize_url(p["url"])
            if norm in page_topics:
                skipped_already += 1
                continue  # Already assigned

            # Add to page_topics
            page_topics[norm] = [{"topic": chosen, "queries_in_topic": 0, "clicks": p["clicks"]}]

            # Add to cluster's pages list (defensive: cluster may not exist
            # under that name, or its pages key may be missing)
            cluster = cluster_by_name.get(chosen)
            if cluster is None:
                skipped_unknown_cluster += 1
            else:
                cluster.setdefault("pages", []).append({
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
            # Clear the persistent picks for saved rows so the dropdowns
            # reset and the same pick can't be saved twice.
            st.session_state["_cluster_assignment_picks"] = {}
            note = ""
            if skipped_already:
                note += f" ({skipped_already} already had a cluster, skipped)"
            if skipped_unknown_cluster:
                note += f" ({skipped_unknown_cluster} cluster name not found in topic_clusters)"
            st.success(f"Saved {saved} cluster assignments{note}")
            st.rerun()
        else:
            n_picks = len(picks)
            if n_picks == 0:
                st.info(
                    "No assignments to save — pick a cluster from the dropdown next "
                    "to a page first."
                )
            else:
                st.warning(
                    f"You picked clusters for {n_picks} pages, but none were saved. "
                    f"This usually means they were already assigned. Skipped: "
                    f"{skipped_already} already-clustered, "
                    f"{skipped_unknown_cluster} unknown cluster name."
                )


def _render_cluster_balance(clusters, audit_lookup):
    """Tab 3: Show cluster sizes and flag imbalances."""
    if not clusters:
        st.info("No clusters available. Run Step 5 (Topic Clusters) first.")
        return

    st.markdown(
        "<div style='background:#0d0d15; border:1px solid #2a2a40; border-radius:6px; padding:0.8rem; margin-bottom:1rem;'>"
        "<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600;'>What is this?</div>"
        "<div style='font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;'>"
        "Each topic cluster should ideally have 3-14 pages. Think of it like a bookshelf: "
        "a topic with only 1 book looks weak, but 20 books about the same thing is confusing.</div>"
        "<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600; margin-top:0.5rem;'>Color guide — what to do:</div>"
        "<div style='font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;'>"
        "<span style='color:#ff4455;'>RED — Needs more pages</span>: High traffic but only 1-2 pages. "
        "This is a big opportunity! Create 3-5 new pages: a guide, a comparison, a FAQ, or blog posts about subtopics. "
        "Use the Content Generator to write them.<br><br>"
        "<span style='color:#ffaa33;'>YELLOW — Too many pages</span>: 15+ pages competing for the same topic. "
        "Look at the page list below — are some pages very similar? Those should be merged (combine content into one page, "
        "redirect the other). Check the Structure Actions tab for specific merge suggestions.<br><br>"
        "<span style='color:#33dd88;'>GREEN — Healthy</span>: 3-14 pages. No action needed right now. Focus on red and yellow first.<br><br>"
        "<span style='color:#6b6b8a;'>GREY — Low priority</span>: Few pages AND low traffic. Fix these last, or ignore them for now.</div>"
        "</div>",
        unsafe_allow_html=True,
    )

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
                "<div style='background:#1a1020; border-radius:4px; padding:0.5rem; margin-top:0.4rem;'>"
                "<div style='color:#ffaa33; font-size:0.75rem; font-weight:600;'>ACTION NEEDED:</div>"
                "<div style='color:#c8b4ff; font-size:0.75rem; margin-top:0.2rem;'>"
                f"This topic gets {impr:,} searches but you only have {pc} page(s). Google doesn't see you as an expert here. "
                "To fix this:<br>"
                f"1. Go to the <strong>Unclustered Pages</strong> tab and assign relevant orphan pages to this cluster<br>"
                f"2. Create 2-4 new pages: a buying guide, a comparison article ('best {topic}'), or FAQ page<br>"
                f"3. Use the Content Generator in this tool to write them<br>"
                f"4. Link all pages in this cluster to each other</div></div>"
            )
        elif label == "OVERSATURATED":
            suggestion = (
                "<div style='background:#1a1a10; border-radius:4px; padding:0.5rem; margin-top:0.4rem;'>"
                "<div style='color:#ffaa33; font-size:0.75rem; font-weight:600;'>ACTION NEEDED:</div>"
                "<div style='color:#c8b4ff; font-size:0.75rem; margin-top:0.2rem;'>"
                f"With {pc} pages, these are likely competing in Google for the same keywords. "
                "To fix this:<br>"
                "1. Open the page list below and look for pages that are very similar<br>"
                "2. Merge similar pages: combine content into the strongest one, 301 redirect the rest<br>"
                "3. For pages that are different enough to keep: make sure each targets a DIFFERENT keyword<br>"
                "4. Check the Cannibalization view to see which specific keywords conflict</div></div>"
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
        "<div style='background:#0d0d15; border:1px solid #5533ff; border-radius:8px; padding:1rem; margin-bottom:1.5rem;'>"
        "<div style='font-size:1rem; color:#e8e8f0; font-weight:700; margin-bottom:0.5rem;'>How to work through this (do it in order)</div>"
        "<div style='font-size:0.85rem; color:#c8b4ff;'>"
        "<strong>Step A — Structure Actions tab:</strong> Review and approve merges, deletes, and new pages. "
        "Then do the actual changes in Magento (redirects, delete pages, create pages). "
        "This is typically 1-2 hours of work.<br><br>"
        "<strong>Step B — Unclustered Pages tab:</strong> Assign orphan pages to topic clusters. "
        "You don't need to do all 100+ at once — start with the top 25 (highest traffic) and save. "
        "Come back and do more later. This is just picking from a dropdown.<br><br>"
        "<strong>Step C — Cluster Balance tab:</strong> Review which clusters need more content (red) "
        "or have too many pages (yellow). Use this to plan what content to create or merge next.<br><br>"
        "<strong>When done:</strong> Go back to Run Pipeline and re-run Step 7 + 8. Then your individual "
        "page plans (Quick Wins, Action Plan) will work much better because the foundation is fixed."
        "</div></div>",
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
        # Pass the full clusters list so the dropdown can pre-fill an AI
        # suggestion for each unclustered page (esp. pages with 0 GSC data).
        _render_unclustered(unclustered, cluster_names, clusters=clusters)
    with tab3:
        _render_cluster_balance(clusters, audit_lookup)

    st.session_state["_structure_fix_viewed"] = True
