"""
Run Pipeline — One-page control center for running all SEO analysis steps.
Each step has a Run button and shows status. "Run All" runs everything sequentially.
"""

import streamlit as st
from utils.persistence import save_key
from utils.ui_helpers import stable_hash
from config import get_anthropic_key, has_anthropic_key


def _data_age_str(state_key):
    """Return age suffix like ' · 3d old' if file exists on disk, else ''."""
    try:
        import os, time
        from utils.persistence import _file_path, PERSIST_KEYS, AI_CACHE_DIR
        if state_key in PERSIST_KEYS:
            path = _file_path(state_key, PERSIST_KEYS[state_key])
        else:
            path = os.path.join(AI_CACHE_DIR, f"{state_key}.json")
        if not os.path.exists(path):
            return "", False
        age_sec = time.time() - os.path.getmtime(path)
        age_days = age_sec / 86400
        stale = age_days > 7
        if age_days < 1:
            label = f" · {int(age_sec/3600)}h old"
        else:
            label = f" · {int(age_days)}d old"
        return label, stale
    except Exception:
        return "", False


def _step_status(state_key):
    """Returns status icon + label with smart count display."""
    if state_key in st.session_state and st.session_state[state_key] is not None:
        data = st.session_state[state_key]
        try:
            # DataFrames need .empty check, not just len()
            import pandas as pd
            if isinstance(data, pd.DataFrame):
                if data.empty:
                    return "✗", "Not run", "#6b6b8a"
                labels = {
                    "gsc_data": "queries",
                    "ctr_gaps": "gaps",
                    "cannibalization": "conflicts",
                    "page_authority": "pages",
                }
                label = labels.get(state_key, "rows")
                return "✓", f"Done ({len(data):,} {label})", "#33dd88"
            # Special handling for topic_clusters dict
            if state_key == "topic_clusters" and isinstance(data, dict):
                clusters = data.get("clusters", [])
                if not clusters:
                    return "✗", "Not run", "#6b6b8a"
                return "✓", f"Done ({len(clusters):,} clusters)", "#33dd88"
            # Special handling for crawl issues dict
            if state_key == "sf_crawl_issues" and isinstance(data, dict):
                total = sum(len(v) for v in data.values() if hasattr(v, "__len__"))
                if total == 0:
                    return "✗", "Not run", "#6b6b8a"
                return "✓", f"Done ({total:,} issues)", "#33dd88"
            # Lists
            if isinstance(data, list):
                if not data:
                    return "✗", "Not run", "#6b6b8a"
                return "✓", f"Done ({len(data):,} items)", "#33dd88"
            # Other dicts
            if isinstance(data, dict) and data:
                return "✓", "Done", "#33dd88"
        except Exception:
            pass
        return "✓", "Done", "#33dd88"
    return "✗", "Not run", "#6b6b8a"


def _run_step_card(num, title, description, state_key, run_fn, button_key):
    """Render one step card with status + Run button."""
    icon, status_label, color = _step_status(state_key)
    age_str, stale = _data_age_str(state_key)
    if age_str:
        status_label = f"{status_label}{age_str}"
        if stale and color == "#33dd88":
            color = "#ffaa33"  # orange = data older than 7 days
            status_label += " ⚠ stale"

    col1, col2, col3 = st.columns([1, 6, 2])
    with col1:
        st.markdown(
            f"<div style='font-size:1.5rem; color:{color}; text-align:center; padding-top:0.5rem;'>{icon}</div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"<div style='font-weight:600; color:#e8e8f0;'>{num}. {title}</div>"
            f"<div style='font-size:0.8rem; color:#9b9bb8;'>{description}</div>"
            f"<div style='font-size:0.7rem; color:{color}; margin-top:0.2rem;'>{status_label}</div>",
            unsafe_allow_html=True,
        )
    with col3:
        if st.button("Run", key=button_key, use_container_width=True):
            try:
                with st.spinner(f"Running {title}..."):
                    run_fn()
                st.success(f"{title} done")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
                import traceback
                st.code(traceback.format_exc())

    st.markdown("<hr style='margin:0.5rem 0; border:none; border-top:1px solid #1e1e2e;'>", unsafe_allow_html=True)


# ── Run functions for each step ─────────────────────────────────

def _run_fetch_gsc():
    from utils.gsc_client import fetch_gsc_data, build_gsc_service, list_properties
    creds = st.session_state.get("gsc_credentials")
    # Prefer the disk-saved gsc_site (verified by user via Setup picker) over
    # the env-var gsc_site_url. Env var is only fallback for first-time setup.
    # Without this, every deploy = session reset = env var overrides the
    # working value, causing 403 if env var format differs from GSC's stored property.
    site = st.session_state.get("gsc_site") or st.session_state.get("gsc_site_url")
    if not creds or not site:
        raise ValueError("GSC credentials or site URL missing — go to 1. Setup & Connect first")

    # Always rebuild service to avoid stale cached client
    service = build_gsc_service(creds)
    st.session_state["gsc_service"] = service

    try:
        df = fetch_gsc_data(service, site)
    except Exception as e:
        msg = str(e)
        if "403" in msg or "sufficient permission" in msg.lower() or "forbidden" in msg.lower():
            sa_email = creds.get("client_email", "(unknown)") if isinstance(creds, dict) else "(unknown)"
            # Try to list visible properties to help diagnose
            visible = []
            try:
                visible = list_properties(service)
            except Exception:
                pass
            visible_str = "\n".join(f"  - {v}" for v in visible) if visible else "  (none — service account has no GSC access at all)"
            raise RuntimeError(
                f"GSC 403 — service account does not have access to '{site}'.\n\n"
                f"Service account email: {sa_email}\n\n"
                f"FIX:\n"
                f"1. Go to https://search.google.com/search-console\n"
                f"2. Select property '{site}'\n"
                f"3. Settings → Users and permissions → Add user\n"
                f"4. Paste: {sa_email}\n"
                f"5. Role: Full or Restricted\n"
                f"6. Save and re-run this step\n\n"
                f"Properties this service account CAN see right now:\n{visible_str}"
            ) from e
        raise

    st.session_state["gsc_data"] = df
    st.session_state["gsc_site"] = site
    save_key("gsc_data")
    save_key("gsc_site")


def _run_build_authority():
    from utils.ahrefs_import import build_page_authority
    bbl = st.session_state.get("ahrefs_best_by_links")
    bl = st.session_state.get("ahrefs_backlinks")
    if bbl is None or bbl.empty:
        raise ValueError("Ahrefs Best by Links not loaded — check 2. Upload Ahrefs")
    authority = build_page_authority(best_by_links_df=bbl, backlinks_df=bl)
    st.session_state["page_authority"] = authority
    save_key("page_authority")


def _run_crawl_analysis():
    import pandas as pd
    from utils.screaming_frog_import import analyze_crawl_data
    sf_pages = st.session_state.get("sf_pages")
    sf_inlinks = st.session_state.get("sf_inlinks")
    if sf_pages is None or sf_pages.empty:
        raise ValueError("Screaming Frog pages not loaded")
    site_domain = ""
    if "gsc_site" in st.session_state:
        site_domain = st.session_state["gsc_site"].replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
    issues = analyze_crawl_data(
        sf_pages,
        sf_inlinks if sf_inlinks is not None else pd.DataFrame(),
        site_domain,
        gsc_data=st.session_state.get("gsc_data"),
        page_authority=st.session_state.get("page_authority"),
        sf_all_pages=sf_pages,
    )
    st.session_state["sf_crawl_issues"] = issues
    save_key("sf_crawl_issues")


def _run_ctr_analysis():
    from utils.gsc_client import identify_ctr_gaps
    df = st.session_state.get("gsc_data")
    if df is None or df.empty:
        raise ValueError("GSC data not loaded")
    gaps = identify_ctr_gaps(df, gap_threshold=-5)
    st.session_state["ctr_gaps"] = gaps
    save_key("ctr_gaps")


def _run_cannibalization():
    from utils.cannibalization import detect_cannibalization, get_page_cannibalization_summary, get_cannibalization_clusters
    df = st.session_state.get("gsc_data")
    if df is None or df.empty:
        raise ValueError("GSC data not loaded")
    cannibal_df = detect_cannibalization(df, min_impressions=10)
    st.session_state["cannibalization"] = cannibal_df
    st.session_state["cannibal_page_summary"] = get_page_cannibalization_summary(cannibal_df)
    st.session_state["cannibal_clusters"] = get_cannibalization_clusters(cannibal_df)
    save_key("cannibalization")


def _run_topic_clusters():
    import pandas as pd
    from utils.ai_generator import get_client, ai_generate_clusters
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    df = st.session_state.get("gsc_data")
    if df is None or df.empty:
        raise ValueError("GSC data not loaded")
    client = get_client(get_anthropic_key())
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")

    # Prepare keyword data
    kw_summary = df.groupby("query").agg(
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        position=("position", "mean"),
    ).sort_values("impressions", ascending=False).head(250).reset_index()
    keywords_data = []
    for _, row in kw_summary.iterrows():
        pages = df[df["query"] == row["query"]]["page"].unique().tolist()[:3]
        keywords_data.append({
            "keyword": row["query"],
            "impressions": int(row["impressions"]),
            "clicks": int(row["clicks"]),
            "position": round(row["position"], 1),
            "pages": pages,
        })

    result = ai_generate_clusters(client, keywords_data, site_context=site_context, language=language)

    # Build topic_clusters structure compatible with rest of system
    from utils.topic_clusters import build_topic_clusters, normalize_cluster_pages
    fallback = build_topic_clusters(df, min_cluster_size=2)
    if result and result.get("clusters"):
        # Use AI clusters but keep page_topics from algorithmic for completeness
        ai_clusters = result["clusters"]
        # Enrich with page data from GSC. Compute query_count + clicks per
        # (cluster, page) so the primary-cluster dedup downstream has real
        # weights to compare on (was hardcoded 0 before, which broke the
        # tiebreak — every page got assigned to whichever cluster appeared
        # FIRST instead of where it had the most queries).
        for c in ai_clusters:
            cluster_queries = c.get("queries", [])
            cluster_df = df[df["query"].isin(cluster_queries)]
            page_agg = cluster_df.groupby("page").agg(
                query_count=("query", "nunique"),
                total_clicks=("clicks", "sum"),
                total_impressions=("impressions", "sum"),
                avg_position=("position", "mean"),
            ).reset_index().sort_values("total_clicks", ascending=False)
            c["pages"] = [
                {
                    "page": r["page"],
                    "query_count": int(r["query_count"]),
                    "total_clicks": int(r["total_clicks"]),
                    "total_impressions": int(r["total_impressions"]),
                    "avg_position": float(r["avg_position"]) if pd.notna(r["avg_position"]) else 0.0,
                }
                for _, r in page_agg.head(20).iterrows()
            ]
            c["page_count"] = len(c["pages"])
        # Apply both architecture rules (drop homepage, primary-cluster dedup).
        # The algorithmic build_topic_clusters already calls this, but the
        # AI path bypasses build_topic_clusters' enrichment loop and
        # therefore needs the explicit call.
        normalize_cluster_pages(ai_clusters)
        fallback["clusters"] = ai_clusters
        fallback["summary"] = result.get("summary", "")

    st.session_state["topic_clusters"] = fallback
    save_key("topic_clusters")

    # Also generate content_gaps and content_roadmap
    from utils.topic_clusters import identify_content_gaps, generate_content_roadmap
    auth = st.session_state.get("page_authority")
    try:
        gaps = identify_content_gaps(fallback.get("clusters", []), auth)
        st.session_state["content_gaps"] = gaps
        save_key("content_gaps")
    except Exception as e:
        print(f"[pipeline] content_gaps failed: {e}")

    try:
        roadmap = generate_content_roadmap(
            fallback.get("clusters", []),
            df,
            auth,
            language=language,
        )
        st.session_state["content_roadmap"] = roadmap
        save_key("content_roadmap")
    except Exception as e:
        print(f"[pipeline] content_roadmap failed: {e}")


def _run_bulk_audit():
    """
    Run bulk audit inline. Uses the same scrape function as Page Auditor.
    Saves every 25 pages so crash recovery loses at most ~25 seconds.
    """
    from utils.page_scraper import scrape_page
    from utils.category_analyzer import classify_page_type, deep_scrape_category
    from utils.ui_helpers import normalize_url as _norm
    from utils.persistence import _volume_available, _file_path
    import os, json

    gsc = st.session_state.get("gsc_data")
    if gsc is None or not hasattr(gsc, "page"):
        raise ValueError("Run Step 1 (Fetch GSC) first")

    all_pages = gsc["page"].unique().tolist()
    existing = st.session_state.get("audit_results", []) or []
    existing_urls = set(_norm(r.get("url", "")) for r in existing)
    to_scrape = [p for p in all_pages if _norm(p) not in existing_urls]
    if not to_scrape:
        return

    new_results = []
    for i, url in enumerate(to_scrape):
        try:
            quick = classify_page_type(url)
            if quick.get("page_type") == "category":
                page_data = deep_scrape_category(url, timeout=30)
            else:
                page_data = scrape_page(url, timeout=30)
            page_data["url"] = url
            new_results.append(page_data)
        except Exception as e:
            new_results.append({"url": url, "success": False, "error": str(e)})

        # Save every 25 pages to disk
        if (i + 1) % 25 == 0 and _volume_available():
            try:
                path = _file_path("audit_results", "json")
                on_disk = []
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        on_disk = json.load(f)
                # CRITICAL: fresh scrapes must OVERWRITE existing disk entries,
                # not skip them. Previous logic appended-only and silently
                # discarded fresh re-scrapes of already-audited URLs.
                fresh_urls = set(_norm(r.get("url", "")) for r in new_results)
                kept = [r for r in on_disk if _norm(r.get("url", "")) not in fresh_urls]
                merged = kept + new_results
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(merged, f, ensure_ascii=False, indent=1, default=str)
                print(f"[bulk_audit] checkpoint at {i+1}: {len(merged)} total ({len(kept)} kept + {len(new_results)} fresh)")
            except Exception as e:
                print(f"[bulk_audit] checkpoint save failed at {i+1}: {e}")

    # Final merge into session_state + save
    merged = list(existing) + new_results
    st.session_state["audit_results"] = merged
    try:
        save_key("audit_results")
    except Exception as e:
        print(f"[bulk_audit] final save failed: {e}")


# Quality-check hashing, batching and "until done" logic live in
# utils/quality_check_runner.py — single source of truth shared with the
# Page Auditor view. Do NOT re-implement any of it here; import as needed.


def _run_ideal_structure():
    """Generate AI ideal site structure: clusters, merges, deletes, creates."""
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    if "_site_validation" not in st.session_state:
        raise ValueError("Run site validation first (step 9)")
    if "topic_clusters" not in st.session_state:
        raise ValueError("Run topic clusters first")

    import json
    from utils.ai_generator import get_client, _parse_ai_json

    client = get_client(get_anthropic_key())
    site_ctx = st.session_state.get("site_context", "")
    site_issues = st.session_state.get("_site_validation", {})
    topic_clusters = st.session_state.get("topic_clusters", {})
    gsc_data = st.session_state.get("gsc_data")
    audit_results = st.session_state.get("audit_results", [])

    # Prepare keyword data
    kw_lines = []
    if gsc_data is not None and hasattr(gsc_data, "groupby"):
        kw_summary = gsc_data.groupby("query").agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
        ).sort_values("impressions", ascending=False).head(80)
        for kw, row in kw_summary.iterrows():
            kw_lines.append(f"{kw}: {int(row['impressions'])} impr, {int(row['clicks'])} cl")
    kw_text = chr(10).join(kw_lines)

    current_clusters_text = chr(10).join(
        f"- {c.get('topic', '')}: {c.get('query_count', 0)} queries, {c.get('total_impressions', 0)} impr"
        for c in topic_clusters.get("clusters", [])[:20]
    )
    issues_text = chr(10).join(site_issues.get("critical_issues", [])[:5])

    # Build REAL URL list from audit (the ONLY URLs the AI is allowed to reference)
    from utils.ui_helpers import normalize_url as _nu
    real_urls = sorted({_nu(r.get("url", "")) for r in audit_results if r.get("url")})
    # Strip origin for brevity (keep only paths)
    site_origin = (st.session_state.get("gsc_site") or "").rstrip("/")
    real_paths = []
    for u in real_urls:
        p = u
        if site_origin and p.startswith(site_origin):
            p = p[len(site_origin):] or "/"
        real_paths.append(p)
    # Pre-filter by top categories/blogs to keep prompt size manageable (top 300)
    url_list_for_prompt = chr(10).join(real_paths[:300])

    anti_hallucination = """
CRITICAL RULE — ZERO HALLUCINATION ON URLs:
Every URL in your output (hub, spokes, from, to, url, ideal_page) MUST be
copied EXACTLY from the REAL URL list provided below. Do NOT invent URLs
like '/old-product-123' or '/vibrator-tips'. Do NOT add '-2024' suffixes.
If a good URL doesn't exist, leave that action out rather than inventing one.
For 'create' actions you may propose NEW paths BUT mark type='new' and make
the path realistic for the site's URL structure (observe patterns in the list).
"""

    # Call 1: Cluster design
    msg1 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        temperature=0,
        messages=[{"role": "user", "content": f"""Design 15-25 topic clusters for this e-commerce site.
Site: {site_ctx}
Problems: {issues_text}
Top keywords:
{kw_text}
Current clusters: {current_clusters_text}

{anti_hallucination}

REAL URLs that exist on this site (USE ONLY THESE for hub/spokes):
{url_list_for_prompt}

For each cluster: name, intent (commercial/informational), hub URL (from list),
hub keyword, 2-4 spoke URLs (from list). Keep names short (<40 chars).

Output ONLY valid JSON, no markdown, no commentary:
{{"clusters":[{{"name":"...","intent":"...","hub":"/url","hub_kw":"...","spokes":["/url1","/url2"]}}]}}"""}],
    )
    try:
        clusters_result = _parse_ai_json(msg1)
    except Exception as e:
        # Provide actionable error if JSON truncated
        raw = msg1.content[0].text if msg1.content else ""
        stop_reason = getattr(msg1, 'stop_reason', 'unknown')
        raise ValueError(
            f"Cluster design call failed to return valid JSON. "
            f"Stop reason: {stop_reason}. "
            f"Response length: {len(raw)} chars. "
            f"{'TRUNCATED — increase max_tokens or reduce cluster count.' if stop_reason == 'max_tokens' else ''} "
            f"First 300 chars: {raw[:300]}"
        ) from e

    # Call 2: Merge/delete/create
    cluster_names = [c.get("name", "") for c in clusters_result.get("clusters", [])]
    msg2 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        temperature=0,
        messages=[{"role": "user", "content": f"""Given these topic clusters for {site_ctx}:
{chr(10).join(f'- {n}' for n in cluster_names)}
The site has {len(audit_results)} pages. Problems: {issues_text}

{anti_hallucination}

REAL URLs that exist (USE ONLY THESE for merge/delete — creates may be new):
{url_list_for_prompt}

What pages should be:
1. MERGED (multiple pages competing for same keyword) — ALL URLs from real list
2. DELETED (no SEO value) — URL from real list
3. CREATED (missing content) — may be new path, mark type accordingly

Keep "why" short (<60 chars). Output ONLY valid JSON, no commentary:
{{"merge":[{{"from":["/url1","/url2"],"to":"/url","why":"reason"}}],"delete":[{{"url":"/url","why":"reason"}}],"create":[{{"url":"/url","type":"blog","kw":"keyword","why":"reason"}}]}}"""}],
    )
    try:
        changes_result = _parse_ai_json(msg2)
    except Exception as e:
        raw = msg2.content[0].text if msg2.content else ""
        stop_reason = getattr(msg2, 'stop_reason', 'unknown')
        raise ValueError(
            f"Merge/delete/create call failed to return valid JSON. "
            f"Stop reason: {stop_reason}. Length: {len(raw)} chars. "
            f"{'TRUNCATED — bump max_tokens.' if stop_reason == 'max_tokens' else ''} "
            f"First 300 chars: {raw[:300]}"
        ) from e

    # Call 3: Summary
    msg3 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        temperature=0,
        messages=[{"role": "user", "content": f"""Site: {site_ctx}
Current score: {site_issues.get('overall_health_score', '?')}/100
Proposed: {len(clusters_result.get('clusters', []))} clusters, {len(changes_result.get('merge', []))} merges, {len(changes_result.get('delete', []))} deletes, {len(changes_result.get('create', []))} new pages.
Top 10 keywords and where they should live:
{chr(10).join(kw_lines[:10])}

Output ONLY valid JSON, no commentary:
{{"keyword_assignments":[{{"keyword":"kw","ideal_page":"/url","action":"keep|move|create"}}],"estimated_new_score":0,"summary":"3 sentences about ideal vs current"}}"""}],
    )
    try:
        summary_result = _parse_ai_json(msg3)
    except Exception as e:
        raw = msg3.content[0].text if msg3.content else ""
        stop_reason = getattr(msg3, 'stop_reason', 'unknown')
        # Non-fatal — fill defaults so the other 2 results aren't lost
        print(f"[ideal_structure] Call 3 summary failed ({stop_reason}): {e}")
        summary_result = {"keyword_assignments": [], "estimated_new_score": 0,
                          "summary": f"(Summary call failed: {stop_reason})"}

    # ── Post-validation: strip hallucinated URLs ─────────────────
    real_path_set = set(real_paths)

    def _is_real(url: str) -> bool:
        if not url:
            return False
        u = str(url).strip()
        # Strip origin if full URL
        if site_origin and u.startswith(site_origin):
            u = u[len(site_origin):] or "/"
        return u in real_path_set

    hallucinated = {"clusters_hub": 0, "clusters_spokes": 0,
                    "merge_from": 0, "merge_to": 0, "delete": 0}

    clean_clusters = []
    for c in clusters_result.get("clusters", []):
        if not isinstance(c, dict):
            continue
        hub = c.get("hub", "")
        if hub and not _is_real(hub):
            hallucinated["clusters_hub"] += 1
            continue  # skip cluster with fake hub
        clean_spokes = []
        for s in c.get("spokes", []) or []:
            if _is_real(s):
                clean_spokes.append(s)
            else:
                hallucinated["clusters_spokes"] += 1
        c["spokes"] = clean_spokes
        clean_clusters.append(c)

    clean_merges = []
    for m in changes_result.get("merge", []):
        if not isinstance(m, dict):
            continue
        to_url = m.get("to", "")
        from_urls = m.get("from", []) or []
        if not _is_real(to_url):
            hallucinated["merge_to"] += 1
            continue
        real_from = [u for u in from_urls if _is_real(u)]
        if not real_from:
            hallucinated["merge_from"] += len(from_urls)
            continue
        if len(real_from) != len(from_urls):
            hallucinated["merge_from"] += len(from_urls) - len(real_from)
        # Also skip "merge page with itself" (same from and to)
        real_from = [u for u in real_from if _nu(u) != _nu(to_url)]
        if not real_from:
            continue
        m["from"] = real_from
        clean_merges.append(m)

    clean_deletes = []
    for d in changes_result.get("delete", []):
        if not isinstance(d, dict):
            continue
        if _is_real(d.get("url", "")):
            clean_deletes.append(d)
        else:
            hallucinated["delete"] += 1

    # creates can legitimately be new URLs — keep as-is but mark type
    clean_creates = []
    for c in changes_result.get("create", []):
        if not isinstance(c, dict):
            continue
        c["type"] = c.get("type", "new")
        clean_creates.append(c)

    combined = {
        "clusters": clean_clusters,
        "merge": clean_merges,
        "delete": clean_deletes,
        "create": clean_creates,
        "keyword_assignments": summary_result.get("keyword_assignments", []),
        "estimated_new_score": summary_result.get("estimated_new_score", 0),
        "summary": summary_result.get("summary", ""),
        "_hallucination_report": hallucinated,
    }
    print(f"[ideal_structure] Hallucination filter: {hallucinated}")
    st.session_state["_ideal_structure"] = combined
    from utils.persistence import _save_ai_key, _volume_available
    if _volume_available():
        _save_ai_key("_ideal_structure", combined)


def _run_plan_validation():
    """AI reviews all generated implementation plans against site issues.
    Checks coverage, conflicts, priority order, missing actions."""
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    if "_site_validation" not in st.session_state:
        raise ValueError("Run site validation first (step 9)")

    import json
    from utils.ai_generator import get_client, _parse_ai_json

    # Collect all generated implementation plans
    plans_data = {}
    for key, val in st.session_state.items():
        if key.startswith("_ai_plan_") and isinstance(val, dict) and not val.get("error"):
            url = val.get("url") or key
            plans_data[url] = val

    if len(plans_data) == 0:
        raise ValueError("No implementation plans generated yet. Generate plans in Quick Wins first.")

    client = get_client(get_anthropic_key())
    site_issues = st.session_state.get("_site_validation", {})
    ideal = st.session_state.get("_ideal_structure", {})

    # Summarize all plans
    plan_summaries = []
    for url, plan in list(plans_data.items())[:20]:
        steps_summary = []
        for s in plan.get("steps", []):
            steps_summary.append(f"- [{s.get('type','')}] {s.get('action','')}")
        new_content = [nc.get("suggested_title", "") for nc in plan.get("new_content_suggestions", []) or []]
        rewrites = [rw.get("section", "") for rw in plan.get("text_rewrites", []) or []]
        plan_summaries.append({
            "url": url,
            "primary_keyword": plan.get("primary_keyword", ""),
            "steps": steps_summary[:6],
            "new_content": new_content,
            "rewrites": rewrites,
            "meta_changed": plan.get("meta_changed", False),
        })

    prompt = f"""You are a senior SEO strategist doing a final review.

## SITE ISSUES FOUND
Health score: {site_issues.get('overall_health_score', '?')}/100
Critical issues: {json.dumps(site_issues.get('critical_issues', []))}
Structural problems: {json.dumps(site_issues.get('structural_problems', []))}
Priority actions recommended: {json.dumps([a.get('action','') if isinstance(a, dict) else str(a) for a in site_issues.get('priority_actions', [])])}

## IDEAL STRUCTURE (if available)
Pages to merge: {len(ideal.get('merge', [])) if isinstance(ideal, dict) else 0}
Pages to delete: {len(ideal.get('delete', [])) if isinstance(ideal, dict) else 0}
Pages to create: {len(ideal.get('create', [])) if isinstance(ideal, dict) else 0}

## IMPLEMENTATION PLANS GENERATED ({len(plan_summaries)} pages)
{json.dumps(plan_summaries, ensure_ascii=False, indent=1)}

## YOUR TASK
Cross-check the implementation plans against site issues AND ideal structure. Answer:

1. **Coverage**: Do the plans address ALL critical site issues? Which are NOT covered?
2. **Conflicts**: Do any plans conflict with each other?
3. **Priority**: Is the order correct?
4. **Missing**: What actions are needed that NO plan includes?
5. **Risks**: Will any recommended change potentially hurt rankings?
6. **Sequence**: What is the correct order to implement these changes?
7. **Ideal structure conflicts**: Do any plans try to improve pages scheduled for merge/delete?

## OUTPUT (JSON):
{{
    "plans_cover_issues": true,
    "coverage_score": 0,
    "uncovered_issues": ["critical issue not addressed by any plan"],
    "conflicts": [{{"plan_a": "url", "plan_b": "url", "conflict": "description"}}],
    "priority_corrections": ["plan X should be done before plan Y because..."],
    "missing_actions": ["action needed but not in any plan"],
    "risks": ["potential risk from recommended changes"],
    "recommended_sequence": [
        {{"order": 1, "action": "what to do first", "urls": ["url1"], "reason": "why first"}}
    ],
    "overall_verdict": "2-3 sentences: are these plans correct and complete?",
    "confidence": 0
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    result = _parse_ai_json(message)
    st.session_state["_plan_validation"] = result
    from utils.persistence import _save_ai_key, _volume_available
    if _volume_available():
        _save_ai_key("_plan_validation", result)


def _run_gap_analysis():
    """Generate migration plan from current to ideal structure."""
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    if "_ideal_structure" not in st.session_state:
        raise ValueError("Run ideal structure first (step 10)")
    if "_site_validation" not in st.session_state:
        raise ValueError("Run site validation first")

    import json
    from utils.ai_generator import get_client, _parse_ai_json

    client = get_client(get_anthropic_key())
    site_val = st.session_state.get("_site_validation", {})
    ideal = st.session_state.get("_ideal_structure", {})
    audit_results = st.session_state.get("audit_results", [])

    prompt = f"""Create a prioritized migration plan from current to ideal site structure.

## CURRENT
- Pages: {len(audit_results)}
- Health score: {site_val.get('overall_health_score', '?')}/100
- Critical issues: {'; '.join(site_val.get('critical_issues', [])[:5])}

## IDEAL
- Clusters: {len(ideal.get('clusters', []))}
- Pages to merge: {len(ideal.get('merge', []))}
- Pages to delete: {len(ideal.get('delete', []))}
- Pages to create: {len(ideal.get('create', []))}
- Estimated new score: {ideal.get('estimated_new_score', '?')}/100

## TASK
Create a 4-phase migration plan. Phase 1 = quick wins, Phase 4 = long-term.

Output JSON:
{{
  "phases": [
    {{
      "phase": 1,
      "name": "Quick wins",
      "duration_weeks": 1,
      "actions": ["action 1", "action 2"],
      "risk": "low/medium/high"
    }}
  ],
  "total_weeks": 0,
  "risks": ["risk 1", "risk 2"],
  "success_metrics": ["metric 1", "metric 2"]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    result = _parse_ai_json(message)
    st.session_state["_gap_analysis"] = result
    from utils.persistence import _save_ai_key, _volume_available
    if _volume_available():
        _save_ai_key("_gap_analysis", result)


def _run_site_validation():
    """Run AI site structure validation."""
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    if "audit_results" not in st.session_state:
        raise ValueError("Run bulk audit first")
    if "topic_clusters" not in st.session_state:
        raise ValueError("Run topic clusters first")

    import json
    from utils.ai_generator import get_client, _parse_ai_json
    from views.site_map_export import _build_site_structure

    audit_results = st.session_state["audit_results"]
    gsc_data = st.session_state.get("gsc_data")
    topic_clusters = st.session_state.get("topic_clusters", {})
    page_authority = st.session_state.get("page_authority")

    df_structure = _build_site_structure(audit_results, gsc_data, topic_clusters, page_authority)
    if df_structure.empty:
        raise ValueError("No site structure data")

    # Prefer SF's actual orphan_pages list (ground truth from real crawl)
    # over df_structure's Links-In == 0 calculation (which over-counts because
    # the inlink map is based on a limited crawl sample).
    sf_issues = st.session_state.get("sf_crawl_issues") or {}
    sf_orphans = sf_issues.get("orphan_pages") or []
    if isinstance(sf_orphans, list) and len(sf_orphans) > 0:
        orphans = len(sf_orphans)
    else:
        # Fallback to df_structure calculation only if SF data unavailable
        orphans = len(df_structure[df_structure["Links In"] == 0]) if "Links In" in df_structure.columns else 0
    no_cluster = len(df_structure[df_structure["Cluster(s)"] == ""]) if "Cluster(s)" in df_structure.columns else 0
    thin = len(df_structure[df_structure.get("Word Count", 0) < 300]) if "Word Count" in df_structure.columns else 0

    summary = {
        "total_pages": len(df_structure),
        "total_clusters": len(topic_clusters.get("clusters", [])),
        "orphan_pages": int(orphans),
        "pages_without_cluster": int(no_cluster),
        "thin_pages": int(thin),
        "total_impressions": int(df_structure["Impressions"].sum()) if "Impressions" in df_structure.columns else 0,
        "total_clicks": int(df_structure["Clicks"].sum()) if "Clicks" in df_structure.columns else 0,
        "page_types": df_structure["Page Type"].value_counts().to_dict() if "Page Type" in df_structure.columns else {},
        "clusters_summary": [
            {"topic": c.get("topic", ""), "pages": c.get("page_count", 0), "impressions": c.get("total_impressions", 0)}
            for c in topic_clusters.get("clusters", [])[:20]
        ],
    }

    # Compute deterministic sub-scores from the data BEFORE asking the AI.
    # This prevents the model from inventing wildly different scores each run.
    total = max(1, summary["total_pages"])
    orphan_pct = orphans / total * 100
    no_cluster_pct = no_cluster / total * 100
    thin_pct = thin / total * 100

    # Deterministic health score (0-100) — computed from data, not LLM guess
    health = 100
    health -= min(40, orphan_pct * 1.0)        # up to -40 for orphans
    health -= min(30, no_cluster_pct * 0.6)    # up to -30 for unclustered
    health -= min(20, thin_pct * 0.4)          # up to -20 for thin
    if summary["total_clusters"] < 10:
        health -= 10                            # penalty for too few clusters
    deterministic_score = max(0, min(100, int(round(health))))

    client = get_client(get_anthropic_key())
    prompt = f"""You are a senior SEO architect. Review this site structure and identify SYSTEMIC issues.

## SITE SUMMARY
{json.dumps(summary, ensure_ascii=False, indent=2)}

## DERIVED METRICS
- Orphan pages: {orphans} ({orphan_pct:.1f}% of site)
- Pages without cluster: {no_cluster} ({no_cluster_pct:.1f}% of site)
- Thin pages (<300 words): {thin} ({thin_pct:.1f}% of site)
- Total clusters: {summary['total_clusters']}

## DETERMINISTIC HEALTH SCORE
The site's structural health score is **{deterministic_score}/100**.
This is computed deterministically from the metrics above using a fixed
rubric (penalties for orphan %, unclustered %, thin %, cluster count).
You MUST use this exact number in your output. Do NOT invent your own.

## YOUR ANALYSIS
Identify:
1. Cluster completeness issues
2. Orphan / unclustered page patterns
3. Content gaps relative to cluster topics
4. Structural problems
5. Concrete priority actions

## OUTPUT (JSON):
{{
  "overall_health_score": {deterministic_score},
  "summary": "3-4 sentences about site SEO health",
  "critical_issues": ["issue 1", "issue 2"],
  "structural_problems": ["problem 1"],
  "cluster_issues": ["cluster issue 1"],
  "opportunities": ["opportunity 1"],
  "priority_actions": [
    {{"action": "what to do", "impact": "high/medium/low", "pages_affected": 0}}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        temperature=0,  # Deterministic output
        messages=[{"role": "user", "content": prompt}],
    )
    result = _parse_ai_json(message)
    # Force deterministic score regardless of what the model returned
    if isinstance(result, dict):
        result["overall_health_score"] = deterministic_score
        result["_score_components"] = {
            "orphan_pct": round(orphan_pct, 1),
            "no_cluster_pct": round(no_cluster_pct, 1),
            "thin_pct": round(thin_pct, 1),
            "cluster_count": summary["total_clusters"],
        }
    st.session_state["_site_validation"] = result
    from utils.persistence import _save_ai_key, _volume_available
    if _volume_available():
        _save_ai_key("_site_validation", result)


# ── Main render ────────────────────────────────────────────────

def _run_quality_until_done():
    """Step 7 entry point — delegates to the shared runner so this view never
    re-implements the loop. Exceptions bubble to the pipeline UI handler."""
    from utils.quality_check_runner import run_until_done
    audit = st.session_state.get("audit_results", []) or []
    if not audit:
        raise ValueError("Run bulk audit first (step 6)")
    run_until_done(audit)


def _run_cluster_linking():
    """Generate horizontal/vertical link recommendations within each cluster."""
    from utils.cluster_linking import generate_cluster_link_recommendations
    from utils.persistence import save
    tc = st.session_state.get("topic_clusters", {}) or {}
    clusters = tc.get("clusters", []) if isinstance(tc, dict) else []
    audit = st.session_state.get("audit_results", []) or []
    sf = st.session_state.get("sf_link_map", {}) or {}
    recs = generate_cluster_link_recommendations(clusters, audit, sf)
    st.session_state["cluster_link_recommendations"] = recs
    try:
        save("cluster_link_recommendations", recs)
    except Exception:
        pass
    return recs


# Pipeline definition — single source of truth for "what to run, in what order"
PIPELINE_STEPS = [
    {"num": 1,  "title": "Fetch GSC data",         "key": "gsc_data",         "fn": _run_fetch_gsc,         "long": False, "estimate": "~30 sec"},
    {"num": 2,  "title": "Build Page Authority",   "key": "page_authority",   "fn": _run_build_authority,   "long": False, "estimate": "~30 sec"},
    {"num": 3,  "title": "Analyze Crawl Issues",   "key": "sf_crawl_issues",  "fn": _run_crawl_analysis,    "long": False, "estimate": "~1 min"},
    {"num": 4,  "title": "CTR Gap Analysis",       "key": "ctr_gaps",         "fn": _run_ctr_analysis,      "long": False, "estimate": "~30 sec"},
    {"num": 5,  "title": "Build Topic Clusters",   "key": "topic_clusters",   "fn": _run_topic_clusters,    "long": False, "estimate": "~1 min (AI)"},
    {"num": 6,  "title": "Bulk Audit Pages",       "key": "audit_results",    "fn": _run_bulk_audit,        "long": True,  "estimate": "~18 min for 1000+ pages"},
    {"num": 7,  "title": "AI Content Quality",     "key": None,               "fn": _run_quality_until_done,"long": True,  "estimate": "~15 min (AI)"},
    {"num": 8,  "title": "Cannibalization",        "key": "cannibalization",  "fn": _run_cannibalization,   "long": False, "estimate": "~5 min"},
    {"num": 9,  "title": "Cluster Linking",        "key": "cluster_link_recommendations", "fn": _run_cluster_linking, "long": False, "estimate": "~10 sec"},
    {"num": 10, "title": "Site Validation",        "key": "_site_validation", "fn": _run_site_validation,   "long": False, "estimate": "~30 sec (AI)"},
    {"num": 11, "title": "Generate Ideal Structure","key": "_ideal_structure","fn": _run_ideal_structure,   "long": False, "estimate": "~1 min (AI)"},
    {"num": 12, "title": "Gap Analysis",           "key": "_gap_analysis",    "fn": _run_gap_analysis,      "long": False, "estimate": "~1 min (AI)"},
    {"num": 13, "title": "Plan Validation",        "key": "_plan_validation", "fn": _run_plan_validation,   "long": False, "estimate": "~30 sec (AI)"},
]


def _step_done(step) -> bool:
    """Has this step completed (data exists in session_state)?"""
    if step["num"] == 7:
        from utils.quality_check_runner import eligible_pages, already_checked_count
        eligible = eligible_pages(st.session_state.get("audit_results", []))
        if not eligible:
            return False
        return already_checked_count(eligible) >= len(eligible)
    return step["key"] in st.session_state and st.session_state[step["key"]] is not None


def _step_progress_text(step) -> str:
    """Status string for a step — used in timeline."""
    if step["num"] == 7:
        from utils.quality_check_runner import (
            eligible_pages, quality_input_hash, quality_key,
            ELIGIBLE_PAGE_TYPES, MIN_WORD_COUNT,
        )
        from collections import Counter
        audit = st.session_state.get("audit_results", []) or []
        eligible = eligible_pages(audit)
        if not eligible:
            if not audit:
                return "waiting for audit"
            # Honest diagnosis: audit IS done but no pages match the filter.
            type_counts = Counter((r.get("page_type") or "missing") for r in audit)
            type_str = ", ".join(f"{t}:{n}" for t, n in type_counts.most_common())
            return (
                f"⚠ 0/{len(audit)} eligible — needs {'/'.join(ELIGIBLE_PAGE_TYPES)} "
                f"with >{MIN_WORD_COUNT} words. Got: {type_str}"
            )
        up_to_date = stale = missing = 0
        for r in eligible:
            existing = st.session_state.get(quality_key(r.get("url", "")))
            if existing is None:
                missing += 1
            elif isinstance(existing, dict) and existing.get("_input_hash") == quality_input_hash(r):
                up_to_date += 1
            else:
                stale += 1
        total = len(eligible)
        if up_to_date >= total:
            return f"✓ {up_to_date}/{total} checked"
        parts = []
        if up_to_date:
            parts.append(f"{up_to_date} current")
        if stale:
            parts.append(f"{stale} stale")
        if missing:
            parts.append(f"{missing} new")
        need_check = stale + missing
        return f"⏳ {need_check}/{total} need check ({', '.join(parts)})"
    if _step_done(step):
        data = st.session_state.get(step["key"])
        if hasattr(data, "__len__"):
            try:
                return f"✓ done ({len(data)})"
            except Exception:
                pass
        return "✓ done"
    return "not started"


def _render_timeline():
    """Visual timeline of all 12 steps with status icons + estimates."""
    st.markdown(
        "<div style='background:#0d0d15; border:1px solid #2a2a40; border-radius:8px; padding:1rem; margin:0.5rem 0;'>",
        unsafe_allow_html=True,
    )
    cols = st.columns([1, 5, 3, 2])
    cols[0].markdown("<div style='font-size:0.7rem; color:#6b6b8a; font-family:monospace;'>STEP</div>", unsafe_allow_html=True)
    cols[1].markdown("<div style='font-size:0.7rem; color:#6b6b8a; font-family:monospace;'>NAME</div>", unsafe_allow_html=True)
    cols[2].markdown("<div style='font-size:0.7rem; color:#6b6b8a; font-family:monospace;'>STATUS</div>", unsafe_allow_html=True)
    cols[3].markdown("<div style='font-size:0.7rem; color:#6b6b8a; font-family:monospace;'>EST. TIME</div>", unsafe_allow_html=True)

    for step in PIPELINE_STEPS:
        done = _step_done(step)
        icon = "✓" if done else "○"
        color = "#33dd88" if done else "#6b6b8a"
        c = st.columns([1, 5, 3, 2])
        c[0].markdown(f"<div style='font-size:1.1rem; color:{color}; padding:0.3rem 0;'>{icon} {step['num']}</div>", unsafe_allow_html=True)
        c[1].markdown(f"<div style='color:#e8e8f0; padding:0.3rem 0;'>{step['title']}</div>", unsafe_allow_html=True)
        c[2].markdown(f"<div style='color:{color}; font-size:0.85rem; padding:0.3rem 0;'>{_step_progress_text(step)}</div>", unsafe_allow_html=True)
        c[3].markdown(f"<div style='color:#9b9bb8; font-size:0.8rem; padding:0.3rem 0;'>{step['estimate']}</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def render():
    st.markdown("## ⚡ Run Pipeline")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:0.5rem;'>"
        "ONE place to run everything. Click <strong>🚀 Run All Remaining</strong> "
        "and the system steps through every step in order, picking up where it left off.</p>",
        unsafe_allow_html=True,
    )

    if "gsc_data" not in st.session_state:
        st.warning("**First time?** Go to **1. Setup & Connect** in the menu and connect GSC. Then come back here.")
        return

    # ── MEGA BUTTON: Run all remaining ──────────────────────
    remaining_steps = [s for s in PIPELINE_STEPS if not _step_done(s)]
    n_done = len(PIPELINE_STEPS) - len(remaining_steps)

    if remaining_steps:
        next_up = remaining_steps[0]
        long_count = sum(1 for s in remaining_steps if s["long"])
        button_label = f"🚀 Run all remaining ({len(remaining_steps)} steps)"
        st.markdown(
            f"<div style='background:#0d0d15; border:3px solid #5533ff; border-radius:10px; "
            f"padding:1.2rem; margin-bottom:1rem;'>"
            f"<div style='font-family:\"Syne\",sans-serif; font-size:1.1rem; color:#c8b4ff; font-weight:700;'>"
            f"{n_done}/{len(PIPELINE_STEPS)} steps done · {len(remaining_steps)} remaining</div>"
            f"<div style='color:#9b9bb8; font-size:0.9rem; margin-top:0.4rem;'>"
            f"Next up: <strong>Step {next_up['num']} — {next_up['title']}</strong> "
            f"({next_up['estimate']}). "
            f"{'Total has ' + str(long_count) + ' long-running step(s) — total time approx 30-60 min.' if long_count else 'All remaining are quick.'}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button(button_label, type="primary", key="rp_run_all", use_container_width=True):
            from utils.diagnostics import log_run
            progress = st.progress(0)
            status = st.empty()
            done_now = 0
            for step in remaining_steps:
                status.markdown(f"**Step {step['num']} — {step['title']}** ({step['estimate']})...")
                try:
                    with log_run(f"Step {step['num']}: {step['title']}") as run_ctx:
                        run_ctx.input("step_num", step["num"])
                        run_ctx.input("estimate", step["estimate"])
                        # Snapshot relevant input sizes
                        for k in ("gsc_data", "audit_results", "topic_clusters", "cannibalization", "page_authority"):
                            v = st.session_state.get(k)
                            if v is not None:
                                try:
                                    run_ctx.input(f"{k}_size", len(v) if hasattr(v, "__len__") else "present")
                                except Exception:
                                    pass
                        step["fn"]()
                        # Snapshot what was produced
                        if step["key"]:
                            out_data = st.session_state.get(step["key"])
                            if out_data is not None:
                                try:
                                    run_ctx.output(f"{step['key']}_size", len(out_data) if hasattr(out_data, "__len__") else "present")
                                except Exception:
                                    pass
                    done_now += 1
                    progress.progress(done_now / len(remaining_steps))
                except Exception as e:
                    status.error(f"Step {step['num']} ({step['title']}) failed: {e}")
                    import traceback
                    st.code(traceback.format_exc())
                    break
            status.success(f"Pipeline run complete — {done_now}/{len(remaining_steps)} steps finished")
            st.rerun()
    else:
        st.success(f"🎉 All {len(PIPELINE_STEPS)} pipeline steps complete!")

    # ── Visual timeline ─────────────────────────────────────
    st.markdown("### Pipeline status")
    _render_timeline()

    # ── Per-step controls (collapsed by default) ────────────
    with st.expander("⚙ Run a single step (advanced)", expanded=False):
        st.caption("Use these only if you need to re-run one specific step. Normally just click the mega-button above.")
        for step in PIPELINE_STEPS:
            done = _step_done(step)
            icon = "✓" if done else "○"
            c = st.columns([1, 5, 2])
            with c[0]:
                st.markdown(f"<div style='color:{'#33dd88' if done else '#6b6b8a'};'>{icon} {step['num']}</div>", unsafe_allow_html=True)
            with c[1]:
                st.markdown(f"**{step['title']}** — {step['estimate']}")
            with c[2]:
                if st.button("Run", key=f"rp_solo_{step['num']}", use_container_width=True):
                    from utils.diagnostics import log_run
                    try:
                        with st.spinner(f"Running {step['title']}..."):
                            with log_run(f"Solo: Step {step['num']}: {step['title']}"):
                                step["fn"]()
                        st.success("done")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                        import traceback
                        st.code(traceback.format_exc())

    # ── Maintenance — reset cache, etc. ─────────────────────
    st.markdown("---")
    with st.expander("🔧 Maintenance — reset analyses, clear cache", expanded=False):
        st.markdown(
            "<div style='background:#1a0a0a; border:2px solid #ff4455; border-radius:6px; "
            "padding:0.8rem; margin-bottom:0.8rem;'>"
            "<strong style='color:#ff4455;'>🗑 Reset site-level analyses</strong><br>"
            "<span style='color:#e8e8f0; font-size:0.85rem;'>"
            "Deletes: site validation, ideal structure, gap analysis, plan validation, "
            "cannibalization, cluster_link_recommendations, cluster_health.<br>"
            "<strong>KEEPS (expensive, hash-protected):</strong> "
            "Step 7 AI quality verdicts (~1 hour to recompute), AI implementation plans, "
            "generated bottom texts, generated intro texts, audit page data. These are all "
            "auto-invalidated per page when their inputs change — no need to nuke them.</span></div>",
            unsafe_allow_html=True,
        )
        if st.button("🗑 Reset site-level analyses", key="rp_maint_reset", type="secondary"):
            import os as _os
            from utils.persistence import AI_CACHE_DIR as _AID
            # NEVER include _quality_, _ai_plan_, _bottom_text_, _intro_text_ here.
            # Those are per-page AI cache, hash-protected against staleness, and
            # reflect HOURS of paid Sonnet calls. Deleting them on a generic
            # "reset analyses" click is a foot-gun — caused 5h of lost work
            # for Henrik on 2026-05-10 and must never happen again.
            prefixes = (
                "_site_validation", "_ideal_structure", "_gap_analysis", "_plan_validation",
                "_refresh_all_result", "_cluster_health_",
            )
            deleted = 0
            keys_to_del = [k for k in st.session_state if any(k.startswith(p) for p in prefixes)]
            for k in keys_to_del:
                del st.session_state[k]
                deleted += 1
            for k in ("cannibalization", "cannibal_page_summary", "cannibal_clusters",
                      "cluster_link_recommendations"):
                if k in st.session_state:
                    del st.session_state[k]
                    deleted += 1
            disk_deleted = 0
            if _os.path.isdir(_AID):
                for f in _os.listdir(_AID):
                    if any(f.startswith(p) for p in prefixes):
                        try:
                            _os.remove(_os.path.join(_AID, f))
                            disk_deleted += 1
                        except Exception:
                            pass
            for fname in ("cannibalization.json", "cluster_link_recommendations.json"):
                p = _os.path.join("/data", fname)
                if _os.path.exists(p):
                    try:
                        _os.remove(p)
                        disk_deleted += 1
                    except Exception:
                        pass
            st.success(
                f"🗑 Reset done: {deleted} session keys + {disk_deleted} disk files deleted. "
                f"Audit data kept — go scrape if you want fresh, otherwise click 🚀 Run all."
            )
            st.rerun()

        # ── Re-parse cached HTML (no network) ────────────────
        from utils.html_cache import cache_stats, parse_from_cache, clear_cache
        stats = cache_stats()
        st.markdown(
            f"<div style='background:#0d0d15; border:1px solid #5bb4d4; border-radius:6px; "
            f"padding:0.8rem; margin-top:1rem;'>"
            f"<strong style='color:#5bb4d4;'>🔄 Re-parse cached HTML (no re-scrape needed)</strong><br>"
            f"<span style='color:#9b9bb8; font-size:0.85rem;'>"
            f"Cached HTML: <strong>{stats['count']} pages</strong> · {stats['size_mb']} MB on disk.<br>"
            f"Re-runs the full parser + classifier on already-fetched HTML. "
            f"Use after fixing parser/classifier bugs — takes ~2 min instead of 18.</span></div>",
            unsafe_allow_html=True,
        )
        rpc1, rpc2 = st.columns(2)
        with rpc1:
            if st.button("🔄 Re-parse ALL cached HTML", key="rp_reparse_cached", type="primary", use_container_width=True):
                if stats["count"] == 0:
                    st.warning("No cached HTML found. Run a scrape first.")
                else:
                    from utils.ui_helpers import normalize_url as _nurl_rp
                    from utils.diagnostics import log_run
                    audit = st.session_state.get("audit_results", []) or []
                    urls_to_reparse = [r.get("url", "") for r in audit if r.get("url")]
                    progress = st.progress(0)
                    status_txt = st.empty()
                    reparsed = 0
                    with log_run("Re-parse cached HTML") as run_ctx:
                        run_ctx.input("urls", len(urls_to_reparse))
                        run_ctx.input("cached_pages", stats["count"])
                        for i, url in enumerate(urls_to_reparse):
                            parsed = parse_from_cache(url)
                            if parsed:
                                # Update the audit entry in-place
                                norm = _nurl_rp(url)
                                for j, r in enumerate(audit):
                                    if _nurl_rp(r.get("url", "")) == norm:
                                        parsed["url"] = url
                                        audit[j] = parsed
                                        reparsed += 1
                                        break
                            if (i + 1) % 50 == 0:
                                progress.progress((i + 1) / len(urls_to_reparse))
                                status_txt.text(f"Re-parsed {i+1}/{len(urls_to_reparse)}...")
                        run_ctx.output("reparsed", reparsed)
                    st.session_state["audit_results"] = audit
                    save_key("audit_results")
                    progress.progress(1.0)
                    st.success(f"Re-parsed {reparsed}/{len(urls_to_reparse)} pages from cached HTML")
                    st.rerun()
        with rpc2:
            if st.button("🗑 Clear HTML cache", key="rp_clear_html_cache", use_container_width=True):
                n = clear_cache()
                st.success(f"Cleared {n} cached HTML files")

        st.markdown(
            "<div style='background:#0d0d15; border:1px solid #2a2a40; border-radius:6px; "
            "padding:0.8rem; margin-top:1rem;'>"
            "<strong style='color:#c8b4ff;'>🌐 Re-scrape from network</strong><br>"
            "<span style='color:#9b9bb8; font-size:0.85rem;'>"
            "Only needed when the SITE's content has changed (new pages, updated text). "
            "If you just fixed parser/classifier bugs, use Re-parse above instead.</span><br>"
            "<span style='color:#5bb4d4;'>→ Go to <strong>6. Page Auditor</strong> "
            "in left menu and click \"Re-scrape ALL pages (force)\".</span></div>",
            unsafe_allow_html=True,
        )

    # ── Diagnostics — download + summary ─────────────────────
    with st.expander("🔬 Diagnostics — download run logs (errors, timing, inputs/outputs)", expanded=False):
        from utils.diagnostics import get_summary, export_all_as_json, get_logs, clear_logs
        summary = get_summary()
        st.caption(
            "Every pipeline step + AI call writes a log entry: inputs (data sizes), "
            "outputs (what was produced), elapsed time, full error traceback. "
            "Persisted to /data/diagnostics/ on the Railway volume — survives restarts."
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total log entries", summary["total_entries"])
        c2.metric("Distinct operations", len(summary["by_name"]))
        err_count = sum(summary["errors_by_name"].values())
        c3.metric("Errors", err_count, delta="↓ good" if err_count == 0 else f"↑ {err_count}")
        c4.metric("Total elapsed (s)", summary["total_seconds"])

        d1, d2 = st.columns(2)
        with d1:
            if summary["total_entries"] > 0:
                blob = export_all_as_json()
                from datetime import datetime as _dt
                fname = f"diagnostics_{_dt.now().strftime('%Y%m%d_%H%M')}.json"
                st.download_button(
                    f"⬇ Download {fname} ({len(blob)//1024} KB)",
                    data=blob, file_name=fname, mime="application/json",
                    type="primary", use_container_width=True, key="rp_diag_dl",
                )
            else:
                st.caption("No log entries yet. Run something to generate logs.")
        with d2:
            if st.button("🗑 Clear all logs", key="rp_diag_clear", use_container_width=True):
                n = clear_logs()
                st.success(f"Cleared {n} log files")
                st.rerun()

        if err_count > 0:
            st.markdown("**Recent errors:**")
            for entry in get_logs(limit=20, errors_only=True):
                err = entry.get("error", {})
                st.markdown(
                    f"<div style='background:#1a0a0a; border-left:3px solid #ff4455; "
                    f"padding:0.6rem; margin:0.3rem 0; border-radius:0 6px 6px 0; font-size:0.85rem;'>"
                    f"<div style='color:#ff4455; font-weight:600;'>{entry.get('name', '?')}</div>"
                    f"<div style='color:#9b9bb8; font-size:0.75rem;'>{entry.get('ts', '')}</div>"
                    f"<div style='color:#e8e8f0; margin-top:0.3rem;'>{err.get('type', '')}: {err.get('message', '')}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        if summary["by_name"]:
            st.markdown("**Operation counts:**")
            for name, count in list(summary["by_name"].items())[:20]:
                err_n = summary["errors_by_name"].get(name, 0)
                color = "#ff4455" if err_n > 0 else "#33dd88"
                st.markdown(
                    f"- `{name}`: {count} runs"
                    + (f" · <span style='color:{color};'>{err_n} errors</span>" if err_n else ""),
                    unsafe_allow_html=True,
                )

        return  # end render

