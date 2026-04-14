"""
Run Pipeline — One-page control center for running all SEO analysis steps.
Each step has a Run button and shows status. "Run All" runs everything sequentially.
"""

import streamlit as st
from utils.persistence import save_key
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
    from utils.topic_clusters import build_topic_clusters
    fallback = build_topic_clusters(df, min_cluster_size=2)
    if result and result.get("clusters"):
        # Use AI clusters but keep page_topics from algorithmic for completeness
        ai_clusters = result["clusters"]
        # Enrich with page data from GSC
        for c in ai_clusters:
            cluster_queries = c.get("queries", [])
            cluster_pages = df[df["query"].isin(cluster_queries)]["page"].unique().tolist()
            c["pages"] = [{"page": p, "query_count": 0, "total_clicks": 0, "total_impressions": 0, "avg_position": 0} for p in cluster_pages[:20]]
            c["page_count"] = len(cluster_pages)
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
    """Trigger the bulk audit. This is the slowest step."""
    raise NotImplementedError("Bulk audit must be run from 6. Page Auditor — too long for this page")


def _run_quality_check():
    from utils.ai_generator import get_client, assess_content_quality_batch
    from utils.ui_helpers import stable_hash
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    audit_results = st.session_state.get("audit_results", [])
    if not audit_results:
        raise ValueError("Run bulk audit first")
    # Check pages not yet assessed
    candidates = [r for r in audit_results
                  if r.get("page_type") in ("category", "blog", "faq")
                  and r.get("word_count", 0) > 50
                  and f"_quality_{stable_hash(r['url'])}" not in st.session_state]
    if not candidates:
        return
    client = get_client(get_anthropic_key())
    from utils.persistence import save
    # Process in batches of 5
    for i in range(0, min(len(candidates), 50), 5):  # Max 50 pages per click
        batch = candidates[i:i+5]
        results = assess_content_quality_batch(
            client, batch,
            site_context=st.session_state.get("site_context", ""),
            language=st.session_state.get("content_language", "Swedish"),
            topic_clusters=st.session_state.get("topic_clusters"),
        )
        for r in results:
            url = r.get("url", "")
            key = f"_quality_{stable_hash(url)}"
            st.session_state[key] = r
            save(key)  # Persist immediately per-item


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
        model="claude-sonnet-4-20250514",
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
        model="claude-sonnet-4-20250514",
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
        model="claude-sonnet-4-20250514",
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
        model="claude-sonnet-4-20250514",
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
        model="claude-sonnet-4-20250514",
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
        model="claude-sonnet-4-20250514",
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

def render():
    st.markdown("## ⚡ Run Pipeline")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1rem;'>"
        "Run all SEO analysis steps from one page. Click each step's Run button, "
        "or use Run All Remaining at the bottom.</p>",
        unsafe_allow_html=True,
    )

    if "gsc_data" not in st.session_state:
        st.warning("**First time?** Go to **1. Setup & Connect** in the menu and connect GSC. Then come back here.")
        return

    # ── Freshness banner: warn if gsc_data is old ───────────────
    age_str, stale = _data_age_str("gsc_data")
    if age_str:
        if stale:
            col_a, col_b = st.columns([4, 1])
            with col_a:
                st.warning(f"⚠ GSC data is{age_str.replace(' · ','')} — re-fetch recommended (run Step 1 again).")
            with col_b:
                if st.button("Re-fetch GSC", key="rp_refetch_gsc", use_container_width=True, type="primary"):
                    try:
                        with st.spinner("Re-fetching fresh GSC data..."):
                            _run_fetch_gsc()
                        st.success("GSC data refreshed")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
        else:
            st.caption(f"📅 GSC data{age_str}")

    st.markdown("---")

    # ── Steps ───────────────────────────────────────────────
    _run_step_card(
        1, "Fetch GSC data",
        "Pull queries, pages, clicks, impressions from Google Search Console (90 days)",
        "gsc_data", _run_fetch_gsc, "rp_gsc"
    )

    _run_step_card(
        2, "Build Page Authority",
        "Combine Ahrefs Best by Links + Backlinks → per-page authority scores",
        "page_authority", _run_build_authority, "rp_authority"
    )

    _run_step_card(
        3, "Analyze Crawl Issues",
        "Detect orphans, broken links, canonicals, faceted URLs, near-duplicates from SF data",
        "sf_crawl_issues", _run_crawl_analysis, "rp_crawl"
    )

    _run_step_card(
        4, "CTR Gap Analysis",
        "Find pages where CTR underperforms vs position benchmarks",
        "ctr_gaps", _run_ctr_analysis, "rp_ctr"
    )

    _run_step_card(
        5, "Build Topic Clusters",
        "AI groups GSC queries into 30-50 topic clusters (~30 sec)",
        "topic_clusters", _run_topic_clusters, "rp_clusters"
    )

    # Bulk audit — special case (long running)
    icon, status, color = _step_status("audit_results")
    col1, col2, col3 = st.columns([1, 6, 2])
    with col1:
        st.markdown(
            f"<div style='font-size:1.5rem; color:{color}; text-align:center; padding-top:0.5rem;'>{icon}</div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"<div style='font-weight:600; color:#e8e8f0;'>6. Bulk Audit Pages</div>"
            f"<div style='font-size:0.8rem; color:#9b9bb8;'>Scrape + audit all pages from GSC (~20 min for 1000+ pages)</div>"
            f"<div style='font-size:0.7rem; color:{color}; margin-top:0.2rem;'>{status}</div>",
            unsafe_allow_html=True,
        )
    with col3:
        if st.button("Open →", key="rp_audit_link", use_container_width=True):
            st.session_state["selected_page"] = "6. Page Auditor"
            st.rerun()
    st.markdown("<hr style='margin:0.5rem 0; border:none; border-top:1px solid #1e1e2e;'>", unsafe_allow_html=True)

    # AI Quality (only if audit is done)
    if "audit_results" in st.session_state:
        from utils.ui_helpers import stable_hash
        audit_results = st.session_state.get("audit_results", [])
        candidates = [r for r in audit_results
                      if r.get("page_type") in ("category", "blog", "faq")
                      and r.get("word_count", 0) > 50]
        checked = sum(1 for r in candidates if f"_quality_{stable_hash(r['url'])}" in st.session_state)

        col1, col2, col3 = st.columns([1, 6, 2])
        with col1:
            done = checked == len(candidates) and len(candidates) > 0
            icon = "✓" if done else "⏳" if checked > 0 else "✗"
            color = "#33dd88" if done else "#ffaa33" if checked > 0 else "#6b6b8a"
            st.markdown(
                f"<div style='font-size:1.5rem; color:{color}; text-align:center; padding-top:0.5rem;'>{icon}</div>",
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                f"<div style='font-weight:600; color:#e8e8f0;'>7. AI Content Quality Check</div>"
                f"<div style='font-size:0.8rem; color:#9b9bb8;'>AI evaluates text quality on category + blog pages (50 per click)</div>"
                f"<div style='font-size:0.7rem; color:{color}; margin-top:0.2rem;'>{checked}/{len(candidates)} checked</div>",
                unsafe_allow_html=True,
            )
        with col3:
            remaining = len(candidates) - checked
            run_label = f"Run {min(50, remaining)}" if remaining > 0 else "Done"
            if st.button(run_label, key="rp_quality", use_container_width=True, disabled=remaining == 0):
                try:
                    with st.spinner(f"AI checking quality of {min(50, remaining)} pages..."):
                        _run_quality_check()
                    st.success("Quality check done")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        st.markdown("<hr style='margin:0.5rem 0; border:none; border-top:1px solid #1e1e2e;'>", unsafe_allow_html=True)

    # ── Step 8: Cannibalization (after quality check so it has E-E-A-T data)
    _run_step_card(
        8, "Cannibalization Detection",
        "Find queries where multiple pages compete (with brand keyword filter + quality verdicts)",
        "cannibalization", _run_cannibalization, "rp_cannibal"
    )

    # ── Site Validation (step 9) ────────────────────────────
    icon, status, color = _step_status("_site_validation")
    val_data = st.session_state.get("_site_validation", {})
    if isinstance(val_data, dict) and val_data.get("overall_health_score") is not None:
        score = val_data.get("overall_health_score", 0)
        status = f"Done (health score: {score}/100)"
        color = "#33dd88" if score >= 70 else "#ffaa33" if score >= 40 else "#ff4455"
        icon = "✓"
    col1, col2, col3 = st.columns([1, 6, 2])
    with col1:
        st.markdown(
            f"<div style='font-size:1.5rem; color:{color}; text-align:center; padding-top:0.5rem;'>{icon}</div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"<div style='font-weight:600; color:#e8e8f0;'>9. Site Validation</div>"
            f"<div style='font-size:0.8rem; color:#9b9bb8;'>AI evaluates entire site architecture and gives health score</div>"
            f"<div style='font-size:0.7rem; color:{color}; margin-top:0.2rem;'>{status}</div>",
            unsafe_allow_html=True,
        )
    with col3:
        if st.button("Run", key="rp_validation", use_container_width=True):
            try:
                with st.spinner("AI evaluating site architecture..."):
                    _run_site_validation()
                st.success("Validation done")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
                import traceback
                st.code(traceback.format_exc())
    st.markdown("<hr style='margin:0.5rem 0; border:none; border-top:1px solid #1e1e2e;'>", unsafe_allow_html=True)

    # ── Step 10: Ideal Structure ────────────────────────────
    icon10, status10, color10 = _step_status("_ideal_structure")
    ideal_data = st.session_state.get("_ideal_structure", {})
    if isinstance(ideal_data, dict) and ideal_data.get("clusters"):
        n_merge = len(ideal_data.get("merge", []))
        n_delete = len(ideal_data.get("delete", []))
        n_create = len(ideal_data.get("create", []))
        status10 = f"Done ({len(ideal_data.get('clusters', []))} clusters, {n_merge} merges, {n_delete} deletes, {n_create} creates)"
        color10 = "#33dd88"
        icon10 = "✓"
    col1, col2, col3 = st.columns([1, 6, 2])
    with col1:
        st.markdown(f"<div style='font-size:1.5rem; color:{color10}; text-align:center; padding-top:0.5rem;'>{icon10}</div>", unsafe_allow_html=True)
    with col2:
        st.markdown(
            f"<div style='font-weight:600; color:#e8e8f0;'>10. Generate Ideal Structure</div>"
            f"<div style='font-size:0.8rem; color:#9b9bb8;'>AI designs optimal site structure: new clusters, merges, deletes, new pages needed (3 AI calls)</div>"
            f"<div style='font-size:0.7rem; color:{color10}; margin-top:0.2rem;'>{status10}</div>",
            unsafe_allow_html=True,
        )
    with col3:
        if st.button("Run", key="rp_ideal", use_container_width=True):
            try:
                with st.spinner("AI designing ideal structure (3 calls, ~90 sec)..."):
                    _run_ideal_structure()
                st.success("Ideal structure generated")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
    st.markdown("<hr style='margin:0.5rem 0; border:none; border-top:1px solid #1e1e2e;'>", unsafe_allow_html=True)

    # ── Step 11: Gap Analysis ────────────────────────────────
    icon11, status11, color11 = _step_status("_gap_analysis")
    gap_data = st.session_state.get("_gap_analysis", {})
    if isinstance(gap_data, dict) and gap_data.get("phases"):
        status11 = f"Done ({len(gap_data.get('phases', []))} phases, {gap_data.get('total_weeks', 0)} weeks total)"
        color11 = "#33dd88"
        icon11 = "✓"
    col1, col2, col3 = st.columns([1, 6, 2])
    with col1:
        st.markdown(f"<div style='font-size:1.5rem; color:{color11}; text-align:center; padding-top:0.5rem;'>{icon11}</div>", unsafe_allow_html=True)
    with col2:
        st.markdown(
            f"<div style='font-weight:600; color:#e8e8f0;'>11. Gap Analysis (Migration Plan)</div>"
            f"<div style='font-size:0.8rem; color:#9b9bb8;'>AI creates 4-phase plan to go from current to ideal structure</div>"
            f"<div style='font-size:0.7rem; color:{color11}; margin-top:0.2rem;'>{status11}</div>",
            unsafe_allow_html=True,
        )
    with col3:
        if st.button("Run", key="rp_gap", use_container_width=True):
            try:
                with st.spinner("AI creating migration plan..."):
                    _run_gap_analysis()
                st.success("Gap analysis done")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    # Show gap analysis result inline if available
    if isinstance(gap_data, dict) and gap_data.get("phases"):
        with st.expander("View migration plan", expanded=False):
            for phase in gap_data.get("phases", []):
                risk_color = {"low": "#33dd88", "medium": "#ffaa33", "high": "#ff4455"}.get(
                    str(phase.get("risk", "")).lower(), "#9b9bb8")
                st.markdown(
                    f"**Phase {phase.get('phase', '?')}: {phase.get('name', '')}** "
                    f"({phase.get('duration_weeks', '?')} weeks, "
                    f"<span style='color:{risk_color};'>{phase.get('risk', '?')} risk</span>)",
                    unsafe_allow_html=True,
                )
                for action in phase.get("actions", []):
                    st.markdown(f"- {action}")
            risks = gap_data.get("risks", [])
            if risks:
                st.markdown("**Risks:**")
                for r in risks:
                    st.markdown(f"- {r}")
            metrics = gap_data.get("success_metrics", [])
            if metrics:
                st.markdown("**Success metrics:**")
                for m in metrics:
                    st.markdown(f"- {m}")

    st.markdown("<hr style='margin:0.5rem 0; border:none; border-top:1px solid #1e1e2e;'>", unsafe_allow_html=True)

    # ── Step 12: Plan Validation ─────────────────────────────
    icon12, status12, color12 = _step_status("_plan_validation")
    pv_data = st.session_state.get("_plan_validation", {})
    if isinstance(pv_data, dict) and pv_data.get("overall_verdict"):
        cov = pv_data.get("coverage_score", "?")
        conf = pv_data.get("confidence", "?")
        status12 = f"Done (coverage {cov}/100, confidence {conf}/100)"
        color12 = "#33dd88"
        icon12 = "✓"
    # Count plans available
    plans_count = sum(1 for k, v in st.session_state.items()
                      if k.startswith("_ai_plan_") and isinstance(v, dict) and not v.get("error"))
    col1, col2, col3 = st.columns([1, 6, 2])
    with col1:
        st.markdown(f"<div style='font-size:1.5rem; color:{color12}; text-align:center; padding-top:0.5rem;'>{icon12}</div>", unsafe_allow_html=True)
    with col2:
        st.markdown(
            f"<div style='font-weight:600; color:#e8e8f0;'>12. Plan Validation (Final Cross-Check)</div>"
            f"<div style='font-size:0.8rem; color:#9b9bb8;'>AI reviews ALL generated page plans against site issues — checks coverage, conflicts, priority, missing actions ({plans_count} plans found)</div>"
            f"<div style='font-size:0.7rem; color:{color12}; margin-top:0.2rem;'>{status12}</div>",
            unsafe_allow_html=True,
        )
    with col3:
        disabled = plans_count == 0
        label = "Run" if not disabled else "No plans"
        if st.button(label, key="rp_plan_val", use_container_width=True, disabled=disabled):
            try:
                with st.spinner("AI cross-checking all plans against site issues..."):
                    _run_plan_validation()
                st.success("Plan validation done")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    # Show plan validation result inline if available
    if isinstance(pv_data, dict) and pv_data.get("overall_verdict"):
        with st.expander("View validation report", expanded=False):
            st.markdown(f"**Verdict:** {pv_data.get('overall_verdict','')}")
            uncovered = pv_data.get("uncovered_issues") or []
            if uncovered:
                st.markdown("**Uncovered issues:**")
                for u in uncovered:
                    st.markdown(f"- {u}")
            missing = pv_data.get("missing_actions") or []
            if missing:
                st.markdown("**Missing actions:**")
                for m in missing:
                    st.markdown(f"- {m}")
            conflicts = pv_data.get("conflicts") or []
            if conflicts:
                st.markdown("**Conflicts:**")
                for c in conflicts:
                    if isinstance(c, dict):
                        st.markdown(f"- {c.get('plan_a','')} ↔ {c.get('plan_b','')}: {c.get('conflict','')}")
            risks = pv_data.get("risks") or []
            if risks:
                st.markdown("**Risks:**")
                for r in risks:
                    st.markdown(f"- {r}")
            seq = pv_data.get("recommended_sequence") or []
            if seq:
                st.markdown("**Recommended sequence:**")
                for s in seq:
                    if isinstance(s, dict):
                        st.markdown(f"{s.get('order','?')}. **{s.get('action','')}** — {s.get('reason','')}")
    st.markdown("<hr style='margin:0.5rem 0; border:none; border-top:1px solid #1e1e2e;'>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Maintenance")

    # ── NUCLEAR: Reset all analyses + AI cache ────────────
    if "audit_results" in st.session_state:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(
                "<div style='font-size:0.85rem; color:#ff4455; background:#1a0a0a; border:2px solid #ff4455; border-radius:6px; padding:0.8rem;'>"
                "<strong>🗑 Reset all analyses + AI cache</strong><br>"
                "Deletes: quality scores, AI plans, generated texts, cannibalization, "
                "site validation, ideal structure, gap analysis, plan validation.<br>"
                "<strong>KEEPS:</strong> GSC data, Ahrefs, Screaming Frog, topic clusters, CTR gaps, audit page data.<br>"
                "After reset: re-scrape (force all) → step 7 → 8 → 9 → 10 → 11.</div>",
                unsafe_allow_html=True,
            )
        with col2:
            if st.button("🗑 Reset analyses", key="rp_reset_analyses", use_container_width=True):
                import os
                from utils.persistence import AI_CACHE_DIR

                deleted = 0
                # Delete from session state
                prefixes_to_delete = (
                    "_quality_", "_ai_plan_", "_bottom_text_", "_intro_text_",
                    "_cannibal_meta_", "_cannibal_rewrite_",
                    "_site_validation", "_ideal_structure", "_gap_analysis", "_plan_validation",
                    "_refresh_all_result", "_cluster_health_",
                )
                keys_to_del = [k for k in st.session_state
                               if any(k.startswith(p) for p in prefixes_to_delete)]
                for k in keys_to_del:
                    del st.session_state[k]
                    deleted += 1

                # Also delete cannibalization DataFrame
                if "cannibalization" in st.session_state:
                    del st.session_state["cannibalization"]
                    deleted += 1

                # Delete from disk
                disk_deleted = 0
                if os.path.isdir(AI_CACHE_DIR):
                    for f in os.listdir(AI_CACHE_DIR):
                        if any(f.startswith(p) for p in prefixes_to_delete):
                            try:
                                os.remove(os.path.join(AI_CACHE_DIR, f))
                                disk_deleted += 1
                            except Exception:
                                pass
                # Delete cannibalization from disk
                cannibal_path = os.path.join("/data", "cannibalization.json")
                if os.path.exists(cannibal_path):
                    try:
                        os.remove(cannibal_path)
                        disk_deleted += 1
                    except Exception:
                        pass

                st.success(f"🗑 Reset done: {deleted} session keys + {disk_deleted} disk files deleted. Now: re-scrape (force all) → step 7 → 8 → 9 → 10 → 11.")
                st.rerun()

        st.markdown("---")

    # ── ONE-CLICK: Refresh all analyses ────────────────────
    if "audit_results" in st.session_state:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(
                "<div style='font-size:0.85rem; color:#c8b4ff; background:#12121f; border:2px solid #5533ff; border-radius:6px; padding:0.8rem;'>"
                "<strong>🔄 Refresh ALL analyses (one click)</strong><br>"
                "Runs everything in order: fix editorial text → re-classify pages → "
                "reset quality scores → re-run quality check (all pages) → re-run cannibalization. "
                "No re-scrape needed. Takes 5-15 min depending on number of pages.</div>",
                unsafe_allow_html=True,
            )
        existing_q = sum(1 for k in st.session_state if k.startswith("_quality_"))
        force_reset = st.checkbox("Force reset ALL quality scores (otherwise resumes from crash)", key="rp_force_quality_reset")
        if force_reset:
            st.session_state["_refresh_force_reset"] = True
        if existing_q > 0 and not force_reset:
            st.caption(f"ℹ {existing_q} quality scores exist — will resume, not restart")
        with col2:
            if st.button("🔄 Refresh all", key="rp_refresh_all", use_container_width=True, type="primary"):
                import re as _re
                import os
                from utils.category_analyzer import classify_page_type
                from utils.persistence import AI_CACHE_DIR

                results = st.session_state["audit_results"]
                progress = st.progress(0)
                status = st.empty()

                # Step 1: Fix editorial text
                status.text("Step 1/5: Fixing editorial text separation...")
                fixed_ed = 0
                for r in results:
                    if r.get("intro_text") or r.get("bottom_text"):
                        continue
                    body = r.get("body_text", "")
                    if not body or len(body) < 100:
                        continue
                    lines = body.split(". ")
                    intro_lines, bottom_lines = [], []
                    found_grid = False
                    for line in lines:
                        ls = line.strip()
                        if not ls:
                            continue
                        has_price = bool(_re.search(r'\d+\s*kr|\d+:-|rea\s|pris:', ls.lower()))
                        is_short = len(ls.split()) < 8
                        if has_price and is_short:
                            found_grid = True
                            continue
                        if not found_grid:
                            intro_lines.append(ls)
                        elif len(ls.split()) >= 10 and not has_price:
                            bottom_lines.append(ls)
                    intro = ". ".join(intro_lines).strip()
                    bottom = ". ".join(bottom_lines).strip()
                    if intro or bottom:
                        r["intro_text"] = intro[:5000]
                        r["intro_word_count"] = len(intro.split()) if intro else 0
                        r["bottom_text"] = bottom[:25000]
                        r["bottom_word_count"] = len(bottom.split()) if bottom else 0
                        r["total_editorial_words"] = r["intro_word_count"] + r["bottom_word_count"]
                        fixed_ed += 1
                progress.progress(0.1)

                # Step 2: Re-classify
                status.text("Step 2/5: Re-classifying pages...")
                changed = 0
                for r in results:
                    old_type = r.get("page_type", "unknown")
                    new_class = classify_page_type(r.get("url", ""), r)
                    new_type = new_class.get("page_type", "unknown")
                    if new_type != old_type:
                        r["page_type"] = new_type
                        changed += 1
                save_key("audit_results")
                progress.progress(0.2)

                # Step 3: Reset quality scores — BUT only if not resuming from crash
                # Check if we're resuming (some quality scores already exist from this session)
                existing_quality = sum(1 for k in st.session_state if k.startswith("_quality_"))
                force_reset = st.session_state.get("_refresh_force_reset", False)

                if existing_quality == 0 or force_reset:
                    status.text("Step 3/5: Clearing old quality scores...")
                    keys_del = [k for k in st.session_state if k.startswith("_quality_")]
                    for k in keys_del:
                        del st.session_state[k]
                    if os.path.isdir(AI_CACHE_DIR):
                        for f in os.listdir(AI_CACHE_DIR):
                            if f.startswith("_quality_"):
                                try:
                                    os.remove(os.path.join(AI_CACHE_DIR, f))
                                except Exception:
                                    pass
                    st.session_state["_refresh_force_reset"] = False
                else:
                    status.text(f"Step 3/5: Resuming — keeping {existing_quality} existing quality scores...")
                    keys_del = []  # Nothing deleted
                progress.progress(0.3)

                # Step 4: Re-run quality check (all pages, crash-safe)
                status.text("Step 4/5: AI quality check (this takes a few minutes)...")
                try:
                    total_checked = 0
                    while True:
                        _run_quality_check()  # Does 50 pages, saves each to disk
                        total_checked += 50
                        remaining = sum(1 for r in results
                                       if r.get("page_type") in ("category", "blog", "faq")
                                       and r.get("word_count", 0) > 50
                                       and f"_quality_{stable_hash(r['url'])}" not in st.session_state)
                        pct = 0.3 + (0.5 * (1 - remaining / max(1, remaining + total_checked)))
                        progress.progress(min(0.8, pct))
                        status.text(f"Step 4/5: AI quality check... {total_checked} done, {remaining} remaining")
                        if remaining == 0:
                            break
                except Exception as e:
                    # Quality check crashed — but all completed pages are already saved to disk.
                    # User can click Refresh All again to continue from where it stopped.
                    status.text(f"Quality check paused at {total_checked}: {e}")
                    st.warning(f"⚠ Quality check stopped at {total_checked} pages ({e}). Already-checked pages are saved. Click Refresh All again to continue.")
                progress.progress(0.85)

                # Step 5: Re-run cannibalization (uses whatever quality data exists)
                status.text("Step 5/5: Cannibalization detection...")
                try:
                    _run_cannibalization()
                    save_key("cannibalization")
                except Exception as e:
                    status.text(f"Cannibalization: {e}")
                progress.progress(1.0)

                status.empty()
                progress.empty()
                import datetime
                st.session_state["_refresh_all_result"] = {
                    "editorial": fixed_ed,
                    "reclassified": changed,
                    "quality_reset": len(keys_del),
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
                st.rerun()

        # Show last refresh result (persists across reruns)
        last_refresh = st.session_state.get("_refresh_all_result")
        if last_refresh:
            st.markdown(
                f"<div style='background:#0d2210; border:1px solid #33dd88; border-radius:6px; padding:0.8rem; margin:0.5rem 0;'>"
                f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#33dd88;'>LAST REFRESH: {last_refresh['timestamp']}</div>"
                f"<div style='font-size:0.85rem; color:#e8e8f0;'>"
                f"Editorial: {last_refresh['editorial']} fixed · "
                f"Re-classified: {last_refresh['reclassified']} pages · "
                f"Quality: {last_refresh['quality_reset']} re-checked · "
                f"Cannibalization: refreshed</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown("---")

    # Re-classify all audit results without re-scraping
    if "audit_results" in st.session_state:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(
                "<div style='font-size:0.85rem; color:#9b9bb8;'>"
                "<strong>Re-classify all pages</strong><br>"
                "Run new page type classifier on existing audit data without re-scraping. "
                "Use this after fixing classification rules.</div>",
                unsafe_allow_html=True,
            )
        with col2:
            if st.button("Re-classify", key="rp_reclassify", use_container_width=True):
                from utils.category_analyzer import classify_page_type
                results = st.session_state["audit_results"]
                changed = 0
                for r in results:
                    old_type = r.get("page_type", "unknown")
                    new_class = classify_page_type(r.get("url", ""), r)
                    new_type = new_class.get("page_type", "unknown")
                    if new_type != old_type:
                        r["page_type"] = new_type
                        changed += 1
                save_key("audit_results")
                st.success(f"Re-classified {changed}/{len(results)} pages")
                st.rerun()

        # Fix editorial text separation on existing data (no re-scrape needed)
        col1, col2 = st.columns([3, 1])
        missing_editorial = sum(1 for r in st.session_state.get("audit_results", [])
                                if not r.get("intro_text") and not r.get("bottom_text") and r.get("word_count", 0) > 100)
        with col1:
            st.markdown(
                f"<div style='font-size:0.85rem; color:#9b9bb8;'>"
                f"<strong>Fix editorial text ({missing_editorial} pages missing)</strong><br>"
                f"Separates intro + bottom text from product grid in existing audit data. "
                f"No re-scrape needed — parses stored body_text to extract editorial content only.</div>",
                unsafe_allow_html=True,
            )
        with col2:
            if st.button("Fix editorial", key="rp_fix_editorial", use_container_width=True):
                import re as _re
                results = st.session_state["audit_results"]
                fixed = 0
                for r in results:
                    if r.get("intro_text") or r.get("bottom_text"):
                        continue  # already has editorial separation
                    body = r.get("body_text", "")
                    if not body or len(body) < 100:
                        continue

                    # Split body at price/product patterns
                    # Product grid lines typically contain: "XXX kr", "Rea", "Köp", repeated price patterns
                    lines = body.split(". ")
                    intro_lines = []
                    bottom_lines = []
                    found_grid = False

                    for line in lines:
                        line_stripped = line.strip()
                        if not line_stripped:
                            continue
                        # Detect product grid content: price patterns, short fragments
                        has_price = bool(_re.search(r'\d+\s*kr|\d+:-|rea\s|pris:', line_stripped.lower()))
                        is_short_fragment = len(line_stripped.split()) < 8
                        if has_price and is_short_fragment:
                            found_grid = True
                            continue  # skip product grid content
                        if not found_grid:
                            intro_lines.append(line_stripped)
                        else:
                            # After grid: only keep substantial paragraphs (not more price fragments)
                            if len(line_stripped.split()) >= 10 and not has_price:
                                bottom_lines.append(line_stripped)

                    intro = ". ".join(intro_lines).strip()
                    bottom = ". ".join(bottom_lines).strip()

                    if intro or bottom:
                        r["intro_text"] = intro[:3000]
                        r["intro_word_count"] = len(intro.split()) if intro else 0
                        r["bottom_text"] = bottom[:3000]
                        r["bottom_word_count"] = len(bottom.split()) if bottom else 0
                        r["total_editorial_words"] = r["intro_word_count"] + r["bottom_word_count"]
                        fixed += 1

                save_key("audit_results")
                st.success(f"Fixed editorial text on {fixed} pages. Run Step 7 + Step 8 to see corrected quality scores.")
                st.rerun()

        # Re-scrape + re-classify category pages (picks up new HTML signals)
        col1, col2 = st.columns([3, 1])
        # Re-scrape all CONTENT pages (not just categories — blogs, FAQ, guides also have editorial text)
        _rescrape_types = ("category", "blog", "faq", "info")
        category_pages = [r for r in st.session_state.get("audit_results", []) if r.get("page_type") in _rescrape_types]
        with col1:
            st.markdown(
                f"<div style='font-size:0.85rem; color:#9b9bb8;'>"
                f"<strong>Re-scrape all content pages ({len(category_pages)})</strong><br>"
                f"Re-downloads HTML for all categories, blogs, FAQ, and guides. "
                f"Re-extracts editorial text (intro + bottom) with latest parser. "
                f"Saves every 25 pages. Skips pages with full text unless Force is checked.</div>",
                unsafe_allow_html=True,
            )
        force_all = st.checkbox("Force re-scrape ALL (ignore cached text)", key="rp_force_rescrape")
        with col2:
            if st.button(f"Re-scrape {len(category_pages)}", key="rp_rescrape_cats", use_container_width=True):
                from utils.page_scraper import scrape_page, reset_playwright
                from utils.category_analyzer import classify_page_type
                # Reset Playwright so it gets a fresh chance (may have crashed in prior run)
                reset_playwright()
                from utils.persistence import save
                results = st.session_state["audit_results"]
                progress = st.progress(0)
                changed = 0
                errors = 0
                scraped = 0
                log_lines = []
                status_text = st.empty()
                cat_indices = [i for i, r in enumerate(results) if r.get("page_type") in _rescrape_types]
                total_cats = len(cat_indices)
                skipped = 0
                for idx_num, i in enumerate(cat_indices):
                    r = results[i]
                    url = r.get("url", "")
                    short = url.split("/")[-1][:40] if "/" in url else url[:40]

                    # Skip pages that already have full editorial text (from prior run)
                    existing_bottom = len(r.get("bottom_text", "") or "")
                    if existing_bottom > 500 and not force_all:
                        skipped += 1
                        progress.progress(min(1.0, (idx_num + 1) / max(1, total_cats)))
                        continue

                    status_text.text(f"[{idx_num+1}/{total_cats}] {short}... ({skipped} skipped)")
                    try:
                        page_data = scrape_page(url, timeout=12)
                        scraped += 1
                        # Extract key signals
                        tmpl = page_data.get("template_type", "")
                        accordion = page_data.get("has_accordion_product", False)
                        breadcrumb = page_data.get("has_breadcrumb_schema", False)
                        body_cls = page_data.get("body_classes", "")
                        schemas = page_data.get("schema_types", [])
                        scraper_used = page_data.get("_scraper", "?")

                        # DIRECT Magento body class override (strongest signal, works without JS)
                        is_product_by_body = "catalog-product-view" in body_cls or "product-view" in body_cls
                        is_product_by_accordion = accordion
                        is_product_by_schema = any("product" in str(s).lower() for s in schemas) and not any("itemlist" in str(s).lower() for s in schemas)

                        if page_data.get("success") or page_data.get("title"):
                            # Copy ALL useful fields from fresh scrape to audit_results
                            for key in ("template_type", "has_accordion_product",
                                        "has_breadcrumb_schema", "body_classes",
                                        "schema_types", "product_count",
                                        "body_text", "word_count",
                                        "intro_text", "intro_word_count",
                                        "bottom_text", "bottom_word_count",
                                        "total_editorial_words",
                                        "title", "meta_description", "h1", "h2s",
                                        "internal_links", "images_without_alt"):
                                if key in page_data:
                                    r[key] = page_data[key]

                            # Force product if ANY definitive signal detected
                            if is_product_by_body or is_product_by_accordion or is_product_by_schema:
                                if r["page_type"] == "category":
                                    reason = []
                                    if is_product_by_body: reason.append("body class")
                                    if is_product_by_accordion: reason.append("accordion")
                                    if is_product_by_schema: reason.append("schema")
                                    r["page_type"] = "product"
                                    r["_reclassified_from"] = "category"
                                    r["_reclassified_signals"] = reason
                                    changed += 1
                                    log_lines.append(f"✓ {short} → product ({', '.join(reason)})")
                            else:
                                # Run classifier for other possible reclassifications
                                new_class = classify_page_type(url, {**r, **page_data})
                                new_type = new_class.get("page_type", "unknown")
                                if new_type != "category":
                                    r["page_type"] = new_type
                                    r["_reclassified_from"] = "category"
                                    r["_reclassified_signals"] = new_class.get("signals", [])
                                    changed += 1
                                    log_lines.append(f"✓ {short} → {new_type}")

                            # Log first 20 pages for diagnostics
                            if idx_num < 20 and not any(short in l for l in log_lines):
                                log_lines.append(
                                    f"  {short}: tmpl={tmpl} accordion={accordion} "
                                    f"breadcrumb={breadcrumb} body_cls={body_cls[:30]} "
                                    f"schemas={schemas[:3]} scraper={scraper_used} → stays category"
                                )
                        else:
                            errors += 1
                            if idx_num < 10:
                                log_lines.append(f"✗ {short}: scrape failed ({scraper_used})")
                    except Exception as e:
                        errors += 1
                        if idx_num < 10:
                            log_lines.append(f"✗ {short}: error {str(e)[:60]}")
                    progress.progress(min(1.0, (idx_num + 1) / max(1, total_cats)))
                    # Save every 25 pages so a crash doesn't lose progress
                    if scraped > 0 and scraped % 25 == 0:
                        save_key("audit_results")
                save_key("audit_results")
                status_text.empty()
                progress.empty()

                # Show results WITHOUT st.rerun() so user can see diagnostics
                st.success(f"Re-scraped {scraped}/{total_cats} category pages → **{changed} reclassified** to product. {skipped} skipped (already had full text). {errors} errors.")
                if log_lines:
                    with st.expander(f"Diagnostic log ({len(log_lines)} entries)", expanded=True):
                        st.code("\n".join(log_lines[:50]), language="text")

        # Reset + re-run ALL quality checks (with new detection rules)
        col1, col2 = st.columns([3, 1])
        with col1:
            # Count existing quality checks
            existing_quality = sum(1 for k in st.session_state if k.startswith("_quality_"))
            st.markdown(
                f"<div style='font-size:0.85rem; color:#9b9bb8;'>"
                f"<strong>Reset + re-run ALL quality checks ({existing_quality} existing)</strong><br>"
                f"Clears all cached quality scores and re-evaluates every page with latest "
                f"detection rules (keyword stuffing, generic text, E-E-A-T). "
                f"Then automatically re-runs Step 5 (Cannibalization) so all data is fresh.</div>",
                unsafe_allow_html=True,
            )
        with col2:
            if st.button("Reset & re-run", key="rp_reset_quality", use_container_width=True):
                # 1. Delete all cached quality scores
                keys_to_delete = [k for k in st.session_state if k.startswith("_quality_")]
                for k in keys_to_delete:
                    del st.session_state[k]
                # Also delete from disk
                import os
                from utils.persistence import AI_CACHE_DIR
                if os.path.isdir(AI_CACHE_DIR):
                    for f in os.listdir(AI_CACHE_DIR):
                        if f.startswith("_quality_"):
                            try:
                                os.remove(os.path.join(AI_CACHE_DIR, f))
                            except Exception:
                                pass
                st.success(f"Cleared {len(keys_to_delete)} quality scores. Now run Step 7 (Quality Check) to re-evaluate, then Step 8 (Cannibalization).")
                st.rerun()

    # ── Export pipeline state ────────────────────────────────
    st.markdown("---")
    st.markdown("### 📋 Export pipeline state")
    st.markdown(
        "<p style='color:#9b9bb8; font-size:0.85rem;'>"
        "Compact text dump of all pipeline results for sharing or AI review.</p>",
        unsafe_allow_html=True,
    )
    if st.button("Generate export", key="rp_export_state", use_container_width=False):
        import json as _json
        lines = ["# Pipeline State Export", ""]

        # GSC + crawl basics
        gsc = st.session_state.get("gsc_data")
        if gsc is not None and hasattr(gsc, "shape"):
            lines.append(f"**GSC:** {len(gsc):,} query/page rows · {gsc['page'].nunique() if 'page' in gsc.columns else '?'} unique pages")
        auth = st.session_state.get("page_authority")
        if auth is not None and hasattr(auth, "shape"):
            lines.append(f"**Authority:** {len(auth):,} pages with backlink data")
        sf = st.session_state.get("sf_crawl_issues") or {}
        if isinstance(sf, dict):
            lines.append(f"**Crawl issues:** " + ", ".join(f"{k}={len(v) if hasattr(v,'__len__') else v}" for k, v in sf.items()))
        ctr = st.session_state.get("ctr_gaps")
        if ctr is not None and hasattr(ctr, "shape") and not ctr.empty:
            lines.append(f"**CTR gaps:** {len(ctr):,} rows")
            top_ctr = ctr.sort_values("lost_clicks_estimate", ascending=False).head(10)
            lines.append("\n**Top 10 CTR gap pages (most lost clicks):**")
            for _, r in top_ctr.iterrows():
                lines.append(f"- `{r.get('page','')}` · q='{r.get('query','')}' · pos {r.get('position',0):.1f} · lost {int(r.get('lost_clicks_estimate',0))}")
        cann = st.session_state.get("cannibalization")
        if cann is not None and hasattr(cann, "shape") and not cann.empty:
            severe = len(cann[cann["severity"] == "severe"]) if "severity" in cann.columns else 0
            moderate = len(cann[cann["severity"] == "moderate"]) if "severity" in cann.columns else 0
            lines.append(f"\n**Cannibalization:** {severe} severe, {moderate} moderate")
        else:
            lines.append("\n**Cannibalization:** NOT RUN")

        # Topic clusters
        tc = st.session_state.get("topic_clusters", {})
        if isinstance(tc, dict):
            lines.append(f"\n**Topic clusters:** {len(tc.get('clusters', []))}")
            top_clusters = sorted(tc.get("clusters", []), key=lambda c: -c.get("total_impressions", 0))[:10]
            lines.append("\n**Top 10 clusters by impressions:**")
            for c in top_clusters:
                lines.append(f"- {c.get('topic','?')}: {c.get('query_count',0)} queries · {c.get('total_impressions',0):,} impr · {c.get('total_clicks',0):,} cl · {c.get('page_count',0)} pages")

        # Content gaps
        gaps = st.session_state.get("content_gaps", []) or []
        if gaps:
            lines.append(f"\n**Content gaps:** {len(gaps)}")
            high = [g for g in gaps if g.get("priority") == "high"]
            lines.append(f"  - High: {len(high)}")
            for g in high[:5]:
                lines.append(f"    - {g.get('topic','?')}: " + " | ".join(g.get('issues', [])))

        # Site validation
        sv = st.session_state.get("_site_validation", {})
        if isinstance(sv, dict) and sv:
            lines.append(f"\n## Site Validation (score {sv.get('overall_health_score','?')}/100)")
            comp = sv.get("_score_components", {})
            if comp:
                lines.append(f"_Score components: {_json.dumps(comp)}_")
            lines.append(f"Summary: {sv.get('summary','')}")
            lines.append(f"\n**Critical issues:**")
            for x in sv.get("critical_issues", []):
                lines.append(f"- {x}")
            lines.append(f"\n**Structural problems:**")
            for x in sv.get("structural_problems", []):
                lines.append(f"- {x}")
            lines.append(f"\n**Cluster issues:**")
            for x in sv.get("cluster_issues", []):
                lines.append(f"- {x}")
            lines.append(f"\n**Opportunities:**")
            for x in sv.get("opportunities", []):
                lines.append(f"- {x}")
            lines.append(f"\n**Priority actions:**")
            for a in sv.get("priority_actions", []):
                if isinstance(a, dict):
                    lines.append(f"- [{a.get('impact','?')}] {a.get('action','')} ({a.get('pages_affected','?')} pages)")
                else:
                    lines.append(f"- {a}")

        # Ideal structure
        ideal = st.session_state.get("_ideal_structure", {})
        if isinstance(ideal, dict) and ideal:
            lines.append(f"\n## Ideal Structure")
            lines.append(f"{len(ideal.get('clusters', []))} clusters · {len(ideal.get('merge', []))} merges · {len(ideal.get('delete', []))} deletes · {len(ideal.get('create', []))} creates")
            lines.append(f"Estimated new score: {ideal.get('estimated_new_score','?')}/100")
            lines.append(f"Summary: {ideal.get('summary','')}")
            if ideal.get("merge"):
                lines.append(f"\n**Merges:**")
                for m in ideal.get("merge", [])[:10]:
                    lines.append(f"- {m.get('from',[])} → {m.get('to','')} ({m.get('why','')[:80]})")
            if ideal.get("delete"):
                lines.append(f"\n**Deletes:**")
                for d in ideal.get("delete", [])[:10]:
                    lines.append(f"- {d.get('url','')}: {d.get('why','')[:80]}")
            if ideal.get("create"):
                lines.append(f"\n**Creates:**")
                for c in ideal.get("create", [])[:10]:
                    lines.append(f"- {c.get('url','')} ({c.get('type','')}, kw={c.get('kw','')}): {c.get('why','')[:80]}")

        # Gap analysis
        ga = st.session_state.get("_gap_analysis", {})
        if isinstance(ga, dict) and ga.get("phases"):
            lines.append(f"\n## Gap Analysis ({ga.get('total_weeks','?')} weeks total)")
            for ph in ga.get("phases", []):
                lines.append(f"\n**Phase {ph.get('phase','?')}: {ph.get('name','')}** ({ph.get('duration_weeks','?')}w, risk {ph.get('risk','?')})")
                for a in ph.get("actions", []):
                    lines.append(f"- {a}")
            if ga.get("risks"):
                lines.append(f"\n**Risks:**")
                for r in ga.get("risks", []):
                    lines.append(f"- {r}")
            if ga.get("success_metrics"):
                lines.append(f"\n**Success metrics:**")
                for m in ga.get("success_metrics", []):
                    lines.append(f"- {m}")

        # Plan validation
        pv = st.session_state.get("_plan_validation", {})
        if isinstance(pv, dict) and pv:
            lines.append(f"\n## Plan Validation (coverage {pv.get('coverage_score','?')}/100, confidence {pv.get('confidence','?')}/100)")
            lines.append(f"Verdict: {pv.get('overall_verdict','')}")
            if pv.get("uncovered_issues"):
                lines.append(f"\n**Uncovered issues:**")
                for x in pv.get("uncovered_issues", []):
                    lines.append(f"- {x}")
            if pv.get("missing_actions"):
                lines.append(f"\n**Missing actions:**")
                for x in pv.get("missing_actions", []):
                    lines.append(f"- {x}")
            if pv.get("conflicts"):
                lines.append(f"\n**Conflicts:**")
                for c in pv.get("conflicts", []):
                    if isinstance(c, dict):
                        lines.append(f"- {c.get('plan_a','')} ↔ {c.get('plan_b','')}: {c.get('conflict','')}")
            if pv.get("risks"):
                lines.append(f"\n**Risks:**")
                for r in pv.get("risks", []):
                    lines.append(f"- {r}")

        # Page type breakdown from audit
        ar = st.session_state.get("audit_results", [])
        if ar:
            from collections import Counter
            types = Counter(r.get("page_type", "unknown") for r in ar)
            lines.append(f"\n## Audit ({len(ar)} pages)")
            lines.append("Page types: " + ", ".join(f"{k}={v}" for k, v in types.most_common()))
            wcs = [r.get("word_count", 0) for r in ar]
            if wcs:
                thin_count = sum(1 for w in wcs if w < 300)
                lines.append(f"Thin pages (<300 words): {thin_count}")

        export_text = "\n".join(lines)
        st.code(export_text, language="markdown")
        st.download_button(
            "Download as .md",
            export_text,
            file_name="pipeline_state.md",
            mime="text/markdown",
        )

    # ── Cache Status ────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 💾 Cache Status")
    from utils.persistence import get_storage_info, _volume_available, AI_CACHE_DIR
    import os
    if not _volume_available():
        st.warning("⚠ No persistent volume mounted (/data missing). Running locally — nothing is cached to disk.")
    else:
        info = get_storage_info()
        ai_info = info.get("files", {}).get("ai_cache", {})
        total_mb = info.get("total_mb", 0)

        # Count AI cache files by prefix
        prefix_counts = {}
        if os.path.isdir(AI_CACHE_DIR):
            for fname in os.listdir(AI_CACHE_DIR):
                if not fname.endswith(".json"):
                    continue
                key = fname[:-5]
                prefix = "other"
                for p in ("_cluster_health_", "_quality_", "_ai_plan_", "_bottom_text_",
                          "_intro_text_", "_site_validation", "_ideal_structure",
                          "_gap_analysis", "_plan_validation", "_kw_filter_"):
                    if key.startswith(p):
                        prefix = p.rstrip("_")
                        break
                prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1

        col1, col2 = st.columns([3, 1])
        with col1:
            lines = [f"**Total on disk:** {total_mb} MB · **AI cache files:** {ai_info.get('count', 0)}"]
            if prefix_counts:
                lines.append("")
                lines.append("**AI cache breakdown:**")
                for p, c in sorted(prefix_counts.items(), key=lambda x: -x[1]):
                    lines.append(f"- `{p}` — {c} file(s)")
            st.markdown("\n".join(lines))
        with col2:
            if st.button("Force save all", key="rp_force_save", use_container_width=True):
                from utils.persistence import save_all
                save_all()
                st.success("All in-memory state saved to disk")
                st.rerun()

    st.markdown("---")
    st.markdown(
        "<div style='background:#0d0d15; border:1px solid #5533ff; border-radius:6px; padding:0.8rem;'>"
        "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#5533ff; margin-bottom:0.3rem;'>NEXT</div>"
        "<div style='font-size:0.85rem; color:#c8b4ff;'>Once all steps are done, go to <strong>🎯 Action Center</strong> "
        "to see prioritized recommendations and generate content.</div>"
        "</div>",
        unsafe_allow_html=True,
    )
