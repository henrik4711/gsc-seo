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
        from utils.ui_helpers import stable_hash as _rc_sh
        from utils.quality_check_runner import quality_key as _rc_qk
        before = Counter((r.get("page_type") or "missing") for r in results)
        changed = 0
        # Track which URLs flipped type so we can drop their per-URL caches
        # (quality verdict, plan, bottom text, intro). Keeping verdicts
        # generated under the wrong page-type assumption leads to confusing
        # stale data — e.g. a product page still showing "REWRITE" from
        # when it was misclassified as a category.
        flipped_urls = []
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
                        flipped_urls.append(r.get("url", ""))
                except Exception:
                    pass

            # Drop per-URL AI caches for pages that flipped type — the
            # cached verdict/plan/text was generated under the wrong
            # type-assumption and would mislead the user.
            import os as _os_pc
            from utils.persistence import AI_CACHE_DIR as _ACD_pc
            for _u in flipped_urls:
                if not _u:
                    continue
                _h = _rc_sh(_u)
                _per_url_keys = [
                    _rc_qk(_u),
                    f"_ai_plan_{_h}",
                    f"_bottom_text_{_h}",
                    f"_intro_text_{_h}",
                ]
                for _k in _per_url_keys:
                    st.session_state.pop(_k, None)
                    _p = _os_pc.path.join(_ACD_pc, f"{_k}.json")
                    if _os_pc.path.exists(_p):
                        try:
                            _os_pc.remove(_p)
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

    # Diagnostic from "🔍 Re-scrape + re-check" is rendered INLINE under
    # the button that triggered it (further down in this section), not at
    # the top — otherwise users with a 50-deep card list never see the
    # output. Just hint here that one is available if it's set:
    if st.session_state.get("_qq_diag"):
        _diag_url = st.session_state["_qq_diag"].get("url", "?")
        st.info(
            f"🔍 Diagnostic available for `{_diag_url}` — scroll down to that card to see "
            "the new verdict + push log."
        )

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

        # ── Re-check ALL flagged pages (cache-bypass scrape + fresh verdict) ──
        # Many earlier REWRITE verdicts were false positives caused by the
        # quality check measuring whole-page word count (incl. product grid)
        # instead of editorial text. After fixing that bug we want a way to
        # re-evaluate every flagged page in one shot — so the user sees
        # which pages were actually bad vs. which were just mis-measured.
        # Iteration is rerun-based: process 1 page per rerun so the spinner
        # stays responsive and the user can stop mid-run.
        _recheck_state_key = "_recheck_all_state"
        _recheck_state = st.session_state.get(_recheck_state_key) or {}
        _recheck_running = bool(_recheck_state.get("running"))

        from utils.ui_helpers import normalize_url as _qr_nu_top
        _audit_by_url_top = {_qr_nu_top(r["url"]): r for r in results if r.get("url")}

        # Re-check history: URLs already re-checked previously, persisted
        # to disk so we can skip them if user clicks Re-check ALL again.
        # Stored as list, used as set here for fast membership test.
        _recheck_history = set(st.session_state.get("_recheck_history") or [])
        # Failure counter for Fix ALL — pages that fail twice get
        # auto-excluded from future runs so they don't keep crashing
        # the batch. {url: count}, persisted.
        _fix_fail_counts = dict(st.session_state.get("_fix_failure_count") or {})
        _MAX_FAILURES = 2

        # Detect SILENT crashes: if /data/_fix_in_progress.json exists
        # AND we're not currently running, that URL must have been
        # processing when Streamlit dropped its session. Bump its
        # failure counter and clear the marker — same effect as a real
        # exception would have had.
        import os as _os_ip, json as _json_ip
        _IP_FILE = "/data/_fix_in_progress.json"
        if not _recheck_running and _os_ip.path.exists(_IP_FILE):
            try:
                with open(_IP_FILE, "r", encoding="utf-8") as _ipf:
                    _silent_url = (_json_ip.load(_ipf) or {}).get("url")
                if _silent_url:
                    _fix_fail_counts[_silent_url] = _fix_fail_counts.get(_silent_url, 0) + 1
                    st.session_state["_fix_failure_count"] = _fix_fail_counts
                    try:
                        from utils.persistence import save_key as _sk_silent
                        _sk_silent("_fix_failure_count")
                    except Exception:
                        pass
                    try:
                        _os_ip.remove(_IP_FILE)
                    except Exception:
                        pass
            except Exception:
                pass

        rc_col1, rc_col2, rc_col3 = st.columns([2, 2, 2])
        if not _recheck_running:
            with rc_col1:
                # All flagged URLs
                _all_flagged = [
                    q["url"] for q in quality_results
                    if q["verdict"] in ("REWRITE", "IMPROVE")
                ]
                # Filter out ones already re-checked previously
                _eligible_urls = [u for u in _all_flagged if u not in _recheck_history]
                _skipped_count = len(_all_flagged) - len(_eligible_urls)
                _btn_label = (
                    f"🔄 Re-check {len(_eligible_urls)} pending"
                    + (f" (skipping {_skipped_count} already done)" if _skipped_count else "")
                    if _eligible_urls
                    else "🔄 Re-check ALL flagged (all already done)"
                )
                if st.button(
                    _btn_label,
                    key="recheck_all_btn",
                    type="primary",
                    use_container_width=True,
                    disabled=not _eligible_urls,
                    help="Re-scrapes every REWRITE+IMPROVE page that hasn't been "
                         "re-checked yet, with cache-bypass headers. Skips pages "
                         "already in the re-check history (persisted across "
                         "Railway restarts). Click 'Clear re-check history' to "
                         "force re-doing everything from scratch.",
                ):
                    st.session_state[_recheck_state_key] = {
                        "running": True,
                        "pending_urls": list(_eligible_urls),
                        "done_urls": [],
                        "errors": [],
                        "before": {q["url"]: q["verdict"] for q in quality_results if q["url"] in _eligible_urls},
                        "started_at": time.time(),
                    }
                    st.rerun()
            with rc_col2:
                # Show last-run summary if one finished recently
                _last = st.session_state.get("_recheck_all_last_summary")
                if _last:
                    flipped = _last.get("flipped", 0)
                    total = _last.get("total", 0)
                    st.caption(
                        f"Last re-check: {flipped}/{total} pages flipped to "
                        f"better verdict ({_last.get('seconds', 0):.0f}s)"
                    )
                # History stats + clear button
                if _recheck_history:
                    st.caption(
                        f"Re-check history: {len(_recheck_history)} URLs already done"
                    )
                    if st.button(
                        "🗑 Clear re-check history",
                        key="recheck_clear_history",
                        help="Wipes the persisted set of already-re-checked URLs "
                             "so the next Re-check ALL run starts fresh.",
                    ):
                        st.session_state["_recheck_history"] = []
                        from utils.persistence import save_key as _sk_clear
                        try:
                            _sk_clear("_recheck_history")
                        except Exception:
                            pass
                        st.rerun()
            with rc_col3:
                # "Seed" history with all URLs that already have a verdict.
                # Useful right now: user re-scraped ~120 pages BEFORE the
                # history-tracking was added, so those 120 aren't in the
                # set yet. Clicking this once adds every currently-checked
                # URL to history, so next Re-check ALL run only processes
                # NEW flagged pages.
                _flagged_not_in_history = [
                    q["url"] for q in quality_results
                    if q["verdict"] in ("REWRITE", "IMPROVE")
                    and q["url"] not in _recheck_history
                ]
                if _flagged_not_in_history:
                    if st.button(
                        f"✓ Mark all {len(_flagged_not_in_history)} flagged as re-checked",
                        key="recheck_mark_done",
                        help="Adds every flagged URL with a current verdict to "
                             "re-check history. Use this if you've already "
                             "re-checked them via the per-page button (or in "
                             "an earlier batch run before history tracking was "
                             "added). Future Re-check ALL runs will skip them.",
                    ):
                        _h = list(_recheck_history)
                        for u in _flagged_not_in_history:
                            if u not in _h:
                                _h.append(u)
                        st.session_state["_recheck_history"] = _h
                        from utils.persistence import save_key as _sk_mark
                        try:
                            _sk_mark("_recheck_history")
                        except Exception:
                            pass
                        st.success(f"Marked {len(_flagged_not_in_history)} URLs as re-checked.")
                        st.rerun()
        else:
            # Live progress while running
            pending = _recheck_state.get("pending_urls") or []
            done = _recheck_state.get("done_urls") or []
            errors = _recheck_state.get("errors") or []
            total = len(pending) + len(done)
            elapsed = time.time() - (_recheck_state.get("started_at") or time.time())
            with rc_col1:
                pct = (len(done) / max(total, 1)) * 100
                st.markdown(
                    f"<div style='background:#0d0d15; border:2px solid #5533ff; "
                    f"border-radius:6px; padding:0.6rem;'>"
                    f"<div style='font-size:0.85rem; color:#c8b4ff; font-weight:700;'>"
                    f"Re-checking {len(done)}/{total} ({pct:.0f}%)</div>"
                    f"<div style='font-size:0.7rem; color:#9b9bb8;'>"
                    f"Elapsed: {elapsed:.0f}s · Errors: {len(errors)}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with rc_col2:
                if st.button(
                    "⏸ Stop re-check",
                    key="recheck_stop_btn",
                    use_container_width=True,
                ):
                    st.session_state[_recheck_state_key] = {**_recheck_state, "running": False}
                    st.rerun()

            # Process the next page in the queue and trigger another rerun
            if pending:
                next_url = pending[0]
                with st.spinner(f"Re-checking {next_url[-50:]}…"):
                    try:
                        from utils.page_scraper import scrape_page
                        from utils.category_analyzer import classify_page_type
                        from utils.quality_check_runner import run_quality_batches, quality_key as _qk_loop
                        from utils.persistence import save_key
                        fresh = scrape_page(next_url, bypass_cache=True)
                        cls = classify_page_type(next_url, fresh)
                        fresh["page_type"] = cls.get("page_type", "unknown")
                        # Replace in audit_results in place
                        for i, rr in enumerate(results):
                            if _qr_nu_top(rr.get("url", "")) == _qr_nu_top(next_url):
                                fresh["url"] = rr.get("url", next_url)
                                for carry in ("target_keywords", "cluster_keywords",
                                              "impressions", "clicks", "lost_clicks_estimate"):
                                    if carry in rr and carry not in fresh:
                                        fresh[carry] = rr[carry]
                                results[i] = fresh
                                break
                        st.session_state["audit_results"] = results
                        # Drop cached verdict so it re-runs
                        st.session_state.pop(_qk_loop(next_url), None)
                        # Re-run quality check on JUST this URL
                        _errs = run_quality_batches([fresh], cap=1)
                        if _errs:
                            for _bn, _err in _errs:
                                _recheck_state["errors"].append(f"{next_url}: {_err}")
                    except Exception as _e:
                        _recheck_state["errors"].append(f"{next_url}: {type(_e).__name__}: {_e}")
                _recheck_state["pending_urls"] = pending[1:]
                _recheck_state["done_urls"] = done + [next_url]
                st.session_state[_recheck_state_key] = _recheck_state
                # Persist updated audit_results so a refresh doesn't lose progress
                try:
                    from utils.persistence import save_key as _sk
                    _sk("audit_results")
                except Exception:
                    pass
                # Add to persistent re-check history so we don't redo this URL
                # on the next Re-check ALL run (survives Railway restart).
                _hist = list(st.session_state.get("_recheck_history") or [])
                if next_url not in _hist:
                    _hist.append(next_url)
                    st.session_state["_recheck_history"] = _hist
                    try:
                        from utils.persistence import save_key as _sk2
                        _sk2("_recheck_history")
                    except Exception:
                        pass
                st.rerun()
            else:
                # Queue empty — finalize
                _before = _recheck_state.get("before") or {}
                _flipped = 0
                for u in done:
                    _new_q = st.session_state.get(_qk_pa(u))
                    if isinstance(_new_q, dict):
                        _new_v = _new_q.get("verdict")
                        _old_v = _before.get(u)
                        if _new_v == "KEEP" and _old_v in ("REWRITE", "IMPROVE"):
                            _flipped += 1
                        elif _new_v == "IMPROVE" and _old_v == "REWRITE":
                            _flipped += 1
                st.session_state["_recheck_all_last_summary"] = {
                    "total": len(done),
                    "flipped": _flipped,
                    "errors": len(errors),
                    "seconds": elapsed,
                }
                st.session_state[_recheck_state_key] = {"running": False}
                if errors:
                    st.warning(
                        f"Re-check done with {len(errors)} error(s). Flipped to "
                        f"better verdict: {_flipped}/{len(done)} pages.\n\n"
                        + "\n".join(f"- {e}" for e in errors[:5])
                    )
                else:
                    st.success(
                        f"Re-check done. {_flipped}/{len(done)} pages flipped "
                        f"to a better verdict in {elapsed:.0f}s. Scroll the "
                        f"list below to see new verdicts."
                    )
                st.rerun()

        # ── Fix ALL flagged pages (generate + push everything in batch) ──
        # The big "do it all for me" button: for every flagged page,
        # generate plan + bottom + intro, then push all three to Mshop.
        # Same rerun-based iteration as Re-check ALL so the spinner stays
        # responsive and the user can stop mid-run. Uses a separate
        # history key so re-checks and fixes don't interfere.
        st.markdown("---")
        _fix_state_key = "_fix_all_state"
        _fix_state = st.session_state.get(_fix_state_key) or {}
        _fix_running = bool(_fix_state.get("running"))
        _fix_history = set(st.session_state.get("_fix_history") or [])

        fix_col1, fix_col2, fix_col3 = st.columns([2, 2, 2])
        if not _fix_running:
            with fix_col1:
                _all_flagged_fix = [
                    q["url"] for q in quality_results
                    if q["verdict"] in ("REWRITE", "IMPROVE")
                ]
                # Exclude both already-fixed URLs AND pages that have
                # failed too many times (likely too-large content or
                # consistent API timeout — no point retrying every run).
                _failed_too_often = {u for u, n in _fix_fail_counts.items() if n >= _MAX_FAILURES}
                _eligible_fix = [
                    u for u in _all_flagged_fix
                    if u not in _fix_history and u not in _failed_too_often
                ]
                _skipped_fix = len(_all_flagged_fix) - len(_eligible_fix)
                # Cost estimate for transparency — Anthropic Sonnet 4.6
                # rough cost: ~$0.02 per page (plan + bottom + intro
                # + retries). 400 pages ≈ $8. Show before commit.
                _est_cost_usd = len(_eligible_fix) * 0.02
                _est_min = len(_eligible_fix) * 2  # ~2 min per page
                _btn_label = (
                    f"🤖 Fix ALL {len(_eligible_fix)} pending "
                    f"(~${_est_cost_usd:.0f}, ~{_est_min // 60}h{_est_min % 60}m)"
                    + (f" · skip {_skipped_fix} done" if _skipped_fix else "")
                    if _eligible_fix
                    else "🤖 Fix ALL flagged (all already done)"
                )
                if st.button(
                    _btn_label,
                    key="fix_all_btn",
                    type="primary" if _eligible_fix else "secondary",
                    use_container_width=True,
                    disabled=not _eligible_fix,
                    help="For EACH flagged page in sequence: generate AI plan + "
                         "bottom text + intro (if needed), then push everything "
                         "to Mshop (bottom text via footer API, meta + intro "
                         "via admin API). Skips pages already in fix history. "
                         "Click 'Stop' anytime — state is saved per page so a "
                         "Railway restart resumes from the last completed URL.",
                ):
                    st.session_state[_fix_state_key] = {
                        "running": True,
                        "pending_urls": list(_eligible_fix),
                        "done_urls": [],
                        "errors": [],
                        "started_at": time.time(),
                        "stage_counts": {"generated": 0, "pushed": 0},
                    }
                    st.rerun()
            with fix_col2:
                _last_fix = st.session_state.get("_fix_all_last_summary")
                if _last_fix:
                    st.caption(
                        f"Last fix run: {_last_fix.get('done', 0)} pages done · "
                        f"{_last_fix.get('errors', 0)} errors · "
                        f"{_last_fix.get('seconds', 0):.0f}s"
                    )
                if _fix_history:
                    st.caption(f"Fix history: {len(_fix_history)} URLs already done")
                    if st.button(
                        "🗑 Clear fix history",
                        key="fix_clear_history",
                        help="Wipes the persisted set of already-fixed URLs so "
                             "the next Fix ALL run starts fresh.",
                    ):
                        st.session_state["_fix_history"] = []
                        from utils.persistence import save_key as _sk_fc
                        try:
                            _sk_fc("_fix_history")
                        except Exception:
                            pass
                        st.rerun()
                # Show fix_all_log tail — survives Streamlit crashes so the
                # user can see WHICH page+step the run actually died on,
                # even when the spinner just disappears with no traceback.
                import os as _os_show
                if _os_show.path.exists("/data/fix_all_log.txt"):
                    with st.popover("📜 View fix_all_log (last 50 lines)"):
                        try:
                            with open("/data/fix_all_log.txt", "r", encoding="utf-8") as _lf:
                                _lines = _lf.readlines()[-50:]
                            st.code("".join(_lines), language="text")
                        except Exception as _le:
                            st.error(f"Could not read log: {_le}")
        else:
            pending_fix = _fix_state.get("pending_urls") or []
            done_fix = _fix_state.get("done_urls") or []
            errors_fix = _fix_state.get("errors") or []
            total_fix = len(pending_fix) + len(done_fix)
            elapsed_fix = time.time() - (_fix_state.get("started_at") or time.time())
            with fix_col1:
                pct = (len(done_fix) / max(total_fix, 1)) * 100
                eta_seconds = (elapsed_fix / max(len(done_fix), 1)) * len(pending_fix) if done_fix else 0
                st.markdown(
                    f"<div style='background:#0d0d15; border:2px solid #ffaa33; "
                    f"border-radius:6px; padding:0.6rem;'>"
                    f"<div style='font-size:0.85rem; color:#ffaa33; font-weight:700;'>"
                    f"Fixing {len(done_fix)}/{total_fix} ({pct:.0f}%)</div>"
                    f"<div style='font-size:0.7rem; color:#9b9bb8;'>"
                    f"Elapsed: {elapsed_fix/60:.1f}min · ETA: ~{eta_seconds/60:.0f}min · "
                    f"Errors: {len(errors_fix)}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with fix_col2:
                if st.button(
                    "⏸ Stop fix run",
                    key="fix_stop_btn",
                    use_container_width=True,
                ):
                    st.session_state[_fix_state_key] = {**_fix_state, "running": False}
                    st.rerun()

            # Process the next URL — generate everything, push everything
            if pending_fix:
                next_fix_url = pending_fix[0]
                _row = _audit_by_url_top.get(_qr_nu_top(next_fix_url))

                # Disk-based debug log so silent crashes leave a trail.
                # Streamlit can drop WebSocket mid-process and the spinner
                # just disappears — without this log we have NO clue
                # which step hung. File at /data/fix_all_log.txt.
                import os as _os_log, traceback as _tb_log
                _LOG = "/data/fix_all_log.txt"
                def _log(msg: str) -> None:
                    try:
                        from datetime import datetime as _dt
                        line = f"[{_dt.utcnow().isoformat()}Z] {msg}\n"
                        with open(_LOG, "a", encoding="utf-8") as f:
                            f.write(line)
                    except Exception:
                        pass

                # Mark this URL as in-progress on disk. If Streamlit
                # drops the session before we finish, the next page-load
                # will see this file, count it as a failure, and remove it.
                try:
                    import json as _jip
                    with open(_IP_FILE, "w", encoding="utf-8") as _ipw:
                        _jip.dump({"url": next_fix_url}, _ipw)
                except Exception:
                    pass

                with st.spinner(
                    f"Fixing {next_fix_url[-50:]} "
                    f"(generate plan + bottom + intro + push to Mshop)…"
                ):
                    _log(f"START {next_fix_url}")
                    try:
                        if _row is None:
                            raise ValueError("URL not in audit_results")
                        # Build page dict the runner expects
                        from utils.page_fix_runner import (
                            generate_all_fixes_for_page, page_audit_to_page_dict
                        )
                        from utils.ui_helpers import stable_hash as _sh
                        _page = page_audit_to_page_dict(_row)

                        # 1. Generate plan + bottom + intro
                        # batch_mode=True: 1 attempt instead of 3 for bottom
                        # text and 1 instead of 2 for intro. Worst-case
                        # per-page time drops from ~5 min to ~90s, well
                        # within Streamlit's WebSocket timeout window.
                        _log(f"  step=generate {next_fix_url}")
                        _gen_status = generate_all_fixes_for_page(_page, batch_mode=True)
                        _log(f"  generate-done {next_fix_url} status={_gen_status}")

                        # 2. Push bottom text via footer API
                        _url_hash = _sh(next_fix_url)
                        _bottom = (st.session_state.get(f"_bottom_text_{_url_hash}") or {}).get("bottom_html") or ""
                        if _bottom:
                            _log(f"  step=push_bottom {next_fix_url} chars={len(_bottom)}")
                            try:
                                from utils.footer_text_api import push_footer_text
                                _br = push_footer_text(next_fix_url, _bottom)
                                if _br.get("status") != "success":
                                    _err = f"bottom push failed — {_br.get('error', _br.get('status'))}"
                                    _fix_state["errors"].append(f"{next_fix_url}: {_err}")
                                    _log(f"  ERR {next_fix_url}: {_err}")
                                else:
                                    _log(f"  push_bottom-ok {next_fix_url}")
                            except Exception as _push_e:
                                _err = f"push_bottom exception: {type(_push_e).__name__}: {_push_e}"
                                _fix_state["errors"].append(f"{next_fix_url}: {_err}")
                                _log(f"  ERR {next_fix_url}: {_err}")
                        else:
                            _log(f"  skip=push_bottom {next_fix_url} (no bottom_html)")

                        # 3. Push intro + meta via admin API
                        _plan = st.session_state.get(f"_ai_plan_{_url_hash}") or {}
                        _intro_obj = st.session_state.get(f"_intro_text_{_url_hash}") or {}
                        _intro_html = _intro_obj.get("optimized_text") or ""
                        _meta_t = _plan.get("meta_title", "") if isinstance(_plan, dict) else ""
                        _meta_d = _plan.get("meta_description", "") if isinstance(_plan, dict) else ""
                        if _intro_html or _meta_t or _meta_d:
                            try:
                                from utils.mshop_admin_api import update_for_page, lookup_url as _mlu_fix
                                _active = st.session_state.get("mshop_active_pages") or {}
                                _pi = _mlu_fix(_active, next_fix_url)
                                if _pi:
                                    _log(f"  step=push_admin {next_fix_url} intro={len(_intro_html)} mt={len(_meta_t)} md={len(_meta_d)}")
                                    _adm = update_for_page(
                                        _pi,
                                        description=_intro_html or None,
                                        meta_title=_meta_t or None,
                                        meta_description=_meta_d or None,
                                    )
                                    if _adm.get("status") != "success":
                                        _err = f"admin push failed — {_adm.get('error', _adm.get('status'))}"
                                        _fix_state["errors"].append(f"{next_fix_url}: {_err}")
                                        _log(f"  ERR {next_fix_url}: {_err}")
                                    else:
                                        _log(f"  push_admin-ok {next_fix_url}")
                                else:
                                    _err = "no Mshop page-info (URL not in active-pages cache)"
                                    _fix_state["errors"].append(f"{next_fix_url}: {_err}")
                                    _log(f"  ERR {next_fix_url}: {_err}")
                            except Exception as _adm_e:
                                _err = f"push_admin exception: {type(_adm_e).__name__}: {_adm_e}"
                                _fix_state["errors"].append(f"{next_fix_url}: {_err}")
                                _log(f"  ERR {next_fix_url}: {_err}")
                        else:
                            _log(f"  skip=push_admin {next_fix_url} (nothing to push)")

                        _log(f"END {next_fix_url} OK")
                    except Exception as _fix_e:
                        _err = f"{type(_fix_e).__name__}: {_fix_e}"
                        _fix_state["errors"].append(f"{next_fix_url}: {_err}")
                        _log(f"  EXCEPTION {next_fix_url}: {_err}\n{_tb_log.format_exc()}")
                        _log(f"END {next_fix_url} ERR")
                _fix_state["pending_urls"] = pending_fix[1:]
                _fix_state["done_urls"] = done_fix + [next_fix_url]
                st.session_state[_fix_state_key] = _fix_state
                # Persist fix history ONLY if this URL had no errors. A
                # transient AI/network failure shouldn't permanently mark
                # a page as "done" — otherwise resuming Fix ALL would
                # silently skip pages that never actually got fixed.
                _url_had_error = any(next_fix_url in str(e) for e in _fix_state.get("errors", []))
                if not _url_had_error:
                    _fhist = list(st.session_state.get("_fix_history") or [])
                    if next_fix_url not in _fhist:
                        _fhist.append(next_fix_url)
                        st.session_state["_fix_history"] = _fhist
                        try:
                            from utils.persistence import save_key as _sk_fh
                            _sk_fh("_fix_history")
                        except Exception:
                            pass
                else:
                    # Bump failure counter so this URL gets auto-excluded
                    # from future Fix ALL runs after MAX_FAILURES attempts.
                    # Prevents one chronically-broken page from blocking
                    # the entire queue indefinitely.
                    _fc = dict(st.session_state.get("_fix_failure_count") or {})
                    _fc[next_fix_url] = _fc.get(next_fix_url, 0) + 1
                    st.session_state["_fix_failure_count"] = _fc
                    try:
                        from utils.persistence import save_key as _sk_fc
                        _sk_fc("_fix_failure_count")
                    except Exception:
                        pass
                # Clear in-progress marker — page completed (success or
                # explicit error). The marker is only kept for SILENT
                # crashes that bypass this code path.
                try:
                    import os as _os_clr
                    if _os_clr.path.exists(_IP_FILE):
                        _os_clr.remove(_IP_FILE)
                except Exception:
                    pass
                st.rerun()
            else:
                # Queue empty — finalize
                st.session_state["_fix_all_last_summary"] = {
                    "done": len(done_fix),
                    "errors": len(errors_fix),
                    "seconds": elapsed_fix,
                }
                st.session_state[_fix_state_key] = {"running": False}
                if errors_fix:
                    st.warning(
                        f"Fix run done with {len(errors_fix)} error(s). "
                        f"Processed {len(done_fix)} pages in {elapsed_fix/60:.1f}min.\n\n"
                        + "\n".join(f"- {e}" for e in errors_fix[:5])
                    )
                else:
                    st.success(
                        f"Fix run done. {len(done_fix)} pages fixed in "
                        f"{elapsed_fix/60:.1f}min. Click Re-check ALL to "
                        f"verify the new verdicts."
                    )
                st.rerun()

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

            # Action buttons — Re-scrape is ALWAYS available (diagnostic
            # works on any verdict, including KEEP, since the user might
            # want to verify a recent push didn't break anything).
            # Generation buttons are only meaningful for flagged pages.
            audit_row = _audit_by_url.get(_qr_nu(q["url"]))
            if audit_row is not None:
                btn_cols = st.columns([3, 3, 3, 3])
                with btn_cols[0]:
                    # Open / Rewrite — only for REWRITE/IMPROVE pages
                    if verdict in ("REWRITE", "IMPROVE"):
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
                    elif ai_plan_present:
                        # KEEP page that already has an AI plan — let user
                        # still navigate to Quick Wins (e.g. to push a
                        # tweak or review the cached output).
                        if st.button(
                            "🚀 Open in Quick Wins",
                            key=f"qq_open_keep_{url_hash}",
                            use_container_width=True,
                        ):
                            open_in_quick_wins(q["url"])
                            st.rerun()
                with btn_cols[1]:
                    # Regenerate — only if plan exists, regardless of verdict
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
                        with st.spinner(f"Re-scraping {q['url'][-50:]} (cache-bypass)…"):
                            # bypass_cache=True sends Cache-Control: no-cache
                            # headers AND appends a cache-busting query param.
                            # Without this, Magento's full-page cache can
                            # serve a stale copy of the HTML and the verdict
                            # reflects pre-push content even when the push
                            # actually landed.
                            fresh = scrape_page(q["url"], bypass_cache=True)
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
                            # Admin log = intro_text + meta_title + meta_desc
                            # (resolved via mshop_active_pages → page_id)
                            from utils.mshop_admin_api import read_push_log as _read_admin, lookup_url as _mlu
                            active = st.session_state.get("mshop_active_pages") or {}
                            page_info = _mlu(active, q["url"])
                            admin_log = _read_admin(limit=200)
                            admin_entries = []
                            if page_info and isinstance(admin_log, list):
                                pid = page_info.get("id")
                                ptype = page_info.get("type")
                                pid_field = {
                                    "category": "categoryId",
                                    "cms": "cmsPageId",
                                    "filterpage": "filterPageId",
                                }.get(ptype, "")
                                for entry in admin_log:
                                    payload = entry.get("payload") or {}
                                    if pid_field and payload.get(pid_field) == pid:
                                        admin_entries.append(entry)
                            # Footer log = bottom_text (separate API,
                            # uses URL as identifier — does NOT need
                            # the active-pages cache).
                            from utils.footer_text_api import read_push_log as _read_footer
                            footer_entries = _read_footer(url=q["url"])
                            st.session_state["_qq_diag"] = {
                                "url": q["url"],
                                "page_info": page_info,
                                "admin_entries": admin_entries[:5],
                                "footer_entries": (footer_entries or [])[-5:][::-1],
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

                # ── INLINE diagnostic: shown right below the button that
                # triggered it, not at the top of the section. Avoids the
                # "where did the result go?" UX problem when the card is
                # 50 entries deep in the page.
                _diag = st.session_state.get("_qq_diag")
                if _diag and _qr_nu(_diag.get("url", "")) == _qr_nu(q["url"]):
                    with st.expander("🔍 Re-scrape + push-log diagnostic", expanded=True):
                        # Fresh verdict from this run, if any
                        from utils.quality_check_runner import quality_key as _qkk
                        fresh_verdict = st.session_state.get(_qkk(q["url"]))
                        if isinstance(fresh_verdict, dict):
                            fv = fresh_verdict.get("verdict", "?")
                            fs = fresh_verdict.get("score", "?")
                            fc = {"REWRITE": "#ff4455", "IMPROVE": "#ffaa33", "KEEP": "#33dd88"}.get(fv, "#9b9bb8")
                            st.markdown(
                                f"<div style='padding:0.5rem; background:#0d0d15; border-radius:4px; margin-bottom:0.5rem;'>"
                                f"<strong>New verdict on the freshly-scraped LIVE text:</strong> "
                                f"<span style='color:{fc}; font-weight:700; font-size:1.1rem;'>{fv} {fs}/10</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                            st.caption(f"Summary: {fresh_verdict.get('summary', '')}")
                        if _diag.get("error"):
                            st.error(f"Could not read push log: {_diag['error']}")
                        elif not _diag.get("page_info"):
                            active_now = st.session_state.get("mshop_active_pages") or {}
                            lookup_size = len(active_now.get("lookup", {})) if isinstance(active_now, dict) else 0
                            st.warning(
                                f"**No Mshop page-info for this URL.**\n\n"
                                f"Current active-pages cache contains "
                                f"**{lookup_size}** URL → page-id mappings, but `{q['url']}` "
                                f"is NOT one of them.\n\n"
                                "**This is critical.** If pocket-pussy was never in the cache, "
                                "the Push buttons in Quick Wins would have been HIDDEN for this "
                                "page — meaning your earlier 'pushes' for this URL never "
                                "actually pushed anything (the buttons weren't there to click).\n\n"
                                "Two possible causes:\n"
                                "1. The cache was never synced — sync it now (button below)\n"
                                "2. Mshop's admin API doesn't include this category in its list "
                                "of active pages (e.g. it's disabled in Magento, or it's a sale/"
                                "filter page the API doesn't return)"
                            )
                            sync_cols = st.columns([2, 3])
                            with sync_cols[0]:
                                if st.button(
                                    "🔌 Sync Mshop active pages now",
                                    key=f"qq_sync_{url_hash}",
                                    type="primary",
                                    use_container_width=True,
                                    help="Calls Mshop Admin API to fetch ALL "
                                         "categories + CMS pages + filter pages, "
                                         "rebuilds the URL → page-id lookup, and "
                                         "saves to disk.",
                                ):
                                    from utils.mshop_admin_api import fetch_active_pages_all
                                    with st.spinner("Fetching all active pages from Mshop…"):
                                        try:
                                            result = fetch_active_pages_all()
                                            if isinstance(result, dict) and result.get("lookup"):
                                                st.session_state["mshop_active_pages"] = result
                                                from utils.persistence import save_key
                                                save_key("mshop_active_pages")
                                                # Refresh the diagnostic with new lookup
                                                from utils.mshop_admin_api import lookup_url as _mlu_re
                                                page_info = _mlu_re(result, q["url"])
                                                if page_info:
                                                    st.success(
                                                        f"Sync done. Found "
                                                        f"{len(result.get('lookup', {}))} pages. "
                                                        f"This URL now resolves to "
                                                        f"**{page_info.get('type')} id="
                                                        f"{page_info.get('id')}**. Click "
                                                        f"🔍 Re-scrape + re-check again to see "
                                                        f"the push log."
                                                    )
                                                else:
                                                    st.error(
                                                        f"Sync done ({len(result.get('lookup', {}))} "
                                                        f"pages fetched), but `{q['url']}` is STILL "
                                                        f"not in the lookup. This means Magento's "
                                                        f"Admin API doesn't return this category "
                                                        f"as an active page. Likely the page is "
                                                        f"disabled in Magento, or it's a special "
                                                        f"page type (sale / dynamic filter) the "
                                                        f"API doesn't expose."
                                                    )
                                            else:
                                                st.error(f"Sync failed: {result.get('error', 'unknown')}")
                                        except Exception as _se:
                                            st.error(f"Sync error: {_se}")

                            # Footer-text pushes use URL directly (no
                            # active-pages cache needed), so even when
                            # the admin lookup failed we can still show
                            # whether bottom-text pushes landed.
                            footer_entries_no_pinfo = _diag.get("footer_entries") or []
                            st.markdown("---")
                            st.markdown("##### 📄 Bottom text (footer API — works without active-pages cache)")
                            if not footer_entries_no_pinfo:
                                st.warning(
                                    "No footer-API push entries for this URL either. "
                                    "Either no bottom-text push was ever made, or the "
                                    "footer log (/data/footer_push_log.json) was reset."
                                )
                            else:
                                st.caption(
                                    f"Last {len(footer_entries_no_pinfo)} bottom-text "
                                    f"push attempts (newest first):"
                                )
                                for e in footer_entries_no_pinfo:
                                    status_e = e.get("status", "?")
                                    http = e.get("http_code", "?")
                                    color = "#33dd88" if status_e == "success" else "#ff4455"
                                    payload = e.get("payload") or {}
                                    sections = e.get("section_count", 0)
                                    texts = payload.get("texts", []) if isinstance(payload, dict) else []
                                    total_chars = sum(
                                        len((t.get("content") or t.get("text") or ""))
                                        for t in texts
                                    ) if texts else 0
                                    body_excerpt = (e.get("response_body") or "")[:300]
                                    st.markdown(
                                        f"<div style='background:#0d0d15; border-left:3px solid {color}; "
                                        f"padding:0.6rem; margin:0.4rem 0; border-radius:4px; "
                                        f"font-size:0.75rem; font-family:\"IBM Plex Mono\",monospace;'>"
                                        f"<div style='color:{color}; font-weight:700;'>"
                                        f"{status_e.upper()} · HTTP {http} · {e.get('timestamp', '')}</div>"
                                        f"<div style='color:#9b9bb8; margin-top:0.3rem;'>endpoint: (footer API)</div>"
                                        f"<div style='color:#e8e8f0; margin-top:0.3rem;'>"
                                        f"sections sent: <strong>{sections}</strong> · "
                                        f"total chars: <strong>{total_chars}</strong></div>"
                                        f"<div style='color:#6b6b8a; margin-top:0.3rem; word-break:break-all;'>"
                                        f"response: {body_excerpt}</div>"
                                        f"</div>",
                                        unsafe_allow_html=True,
                                    )
                        else:
                            admin_entries = _diag.get("admin_entries") or []
                            footer_entries = _diag.get("footer_entries") or []
                            pinfo = _diag.get("page_info") or {}

                            def _render_entry(entry, show_admin_fields=True):
                                status_e = entry.get("status", "?")
                                http = entry.get("http_code", "?")
                                color = "#33dd88" if status_e == "success" else "#ff4455"
                                payload = entry.get("payload") or {}
                                if show_admin_fields:
                                    desc = payload.get("description") or ""
                                    mt = payload.get("metaTitle") or ""
                                    md = payload.get("metaDescription") or ""
                                    fields_line = (
                                        f"description sent: <strong>{len(desc)}</strong> chars · "
                                        f"meta_title sent: <strong>{len(mt)}</strong> chars · "
                                        f"meta_desc sent: <strong>{len(md)}</strong> chars"
                                    )
                                else:
                                    sections = entry.get("section_count", 0)
                                    texts = payload.get("texts", []) if isinstance(payload, dict) else []
                                    # Footer API uses field "content" — earlier
                                    # this read "text" and always showed 0,
                                    # falsely suggesting empty pushes.
                                    total_chars = sum(
                                        len((t.get("content") or t.get("text") or ""))
                                        for t in texts
                                    ) if texts else 0
                                    faq_count = sum(1 for t in texts if t.get("tagAsFaq"))
                                    fields_line = (
                                        f"sections sent: <strong>{sections}</strong> "
                                        f"({sections - faq_count} body + {faq_count} FAQ) · "
                                        f"total chars: <strong>{total_chars}</strong>"
                                    )
                                body_excerpt = (entry.get("response_body") or "")[:300]
                                ep = entry.get("endpoint") or ("(footer API)" if not show_admin_fields else "")
                                st.markdown(
                                    f"<div style='background:#0d0d15; border-left:3px solid {color}; "
                                    f"padding:0.6rem; margin:0.4rem 0; border-radius:4px; "
                                    f"font-size:0.75rem; font-family:\"IBM Plex Mono\",monospace;'>"
                                    f"<div style='color:{color}; font-weight:700;'>"
                                    f"{status_e.upper()} · HTTP {http} · {entry.get('timestamp', '')}</div>"
                                    f"<div style='color:#9b9bb8; margin-top:0.3rem;'>endpoint: {ep}</div>"
                                    f"<div style='color:#e8e8f0; margin-top:0.3rem;'>{fields_line}</div>"
                                    f"<div style='color:#6b6b8a; margin-top:0.3rem; word-break:break-all;'>"
                                    f"response: {body_excerpt}</div>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )

                            # ── Intro text + meta (admin API) ──
                            st.markdown("##### 📝 Intro text + meta (admin API)")
                            if not pinfo:
                                st.warning(
                                    "URL not in active-pages cache → intro/meta push buttons "
                                    "in Quick Wins were HIDDEN for this page. Nothing was sent."
                                )
                            elif not admin_entries:
                                st.warning(
                                    f"No admin-API push entries for {pinfo.get('type')} "
                                    f"id={pinfo.get('id')}. Either no intro/meta push was ever "
                                    f"made, or the push log was reset."
                                )
                            else:
                                st.caption(
                                    f"Last {len(admin_entries)} push attempts (newest first):"
                                )
                                for e in admin_entries:
                                    _render_entry(e, show_admin_fields=True)

                            # ── Bottom text (footer API — separate system) ──
                            st.markdown("##### 📄 Bottom text (footer API — separate from admin)")
                            st.caption(
                                "The footer push uses URL directly (not the active-pages "
                                "cache), so it works independently of intro/meta pushes."
                            )
                            if not footer_entries:
                                st.warning(
                                    "No footer-API push entries for this URL. Either no "
                                    "bottom-text push was ever made, or the footer log "
                                    "(/data/footer_push_log.json) was reset."
                                )
                            else:
                                st.caption(
                                    f"Last {len(footer_entries)} bottom-text push attempts "
                                    f"(newest first):"
                                )
                                for e in footer_entries:
                                    _render_entry(e, show_admin_fields=False)

                            st.markdown(
                                "**How to read this:**\n\n"
                                "- ✅ `success` + non-zero chars + still-bad live text → Magento "
                                "full-page cache stale; flush in Magento Admin → System → Cache → "
                                "Flush Magento Cache.\n"
                                "- ❌ Non-200 HTTP or `network_error` → push didn't land; read "
                                "the response body for the Magento error.\n"
                                "- 0 chars / 0 sections → push button sent empty payload; AI "
                                "output wasn't loaded into the field.\n"
                                "- No entries on either side → nothing was actually pushed for "
                                "this URL, OR the relevant log got reset."
                            )
                        if st.button("Dismiss diagnostic", key=f"qq_dismiss_{url_hash}"):
                            st.session_state.pop("_qq_diag", None)
                            st.rerun()

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
