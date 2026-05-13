"""
Page Auditor
Scrapes landing pages, extracts meta data, evaluates quality vs. keywords.
Now with page-type detection and deep category analysis.
"""

import streamlit as st
import pandas as pd
import time
from utils.ui_helpers import shorten_url, stable_hash


def score_badge(score: int) -> str:
    if score >= 80:
        color, label = "#33dd88", "Good"
    elif score >= 50:
        color, label = "#ffaa33", "Issues"
    else:
        color, label = "#ff4455", "Critical"
    return f"<span style='color:{color}; font-family:\"IBM Plex Mono\",monospace; font-weight:600;'>{score}/100 · {label}</span>"


def issue_badge(issue_type: str) -> str:
    colors = {"critical": "#ff4455", "warn": "#ffaa33", "info": "#6b6baa"}
    labels = {"critical": "CRITICAL", "warn": "WARNING", "info": "INFO"}
    color = colors.get(issue_type, "#6b6b8a")
    label = labels.get(issue_type, issue_type.upper())
    return f"<span style='color:{color}; font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; font-weight:600;'>[{label}]</span>"


def severity_badge(severity: str) -> str:
    colors = {"critical": "#ff4455", "warn": "#ffaa33", "info": "#6b6baa"}
    labels = {"critical": "CRITICAL", "warn": "WARNING", "info": "INFO"}
    color = colors.get(severity, "#6b6b8a")
    label = labels.get(severity, severity.upper())
    return f"<span style='color:{color}; font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; font-weight:600;'>[{label}]</span>"


PAGE_TYPE_LABELS = {
    "category": ("CATEGORY", "#c8b4ff"),
    "product": ("PRODUCT", "#33dd88"),
    "blog": ("BLOG/GUIDE", "#ffaa33"),
    "faq": ("FAQ/HELP", "#5bb4d4"),
    "unknown": ("UNKNOWN", "#6b6b8a"),
}


def _get_cluster_keywords(url: str) -> list:
    """Get keywords from topic clusters for this URL."""
    tc = st.session_state.get("topic_clusters")
    if not tc:
        return []
    keywords = []
    for cluster in tc.get("clusters", []):
        for page in cluster.get("pages", []):
            from utils.ui_helpers import normalize_url as _nu
            if _nu(page.get("page", "")) == _nu(url):
                keywords.extend(cluster.get("queries", []))
    return list(set(keywords))[:50]


def render():
    # Anchor at the absolute top so reruns scroll here, not to ### headings
    st.markdown("<div id='page-auditor-top'></div>", unsafe_allow_html=True)
    st.markdown("## Page Auditor")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:1rem;'>Analyze meta title, description and content - with deep analysis of category pages</p>",
        unsafe_allow_html=True
    )

    if "gsc_data" not in st.session_state:
        st.warning("Go to **1. Setup & Connect** and connect GSC first.")
        return

    df = st.session_state["gsc_data"]

    # ── PROMINENT Re-scrape button at the very top ──────────────
    all_pages_top = df["page"].unique().tolist()
    already_audited_top = set(r["url"] for r in st.session_state.get("audit_results", []) or [])
    page_impr_top = df.groupby("page")["impressions"].sum().sort_values(ascending=False)

    st.markdown(
        f"<div style='background:#0d0d15; border:3px solid #5533ff; border-radius:10px; "
        f"padding:1.2rem; margin-bottom:1.5rem;'>"
        f"<div style='font-family:\"Syne\",sans-serif; font-size:1.2rem; font-weight:700; color:#c8b4ff; margin-bottom:0.4rem;'>"
        f"🔄 Re-scrape all pages (START HERE)</div>"
        f"<div style='font-size:0.85rem; color:#9b9bb8; margin-bottom:0.8rem;'>"
        f"{len(all_pages_top)} pages in GSC · {len(already_audited_top)} already audited · "
        f"{len(all_pages_top) - len(already_audited_top)} new. "
        f"Re-scrape picks up the latest page_scraper fixes (editorial images, container diagnostics).</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    top_c1, top_c2, top_c3 = st.columns([1, 1, 1])
    _top_rescrape_all = False
    _top_rescrape_new = False
    with top_c1:
        _top_rescrape_all = st.button("🔄 Re-scrape ALL pages (force)", type="primary", key="btn_top_rescrape_all", use_container_width=True)
    with top_c2:
        _top_rescrape_new = st.button("➕ Scrape NEW pages only", key="btn_top_rescrape_new", use_container_width=True)
    with top_c3:
        st.caption(f"~{max(1, (len(all_pages_top)) // 60)} min for all · ~1 sec/page")

    # Immediate feedback + execute (no rerun dance — run inline below)
    if _top_rescrape_all:
        st.success(f"✓ Button clicked — preparing to re-scrape ALL {len(all_pages_top)} pages…")
    elif _top_rescrape_new:
        _new_urls = [p for p in all_pages_top if p not in already_audited_top]
        st.success(f"✓ Button clicked — preparing to scrape {len(_new_urls)} NEW page(s)…")

    # ── URL Input ─────────────────────────────────────────────────
    with st.form("audit_form"):
        col1, col2 = st.columns([2, 1])
        with col1:
            urls_input = st.text_area(
                "URLs to analyze (one per line)",
                height=150,
                help="Enter the URLs you want to audit",
            )
        with col2:
            st.markdown("#### Settings")
            scrape_live = st.toggle("Scrape live pages", value=True, help="Fetch current content from the website")
            deep_category = st.toggle("Deep category analysis", value=True, help="Separates editorial content from product grid on category pages")
            show_keywords = st.number_input("Top N keywords per page", min_value=3, max_value=15, value=5)
        run_audit = st.form_submit_button("Run Audit", type="primary")

    urls = [u.strip() for u in urls_input.split("\n") if u.strip()]

    # ── Bulk audit ALL pages ──────────────────────────────────────
    all_pages = df["page"].unique().tolist()
    already_audited = set(r["url"] for r in st.session_state.get("audit_results", []))
    not_audited = [p for p in all_pages if p not in already_audited]

    st.markdown("---")
    st.markdown(
        f"<div style='background:#0d0d15; border:2px solid #5533ff; border-radius:8px; padding:1rem; margin-bottom:1rem;'>"
        f"<div style='font-family:\"Syne\",sans-serif; font-size:1.1rem; font-weight:700; color:#c8b4ff; margin-bottom:0.5rem;'>"
        f"Bulk Audit — {len(all_pages)} pages in GSC, {len(not_audited)} not yet audited</div>"
        f"<div style='font-size:0.85rem; color:#9b9bb8;'>"
        f"Scrapes ALL pages from GSC and extracts title, meta, body text, links, headings, word count. "
        f"This data powers Internal Linking, Missing Keywords, Content Quality, and the Unified Task List. "
        f"Takes ~1 second per page.</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    with st.expander("Bulk audit settings", expanded=True):
        st.empty()

        bulk_col1, bulk_col2 = st.columns(2)
        with bulk_col1:
            min_impressions_bulk = st.number_input(
                "Min impressions per page",
                min_value=0, max_value=10000, value=0,
                help="Set to 0 to include ALL pages — low-traffic pages matter for topic clusters and internal linking",
                key="bulk_min_impr",
            )
        with bulk_col2:
            max_pages_bulk = st.number_input(
                "Max pages to audit",
                min_value=10, max_value=5000, value=2000,
                help="All pages from GSC — takes ~1 sec per page. 2000 pages ≈ 33 min.",
                key="bulk_max_pages",
            )

        # Filter + sort by impressions
        page_impressions = df.groupby("page")["impressions"].sum().sort_values(ascending=False)
        bulk_pages = page_impressions[page_impressions >= min_impressions_bulk].head(max_pages_bulk).index.tolist()
        bulk_new = [p for p in bulk_pages if p not in already_audited]

        st.markdown(
            f"**{len(bulk_pages)} pages** match filters, **{len(bulk_new)} new** to audit "
            f"(~{len(bulk_new)} seconds estimated)"
        )

        audit_new_only = st.toggle(
            "Only audit new pages (keep existing results)",
            value=True,
            key="bulk_new_only",
        )

        run_bulk = st.button("Run Bulk Audit", type="primary", key="btn_bulk_audit")

        if run_bulk:
            pages_to_audit = bulk_new if audit_new_only else bulk_pages
            if not pages_to_audit:
                st.success("All pages already audited!")
            else:
                # Inject into urls and trigger audit
                urls = pages_to_audit
                run_audit = True

    # Handle top re-scrape buttons (set earlier this render)
    if _top_rescrape_all:
        urls = all_pages_top
        run_audit = True
    elif _top_rescrape_new:
        urls = [p for p in all_pages_top if p not in already_audited_top]
        if not urls:
            st.warning("All pages already audited — nothing new to scrape.")
        else:
            run_audit = True

    if not urls and not run_audit:
        # Don't block if there's existing audit data to show
        if "audit_results" not in st.session_state or not st.session_state["audit_results"]:
            st.info("Enter URLs above to start audit")
            return

    # ── Run Audit ─────────────────────────────────────────────────
    if run_audit and urls:
        # Normalize input URLs to match GSC data format
        from utils.ui_helpers import normalize_url as _norm_input
        urls = [_norm_input(u) for u in urls]

        audit_results = []
        total_urls = len(urls)

        try:
          with st.status(f"Auditing {total_urls} pages...", expanded=True) as status:
            progress = st.progress(0)
            log = st.empty()

            for i, url in enumerate(urls):
                remaining = (total_urls - i)
                log.write(f"[{i+1}/{total_urls}] {url}")
                progress.progress(i / max(total_urls, 1))

                # Get keywords for this page from GSC
                # Filter out brand keywords that appear on every page
                page_queries = df[df["page"] == url].sort_values("impressions", ascending=False)

                # Detect brand terms: keywords that appear on 30%+ of all pages
                if "_brand_keywords" not in st.session_state:
                    total_pages = df["page"].nunique()
                    kw_page_counts = df.groupby("query")["page"].nunique()
                    brand_kws = set(kw_page_counts[kw_page_counts >= total_pages * 0.3].index)
                    st.session_state["_brand_keywords"] = brand_kws
                brand_kws = st.session_state["_brand_keywords"]

                # Prioritize: non-brand keywords first, then brand keywords
                non_brand = page_queries[~page_queries["query"].isin(brand_kws)]
                brand_only = page_queries[page_queries["query"].isin(brand_kws)]

                target_keywords = (
                    non_brand["query"].head(show_keywords).tolist()
                    + brand_only["query"].head(2).tolist()
                )[:show_keywords]

                # Also get cluster keywords for deeper validation
                cluster_keywords = _get_cluster_keywords(url)

                # Get backlink data if available
                page_auth = st.session_state.get("page_authority")
                rd = 0
                bl_count = 0
                auth_score = 0
                if page_auth is not None and hasattr(page_auth, "iterrows"):
                    from utils.ui_helpers import normalize_url as _norm
                    match = page_auth[page_auth["page"].apply(_norm) == _norm(url)]
                    if not match.empty:
                        rd = int(match.iloc[0].get("referring_domains", 0))
                        bl_count = int(match.iloc[0].get("backlinks", 0))
                        auth_score = int(match.iloc[0].get("authority_score", 0))

                result = {
                    "url": url,
                    "target_keywords": target_keywords,
                    "cluster_keywords": cluster_keywords,
                    "lost_clicks_estimate": page_queries["lost_clicks_estimate"].sum() if "lost_clicks_estimate" in page_queries.columns else 0,
                    "position": page_queries["position"].mean() if len(page_queries) > 0 else None,
                    "ctr_gap_pct": page_queries["ctr_gap_pct"].mean() if "ctr_gap_pct" in page_queries.columns and len(page_queries) > 0 else 0,
                    "impressions": page_queries["impressions"].sum(),
                    "clicks": page_queries["clicks"].sum(),
                    "referring_domains": rd,
                    "backlinks": bl_count,
                    "authority_score": auth_score,
                }

                # ── Search intent from Ahrefs ────────────────────
                ahrefs_kw = st.session_state.get("ahrefs_organic_keywords")
                if ahrefs_kw is not None and not ahrefs_kw.empty:
                    from utils.ui_helpers import normalize_url as _ni
                    page_kws = ahrefs_kw[ahrefs_kw["page"].apply(_ni) == _ni(url)]
                    if not page_kws.empty:
                        # TEMPLATE-FIRST intent: page type is primary signal
                        # Keywords only override when strongly mismatched
                        vol = page_kws["volume"].fillna(0)
                        total_vol = max(vol.sum(), 1)
                        info_pct = (vol[page_kws.get("intent_informational", False) == True].sum() / total_vol * 100)
                        comm_pct = (vol[page_kws.get("intent_commercial", False) == True].sum() / total_vol * 100)
                        trans_pct = (vol[page_kws.get("intent_transactional", False) == True].sum() / total_vol * 100)

                        # Step 1: Template-based intent (structural truth)
                        pt = result.get("page_type", "unknown")
                        if pt == "category":
                            template_intent = "transactional"  # Categories are ALWAYS transactional
                        elif pt == "product":
                            template_intent = "transactional"
                        elif pt == "blog":
                            template_intent = "informational"
                        elif pt == "faq":
                            template_intent = "informational"
                        else:
                            template_intent = "mixed"

                        # Step 2: Keyword-based intent (user signal)
                        purchase_pct = trans_pct + comm_pct
                        if purchase_pct >= 50:
                            kw_intent = "transactional"
                        elif info_pct >= 70 and purchase_pct < 20:
                            kw_intent = "informational"
                        else:
                            kw_intent = "mixed"

                        # Step 3: Final = template wins, keyword flags mismatch
                        dominant_intent = template_intent
                        intent_mismatch = ""
                        if template_intent == "transactional" and kw_intent == "informational":
                            intent_mismatch = "Page is structurally transactional (category/product) but keywords are informational — content may be too guide-like for purchase intent"
                        elif template_intent == "informational" and kw_intent == "transactional":
                            intent_mismatch = "Page is structurally informational (blog/guide) but keywords are transactional — consider adding product links and CTAs"
                        result["search_intent"] = dominant_intent
                        result["intent_mismatch"] = intent_mismatch
                        result["intent_scores"] = {
                            "informational": round(info_pct),
                            "commercial": round(comm_pct),
                            "transactional": round(trans_pct),
                        }
                        # Also get top volume keywords from Ahrefs (supplement GSC)
                        top_ahrefs_kws = page_kws.sort_values("volume", ascending=False)["keyword"].head(5).tolist()
                        result["ahrefs_keywords"] = top_ahrefs_kws
                        result["ahrefs_volume"] = int(page_kws["volume"].sum())

                if scrape_live:
                    from utils.page_scraper import scrape_page, evaluate_meta
                    from utils.category_analyzer import classify_page_type, deep_scrape_category, audit_category_content

                    quick_class = classify_page_type(url)
                    is_likely_category = quick_class["page_type"] == "category"

                    if deep_category and is_likely_category:
                        page_data = deep_scrape_category(url)
                        result.update(page_data)
                        # Coerce to str — pandas/numpy cells may be NaN (float)
                        def _s2(v):
                            if v is None:
                                return ""
                            try:
                                import math
                                if isinstance(v, float) and math.isnan(v):
                                    return ""
                            except Exception:
                                pass
                            return str(v)
                        _body = _s2(page_data.get("full_body_text"))
                        result["body_text"] = _body
                        result["word_count"] = len(_body.split()) if _body else 0
                        result["title_length"] = len(_s2(page_data.get("title")))
                        result["description_length"] = len(_s2(page_data.get("meta_description")))
                        result["internal_links"] = page_data.get("internal_link_count", 0)
                        result["images_without_alt"] = page_data.get("images_without_alt", 0)
                    else:
                        page_data = scrape_page(url)
                        result.update(page_data)
                        classification = classify_page_type(url, page_data)
                        result["page_type"] = classification["page_type"]

                    if result.get("success", page_data.get("success")):
                        # ── Scrape quality validation ─────────────────
                        scraper = result.get("_scraper", "unknown")
                        wc = result.get("word_count", 0)
                        has_title = bool(result.get("title"))
                        has_body = wc > 0
                        data_warnings = []

                        if "requests" in scraper:
                            data_warnings.append("Scraped without JavaScript rendering (Playwright unavailable) — content may be incomplete")
                        if has_title and not has_body:
                            data_warnings.append(f"Page has title but 0 words of body text — possible JS-rendered content not captured")
                        if result.get("page_type") == "category" and not result.get("bottom_text") and wc > 100:
                            data_warnings.append("Category page: no bottom text detected — product grid may use non-standard markup")

                        result["_data_warnings"] = data_warnings

                        meta_eval = evaluate_meta(result, target_keywords)
                        result["meta_score"] = meta_eval["score"]
                        result["issues"] = meta_eval["issues"]
                        result["meta_eval"] = meta_eval

                        cat_audit = audit_category_content(
                            result, cluster_keywords, target_keywords,
                            topic_clusters=st.session_state.get("topic_clusters"),
                            page_authority=st.session_state.get("page_authority"),
                        )
                        result["content_score"] = cat_audit["score"]
                        result["content_audit"] = cat_audit
                        for issue in cat_audit.get("issues", []):
                            result["issues"].append({
                                "type": issue["severity"],
                                "field": issue["area"],
                                "msg": issue["msg"],
                            })
                    else:
                        # Scrape failed — try Screaming Frog data as fallback
                        sf_pages = st.session_state.get("sf_pages")
                        sf_fallback = False
                        print(f"[audit] Scrape failed for {url}, trying SF fallback. SF pages: {len(sf_pages) if sf_pages is not None else 'None'}")
                        if sf_pages is not None and not sf_pages.empty:
                            from utils.ui_helpers import normalize_url as _nfu
                            url_norm = _nfu(url)
                            sf_match = sf_pages[sf_pages["url"].apply(_nfu) == url_norm]
                            print(f"[audit] SF lookup: url_norm={url_norm}, matches={len(sf_match)}, SF sample URLs: {sf_pages['url'].head(3).tolist()}")
                            if not sf_match.empty:
                                sf_row = sf_match.iloc[0]
                                # Coerce to str — pandas cells can be NaN (float) not None
                                def _s(v):
                                    if v is None:
                                        return ""
                                    try:
                                        import math
                                        if isinstance(v, float) and math.isnan(v):
                                            return ""
                                    except Exception:
                                        pass
                                    return str(v)
                                result["title"] = _s(sf_row.get("title")) or _s(result.get("title"))
                                result["meta_description"] = _s(sf_row.get("meta_description")) or _s(result.get("meta_description"))
                                result["h1"] = _s(sf_row.get("h1")) or _s(result.get("h1"))
                                try:
                                    _wc = int(sf_row.get("word_count", 0) or 0)
                                except Exception:
                                    _wc = 0
                                result["word_count"] = _wc or result.get("word_count", 0)
                                result["title_length"] = len(result.get("title") or "")
                                result["description_length"] = len(result.get("meta_description") or "")
                                result["success"] = True
                                sf_fallback = True
                                result["_data_warnings"] = [
                                    f"Live scrape failed ({result.get('error', 'unknown')}). Using Screaming Frog data as fallback — title, meta, word count from SF crawl.",
                                ]

                        if sf_fallback:
                            # Run meta eval + content audit with SF data
                            print(f"[audit] SF fallback SUCCESS: title='{result.get('title','')[:50]}', words={result.get('word_count',0)}")
                            meta_eval = evaluate_meta(result, target_keywords)
                            result["meta_score"] = meta_eval["score"]
                            result["issues"] = meta_eval["issues"]
                            result["meta_eval"] = meta_eval
                        else:
                            result["_data_warnings"] = ["Scrape failed and no Screaming Frog data available"]
                            result["meta_score"] = None
                            result["issues"] = [{"type": "critical", "field": "url", "msg": f"Could not fetch the page: {result.get('error', page_data.get('error'))}"}]
                else:
                    result["success"] = True
                    result["title"] = "(not fetched - scraping disabled)"
                    result["meta_description"] = "(not fetched)"
                    result["meta_score"] = None
                    result["page_type"] = "unknown"
                    result["issues"] = []

                # SAFETY NET: page_type MUST be set before append, no matter
                # which branch above ran. Previously the deep_scrape_category
                # path and the SF-fallback path could leave page_type unset
                # entirely — Step 7 (AI Content Quality) then filtered out
                # every page because the eligibility check required
                # page_type ∈ (category|blog|faq).
                if "page_type" not in result:
                    try:
                        from utils.category_analyzer import classify_page_type as _cls_pt
                        result["page_type"] = _cls_pt(url, result).get("page_type", "unknown")
                    except Exception:
                        result["page_type"] = "unknown"

                audit_results.append(result)

                # Only update UI every 10 pages (reduces re-renders from 900 to 90)
                if (i + 1) % 10 == 0 or (i + 1) == total_urls:
                    progress.progress((i + 1) / total_urls)
                    log.write(f"[{i+1}/{total_urls}] Done: {url}")

                # Auto-save every 25 pages — write to DISK only (not session_state)
                # to avoid triggering Streamlit re-renders during audit.
                # 25 = max ~25 sec lost on crash (vs 100 = ~100 sec).
                # CRITICAL: fresh scrapes OVERWRITE existing disk entries.
                # Previous code only APPENDED new URLs — so a re-scrape of
                # an already-audited URL was silently discarded at checkpoint
                # time. Fresh editorial_images / structural_signals data from
                # a new scrape run got dropped and old polluted data stayed.
                if len(audit_results) % 25 == 0:
                    try:
                        from utils.persistence import _volume_available, _file_path
                        from utils.ui_helpers import normalize_url as _nu_ckpt
                        import json
                        if _volume_available():
                            path = _file_path("audit_results", "json")
                            existing_on_disk = []
                            if __import__("os").path.exists(path):
                                with open(path, "r", encoding="utf-8") as f:
                                    existing_on_disk = json.load(f)
                            # Build a set of URLs from this scrape run (freshly scraped)
                            fresh_urls_norm = set(_nu_ckpt(r.get("url", "")) for r in audit_results)
                            # Keep only disk entries that are NOT being re-scraped right now
                            kept_from_disk = [r for r in existing_on_disk
                                              if _nu_ckpt(r.get("url", "")) not in fresh_urls_norm]
                            # Concatenate: untouched disk entries + all fresh entries from this run
                            merged = kept_from_disk + list(audit_results)
                            def _conv(obj):
                                if hasattr(obj, 'item'): return obj.item()
                                raise TypeError(type(obj))
                            with open(path, "w", encoding="utf-8") as f:
                                json.dump(merged, f, ensure_ascii=False, indent=1, default=_conv)
                            print(f"[audit checkpoint] saved {len(merged)} total ({len(kept_from_disk)} kept + {len(audit_results)} fresh)")
                    except Exception as e:
                        print(f"[audit checkpoint] save failed: {e}")

            # Merge: replace existing entries for re-audited URLs, keep the rest
            if "audit_results" in st.session_state and st.session_state["audit_results"]:
                from utils.ui_helpers import normalize_url as _nurl
                new_urls_norm = set(_nurl(r["url"]) for r in audit_results)
                old_count = len(st.session_state["audit_results"])
                kept = [r for r in st.session_state["audit_results"] if _nurl(r["url"]) not in new_urls_norm]
                st.session_state["audit_results"] = kept + audit_results
                print(f"[audit] Merge: {old_count} old, removed {old_count - len(kept)}, added {len(audit_results)}, total {len(st.session_state['audit_results'])}")
                for r in audit_results:
                    print(f"[audit] New entry: url={r['url']}, title='{(r.get('title') or '')[:40]}', words={r.get('word_count',0)}, success={r.get('success')}")
            else:
                st.session_state["audit_results"] = audit_results

            # Auto-save to volume
            from utils.persistence import save_key
            save_key("audit_results")

            status.update(label=f"Audit complete — {len(audit_results)} pages", state="complete", expanded=False)
        except Exception as audit_err:
            st.error(f"AUDIT CRASHED: {audit_err}")
            import traceback
            st.code(traceback.format_exc())

    # ── Display Results ───────────────────────────────────────────
    if "audit_results" not in st.session_state:
        return

    results = st.session_state["audit_results"]

    # ── Reclassify page types (no re-scrape) ───────────────────────
    st.markdown("---")
    from collections import Counter
    _type_counts = Counter((r.get("page_type") or "missing") for r in results)
    _types_str = ", ".join(f"`{t}`: {n}" for t, n in _type_counts.most_common())
    st.markdown(f"**Current page-type breakdown:** {_types_str}")

    rc1, rc2 = st.columns([1, 2])
    with rc1:
        run_reclassify = st.button(
            "Reclassify page types (no re-scrape)",
            type="primary" if _type_counts.get("unknown", 0) > len(results) // 2 else "secondary",
            key="btn_reclassify_types",
        )
    with rc2:
        st.caption(
            "Re-runs classify_page_type() on each audited page using saved scrape data — "
            "fixes 'unknown' classifications without spending 18 min re-scraping."
        )

    if run_reclassify:
        from utils.category_analyzer import classify_page_type
        before = Counter((r.get("page_type") or "missing") for r in results)
        changed = 0
        with st.status("Reclassifying...", expanded=True) as rc_status:
            for r in results:
                old_type = r.get("page_type")
                try:
                    classification = classify_page_type(r.get("url", ""), r)
                    new_type = classification.get("page_type", "unknown")
                    if new_type != old_type:
                        r["page_type"] = new_type
                        r["_reclassify_signals"] = classification.get("signals", [])
                        changed += 1
                except Exception:
                    pass
            st.session_state["audit_results"] = results
            from utils.persistence import save_key
            save_key("audit_results")
            after = Counter((r.get("page_type") or "missing") for r in results)

            # If page_types actually changed, EVERY downstream AI analysis
            # that read page_type is now stale. Clear them so the pipeline
            # re-runs them on the corrected data — otherwise Step 10's
            # "all 1098 are unknown" verdict sits in the cache and shows
            # up on the dashboard forever.
            invalidated = []
            if changed:
                import os as _os
                downstream_keys = (
                    "_site_validation", "_ideal_structure",
                    "_gap_analysis", "_plan_validation",
                    "cluster_link_recommendations",
                )
                for k in downstream_keys:
                    if k in st.session_state:
                        del st.session_state[k]
                        invalidated.append(k)
                # Also drop the on-disk copies so they don't reload on rerun
                from utils.persistence import DATA_DIR, AI_CACHE_DIR
                for k in downstream_keys:
                    for ext in ("json", "csv"):
                        p = _os.path.join(DATA_DIR, f"{k}.{ext}")
                        if _os.path.exists(p):
                            try:
                                _os.remove(p)
                            except Exception:
                                pass
                    p = _os.path.join(AI_CACHE_DIR, f"{k}.json")
                    if _os.path.exists(p):
                        try:
                            _os.remove(p)
                        except Exception:
                            pass

            label = f"Reclassified {changed} pages — before: {dict(before)}, after: {dict(after)}"
            if invalidated:
                label += f". Invalidated stale analyses: {', '.join(invalidated)} — re-run via Run Pipeline."
            rc_status.update(label=label, state="complete")
        st.rerun()

    # Debug: show what fields the saved audit data actually contains
    with st.expander("🔍 Debug: what fields are in audit_results[0]?", expanded=False):
        if results:
            sample = results[0]
            keys = sorted(sample.keys())
            st.caption(f"Sample URL: `{sample.get('url', '?')}` — {len(keys)} fields")
            classifier_relevant = [
                "page_type", "template_type", "body_classes", "schema_types",
                "has_accordion_product", "has_breadcrumb_schema",
                "structural_signals", "h1", "word_count", "internal_links",
                "product_count",
            ]
            st.markdown("**Classifier-relevant fields present in this row:**")
            for k in classifier_relevant:
                v = sample.get(k, "<MISSING>")
                if isinstance(v, (dict, list)):
                    v_str = str(v)[:200]
                else:
                    v_str = str(v)[:120]
                marker = "✓" if k in sample else "✗"
                st.markdown(f"- {marker} `{k}` = `{v_str}`")
            st.caption(f"All keys: {', '.join(keys)}")

    # ── Recalculate content scores (no re-scrape) ──────────────────
    st.markdown("---")
    if st.button("Recalculate content scores (no re-scrape)", key="btn_recalc"):
        from utils.category_analyzer import audit_category_content
        recalc_count = 0
        with st.status("Recalculating...", expanded=True) as recalc_status:
            for i, r in enumerate(results):
                if r.get("body_text") or r.get("full_body_text"):
                    try:
                        cat_audit = audit_category_content(
                            r,
                            r.get("cluster_keywords", []),
                            r.get("target_keywords", []),
                            topic_clusters=st.session_state.get("topic_clusters"),
                            page_authority=st.session_state.get("page_authority"),
                        )
                        r["content_score"] = cat_audit["score"]
                        r["content_audit"] = cat_audit
                        recalc_count += 1
                    except Exception:
                        pass
            st.session_state["audit_results"] = results
            from utils.persistence import save_key
            save_key("audit_results")
            recalc_status.update(label=f"Recalculated {recalc_count} pages", state="complete")
        st.rerun()

    # ── AI Content Quality Check ─────────────────────────────────
    # Render as HTML (not `###`) so Streamlit doesn't auto-generate an
    # anchor that browsers scroll to on rerun.
    st.markdown("---")
    st.markdown(
        "<div style='font-size:1.2rem; font-weight:700; color:#e8e8f0; margin-top:0.5rem;'>"
        "AI Content Quality Check</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='color:#9b9bb8; font-size:0.85rem;'>"
        "AI evaluates text quality on category and blog pages — finds generic filler, "
        "keyword spam, thin content, and repetitive text. Skips product pages.</p>",
        unsafe_allow_html=True,
    )

    # ── Persisted diagnostic banner from "🔍 Re-scrape + re-check" ──
    _qq_diag = st.session_state.get("_qq_diag")
    if _qq_diag:
        with st.expander(
            f"🔍 Push-log diagnostic for {_qq_diag.get('url', '?')}",
            expanded=True,
        ):
            if _qq_diag.get("error"):
                st.error(f"Could not read push log: {_qq_diag['error']}")
            elif not _qq_diag.get("page_info"):
                st.warning(
                    "No Mshop page-info for this URL — your Mshop active-pages cache "
                    "hasn't been synced for this URL. Sync via the 🔌 Mshop Admin API "
                    "panel in Quick Wins."
                )
            elif not _qq_diag.get("entries"):
                pinfo = _qq_diag["page_info"]
                st.warning(
                    f"**No push entries logged for this page** "
                    f"({pinfo.get('type')} id={pinfo.get('id')}).\n\n"
                    "Either nothing was ever pushed for this page, OR the push log on "
                    "disk got reset.\n\n"
                    "If you DID push earlier and the live text is still bad, the most "
                    "likely cause is that you pushed a different page (different ID) "
                    "or the Mshop active-pages cache mapped this URL to the wrong ID."
                )
            else:
                st.caption(
                    f"Last {len(_qq_diag['entries'])} push attempts for this exact "
                    f"page ({_qq_diag['page_info'].get('type')} id="
                    f"{_qq_diag['page_info'].get('id')}, newest first):"
                )
                for entry in _qq_diag["entries"]:
                    status = entry.get("status", "?")
                    http = entry.get("http_code", "?")
                    color = "#33dd88" if status == "success" else "#ff4455"
                    payload = entry.get("payload") or {}
                    desc = payload.get("description") or ""
                    mt = payload.get("metaTitle") or ""
                    md = payload.get("metaDescription") or ""
                    body_excerpt = (entry.get("response_body") or "")[:300]
                    st.markdown(
                        f"<div style='background:#0d0d15; border-left:3px solid {color}; "
                        f"padding:0.6rem; margin:0.4rem 0; border-radius:4px; "
                        f"font-size:0.75rem; font-family:\"IBM Plex Mono\",monospace;'>"
                        f"<div style='color:{color}; font-weight:700;'>"
                        f"{status.upper()} · HTTP {http} · {entry.get('timestamp', '')}</div>"
                        f"<div style='color:#9b9bb8; margin-top:0.3rem;'>"
                        f"endpoint: {entry.get('endpoint', '')}</div>"
                        f"<div style='color:#e8e8f0; margin-top:0.3rem;'>"
                        f"description sent: <strong>{len(desc)}</strong> chars · "
                        f"meta_title sent: <strong>{len(mt)}</strong> chars · "
                        f"meta_desc sent: <strong>{len(md)}</strong> chars</div>"
                        f"<div style='color:#6b6b8a; margin-top:0.3rem; word-break:break-all;'>"
                        f"response: {body_excerpt}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                st.markdown(
                    "**How to read this:**\n\n"
                    "- ✅ `success` + HTTP 200 + `description sent: NNNN chars` = your "
                    "push reached Magento. If live text is STILL the old text, Magento's "
                    "full-page cache is serving stale HTML — flush it in Magento Admin "
                    "(System → Cache Management → Flush Magento Cache).\n"
                    "- ❌ Non-200 HTTP or `network_error` = the push never landed. "
                    "Check the response body above for Magento's error message.\n"
                    "- `description sent: 0 chars` = the push button sent an empty value. "
                    "Could mean the AI output wasn't loaded into the textarea before you "
                    "clicked Push, or the field-routing mapped intro to the wrong slot."
                )
            if st.button("Dismiss diagnostic", key="qq_dismiss_diag"):
                st.session_state.pop("_qq_diag", None)
                st.rerun()

    # All quality-check logic lives in utils.quality_check_runner.
    # This view only renders UI + delegates to the shared module.
    from utils.quality_check_runner import (
        eligible_pages, pages_needing_check, already_checked_count,
        run_quality_batches, ELIGIBLE_PAGE_TYPES, MIN_WORD_COUNT,
    )

    quality_candidates = eligible_pages(results)
    already_checked = already_checked_count(quality_candidates)

    q1, q2, q3 = st.columns(3)
    q1.metric("Category + blog pages", len(quality_candidates))
    q2.metric("Already checked", already_checked)
    q3.metric("Remaining", len(quality_candidates) - already_checked)

    # If filter excluded everything, show WHY so the user can act.
    if not quality_candidates and results:
        from collections import Counter
        type_counts = Counter((r.get("page_type") or "missing") for r in results)
        wc_short = sum(
            1 for r in results
            if r.get("page_type") in ELIGIBLE_PAGE_TYPES
            and (r.get("word_count") or 0) <= MIN_WORD_COUNT
        )
        type_str = ", ".join(f"`{t}`: {n}" for t, n in type_counts.most_common())
        st.warning(
            f"**0 of {len(results)} audited pages match the quality-check filter.** "
            f"Filter requires `page_type` in ({', '.join(ELIGIBLE_PAGE_TYPES)}) "
            f"AND `word_count` > {MIN_WORD_COUNT}.\n\n"
            f"**Page types in audit_results:** {type_str}\n\n"
            + (
                f"**Note:** {wc_short} eligible-type pages were excluded for having "
                f"≤{MIN_WORD_COUNT} words. "
                if wc_short else ""
            )
            + (
                "If everything is `product` or `unknown`, the page-type classifier "
                "(utils/category_analyzer.py `classify_page_type`) is misclassifying — "
                "re-scrape with **Re-scrape ALL pages (force)** at the top to refresh."
            )
        )

    col_qgen, col_qinfo = st.columns([1, 2])
    with col_qgen:
        run_quality = st.button("Run AI quality check", type="primary", key="btn_quality_check")
    with col_qinfo:
        st.markdown(
            "<span style='font-size:0.75rem; color:#6b6b8a;'>"
            "Checks 5 pages per API call. ~10 seconds per batch. Results cached.</span>",
            unsafe_allow_html=True,
        )

    # Show any errors from a previous run — persisted so they survive st.rerun
    prev_errors = st.session_state.get("_quality_check_errors", [])
    if prev_errors:
        st.error(
            "Last AI quality check had errors:\n\n"
            + "\n".join(f"- Batch {b}: `{e}`" for b, e in prev_errors[:5])
            + ("\n\n_(showing first 5)_" if len(prev_errors) > 5 else "")
        )
        if st.button("Clear errors", key="btn_clear_quality_errors"):
            st.session_state.pop("_quality_check_errors", None)
            st.rerun()

    if run_quality:
        unchecked = pages_needing_check(quality_candidates)
        if not quality_candidates:
            st.warning(
                "No pages match the quality-check filter "
                "(category / blog / faq with >50 words). "
                "Run **Re-scrape ALL pages** at the top first."
            )
        elif not unchecked:
            st.success("All pages already checked!")
        else:
            with st.status(f"Checking {len(unchecked)} pages...", expanded=True) as qstatus:
                progress_q = st.progress(0)
                log_q = st.empty()

                def _on_batch_start(batch_num, total_batches, batch):
                    labels = ", ".join(
                        r["url"].split("/")[-1] or r["url"].split("/")[-2]
                        for r in batch
                    )
                    log_q.write(f"Batch {batch_num}/{total_batches}: {labels}")

                def _on_progress(frac):
                    progress_q.progress(frac)

                try:
                    run_errors = run_quality_batches(
                        unchecked,
                        on_batch_start=_on_batch_start,
                        on_progress=_on_progress,
                        cap=len(unchecked),  # interactive view: process all
                    )
                except Exception as e:
                    run_errors = [(0, str(e))]
                    st.error(f"Quality check failed before any batch: {e}")

                for batch_num, err in run_errors:
                    st.error(f"Batch {batch_num} failed: {err}")

                if run_errors:
                    qstatus.update(
                        label=f"Quality check finished with {len(run_errors)} batch error(s)",
                        state="error",
                        expanded=True,
                    )
                else:
                    qstatus.update(label="Quality check complete", state="complete", expanded=False)

            st.session_state["_quality_check_errors"] = run_errors
            if not run_errors:
                st.rerun()

    # Display quality results
    from utils.quality_check_runner import quality_key as _qk_pa
    quality_results = []
    for r in quality_candidates:
        qkey = _qk_pa(r["url"])
        if qkey in st.session_state:
            q = st.session_state[qkey]
            quality_results.append({
                "url": r["url"],
                "page_type": r.get("page_type", "?"),
                "word_count": r.get("word_count", 0),
                "verdict": q.get("verdict", "?"),
                "score": q.get("score", 0),
                "summary": q.get("summary", ""),
                "main_issues": q.get("main_issues", []),
                "specific_fixes": q.get("specific_fixes", []),
            })

    if quality_results:
        # Sort: REWRITE first, then IMPROVE, then KEEP
        verdict_order = {"REWRITE": 0, "IMPROVE": 1, "KEEP": 2}
        quality_results.sort(key=lambda x: (verdict_order.get(x["verdict"], 1), -x.get("word_count", 0)))

        # Summary counts
        rewrite_count = sum(1 for q in quality_results if q["verdict"] == "REWRITE")
        improve_count = sum(1 for q in quality_results if q["verdict"] == "IMPROVE")
        keep_count = sum(1 for q in quality_results if q["verdict"] == "KEEP")

        qc1, qc2, qc3 = st.columns(3)
        qc1.metric("REWRITE", rewrite_count)
        qc2.metric("IMPROVE", improve_count)
        qc3.metric("KEEP", keep_count)

        # Pagination
        QR_PER_PAGE = 15
        qr_total = len(quality_results)
        qr_max_pg = max(1, (qr_total + QR_PER_PAGE - 1) // QR_PER_PAGE)
        qr_pg = st.number_input("Page", min_value=1, max_value=qr_max_pg, value=1, key="quality_page")
        qr_start = (qr_pg - 1) * QR_PER_PAGE
        qr_visible = quality_results[qr_start:qr_start + QR_PER_PAGE]

        # Look-up table: normalized URL -> raw audit row, so we can wire
        # the same AI fix runner Quick Wins uses without re-querying.
        from utils.ui_helpers import normalize_url as _qr_nu, stable_hash as _qr_sh
        from utils.page_fix_runner import generate_ai_fixes_for_page, page_audit_to_page_dict
        from utils.page_deeplink import open_in_quick_wins
        _audit_by_url = {_qr_nu(r["url"]): r for r in results if r.get("url")}

        for q in qr_visible:
            verdict = q["verdict"]
            v_color = {"REWRITE": "#ff4455", "IMPROVE": "#ffaa33", "KEEP": "#33dd88"}.get(verdict, "#6b6b8a")
            score = q["score"]
            ptype = q["page_type"].upper()
            url_hash = _qr_sh(q["url"])
            ai_plan_present = f"_ai_plan_{url_hash}" in st.session_state

            st.markdown(
                f"<div style='background:#12121f; border-left:4px solid {v_color}; "
                f"border-radius:6px; padding:0.8rem; margin-bottom:0.5rem;'>"
                f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.3rem;'>"
                f"<div>"
                f"<span style='font-weight:800; color:{v_color}; font-size:1rem;'>{verdict}</span>"
                f"<span style='font-size:0.7rem; color:#6b6b8a; margin-left:0.5rem;'>{ptype} · {q['word_count']} words</span>"
                f"</div>"
                f"<span style='font-size:1.2rem; font-weight:800; color:{v_color};'>{score}/10</span>"
                f"</div>"
                f"<div style='font-size:0.9rem; color:#e8e8f0; margin-bottom:0.3rem;'>{q['url']}</div>"
                f"<div style='font-size:0.8rem; color:#9b9bb8;'>{q['summary']}</div>",
                unsafe_allow_html=True,
            )

            if q["main_issues"]:
                issues_html = " ".join(f"<span style='color:#ff4455; font-size:0.75rem;'>✗ {iss}</span><br>" for iss in q["main_issues"][:3])
                st.markdown(f"<div style='margin-top:0.3rem;'>{issues_html}</div>", unsafe_allow_html=True)

            if q["specific_fixes"]:
                fixes_html = " ".join(f"<span style='color:#c8b4ff; font-size:0.75rem;'>→ {fix}</span><br>" for fix in q["specific_fixes"][:3])
                st.markdown(f"<div>{fixes_html}</div>", unsafe_allow_html=True)

            # Action: rewrite this exact page via the same flow as Quick Wins
            audit_row = _audit_by_url.get(_qr_nu(q["url"]))
            if audit_row is not None and verdict in ("REWRITE", "IMPROVE"):
                btn_cols = st.columns([3, 3, 3, 3])
                with btn_cols[0]:
                    if ai_plan_present:
                        if st.button(
                            "🚀 Open in Quick Wins",
                            key=f"qq_open_{url_hash}",
                            use_container_width=True,
                        ):
                            open_in_quick_wins(q["url"])
                            st.rerun()
                    else:
                        if st.button(
                            "🤖 Rewrite with AI + open",
                            key=f"qq_gen_{url_hash}",
                            type="primary",
                            use_container_width=True,
                        ):
                            generate_ai_fixes_for_page(page_audit_to_page_dict(audit_row))
                            open_in_quick_wins(q["url"])
                            st.rerun()
                with btn_cols[1]:
                    if ai_plan_present:
                        if st.button(
                            "🔄 Regenerate AI fixes",
                            key=f"qq_regen_{url_hash}",
                            use_container_width=True,
                        ):
                            st.session_state.pop(f"_ai_plan_{url_hash}", None)
                            generate_ai_fixes_for_page(page_audit_to_page_dict(audit_row))
                            open_in_quick_wins(q["url"])
                            st.rerun()
                with btn_cols[2]:
                    # DIAGNOSTIC: re-scrape the LIVE page, replace audit
                    # data, and re-run quality check just for this URL.
                    # Tells the user definitively whether their Mshop
                    # push landed or not — if verdict flips from
                    # REWRITE → KEEP, the push worked and audit was just
                    # stale. If verdict stays REWRITE, the push didn't
                    # replace the live text.
                    if st.button(
                        "🔍 Re-scrape + re-check",
                        key=f"qq_recheck_{url_hash}",
                        use_container_width=True,
                        help="Fetches the LIVE page from mshop.se RIGHT NOW, "
                             "replaces the audit data with the fresh scrape, "
                             "and re-runs the AI quality check just on this "
                             "page. Use to verify whether your earlier "
                             "Mshop pushes actually replaced the text.",
                    ):
                        from utils.page_scraper import scrape_page
                        from utils.category_analyzer import classify_page_type
                        from utils.quality_check_runner import run_quality_batches, quality_key
                        from utils.persistence import save_key
                        with st.spinner(f"Re-scraping {q['url'][-50:]}…"):
                            fresh = scrape_page(q["url"])
                            cls = classify_page_type(q["url"], fresh)
                            fresh["page_type"] = cls.get("page_type", "unknown")
                            # Replace this URL's row in audit_results in place
                            for i, rr in enumerate(results):
                                if _qr_nu(rr.get("url", "")) == _qr_nu(q["url"]):
                                    fresh["url"] = rr.get("url", q["url"])
                                    # Carry over fields the scraper doesn't produce
                                    for carry in ("target_keywords", "cluster_keywords", "impressions", "clicks", "lost_clicks_estimate"):
                                        if carry in rr and carry not in fresh:
                                            fresh[carry] = rr[carry]
                                    results[i] = fresh
                                    break
                            st.session_state["audit_results"] = results
                            save_key("audit_results")
                        # Drop cached verdict so quality check re-runs
                        st.session_state.pop(quality_key(q["url"]), None)
                        with st.spinner("Re-running AI quality check on this page only…"):
                            errors = run_quality_batches(
                                [fresh],
                                cap=1,
                            )
                        if errors:
                            for bn, err in errors:
                                st.error(f"Quality check failed: {err}")
                        else:
                            st.success(
                                "Re-scrape + re-check done. Look for this page "
                                "again above — its verdict should reflect the "
                                "CURRENT live text on mshop.se. Reload the AI "
                                "Content Quality section to see the new verdict."
                            )

                        # ── PUSH-LOG DIAGNOSTIC ──
                        # Snapshot what we sent to Mshop and what Mshop
                        # replied so the user can see whether pushes
                        # actually landed. Persisted to session_state
                        # so the upcoming st.rerun() doesn't discard it.
                        try:
                            from utils.mshop_admin_api import read_push_log, lookup_url as _mlu
                            active = st.session_state.get("mshop_active_pages") or {}
                            page_info = _mlu(active, q["url"])
                            log = read_push_log(limit=200)
                            relevant = []
                            if page_info and isinstance(log, list):
                                pid = page_info.get("id")
                                ptype = page_info.get("type")
                                pid_field = {
                                    "category": "categoryId",
                                    "cms": "cmsPageId",
                                    "filterpage": "filterPageId",
                                }.get(ptype, "")
                                for entry in log:
                                    payload = entry.get("payload") or {}
                                    if pid_field and payload.get(pid_field) == pid:
                                        relevant.append(entry)
                            st.session_state["_qq_diag"] = {
                                "url": q["url"],
                                "page_info": page_info,
                                "entries": relevant[:5],
                            }
                        except Exception as _push_log_err:
                            st.session_state["_qq_diag"] = {
                                "url": q["url"],
                                "error": str(_push_log_err),
                            }

                        st.rerun()
                with btn_cols[3]:
                    status = "✓ AI fixes ready" if ai_plan_present else "○ No AI fixes generated yet"
                    st.markdown(
                        f"<div style='padding-top:0.4rem; font-size:0.7rem; color:#9b9bb8;'>{status}</div>",
                        unsafe_allow_html=True,
                    )

            st.markdown("</div>", unsafe_allow_html=True)

    # ── Results display ───────────────────────────────────────────
    st.markdown("---")

    # Summary table
    st.markdown("### Overview")

    summary_rows = []
    for r in results:
        ptype = r.get("page_type", "unknown")
        label, _ = PAGE_TYPE_LABELS.get(ptype, ("?", "#6b6b8a"))
        summary_rows.append({
            "Page": shorten_url(r["url"]),
            "Type": label,
            "Meta Score": r.get("meta_score"),
            "Content Score": r.get("content_score"),
            "Title": (r.get("title") or "")[:60],
            "Title Lgd": r.get("title_length", 0),
            "Desc Lgd": r.get("description_length", 0),
            "Lost Clicks": r.get("lost_clicks_estimate", 0),
            "Top Keywords": ", ".join(r.get("target_keywords", [])[:3]),
        })

    summary_df = pd.DataFrame(summary_rows)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Detailed per-page view with pagination + search
    st.markdown("### Detailed Audit")

    search_url = st.text_input("Search URL", key="audit_search", placeholder="Type part of URL to filter (e.g. sexleksaker-for-man)")
    if search_url:
        from utils.ui_helpers import normalize_url as _nu_search
        search_norm = _nu_search(search_url) if search_url.startswith("http") else search_url.lower().strip()
        filtered_results = [r for r in results if search_norm in r.get("url", "").lower()]
    else:
        filtered_results = results

    AUDIT_PER_PAGE = 10
    total_audit_pages = max(1, (len(filtered_results) + AUDIT_PER_PAGE - 1) // AUDIT_PER_PAGE)
    audit_page = st.number_input(
        "Page", min_value=1, max_value=total_audit_pages, value=1, key="audit_detail_page"
    )
    start_idx = (audit_page - 1) * AUDIT_PER_PAGE
    visible_results = filtered_results[start_idx:start_idx + AUDIT_PER_PAGE]
    st.markdown(f"**Showing {start_idx+1}-{min(start_idx+AUDIT_PER_PAGE, len(filtered_results))} of {len(filtered_results)} pages**")

    for r in visible_results:
        url_short = r["url"].replace("https://", "").replace("http://", "")
        meta_score = r.get("meta_score")
        content_score = r.get("content_score")
        lost = r.get("lost_clicks_estimate", 0)
        ptype = r.get("page_type", "unknown")
        type_label, type_color = PAGE_TYPE_LABELS.get(ptype, ("?", "#6b6b8a"))

        expander_label = f"{url_short}  |  {type_label}  |  Meta: {meta_score or '?'}/100"
        if content_score is not None:
            expander_label += f"  |  Content: {content_score}/100"
        expander_label += f"  |  Lost clicks: {lost:,}"

        with st.expander(expander_label):

            # ── Action bar: jump straight to AI fixes for this page ──
            # Single source of truth: both the generation flow and the
            # cross-view jump live in utils/. No duplicated orchestration.
            from utils.page_fix_runner import generate_ai_fixes_for_page, page_audit_to_page_dict
            from utils.page_deeplink import open_in_quick_wins
            from utils.ui_helpers import stable_hash as _qa_sh
            _ai_plan_present = f"_ai_plan_{_qa_sh(r['url'])}" in st.session_state

            act1, act2, act3 = st.columns([2, 2, 3])
            with act1:
                if _ai_plan_present:
                    if st.button("🚀 Open in Quick Wins", key=f"qa_open_{_qa_sh(r['url'])}", use_container_width=True):
                        open_in_quick_wins(r["url"])
                        st.rerun()
                else:
                    if st.button("🤖 Generate AI fixes + open", key=f"qa_gen_{_qa_sh(r['url'])}", type="primary", use_container_width=True):
                        generate_ai_fixes_for_page(page_audit_to_page_dict(r))
                        open_in_quick_wins(r["url"])
                        st.rerun()
            with act2:
                if _ai_plan_present:
                    if st.button("🔄 Regenerate AI fixes", key=f"qa_regen_{_qa_sh(r['url'])}", use_container_width=True):
                        # Drop cached plan so the runner regenerates fresh
                        st.session_state.pop(f"_ai_plan_{_qa_sh(r['url'])}", None)
                        generate_ai_fixes_for_page(page_audit_to_page_dict(r))
                        open_in_quick_wins(r["url"])
                        st.rerun()
            with act3:
                status = "✓ AI fixes ready — click Open to review + push to Mshop" if _ai_plan_present else "○ No AI fixes generated yet for this page"
                st.markdown(
                    f"<div style='padding-top:0.4rem; font-size:0.75rem; color:#9b9bb8;'>{status}</div>",
                    unsafe_allow_html=True,
                )

            # Data quality warnings
            dw = r.get("_data_warnings", [])
            if dw:
                st.warning("**Data quality:** " + " | ".join(dw))

            # Page type badge
            st.markdown(
                f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:{type_color}; "
                f"background:#0d0d15; display:inline-block; padding:3px 10px; border:1px solid {type_color}; "
                f"border-radius:4px; margin-bottom:1rem;'>{type_label} PAGE</div>",
                unsafe_allow_html=True
            )

            left, right = st.columns([3, 2])

            with left:
                # Current meta
                st.markdown("#### Current Meta")

                title = r.get("title") or "_(not found)_"
                desc = r.get("meta_description") or "_(not found)_"
                t_len = r.get("title_length", 0)
                d_len = r.get("description_length", 0)

                t_color = "#33dd88" if 50 <= t_len <= 60 else "#ffaa33" if 30 <= t_len < 50 else "#ff4455"
                d_color = "#33dd88" if 140 <= d_len <= 165 else "#ffaa33" if 80 <= d_len < 140 else "#ff4455"

                st.markdown(f"""
                <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1rem; margin-bottom:0.5rem;">
                    <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#5533ff; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.3rem;">
                        TITLE <span style="color:{t_color};">({t_len} chars)</span>
                    </div>
                    <div style="font-size:0.9rem; color:#e8e8f0;">{title}</div>
                </div>
                <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1rem;">
                    <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#5533ff; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.3rem;">
                        META DESCRIPTION <span style="color:{d_color};">({d_len} chars)</span>
                    </div>
                    <div style="font-size:0.85rem; color:#e8e8f0;">{desc}</div>
                </div>
                """, unsafe_allow_html=True)

                # H1 and headings
                if r.get("h1"):
                    st.markdown(f"""
                    <div style="margin-top:0.5rem; background:#0f0f1a; border:1px solid #1a1a2e; border-radius:6px; padding:0.7rem;">
                        <span style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#6b6b8a; text-transform:uppercase;">H1: </span>
                        <span style="font-size:0.85rem;">{r.get('h1')}</span>
                    </div>
                    """, unsafe_allow_html=True)

                if r.get("h2s"):
                    h2_list = " ".join(r["h2s"][:5])
                    st.markdown(f"<div style='font-size:0.75rem; color:#6b6b8a; margin-top:0.5rem; font-family:\"IBM Plex Mono\",monospace;'>H2: {h2_list}</div>", unsafe_allow_html=True)

                # ── Content deep audit ─────────────────────────────
                cat_audit = r.get("content_audit")
                if cat_audit:
                    st.markdown("---")
                    st.markdown("#### Deep Content Analysis")

                    stats = cat_audit.get("content_stats", {})
                    kw_cov = cat_audit.get("keyword_coverage", {})
                    topic_cov = cat_audit.get("topic_coverage", {})
                    linking = cat_audit.get("linking", {})
                    trust = cat_audit.get("trust", {})

                    # ── Score overview ──
                    s1, s2, s3, s4, s5 = st.columns(5)
                    with s1:
                        intro_w = stats.get("intro_words", 0)
                        intro_color = "#33dd88" if intro_w >= 80 else "#ffaa33" if intro_w >= 30 else "#ff4455"
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.4rem; font-weight:700; color:{intro_color};'>{intro_w}</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>INTRO WORDS</div></div>", unsafe_allow_html=True)
                    with s2:
                        bottom_w = stats.get("bottom_words", 0)
                        bottom_color = "#33dd88" if bottom_w >= 150 else "#ffaa33" if bottom_w >= 50 else "#ff4455"
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.4rem; font-weight:700; color:{bottom_color};'>{bottom_w}</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>BOTTOM WORDS</div></div>", unsafe_allow_html=True)
                    with s3:
                        tp = topic_cov.get("coverage_pct", 0)
                        tp_color = "#33dd88" if tp >= 60 else "#ffaa33" if tp >= 30 else "#ff4455"
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.4rem; font-weight:700; color:{tp_color};'>{tp:.0f}%</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>TOPIC MATCH</div></div>", unsafe_allow_html=True)
                    with s4:
                        kp = kw_cov.get("coverage_pct", 0)
                        kp_color = "#33dd88" if kp >= 60 else "#ffaa33" if kp >= 30 else "#ff4455"
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.4rem; font-weight:700; color:{kp_color};'>{kp:.0f}%</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>KW COVERAGE</div></div>", unsafe_allow_html=True)
                    with s5:
                        tpct = trust.get("trust_pct", 0)
                        t_color = "#33dd88" if tpct >= 60 else "#ffaa33" if tpct >= 30 else "#ff4455"
                        st.markdown(f"<div style='text-align:center;'><div style='font-size:1.4rem; font-weight:700; color:{t_color};'>{tpct:.0f}%</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>TRUST/E-E-A-T</div></div>", unsafe_allow_html=True)

                    # ── Feature flags row ──
                    has_faq = stats.get("has_faq", False)
                    has_guide = stats.get("has_buying_guide", False)
                    faq_c = "#33dd88" if has_faq else "#ff4455"
                    guide_c = "#33dd88" if has_guide else "#ff4455"
                    bc_c = "#33dd88" if trust.get("has_breadcrumb") else "#ff4455"
                    rev_c = "#33dd88" if trust.get("has_reviews") else "#ff4455"
                    st.markdown(
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; margin:0.5rem 0; padding:0.5rem; background:#0d0d15; border-radius:4px;'>"
                        f"FAQ: <span style='color:{faq_c};'>{'OK' if has_faq else 'MISSING'}</span> &nbsp;|&nbsp; "
                        f"Buying guide: <span style='color:{guide_c};'>{'OK' if has_guide else 'MISSING'}</span> &nbsp;|&nbsp; "
                        f"Breadcrumb: <span style='color:{bc_c};'>{'OK' if trust.get('has_breadcrumb') else 'MISSING'}</span> &nbsp;|&nbsp; "
                        f"Reviews: <span style='color:{rev_c};'>{'OK' if trust.get('has_reviews') else 'MISSING'}</span> &nbsp;|&nbsp; "
                        f"H2: {stats.get('editorial_h2_count', 0)} &nbsp;|&nbsp; "
                        f"Products: {stats.get('product_count', 0)}</div>",
                        unsafe_allow_html=True
                    )

                    # ── Topic coverage detail ──
                    subtopics = topic_cov.get("subtopics", [])
                    if subtopics:
                        st.markdown(
                            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                            f"text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                            f"TOPIC CLUSTER COVERAGE ({topic_cov.get('covered_topics',0)}/{topic_cov.get('total_topics',0)} topics)</div>",
                            unsafe_allow_html=True
                        )
                        for sub in subtopics:
                            status = sub["status"]
                            if status == "covered":
                                icon, scolor = "OK", "#33dd88"
                            elif status == "partial":
                                icon, scolor = "PARTIAL", "#ffaa33"
                            else:
                                icon, scolor = "MISSING", "#ff4455"
                            queries_str = ", ".join(sub["queries"][:3])
                            if sub["query_count"] > 3:
                                queries_str += f" +{sub['query_count']-3} more"
                            st.markdown(
                                f"<div style='padding:3px 0; font-size:0.8rem;'>"
                                f"<span style='color:{scolor}; font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; font-weight:600; min-width:70px; display:inline-block;'>[{icon}]</span> "
                                f"<span style='color:#e8e8f0; font-weight:500;'>{sub['topic']}</span> "
                                f"<span style='color:#6b6b8a; font-size:0.72rem;'>({queries_str})</span></div>",
                                unsafe_allow_html=True
                            )

                    # ── KW placement quality ──
                    kw_h1 = kw_cov.get("in_h1", 0)
                    kw_h2 = kw_cov.get("in_h2", 0)
                    kw_intro = kw_cov.get("in_intro", 0)
                    st.markdown(
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#6b6b8a; margin:0.3rem 0;'>"
                        f"KW in H1: <span style='color:{'#33dd88' if kw_h1 > 0 else '#ff4455'};'>{kw_h1}</span> &nbsp; "
                        f"KW in H2: <span style='color:{'#33dd88' if kw_h2 > 0 else '#ffaa33'};'>{kw_h2}</span> &nbsp; "
                        f"KW in intro: <span style='color:{'#33dd88' if kw_intro > 0 else '#ff4455'};'>{kw_intro}</span></div>",
                        unsafe_allow_html=True
                    )

                    # ── Internal linking detail ──
                    missing_crosslinks = linking.get("missing_crosslinks", [])
                    if missing_crosslinks or linking.get("category_links", 0) < 2:
                        st.markdown(
                            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                            f"text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                            f"INTERNAL LINKING ({linking.get('total_internal',0)} links, {linking.get('category_links',0)} to categories)</div>",
                            unsafe_allow_html=True
                        )
                        if missing_crosslinks:
                            st.markdown(f"**{len(missing_crosslinks)} related pages missing link:**")
                            for ml in missing_crosslinks[:5]:
                                short = ml["url"].replace("https://", "").replace("http://", "")
                                shared = ", ".join(ml["shared_topics"][:2])
                                st.markdown(
                                    f"<div style='font-size:0.8rem; padding:2px 0;'>"
                                    f"<span style='color:#ff8888;'>Missing:</span> <code>{short}</code> "
                                    f"<span style='color:#6b6b8a;'>(shared: {shared})</span></div>",
                                    unsafe_allow_html=True
                                )

                    # ── Link fix suggestions (WP1) ──
                    link_fixes = linking.get("link_fix_suggestions", [])
                    if link_fixes:
                        st.markdown(
                            "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                            "text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                            "LINK FIX SUGGESTIONS</div>",
                            unsafe_allow_html=True
                        )
                        for lf in link_fixes[:5]:
                            pri = lf.get("priority", "medium").upper()
                            pri_color = "#ff4455" if pri == "HIGH" else "#ffaa33" if pri == "MEDIUM" else "#6b6b8a"
                            target_short = lf["target_url"].replace("https://", "").replace("http://", "")
                            placement = lf.get("placement_detail") or lf.get("placement", "bottom_text")
                            st.markdown(
                                f"<div style='background:#0d0d15; border:1px solid #1e1e2e; border-radius:6px; padding:0.6rem; margin-bottom:0.4rem; font-size:0.8rem;'>"
                                f"<span style='color:{pri_color}; font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem;'>[{pri}]</span> "
                                f"Add link to: <code>{target_short}</code><br>"
                                f"<span style='color:#6b6b8a;'>Anchor:</span> <span style='color:#33dd88;'>\"{lf['suggested_anchor']}\"</span><br>"
                                f"<span style='color:#6b6b8a;'>Place in:</span> {placement}<br>"
                                f"<span style='color:#6b6b8a;'>Reason:</span> {lf['reason']}</div>",
                                unsafe_allow_html=True
                            )

                    # ── Anchor text issues (WP1) ──
                    sem_val = linking.get("semantic_validation", {})
                    anchor_mismatches = sem_val.get("anchor_mismatches", [])
                    if anchor_mismatches:
                        st.markdown(
                            "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                            "text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                            "ANCHOR TEXT OPTIMIZATION</div>",
                            unsafe_allow_html=True
                        )
                        for am in anchor_mismatches[:5]:
                            st.markdown(
                                f"<div style='font-size:0.8rem; padding:3px 0;'>"
                                f"<code>{am['url'][:50]}</code><br>"
                                f"<span style='color:#ff8888;'>Current:</span> \"{am['current_anchor']}\" "
                                f"<span style='color:#33dd88;'>Suggested:</span> \"{am['suggested_anchor']}\"</div>",
                                unsafe_allow_html=True
                            )

                    # ── Product alignment (WP2) ──
                    prod_align = cat_audit.get("product_alignment", {})
                    if prod_align and prod_align.get("alignment_pct") is not None:
                        apct = prod_align["alignment_pct"]
                        a_color = "#33dd88" if apct >= 70 else "#ffaa33" if apct >= 40 else "#ff4455"
                        st.markdown(
                            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                            f"text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                            f"PRODUCT-CLUSTER ALIGNMENT "
                            f"<span style='color:{a_color};'>{apct:.0f}%</span> "
                            f"({prod_align.get('total_checked', 0)} products checked)</div>",
                            unsafe_allow_html=True
                        )
                        misplaced = prod_align.get("misplaced", [])
                        if misplaced:
                            for mp in misplaced[:5]:
                                st.markdown(
                                    f"<div style='font-size:0.8rem; padding:2px 0;'>"
                                    f"<span style='color:#ff8888;'>Misplaced:</span> {mp['name'][:50]} "
                                    f"<span style='color:#6b6b8a;'>({mp['reason']})</span></div>",
                                    unsafe_allow_html=True
                                )

                    # ── Trust signals detail ──
                    trust_signals_found = trust.get("signals_found", [])
                    schema_types = trust.get("schema_types", [])
                    st.markdown(
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                        f"text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                        f"TRUST & E-E-A-T ({trust.get('trust_score',0)}/{trust.get('trust_max',0)} signals)</div>",
                        unsafe_allow_html=True
                    )
                    if schema_types:
                        st.markdown(f"**Schema types:** {', '.join(schema_types)}")
                    else:
                        st.markdown("<span style='color:#ff4455;'>No structured data found</span>", unsafe_allow_html=True)
                    if trust_signals_found:
                        for sig in trust_signals_found:
                            st.markdown(f"<div style='font-size:0.8rem; color:#33dd88; padding:1px 0;'>+ {sig}</div>", unsafe_allow_html=True)
                    missing_trust = []
                    if not trust.get("has_breadcrumb"):
                        missing_trust.append("BreadcrumbList schema")
                    if not trust.get("has_reviews"):
                        missing_trust.append("Reviews/ratings")
                    if not trust.get("has_last_modified"):
                        missing_trust.append("Update date")
                    if not trust.get("has_org_schema"):
                        missing_trust.append("Organization schema")
                    for mt in missing_trust:
                        st.markdown(f"<div style='font-size:0.8rem; color:#ff4455; padding:1px 0;'>- {mt}</div>", unsafe_allow_html=True)

                    # ── E-E-A-T depth (WP3) ──
                    eeat = cat_audit.get("eeat_depth", {})
                    if eeat:
                        st.markdown(
                            "<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.7rem; color:#5533ff; "
                            "text-transform:uppercase; letter-spacing:0.1em; margin:0.8rem 0 0.3rem;'>"
                            "E-E-A-T DEPTH ANALYSIS</div>",
                            unsafe_allow_html=True
                        )
                        e_cols = st.columns(3)
                        # Credibility
                        cred = eeat.get("credibility", {})
                        with e_cols[0]:
                            cp = cred.get("credibility_pct", 0)
                            c_color = "#33dd88" if cp >= 50 else "#ffaa33" if cp >= 25 else "#ff4455"
                            st.markdown(f"<div style='text-align:center;'><div style='font-size:1.2rem; font-weight:700; color:{c_color};'>{cp}%</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>CREDIBILITY</div></div>", unsafe_allow_html=True)
                        # Topical authority
                        ta = eeat.get("topical_authority", {})
                        with e_cols[1]:
                            ta_score = ta.get("authority_score", 0)
                            ta_max = ta.get("authority_max", 3)
                            pages_in = ta.get("pages_in_cluster", 0)
                            ta_color = "#33dd88" if ta_score >= 2 else "#ffaa33" if ta_score >= 1 else "#ff4455"
                            st.markdown(f"<div style='text-align:center;'><div style='font-size:1.2rem; font-weight:700; color:{ta_color};'>{ta_score}/{ta_max}</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>AUTHORITY ({pages_in} pages)</div></div>", unsafe_allow_html=True)
                        # Trust flow
                        tf = eeat.get("trust_flow", {})
                        with e_cols[2]:
                            rd = tf.get("referring_domains", 0)
                            tf_score = tf.get("trust_flow_score", 0)
                            tf_color = "#33dd88" if tf_score >= 2 else "#ffaa33" if tf_score >= 1 else "#ff4455"
                            st.markdown(f"<div style='text-align:center;'><div style='font-size:1.2rem; font-weight:700; color:{tf_color};'>{rd}</div><div style='font-size:0.6rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace;'>REFERRING DOMAINS</div></div>", unsafe_allow_html=True)

                        # Detail signals
                        all_eeat_signals = cred.get("signals", []) + ta.get("signals", []) + tf.get("signals", [])
                        for sig in all_eeat_signals:
                            st.markdown(f"<div style='font-size:0.78rem; color:#9b9bb8; padding:1px 0;'>  {sig}</div>", unsafe_allow_html=True)

                    # ── Missing keywords ──
                    missing_kws = kw_cov.get("missing", [])
                    if missing_kws:
                        kw_badges = " ".join([
                            f"<span style='background:#1a0a0a; border:1px solid #ff4455; border-radius:4px; padding:2px 6px; font-size:0.7rem; color:#ff8888; margin:2px; display:inline-block;'>{kw}</span>"
                            for kw in missing_kws[:10]
                        ])
                        st.markdown(f"<div style='margin-top:0.5rem;'><span style='font-size:0.7rem; color:#6b6b8a;'>Missing keywords:</span><br>{kw_badges}</div>", unsafe_allow_html=True)

                    # ── Recommendations ──
                    recs = cat_audit.get("recommendations", [])
                    if recs:
                        st.markdown("**Recommendations:**")
                        for rec in recs:
                            st.markdown(f"<div style='font-size:0.82rem; color:#c8b4ff; padding:2px 0;'>-> {rec}</div>", unsafe_allow_html=True)

            with right:
                st.markdown("#### Issues")
                issues = r.get("issues", [])
                if not issues:
                    st.markdown("<div style='color:#33dd88; font-size:0.85rem;'>No critical issues</div>", unsafe_allow_html=True)
                else:
                    for issue in issues:
                        st.markdown(
                            f"{issue_badge(issue['type'])} <span style='font-size:0.82rem; color:#c8b4ff;'>[{issue['field']}]</span> "
                            f"<span style='font-size:0.82rem; color:#e8e8f0;'>{issue['msg']}</span>",
                            unsafe_allow_html=True
                        )

                st.markdown("#### GSC Keywords")
                kws = r.get("target_keywords", [])
                for kw in kws:
                    st.markdown(
                        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.75rem; color:#c8b4ff; padding:2px 0;'>-> {kw}</div>",
                        unsafe_allow_html=True
                    )

                # Show cluster keywords if different from GSC keywords
                cluster_kws = r.get("cluster_keywords", [])
                extra_cluster = [k for k in cluster_kws if k not in kws][:5]
                if extra_cluster:
                    st.markdown("#### Cluster Keywords")
                    for kw in extra_cluster:
                        st.markdown(
                            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.75rem; color:#9b9bb8; padding:2px 0;'>-> {kw}</div>",
                            unsafe_allow_html=True
                        )

                st.markdown("#### Page Statistics")
                st.markdown(f"""
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.72rem; color:#6b6b8a; line-height:1.9;">
                    Words on page: {r.get('word_count', '?')}<br>
                    Internal links: {r.get('internal_links', '?')}<br>
                    Images w/o alt: {r.get('images_without_alt', '?')}<br>
                    Schema: {', '.join(r.get('schema_types', [])) or 'None'}<br>
                    Impressions: {r.get('impressions', 0):,}<br>
                    Clicks: {r.get('clicks', 0):,}
                </div>
                """, unsafe_allow_html=True)

                # Authority warning for high-value pages
                if "page_authority" in st.session_state:
                    auth = st.session_state["page_authority"]
                    from utils.ui_helpers import normalize_url as _nu
                    page_auth = auth[auth["page"].apply(_nu) == _nu(r["url"])]
                    if not page_auth.empty:
                        rd = page_auth.iloc[0].get("referring_domains", 0)
                        risk = page_auth.iloc[0].get("change_risk", "Unknown")
                        if rd > 5:
                            risk_color = "#ff4455" if risk == "HIGH" else "#ffaa33" if risk == "MEDIUM" else "#33dd88"
                            st.markdown(
                                f"<div style='margin-top:0.5rem; padding:0.5rem; background:#1a0a0a; border:1px solid {risk_color}; border-radius:6px;'>"
                                f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:{risk_color};'>BACKLINK RISK: {risk}</div>"
                                f"<div style='font-size:0.75rem; color:#e8e8f0;'>{rd} referring domains - be careful with URL changes</div></div>",
                                unsafe_allow_html=True
                            )

            # Send to content generator button
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(f"Generate optimized content for this page", key=f"gen_{r['url']}"):
                st.session_state["generate_for_url"] = r["url"]
                st.session_state["selected_audit"] = r
                st.info("-> Go to Content Generator to generate content")
