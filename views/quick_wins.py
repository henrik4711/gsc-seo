"""
Quick Wins — One page at a time, fully generated, approve/reject workflow.
For users who want fast wins without navigating multiple menus.
"""

import re
import streamlit as st
from config import get_anthropic_key, has_anthropic_key
from utils.ui_helpers import stable_hash, normalize_url, shorten_url, extract_content_summary, show_ai_error, render_recommendation_diff


# ── Site-action drilldown helpers ─────────────────────────────────────
# Convert AI's high-level priority actions ("Audit and assign 329 unclustered
# pages…") into concrete per-page todos so the user never has to figure out
# "which 329 pages?" themselves.

_MATCH_TOKEN_RE = re.compile(r"[a-zåäöæøéèà0-9]+")
_MATCH_STOP_BASE = {
    "and", "the", "for", "with", "this", "that", "from", "are", "was",
    "och", "att", "att", "som", "med", "till", "kop", "kopa", "kob",
    "sex", "sexleksaker",  # ubiquitous in this niche, drowns out signal
    "html", "www", "com", "https", "http",
}


def _get_site_brand_tokens() -> set:
    """Tokens derived from the site's own domain name (e.g. www.mshop.se → {"mshop"}).
    These appear in nearly every page title because of the "| Mshop" suffix
    and would otherwise dominate cluster matching, sending every page into
    a noise cluster like "brand_mshop". Filtered both from page tokens and
    from cluster signatures."""
    site = (st.session_state.get("gsc_site") or "").lower()
    if not site:
        return set()
    try:
        from urllib.parse import urlparse
        netloc = urlparse(site).netloc or site
    except Exception:
        netloc = site
    netloc = netloc.replace("https://", "").replace("http://", "")
    if netloc.startswith("www."):
        netloc = netloc[4:]
    stem = netloc.split(".")[0] if netloc else ""
    if not stem or len(stem) < 3:
        return set()
    return {stem}


def _tokenize_for_match(text: str) -> set:
    if not text:
        return set()
    stop = _MATCH_STOP_BASE | _get_site_brand_tokens()
    return {t for t in _MATCH_TOKEN_RE.findall(text.lower()) if len(t) >= 3 and t not in stop}


def _is_site_brand_cluster(cluster_topic: str) -> bool:
    """True if the cluster is just the site's own brand (e.g. 'brand_mshop').
    These are noise — visitors searching the site name should land on the
    homepage, not need their own topical cluster. Filtered from drilldowns."""
    if not cluster_topic:
        return False
    t = cluster_topic.lower().strip()
    brands = _get_site_brand_tokens()
    if not brands:
        return False
    for b in brands:
        if t == b or t == f"brand_{b}":
            return True
    return False


def _suggest_cluster_for_page(url: str, title: str, clusters: list, top_n: int = 1) -> list:
    """Score each cluster against URL/title tokens; return top matches with overlap terms."""
    page_tokens = _tokenize_for_match(f"{url} {title}")
    if not page_tokens:
        return []
    scored = []
    for c in clusters:
        topic = c.get("topic", "") or ""
        # Site-brand cluster ('brand_mshop') is noise — never suggest it.
        if _is_site_brand_cluster(topic):
            continue
        core_terms = c.get("core_terms", []) or []
        queries = c.get("queries", []) or []
        sig_text = topic + " " + " ".join(core_terms) + " " + " ".join(queries[:30])
        sig = _tokenize_for_match(sig_text)
        if not sig:
            continue
        overlap = page_tokens & sig
        if not overlap:
            continue
        # Score = overlap size weighted by inverse cluster signature size (favor specific clusters)
        score = len(overlap) * 100 / max(8, len(sig))
        scored.append((score, len(overlap), topic, sorted(overlap)[:4]))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [{"cluster": t[2], "score": round(t[0], 1), "match_terms": t[3]} for t in scored[:top_n]]


def _classify_priority_action(action_text: str) -> str:
    """Categorize a site-wide priority action by keywords."""
    s = (action_text or "").lower()
    if any(k in s for k in ["unclustered", "outside cluster", "without cluster",
                            "no cluster", "fragment", "topical authority"]):
        return "assign_clusters"
    if any(k in s for k in ["informational", "buying guide", "blog post", "blog content",
                            "educational", "guides and educational"]):
        return "informational_gap"
    if any(k in s for k in ["thin", "consolidate"]):
        return "thin_pages"
    if any(k in s for k in ["expand", "underrepresented", "additional relevant",
                            "underserved", "underdeveloped"]):
        return "expand_clusters"
    return "other"


def _resolve_priority_action(action_text: str, df_structure, topic_clusters: dict) -> dict:
    """Map a site-wide priority action to concrete per-page suggestions."""
    cat = _classify_priority_action(action_text)
    clusters = (topic_clusters or {}).get("clusters", []) or []
    out = {"category": cat, "pages": [], "note": ""}
    if df_structure is None or len(df_structure) == 0:
        return out

    df = df_structure

    if cat == "assign_clusters":
        if "Cluster(s)" not in df.columns:
            return out
        unclustered = df[df["Cluster(s)"].fillna("") == ""].copy()
        if unclustered.empty:
            return out
        # Drop the homepage — it doesn't belong in a topical cluster
        # (it's the architecture root). It was showing up in this list
        # with empty path and tens of thousands of impressions because
        # GSC traffic for the site name lands there.
        from urllib.parse import urlparse as _up_clusters
        def _is_homepage(_u: str) -> bool:
            try:
                p = _up_clusters(str(_u or "")).path
            except Exception:
                p = str(_u or "")
            return p.strip("/") == ""
        unclustered = unclustered[~unclustered["URL"].apply(_is_homepage)]
        if unclustered.empty:
            return out
        if "Impressions" in unclustered.columns:
            unclustered = unclustered.sort_values("Impressions", ascending=False)
        rows = []
        for _, r in unclustered.head(80).iterrows():
            url = r["URL"]
            title = (r.get("Title") or "")
            suggestions = _suggest_cluster_for_page(url, title, clusters, top_n=2)
            if suggestions:
                top = suggestions[0]
                action = (
                    f"Assign to cluster **{top['cluster']}** "
                    f"(matched on: {', '.join(top['match_terms'])}). "
                    f"Add 1 link from this page to the cluster's hub URL in intro, "
                    f"and 2-3 contextual links to sibling spokes in body."
                )
                if len(suggestions) > 1:
                    action += f" Alt cluster if better fit: **{suggestions[1]['cluster']}**."
            else:
                impressions = int(r.get("Impressions", 0) or 0)
                if impressions < 50:
                    action = ("No matching cluster found. Low impressions (<50/30d) "
                              "→ schedule for **delete or 301 redirect** to nearest parent category.")
                else:
                    action = ("No matching cluster found, but page has traffic. "
                              "→ **Create a new cluster** seeded with this page's primary keyword, "
                              "or merge into the closest existing cluster manually.")
            rows.append({
                "url": url,
                "page_type": r.get("Page Type", ""),
                "impressions": int(r.get("Impressions", 0) or 0),
                "clicks": int(r.get("Clicks", 0) or 0),
                "words": int(r.get("Word Count", 0) or 0),
                "suggested_cluster": suggestions[0]["cluster"] if suggestions else None,
                "suggested_action": action,
            })
        out["pages"] = rows
        out["note"] = f"Showing top {len(rows)} unclustered pages by impressions (highest-leverage first)."
        return out

    if cat == "thin_pages":
        if "Word Count" not in df.columns:
            return out
        thin = df[df["Word Count"].fillna(0) < 300].copy()
        if "Page Type" in thin.columns:
            thin = thin[thin["Page Type"].isin(["category", "subcategory", "brand"])]
        if thin.empty:
            return out
        if "Impressions" in thin.columns:
            thin = thin.sort_values("Impressions", ascending=False)
        rows = []
        for _, r in thin.head(60).iterrows():
            words = int(r.get("Word Count", 0) or 0)
            ptype = r.get("Page Type", "")
            target = 600 if ptype in ("category", "subcategory") else 400
            need = max(0, target - words)
            impressions = int(r.get("Impressions", 0) or 0)
            if impressions < 30 and words < 100:
                action = ("Almost empty AND no traffic → **mark for delete or merge** "
                          "into the parent category. Open Site Cleanup → Merge/Delete to schedule.")
            else:
                action = (
                    f"Add ~{need} words: **intro (60-100 words) + buying-guide (200-300) + "
                    f"FAQ (3-5 Q&A) + bottom text (150-200)**. "
                    f"Open this URL in **Per-page work** tab → Quick Wins panel auto-generates all four."
                )
            rows.append({
                "url": r["URL"],
                "page_type": ptype,
                "impressions": impressions,
                "clicks": int(r.get("Clicks", 0) or 0),
                "words": words,
                "suggested_action": action,
            })
        out["pages"] = rows
        out["note"] = f"Showing thin category/brand pages (<300 words), top {len(rows)} by impressions."
        return out

    if cat == "expand_clusters":
        # Pull cluster names mentioned explicitly inside parens, else fall back
        # to the smallest clusters by page count.
        mentioned_raw = re.findall(r"\(([^)]+)\)", action_text)
        mentioned_tokens = set()
        for m in mentioned_raw:
            for piece in re.split(r"[,;]| and ", m):
                p = piece.strip().lower()
                if len(p) >= 3:
                    mentioned_tokens.add(p)
        rows = []
        for c in clusters:
            topic = (c.get("topic") or "").lower()
            # Site-brand cluster is noise — never recommend "expand" it.
            if _is_site_brand_cluster(topic):
                continue
            page_count = c.get("page_count", 0)
            in_mentioned = any(tok in topic or topic in tok for tok in mentioned_tokens) if mentioned_tokens else False
            is_small = page_count <= 2
            if not (in_mentioned or (not mentioned_tokens and is_small)):
                continue
            pages = c.get("pages", []) or []
            page_urls = [p.get("page", "") for p in pages]
            queries = c.get("queries", []) or []
            existing = ", ".join(shorten_url(u) for u in page_urls[:3]) or "(no pages yet)"
            top_queries = ", ".join(queries[:5]) or "(no queries indexed)"
            action = (
                f"Cluster **{c.get('topic')}** has {page_count} page(s): {existing}. "
                f"→ Create **2-3 new spoke articles** (use **New Articles** tab) targeting these queries: "
                f"_{top_queries}_. Each new spoke must link to the cluster hub, and the hub must "
                f"add a contextual link back to each new spoke."
            )
            rows.append({
                "url": page_urls[0] if page_urls else "",
                "page_type": "cluster",
                "impressions": c.get("total_impressions", 0),
                "clicks": c.get("total_clicks", 0),
                "words": 0,
                "cluster": c.get("topic", ""),
                "suggested_action": action,
            })
        rows.sort(key=lambda r: -r["impressions"])
        out["pages"] = rows[:15]
        out["note"] = (f"Underrepresented clusters identified: {len(out['pages'])}."
                       if out["pages"] else "")
        return out

    if cat == "informational_gap":
        rows = []
        for c in clusters[:25]:
            # Skip the site-brand noise cluster — visitors searching the
            # site name go to the homepage; they don't need a buying guide.
            if _is_site_brand_cluster(c.get("topic", "") or ""):
                continue
            pages = c.get("pages", []) or []
            has_blog = any(
                "/blog/" in (p.get("page", "") or "").lower()
                or "/artikel" in (p.get("page", "") or "").lower()
                or "/guide" in (p.get("page", "") or "").lower()
                for p in pages
            )
            if has_blog:
                continue
            if (c.get("total_impressions", 0) or 0) < 100:
                continue
            queries = c.get("queries", []) or []
            informational = [q for q in queries if any(
                kw in q.lower() for kw in ("hur", "vad", "varför", "guide", "bäst",
                                           "hvordan", "hvad", "hvorfor", "bedst",
                                           "how", "what", "why", "best")
            )]
            target_queries = informational[:4] if informational else queries[:4]
            if not target_queries:
                continue
            action = (
                f"Cluster **{c.get('topic')}** has product/category pages but **no blog/guide content** "
                f"({c.get('total_impressions', 0)} impressions/30d). "
                f"→ Create **1 buying guide + 1 how-to article** in **New Articles** tab. "
                f"Suggested target queries: _{', '.join(target_queries)}_. "
                f"Link both new articles → cluster hub category, and add a 'Read more' card on the hub → both articles."
            )
            rows.append({
                "url": "",
                "page_type": "blog_gap",
                "impressions": c.get("total_impressions", 0),
                "clicks": c.get("total_clicks", 0),
                "words": 0,
                "cluster": c.get("topic", ""),
                "suggested_action": action,
            })
        rows.sort(key=lambda r: -r["impressions"])
        out["pages"] = rows[:10]
        out["note"] = (f"Top {len(out['pages'])} commercial clusters lacking informational content."
                       if out["pages"] else "")
        return out

    return out


def _get_or_build_df_structure_cached():
    """Lazy build the Site Structure dataframe used by drilldown — once per session."""
    df = st.session_state.get("_qw_df_structure_cache")
    if df is not None:
        return df
    try:
        from views.site_map_export import _build_site_structure
        df = _build_site_structure(
            st.session_state.get("audit_results", []),
            st.session_state.get("gsc_data"),
            st.session_state.get("topic_clusters", {}),
            st.session_state.get("page_authority"),
        )
        st.session_state["_qw_df_structure_cache"] = df
        return df
    except Exception as e:
        st.session_state["_qw_df_structure_error"] = str(e)
        return None


def _build_consolidated_action_plan(site_validation: dict, df_structure, topic_clusters: dict) -> list:
    """Resolve every priority action into a flat list of (impact, action, page-row) entries.

    Output is one row per page (or per cluster, for the cluster-level actions),
    grouped/sorted so the user can read top-to-bottom and act.
    """
    entries = []
    if not isinstance(site_validation, dict):
        return entries
    impact_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "?": 3}
    seen_url_action = set()
    for pa in site_validation.get("priority_actions", []) or []:
        if isinstance(pa, dict):
            action_text = pa.get("action", "")
            impact = (pa.get("impact") or "?").upper()
        else:
            action_text = str(pa)
            impact = "?"
        cat = _classify_priority_action(action_text)
        if cat == "other" or df_structure is None:
            continue
        resolved = _resolve_priority_action(action_text, df_structure, topic_clusters)
        for row in resolved.get("pages", []):
            url = row.get("url", "") or ""
            cluster = row.get("cluster", "") or ""
            key = (url, cluster, action_text)
            if key in seen_url_action:
                continue
            seen_url_action.add(key)
            entries.append({
                "impact": impact,
                "impact_rank": impact_rank.get(impact, 3),
                "category": cat,
                "action_label": action_text,
                "url": url,
                "cluster": cluster,
                "page_type": row.get("page_type", ""),
                "impressions": row.get("impressions", 0) or 0,
                "clicks": row.get("clicks", 0) or 0,
                "words": row.get("words", 0) or 0,
                "suggested_cluster": row.get("suggested_cluster"),
                "suggested_action": row.get("suggested_action", ""),
            })
    # Sort: by impact (HIGH first), then impressions desc
    entries.sort(key=lambda e: (e["impact_rank"], -e["impressions"]))
    return entries


_CATEGORY_LABEL = {
    "assign_clusters": "Assign to a topical cluster",
    "thin_pages": "Thicken thin category page",
    "expand_clusters": "Expand under-served cluster",
    "informational_gap": "Add blog / buying-guide content",
}


def _action_plan_to_markdown(entries: list, site_validation: dict) -> str:
    """Render the consolidated plan as a single markdown document for export."""
    out = []
    health = site_validation.get("overall_health_score", 0) if isinstance(site_validation, dict) else 0
    summary = site_validation.get("summary", "") if isinstance(site_validation, dict) else ""
    out.append(f"# Site Action Plan — Health {health}/100\n")
    if summary:
        out.append(f"> {summary}\n")
    out.append(f"_Total actionable items: **{len(entries)}**, sorted by impact and impressions._\n")
    out.append("")

    # Group by category for readable export
    from collections import defaultdict
    grouped = defaultdict(list)
    for e in entries:
        grouped[e["category"]].append(e)

    for cat in ("assign_clusters", "thin_pages", "expand_clusters", "informational_gap"):
        rows = grouped.get(cat, [])
        if not rows:
            continue
        out.append(f"\n## {_CATEGORY_LABEL.get(cat, cat)} — {len(rows)} item(s)\n")
        for i, e in enumerate(rows, 1):
            target = e["url"] or (f"Cluster: {e['cluster']}" if e["cluster"] else "(no target)")
            out.append(f"### {i}. [{e['impact']}] {target}")
            meta_bits = []
            if e["page_type"]:
                meta_bits.append(e["page_type"])
            if e["words"]:
                meta_bits.append(f"{e['words']} words")
            if e["impressions"]:
                meta_bits.append(f"{e['impressions']:,} impr/30d")
            if e["clicks"]:
                meta_bits.append(f"{e['clicks']:,} clicks/30d")
            if meta_bits:
                out.append(f"_{' · '.join(meta_bits)}_\n")
            out.append(f"**Action:** {e['suggested_action']}\n")
            out.append(f"_Site-wide priority this addresses:_ {e['action_label']}\n")
    return "\n".join(out)


def _render_site_action_plan_tab():
    """Tab renderer: one screen with every actionable page + per-page concrete action."""
    st.markdown("### 📋 Site Action Plan")
    st.markdown(
        "<p style='color:#9b9bb8; font-size:0.85rem; margin-bottom:1rem;'>"
        "Every page that the AI flagged as part of a site-wide priority, "
        "expanded into a concrete per-page action. Sorted by impact, then traffic. "
        "Work top-to-bottom or hand the markdown export to a team member.</p>",
        unsafe_allow_html=True,
    )

    site_validation = st.session_state.get("_site_validation")
    if not site_validation or not isinstance(site_validation, dict):
        st.warning(
            "Site structure validation not yet run. Go to **⚡ Run Pipeline → Step 10: Site Validation** first."
        )
        return

    topic_clusters = st.session_state.get("topic_clusters", {}) or {}
    df_structure = _get_or_build_df_structure_cached()
    if df_structure is None:
        err = st.session_state.get("_qw_df_structure_error", "")
        st.error(
            f"Could not build the site-structure dataframe needed for the action plan. "
            f"Re-run the pipeline (Step 1–9). {('Error: ' + err) if err else ''}"
        )
        return

    entries = _build_consolidated_action_plan(site_validation, df_structure, topic_clusters)
    if not entries:
        st.info(
            "No site-wide priority actions resolve to specific pages right now. Either the AI's "
            "priority actions are purely architectural this run, or required pipeline data is missing."
        )
        return

    # ── Top bar: counts + filters + export ─────────────────────────
    bar_l, bar_m, bar_r = st.columns([2, 2, 1])
    with bar_l:
        impact_counts = {}
        for e in entries:
            impact_counts[e["impact"]] = impact_counts.get(e["impact"], 0) + 1
        bits = []
        for k in ("HIGH", "MEDIUM", "LOW"):
            if k in impact_counts:
                color = {"HIGH": "#ff4455", "MEDIUM": "#ffaa33", "LOW": "#5bb4d4"}[k]
                bits.append(f"<span style='color:{color}; font-weight:600;'>{impact_counts[k]} {k}</span>")
        st.markdown(
            f"<div style='font-size:0.85rem; color:#9b9bb8;'>"
            f"<strong style='color:#e8e8f0;'>{len(entries)} actionable items</strong>"
            f"{' — ' + ' · '.join(bits) if bits else ''}</div>",
            unsafe_allow_html=True,
        )

    with bar_m:
        cat_options = ["All categories"] + [
            _CATEGORY_LABEL[c] for c in ("assign_clusters", "thin_pages", "expand_clusters", "informational_gap")
            if any(e["category"] == c for e in entries)
        ]
        cat_pick = st.selectbox(
            "Filter by action type",
            cat_options,
            key="_qw_plan_cat_filter",
            label_visibility="collapsed",
        )

    with bar_r:
        md_export = _action_plan_to_markdown(entries, site_validation)
        st.download_button(
            "📄 Export markdown",
            data=md_export,
            file_name="site_action_plan.md",
            mime="text/markdown",
            key="_qw_plan_export",
            use_container_width=True,
        )

    # ── Filter ──
    if cat_pick != "All categories":
        rev_label = {v: k for k, v in _CATEGORY_LABEL.items()}
        wanted_cat = rev_label.get(cat_pick)
        filtered = [e for e in entries if e["category"] == wanted_cat]
    else:
        filtered = entries

    impact_filter = st.radio(
        "Impact",
        ["All impacts", "HIGH only", "HIGH + MEDIUM"],
        horizontal=True,
        key="_qw_plan_impact_filter",
    )
    if impact_filter == "HIGH only":
        filtered = [e for e in filtered if e["impact"] == "HIGH"]
    elif impact_filter == "HIGH + MEDIUM":
        filtered = [e for e in filtered if e["impact"] in ("HIGH", "MEDIUM")]

    if not filtered:
        st.caption("No entries match the current filters.")
        return

    st.markdown(f"<div style='font-size:0.78rem; color:#6b6b8a; margin:0.4rem 0 0.8rem 0;'>"
                f"Showing {len(filtered)} of {len(entries)} items.</div>", unsafe_allow_html=True)

    # ── Render the list (group within categories for readability) ─
    from collections import defaultdict
    grouped = defaultdict(list)
    for e in filtered:
        grouped[e["category"]].append(e)

    for cat in ("assign_clusters", "thin_pages", "expand_clusters", "informational_gap"):
        rows = grouped.get(cat, [])
        if not rows:
            continue
        st.markdown(
            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; "
            f"color:#5533ff; letter-spacing:0.08em; margin:1.2rem 0 0.5rem 0;'>"
            f"{_CATEGORY_LABEL[cat].upper()} · {len(rows)} ITEM(S)</div>",
            unsafe_allow_html=True,
        )
        for i, e in enumerate(rows[:200], 1):
            impact_color = {"HIGH": "#ff4455", "MEDIUM": "#ffaa33", "LOW": "#5bb4d4"}.get(e["impact"], "#6b6b8a")
            target = e["url"] or (f"Cluster: {e['cluster']}" if e["cluster"] else "(no target)")
            display_target = shorten_url(target) if e["url"] else target
            meta_bits = []
            if e["page_type"]:
                meta_bits.append(str(e["page_type"]))
            if e["words"]:
                meta_bits.append(f"{e['words']} words")
            if e["impressions"]:
                meta_bits.append(f"{e['impressions']:,} impr")
            if e["clicks"]:
                meta_bits.append(f"{e['clicks']:,} clicks")
            meta = " · ".join(meta_bits)
            st.markdown(
                f"<div style='background:#0d0d15; border:1px solid #2a2a3a; "
                f"border-left:3px solid {impact_color}; border-radius:0 6px 6px 0; "
                f"padding:0.6rem 0.8rem; margin-bottom:0.5rem;'>"
                f"<div style='display:flex; justify-content:space-between; align-items:baseline; gap:0.5rem;'>"
                f"<div style='font-size:0.85rem; color:#e8e8f0; font-weight:600; word-break:break-word;'>"
                f"<span style='color:{impact_color}; font-family:\"IBM Plex Mono\",monospace; "
                f"font-size:0.65rem; margin-right:0.5rem;'>[{e['impact']}]</span>"
                f"{i}. {display_target}</div>"
                f"<div style='color:#6b6b8a; font-size:0.7rem; white-space:nowrap;'>{meta}</div>"
                f"</div>"
                f"<div style='font-size:0.78rem; color:#c8b4ff; margin-top:0.4rem; line-height:1.5;'>"
                f"→ {e['suggested_action']}</div>"
                f"<div style='font-size:0.68rem; color:#6b6b8a; margin-top:0.35rem;'>"
                f"<em>Addresses site-wide priority:</em> {e['action_label']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        if len(rows) > 200:
            st.caption(f"… plus {len(rows) - 200} more items in this category. Use the markdown export for the full list.")


def _render_priority_action_drilldown(action_text: str, df_structure, topic_clusters: dict):
    """Render the per-page drill-down for one priority action."""
    resolution = _resolve_priority_action(action_text, df_structure, topic_clusters)
    pages = resolution["pages"]
    if not pages:
        st.caption(
            "_No specific pages could be auto-mapped to this action. Either it is a high-level "
            "architectural recommendation, or required pipeline data is missing — re-run the full "
            "pipeline (audit + topic clusters + site validation) and reopen this card._"
        )
        return
    if resolution["note"]:
        st.caption(resolution["note"])
    for i, row in enumerate(pages[:30]):
        url = row.get("url", "") or ""
        cluster = row.get("cluster", "")
        if url:
            header = f"**{i+1}. {shorten_url(url)}**"
            meta_bits = []
            if row.get("page_type"):
                meta_bits.append(str(row["page_type"]))
            if row.get("words"):
                meta_bits.append(f"{row['words']} words")
            if row.get("impressions"):
                meta_bits.append(f"{row['impressions']:,} impr")
            if row.get("clicks"):
                meta_bits.append(f"{row['clicks']:,} clicks")
            meta = " · ".join(meta_bits)
        elif cluster:
            header = f"**{i+1}. Cluster: {cluster}**"
            meta = f"{row.get('impressions', 0):,} impressions · {row.get('clicks', 0):,} clicks"
        else:
            header = f"**{i+1}.**"
            meta = ""
        st.markdown(
            f"<div style='padding:0.5rem 0.6rem; border-left:2px solid #5a4a8a; "
            f"background:#0d0d15; margin-bottom:0.4rem; border-radius:0 4px 4px 0;'>"
            f"<div style='font-size:0.85rem;'>{header}</div>"
            f"<div style='color:#8a8aaa; font-size:0.72rem; margin:0.15rem 0 0.35rem 0;'>{meta}</div>"
            f"<div style='font-size:0.78rem; color:#c8b4ff;'>→ {row['suggested_action']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    if len(pages) > 30:
        st.caption(f"… plus {len(pages) - 30} more. Work through the top 30 first; the rest are typically lower-leverage.")


def _get_top_pages(audit_results, top_n=20):
    """Get top pages by lost clicks, excluding done and merge/delete scheduled pages."""
    # Build sets of URLs scheduled for merge (as source) or delete in ideal structure
    ideal = st.session_state.get("_ideal_structure") or {}
    excluded_urls = set()
    if isinstance(ideal, dict):
        for m in ideal.get("merge", []) or []:
            if isinstance(m, dict):
                for from_url in m.get("from", []):
                    excluded_urls.add(normalize_url(from_url))
        for d in ideal.get("delete", []) or []:
            if isinstance(d, dict) and d.get("url"):
                excluded_urls.add(normalize_url(d["url"]))

    # Build set of URLs with crawl issues for priority boosting
    sf_crawl_issues = st.session_state.get("sf_crawl_issues") or {}
    crawl_issue_urls = set()
    for b in sf_crawl_issues.get("broken_links", []) or []:
        if b.get("url"):
            crawl_issue_urls.add(normalize_url(b["url"]))
    for c in sf_crawl_issues.get("canonical_issues", []) or []:
        if c.get("url"):
            crawl_issue_urls.add(normalize_url(c["url"]))

    pages = []
    excluded_count = 0
    for r in audit_results:
        if not r.get("url"):
            continue
        url_hash = stable_hash(r["url"])
        if st.session_state.get(f"_qw_done_{url_hash}", False):
            continue
        # Exclude pages scheduled for merge/delete
        if normalize_url(r["url"]) in excluded_urls:
            excluded_count += 1
            continue
        # Use brand-filtered lost clicks from page profile
        from utils.page_profile import build_page_profile as _bpp_qw
        _prof = _bpp_qw(r["url"])
        _filtered_lost = sum(g.get("lost_clicks", 0) for g in _prof.get("ctr_gaps", []))
        pages.append({
            "url": r["url"],
            "page_type": r.get("page_type", "unknown"),
            "impressions": _prof.get("total_impressions", 0),
            "lost_clicks": _filtered_lost,
            "meta_score": r.get("meta_score") or 0,
            "content_score": r.get("content_score") or 0,
            "title": r.get("title", ""),
            "meta_description": r.get("meta_description", ""),
            "h1": r.get("h1", ""),
            "word_count": r.get("word_count", 0),
            "intro_text": r.get("intro_text", ""),
            "bottom_text": r.get("bottom_text", ""),
            "audit": r,
        })
    # Sort by lost_clicks (primary) with quality verdict + crawl issue boost (secondary).
    # REWRITE pages get priority boost, KEEP pages get deprioritized.
    # Pages with crawl issues get a boost similar to REWRITE.
    def _sort_key(p):
        from utils.quality_check_runner import quality_key as _qk_qw
        quality = st.session_state.get(_qk_qw(p["url"]))
        verdict = quality.get("verdict", "") if quality else ""
        # Boost: REWRITE=2, IMPROVE=1, KEEP/unknown=0
        verdict_boost = {"REWRITE": 2, "IMPROVE": 1}.get(verdict, 0)
        # Crawl issue boost: pages with broken links or canonical issues get +2
        crawl_boost = 2 if normalize_url(p["url"]) in crawl_issue_urls else 0
        total_boost = verdict_boost + crawl_boost
        # Combined: lost_clicks + boost bonus (scaled to not overwhelm lost_clicks)
        return -(p["lost_clicks"] + total_boost * max(p["lost_clicks"] * 0.3, 50))
    pages.sort(key=_sort_key)

    # Store excluded count for display
    st.session_state["_qw_excluded_count"] = excluded_count

    return pages[:top_n]


def _detect_issues(page):
    """Auto-detect what's wrong with this page."""
    issues = []
    audit = page["audit"]

    # Meta title
    title = page["title"] or ""
    if not title:
        issues.append("Missing meta title")
    elif len(title) < 30:
        issues.append(f"Meta title too short ({len(title)} chars, recommend 50-60)")
    elif len(title) > 65:
        issues.append(f"Meta title too long ({len(title)} chars, max 65)")

    # Meta description
    desc = page["meta_description"] or ""
    if not desc:
        issues.append("Missing meta description")
    elif len(desc) < 120:
        issues.append(f"Meta description short ({len(desc)} chars, recommend 140-160)")
    elif len(desc) > 165:
        issues.append(f"Meta description too long ({len(desc)} chars, max 165)")

    # Content audit data
    content_audit = audit.get("content_audit") or {}
    kw_coverage = content_audit.get("keyword_coverage") or {}
    missing_kws = kw_coverage.get("missing", [])
    if missing_kws:
        issues.append(f"Missing {len(missing_kws)} keywords: {', '.join(missing_kws[:5])}")

    # Internal links
    internal_links = audit.get("internal_links", 0)
    link_count = internal_links if isinstance(internal_links, int) else len(internal_links)
    if link_count < 5 and page["page_type"] == "category":
        issues.append(f"Few internal links ({link_count}, recommend 8-12)")

    # FAQ section
    if not audit.get("has_faq") and page["page_type"] == "category":
        issues.append("No FAQ section")

    # Buying guide
    if not audit.get("has_buying_guide") and page["page_type"] == "category":
        issues.append("No buying guide section")

    # Bottom text
    bottom_words = audit.get("bottom_word_count", 0)
    if bottom_words < 50 and page["page_type"] == "category":
        issues.append(f"Bottom text missing or too thin ({bottom_words} words)")

    # Linking issues
    linking = content_audit.get("linking") or {}
    missing_crosslinks = linking.get("missing_crosslinks") or []
    if missing_crosslinks:
        issues.append(f"{len(missing_crosslinks)} missing cluster cross-links")

    # Trust signals
    trust = content_audit.get("trust") or {}
    if trust:
        trust_signals = trust.get("trust_signals", {})
        if isinstance(trust_signals, dict):
            missing_trust = [k for k, v in trust_signals.items() if not v]
            if len(missing_trust) >= 3:
                issues.append(f"Missing trust signals: {', '.join(missing_trust[:3])}")

    return issues


def _generate_all_fixes(page):
    """Thin wrapper — delegates to utils.page_fix_runner so Page Auditor
    and Quick Wins run the EXACT same generation flow. Do not re-implement
    here; extend the runner instead."""
    from utils.page_fix_runner import generate_ai_fixes_for_page
    generate_ai_fixes_for_page(page)


def _build_total_plan(page, plan_data, text_data, intro_data):
    """Build ordered action list with priorities and time estimates."""
    from utils.page_profile import build_page_profile

    url = page["url"]
    audit = page["audit"]
    url_hash = stable_hash(url)
    profile = build_page_profile(url)
    actions = []

    # Priority 1: Cannibalization — NEVER suggest redirecting homepage, sale pages, etc.
    from urllib.parse import urlparse as _up_qw
    page_path = _up_qw(normalize_url(url)).path.rstrip("/")
    is_homepage = page_path == "" or page_path == "/"

    for cannibal in profile["cannibalization"]:
        if cannibal.get("is_winner"):
            actions.append({
                "priority": 1,
                "title": f"CANNIBALIZATION: This page WINS for '{cannibal['query']}'",
                "detail": f"{cannibal.get('lost_clicks', 0):,.0f} lost clicks. Other pages should link here.",
                "time": 15,
                "type": "cannibalization",
            })
        else:
            # NEVER redirect: homepage, sale pages, or pages with different intent
            from utils.site_patterns import get_sale_patterns
            is_sale = any(sp in url.lower() for sp in get_sale_patterns())
            if is_homepage:
                actions.append({
                    "priority": 1,
                    "title": f"CANNIBALIZATION: Homepage competes for '{cannibal['query']}'",
                    "detail": f"Do NOT redirect homepage. Instead: strengthen {', '.join(cannibal.get('competing_pages', [])[:2])} to own this query, so homepage stops competing.",
                    "time": 10,
                    "type": "cannibalization",
                })
            elif is_sale:
                actions.append({
                    "priority": 1,
                    "title": f"CANNIBALIZATION: Sale page competes for '{cannibal['query']}'",
                    "detail": f"Do NOT redirect. Differentiate meta to target sale variant. Add link to main category.",
                    "time": 10,
                    "type": "cannibalization",
                })
            else:
                actions.append({
                    "priority": 1,
                    "title": f"CANNIBALIZATION: This page competes for '{cannibal['query']}'",
                    "detail": f"Differentiate meta from {', '.join(cannibal.get('competing_pages', [])[:2])}. See Site Cleanup → Merge tab for full analysis.",
                    "time": 10,
                    "type": "cannibalization",
                })
        break  # Only show first cannibalization issue

    # Priority 2: Meta title + description — only if actually different from current
    if plan_data.get("meta_changed"):
        new_title = plan_data.get("meta_title", "")
        new_desc = plan_data.get("meta_description", "")
        current_title = (page.get("title") or "").strip()
        current_desc = (page.get("meta_description") or "").strip()
        # Skip if AI suggestion is identical to current meta
        title_changed = new_title.strip() and new_title.strip().lower() != current_title.lower()
        desc_changed = new_desc.strip() and new_desc.strip().lower() != current_desc.lower()
        if title_changed or desc_changed:
            detail_parts = []
            if title_changed:
                detail_parts.append(f"Current title: {current_title} ({len(current_title)} chars)\nNew title: {new_title} ({len(new_title)} chars)")
            else:
                detail_parts.append(f"Title: OK (no change needed)")
            if desc_changed:
                detail_parts.append(f"Current desc: {current_desc[:80]}... ({len(current_desc)} chars)\nNew desc: {new_desc} ({len(new_desc)} chars)")
            else:
                detail_parts.append(f"Description: OK (no change needed)")
            actions.append({
                "priority": 2,
                "title": "Update meta title and description",
                "detail": "\n".join(detail_parts),
                "time": 5,
                "type": "meta",
            })

    # Priority 3: Replace bottom text — only if current bottom text is thin or missing
    if text_data and text_data.get("html"):
        wc = text_data.get("word_count", 0)
        current_bottom_words = audit.get("bottom_word_count", 0)
        # Skip if current bottom text is already substantial (300+ words) and new text isn't significantly longer
        if current_bottom_words >= 300 and wc <= current_bottom_words * 1.3:
            actions.append({
                "priority": 3,
                "title": "Bottom text already adequate — review AI suggestion",
                "detail": f"Current: {current_bottom_words} words. AI generated: {wc} words. Current text may already be good enough — only replace if quality is poor.",
                "time": 5,
                "type": "bottom_text",
            })
        else:
            actions.append({
                "priority": 3,
                "title": "Replace bottom text (below product grid)",
                "detail": f"Current: {current_bottom_words} words. New text: {wc} words with FAQ, E-E-A-T, products. Download HTML and paste into Magento Description field.",
                "time": 10,
                "type": "bottom_text",
            })

    # Priority 4: Replace intro text — only if current intro is thin or missing
    if intro_data and not intro_data.get("error"):
        new_intro = intro_data.get("optimized_text") or intro_data.get("rewritten_intro") or intro_data.get("html", "") or intro_data.get("text", "")
        if new_intro:
            intro_wc = len(new_intro.split())
            current_intro_words = audit.get("intro_word_count", 0)
            if current_intro_words >= 80:
                # Current intro is decent length — flag as review, not replace
                actions.append({
                    "priority": 4,
                    "title": "Intro text exists — review AI suggestion",
                    "detail": f"Current intro: {current_intro_words} words (already meets minimum). AI suggestion: {intro_wc} words. Only replace if current intro lacks target keywords.",
                    "time": 5,
                    "type": "intro",
                })
            else:
                actions.append({
                    "priority": 4,
                    "title": "Update intro text (above product grid)",
                    "detail": f"Current intro: {current_intro_words} words (too thin). New intro: {intro_wc} words. Paste as first paragraph of Description.",
                    "time": 5,
                    "type": "intro",
                })

    # Priority 5: Add missing internal links
    content_audit = audit.get("content_audit") or {}
    linking = content_audit.get("linking") or {}
    link_details = linking.get("details") or {}
    missing_links = link_details.get("missing_crosslinks", [])
    if missing_links:
        actions.append({
            "priority": 5,
            "title": f"Add {len(missing_links)} missing internal links to cluster pages",
            "detail": "See [INBOUND LINKS] section for specific URLs and anchor texts",
            "time": len(missing_links) * 2,
            "type": "links_add",
        })

    # Priority 6: Remove bad links
    links_to_remove = link_details.get("links_to_remove", [])
    if links_to_remove:
        actions.append({
            "priority": 6,
            "title": f"Review {len(links_to_remove)} links pointing outside topic cluster",
            "detail": "Remove only if they harm topical focus — be conservative",
            "time": 5,
            "type": "links_remove",
        })

    # Priority 7: New articles to write — combined from plan + content_roadmap + content_gaps
    new_articles = list(plan_data.get("new_content_suggestions", []) or [])

    # Add from content_roadmap if this URL is the link_from source
    roadmap = st.session_state.get("content_roadmap", {})
    if isinstance(roadmap, dict):
        for a in roadmap.get("new_articles", []) or []:
            if isinstance(a, dict):
                link_from = a.get("supporting_page") or a.get("link_from", "")
                if normalize_url(link_from) == normalize_url(url):
                    new_articles.append(a)

    # Deduplicate by title
    seen_titles = set()
    unique_articles = []
    for a in new_articles:
        if isinstance(a, dict):
            title = a.get("suggested_title", "")
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_articles.append(a)
    new_articles = unique_articles
    if new_articles:
        actions.append({
            "priority": 7,
            "title": f"Write {len(new_articles)} supporting blog articles",
            "detail": f"Topics: {', '.join(a.get('suggested_title', '')[:40] for a in new_articles[:3])}",
            "time": len(new_articles) * 60,
            "type": "blogs",
        })

    # Priority 7b: Topic-level gaps (from profile's content_gaps + clusters)
    page_gaps = profile["content_gaps"]
    if page_gaps:
        all_issues = []
        for g in page_gaps:
            for iss in g.get("issues", []):
                all_issues.append(f"[{g.get('topic', g.get('cluster', '?'))}] {iss}")
        if all_issues:
            actions.append({
                "priority": 7,
                "title": f"Topic gaps: {len(all_issues)} issue(s) in clusters this page belongs to",
                "detail": " · ".join(all_issues[:3]) + (" ..." if len(all_issues) > 3 else ""),
                "time": 15,
                "type": "topic_gaps",
            })

    # Priority 8: Technical fixes
    tech_items = []
    schema_types = audit.get("schema_types", []) or []
    if not any("breadcrumb" in str(s).lower() for s in schema_types):
        tech_items.append("BreadcrumbList schema")
    if page["page_type"] == "category" and not any("itemlist" in str(s).lower() for s in schema_types):
        tech_items.append("ItemList schema")
    images_no_alt = audit.get("images_without_alt", 0)
    if images_no_alt > 0:
        tech_items.append(f"{images_no_alt} alt texts")
    if tech_items:
        actions.append({
            "priority": 8,
            "title": f"Technical fixes: {', '.join(tech_items)}",
            "detail": "Add schema markup and fix alt texts",
            "time": 15,
            "type": "technical",
        })

    return actions


def _validate_generated_content(page, text_data, plan_data):
    """
    Post-generation validation layer.
    Verifies AI-generated content actually uses correct URLs, products, images.
    Returns dict with passed/failed checks.
    """
    import re

    results = {
        "checks": [],
        "passed": 0,
        "failed": 0,
        "warnings": 0,
    }

    def _check(passed, message, severity="error"):
        results["checks"].append({"passed": passed, "message": message, "severity": severity})
        if passed:
            results["passed"] += 1
        elif severity == "warning":
            results["warnings"] += 1
        else:
            results["failed"] += 1

    audit = page["audit"]
    # Validate the FULL editorial output (top + bottom) — keywords/links
    # may legitimately appear in either, so checking only bottom_html
    # produces false negatives.
    if text_data:
        html = (
            (text_data.get("top_html") or "")
            + " "
            + (text_data.get("bottom_html") or text_data.get("html", "") or "")
        )
    else:
        html = ""

    # ── 1. Check all URLs in generated HTML exist on the site ──
    all_site_urls = set()
    audit_results = st.session_state.get("audit_results", [])
    for r in audit_results:
        if r.get("url"):
            all_site_urls.add(normalize_url(r["url"]))
    gsc = st.session_state.get("gsc_data")
    if gsc is not None and hasattr(gsc, "page"):
        for p in gsc["page"].unique():
            all_site_urls.add(normalize_url(str(p)))

    if html:
        urls_in_html = re.findall(r'href=["\']([^"\']+)["\']', html)
        site_urls_used = [u for u in urls_in_html if "mshop.se" in u or u.startswith("/")]

        invented = []
        for u in site_urls_used:
            norm = normalize_url(u)
            if norm not in all_site_urls:
                invented.append(u)

        if invented:
            _check(False, f"{len(invented)} invented URLs in generated text (not on site): {', '.join(invented[:3])}", "error")
        else:
            _check(True, f"All {len(site_urls_used)} internal URLs exist on the site", "info")

        # ── 2. Check URLs don't point to broken pages ──
        crawl_issues = st.session_state.get("sf_crawl_issues", {})
        broken_urls = set(normalize_url(b.get("url", "")) for b in crawl_issues.get("broken_links", []))
        redirected_urls = set(normalize_url(r.get("url", "")) for r in crawl_issues.get("redirect_chains", []))
        noindex_urls = set(normalize_url(n.get("url", "")) for n in crawl_issues.get("non_indexable", []))

        broken_in_text = [u for u in site_urls_used if normalize_url(u) in broken_urls]
        redirect_in_text = [u for u in site_urls_used if normalize_url(u) in redirected_urls]
        noindex_in_text = [u for u in site_urls_used if normalize_url(u) in noindex_urls]

        if broken_in_text:
            _check(False, f"{len(broken_in_text)} links point to BROKEN pages: {', '.join(broken_in_text[:3])}", "error")
        else:
            _check(True, "No links to broken pages", "info")

        if redirect_in_text:
            _check(False, f"{len(redirect_in_text)} links point to REDIRECT pages: {', '.join(redirect_in_text[:3])}", "warning")

        if noindex_in_text:
            _check(False, f"{len(noindex_in_text)} links point to NON-INDEXABLE pages: {', '.join(noindex_in_text[:3])}", "warning")

        # ── 3. Check product images are actually used ──
        real_products = audit.get("products", []) or []
        if real_products:
            real_image_urls = set(p.get("image", "") for p in real_products if p.get("image"))
            images_in_html = set(re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html))

            if real_image_urls:
                used_real_images = real_image_urls & images_in_html
                if used_real_images:
                    _check(True, f"Uses {len(used_real_images)}/{len(real_image_urls)} real product images", "info")
                else:
                    _check(False, f"0/{len(real_image_urls)} real product images used — AI may have invented image paths", "warning")

        # ── 4. Check product URLs are real ──
        real_product_urls = set(normalize_url(p.get("url", "")) for p in real_products if p.get("url"))
        product_link_urls = set(normalize_url(u) for u in site_urls_used
                                if any(patt in u.lower() for patt in ["/produkt", "/product", "/p/"]))

        if real_product_urls and product_link_urls:
            invented_products = product_link_urls - real_product_urls - all_site_urls
            if invented_products:
                _check(False, f"{len(invented_products)} invented product URLs", "error")
            else:
                _check(True, "All product URLs are real", "info")

        # ── 5. Check minimum link count ──
        link_count = len(site_urls_used)
        if link_count < 8:
            _check(False, f"Only {link_count} internal links (target: 8-12)", "warning")
        else:
            _check(True, f"{link_count} internal links (good)", "info")

        # ── 6. Check FAQ section present ──
        if page["page_type"] == "category":
            has_faq = "vanliga frågor" in html.lower() or "<h2" in html.lower() and "faq" in html.lower()
            _check(has_faq, "FAQ section present" if has_faq else "FAQ section missing", "warning" if not has_faq else "info")

        # ── 7. Required keywords + links — single source of truth ──
        # The generator stamps the result with _required_keywords +
        # _required_links so validation matches exactly what the prompt
        # demanded. Falls back to top-5 target_keywords for legacy results.
        from utils.ai_generator import _missing_required
        required_kws = (text_data or {}).get("_required_keywords") or []
        required_links = (text_data or {}).get("_required_links") or []
        if not required_kws:
            required_kws = audit.get("target_keywords", [])[:5]

        if required_kws or required_links:
            missing_kws, missing_links = _missing_required(html, required_kws, required_links)

            if required_kws:
                if missing_kws:
                    _check(
                        False,
                        f"{len(missing_kws)}/{len(required_kws)} REQUIRED keywords missing: "
                        + ", ".join(missing_kws[:5]),
                        "error",
                    )
                else:
                    _check(True, f"All {len(required_kws)} required keywords present", "info")

            if required_links:
                if missing_links:
                    miss_lines = ", ".join(
                        f"{ml.get('anchor','?')} → {ml.get('url','?')}"
                        for ml in missing_links[:3]
                    )
                    _check(
                        False,
                        f"{len(missing_links)}/{len(required_links)} REQUIRED links missing: {miss_lines}",
                        "error",
                    )
                else:
                    _check(True, f"All {len(required_links)} required internal links present", "info")

        # ── Potential product-name hallucinations (warning only) ──
        # Brand-anchored model names that don't appear in the page's real
        # product list. May be a real product on another page — review
        # before pushing to verify each name actually exists in the store.
        potential_hallu = (text_data or {}).get("_potential_hallucinations") or []
        if potential_hallu:
            shown = ", ".join(f"\"{p}\"" for p in potential_hallu[:5])
            extra = f" (+{len(potential_hallu) - 5} more)" if len(potential_hallu) > 5 else ""
            _check(
                False,
                f"Verify these product names exist in your catalog: {shown}{extra}",
                "warning",
            )

        # ── 8. LIX readability (target 35-40) ──
        from utils.ui_helpers import compute_lix
        lix = compute_lix(html)
        if lix == 0:
            pass  # no content to measure
        elif 35 <= lix <= 40:
            _check(True, f"LIX {lix} — ideal readability (target 35-40)", "info")
        elif 30 <= lix < 35 or 40 < lix <= 45:
            _check(True, f"LIX {lix} — acceptable (ideal is 35-40)", "info")
        elif lix < 25:
            _check(False, f"LIX {lix} — too easy, reads as childish (target 35-40)", "warning")
        elif lix < 30:
            _check(False, f"LIX {lix} — a bit too simple (target 35-40)", "warning")
        elif lix <= 50:
            _check(False, f"LIX {lix} — getting difficult, consider shorter sentences (target 35-40)", "warning")
        else:
            _check(False, f"LIX {lix} — too difficult, regenerate recommended (target 35-40)", "error")

    return results


def _export_page_as_markdown(page, plan_data, text_data, intro_data):
    """Export everything for this page as markdown."""
    url = page["url"]
    audit = page["audit"]
    md = []

    md.append(f"# {url}")
    md.append("")
    md.append(f"## Metrics")
    md.append(f"- **Impressions:** {page['impressions']:,}")
    md.append(f"- **Lost clicks:** {page['lost_clicks']:,}")
    md.append(f"- **Meta score:** {page['meta_score']}/100")
    md.append(f"- **Content score:** {page['content_score']}/100")
    md.append(f"- **Page type:** {page['page_type']}")
    md.append(f"- **Word count:** {page['word_count']}")
    md.append(f"- **Intent:** {audit.get('search_intent', 'unknown')}")
    md.append(f"- **Referring domains:** {audit.get('referring_domains', 0)}")
    md.append("")

    # Total Plan
    total_plan = _build_total_plan(page, plan_data, text_data, intro_data)
    if total_plan:
        total_time = sum(a["time"] for a in total_plan)
        md.append(f"## TOTAL PLAN ({total_time} min total)")
        md.append("")
        for a in total_plan:
            md.append(f"### {a['priority']}. {a['title']} ({a['time']} min)")
            md.append(a["detail"])
            md.append("")

    # Meta
    md.append("## META")
    md.append(f"**Current title** ({len(page['title'] or '')} chars):")
    md.append(f"`{page['title']}`")
    md.append("")
    md.append(f"**Current description** ({len(page['meta_description'] or '')} chars):")
    md.append(f"`{page['meta_description']}`")
    md.append("")
    if plan_data.get("meta_changed"):
        md.append(f"**New title** ({len(plan_data.get('meta_title', ''))} chars):")
        md.append(f"`{plan_data.get('meta_title', '')}`")
        md.append("")
        md.append(f"**New description** ({len(plan_data.get('meta_description', ''))} chars):")
        md.append(f"`{plan_data.get('meta_description', '')}`")
        md.append("")

    # Intro text
    if intro_data and not intro_data.get("error"):
        new_intro = intro_data.get("optimized_text") or intro_data.get("rewritten_intro") or intro_data.get("html", "") or intro_data.get("text", "")
        if new_intro:
            md.append("## NEW INTRO TEXT (above product grid)")
            md.append("")
            md.append(new_intro)
            md.append("")

    # Bottom text
    if text_data and (text_data.get("bottom_html") or text_data.get("html")):
        md.append("## NEW BOTTOM TEXT (below product grid)")
        wc = text_data.get("bottom_word_count") or text_data.get("word_count", 0)
        md.append(f"- Word count: {wc}")
        ex_kws, ex_links, ex_prods = extract_content_summary(text_data)
        md.append(f"- Keywords: {', '.join(ex_kws)}")
        md.append(f"- Internal links: {len(ex_links)}")
        md.append(f"- Products: {len(ex_prods)}")
        md.append("")
        md.append("```html")
        md.append(text_data.get("bottom_html") or text_data.get("html", ""))
        md.append("```")
        md.append("")

    # Plan steps
    plan_steps = plan_data.get("steps", [])
    if plan_steps:
        md.append("## IMPLEMENTATION STEPS")
        md.append("")
        for i, s in enumerate(plan_steps, 1):
            md.append(f"### {i}. {s.get('action', '')} ({s.get('time_minutes', '?')} min)")
            md.append(f"**Problem:** {s.get('detail', '')}")
            md.append(f"**Action:** {s.get('instruction', '')}")
            md.append("")

    # New articles
    new_articles = plan_data.get("new_content_suggestions", [])
    if new_articles:
        md.append("## NEW ARTICLES TO WRITE")
        md.append("")
        for a in new_articles:
            md.append(f"### {a.get('suggested_title', '')}")
            md.append(f"**Why:** {a.get('why', '')}")
            md.append(f"**Keywords:** {', '.join(a.get('target_keywords', []))}")
            md.append(f"**Link from:** {a.get('link_from', '')}")
            md.append("")

    # Links
    content_audit = audit.get("content_audit") or {}
    linking = content_audit.get("linking") or {}
    link_details = linking.get("details") or {}

    missing_links = link_details.get("missing_crosslinks", [])
    if missing_links:
        md.append("## INTERNAL LINKS TO ADD")
        md.append("")
        for l in missing_links[:10]:
            md.append(f"- Link to `{l.get('url', '')}` (shared topics: {', '.join(l.get('shared_topics', [])[:2])})")
        md.append("")

    links_to_remove = link_details.get("links_to_remove", [])
    if links_to_remove:
        md.append("## LINKS TO REVIEW (possibly remove)")
        md.append("")
        for l in links_to_remove[:10]:
            md.append(f"- `{l.get('url', '')}` — anchor: '{l.get('anchor', '')}'")
        md.append("")

    # Cannibalization (from profile)
    from utils.page_profile import build_page_profile as _bpp_export
    _export_profile = _bpp_export(url)
    cannibal_entries = _export_profile["cannibalization"]
    if cannibal_entries:
        md.append("## CANNIBALIZATION CONFLICTS")
        md.append("")
        for entry in cannibal_entries[:5]:
            winner_text = "This page WINS" if entry.get("is_winner") else f"Competing: {', '.join(entry.get('competing_pages', []))}"
            md.append(f"- **'{entry.get('query', '')}'** [{entry.get('type', '').upper()}]")
            md.append(f"  - {winner_text}")
            md.append(f"  - Lost clicks: {entry.get('lost_clicks', 0):,.0f}")
        md.append("")

    return "\n".join(md)


def _approval_button(label, key):
    """Approve/Reject toggle stored in session state."""
    state_key = f"_qw_approved_{key}"
    current = st.session_state.get(state_key, None)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Approve", key=f"{key}_app", type="primary" if current == "approved" else "secondary"):
            st.session_state[state_key] = "approved"
            st.rerun()
    with col2:
        if st.button("Edit later", key=f"{key}_edit", type="primary" if current == "edit" else "secondary"):
            st.session_state[state_key] = "edit"
            st.rerun()
    with col3:
        if st.button("Reject", key=f"{key}_rej", type="primary" if current == "rejected" else "secondary"):
            st.session_state[state_key] = "rejected"
            st.rerun()

    if current:
        color = {"approved": "#33dd88", "edit": "#ffaa33", "rejected": "#ff4455"}.get(current)
        st.markdown(f"<div style='font-size:0.75rem; color:{color}; font-weight:600;'>Status: {current.upper()}</div>", unsafe_allow_html=True)


# ── Current SEO state card ────────────────────────────────────────────
# Always-visible diagnosis of what Google sees on this page right now,
# with a per-element verdict (OK / generate new + WHY) so the user never
# has to dig through the AI plan to know if title/meta/h1 need work.

_TITLE_MIN, _TITLE_MAX = 30, 65
_DESC_MIN, _DESC_MAX = 120, 165


def _primary_keyword_for_page(page) -> str:
    """Best-effort top GSC query for this page (single token preferred)."""
    try:
        from utils.page_profile import build_page_profile
        prof = build_page_profile(page["url"])
        q = (prof or {}).get("primary_query") or ""
        if q:
            return q.strip()
        gsc = (prof or {}).get("gsc_queries") or []
        if gsc:
            return (gsc[0].get("query") or "").strip()
    except Exception:
        pass
    return ""


def _kw_present_in(primary_kw: str, text: str) -> bool:
    """Substring-tolerant primary-keyword presence check.

    Why substring (not token equality): GSC query "dildo" should be considered
    present in titles like "Dildos" (plural) or "Favoritdildo" (compound).
    A pure tokenizer-and-set-intersect approach gives too many false positives
    for the "missing primary keyword" verdict.
    """
    if not primary_kw or not text:
        return False
    text_l = text.lower()
    tokens = re.findall(r"\w+", primary_kw.lower())
    if not tokens:
        return False
    long_toks = [t for t in tokens if len(t) >= 4]
    if long_toks:
        # >=4 char tokens use substring match — 'dildo' present in 'dildos',
        # 'kukring' present in 'kukringar', '6000' present in 'cb-6000-chastity'.
        return any(tok in text_l for tok in long_toks)
    # All kw tokens are short (3 chars) — require word-boundary match to avoid
    # false positives like 'rea' matching inside 'realistic'.
    text_tokens = set(re.findall(r"\w+", text_l))
    return any(t in text_tokens for t in tokens if len(t) >= 3)


def _verdict_for_title(title: str, primary_kw: str) -> tuple:
    """Returns (status, color, headline, reason). status: 'ok' | 'warn' | 'bad'."""
    t = (title or "").strip()
    n = len(t)
    if not t:
        return ("bad", "#ff4455", "Missing — must generate",
                "No <title> tag means Google generates one from the page text. "
                "You lose all control over the SERP click-through.")
    if n < _TITLE_MIN:
        return ("warn", "#ffaa33", f"Too short — generate new ({n} chars)",
                f"Recommended {_TITLE_MIN}–{_TITLE_MAX} chars. "
                f"At {n} chars you're wasting SERP real estate and likely missing "
                f"either the primary keyword or a benefit modifier.")
    if n > _TITLE_MAX:
        return ("warn", "#ffaa33", f"Too long — generate new ({n} chars)",
                f"Google truncates titles beyond ~{_TITLE_MAX} chars on desktop SERP. "
                f"At {n} chars the end (often where the brand or USP sits) gets cut off as '…'.")
    if primary_kw and not _kw_present_in(primary_kw, t):
        return ("warn", "#ffaa33", f"Generate new — missing primary keyword '{primary_kw}'",
                f"Top GSC query for this page is '{primary_kw}' but it doesn't appear in the title. "
                f"Front-loading the primary keyword typically lifts CTR by 10–25 %.")
    return ("ok", "#33dd88", "Looks OK — keep as-is",
            f"{n} chars (within {_TITLE_MIN}–{_TITLE_MAX} window)"
            + (f", primary keyword '{primary_kw}' present." if primary_kw else "."))


def _verdict_for_description(desc: str, primary_kw: str) -> tuple:
    d = (desc or "").strip()
    n = len(d)
    if not d:
        return ("bad", "#ff4455", "Missing — must generate",
                "No meta description means Google auto-generates a snippet from page text. "
                "It's usually generic and CTR suffers vs. a hand-crafted snippet.")
    if n < _DESC_MIN:
        return ("warn", "#ffaa33", f"Too short — generate new ({n} chars)",
                f"Recommended {_DESC_MIN}–{_DESC_MAX} chars. "
                f"At {n} chars you're leaving SERP space empty and Google may "
                f"override with its own auto-generated snippet anyway.")
    if n > _DESC_MAX:
        return ("warn", "#ffaa33", f"Too long — generate new ({n} chars)",
                f"Google truncates beyond ~{_DESC_MAX} chars on desktop. "
                f"Anything after that is cut as '…' and the CTA never makes it to the user.")
    cta_words = {"köp", "kop", "shop", "se", "upptäck", "upptack", "läs", "las",
                 "best", "bedst", "hitta", "find", "discover", "explore",
                 "beställ", "bestall", "bestil", "fri frakt", "fri fragt"}
    if not any(w in d.lower() for w in cta_words):
        return ("warn", "#ffaa33", "Generate new — no call-to-action",
                "The description reads like a label, not an invitation. "
                "Add a soft CTA ('Köp', 'Se vårt sortiment', 'Upptäck …') at the end "
                "to nudge clicks.")
    if primary_kw and not _kw_present_in(primary_kw, d):
        return ("warn", "#ffaa33", f"Generate new — missing primary keyword '{primary_kw}'",
                f"Google bolds the primary keyword in the SERP snippet — without "
                f"'{primary_kw}' anywhere in the description, you lose that visual cue.")
    return ("ok", "#33dd88", "Looks OK — keep as-is",
            f"{n} chars (within {_DESC_MIN}–{_DESC_MAX} window), CTA present"
            + (f", primary keyword '{primary_kw}' present." if primary_kw else "."))


def _verdict_for_h1(h1: str, title: str) -> tuple:
    h = (h1 or "").strip()
    if not h:
        return ("bad", "#ff4455", "Missing — must add",
                "No H1 tag found. Every page needs exactly one H1 for accessibility "
                "and to tell Google the page's primary topic.")
    if len(h) < 10:
        return ("warn", "#ffaa33", f"Too short ({len(h)} chars)",
                "An H1 should describe what's on the page — single-word H1s waste "
                "the strongest on-page semantic signal.")
    if title and h.strip().lower() == (title or "").strip().lower():
        return ("warn", "#ffaa33", "Identical to <title>",
                "H1 and <title> being byte-identical is a missed opportunity — "
                "the title can lean on SERP-friendly modifiers ('Köp …', '— Brand'), "
                "while the H1 should read more naturally as a page heading.")
    return ("ok", "#33dd88", "Looks OK", f"{len(h)} chars, distinct from <title>.")


def _render_seo_element_row(label: str, current_text: str, verdict: tuple,
                            char_count_window: tuple = None):
    """Render one row of the Current SEO State card."""
    status, color, headline, reason = verdict
    icon = {"ok": "✓", "warn": "⚠", "bad": "✗"}[status]
    n = len(current_text or "")
    range_str = ""
    if char_count_window:
        lo, hi = char_count_window
        ok = lo <= n <= hi
        range_color = "#33dd88" if ok else ("#ff4455" if n == 0 else "#ffaa33")
        range_str = (
            f"<span style='color:{range_color}; font-family:\"IBM Plex Mono\",monospace; "
            f"font-size:0.7rem;'>{n} chars</span>"
            f"<span style='color:#6b6b8a; font-size:0.7rem;'> / target {lo}–{hi}</span>"
        )

    # Escape angle brackets so titles like "<empty>" don't break HTML
    display_text = (current_text or "(empty — nothing set)").replace("<", "&lt;").replace(">", "&gt;")
    is_empty = not (current_text or "").strip()
    text_color = "#6b6b8a" if is_empty else "#e8e8f0"
    text_style = "italic" if is_empty else "normal"

    st.markdown(
        f"<div style='background:#0d0d15; border:1px solid #2a2a3a; border-left:4px solid {color}; "
        f"border-radius:0 6px 6px 0; padding:0.7rem 0.9rem; margin-bottom:0.6rem;'>"
        f"<div style='display:flex; justify-content:space-between; align-items:baseline; margin-bottom:0.3rem;'>"
        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; "
        f"color:#8a8aaa; letter-spacing:0.08em;'>{label.upper()}</div>"
        f"<div>{range_str}</div>"
        f"</div>"
        f"<div style='font-size:0.9rem; color:{text_color}; font-style:{text_style}; "
        f"margin:0.2rem 0 0.55rem 0; word-break:break-word; line-height:1.4;'>"
        f"\"{display_text}\""
        f"</div>"
        f"<div style='font-size:0.78rem; color:{color}; font-weight:600; margin-bottom:0.15rem;'>"
        f"{icon} {headline}"
        f"</div>"
        f"<div style='font-size:0.74rem; color:#9b9bb8; line-height:1.45;'>"
        f"{reason}"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_current_seo_state(page):
    """Always-visible diagnosis card: current title/meta/H1 + per-element verdict."""
    title = page.get("title") or ""
    desc = page.get("meta_description") or ""
    h1 = page.get("h1") or ""
    primary_kw = _primary_keyword_for_page(page)

    title_verdict = _verdict_for_title(title, primary_kw)
    desc_verdict = _verdict_for_description(desc, primary_kw)
    h1_verdict = _verdict_for_h1(h1, title)

    needs_action = any(v[0] != "ok" for v in (title_verdict, desc_verdict, h1_verdict))
    overall_color = "#ff4455" if any(v[0] == "bad" for v in (title_verdict, desc_verdict, h1_verdict)) \
        else ("#ffaa33" if needs_action else "#33dd88")

    if needs_action:
        bad = sum(1 for v in (title_verdict, desc_verdict, h1_verdict) if v[0] == "bad")
        warn = sum(1 for v in (title_verdict, desc_verdict, h1_verdict) if v[0] == "warn")
        bits = []
        if bad:
            bits.append(f"{bad} missing")
        if warn:
            bits.append(f"{warn} need rewriting")
        summary_text = " · ".join(bits)
    else:
        summary_text = "All three elements look healthy — no rewrite needed."

    st.markdown(
        f"<div style='background:#0d0d15; border:2px solid {overall_color}; border-radius:8px; "
        f"padding:0.9rem 1rem 0.7rem 1rem; margin:1rem 0 1rem 0;'>"
        f"<div style='display:flex; justify-content:space-between; align-items:baseline; margin-bottom:0.6rem;'>"
        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; "
        f"color:{overall_color}; letter-spacing:0.06em;'>WHAT GOOGLE SEES RIGHT NOW</div>"
        f"<div style='font-size:0.78rem; color:{overall_color}; font-weight:600;'>{summary_text}</div>"
        f"</div>"
        + (f"<div style='font-size:0.72rem; color:#6b6b8a; margin-bottom:0.6rem;'>"
           f"Primary GSC query for this page: <strong style='color:#c8b4ff;'>{primary_kw}</strong></div>"
           if primary_kw else "")
        + "</div>",
        unsafe_allow_html=True,
    )

    _render_seo_element_row("Meta title", title, title_verdict, char_count_window=(_TITLE_MIN, _TITLE_MAX))
    _render_seo_element_row("Meta description", desc, desc_verdict, char_count_window=(_DESC_MIN, _DESC_MAX))
    _render_seo_element_row("H1 heading", h1, h1_verdict, char_count_window=None)

    if needs_action:
        st.markdown(
            "<div style='font-size:0.75rem; color:#9b9bb8; margin:0.2rem 0 0.4rem 0;'>"
            "→ Click <strong>Generate plan</strong> below — the AI will produce concrete "
            "rewrites for everything flagged ⚠ / ✗ above, plus a step-by-step plan for the rest of the page."
            "</div>",
            unsafe_allow_html=True,
        )


def _render_topical_scope_panel(page):
    """
    Show which GSC queries this page should OWN vs. queries that belong to
    its hub. Renders only when the page is a SPOKE in a cluster with a
    detectable URL-hierarchy hub — otherwise the page has no topical
    boundary to enforce.
    """
    topic_clusters = st.session_state.get("topic_clusters", {}) or {}
    if not topic_clusters:
        return
    try:
        from utils.topical_scope import get_topical_scope, deoptimization_action_text
    except Exception:
        return

    scope = get_topical_scope(page["url"], topic_clusters)
    if not scope:
        return  # not in any cluster, or cluster has no hub

    if scope.get("is_hub"):
        owned = scope.get("owned", []) or []
        spoke_count = scope.get("spoke_count", 0)
        topic = scope.get("cluster_topic", "")
        if not owned:
            return
        owned_html = " ".join(
            f"<span style='display:inline-block; background:#0d2d1a; color:#33dd88; "
            f"font-size:0.72rem; padding:0.15rem 0.5rem; border-radius:3px; "
            f"margin:0.1rem 0.2rem 0.1rem 0;'>{q}</span>"
            for q in owned[:12]
        )
        st.markdown(
            f"<div style='background:#0d0d15; border:2px solid #33dd88; border-radius:8px; "
            f"padding:0.9rem 1rem; margin:0.8rem 0;'>"
            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; "
            f"color:#33dd88; letter-spacing:0.06em; margin-bottom:0.4rem;'>"
            f"TOPICAL SCOPE — THIS PAGE IS THE HUB ({topic})</div>"
            f"<div style='font-size:0.78rem; color:#c8b4ff; margin-bottom:0.5rem;'>"
            f"This page owns the head terms for cluster <strong>{topic}</strong>. "
            f"{spoke_count} sub-page(s) defer to it. Keep these queries front-and-center "
            f"in title/H1/meta:</div>"
            f"<div>{owned_html}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    # Spoke case — show what to own and what to avoid
    owned = scope.get("owned", []) or []
    do_not_compete = scope.get("do_not_compete", []) or []
    hub_url = scope.get("hub_url", "")
    topic = scope.get("cluster_topic", "")
    if not do_not_compete and not owned:
        return  # nothing useful to surface

    has_conflict = bool(do_not_compete)
    border_color = "#ffaa33" if has_conflict else "#5bb4d4"
    headline_color = border_color

    owned_html = " ".join(
        f"<span style='display:inline-block; background:#0d2d1a; color:#33dd88; "
        f"font-size:0.72rem; padding:0.15rem 0.5rem; border-radius:3px; "
        f"margin:0.1rem 0.2rem 0.1rem 0;'>✓ {q}</span>"
        for q in owned[:8]
    )
    avoid_html = " ".join(
        f"<span style='display:inline-block; background:#2d0d0d; color:#ff6644; "
        f"font-size:0.72rem; padding:0.15rem 0.5rem; border-radius:3px; "
        f"margin:0.1rem 0.2rem 0.1rem 0;'>✗ {q}</span>"
        for q in do_not_compete[:8]
    )

    action_text = deoptimization_action_text(
        scope,
        page_title=page.get("title", ""),
        page_h1=page.get("h1", ""),
        page_meta_desc=page.get("meta_description", ""),
    )

    parts = [
        f"<div style='background:#0d0d15; border:2px solid {border_color}; border-radius:8px; "
        f"padding:0.9rem 1rem; margin:0.8rem 0;'>"
        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; "
        f"color:{headline_color}; letter-spacing:0.06em; margin-bottom:0.5rem;'>"
        f"TOPICAL SCOPE — THIS PAGE IS A SPOKE IN CLUSTER \"{topic}\"</div>"
    ]

    if owned_html:
        parts.append(
            f"<div style='font-size:0.74rem; color:#9b9bb8; margin:0.3rem 0 0.2rem 0;'>"
            f"This page owns:</div><div>{owned_html}</div>"
        )

    if avoid_html:
        parts.append(
            f"<div style='font-size:0.74rem; color:#9b9bb8; margin:0.6rem 0 0.2rem 0;'>"
            f"Do <strong>not</strong> compete for "
            f"(owned by hub <code style='color:#c8b4ff;'>{hub_url}</code>):</div>"
            f"<div>{avoid_html}</div>"
        )

    if action_text:
        parts.append(
            f"<div style='font-size:0.76rem; color:#c8b4ff; margin-top:0.7rem; "
            f"line-height:1.55; padding:0.55rem 0.7rem; background:#12121f; "
            f"border-left:3px solid {border_color}; border-radius:0 4px 4px 0;'>"
            f"{action_text}</div>"
        )

    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def _render_context_card_body(page, url, url_hash, plan):
    """Render the per-page CONTEXT block: action steps, articles, links,
    cannibalization, technical issues. Lives inside Card 4 (collapsed by default)."""
    # ── Action steps (only if NOT replacing text) ──
    steps = plan.get("steps", [])
    if steps:
        with st.popover(f"[ALTERNATIVE] {len(steps)} action steps (only if you want to keep existing text)"):
            st.markdown(
                "<p style='color:#9b9bb8; font-size:0.85rem;'>"
                "These steps are for fixing the EXISTING text instead of replacing it. "
                "If you used the PRIMARY action above, you can skip these.</p>",
                unsafe_allow_html=True,
            )
            for i, s in enumerate(steps[:5], 1):
                st.markdown(f"**{i}. {s.get('action', '')}** ({s.get('time_minutes', '?')} min)")
                st.markdown(f"<div style='color:#9b9bb8; font-size:0.85rem; margin-left:1rem;'>{s.get('detail', '')}</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='color:#c8b4ff; font-size:0.85rem; margin-left:1rem;'>→ {s.get('instruction', '')}</div>", unsafe_allow_html=True)
        st.markdown("---")

    # ── New articles/blogs to write that support this page ──
    new_articles = plan.get("new_content_suggestions", [])
    if new_articles:
        st.markdown(f"#### [BLOGS] {len(new_articles)} new articles/guides to write")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.8rem;'>"
            "These articles should be created and linked TO this page to support topical authority.</p>",
            unsafe_allow_html=True,
        )
        for art_idx, art in enumerate(new_articles[:5]):
            art_title = art.get('suggested_title', '')
            art_hash = stable_hash(f"{url}_{art_title}")
            art_cache_key = f"_gen_article_{art_hash}"

            st.markdown(f"**{art_idx+1}. {art_title}**")
            st.markdown(f"<div style='color:#9b9bb8; font-size:0.85rem; margin-left:1rem;'>{art.get('why', '')[:200]}</div>", unsafe_allow_html=True)
            if art.get("target_keywords"):
                st.markdown(f"<div style='color:#c8b4ff; font-size:0.75rem; margin-left:1rem;'>Keywords: {', '.join(art.get('target_keywords', [])[:5])}</div>", unsafe_allow_html=True)
            if art.get("link_from"):
                st.markdown(f"<div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>Link from: {art.get('link_from', '')}</div>", unsafe_allow_html=True)

            if art_cache_key in st.session_state:
                article_data = st.session_state[art_cache_key]
                article_html = article_data.get("html", "") if isinstance(article_data, dict) else ""
                wc = article_data.get("word_count", 0) if isinstance(article_data, dict) else 0
                st.markdown(f"<div style='color:#33dd88; font-size:0.75rem; margin-left:1rem;'>✓ Generated: {wc} words</div>", unsafe_allow_html=True)
                with st.popover(f"View article {art_idx+1}"):
                    st.code(article_html[:3000] + ("..." if len(article_html) > 3000 else ""), language="html")
                st.download_button(
                    "Download article HTML",
                    data=article_html,
                    file_name=f"blog_{art_hash}.html",
                    mime="text/html",
                    key=f"dl_art_{art_hash}",
                )
            else:
                if st.button(f"Generate full article", key=f"gen_art_{art_hash}"):
                    try:
                        from utils.ai_generator import generate_full_article_html
                        client = get_client(get_anthropic_key())
                        with st.spinner(f"Generating article: {art_title}..."):
                            audit_results_list = st.session_state.get("audit_results", [])
                            raw_urls_s = set(r["url"] for r in audit_results_list if r.get("url"))
                            all_site_urls_local = sorted(raw_urls_s)
                            article_result = generate_full_article_html(
                                client,
                                title=art_title,
                                keywords=art.get("target_keywords", []),
                                content_type=art.get("type", "guide"),
                                products=None,
                                link_from_url=art.get("link_from", url),
                                tone_sample="",
                                site_context=st.session_state.get("site_context", ""),
                                language=st.session_state.get("content_language", "Swedish"),
                                all_site_urls=all_site_urls_local,
                                cluster_context=f"This article supports {url} as part of its topic cluster",
                            )
                        st.session_state[art_cache_key] = article_result
                        from utils.persistence import save_ai_cache
                        save_ai_cache()
                        st.rerun()
                    except Exception as e:
                        show_ai_error(
                            "Full article generation",
                            e,
                            context={
                                "article_title": art_title,
                                "keywords": art.get("target_keywords", []),
                                "link_from": art.get("link_from", url),
                                "content_type": art.get("type", "guide"),
                            },
                        )
            st.markdown("")
        _approval_button("Articles", f"{url_hash}_articles")
        st.markdown("---")
    else:
        st.markdown("#### [BLOGS] ✓ No new articles needed")
        st.markdown(
            "<div style='font-size:0.75rem; color:#33dd88; margin-bottom:0.5rem;'>"
            "AI did not identify content gaps requiring new articles.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("---")

    # ── Internal links: pages that should link TO this page ──
    audit = page["audit"]  # Local alias for the audit data
    content_audit = audit.get("content_audit") or {}
    linking = content_audit.get("linking") or {}
    link_details = linking.get("details") or {}
    link_fix_suggestions = link_details.get("link_fix_suggestions") or []

    # Inbound anchor stats
    inbound_stats = link_details.get("inbound_anchor_stats") or {}

    st.markdown("#### [INBOUND LINKS] Pages linking to this page")
    if inbound_stats:
        total_in = inbound_stats.get("total", 0)
        descriptive = inbound_stats.get("descriptive", 0)
        generic = inbound_stats.get("generic", 0)
        empty = inbound_stats.get("empty", 0)
        st.markdown(
            f"**Current inbound links:** {total_in} total · "
            f"{descriptive} descriptive · {generic} generic · {empty} empty anchors"
        )
        if total_in < 5:
            st.warning(f"Only {total_in} inbound links — this page needs MORE pages linking to it for topic authority")
        elif generic + empty > total_in * 0.3:
            st.warning(f"{generic + empty}/{total_in} inbound links use generic/empty anchors — ask linking pages to use better anchor text")
    else:
        st.warning("No inbound links data — this page may have very few internal links pointing to it")

    if link_fix_suggestions:
        st.markdown(f"**Suggested new internal links FROM other pages TO this page:** {len(link_fix_suggestions)}")
        for fix in link_fix_suggestions[:5]:
            st.markdown(f"- From: `{fix.get('from_url', '')}`  →  Add link with anchor: **{fix.get('suggested_anchor', '')}**")
            if fix.get("reason"):
                st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>{fix.get('reason', '')}</div>", unsafe_allow_html=True)
    st.markdown("---")

    # ── Links to REMOVE from this page ──
    links_to_remove = link_details.get("links_to_remove") or []
    if links_to_remove:
        st.markdown(f"#### [REMOVE LINKS] {len(links_to_remove)} links to consider removing")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.8rem;'>"
            "These links point to pages outside this topic cluster. "
            "Remove only if they don't serve user navigation.</p>",
            unsafe_allow_html=True,
        )
        for l in links_to_remove[:5]:
            st.markdown(f"- `{l.get('url', '')}` (anchor: '{l.get('anchor', '')}')")
        _approval_button("Remove links", f"{url_hash}_remove")
        st.markdown("---")

    # ── Cannibalization: keywords competing with other pages ──
    cannibal_df = st.session_state.get("cannibalization")
    if cannibal_df is not None and not cannibal_df.empty:
        page_cannibals = []
        for _, row in cannibal_df.iterrows():
            pages_detail = row.get("pages_detail", [])
            if isinstance(pages_detail, list):
                for p in pages_detail:
                    if normalize_url(p.get("page", "")) == normalize_url(url):
                        # Capture ALL competing URLs (excluding this page itself)
                        competing = []
                        for pp in pages_detail:
                            pu = pp.get("page", "")
                            if normalize_url(pu) != normalize_url(url):
                                competing.append({
                                    "url": pu,
                                    "position": pp.get("position", "?"),
                                    "clicks": pp.get("clicks", 0),
                                    "impressions": pp.get("impressions", 0),
                                })
                        page_cannibals.append({
                            "query": row["query"],
                            "severity": row["severity"],
                            "lost_clicks": row["lost_clicks_estimate"],
                            "winner": row.get("recommended_winner", ""),
                            "merge_action": row.get("merge_action", ""),
                            "page_count": row.get("page_count", 2),
                            "competing_pages": competing,
                        })
                        break
        if page_cannibals:
            # ── CONSOLIDATE: group by competing URL so the same
            # competitor doesn't repeat 5x for keyword variants ──
            from collections import defaultdict
            by_competitor = defaultdict(lambda: {"queries": [], "total_lost": 0, "merge_action": "", "severity": "mild", "is_winner": True, "competing_pages": []})
            for c in page_cannibals:
                # Build a key from the competing URLs (sorted)
                comp_key = tuple(sorted(normalize_url(cp["url"]) for cp in (c.get("competing_pages") or [])))
                if not comp_key:
                    comp_key = ("unknown",)
                grp = by_competitor[comp_key]
                grp["queries"].append(c["query"])
                grp["total_lost"] += c.get("lost_clicks", 0)
                if c.get("severity") == "severe":
                    grp["severity"] = "severe"
                elif c.get("severity") == "moderate" and grp["severity"] == "mild":
                    grp["severity"] = "moderate"
                if not (normalize_url(c.get("winner", "")) == normalize_url(url)):
                    grp["is_winner"] = False
                if not grp["merge_action"] and c.get("merge_action"):
                    grp["merge_action"] = c["merge_action"]
                if not grp["competing_pages"] and c.get("competing_pages"):
                    grp["competing_pages"] = c["competing_pages"]

            groups = sorted(by_competitor.values(), key=lambda g: -g["total_lost"])
            total_conflicts = len(page_cannibals)
            unique_competitors = len(groups)
            st.markdown(f"#### [CANNIBALIZATION] {total_conflicts} keyword conflicts → {unique_competitors} unique competitor(s)")

            for grp in groups[:5]:
                sev_color = {"severe": "#ff4455", "moderate": "#ffaa33", "mild": "#6b6b8a"}.get(grp["severity"], "#6b6b8a")
                winner_label = "🏆 This page WINS" if grp["is_winner"] else "✗ Competitor leads"
                queries_str = ", ".join(f"'{q}'" for q in grp["queries"][:5])
                if len(grp["queries"]) > 5:
                    queries_str += f" +{len(grp['queries'])-5} more"

                st.markdown(
                    f"<div style='background:#12121f; border-left:4px solid {sev_color}; "
                    f"padding:0.8rem; margin:0.5rem 0; border-radius:0 6px 6px 0;'>"
                    f"<div style='font-size:0.9rem; color:#e8e8f0; font-weight:600;'>"
                    f"{len(grp['queries'])} keywords: {queries_str}</div>"
                    f"<div style='color:{sev_color}; font-size:0.8rem; margin-top:0.2rem;'>"
                    f"[{grp['severity'].upper()}] · {grp['total_lost']:,} total lost clicks · {winner_label}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                if grp.get("competing_pages"):
                    st.markdown("**Competing with:**")
                    for cp in grp["competing_pages"]:
                        st.markdown(
                            f"- `{cp['url']}` — pos {cp.get('position','?')} · "
                            f"{cp.get('clicks',0)} clicks · {cp.get('impressions',0):,} impressions"
                        )

                if grp.get("merge_action"):
                    with st.popover("What to do"):
                        st.markdown(grp["merge_action"])

            _approval_button("Cannibal", f"{url_hash}_cannibal")
            st.markdown("---")

    # ── Schema, alt text, crawl issues ──
    st.markdown("#### [TECHNICAL]")
    tech_items = []

    # Schema
    schema_types = audit.get("schema_types", []) or []
    if not any("breadcrumb" in str(s).lower() for s in schema_types):
        tech_items.append("Missing BreadcrumbList schema")
    if page["page_type"] == "category" and not any("itemlist" in str(s).lower() or "collection" in str(s).lower() for s in schema_types):
        tech_items.append("Missing ItemList/Collection schema (recommended for category pages)")

    # Alt text
    images_no_alt = audit.get("images_without_alt", 0)
    if images_no_alt > 0:
        tech_items.append(f"{images_no_alt} images missing alt text")

    # Crawl issues for this URL
    crawl_issues = st.session_state.get("sf_crawl_issues", {})
    if crawl_issues:
        for issue_type in ["broken_links", "non_indexable", "redirect_chains", "canonical_issues", "near_duplicates"]:
            items = crawl_issues.get(issue_type, [])
            for item in items:
                if normalize_url(item.get("url", "")) == normalize_url(url):
                    tech_items.append(f"{issue_type.replace('_', ' ').title()}: {item.get('action', '')[:100]}")
                    break

    # Authority
    rd = audit.get("referring_domains", 0)
    if rd < 5:
        tech_items.append(f"LOW backlink authority: only {rd} referring domains — this page needs link building")
    elif rd >= 50:
        tech_items.append(f"✓ Strong authority: {rd} referring domains")

    # AI quality verdict
    from utils.quality_check_runner import quality_key as _qk_qw2
    quality = st.session_state.get(_qk_qw2(url))
    if quality:
        verdict = quality.get("verdict", "")
        score = quality.get("score", 0)
        v_color = {"REWRITE": "#ff4455", "IMPROVE": "#ffaa33", "KEEP": "#33dd88"}.get(verdict, "#6b6b8a")
        tech_items.append(f"<span style='color:{v_color}; font-weight:600;'>AI text quality: {verdict} ({score}/10)</span> — {quality.get('summary', '')[:120]}")

    if tech_items:
        for item in tech_items:
            st.markdown(f"- {item}", unsafe_allow_html=True)
    else:
        st.markdown("<div style='color:#33dd88;'>No technical issues detected</div>", unsafe_allow_html=True)


def _section_status(label: str, has_data: bool, has_error: bool, is_ok: bool = False) -> tuple:
    """Return (icon, color) for a per-page section status badge."""
    if has_error:
        return ("⚠", "#ff6644")
    if is_ok:
        return ("✓", "#33dd88")
    if has_data:
        return ("●", "#ffaa33")  # has new content waiting for review
    return ("○", "#6b6b8a")  # missing


def _render_status_bar(page, plan_data, text_data, intro_data) -> None:
    """One-line status badge row: Plan / Bottom / Intro / Meta status at a glance."""
    url = page["url"]
    url_hash = stable_hash(url)
    audit = page.get("audit") or {}

    has_plan = bool(plan_data and not plan_data.get("error"))
    plan_err = bool(isinstance(plan_data, dict) and plan_data.get("error"))

    has_text = bool(text_data and not text_data.get("error"))
    text_err = bool(isinstance(text_data, dict) and text_data.get("error"))

    has_intro = bool(intro_data and not intro_data.get("error"))
    intro_err = bool(isinstance(intro_data, dict) and intro_data.get("error"))
    intro_ok_existing = (
        not has_intro
        and not intro_err
        and audit.get("intro_word_count", 0) >= 50
    )

    plan = plan_data or {}
    new_title = plan.get("meta_title", "") or ""
    new_desc = plan.get("meta_description", "") or ""
    meta_cache = st.session_state.get(f"_cannibal_meta_{url_hash}") or {}
    if isinstance(meta_cache, dict) and not new_title:
        v = (meta_cache.get("variants") or [])
        if v:
            new_title = v[0].get("title", "") or new_title
            new_desc = v[0].get("description", "") or new_desc
    has_meta_change = bool(
        (new_title and new_title != (page.get("title") or ""))
        or (new_desc and new_desc != (page.get("meta_description") or ""))
    )
    # Use the same verdict logic as the "WHAT GOOGLE SEES" panel so
    # the status bar agrees with the per-element diagnosis (catches
    # missing primary keyword and missing CTA on top of length checks).
    _meta_pk = _primary_keyword_for_page(page)
    _t_status, *_ = _verdict_for_title(page.get("title") or "", _meta_pk)
    _d_status, *_ = _verdict_for_description(page.get("meta_description") or "", _meta_pk)
    meta_needs_change = _t_status in ("warn", "bad") or _d_status in ("warn", "bad")
    meta_ok = not meta_needs_change and not has_meta_change

    pi, pc = _section_status("Plan", has_plan, plan_err)
    ti, tc = _section_status("Bottom", has_text, text_err)
    ii, ic = _section_status("Intro", has_intro, intro_err, is_ok=intro_ok_existing)
    # Meta status: ⚠ when structurally wrong (length / missing kw / missing CTA),
    # ● when AI suggestion exists, ✓ when OK, ○ otherwise.
    if meta_needs_change and not has_meta_change:
        mi, mc = ("⚠", "#ff6644")
    else:
        mi, mc = _section_status("Meta", has_meta_change, False, is_ok=meta_ok)

    parts = ["<div style='display:flex; gap:0.5rem; flex-wrap:wrap; margin:0.4rem 0 0.8rem 0;'>"]
    for icon, color, label in (
        (pi, pc, "Plan"),
        (ti, tc, "Bottom"),
        (ii, ic, "Intro"),
        (mi, mc, "Meta"),
    ):
        parts.append(
            f"<div style='background:#0d0d15; border:1px solid {color}; "
            f"border-radius:4px; padding:0.3rem 0.6rem; font-size:0.75rem; "
            f"color:{color}; font-family:\"IBM Plex Mono\",monospace;'>"
            f"{icon} {label}</div>"
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def _section_card_header(label: str, icon: str, color: str, summary: str = "") -> str:
    """Compact header HTML for a section card expander label."""
    return f"{icon} {label}" + (f" — {summary}" if summary else "")


def render_page_actions_card(page, idx=None, total_pages=None, on_skip=None):
    """
    Render the full per-page SEO action card.
    Called by Quick Wins' per-page tab with prev/next navigation via the
    on_skip callback.
    """
    url = page["url"]
    url_hash = stable_hash(url)

    # Check if this page is scheduled for merge/delete in ideal structure
    ideal = st.session_state.get("_ideal_structure", {})
    merge_target = None
    delete_reason = None
    if isinstance(ideal, dict):
        for m in ideal.get("merge", []) or []:
            if isinstance(m, dict):
                from_urls = [normalize_url(u) for u in m.get("from", [])]
                if normalize_url(url) in from_urls:
                    merge_target = {"to": m.get("to", ""), "why": m.get("why", "")}
                    break
        for d in ideal.get("delete", []) or []:
            if isinstance(d, dict) and normalize_url(d.get("url", "")) == normalize_url(url):
                delete_reason = d.get("why", "")
                break

    if merge_target:
        st.error(
            f"⚠ **AI Ideal Structure recommends MERGING this page** into `{merge_target['to']}`\n\n"
            f"**Reason:** {merge_target['why']}\n\n"
            f"**Action:** Copy unique content to target, set up 301 redirect, update internal links. "
            f"Do NOT invest in improving this page — it should be removed."
        )

    if delete_reason:
        st.error(
            f"⚠ **AI Ideal Structure recommends DELETING this page**\n\n"
            f"**Reason:** {delete_reason}\n\n"
            f"**Action:** Delete the page, set up 301 redirect to a related page if it has backlinks."
        )

    # Header card
    border = "#ff4455" if page["lost_clicks"] > 1000 else "#ffaa33" if page["lost_clicks"] > 200 else "#5533ff"
    st.markdown(
        f"<div style='background:#0d0d15; border:2px solid {border}; border-left:6px solid {border}; "
        f"border-radius:8px; padding:1rem; margin-bottom:1rem;'>"
        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:{border}; margin-bottom:0.3rem;'>"
        f"{('#' + str(idx+1) + ' · ') if idx is not None else ''}{page['page_type'].upper()}</div>"
        f"<div style='font-size:1rem; color:#e8e8f0; font-weight:600; word-break:break-all;'>{url}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Impressions", f"{page['impressions']:,}")
    c2.metric("Lost clicks", f"{page['lost_clicks']:,}")
    c3.metric("Meta score", f"{page['meta_score']}/100")
    c4.metric("Content score", f"{page['content_score']}/100")

    # ── Status bar — Plan / Bottom / Intro / Meta at a glance ──
    _plan_data_for_bar = st.session_state.get(f"_ai_plan_{url_hash}", {})
    _text_data_for_bar = st.session_state.get(f"_bottom_text_{url_hash}", {})
    _intro_data_for_bar = st.session_state.get(f"_intro_text_{url_hash}", {})
    _render_status_bar(page, _plan_data_for_bar, _text_data_for_bar, _intro_data_for_bar)

    # ── Current SEO state — what Google sees right now + per-element verdict ──
    _render_current_seo_state(page)

    # ── Topical scope — which queries this page should/shouldn't target ──
    _render_topical_scope_panel(page)

    # ── DO THIS FIRST — clear, single top-priority action ──
    issues = _detect_issues(page)
    if issues:
        top_issue = issues[0]
        st.markdown(
            f"<div style='background:#1a1020; border:2px solid #ff6644; border-radius:8px; "
            f"padding:1rem; margin:0.5rem 0 1rem 0;'>"
            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; "
            f"color:#ff6644; letter-spacing:0.05em; margin-bottom:0.3rem;'>DO THIS FIRST</div>"
            f"<div style='font-size:1rem; color:#e8e8f0; font-weight:600;'>{top_issue}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Other issues ────────────────────────────────────────
    if len(issues) > 1:
        with st.expander(f"All {len(issues)} issues detected", expanded=False):
            for issue in issues:
                st.markdown(f"- {issue}")
    elif not issues:
        st.success("No major issues detected on this page")

    st.markdown("---")

    # ── TOTAL PLAN (ordered action list) ────────────────────
    plan_key = f"_ai_plan_{url_hash}"
    text_key = f"_bottom_text_{url_hash}"
    intro_key = f"_intro_text_{url_hash}"

    plan_data = st.session_state.get(plan_key, {})
    text_data = st.session_state.get(text_key, {})
    intro_data = st.session_state.get(intro_key, {})

    if plan_data and not plan_data.get("error"):
        total_plan = _build_total_plan(page, plan_data, text_data, intro_data)
        if total_plan:
            total_time = sum(a["time"] for a in total_plan)

            st.markdown(f"### 📋 TOTAL PLAN — {len(total_plan)} actions · ~{total_time} min")
            st.markdown(
                "<p style='color:#9b9bb8; font-size:0.85rem;'>"
                "Ordered by priority. Start from #1 and work down.</p>",
                unsafe_allow_html=True,
            )

            for a in total_plan:
                priority_colors = {
                    1: "#ff4455",  # Cannibalization
                    2: "#ff6644",  # Meta
                    3: "#ffaa33",  # Bottom text
                    4: "#ffaa33",  # Intro
                    5: "#c8b4ff",  # Links add
                    6: "#c8b4ff",  # Links remove
                    7: "#5bb4d4",  # Blogs
                    8: "#6b6b8a",  # Technical
                }
                color = priority_colors.get(a["priority"], "#6b6b8a")
                st.markdown(
                    f"<div style='background:#0d0d15; border-left:3px solid {color}; padding:0.6rem 0.8rem; margin-bottom:0.4rem; border-radius:0 4px 4px 0;'>"
                    f"<div style='font-size:0.85rem; color:#e8e8f0;'><strong>{a['priority']}. {a['title']}</strong> "
                    f"<span style='color:{color}; font-size:0.7rem;'>· {a['time']} min</span></div>"
                    f"<div style='color:#9b9bb8; font-size:0.75rem; margin-top:0.2rem;'>{a['detail']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            # Export button
            col_exp1, col_exp2 = st.columns([3, 1])
            with col_exp2:
                markdown_export = _export_page_as_markdown(page, plan_data, text_data, intro_data)
                st.download_button(
                    "📄 Export all to Markdown",
                    data=markdown_export,
                    file_name=f"seo_plan_{shorten_url(url).replace('/', '_').strip('_')}.md",
                    mime="text/markdown",
                    key=f"export_{url_hash}",
                    use_container_width=True,
                )
            st.markdown("---")

    # ── Generate / Show fixes ────────────────────────────────
    has_plan = bool(plan_data and not plan_data.get("error"))
    has_text = bool(text_data and not text_data.get("error"))
    has_intro = bool(intro_data and not intro_data.get("error"))

    # Render any cached AI failure so users see WHY the last attempt failed,
    # not just a silent "not generated yet" state.
    for _label, _cached in (
        ("Implementation plan", plan_data),
        ("Bottom text", text_data),
        ("Intro text", intro_data),
    ):
        if _cached and _cached.get("error"):
            _cls = _cached.get("error_class") or "Exception"
            _msg = _cached.get("error", "")
            _status = _cached.get("error_status_code")
            _req = _cached.get("error_request_id")
            _tb_txt = _cached.get("error_traceback", "")
            st.error(f"**{_label} — previous attempt failed** · `{_cls}`: {_msg}")
            with st.expander(f"{_label}: full error details", expanded=False):
                if _status:
                    st.markdown(f"- **HTTP status:** `{_status}`")
                if _req:
                    st.markdown(f"- **Request ID:** `{_req}`")
                if _tb_txt:
                    st.markdown("- **Traceback:**")
                    st.code(_tb_txt, language="text")

    if not has_plan:
        st.markdown("### AI fixes — not generated yet")
        st.info("Click below to generate implementation plan for this page (~20 seconds)")
        if st.button("Generate plan", type="primary", use_container_width=True, key=f"gen_all_{url_hash}"):
            _generate_all_fixes(page)
            st.rerun()
    else:
        # Check if old format — show prominent regenerate button
        is_old_format = has_text and not (text_data.get("top_html") or text_data.get("bottom_html") or text_data.get("faq_schema"))
        col_h1, col_h2 = st.columns([3, 2] if is_old_format else [4, 1])
        with col_h1:
            st.markdown("### AI-generated fixes")
        with col_h2:
            btn_label = "🔄 Regenerate with new rules" if is_old_format else "Regenerate"
            btn_type = "primary" if is_old_format else "secondary"
            if st.button(btn_label, key=f"regen_{url_hash}", type=btn_type, use_container_width=True):
                # Snapshot what was cached before clearing — Regenerate
                # should rebuild the SAME outputs that existed, not just
                # the plan. Otherwise users have to click Generate bottom
                # text + Generate intro again afterwards.
                had_text = text_key in st.session_state
                had_intro = f"_intro_text_{url_hash}" in st.session_state

                # Clear cached results for this page
                intro_key = f"_intro_text_{url_hash}"
                for k in [plan_key, text_key, intro_key]:
                    st.session_state.pop(k, None)
                # Also delete from disk cache
                try:
                    import os
                    for k in [plan_key, text_key, intro_key]:
                        path = os.path.join("/data/ai_cache", f"{k}.json")
                        if os.path.exists(path):
                            os.remove(path)
                except Exception:
                    pass

                # Regenerate plan (always — fast)
                _generate_all_fixes(page)

                # If a bottom text was cached, regenerate it with the
                # current rules so the user doesn't have to click
                # 'Generate bottom text' a second time.
                if had_text:
                    with st.spinner("Regenerating bottom text with new rules..."):
                        try:
                            from utils.ai_generator import generate_page_content
                            result = generate_page_content(url)
                            st.session_state[text_key] = result
                        except Exception as e:
                            import traceback as _tb
                            show_ai_error(
                                "Bottom text regeneration",
                                e,
                                context={"url": url, "page_type": page.get("page_type")},
                            )
                            st.session_state[text_key] = {
                                "error": str(e),
                                "error_class": type(e).__name__,
                                "error_traceback": _tb.format_exc()[-3000:],
                            }
                        from utils.persistence import save_ai_cache
                        save_ai_cache()

                # If an intro rewrite was cached, regenerate that too.
                if had_intro:
                    with st.spinner("Regenerating intro rewrite..."):
                        try:
                            from utils.ai_generator import get_client, generate_intro_rewrite
                            client = get_client(get_anthropic_key())
                            content_audit = page["audit"].get("content_audit") or {}
                            kw_coverage = content_audit.get("keyword_coverage") or {}
                            missing_kws = (kw_coverage.get("missing", []) or [])[:8]
                            if not missing_kws:
                                missing_kws = page["audit"].get("target_keywords", [])[:8]
                            result = generate_intro_rewrite(
                                client,
                                missing_keywords=missing_kws,
                                existing_intro=page["audit"].get("intro_text", "") or "",
                                page_type=page.get("page_type", "category"),
                                url=url,
                                site_context=st.session_state.get("site_context", ""),
                                language=st.session_state.get("content_language", "Swedish"),
                            )
                            st.session_state[intro_key] = result
                        except Exception as e:
                            st.session_state[intro_key] = {
                                "error": str(e),
                                "error_class": type(e).__name__,
                            }
                        from utils.persistence import save_ai_cache
                        save_ai_cache()

                st.rerun()

        plan = st.session_state.get(plan_key, {})

        # ── CARD 1: BOTTOM TEXT ──────────────────────────────────
        # Auto-expand whenever something needs the user's attention
        # (new content waiting for review, errored, or missing). Only
        # collapse when this card is in a finished/no-op state. The
        # setup-parameter still forces every card open if the user
        # prefers that.
        _expand_default = bool(st.session_state.get("_qw_per_page_default_expanded", False))
        if has_text:
            _btm_summary = "● generated · review + push"
            _btm_icon = "📝"
            _btm_expand = True  # ● has new content waiting for review
        elif page["page_type"] == "category":
            _btm_summary = "○ click to generate"
            _btm_icon = "📝"
            _btm_expand = True  # missing artifact = expand so the action is visible
        else:
            _btm_summary = "— not applicable for this page type"
            _btm_icon = "📝"
            _btm_expand = _expand_default
        _bottom_card = st.expander(
            f"{_btm_icon} **Bottom text** — {_btm_summary}",
            expanded=_btm_expand,
        )
        with _bottom_card:
            if not has_text and page["page_type"] == "category":
                if st.button("Generate bottom text", type="primary", key=f"gen_bottom_{url_hash}"):
                    with st.spinner("Generating page text with FAQ + E-E-A-T..."):
                        try:
                            from utils.ai_generator import generate_page_content
                            result = generate_page_content(url)
                            st.session_state[text_key] = result
                        except Exception as e:
                            import traceback as _tb
                            show_ai_error(
                                "Bottom text generation",
                                e,
                                context={"url": url, "page_type": page.get("page_type")},
                            )
                            st.session_state[text_key] = {
                                "error": str(e),
                                "error_class": type(e).__name__,
                                "error_status_code": getattr(e, "status_code", None),
                                "error_request_id": getattr(e, "request_id", None),
                                "error_traceback": _tb.format_exc()[-3000:],
                            }
                        from utils.persistence import save_ai_cache
                        save_ai_cache()
                    st.rerun()

            if has_text:
                st.markdown(
                    "<div style='background:#0d0d15; border:1px solid #ffaa33; border-radius:6px; padding:0.6rem; margin-bottom:0.5rem;'>"
                    "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#ffaa33;'>POSITION</div>"
                    "<div style='font-size:0.8rem; color:#e8e8f0;'>"
                    "This is the <strong>BOTTOM TEXT</strong> shown <strong>BELOW</strong> the product grid on the category page. "
                    "<br>It is NOT the intro text above the products. "
                    "<br>In Magento 1.9: typically the <strong>Description</strong> field on the category."
                    "</div></div>",
                    unsafe_allow_html=True,
                )

                # Show current intro text length so user knows we don't touch it
                intro_words = page["audit"].get("intro_word_count", 0)
                bottom_words = page["audit"].get("bottom_word_count", 0)
                st.markdown(
                    f"<div style='font-size:0.75rem; color:#6b6b8a; margin-bottom:0.5rem;'>"
                    f"Current intro text: {intro_words} words (above grid — NOT touched) · "
                    f"Current bottom text: {bottom_words} words (below grid — REPLACED)</div>",
                    unsafe_allow_html=True,
                )

                text_data = st.session_state[text_key]
                # Check if generated with new rules (top/bottom split + FAQ schema)
                has_new_format = text_data.get("top_html") or text_data.get("bottom_html") or text_data.get("faq_schema")
                if not has_new_format and text_data.get("html"):
                    st.warning("⚠ Text generated with old rules. Click **Regenerate** below for improved text with FAQ schema, product images, hierarchy links, and no prices.")
                html = text_data.get("bottom_html") or text_data.get("html", "")
                wc = text_data.get("bottom_word_count") or text_data.get("word_count", 0)
                kws, links, prods = extract_content_summary(text_data)
                from utils.ui_helpers import compute_lix, lix_badge
                lix = compute_lix(html)
                lix_color, lix_msg, _ = lix_badge(lix)
                st.markdown(
                    f"**New bottom text:** {wc} words · **Keywords:** {len(kws)} · "
                    f"**Internal links:** {len(links)} · **Products:** {len(prods)} · "
                    f"<span style='color:{lix_color};'>**LIX {lix}**</span>",
                    unsafe_allow_html=True,
                )
                _btn_col1, _btn_col2, _btn_col3 = st.columns(3)
                with _btn_col1:
                    with st.popover("👁 View HTML preview", use_container_width=True):
                        st.code(html[:3000] + ("..." if len(html) > 3000 else ""), language="html")
                with _btn_col2:
                    with st.popover("✏️ Edit before push", use_container_width=True):
                        st.markdown(
                            "<div style='font-size:0.75rem; color:#9b9bb8; margin-bottom:0.4rem;'>"
                            "Edit the HTML directly. Changes are kept in session and used "
                            "by the Push button below. Click <strong>Save edits</strong> "
                            "before closing this popover.</div>",
                            unsafe_allow_html=True,
                        )
                        edit_key = f"edit_bottom_{url_hash}"
                        edited = st.text_area(
                            "Bottom HTML",
                            value=html,
                            height=400,
                            key=edit_key,
                            label_visibility="collapsed",
                        )
                        save_col, reset_col = st.columns([1, 1])
                        with save_col:
                            if st.button(
                                "💾 Save edits",
                                key=f"save_bottom_{url_hash}",
                                type="primary",
                                use_container_width=True,
                            ):
                                _td = dict(st.session_state.get(text_key) or {})
                                _td["bottom_html"] = edited
                                _td["bottom_word_count"] = len(
                                    __import__("re").sub(r"<[^>]+>", " ", edited).split()
                                )
                                _td["_user_edited"] = True
                                st.session_state[text_key] = _td
                                from utils.persistence import save_ai_cache
                                save_ai_cache()
                                st.success("Saved. Close this popover and click Push to send the edited version.")
                                st.rerun()
                        with reset_col:
                            if st.button(
                                "↩ Discard edits",
                                key=f"reset_bottom_{url_hash}",
                                use_container_width=True,
                            ):
                                # Remove user-edited flag so next render shows original
                                _td = dict(st.session_state.get(text_key) or {})
                                _td.pop("_user_edited", None)
                                st.session_state[text_key] = _td
                                st.rerun()
                with _btn_col3:
                    st.download_button(
                        "⬇ Download HTML",
                        data=html,
                        file_name=f"{shorten_url(url).replace('/', '_').strip('_')}_bottom.html",
                        mime="text/html",
                        key=f"dl_text_{url_hash}",
                        use_container_width=True,
                    )

                # ── Quality gate (prompt-level validators run during generation) ──
                _qc = text_data.get("_quality_checks") or []
                if _qc:
                    _qpass = text_data.get("_quality_pass_count", 0)
                    _qtot = text_data.get("_quality_total", len(_qc))
                    _qcolor = "#33dd88" if _qpass == _qtot else ("#ffaa33" if _qpass >= _qtot - 2 else "#ff4455")
                    st.markdown(
                        f"<div style='background:#0d0d15; border:2px solid {_qcolor}; "
                        f"border-radius:6px; padding:0.6rem; margin:0.5rem 0;'>"
                        f"<div style='font-size:0.85rem; color:{_qcolor}; font-weight:700;'>"
                        f"Quality gate: {_qpass}/{_qtot} checks passed"
                        f"</div>"
                        f"<div style='font-size:0.7rem; color:#9b9bb8; margin-top:0.2rem;'>"
                        f"Run automatically during generation. Failing checks trigger auto-retry "
                        f"(up to 3 attempts) before showing the result here.</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    with st.expander(
                        f"Quality gate detail ({_qpass}/{_qtot} passed)",
                        expanded=(_qpass < _qtot),
                    ):
                        for c in _qc:
                            _cicon = "✓" if c["passed"] else "✗"
                            _ccolor = "#33dd88" if c["passed"] else "#ff4455"
                            st.markdown(
                                f"<div style='font-size:0.8rem; color:{_ccolor}; margin:0.2rem 0;'>"
                                f"{_cicon} <strong>{c['label']}</strong> "
                                f"<span style='color:#9b9bb8;'>· {c['actual']}</span></div>",
                                unsafe_allow_html=True,
                            )

                # ── Push to Magento (preview → confirm) ──
                # If the user edited the text, push the EDITED version, not the original.
                _push_html = (st.session_state.get(text_key) or {}).get("bottom_html") or html
                from utils.footer_push_ui import render_footer_push_block
                render_footer_push_block(url, _push_html, key_prefix=f"qw_push_{url_hash}")

                st.markdown(
                    "<div style='background:#0d0d15; border-left:3px solid #5533ff; padding:0.8rem; margin:0.5rem 0;'>"
                    "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#5533ff;'>MANUAL FALLBACK — IF PUSH IS NOT AVAILABLE</div>"
                    "<div style='font-size:0.85rem; color:#c8b4ff;'>"
                    "1) Download HTML  2) Magento Admin → Catalog → Categories → this category  "
                    "3) Paste into <strong>Description</strong> field (NOT 'Page Title' or 'Meta')  "
                    "4) Make sure 'Display Mode' is set to 'Products and Static Block' or 'Static Block and Products' "
                    "5) Save and clear cache</div></div>",
                    unsafe_allow_html=True,
                )
                _approval_button("Bottom Text", f"{url_hash}_text")

                # ── QUALITY VALIDATION of generated content ──
                st.markdown("##### Quality validation")
                val_results = _validate_generated_content(page, text_data, plan)
                total_checks = len(val_results["checks"])
                passed = val_results["passed"]
                failed = val_results["failed"]
                warnings = val_results["warnings"]

                # Status badge
                if failed == 0 and warnings == 0:
                    badge_color = "#33dd88"
                    badge_text = f"✓ All {total_checks} validations passed"
                elif failed == 0:
                    badge_color = "#ffaa33"
                    badge_text = f"⚠ {passed}/{total_checks} passed, {warnings} warnings"
                else:
                    badge_color = "#ff4455"
                    badge_text = f"✗ {failed} FAILED, {warnings} warnings, {passed} passed"

                st.markdown(
                    f"<div style='background:#0d0d15; border:2px solid {badge_color}; border-radius:6px; padding:0.6rem; margin:0.5rem 0;'>"
                    f"<div style='font-size:0.85rem; color:{badge_color}; font-weight:600;'>{badge_text}</div></div>",
                    unsafe_allow_html=True,
                )

                # Show individual check results — inline when something
                # failed (so the user sees what's wrong), behind a
                # popover when everything passed (just confirmation).
                def _render_checks():
                    for check in val_results["checks"]:
                        icon = "✓" if check["passed"] else ("✗" if check["severity"] == "error" else "⚠")
                        color = "#33dd88" if check["passed"] else ("#ff4455" if check["severity"] == "error" else "#ffaa33")
                        st.markdown(
                            f"<div style='font-size:0.8rem; color:{color}; margin:0.2rem 0;'>"
                            f"{icon} {check['message']}</div>",
                            unsafe_allow_html=True,
                        )
                if failed > 0 or warnings > 0:
                    _render_checks()
                else:
                    with st.popover("View all validation checks"):
                        _render_checks()

                # ── Regenerate with these fixes — feeds failing checks back to the AI prompt ──
                if failed > 0 or warnings > 0:
                    failing_msgs = [
                        c["message"] for c in val_results["checks"]
                        if not c["passed"] and c.get("severity") in ("error", "warning")
                    ]
                    if failing_msgs:
                        st.markdown(
                            f"<div style='font-size:0.8rem; color:#c8b4ff; margin:0.3rem 0;'>"
                            f"Regenerating will inject these {len(failing_msgs)} issue(s) into the prompt with 'fix these'.</div>",
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            f"🔄 Regenerate bottom text — fix these {len(failing_msgs)} issue(s)",
                            key=f"regen_bottom_{url_hash}",
                            type="primary",
                        ):
                            if not has_anthropic_key():
                                st.error("Anthropic API key missing — set it in **1. Setup & Connect** first.")
                                st.stop()
                            with st.spinner(f"Regenerating bottom text with {len(failing_msgs)} fixes…"):
                                try:
                                    from utils.ai_generator import generate_page_content
                                    result = generate_page_content(url, validation_fixes=failing_msgs)
                                    st.session_state[text_key] = result
                                    from utils.persistence import save_ai_cache
                                    save_ai_cache()
                                    st.success("Regenerated — scroll up to review new text + validation.")
                                    st.rerun()
                                except Exception as e:
                                    import traceback as _tb
                                    show_ai_error(
                                        "Bottom text regeneration",
                                        e,
                                        context={"url": url, "validation_fixes": failing_msgs},
                                    )
                                    st.session_state[text_key] = {
                                        "error": str(e),
                                        "error_class": type(e).__name__,
                                        "error_status_code": getattr(e, "status_code", None),
                                        "error_request_id": getattr(e, "request_id", None),
                                        "error_traceback": _tb.format_exc()[-3000:],
                                    }

        # ── CARD 3: META TITLE + DESCRIPTION ─────────────────────────
        new_title = plan.get("meta_title", "") or page["title"]
        new_desc = plan.get("meta_description", "") or page["meta_description"]
        meta_changed = plan.get("meta_changed", False)

        # Use the same verdict functions that drive the "WHAT GOOGLE
        # SEES" panel above — otherwise this card disagrees with the
        # diagnosis the user just read (e.g. WHAT GOOGLE SEES says
        # "Generate new — missing primary keyword 'penisring'" but
        # the card says "✓ OK · no changes needed" because the
        # length-only check passes). The verdict catches: too long,
        # too short, missing primary keyword, missing CTA, missing tag.
        _meta_primary_kw = _primary_keyword_for_page(page)
        _title_status, *_ = _verdict_for_title(page.get("title") or "", _meta_primary_kw)
        _desc_status, *_ = _verdict_for_description(page.get("meta_description") or "", _meta_primary_kw)
        needs_meta_change = (
            meta_changed
            or _title_status in ("warn", "bad")
            or _desc_status in ("warn", "bad")
        )

        _meta_summary = "⚠ changes needed" if needs_meta_change else "✓ OK · no changes needed"
        with st.expander(
            f"🏷 **Meta title + description** — {_meta_summary}",
            expanded=needs_meta_change or _expand_default,
        ):
            if needs_meta_change:
                # Pre-compute meta cache key so both title + description sections can use it
                meta_key = f"_cannibal_meta_{stable_hash(page['url'])}"

                # Resolve recommended title — from action plan, or from cached AI meta
                recommended_title = new_title if new_title and new_title != page['title'] else ""
                recommended_desc = new_desc if new_desc and new_desc != page['meta_description'] else ""
                if (not recommended_title or not recommended_desc) and meta_key in st.session_state:
                    cached_meta = st.session_state.get(meta_key) or {}
                    if isinstance(cached_meta, dict):
                        variants = cached_meta.get("variants", []) or []
                        if variants:
                            if not recommended_title:
                                recommended_title = variants[0].get("title", "") or ""
                            if not recommended_desc:
                                recommended_desc = variants[0].get("description", "") or ""

                # Title — visible diff card
                render_recommendation_diff(
                    "Meta title",
                    page["title"] or "",
                    recommended_title,
                    kind="title",
                    note="Aim for 30–65 chars. Front-load the primary keyword and add a benefit modifier.",
                )

                # Description — visible diff card
                render_recommendation_diff(
                    "Meta description",
                    page["meta_description"] or "",
                    recommended_desc,
                    kind="description",
                    note="Aim for 120–165 chars. Lead with the keyword, end with a soft CTA.",
                )

                # AI generate button — show whenever EITHER field is
                # missing or fails the verdict check. Length-equal-to-
                # current is treated as "missing" so users can always
                # regenerate when the WHAT GOOGLE SEES diagnosis flagged
                # something the cached suggestion didn't fix.
                _gen_btn_label = "🤖 Generate meta title + description"
                if recommended_title and not recommended_desc:
                    _gen_btn_label = "🤖 Generate meta description"
                elif recommended_desc and not recommended_title:
                    _gen_btn_label = "🤖 Generate meta title"
                elif recommended_title and recommended_desc:
                    _gen_btn_label = "🤖 Regenerate meta title + description"
                if st.button(_gen_btn_label, key=f"gen_meta_{stable_hash(page['url'])}"):
                        if not has_anthropic_key():
                            st.error(
                                "Anthropic API key is missing. Set it in **1. Setup & Connect** "
                                "or as the `ANTHROPIC_API_KEY` env var on Railway, then retry."
                            )
                            st.stop()
                        try:
                            from utils.ai_generator import get_client, generate_meta_suggestions
                            from utils.page_profile import build_page_profile
                            # NB: get_anthropic_key is imported at module top (line 7).
                            # Do NOT re-import it inside this function — Python would
                            # then treat it as local, and any earlier reference (e.g. the
                            # intro generate button) would raise UnboundLocalError.
                            client = get_client(get_anthropic_key())
                            profile = build_page_profile(page["url"])
                            target_kws = [q["query"] for q in profile.get("gsc_queries", [])[:5]]
                            result = generate_meta_suggestions(client, page["audit"], target_kws,
                                st.session_state.get("site_context", ""),
                                st.session_state.get("content_language", "Swedish"))
                            st.session_state[meta_key] = result
                            st.rerun()
                        except Exception as e:
                            show_ai_error(
                                "Meta title + description generation",
                                e,
                                context={
                                    "url": page["url"],
                                    "target_keywords": target_kws if "target_kws" in dir() else "(not computed)",
                                },
                            )

                if recommended_title and recommended_desc:
                    with st.popover("Copy both as block"):
                        st.code(f"Title: {recommended_title}\nDescription: {recommended_desc}", language="text")

                # ── Inline push buttons (Mshop Admin API) ──
                # Only push values that actually differ from what's live, so
                # users can't accidentally re-push the existing value.
                _push_title = recommended_title if recommended_title and recommended_title != (page.get("title") or "") else ""
                _push_desc = recommended_desc if recommended_desc and recommended_desc != (page.get("meta_description") or "") else ""
                from utils.mshop_admin_push_ui import (
                    render_inline_meta_title_push,
                    render_inline_meta_desc_push,
                    render_push_resolution_banner,
                )
                render_push_resolution_banner(url)
                _meta_push_col1, _meta_push_col2 = st.columns(2)
                with _meta_push_col1:
                    render_inline_meta_title_push(
                        url, _push_title,
                        key_prefix=f"qw_meta_{url_hash}",
                        current_title=page.get("title") or "",
                    )
                with _meta_push_col2:
                    render_inline_meta_desc_push(
                        url, _push_desc,
                        key_prefix=f"qw_meta_{url_hash}",
                        current_desc=page.get("meta_description") or "",
                    )

                _approval_button("Meta", f"{url_hash}_meta")
            else:
                st.markdown(
                    f"<div style='font-size:0.85rem; color:#33dd88;'>"
                    f"Title: {len(page['title'])} chars · "
                    f"Description: {len(page['meta_description'] or '')} chars · "
                    f"No changes needed</div>",
                    unsafe_allow_html=True,
                )

        # ── CARD 2: INTRO TEXT (above product grid) ─────────────────
        intro_key = f"_intro_text_{url_hash}"
        intro_data = st.session_state.get(intro_key)
        intro_words_current = page["audit"].get("intro_word_count", 0)
        _intro_errored = isinstance(intro_data, dict) and bool(intro_data.get("error"))
        _has_new_intro = bool(intro_data and not _intro_errored)
        _intro_existing_ok = (not _has_new_intro) and (not _intro_errored) and (intro_words_current >= 50)

        if _has_new_intro:
            _intro_summary = "● new intro generated · review + push"
            _intro_expand = True  # new content waiting for review
        elif _intro_errored:
            _intro_summary = "⚠ generation failed · click to retry"
            _intro_expand = True
        elif _intro_existing_ok:
            _intro_summary = f"✓ existing intro OK ({intro_words_current} words)"
            _intro_expand = _expand_default
        elif page["page_type"] == "category":
            _intro_summary = f"○ not generated yet ({intro_words_current} words currently)"
            _intro_expand = True
        else:
            _intro_summary = "— not applicable for this page type"
            _intro_expand = _expand_default

        with st.expander(
            f"📄 **Intro text** — {_intro_summary}",
            expanded=_intro_expand,
        ):
            if _has_new_intro:
                st.markdown(
                    "<div style='background:#0d0d15; border:1px solid #5bb4d4; border-radius:6px; padding:0.6rem; margin-bottom:0.5rem;'>"
                    "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.6rem; color:#5bb4d4;'>POSITION</div>"
                    "<div style='font-size:0.8rem; color:#e8e8f0;'>"
                    "This is the <strong>INTRO TEXT</strong> shown <strong>ABOVE</strong> the product grid. "
                    f"Current: {intro_words_current} words. "
                    "<br>In Magento 1.9: typically a CMS block above the products, or first paragraph of Description."
                    "</div></div>",
                    unsafe_allow_html=True,
                )
                new_intro = (
                    intro_data.get("optimized_text")
                    or intro_data.get("rewritten_intro")
                    or intro_data.get("html", "")
                    or intro_data.get("text", "")
                    or intro_data.get("intro", "")
                    or intro_data.get("intro_text", "")
                    or intro_data.get("paragraph", "")
                    or intro_data.get("content", "")
                )
                # Last resort: pick the longest string value in the dict
                if not new_intro and isinstance(intro_data, dict):
                    strs = [(k, v) for k, v in intro_data.items() if isinstance(v, str) and len(v.split()) > 10]
                    if strs:
                        longest = max(strs, key=lambda kv: len(kv[1]))
                        new_intro = longest[1]
                        st.caption(f"Pulled intro from unknown key `{longest[0]}` — please tell the dev so the keys list can be updated.")

                new_intro_wc = len(new_intro.split()) if new_intro else 0

                # Strip HTML for the visible diff so it reads as prose; the
                # raw HTML is still available below in the "Copy raw" expander.
                try:
                    from bs4 import BeautifulSoup as _Bs
                    intro_plain = _Bs(new_intro or "", "html.parser").get_text(separator=" ").strip()
                except Exception:
                    intro_plain = new_intro or ""

                current_intro_text = (
                    page["audit"].get("intro_text")
                    or page["audit"].get("body_text", "")[:600]
                    or ""
                )
                try:
                    current_intro_plain = _Bs(current_intro_text, "html.parser").get_text(separator=" ").strip()
                except Exception:
                    current_intro_plain = current_intro_text

                render_recommendation_diff(
                    "Intro text",
                    current_intro_plain,
                    intro_plain,
                    kind="intro",
                    note="Place above the product grid. Front-load the primary keyword in the first sentence.",
                )

                # Show full raw response when we couldn't extract any content
                if new_intro_wc == 0:
                    st.warning(
                        "Could not find intro text in any expected key "
                        "(optimized_text, rewritten_intro, html, text, intro, intro_text, paragraph, content). "
                        "Raw AI response shown below — copy what you see and tell the dev which key to map."
                    )
                    st.markdown("**Raw AI response (debug):**")
                    st.json(intro_data)
                    if st.button("🔄 Clear cache and regenerate intro", key=f"force_regen_intro_{url_hash}"):
                        st.session_state.pop(intro_key, None)
                        try:
                            import os as _os
                            _path = _os.path.join("/data/ai_cache", f"{intro_key}.json")
                            if _os.path.exists(_path):
                                _os.remove(_path)
                        except Exception:
                            pass
                        st.rerun()

                # ── Inline push to Mshop ──
                from utils.mshop_admin_push_ui import (
                    render_inline_intro_push,
                    render_push_resolution_banner,
                )
                render_push_resolution_banner(url)
                # Surface the extracted intro length so the user can see
                # immediately if the push button is disabled because the
                # extraction failed (rare, key-mismatch bug).
                st.caption(
                    f"Extracted intro length: {len((new_intro or '').strip())} "
                    f"chars · {len((new_intro or '').split())} words"
                )
                render_inline_intro_push(url, new_intro or "", key_prefix=f"qw_intro_{url_hash}")

                _approval_button("Intro", f"{url_hash}_intro")
            elif _intro_existing_ok:
                st.markdown(
                    f"<div style='font-size:0.85rem; color:#33dd88; margin-bottom:0.5rem;'>"
                    f"Existing intro has {intro_words_current} words — sufficient, not regenerated</div>",
                    unsafe_allow_html=True,
                )
                # Even when content is sufficient, expose a retry button so
                # the user can force a regen without needing to clear cache
                # manually. Useful after architecture/prompt changes.
                if page["page_type"] == "category" and st.button(
                    "Force regenerate intro anyway",
                    key=f"force_gen_intro_{url_hash}",
                    help="Existing intro is long enough but you can still "
                         "regenerate to apply current rules.",
                ):
                    st.session_state.pop(intro_key, None)
                    st.rerun()
            elif page["page_type"] == "category":
                # Reaches here when:
                #   - no intro_data at all, OR
                #   - intro_data is errored (credit fail, transient API error)
                # Either way the user needs a way to (re)generate it.
                if _intro_errored:
                    st.error(
                        f"Last attempt: {intro_data.get('error_class', 'Error')} — "
                        f"{(intro_data.get('error') or '')[:200]}"
                    )
                    st.caption("Click below to retry — the error stamp will be replaced if generation succeeds.")
                if st.button(
                    "Retry intro generation" if _intro_errored else "Generate intro text",
                    key=f"gen_intro_{url_hash}",
                    type="primary",
                ):
                    if not has_anthropic_key():
                        st.error(
                            "Anthropic API key is missing. Set it in **1. Setup & Connect** "
                            "or as the `ANTHROPIC_API_KEY` env var on Railway, then retry."
                        )
                        st.stop()
                    with st.spinner("Generating intro text..."):
                        try:
                            missing_kws = []
                            content_audit = page["audit"].get("content_audit") or {}
                            kw_coverage = content_audit.get("keyword_coverage") or {}
                            missing_kws = (kw_coverage.get("missing", []) or [])[:8]
                            from utils.ai_generator import get_client, generate_intro_rewrite
                            client = get_client(get_anthropic_key())
                            site_context = st.session_state.get("site_context", "")
                            language = st.session_state.get("content_language", "Swedish")
                            result = generate_intro_rewrite(
                                client,
                                missing_keywords=missing_kws,
                                existing_intro=page["audit"].get("intro_text", "") or "",
                                page_type=page["page_type"],
                                url=url,
                                site_context=site_context,
                                language=language,
                            )
                            st.session_state[intro_key] = result
                        except Exception as e:
                            import traceback as _tb
                            show_ai_error(
                                "Intro text generation",
                                e,
                                context={
                                    "url": url,
                                    "page_type": page["page_type"],
                                    "missing_keywords": missing_kws,
                                },
                            )
                            st.session_state[intro_key] = {
                                "error": str(e),
                                "error_class": type(e).__name__,
                                "error_status_code": getattr(e, "status_code", None),
                                "error_request_id": getattr(e, "request_id", None),
                                "error_traceback": _tb.format_exc()[-3000:],
                            }
                        from utils.persistence import save_ai_cache
                        save_ai_cache()
                    st.rerun()

        # ── CARD 4: CONTEXT (action steps, articles, links, cannibalization, technical) ──
        with st.expander(
            "🔍 **Context — links · cannibalization · technical · article suggestions**",
            expanded=_expand_default,
        ):
            _render_context_card_body(page, url, url_hash, plan)

        # Final actions
        st.markdown("### Done with this page?")
        if on_skip is not None:
            fcol1, fcol2 = st.columns(2)
            with fcol1:
                if st.button("⏭ Skip (don't mark done)", use_container_width=True, key=f"skip_{url_hash}"):
                    on_skip()
                    st.rerun()
            with fcol2:
                if st.button("✓ Mark done & next page", type="primary", use_container_width=True, key=f"done_{url_hash}"):
                    st.session_state[f"_qw_done_{url_hash}"] = True
                    st.rerun()
        else:
            if st.button("✓ Mark as done (hides from list)", type="primary", use_container_width=True, key=f"done_{url_hash}"):
                st.session_state[f"_qw_done_{url_hash}"] = True
                st.rerun()



def _new_articles_section():
    """Article suggestions from content_roadmap + per-page plans (moved from Action Center)."""
    from utils.url_helpers import url_path as _url_path

    roadmap = st.session_state.get("content_roadmap", {})
    articles = roadmap.get("new_articles", []) if isinstance(roadmap, dict) else []

    plan_articles = []
    for key, val in st.session_state.items():
        if key.startswith("_ai_plan_") and isinstance(val, dict):
            for nc in val.get("new_content_suggestions", []):
                if nc.get("suggested_title"):
                    plan_articles.append(nc)

    all_articles = articles + plan_articles
    if not all_articles:
        st.info("No new article suggestions yet. Generate plans for top pages to get suggestions.")
        return

    audit_results = st.session_state.get("audit_results", [])
    existing_titles = set()
    existing_url_paths = set()
    for r in audit_results:
        t = (r.get("title") or "").lower().strip()
        if t:
            existing_titles.add(t)
        u = r.get("url", "")
        if u:
            existing_url_paths.add(_url_path(normalize_url(u)).lower())

    st.markdown(f"### {len(all_articles)} New Articles to Write")
    for i, art in enumerate(all_articles[:20]):
        title = art.get("suggested_title") or art.get("title", "")
        keywords = art.get("target_keywords", [])
        why = art.get("why", "")

        already_exists = title.lower().strip() in existing_titles
        if not already_exists and keywords:
            for kw in keywords[:3]:
                kw_slug = kw.lower().replace(" ", "-")
                for ep in existing_url_paths:
                    if kw_slug in ep:
                        already_exists = True
                        break
                if already_exists:
                    break

        expander_label = f"{i+1}. {title}" + (" — MAY ALREADY EXIST" if already_exists else "")
        with st.expander(expander_label, expanded=False):
            if already_exists:
                st.warning("A page with a similar title or keyword already exists on the site. Check before creating.")
            if keywords:
                st.markdown(f"**Keywords:** {', '.join(keywords[:8])}")
            if why:
                st.markdown(f"**Why:** {why}")
            link_from = art.get("link_from") or art.get("supporting_page", "")
            if link_from:
                st.markdown(f"**Link from:** `{link_from}`")
            st.button("Generate full article", key=f"art_{i}_{stable_hash(title)}", help="Coming soon")


def _technical_section():
    """Technical SEO issues from crawl analysis (moved from Action Center)."""
    issues = st.session_state.get("sf_crawl_issues", {})
    if not issues:
        st.info("No crawl issues data. Run **Analyze Crawl Issues** in Run Pipeline.")
        return

    counts = {k: len(v) for k, v in issues.items() if v}
    if not counts:
        st.success("No technical issues found")
        return

    st.markdown("### Technical Issues (Magento 1.9)")
    cols = st.columns(4)
    items = list(counts.items())[:4]
    for i, (key, count) in enumerate(items):
        cols[i].metric(key.replace("_", " ").title(), f"{count:,}")

    if len(counts) > 4:
        cols2 = st.columns(4)
        for i, (key, count) in enumerate(list(counts.items())[4:8]):
            cols2[i].metric(key.replace("_", " ").title(), f"{count:,}")

    st.markdown("**Top issues to fix:**")
    priority_order = ["broken_links", "non_indexable", "near_duplicates", "canonical_issues", "orphan_pages", "faceted_urls"]
    # Build a canonical-target lookup from audit_results so non_indexable items can
    # show WHY the page is flagged — the most common cause is "Canonicalised" (SF term
    # for: this URL canonicals to a different URL), not a missing `index,follow`.
    canonical_by_url = {}
    for r in st.session_state.get("audit_results", []) or []:
        u = r.get("url")
        c = r.get("canonical") or r.get("canonical_url")
        if u and c:
            canonical_by_url[normalize_url(u)] = c

    for key in priority_order:
        if issues.get(key):
            with st.expander(f"{key.replace('_', ' ').title()} ({len(issues[key])} items)", expanded=False):
                if key == "non_indexable":
                    st.caption(
                        "**Non-indexable** is reported by Screaming Frog based on its indexability rules. "
                        "A page with `<meta name=\"robots\" content=\"index, follow\">` can still be flagged "
                        "if its canonical tag points to a DIFFERENT URL (SF calls this 'Canonicalised'), "
                        "if robots.txt blocks it, or if the HTTP status is not 200."
                    )
                for item in issues[key][:20]:
                    url_i = item.get("url", "")
                    action_i = item.get("action", "")
                    st.markdown(f"- `{url_i}` — {action_i}")
                    if key == "non_indexable":
                        reason = item.get("reason", "") or ""
                        canonical = canonical_by_url.get(normalize_url(url_i))
                        if canonical and normalize_url(canonical) != normalize_url(url_i):
                            st.markdown(
                                f"  <div style='font-size:0.75rem; color:#ffaa33; margin-left:1rem;'>"
                                f"Canonical points to: <code>{canonical}</code> — "
                                f"Google will show that URL, not this one.</div>",
                                unsafe_allow_html=True,
                            )
                        elif "canonical" in reason.lower():
                            st.markdown(
                                f"  <div style='font-size:0.75rem; color:#ffaa33; margin-left:1rem;'>"
                                f"SF reason: <code>{reason}</code> (canonical mismatch — see the page's "
                                f"<code>&lt;link rel=\"canonical\"&gt;</code> tag).</div>",
                                unsafe_allow_html=True,
                            )


def _render_per_page_tab():
    """The per-page work tab — one page at a time with prev/next nav. Configurable top_n."""
    audit_results = st.session_state["audit_results"]

    # Configurable top_n — default 100 (what Action Center used to show)
    top_n = int(st.session_state.get("_qw_top_n", 100))
    pages = _get_top_pages(audit_results, top_n=top_n)

    # ── Per-page card layout setting ───────────────────────────────
    _setup_col1, _setup_col2 = st.columns([1, 3])
    with _setup_col1:
        _expand_default = st.checkbox(
            "Expand all cards by default",
            value=bool(st.session_state.get("_qw_per_page_default_expanded", False)),
            key="_qw_per_page_default_expanded",
            help="When off (default), each section card is collapsed — click to "
                 "expand. When on, all cards open automatically.",
        )

    # ── Mshop admin API: sync the list of active pages ────────────
    # Lookup is needed before per-page push of intro / meta title /
    # meta description: the update endpoints take an internal id, not
    # a URL, so we cache URL→id once and reuse for every push.
    _active_pages = st.session_state.get("mshop_active_pages") or {}
    _active_count = (
        len(_active_pages.get("lookup", {}))
        if isinstance(_active_pages, dict) and isinstance(_active_pages.get("lookup"), dict)
        else 0
    )
    with st.expander(
        f"🔌 Mshop Admin API — {_active_count} active pages cached"
        if _active_count else
        "🔌 Mshop Admin API — not synced yet (required for intro/meta push)",
        expanded=(_active_count == 0),
    ):
        st.caption(
            "Fetches the list of active categories, CMS pages, and filter "
            "pages from Mshop so per-page push buttons can resolve a URL "
            "to its internal id. Same credentials as bottom-text push. "
            "Re-sync after Mshop adds/removes pages."
        )
        if _active_count:
            counts = (_active_pages.get("counts") or {}) if isinstance(_active_pages, dict) else {}
            fetched_at = _active_pages.get("fetched_at", "?") if isinstance(_active_pages, dict) else "?"
            st.markdown(
                f"<div style='font-size:0.8rem; color:#9b9bb8;'>"
                f"Last sync: <strong>{fetched_at}</strong> · "
                f"Categories: {counts.get('category', 0)} · "
                f"CMS pages: {counts.get('cms', 0)} · "
                f"Filter pages: {counts.get('filterpage', 0)}"
                f"</div>",
                unsafe_allow_html=True,
            )
        if st.button(
            "🔄 Sync active pages from Mshop now",
            key="_qw_admin_sync",
            type="primary" if _active_count == 0 else "secondary",
        ):
            from utils.mshop_admin_api import fetch_active_pages_all
            from utils.persistence import save_key
            with st.spinner("Fetching categories + CMS pages + filter pages from Mshop..."):
                _result = fetch_active_pages_all()
            if _result.get("status") == "error":
                st.error(
                    "Sync failed — " + "; ".join(_result.get("errors", []) or ["unknown error"])
                )
            else:
                st.session_state["mshop_active_pages"] = _result
                try:
                    save_key("mshop_active_pages")
                except Exception:
                    pass
                _c = _result.get("counts", {})
                msg = (
                    f"Synced {_c.get('category', 0)} categories, "
                    f"{_c.get('cms', 0)} CMS pages, "
                    f"{_c.get('filterpage', 0)} filter pages."
                )
                if _result.get("status") == "partial":
                    st.warning(
                        msg + " Some lists failed: "
                        + "; ".join(_result.get("errors", []))
                    )
                else:
                    st.success(msg)
                st.rerun()

    # ── Controls: how many top pages + bulk AI-plan generation ────
    controls_col1, controls_col2, controls_col3 = st.columns([2, 2, 3])
    with controls_col1:
        new_top_n = st.number_input(
            "Top N pages to work on",
            min_value=5, max_value=500, value=top_n, step=10,
            key="_qw_top_n_input",
            help="Upper bound — the actual list may be shorter if you've marked pages done or excluded them via the ideal structure.",
        )
        if new_top_n != top_n:
            st.session_state["_qw_top_n"] = int(new_top_n)
            st.rerun()

    # A page "needs work" if ANY of plan / bottom text / intro is missing
    # OR was stamped with an error (e.g. credit-balance failure, transient
    # API hiccup). Treating error-stamped entries as "complete" was a real
    # bug — bulk would skip them forever, leaving the user staring at
    # error messages with no way to retry without manually clearing cache.
    _eligible_text_types = {"category", "subcategory", "brand", "unknown", ""}
    def _has_valid(_key):
        v = st.session_state.get(_key)
        if not v:
            return False
        if isinstance(v, dict) and v.get("error"):
            return False
        return True
    def _needs_bulk_work(_p):
        _h = stable_hash(_p["url"])
        if not _has_valid(f"_ai_plan_{_h}"):
            return True
        _pt = (_p.get("page_type") or "")
        if _pt in _eligible_text_types:
            if not _has_valid(f"_bottom_text_{_h}"):
                return True
            if not _has_valid(f"_intro_text_{_h}"):
                return True
        return False
    uncached_pages = [p for p in pages if _needs_bulk_work(p)]
    uncached_count = len(uncached_pages)

    with controls_col2:
        bulk_n = st.number_input(
            "Bulk-generate plan + bottom text + intro for top N (incomplete only)",
            min_value=1, max_value=max(1, uncached_count), value=min(10, max(1, uncached_count)),
            key="_qw_bulk_n",
            disabled=(uncached_count == 0),
            help="Runs plan + bottom text + intro for the next N pages where ANY of those 3 is missing. Already-generated artifacts are skipped per page. ~60-90 sec per fresh page.",
        )

    with controls_col3:
        approx_min = int(bulk_n) * 75 // 60
        approx_cost = int(bulk_n) * 0.05
        # Break down what's actually missing so the user can see why a
        # page is in the queue. Split "missing entirely" from "errored"
        # so the user knows when to add API credits vs just hit retry.
        def _missing_or_errored(_p, _prefix, _eligible_only=False):
            _pt = (_p.get("page_type") or "")
            if _eligible_only and _pt not in _eligible_text_types:
                return (False, False)  # not applicable to this page
            _key = f"{_prefix}{stable_hash(_p['url'])}"
            v = st.session_state.get(_key)
            if not v:
                return (True, False)  # missing
            if isinstance(v, dict) and v.get("error"):
                return (False, True)  # errored
            return (False, False)  # valid
        _missing_plan = sum(1 for p in pages if _missing_or_errored(p, "_ai_plan_")[0])
        _errored_plan = sum(1 for p in pages if _missing_or_errored(p, "_ai_plan_")[1])
        _missing_bottom = sum(1 for p in pages if _missing_or_errored(p, "_bottom_text_", True)[0])
        _errored_bottom = sum(1 for p in pages if _missing_or_errored(p, "_bottom_text_", True)[1])
        _missing_intro = sum(1 for p in pages if _missing_or_errored(p, "_intro_text_", True)[0])
        _errored_intro = sum(1 for p in pages if _missing_or_errored(p, "_intro_text_", True)[1])
        total_errored = _errored_plan + _errored_bottom + _errored_intro
        st.caption(
            f"Pages shown: {len(pages)} · Incomplete: {uncached_count} "
            f"(plan: {_missing_plan} missing / {_errored_plan} errored · "
            f"bottom: {_missing_bottom} missing / {_errored_bottom} errored · "
            f"intro: {_missing_intro} missing / {_errored_intro} errored)"
        )
        if total_errored:
            st.caption(
                f":red[⚠ {total_errored} artifact(s) failed last run] — usually a "
                f"credit-balance / API issue. Fix the underlying cause "
                f"(e.g. add Anthropic credits) then click the button below; "
                f"errored entries are automatically retried."
            )
        if uncached_count == 0:
            st.caption("All visible pages have plan + bottom + intro cached.")
        else:
            st.caption(f"≈ {approx_min} min · ≈ ${approx_cost:.2f} API cost")
            if st.button(
                f"⚡ Generate missing plan + bottom + intro for next {int(bulk_n)} pages",
                key="_qw_bulk_gen",
                type="primary",
            ):
                from utils.ai_generator import (
                    get_client,
                    generate_page_content,
                    generate_intro_rewrite,
                )
                from utils.persistence import save_ai_cache
                client = get_client(get_anthropic_key())
                site_context = st.session_state.get("site_context", "")
                language = st.session_state.get("content_language", "Swedish")
                batch = uncached_pages[:int(bulk_n)]
                # Pages that get bottom text + intro: anything that looks
                # like a landing page. Excludes only product detail pages
                # (their text comes from PIM) and blog/faq/info (they have
                # their own template). "unknown" is included because the
                # classifier sometimes fails on edge cases and silently
                # skipping those was the original bug.
                eligible_for_text = {"category", "subcategory", "brand", "unknown", ""}
                progress = st.progress(0.0)
                status_txt = st.empty()
                failed_text = 0
                failed_intro = 0
                skipped_by_type = 0
                def _safe_save():
                    try:
                        save_ai_cache()
                    except Exception:
                        pass

                for i, p in enumerate(batch):
                    url = p["url"]
                    url_hash = stable_hash(url)
                    status_txt.text(f"[{i+1}/{len(batch)}] {url}  (plan)")
                    # _generate_all_fixes already calls save_ai_cache after
                    # the plan, so the plan is persisted before we start
                    # the (slower) bottom-text call.
                    _generate_all_fixes(p)

                    page_type = p.get("page_type", "") or ""
                    text_key = f"_bottom_text_{url_hash}"
                    # Re-attempt error-stamped entries so the user can recover
                    # from credit-balance / transient API failures by simply
                    # clicking bulk again. Without this, a single bad run
                    # poisons the cache and bulk skips those pages forever.
                    def _is_errored(_k):
                        v = st.session_state.get(_k)
                        return isinstance(v, dict) and bool(v.get("error"))
                    if page_type not in eligible_for_text:
                        skipped_by_type += 1
                    elif text_key not in st.session_state or _is_errored(text_key):
                        status_txt.text(f"[{i+1}/{len(batch)}] {url}  (bottom text)")
                        try:
                            st.session_state[text_key] = generate_page_content(url)
                        except Exception as e:
                            failed_text += 1
                            st.session_state[text_key] = {
                                "error": str(e),
                                "error_class": type(e).__name__,
                            }
                        # Persist bottom text immediately so a crash during
                        # the intro call below doesn't lose this page's
                        # ~$0.04 of bottom-text work.
                        _safe_save()

                    intro_key = f"_intro_text_{url_hash}"
                    if page_type in eligible_for_text and (
                        intro_key not in st.session_state or _is_errored(intro_key)
                    ):
                        status_txt.text(f"[{i+1}/{len(batch)}] {url}  (intro)")
                        try:
                            content_audit = p["audit"].get("content_audit") or {}
                            kw_coverage = content_audit.get("keyword_coverage") or {}
                            missing_kws = (kw_coverage.get("missing", []) or [])[:8]
                            if not missing_kws:
                                missing_kws = p["audit"].get("target_keywords", [])[:8]
                            st.session_state[intro_key] = generate_intro_rewrite(
                                client,
                                missing_keywords=missing_kws,
                                existing_intro=p["audit"].get("intro_text", "") or "",
                                page_type=page_type or "category",
                                url=url,
                                site_context=site_context,
                                language=language,
                            )
                        except Exception as e:
                            failed_intro += 1
                            st.session_state[intro_key] = {
                                "error": str(e),
                                "error_class": type(e).__name__,
                            }
                        # Persist intro before moving to the next page.
                        _safe_save()

                    progress.progress((i + 1) / len(batch))

                status_txt.empty()
                parts = [f"Generated {len(batch)} plans"]
                if skipped_by_type:
                    parts.append(
                        f"{skipped_by_type} page(s) skipped for bottom/intro "
                        f"(page_type is product/blog/faq/info)"
                    )
                if failed_text:
                    parts.append(f"bottom text failures: {failed_text}")
                if failed_intro:
                    parts.append(f"intro failures: {failed_intro}")
                msg = " · ".join(parts)
                if failed_text or failed_intro:
                    st.warning(msg + ". Open individual pages to see errors.")
                elif skipped_by_type:
                    st.info(msg + ".")
                else:
                    st.success(
                        f"Generated plan + bottom text + intro for {len(batch)} pages."
                    )
                st.rerun()

    excluded_count = st.session_state.get("_qw_excluded_count", 0)
    if excluded_count > 0:
        st.markdown(
            f"<div style='font-size:0.8rem; color:#9b9bb8; margin-bottom:0.5rem;'>"
            f"{excluded_count} page(s) excluded (scheduled for merge/delete in ideal structure)</div>",
            unsafe_allow_html=True,
        )

    # ── Bulk regenerate cached bottom texts (force-rebuild after arch
    # changes invalidate them — anchors, hub URLs, owned/dnc keywords).
    cached_pages_with_text = [
        p for p in pages
        if f"_bottom_text_{stable_hash(p['url'])}" in st.session_state
    ]
    if cached_pages_with_text:
        with st.expander(
            f"🔄 Re-generate cached bottom texts ({len(cached_pages_with_text)} pages have stale text)",
            expanded=False,
        ):
            st.markdown(
                "<div style='background:#0d0d15; border-left:3px solid #ffaa33; "
                "padding:0.6rem 0.9rem; margin-bottom:0.8rem; border-radius:0 4px 4px 0;'>"
                "<div style='font-size:0.85rem; color:#e8e8f0;'>"
                "Use this when topical architecture has changed (hub URLs, "
                "owned/do-not-compete keywords, anchor diversity). Old cached "
                "texts are <strong>cleared and regenerated</strong> with the "
                "current rules. ~30 sec + ~$0.02 per page."
                "</div></div>",
                unsafe_allow_html=True,
            )
            rg_col1, rg_col2 = st.columns([2, 3])
            with rg_col1:
                regen_n = st.number_input(
                    "How many to regenerate now?",
                    min_value=1,
                    max_value=len(cached_pages_with_text),
                    value=min(10, len(cached_pages_with_text)),
                    step=5,
                    key="_qw_regen_bottom_n",
                    help="Process in chunks. Re-open this expander to do more.",
                )
                approx_min = int(regen_n) * 30 // 60
                approx_cost = int(regen_n) * 0.02
                st.caption(
                    f"≈ {approx_min} min · ≈ ${approx_cost:.2f} API cost"
                )
            with rg_col2:
                st.caption(
                    f"{len(cached_pages_with_text)} pages have a cached bottom "
                    f"text. They were generated under the previous architecture "
                    f"and won't reflect the new TOPICAL BOUNDARY data."
                )
                confirm_regen = st.checkbox(
                    "I understand this will clear and regenerate cached texts",
                    key="_qw_regen_bottom_confirm",
                )
                if st.button(
                    f"🔄 Regenerate next {int(regen_n)} cached pages",
                    key="_qw_regen_bottom_btn",
                    type="primary",
                    disabled=not confirm_regen,
                ):
                    from utils.ai_generator import generate_page_content
                    from utils.persistence import save_ai_cache
                    batch = cached_pages_with_text[:int(regen_n)]
                    progress = st.progress(0.0)
                    status_txt = st.empty()
                    failed = 0
                    for i, p in enumerate(batch):
                        url = p["url"]
                        url_hash = stable_hash(url)
                        text_key = f"_bottom_text_{url_hash}"
                        status_txt.text(f"[{i+1}/{len(batch)}] {url}")
                        # Drop the stale entry first so the new generation
                        # actually runs and persists.
                        if text_key in st.session_state:
                            del st.session_state[text_key]
                        try:
                            result = generate_page_content(url)
                            st.session_state[text_key] = result
                        except Exception as e:
                            failed += 1
                            st.session_state[text_key] = {
                                "error": str(e),
                                "error_class": type(e).__name__,
                            }
                        # Save after every page so a mid-run crash doesn't
                        # wipe progress on a 200-page batch.
                        try:
                            save_ai_cache()
                        except Exception:
                            pass
                        progress.progress((i + 1) / len(batch))
                    status_txt.empty()
                    if failed:
                        st.warning(
                            f"Regenerated {len(batch) - failed} pages, "
                            f"{failed} failed. Check error details on "
                            f"individual pages."
                        )
                    else:
                        st.success(f"Regenerated {len(batch)} pages.")
                    st.rerun()

    st.markdown("---")

    if not pages:
        st.success("All top pages marked as done. Reset done status to start over.")
        if st.button("Reset all done status"):
            keys = [k for k in st.session_state if k.startswith("_qw_done_")]
            for k in keys:
                del st.session_state[k]
            st.rerun()
        return

    if "_qw_page_idx" not in st.session_state:
        st.session_state["_qw_page_idx"] = 0

    # ── FOCUS MODE: cross-view deep link bypasses pagination entirely ──
    # Identity is the URL itself, not a list-position index. This avoids
    # all the Streamlit widget-lifecycle issues that previously caused
    # deep links to land on the wrong page.
    from utils.page_deeplink import current_focus_url, clear_focus, find_page_index
    focus_url = current_focus_url()
    if focus_url:
        from utils.ui_helpers import normalize_url as _qw_nu
        focus_norm = _qw_nu(focus_url)

        # 1. Try to find it in the sorted Quick Wins pages list (top_n)
        focus_page = next(
            (p for p in pages if _qw_nu(p.get("url", "")) == focus_norm),
            None,
        )
        rank_in_list = find_page_index(pages, focus_url)
        from_filtered_list = focus_page is not None

        # 2. If not in the top_n list, build a synthetic page dict
        # straight from audit_results so the user can still work on it.
        if focus_page is None:
            audit_row = next(
                (r for r in audit_results
                 if _qw_nu(r.get("url", "")) == focus_norm),
                None,
            )
            if audit_row is not None:
                # Reuse the same shape _get_top_pages produces so
                # render_page_actions_card sees no difference.
                from utils.page_profile import build_page_profile as _bpp
                _prof = _bpp(audit_row.get("url", ""))
                _flost = sum(g.get("lost_clicks", 0) for g in _prof.get("ctr_gaps", []))
                focus_page = {
                    "url": audit_row.get("url", ""),
                    "page_type": audit_row.get("page_type", "unknown"),
                    "impressions": _prof.get("total_impressions", 0),
                    "lost_clicks": _flost,
                    "meta_score": audit_row.get("meta_score") or 0,
                    "content_score": audit_row.get("content_score") or 0,
                    "title": audit_row.get("title", ""),
                    "meta_description": audit_row.get("meta_description", ""),
                    "h1": audit_row.get("h1", ""),
                    "word_count": audit_row.get("word_count", 0),
                    "intro_text": audit_row.get("intro_text", ""),
                    "bottom_text": audit_row.get("bottom_text", ""),
                    "audit": audit_row,
                }

        if focus_page is None:
            # Truly not in audit_results — wrong URL or page never audited.
            st.error(
                f"Couldn't find this URL in audit_results:\n\n`{focus_url}`\n\n"
                "Re-run **Page Auditor → Re-scrape ALL pages** (or scrape "
                "this single URL) and try again. Falling back to the top "
                "opportunity list below."
            )
            clear_focus()
        else:
            # ── Render focused page banner + card + back button ──
            top_a, top_b = st.columns([5, 2])
            with top_a:
                where = (
                    f"opening directly (this URL is rank "
                    f"<strong>#{rank_in_list + 1}</strong> of {len(pages)} "
                    "in the top opportunities list)"
                    if from_filtered_list else
                    "opening directly (NOT in the top opportunities list — "
                    "may be marked done, scheduled for merge/delete, or "
                    "below the top-N cutoff)"
                )
                st.markdown(
                    f"<div style='background:#0d0d15; border:1px solid #5533ff; "
                    f"border-radius:8px; padding:0.8rem 1rem; margin-bottom:0.5rem;'>"
                    f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; "
                    f"color:#c8b4ff; letter-spacing:0.05em;'>FOCUSED ON URL</div>"
                    f"<div style='font-size:0.95rem; color:#e8e8f0; margin-top:0.2rem;'>"
                    f"{focus_page['url']}</div>"
                    f"<div style='font-size:0.75rem; color:#9b9bb8; margin-top:0.3rem;'>"
                    f"{where}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with top_b:
                if st.button(
                    "← Back to opportunity list",
                    key="qw_clear_focus",
                    use_container_width=True,
                    help="Clear focus and resume paginated browsing of "
                         "all top opportunities.",
                ):
                    clear_focus()
                    st.rerun()

            st.markdown("---")

            def _skip_focused():
                # In focus mode, "skip" just clears focus so the user
                # returns to the paginated list rather than guessing the
                # next URL.
                clear_focus()

            render_page_actions_card(
                focus_page,
                idx=rank_in_list if rank_in_list is not None else None,
                total_pages=len(pages),
                on_skip=_skip_focused,
            )
            return  # Done — focus mode bypasses pagination entirely

    # ── BROWSING MODE: paginated walk through top opportunities ──
    idx = st.session_state["_qw_page_idx"]
    if idx >= len(pages):
        idx = 0
        st.session_state["_qw_page_idx"] = 0

    nav_col1, nav_col2, nav_col3, nav_col4 = st.columns([1, 4, 2, 1])
    with nav_col1:
        if st.button("◀ Previous", disabled=idx == 0, use_container_width=True):
            st.session_state["_qw_page_idx"] = max(0, idx - 1)
            st.rerun()
    with nav_col2:
        st.markdown(
            f"<div style='text-align:center; font-size:0.85rem; color:#9b9bb8; padding-top:0.5rem;'>"
            f"Page <strong>{idx+1}</strong> of <strong>{len(pages)}</strong> top opportunities</div>",
            unsafe_allow_html=True,
        )
    with nav_col3:
        # Direct page jump — survives deploys/restarts so you don't have to click Next 96 times.
        jump = st.number_input(
            "Go to page",
            min_value=1, max_value=len(pages), value=idx + 1, step=1,
            key="_qw_page_jump",
            label_visibility="collapsed",
            help=f"Jump directly to any page (1–{len(pages)})",
        )
        if int(jump) - 1 != idx:
            st.session_state["_qw_page_idx"] = int(jump) - 1
            st.rerun()
    with nav_col4:
        if st.button("Next ▶", disabled=idx >= len(pages) - 1, use_container_width=True):
            st.session_state["_qw_page_idx"] = min(len(pages) - 1, idx + 1)
            st.rerun()

    st.markdown("---")

    page = pages[idx]

    def _skip():
        st.session_state["_qw_page_idx"] = min(len(pages) - 1, idx + 1)

    render_page_actions_card(page, idx=idx, total_pages=len(pages), on_skip=_skip)


def render():
    st.markdown("## ⚡ Quick Wins")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1rem;'>"
        "One page at a time plus full context — new articles, technical issues, and site health, all here.</p>",
        unsafe_allow_html=True,
    )

    if "audit_results" not in st.session_state or not st.session_state["audit_results"]:
        st.warning("No audit data. Go to **⚡ Run Pipeline** and run all steps first.")
        return

    # ── Anthropic key check — surface upfront so AI calls don't all fail later ──
    if not has_anthropic_key():
        st.error(
            "**Anthropic API key is not available.** AI generation (plans, meta, intro, "
            "footer text) will fail until this is fixed.\n\n"
            "Fix one of these ways:\n"
            "1. Go to **1. Setup & Connect** and paste your Anthropic key in the field there, OR\n"
            "2. Set the `ANTHROPIC_API_KEY` env var on Railway (Variables tab) and redeploy."
        )
        if st.button("Open Setup & Connect", type="primary"):
            st.session_state["selected_page"] = "1. Setup & Connect"
            st.rerun()
        st.markdown("---")

    # ── Site validation card (above tabs — applies to all tabs) ─────
    site_validation = st.session_state.get("_site_validation")
    if not site_validation or not isinstance(site_validation, dict):
        st.error(
            "⚠ **Site structure validation NOT yet run.** "
            "You should validate the OVERALL site structure before working on individual pages — "
            "otherwise link recommendations and cleanup may be based on flawed assumptions."
        )
        if st.button("Go to Run Pipeline → Step 9: Site Validation", type="primary"):
            st.session_state["selected_page"] = "⚡ Run Pipeline"
            st.rerun()
        st.warning("You can still continue below, but recommendations will be less accurate.")
        st.markdown("---")
    else:
        health_score = site_validation.get("overall_health_score", 0)
        summary = site_validation.get("summary", "")
        critical_issues = site_validation.get("critical_issues", [])
        priority_actions = site_validation.get("priority_actions", [])

        score_color = "#33dd88" if health_score >= 70 else "#ffaa33" if health_score >= 40 else "#ff4455"

        with st.expander(f"🏗 Site Architecture — Health {health_score}/100", expanded=(health_score < 50)):
            st.markdown(
                f"<div style='background:#0d0d15; border-left:4px solid {score_color}; padding:0.8rem; border-radius:0 6px 6px 0; margin-bottom:1rem;'>"
                f"<div style='font-size:0.85rem; color:#c8b4ff;'>{summary}</div></div>",
                unsafe_allow_html=True,
            )
            if critical_issues:
                st.markdown("**Critical site-level issues:**")
                for issue in critical_issues[:5]:
                    st.markdown(f"- {issue}")
            if priority_actions:
                st.markdown("**Site-wide priority actions — open each to see exactly which pages and what to do:**")
                topic_clusters_state = st.session_state.get("topic_clusters", {}) or {}
                df_structure_for_drill = _get_or_build_df_structure_cached()
                if df_structure_for_drill is None:
                    err = st.session_state.get("_qw_df_structure_error", "")
                    st.caption(
                        f"_Could not build site-structure dataframe for drill-down. "
                        f"Re-run the full pipeline (Step 1-9). {('Error: ' + err) if err else ''}_"
                    )

                for pa_idx, pa in enumerate(priority_actions[:5]):
                    if isinstance(pa, dict):
                        action_text = pa.get("action", "")
                        impact = pa.get("impact", "?").upper()
                        affected = pa.get("pages_affected", 0)
                        label = (
                            f"**[{impact}]** {action_text}  "
                            f"<span style='color:#8a8aaa;'>({affected} pages affected)</span>"
                        )
                    else:
                        action_text = str(pa)
                        impact = "?"
                        label = action_text

                    st.markdown(f"<div style='margin-top:0.7rem;'>{label}</div>", unsafe_allow_html=True)

                    cat = _classify_priority_action(action_text)
                    if cat == "other" or df_structure_for_drill is None:
                        st.caption(
                            "_This is a high-level architectural recommendation — no specific "
                            "pages auto-mapped. Address it via Site Cleanup / Topic Clusters tabs._"
                        )
                        continue

                    toggle_label = {
                        "assign_clusters": "Show the unclustered pages and which cluster each should join",
                        "thin_pages": "Show the thin pages and exactly what to add to each",
                        "expand_clusters": "Show which clusters need spokes and what to write",
                        "informational_gap": "Show which clusters need blog/guide articles",
                    }.get(cat, "Show specific pages and per-page action")

                    # NB: Streamlit forbids expanders nested inside expanders, and
                    # the whole Site Architecture card is itself an expander — so we
                    # use a toggle here instead.
                    show = st.toggle(toggle_label, key=f"_qw_drill_show_{pa_idx}", value=False)
                    if show:
                        _render_priority_action_drilldown(
                            action_text, df_structure_for_drill, topic_clusters_state
                        )
            st.info("These site-wide issues should be addressed BEFORE or ALONGSIDE per-page work. Per-page recommendations below are informed by this context.")

    # ── Tabs: everything from former Action Center now lives here ───
    tab_page, tab_plan, tab_articles, tab_tech = st.tabs([
        "🎯 Per-page work",
        "📋 Site Action Plan",
        "📝 New Articles",
        "⚙ Technical Issues",
    ])

    with tab_page:
        _render_per_page_tab()

    with tab_plan:
        _render_site_action_plan_tab()

    with tab_articles:
        _new_articles_section()

    with tab_tech:
        _technical_section()
