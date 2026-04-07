"""
Site Cleanup — Site-wide actions: pages to delete, merge, redirect, noindex.
Different from Quick Wins which is per-page improvements.
"""

import streamlit as st
from utils.ui_helpers import normalize_url, stable_hash, shorten_url


def _pages_to_merge():
    """From cannibalization data — pages competing for same keywords."""
    cannibal_df = st.session_state.get("cannibalization")
    if cannibal_df is None or cannibal_df.empty:
        return []

    merges = []
    seen_pairs = set()
    for _, row in cannibal_df.iterrows():
        if row.get("severity") not in ("severe", "moderate"):
            continue
        winner = row.get("recommended_winner", "")
        merge_action = row.get("merge_action", "")

        # Skip "different intent" cases — these should NOT merge
        if "DIFFERENT INTENTS" in merge_action or "Don't merge" in merge_action:
            continue
        if "Homepage involved" in merge_action:
            continue

        pages_detail = row.get("pages_detail", [])
        if not isinstance(pages_detail, list) or len(pages_detail) < 2:
            continue

        losers = [p["page"] for p in pages_detail if normalize_url(p.get("page", "")) != normalize_url(winner)]
        for loser in losers:
            pair = tuple(sorted([normalize_url(winner), normalize_url(loser)]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            merges.append({
                "keep": winner,
                "redirect": loser,
                "query": row["query"],
                "lost_clicks": row["lost_clicks_estimate"],
                "severity": row["severity"],
            })
    return merges[:30]


def _pages_to_redirect():
    """Broken pages (4xx) that have backlinks — should be redirected to similar page."""
    issues = st.session_state.get("sf_crawl_issues", {})
    broken = issues.get("broken_links", [])
    page_authority = st.session_state.get("page_authority")

    redirects = []
    for b in broken:
        url = b.get("url", "")
        rd = 0
        if page_authority is not None and not page_authority.empty:
            match = page_authority[page_authority["page"].apply(normalize_url) == normalize_url(url)]
            if not match.empty:
                rd = int(match.iloc[0].get("referring_domains", 0))
        redirects.append({
            "url": url,
            "status": b.get("status_code", 404),
            "referring_domains": rd,
            "action": "Redirect to closest matching page (preserve any backlinks)" if rd > 0 else "Delete or redirect",
        })
    redirects.sort(key=lambda x: -x["referring_domains"])
    return redirects


def _pages_to_noindex():
    """Pages that should be noindexed: faceted URLs, thin pages, near-duplicates."""
    issues = st.session_state.get("sf_crawl_issues", {})

    noindex_candidates = []

    # Faceted URLs (Magento parameters)
    faceted = issues.get("faceted_urls", [])
    for f in faceted[:50]:
        noindex_candidates.append({
            "url": f.get("url", ""),
            "reason": "Faceted/parameter URL — wastes crawl budget",
            "type": "faceted",
        })

    # Thin pages
    thin = issues.get("thin_pages", [])
    for t in thin[:30]:
        noindex_candidates.append({
            "url": t.get("url", ""),
            "reason": f"Thin content ({t.get('word_count', 0)} words)",
            "type": "thin",
        })

    # Near-duplicates (only the duplicate, not the original)
    near_dupes = issues.get("near_duplicates", [])
    for d in near_dupes[:30]:
        noindex_candidates.append({
            "url": d.get("url", ""),
            "reason": f"Near-duplicate of {d.get('closest_match', '')}",
            "type": "duplicate",
        })

    return noindex_candidates


def _pages_to_delete():
    """Pages with no traffic, no backlinks, thin content."""
    audit_results = st.session_state.get("audit_results", [])
    page_authority = st.session_state.get("page_authority")

    candidates = []
    for r in audit_results:
        url = r.get("url", "")
        impressions = r.get("impressions", 0)
        clicks = r.get("clicks", 0)
        word_count = r.get("word_count", 0)

        # Get backlinks
        rd = 0
        if page_authority is not None and not page_authority.empty:
            match = page_authority[page_authority["page"].apply(normalize_url) == normalize_url(url)]
            if not match.empty:
                rd = int(match.iloc[0].get("referring_domains", 0))

        # Candidate for deletion: no traffic, no backlinks, thin content
        if impressions < 10 and clicks == 0 and rd == 0 and word_count < 200:
            candidates.append({
                "url": url,
                "impressions": impressions,
                "word_count": word_count,
                "page_type": r.get("page_type", "unknown"),
            })
    return candidates[:50]


def _blogs_to_review():
    """Blog posts with REWRITE quality verdict or zero traffic."""
    audit_results = st.session_state.get("audit_results", [])
    blogs = []
    for r in audit_results:
        if r.get("page_type") not in ("blog", "faq"):
            continue
        url = r.get("url", "")
        impressions = r.get("impressions", 0)
        url_hash = stable_hash(url)
        quality = st.session_state.get(f"_quality_{url_hash}")
        if quality:
            verdict = quality.get("verdict", "")
            score = quality.get("score", 0)
            if verdict == "REWRITE" or (verdict == "IMPROVE" and score <= 4):
                blogs.append({
                    "url": url,
                    "verdict": verdict,
                    "score": score,
                    "summary": quality.get("summary", "")[:200],
                    "impressions": impressions,
                })
        elif impressions == 0:
            blogs.append({
                "url": url,
                "verdict": "ZERO TRAFFIC",
                "score": 0,
                "summary": "Blog has 0 impressions — consider deleting or improving",
                "impressions": 0,
            })
    return blogs[:30]


def render():
    st.markdown("## 🧹 Site Cleanup")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1rem;'>"
        "Site-wide cleanup actions: pages to delete, merge, redirect, noindex. "
        "These are decisions that affect site structure, not single-page improvements.</p>",
        unsafe_allow_html=True,
    )

    if "audit_results" not in st.session_state:
        st.warning("Run **⚡ Run Pipeline** first to get analysis data.")
        return

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔀 Merge (cannibalization)",
        "↗ Redirect (broken)",
        "🚫 Noindex (waste)",
        "🗑 Delete (no value)",
        "📝 Blogs to review",
    ])

    # ── TAB 1: MERGE ─────────────────────────────────────────
    with tab1:
        merges = _pages_to_merge()
        st.markdown(f"### {len(merges)} page pairs to merge")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "These pages compete for the same keywords AND have similar intent. "
            "Different-intent pairs are filtered out automatically.</p>",
            unsafe_allow_html=True,
        )
        if not merges:
            st.success("No same-intent cannibalization detected")
        for m in merges[:20]:
            with st.expander(f"{shorten_url(m['keep'])}  ←  {shorten_url(m['redirect'])}  |  '{m['query']}'  |  {m['lost_clicks']:,} lost clicks"):
                st.markdown(f"**Keep:** `{m['keep']}`")
                st.markdown(f"**Redirect FROM:** `{m['redirect']}`")
                st.markdown(f"**Severity:** {m['severity'].upper()}")
                st.markdown(f"**Steps:**")
                st.markdown(f"1. Copy unique content from `{shorten_url(m['redirect'])}` to `{shorten_url(m['keep'])}`")
                st.markdown(f"2. In Magento: set up 301 redirect from old URL to new")
                st.markdown(f"3. Update internal links pointing to old URL")
                st.markdown(f"4. Submit changes to Google Search Console")

    # ── TAB 2: REDIRECT ──────────────────────────────────────
    with tab2:
        redirects = _pages_to_redirect()
        st.markdown(f"### {len(redirects)} broken pages to redirect")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "These pages return 4xx errors. Redirect to closest matching page to preserve any link equity.</p>",
            unsafe_allow_html=True,
        )
        if not redirects:
            st.success("No broken pages detected")
        for r in redirects[:30]:
            priority = "🔴 HIGH" if r["referring_domains"] > 0 else "⚪ LOW"
            st.markdown(f"- {priority} `{r['url']}` ({r['status']}) · {r['referring_domains']} backlinks")
            st.markdown(f"  <div style='color:#9b9bb8; font-size:0.8rem; margin-left:1rem;'>{r['action']}</div>", unsafe_allow_html=True)

    # ── TAB 3: NOINDEX ───────────────────────────────────────
    with tab3:
        noindex = _pages_to_noindex()
        st.markdown(f"### {len(noindex)} pages to noindex / block in robots.txt")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "These pages waste crawl budget without SEO value. Add noindex meta or block in robots.txt.</p>",
            unsafe_allow_html=True,
        )
        if not noindex:
            st.success("No noindex candidates")

        # Group by type
        by_type = {}
        for n in noindex:
            by_type.setdefault(n["type"], []).append(n)

        for type_key, items in by_type.items():
            with st.expander(f"{type_key.upper()} ({len(items)} pages)", expanded=False):
                if type_key == "faceted":
                    st.info("Magento 1.9 faceted URLs. Block via robots.txt:")
                    st.code("Disallow: /*?dir=\nDisallow: /*?limit=\nDisallow: /*?mode=\nDisallow: /*?order=\nDisallow: /*?p=\nDisallow: /*?SID=", language="text")
                for item in items[:30]:
                    st.markdown(f"- `{item['url']}` — {item['reason']}")

    # ── TAB 4: DELETE ────────────────────────────────────────
    with tab4:
        deletes = _pages_to_delete()
        st.markdown(f"### {len(deletes)} pages to consider deleting")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "Pages with: 0 clicks, <10 impressions, 0 backlinks, <200 words. "
            "These provide no value and clutter the site.</p>",
            unsafe_allow_html=True,
        )
        if not deletes:
            st.success("No clearly deletable pages")
        for d in deletes[:30]:
            st.markdown(f"- `{d['url']}` ({d['page_type']}) · {d['word_count']} words · {d['impressions']} impressions")

    # ── TAB 5: BLOGS TO REVIEW ───────────────────────────────
    with tab5:
        blogs = _blogs_to_review()
        st.markdown(f"### {len(blogs)} blog/guide pages needing review")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "Blog posts with REWRITE verdict from AI quality check, or zero traffic. "
            "Either rewrite, delete, or repurpose.</p>",
            unsafe_allow_html=True,
        )
        if not blogs:
            st.success("No blogs flagged for review")
        for b in blogs[:30]:
            v_color = {"REWRITE": "#ff4455", "IMPROVE": "#ffaa33", "ZERO TRAFFIC": "#6b6b8a"}.get(b["verdict"], "#6b6b8a")
            with st.expander(f"[{b['verdict']}] {shorten_url(b['url'])} · {b['impressions']} impressions"):
                st.markdown(f"**Score:** {b['score']}/10")
                st.markdown(f"**Issue:** {b['summary']}")
                st.markdown(f"**Options:**")
                st.markdown("1. **Rewrite** — use Quick Wins to generate new content")
                st.markdown("2. **Delete** — if topic is irrelevant or covered elsewhere")
                st.markdown("3. **Merge** — combine with another article on same topic")
                st.markdown("4. **Redirect** — if better content exists, 301 to that page")
