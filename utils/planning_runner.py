"""Phase-4 AI planning steps — framework-free port of the run_pipeline funcs.

Ports _run_site_validation / _run_ideal_structure / _run_gap_analysis /
_run_plan_validation out of the Streamlit view into shared logic: read state(),
call Claude, write the _-prefixed AI-cache keys. Faithful to the proven
Streamlit versions (same prompts, same deterministic scoring, same
hallucination filter) — only the state accessor changed. No st.* here.

These make Phase 4 of the NiceGUI flow runnable. The heavy AI calls can only
be fully validated against a live run (API key + real audit/cluster data);
the non-AI parts (structure, scoring, URL filtering, plan collection) are
unit-testable with synthetic state.
"""

from __future__ import annotations

import json

from utils.state import state
from utils.progress import Progress, NULL


def _client():
    from config import get_anthropic_key, has_anthropic_key
    from utils.ai_generator import get_client
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    return get_client(get_anthropic_key())


def _save_ai(key, value):
    from utils.persistence import _save_ai_key, _volume_available
    state()[key] = value
    if _volume_available():
        _save_ai_key(key, value)


# ── Step 10: Site validation ─────────────────────────────────────────

def run_site_validation(client=None, progress: Progress = NULL) -> dict:
    from utils.ai_generator import _parse_ai_json, DEFAULT_MODEL
    from utils.site_structure import build_site_structure
    s = state()
    if "audit_results" not in s:
        raise ValueError("Run bulk audit first")
    if "topic_clusters" not in s:
        raise ValueError("Run topic clusters first")

    audit_results = s["audit_results"]
    gsc_data = s.get("gsc_data")
    topic_clusters = s.get("topic_clusters", {})
    page_authority = s.get("page_authority")

    df_structure = build_site_structure(audit_results, gsc_data, topic_clusters, page_authority)
    if df_structure.empty:
        raise ValueError("No site structure data")

    # Prefer SF's real orphan list; else derive from Links In == 0.
    sf_issues = s.get("sf_crawl_issues") or {}
    sf_orphans = sf_issues.get("orphan_pages") or []
    if isinstance(sf_orphans, list) and len(sf_orphans) > 0:
        orphans = len(sf_orphans)
    else:
        orphans = len(df_structure[df_structure["Links In"] == 0]) if "Links In" in df_structure.columns else 0
    no_cluster = len(df_structure[df_structure["Cluster(s)"] == ""]) if "Cluster(s)" in df_structure.columns else 0
    if "Word Count" in df_structure.columns and "Page Type" in df_structure.columns:
        thin = len(df_structure[
            (df_structure["Word Count"] > 0)
            & (df_structure["Word Count"] < 300)
            & (df_structure["Page Type"] != "product")
        ])
    elif "Word Count" in df_structure.columns:
        thin = len(df_structure[(df_structure["Word Count"] > 0) & (df_structure["Word Count"] < 300)])
    else:
        thin = 0

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

    total = max(1, summary["total_pages"])
    orphan_pct = orphans / total * 100
    no_cluster_pct = no_cluster / total * 100
    thin_pct = thin / total * 100

    health = 100
    health -= min(40, orphan_pct * 1.0)
    health -= min(30, no_cluster_pct * 0.6)
    health -= min(20, thin_pct * 0.4)
    if summary["total_clusters"] < 10:
        health -= 10
    deterministic_score = max(0, min(100, int(round(health))))

    client = client or _client()
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

    with progress.spinner("AI reviewing site structure…"):
        message = client.messages.create(
            model=DEFAULT_MODEL, max_tokens=3000, temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
    result = _parse_ai_json(message)
    if isinstance(result, dict):
        result["overall_health_score"] = deterministic_score
        result["_score_components"] = {
            "orphan_pct": round(orphan_pct, 1),
            "no_cluster_pct": round(no_cluster_pct, 1),
            "thin_pct": round(thin_pct, 1),
            "cluster_count": summary["total_clusters"],
        }
    _save_ai("_site_validation", result)
    return result


# ── Step 11: Ideal structure ─────────────────────────────────────────

def run_ideal_structure(client=None, progress: Progress = NULL) -> dict:
    from utils.ai_generator import _parse_ai_json, DEFAULT_MODEL
    from utils.ui_helpers import normalize_url as _nu
    s = state()
    if "_site_validation" not in s:
        raise ValueError("Run site validation first")
    if "topic_clusters" not in s:
        raise ValueError("Run topic clusters first")

    client = client or _client()
    site_ctx = s.get("site_context", "")
    site_issues = s.get("_site_validation", {})
    topic_clusters = s.get("topic_clusters", {})
    gsc_data = s.get("gsc_data")
    audit_results = s.get("audit_results", [])

    kw_lines = []
    if gsc_data is not None and hasattr(gsc_data, "groupby"):
        kw_summary = gsc_data.groupby("query").agg(
            impressions=("impressions", "sum"), clicks=("clicks", "sum"),
        ).sort_values("impressions", ascending=False).head(80)
        for kw, row in kw_summary.iterrows():
            kw_lines.append(f"{kw}: {int(row['impressions'])} impr, {int(row['clicks'])} cl")
    kw_text = chr(10).join(kw_lines)

    current_clusters_text = chr(10).join(
        f"- {c.get('topic', '')}: {c.get('query_count', 0)} queries, {c.get('total_impressions', 0)} impr"
        for c in topic_clusters.get("clusters", [])[:20]
    )
    issues_text = chr(10).join(site_issues.get("critical_issues", [])[:5])

    real_urls = sorted({_nu(r.get("url", "")) for r in audit_results if r.get("url")})
    site_origin = (s.get("gsc_site") or "").rstrip("/")
    real_paths = []
    for u in real_urls:
        p = u
        if site_origin and p.startswith(site_origin):
            p = p[len(site_origin):] or "/"
        real_paths.append(p)
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

    with progress.spinner("AI designing ideal clusters…"):
        msg1 = client.messages.create(
            model=DEFAULT_MODEL, max_tokens=8000, temperature=0,
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
        raw = msg1.content[0].text if msg1.content else ""
        stop_reason = getattr(msg1, 'stop_reason', 'unknown')
        raise ValueError(
            f"Cluster design call failed to return valid JSON. Stop reason: {stop_reason}. "
            f"Response length: {len(raw)} chars. "
            f"{'TRUNCATED — increase max_tokens or reduce cluster count.' if stop_reason == 'max_tokens' else ''} "
            f"First 300 chars: {raw[:300]}"
        ) from e

    cluster_names = [c.get("name", "") for c in clusters_result.get("clusters", [])]
    with progress.spinner("AI planning merges / deletes / new pages…"):
        msg2 = client.messages.create(
            model=DEFAULT_MODEL, max_tokens=6000, temperature=0,
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
            f"Merge/delete/create call failed to return valid JSON. Stop reason: {stop_reason}. "
            f"Length: {len(raw)} chars. "
            f"{'TRUNCATED — bump max_tokens.' if stop_reason == 'max_tokens' else ''} "
            f"First 300 chars: {raw[:300]}"
        ) from e

    with progress.spinner("AI summarizing the plan…"):
        msg3 = client.messages.create(
            model=DEFAULT_MODEL, max_tokens=3000, temperature=0,
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
        stop_reason = getattr(msg3, 'stop_reason', 'unknown')
        print(f"[ideal_structure] Call 3 summary failed ({stop_reason}): {e}")
        summary_result = {"keyword_assignments": [], "estimated_new_score": 0,
                          "summary": f"(Summary call failed: {stop_reason})"}

    real_path_set = set(real_paths)

    def _is_real(url: str) -> bool:
        if not url:
            return False
        u = str(url).strip()
        if site_origin and u.startswith(site_origin):
            u = u[len(site_origin):] or "/"
        return u in real_path_set

    hallucinated = {"clusters_hub": 0, "clusters_spokes": 0, "merge_from": 0, "merge_to": 0, "delete": 0}

    clean_clusters = []
    for c in clusters_result.get("clusters", []):
        if not isinstance(c, dict):
            continue
        hub = c.get("hub", "")
        if hub and not _is_real(hub):
            hallucinated["clusters_hub"] += 1
            continue
        clean_spokes = []
        for sp in c.get("spokes", []) or []:
            if _is_real(sp):
                clean_spokes.append(sp)
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
    _save_ai("_ideal_structure", combined)
    return combined


# ── Step 12: Migration / gap plan ────────────────────────────────────

def run_gap_analysis(client=None, progress: Progress = NULL) -> dict:
    from utils.ai_generator import _parse_ai_json, DEFAULT_MODEL
    s = state()
    if "_ideal_structure" not in s:
        raise ValueError("Run ideal structure first")
    if "_site_validation" not in s:
        raise ValueError("Run site validation first")

    client = client or _client()
    site_val = s.get("_site_validation", {})
    ideal = s.get("_ideal_structure", {})
    audit_results = s.get("audit_results", [])

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
    {{"phase": 1, "name": "Quick wins", "duration_weeks": 1, "actions": ["action 1"], "risk": "low/medium/high"}}
  ],
  "total_weeks": 0,
  "risks": ["risk 1"],
  "success_metrics": ["metric 1"]
}}"""

    with progress.spinner("AI building migration plan…"):
        message = client.messages.create(
            model=DEFAULT_MODEL, max_tokens=3000, temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
    result = _parse_ai_json(message)
    _save_ai("_gap_analysis", result)
    return result


# ── Step 13: Plan validation ─────────────────────────────────────────

def run_plan_validation(client=None, progress: Progress = NULL) -> dict:
    from utils.ai_generator import _parse_ai_json, DEFAULT_MODEL
    s = state()
    if "_site_validation" not in s:
        raise ValueError("Run site validation first")

    plans_data = {}
    for key, val in s.items():
        if key.startswith("_ai_plan_") and isinstance(val, dict) and not val.get("error"):
            url = val.get("url") or key
            plans_data[url] = val

    if len(plans_data) == 0:
        raise ValueError(
            "No per-page implementation plans exist yet to validate. Plans are "
            "created per page by Fix ALL, the per-page Generate-text button, or "
            "Quick Wins. Run one of those first. This step only REVIEWS existing plans."
        )

    client = client or _client()
    site_issues = s.get("_site_validation", {})
    ideal = s.get("_ideal_structure", {})

    plan_summaries = []
    for url, plan in list(plans_data.items())[:20]:
        steps_summary = [f"- [{stp.get('type','')}] {stp.get('action','')}" for stp in plan.get("steps", [])]
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

    with progress.spinner("AI validating the plans…"):
        message = client.messages.create(
            model=DEFAULT_MODEL, max_tokens=3000, temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
    result = _parse_ai_json(message)
    _save_ai("_plan_validation", result)
    return result
