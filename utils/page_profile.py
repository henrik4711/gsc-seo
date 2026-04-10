"""
Build a COMPLETE profile for any URL by aggregating ALL data sources in session_state.
Pure data aggregation — no AI calls, no network, deterministic.
"""

import re
from collections import Counter
from urllib.parse import urlparse

import streamlit as st
import pandas as pd

from utils.ui_helpers import normalize_url, stable_hash


def build_page_profile(url: str) -> dict:
    """
    Aggregate every data source in session_state for a single URL.
    Returns a dict with all known information about the page.
    Every field has a sensible default so callers never need to check for None.
    """
    norm = normalize_url(url)
    url_path = urlparse(norm).path or "/"
    url_hash = stable_hash(norm)

    profile = {
        "url": norm,
        "url_path": url_path,

        # ── Audit results ──
        "page_type": "unknown",
        "title": "",
        "meta_description": "",
        "h1": "",
        "h2s": [],
        "word_count": 0,
        "body_text": "",
        "schema_types": [],
        "template_type": "",
        "has_accordion_product": False,
        "has_breadcrumb_schema": False,
        "internal_links_out": [],
        "internal_links_out_count": 0,
        "images_without_alt": 0,
        "content_audit": {},
        "products": [],

        # ── GSC data ──
        "gsc_queries": [],
        "total_impressions": 0,
        "total_clicks": 0,
        "primary_query": "",
        "lost_clicks_total": 0,

        # ── Ahrefs / page authority ──
        "referring_domains": 0,
        "authority_score": 0,

        # ── CTR gaps ──
        "ctr_gaps": [],

        # ── Topic clusters ──
        "clusters": [],
        "is_pillar": False,
        "child_pages": [],

        # ── Cannibalization ──
        "cannibalization": [],

        # ── Internal links IN (from sf_link_map) ──
        "internal_links_in": [],
        "internal_links_in_count": 0,

        # ── Crawl issues ──
        "crawl_issues": [],

        # ── Quality assessment ──
        "quality_verdict": None,
        "quality_score": 0,
        "quality_summary": "",
        "quality_issues": [],
        "quality_fixes": [],

        # ── AI plan ──
        "has_plan": False,
        "plan_summary": "",

        # ── Ideal structure ──
        "ideal_action": None,
        "ideal_detail": "",

        # ── Content gaps ──
        "content_gaps": [],

        # ── Computed flags ──
        "is_orphan": False,
        "is_thin": False,
        "has_keyword_stuffing": False,
        "has_generic_content": False,
        "needs_action": True,

        # ── Auto-detected issues ──
        "auto_issues": [],
    }

    # ─────────────────────────────────────────────────────────
    # 1. Audit results
    # ─────────────────────────────────────────────────────────
    audit_results = st.session_state.get("audit_results", [])
    page_data = {}
    if isinstance(audit_results, list):
        for r in audit_results:
            if isinstance(r, dict) and normalize_url(r.get("url", "")) == norm:
                page_data = r
                break

    if page_data:
        profile["page_type"] = page_data.get("page_type", "unknown")
        profile["title"] = page_data.get("title", "") or ""
        profile["meta_description"] = page_data.get("meta_description", "") or ""
        profile["h1"] = page_data.get("h1", "") or ""
        profile["h2s"] = page_data.get("h2s", []) or []
        profile["word_count"] = page_data.get("word_count", 0) or 0
        profile["body_text"] = (page_data.get("body_text", "") or "")[:2000]
        profile["schema_types"] = page_data.get("schema_types", []) or []
        profile["template_type"] = page_data.get("template_type", "") or ""
        profile["has_accordion_product"] = bool(page_data.get("has_accordion_product"))
        profile["has_breadcrumb_schema"] = bool(page_data.get("has_breadcrumb_schema"))
        profile["images_without_alt"] = page_data.get("images_without_alt", 0) or 0

        # Internal links out
        raw_links = page_data.get("internal_links") or []
        links_out = []
        if isinstance(raw_links, list):
            for lnk in raw_links:
                if isinstance(lnk, dict):
                    links_out.append({
                        "url": lnk.get("url", ""),
                        "anchor": lnk.get("anchor", ""),
                    })
                elif isinstance(lnk, str):
                    links_out.append({"url": lnk, "anchor": ""})
        profile["internal_links_out"] = links_out
        profile["internal_links_out_count"] = len(links_out)

        # Content audit sub-dict
        content_audit = page_data.get("content_audit") or {}
        profile["content_audit"] = content_audit

        # Products
        products = content_audit.get("products") or page_data.get("products") or []
        if isinstance(products, list):
            profile["products"] = products

    # ─────────────────────────────────────────────────────────
    # 2. GSC data
    # ─────────────────────────────────────────────────────────
    gsc_data = st.session_state.get("gsc_data")
    if gsc_data is not None and isinstance(gsc_data, pd.DataFrame) and not gsc_data.empty:
        try:
            page_gsc = gsc_data[gsc_data["page"].apply(normalize_url) == norm]
            if not page_gsc.empty:
                top_q = page_gsc.sort_values("impressions", ascending=False)
                queries = []
                for _, qr in top_q.iterrows():
                    queries.append({
                        "query": qr.get("query", ""),
                        "clicks": int(qr.get("clicks", 0)),
                        "impressions": int(qr.get("impressions", 0)),
                        "position": round(float(qr.get("position", 0)), 1),
                        "ctr": round(float(qr.get("ctr", 0)), 4),
                    })
                profile["gsc_queries"] = queries
                profile["total_impressions"] = int(top_q["impressions"].sum())
                profile["total_clicks"] = int(top_q["clicks"].sum())
                if queries:
                    profile["primary_query"] = queries[0]["query"]
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────
    # 3. Page authority (Ahrefs)
    # ─────────────────────────────────────────────────────────
    page_authority = st.session_state.get("page_authority")
    if page_authority is not None and isinstance(page_authority, pd.DataFrame) and not page_authority.empty:
        try:
            pa_match = page_authority[page_authority["page"].apply(normalize_url) == norm]
            if not pa_match.empty:
                row = pa_match.iloc[0]
                profile["referring_domains"] = int(row.get("referring_domains", 0) or 0)
                profile["authority_score"] = int(row.get("authority_score", 0) or 0)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────
    # 4. CTR gaps
    # ─────────────────────────────────────────────────────────
    ctr_gaps = st.session_state.get("ctr_gaps")
    if ctr_gaps is not None and isinstance(ctr_gaps, pd.DataFrame) and not ctr_gaps.empty:
        try:
            page_gaps = ctr_gaps[ctr_gaps["page"].apply(normalize_url) == norm]
            if not page_gaps.empty:
                gaps_list = []
                total_lost = 0.0
                for _, gr in page_gaps.iterrows():
                    lost = float(gr.get("lost_clicks", 0) or 0)
                    gaps_list.append({
                        "query": gr.get("query", ""),
                        "lost_clicks": round(lost, 1),
                        "position": round(float(gr.get("position", 0) or 0), 1),
                    })
                    total_lost += lost
                profile["ctr_gaps"] = gaps_list
                profile["lost_clicks_total"] = round(total_lost, 1)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────
    # 5. Topic clusters
    # ─────────────────────────────────────────────────────────
    topic_clusters = st.session_state.get("topic_clusters", {})
    if isinstance(topic_clusters, dict):
        page_topics = topic_clusters.get("page_topics", {})
        my_topics = page_topics.get(norm, [])
        if isinstance(my_topics, list):
            for t in my_topics:
                if isinstance(t, dict):
                    profile["clusters"].append({
                        "topic": t.get("topic", ""),
                        "queries_in_topic": t.get("queries_in_topic", 0),
                        "clicks": t.get("clicks", 0),
                    })

        # Check if this page is a pillar (other pages' paths start with this path)
        all_cluster_pages = set()
        for cluster in topic_clusters.get("clusters", []):
            for cp in cluster.get("pages", []):
                p_url = normalize_url(cp.get("page", ""))
                if p_url:
                    all_cluster_pages.add(p_url)

        children = []
        for other_url in all_cluster_pages:
            if other_url != norm:
                other_path = urlparse(other_url).path or "/"
                if other_path.startswith(url_path + "/") and url_path != "/":
                    children.append(other_url)
        if children:
            profile["is_pillar"] = True
            profile["child_pages"] = sorted(children)

    # ─────────────────────────────────────────────────────────
    # 6. Cannibalization
    # ─────────────────────────────────────────────────────────
    cannibal_df = st.session_state.get("cannibalization")
    if cannibal_df is not None and isinstance(cannibal_df, pd.DataFrame) and not cannibal_df.empty:
        try:
            for _, crow in cannibal_df.iterrows():
                pages_detail = crow.get("pages_detail", [])
                if not isinstance(pages_detail, list):
                    continue
                page_urls_in_row = [
                    normalize_url(p.get("page", ""))
                    for p in pages_detail if isinstance(p, dict)
                ]
                if norm in page_urls_in_row:
                    # Check if this page is the recommended winner
                    recommended_winner = normalize_url(str(crow.get("recommended_winner", "")))
                    is_winner = (norm == recommended_winner)
                    competing = []
                    for p in pages_detail:
                        if not isinstance(p, dict):
                            continue
                        p_norm = normalize_url(p.get("page", ""))
                        if p_norm != norm:
                            competing.append(p_norm)
                    profile["cannibalization"].append({
                        "query": crow.get("query", ""),
                        "type": crow.get("type", ""),
                        "competing_pages": competing,
                        "lost_clicks": float(crow.get("lost_clicks", 0) or 0),
                        "is_winner": is_winner,
                    })
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────
    # 7. Internal links IN (sf_link_map)
    # ─────────────────────────────────────────────────────────
    sf_link_map = st.session_state.get("sf_link_map")
    if sf_link_map and isinstance(sf_link_map, dict):
        # links_to: {target_url: [{source, anchor}, ...]}
        links_to = sf_link_map.get("links_to", {})
        inbound = links_to.get(norm, [])
        if isinstance(inbound, list):
            for lt in inbound:
                if isinstance(lt, dict):
                    profile["internal_links_in"].append({
                        "source": lt.get("source", lt.get("url", "")),
                        "anchor": lt.get("anchor", ""),
                    })
            profile["internal_links_in_count"] = len(profile["internal_links_in"])

        # Also enrich outbound from links_from if audit didn't have them
        if not profile["internal_links_out"]:
            links_from = sf_link_map.get("links_from", {})
            outbound = links_from.get(norm, [])
            if isinstance(outbound, list):
                for lf in outbound:
                    if isinstance(lf, dict):
                        profile["internal_links_out"].append({
                            "url": lf.get("target", lf.get("url", "")),
                            "anchor": lf.get("anchor", ""),
                        })
                profile["internal_links_out_count"] = len(profile["internal_links_out"])

    # ─────────────────────────────────────────────────────────
    # 8. Crawl issues (sf_crawl_issues)
    # ─────────────────────────────────────────────────────────
    sf_crawl_issues = st.session_state.get("sf_crawl_issues")
    if sf_crawl_issues and isinstance(sf_crawl_issues, dict):
        for issue_type, issue_list in sf_crawl_issues.items():
            if not isinstance(issue_list, list):
                continue
            for issue in issue_list:
                if not isinstance(issue, dict):
                    continue
                issue_url = normalize_url(issue.get("url", ""))
                # Also check source/target for link-based issues
                source_url = normalize_url(issue.get("source", ""))
                target_url = normalize_url(issue.get("target", ""))
                if norm in (issue_url, source_url, target_url):
                    profile["crawl_issues"].append({
                        "type": issue_type,
                        **issue,
                    })

    # ─────────────────────────────────────────────────────────
    # 9. Quality assessment (_quality_*)
    # ─────────────────────────────────────────────────────────
    quality = st.session_state.get(f"_quality_{url_hash}")
    if isinstance(quality, dict):
        profile["quality_verdict"] = quality.get("verdict", None)
        profile["quality_score"] = quality.get("score", 0) or 0
        profile["quality_summary"] = quality.get("summary", "") or ""
        profile["quality_issues"] = quality.get("main_issues", []) or []
        profile["quality_fixes"] = quality.get("specific_fixes", []) or []

    # ─────────────────────────────────────────────────────────
    # 10. AI plan (_ai_plan_*)
    # ─────────────────────────────────────────────────────────
    plan = st.session_state.get(f"_ai_plan_{url_hash}")
    if isinstance(plan, dict) and not plan.get("error"):
        profile["has_plan"] = True
        profile["plan_summary"] = plan.get("summary", "") or plan.get("plan_summary", "") or ""

    # ─────────────────────────────────────────────────────────
    # 11. Ideal structure (_ideal_structure)
    # ─────────────────────────────────────────────────────────
    ideal = st.session_state.get("_ideal_structure")
    if isinstance(ideal, dict):
        # Check merges — is this page being merged FROM or TO?
        for m in ideal.get("merge", []) or []:
            if not isinstance(m, dict):
                continue
            to_url = normalize_url(m.get("to", ""))
            from_urls = m.get("from", [])
            if isinstance(from_urls, list):
                for fu in from_urls:
                    if normalize_url(fu) == norm:
                        profile["ideal_action"] = "merge_from"
                        profile["ideal_detail"] = f"merge into {to_url}"
                        break
            if to_url == norm:
                profile["ideal_action"] = "merge_to"
                from_list = ", ".join(normalize_url(f) for f in from_urls if isinstance(f, str))
                profile["ideal_detail"] = f"receive content from {from_list}"

        # Check deletes
        if profile["ideal_action"] is None:
            for d in ideal.get("delete", []) or []:
                if isinstance(d, dict) and normalize_url(d.get("url", "")) == norm:
                    profile["ideal_action"] = "delete"
                    profile["ideal_detail"] = d.get("reason", "")
                    break

        # Check creates
        if profile["ideal_action"] is None:
            for c in ideal.get("create", []) or []:
                if isinstance(c, dict) and normalize_url(c.get("url", "")) == norm:
                    profile["ideal_action"] = "create"
                    profile["ideal_detail"] = c.get("reason", c.get("title", ""))
                    break

    # ─────────────────────────────────────────────────────────
    # 12. Content gaps
    # ─────────────────────────────────────────────────────────
    content_gaps = st.session_state.get("content_gaps", [])
    if isinstance(content_gaps, list):
        my_cluster_topics = {c["topic"] for c in profile["clusters"]}
        for gap in content_gaps:
            if isinstance(gap, dict):
                gap_topic = gap.get("topic", "") or gap.get("cluster", "")
                if gap_topic in my_cluster_topics:
                    profile["content_gaps"].append(gap)

    # ─────────────────────────────────────────────────────────
    # 13. Computed flags
    # ─────────────────────────────────────────────────────────
    # For category pages: use EDITORIAL text only (intro_text + bottom_text)
    # NOT full body_text which includes product grid with prices.
    # "kr rea" x26 comes from product cards, not editorial content.
    intro_text = (page_data.get("intro_text") or "")
    bottom_text_raw = (page_data.get("bottom_text") or "")
    editorial_wc = page_data.get("total_editorial_words", 0)
    profile["intro_text"] = intro_text
    profile["bottom_text_content"] = bottom_text_raw
    profile["editorial_word_count"] = editorial_wc

    editorial = (intro_text + " " + bottom_text_raw).strip().lower()
    body = editorial if editorial and len(editorial) > 50 else profile["body_text"].lower()

    # Thin content — based on editorial words for categories
    check_wc = editorial_wc if editorial_wc > 0 else profile["word_count"]
    profile["is_thin"] = check_wc < 300

    # Orphan: no internal links in AND no crawl issues mentioning it as linked
    if profile["internal_links_in_count"] == 0:
        # Double-check with sf_pages if available
        sf_pages = st.session_state.get("sf_pages")
        if sf_pages is not None and isinstance(sf_pages, pd.DataFrame) and not sf_pages.empty:
            try:
                inlinks_col = None
                for col in ("Unique Inlinks", "unique_inlinks", "Inlinks"):
                    if col in sf_pages.columns:
                        inlinks_col = col
                        break
                if inlinks_col:
                    url_col = None
                    for col in ("Address", "address", "URL", "url"):
                        if col in sf_pages.columns:
                            url_col = col
                            break
                    if url_col:
                        sf_match = sf_pages[sf_pages[url_col].apply(
                            lambda x: normalize_url(str(x)) if pd.notna(x) else ""
                        ) == norm]
                        if not sf_match.empty:
                            inlinks_val = sf_match.iloc[0].get(inlinks_col, 0)
                            if pd.notna(inlinks_val) and int(inlinks_val) > 0:
                                profile["is_orphan"] = False
                            else:
                                profile["is_orphan"] = True
                        else:
                            profile["is_orphan"] = True
                    else:
                        profile["is_orphan"] = True
                else:
                    profile["is_orphan"] = True
            except Exception:
                profile["is_orphan"] = True
        else:
            profile["is_orphan"] = True

    # Keyword stuffing: count bigrams and trigrams
    auto_issues = []
    if body:
        words = re.findall(r'\w+', body.lower())
        for n in (2, 3):
            if len(words) >= n:
                ngrams = [" ".join(words[i:i+n]) for i in range(len(words) - n + 1)]
                counts = Counter(ngrams)
                for ngram, count in counts.most_common(10):
                    if count > 5:
                        profile["has_keyword_stuffing"] = True
                        auto_issues.append(f"keyword stuffing: '{ngram}' x{count}")

    # Generic content: category page with no brand/price references
    if profile["page_type"] == "category" and body:
        has_price = bool(re.search(r'\d+[\s,.]?\d*\s*(kr|:-|SEK|EUR|USD|\$)', body, re.IGNORECASE))
        has_brand = bool(profile["products"])  # If products exist, it references brands
        if not has_price and not has_brand:
            profile["has_generic_content"] = True
            auto_issues.append("generic category content: no product/brand/price references")

    # Images without alt
    if profile["images_without_alt"] > 0:
        auto_issues.append(f"images without alt text: {profile['images_without_alt']}")

    # Thin content flag
    if profile["is_thin"] and profile["page_type"] not in ("product",):
        auto_issues.append(f"thin content: {profile['word_count']} words")

    # Orphan
    if profile["is_orphan"]:
        auto_issues.append("orphan page: no internal links pointing to this page")

    profile["auto_issues"] = auto_issues

    # needs_action: False only if quality=KEEP + no cannibalization + no issues
    profile["needs_action"] = not (
        profile["quality_verdict"] == "KEEP"
        and not profile["cannibalization"]
        and not profile["crawl_issues"]
        and not profile["auto_issues"]
        and profile["ideal_action"] is None
    )

    return profile
