"""
Cluster Health runner — shared logic for evaluating topic clusters.

Single source of truth for:
  - _build_cluster_data: gather all data for one cluster (hub, spokes,
    link map, cannibalization) ready for the AI call.
  - run_cluster_eval: run the full eval pipeline (build → AI → persist)
    with a defensive except that ALWAYS writes a structured payload to
    session_state so the UI never lands in 'NOT EVALUATED + Error: ...'
    inconsistent state.
  - run_all_clusters: pipeline entry point that evaluates every cluster
    (skipping cached ones) so per-page bulk AI text generation
    downstream has the full strategic review available.

Views and pipeline steps MUST import from here — never re-implement.
"""

import streamlit as st
from utils.url_helpers import url_segments as _url_segments
from utils.ui_helpers import stable_hash


def _build_cluster_data(cluster, audit_results, topic_clusters, gsc_data, sf_link_map=None):
    """Gather all data for a single cluster for AI evaluation."""
    from utils.page_profile import build_page_profile
    from utils.ui_helpers import normalize_url as _nu

    pages = cluster.get("pages", [])
    if not pages:
        return None

    # Defensive: skip cluster entries where 'page' isn't a string —
    # legacy/corrupted topic_clusters.json could carry dict-shaped values
    # that crash `set(page_urls)` below with "unhashable type: 'dict'".
    page_urls = [
        p["page"] for p in pages
        if isinstance(p, dict) and isinstance(p.get("page"), str) and p["page"]
    ]
    if not page_urls:
        return None
    hub_url = ""
    hub_depth = 999
    for pu in page_urls:
        depth = len(_url_segments(pu))
        if depth < hub_depth:
            hub_depth = depth
            hub_url = pu

    hub_profile = build_page_profile(hub_url)
    hub_content = (hub_profile["body_text"] or hub_profile["intro_text"] or "")[:500]
    hub_outlink_targets = {
        _nu(l["url"]) for l in hub_profile["internal_links_out"]
        if isinstance(l, dict) and isinstance(l.get("url"), str)
    }

    spokes = []
    spoke_keywords = {}
    spoke_profiles = {}
    hub_norm = _nu(hub_url)
    for purl in page_urls:
        if _nu(purl) == hub_norm:
            continue
        profile = build_page_profile(purl)
        spoke_profiles[purl] = profile
        p = next(
            (x for x in pages
             if isinstance(x, dict) and x.get("page") == purl),
            {}
        )
        spokes.append({
            "url": purl,
            "title": profile["title"][:80],
            "h1": profile["h1"][:80],
            "word_count": profile["word_count"],
            "page_type": profile["page_type"],
            "impressions": profile["total_impressions"] or p.get("total_impressions", 0),
            "clicks": profile["total_clicks"] or p.get("total_clicks", 0),
            "meta_score": profile["content_audit"].get("meta_score"),
            "content_score": profile["content_audit"].get("content_score"),
        })
        spoke_keywords[purl] = profile["content_audit"].get("target_keywords", [])[:8]

    cluster_urls = set(page_urls)

    hub_to_spoke = [s["url"] for s in spokes if _nu(s["url"]) in hub_outlink_targets]

    spoke_to_hub = []
    for s in spokes:
        sp = spoke_profiles[s["url"]]
        spoke_outlink_targets = {
            _nu(l["url"]) for l in sp["internal_links_out"]
            if isinstance(l, dict) and isinstance(l.get("url"), str)
        }
        if _nu(hub_url) in spoke_outlink_targets:
            spoke_to_hub.append(s["url"])

    horizontal = []
    spoke_urls = [s["url"] for s in spokes]
    for s in spokes:
        sp = spoke_profiles[s["url"]]
        s_targets = {
            _nu(l["url"]) for l in sp["internal_links_out"]
            if isinstance(l, dict) and isinstance(l.get("url"), str)
        }
        for other in spoke_urls:
            if other != s["url"] and _nu(other) in s_targets:
                horizontal.append({"from": s["url"], "to": other})

    cannibalized = []
    if gsc_data is not None and not gsc_data.empty:
        cluster_urls_norm = set(_nu(u) for u in cluster_urls)
        cluster_gsc = gsc_data[gsc_data["page"].apply(_nu).isin(cluster_urls_norm)]
        if not cluster_gsc.empty:
            kw_pages = cluster_gsc.groupby("query")["page"].apply(list).to_dict()
            for kw, kw_pages_list in kw_pages.items():
                if len(set(kw_pages_list)) > 1:
                    cannibalized.append({
                        "keyword": kw,
                        "pages": list(set(kw_pages_list))[:3],
                    })
            cannibalized.sort(key=lambda x: -len(x["pages"]))
            cannibalized = cannibalized[:15]

    link_issues = []

    spokes_without_hub_link = [s["url"] for s in spokes if s["url"] not in hub_to_spoke]
    if spokes_without_hub_link:
        link_issues.append({
            "severity": "critical" if len(spokes_without_hub_link) > len(spokes) * 0.5 else "warn",
            "type": "hub_to_spoke_missing",
            "msg": f"Hub does NOT link to {len(spokes_without_hub_link)}/{len(spokes)} spoke pages. Hub must link down to all spokes.",
            "pages": spokes_without_hub_link[:10],
        })

    spokes_without_backlink = [s["url"] for s in spokes if s["url"] not in spoke_to_hub]
    if spokes_without_backlink:
        link_issues.append({
            "severity": "critical" if len(spokes_without_backlink) > len(spokes) * 0.5 else "warn",
            "type": "spoke_to_hub_missing",
            "msg": f"{len(spokes_without_backlink)}/{len(spokes)} spokes do NOT link back to hub. Every spoke must link to its pillar.",
            "pages": spokes_without_backlink[:10],
        })

    spoke_with_sibling_links = set()
    for h in horizontal:
        spoke_with_sibling_links.add(h["from"])
    isolated_spokes = [s["url"] for s in spokes if s["url"] not in spoke_with_sibling_links]
    if isolated_spokes and len(spokes) >= 3:
        link_issues.append({
            "severity": "warn",
            "type": "isolated_spokes",
            "msg": f"{len(isolated_spokes)}/{len(spokes)} spokes have no horizontal links to sibling pages.",
            "pages": isolated_spokes[:10],
        })

    return {
        "topic": cluster.get("topic", ""),
        "core_terms": cluster.get("core_terms", []),
        "query_count": cluster.get("query_count", 0),
        "total_impressions": cluster.get("total_impressions", 0),
        "total_clicks": cluster.get("total_clicks", 0),
        "hub_url": hub_url,
        "hub_title": hub_profile["title"][:80],
        "hub_h1": hub_profile["h1"][:80],
        "hub_word_count": hub_profile["word_count"],
        "hub_outlinks": len(hub_outlink_targets),
        "hub_content": hub_content,
        "hub_keywords": hub_profile["content_audit"].get("target_keywords", [])[:10],
        "spokes": spokes,
        "spoke_keywords": spoke_keywords,
        "hub_to_spoke_links": hub_to_spoke,
        "spoke_to_hub_links": spoke_to_hub,
        "horizontal_links": horizontal,
        "link_issues": link_issues,
        "cannibalized_keywords": cannibalized,
    }


def run_cluster_eval(
    cluster: dict,
    audit_results,
    tc: dict,
    gsc_data,
    sf_link_map,
    site_context: str,
    language: str,
    all_site_urls,
    health_key: str,
) -> dict:
    """Single source of truth for evaluating one cluster + persisting.

    Wraps the whole flow (_build_cluster_data → AI call → save) in one
    except handler that ALWAYS persists a structured result so the UI
    never lands in the inconsistent 'NOT EVALUATED + Error: ...' state.
    Every callsite (batch, per-cluster button, retry, pipeline) goes
    through this so they all behave the same way on failure.
    """
    from utils.ai_generator import get_client, evaluate_cluster_health
    from utils.persistence import save as _persist_save
    from config import get_anthropic_key

    try:
        client = get_client(get_anthropic_key())
        cd = _build_cluster_data(cluster, audit_results, tc, gsc_data, sf_link_map)
        if not cd:
            payload = {
                "error": "Cluster had no usable pages after defensive filtering",
                "error_type": "NoUsablePages",
                "traceback": "",
                "health_score": 0,
            }
        else:
            payload = evaluate_cluster_health(
                client, cd, site_context, language, all_site_urls,
            )
    except Exception as e:
        import traceback as _tb_run
        tb_text = _tb_run.format_exc()
        print(f"[cluster_health] eval failed for {cluster.get('topic', '?')}: {e}")
        print(tb_text)
        payload = {
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": tb_text[-2000:],
            "health_score": 0,
        }

    st.session_state[health_key] = payload
    try:
        _persist_save(health_key)
    except Exception as save_e:
        print(f"[cluster_health] persist failed for {health_key}: {save_e}")
    return payload


def run_all_clusters(progress_cb=None) -> dict:
    """Evaluate every topic cluster, skipping ones already cached.

    Pipeline entry point — called by Step 6.5 (Cluster Health) before
    Step 7 (AI Content Quality) so the per-page bulk AI generation has
    every cluster's strategic review available in session_state. Without
    this step, _format_cluster_health_insights() returns empty strings
    and the AI text generators silently miss the misplaced-keyword and
    cannibalization findings the strategic review would have caught.

    Skips clusters that already have a cached `_cluster_health_<hash>`
    payload — so the step is idempotent and cheap on re-runs. Pass
    progress_cb=lambda(i, n, topic) to receive progress updates.

    Returns a summary dict the pipeline can log: {evaluated, skipped,
    failed, total}.
    """
    tc = st.session_state.get("topic_clusters") or {}
    clusters = tc.get("clusters", []) if isinstance(tc, dict) else []
    if not clusters:
        raise ValueError("Run Topic Clusters (step 5) first — no clusters to evaluate")
    audit_results = st.session_state.get("audit_results", []) or []
    if not audit_results:
        raise ValueError("Run Bulk Audit (step 6) first — cluster health needs page data")

    gsc_data = st.session_state.get("gsc_data")
    sf_link_map = st.session_state.get("sf_link_map")
    site_context = st.session_state.get("site_context", "")
    language = st.session_state.get("content_language", "Swedish")

    all_site_urls = sorted(set(r["url"] for r in audit_results if r.get("url")))
    if gsc_data is not None and hasattr(gsc_data, "page"):
        all_site_urls = sorted(set(all_site_urls + gsc_data["page"].unique().tolist()))

    clusters_sorted = sorted(clusters, key=lambda c: -c.get("total_impressions", 0))
    n = len(clusters_sorted)
    evaluated = skipped = failed = 0

    for i, cluster in enumerate(clusters_sorted):
        topic = cluster.get("topic", f"Cluster {i}")
        health_key = f"_cluster_health_{stable_hash(topic)}"
        if progress_cb:
            try:
                progress_cb(i, n, topic)
            except Exception:
                pass

        cached = st.session_state.get(health_key)
        # Skip when we already have a valid (non-error) cached eval.
        # Failed entries are retried so transient errors don't block
        # downstream AI generation forever.
        if isinstance(cached, dict) and not cached.get("error"):
            skipped += 1
            continue

        payload = run_cluster_eval(
            cluster, audit_results, tc, gsc_data, sf_link_map,
            site_context, language, all_site_urls, health_key,
        )
        if payload.get("error"):
            failed += 1
        else:
            evaluated += 1

    if progress_cb:
        try:
            progress_cb(n, n, "done")
        except Exception:
            pass

    return {"evaluated": evaluated, "skipped": skipped, "failed": failed, "total": n}
