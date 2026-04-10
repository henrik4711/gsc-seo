"""
Site Cleanup — Site-wide actions: pages to delete, merge, redirect, noindex.
Different from Quick Wins which is per-page improvements.
"""

import streamlit as st
from utils.ui_helpers import normalize_url, stable_hash, shorten_url


def _pages_to_merge():
    """Combined from cannibalization + ideal structure + gap analysis."""
    merges = []
    seen_pairs = set()

    # Source 1: Ideal structure (AI-generated merges)
    ideal = st.session_state.get("_ideal_structure") or {}
    if isinstance(ideal, dict):
        for m in ideal.get("merge", []) or []:
            if not isinstance(m, dict):
                continue
            from_urls = m.get("from", [])
            to_url = m.get("to", "")
            why = m.get("why", "")
            if not to_url or not from_urls:
                continue
            for from_url in from_urls:
                pair = tuple(sorted([normalize_url(to_url), normalize_url(from_url)]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                merges.append({
                    "keep": to_url,
                    "redirect": from_url,
                    "query": "(ideal structure recommendation)",
                    "lost_clicks": 0,
                    "severity": "ai-recommended",
                    "reason": why,
                    "source": "ideal_structure",
                })

    # Source 2: Cannibalization data
    cannibal_df = st.session_state.get("cannibalization")
    if cannibal_df is None or cannibal_df.empty:
        return merges

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
    return merges[:50]


def _pages_to_create():
    """NEW pages to create — from ideal structure + content roadmap + page-level plans."""
    creates = []
    seen = set()

    # Build set of existing URLs + titles for duplicate checking
    audit_results = st.session_state.get("audit_results", [])
    existing_urls = set()
    existing_titles_lower = set()
    existing_url_segments = set()
    for r in audit_results:
        u = normalize_url(r.get("url", ""))
        if u:
            existing_urls.add(u)
            # Extract path segments for fuzzy URL matching
            from urllib.parse import urlparse
            path = urlparse(u).path.lower().rstrip("/")
            for seg in path.split("/"):
                if seg and len(seg) > 3:
                    existing_url_segments.add(seg)
        t = (r.get("title") or "").lower().strip()
        if t:
            existing_titles_lower.add(t)

    def _already_exists(url_or_title: str) -> str:
        """Check if page already exists. Returns reason string or empty."""
        # Check exact URL match
        norm = normalize_url(url_or_title)
        if norm in existing_urls:
            return f"Page already exists: {url_or_title}"
        # Check if URL path matches an existing page
        from urllib.parse import urlparse
        path = urlparse(url_or_title).path.lower().rstrip("/") if "://" in url_or_title or url_or_title.startswith("/") else ""
        if path:
            for eu in existing_urls:
                ep = urlparse(eu).path.lower().rstrip("/")
                if ep == path:
                    return f"URL path already exists: {eu}"
        # Check title similarity
        title_lower = url_or_title.lower().strip()
        if title_lower in existing_titles_lower:
            return f"Page with same title already exists"
        return ""

    # Source 1: Ideal structure
    ideal = st.session_state.get("_ideal_structure") or {}
    if isinstance(ideal, dict):
        for c in ideal.get("create", []) or []:
            if not isinstance(c, dict):
                continue
            url = c.get("url", "")
            if url in seen:
                continue
            seen.add(url)
            exists = _already_exists(url)
            entry = {
                "url": url,
                "type": c.get("type", "page"),
                "keyword": c.get("kw", ""),
                "why": c.get("why", ""),
                "source": "ideal_structure",
            }
            if exists:
                entry["already_exists"] = exists
            creates.append(entry)

    # Source 2: Content roadmap (from topic_clusters)
    roadmap = st.session_state.get("content_roadmap", {})
    if isinstance(roadmap, dict):
        for a in roadmap.get("new_articles", []) or []:
            if not isinstance(a, dict):
                continue
            title = a.get("suggested_title", "")
            if title in seen:
                continue
            seen.add(title)
            exists = _already_exists(title)
            entry = {
                "url": f"(new article: {title})",
                "type": a.get("type", "blog"),
                "keyword": ", ".join(a.get("target_keywords", [])[:3]),
                "why": a.get("why", ""),
                "source": "content_roadmap",
                "priority": a.get("priority", ""),
            }
            if exists:
                entry["already_exists"] = exists
            creates.append(entry)

    # Source 3: Per-page plans (collected from all AI plans)
    for key, val in st.session_state.items():
        if not key.startswith("_ai_plan_") or not isinstance(val, dict):
            continue
        for nc in val.get("new_content_suggestions", []) or []:
            if not isinstance(nc, dict):
                continue
            title = nc.get("suggested_title", "")
            if not title or title in seen:
                continue
            seen.add(title)
            exists = _already_exists(title)
            entry = {
                "url": f"(new article: {title})",
                "type": nc.get("type", "blog"),
                "keyword": ", ".join(nc.get("target_keywords", [])[:3]),
                "why": nc.get("why", ""),
                "source": "page_plan",
                "link_from": nc.get("link_from", ""),
            }
            if exists:
                entry["already_exists"] = exists
            creates.append(entry)

    return creates[:100]


def _pages_to_delete_ideal():
    """Pages to delete from ideal structure."""
    ideal = st.session_state.get("_ideal_structure") or {}
    if not isinstance(ideal, dict):
        return []
    deletes = []
    for d in ideal.get("delete", []) or []:
        if not isinstance(d, dict):
            continue
        deletes.append({
            "url": d.get("url", ""),
            "why": d.get("why", ""),
            "source": "ideal_structure",
        })
    return deletes


def _pages_to_redirect():
    """Broken pages (4xx) that have backlinks — should be redirected to similar page."""
    issues = st.session_state.get("sf_crawl_issues", {})
    broken = issues.get("broken_links", [])
    page_authority = st.session_state.get("page_authority")

    # Build set of pages that already have redirects in place
    redirect_chains = issues.get("redirect_chains", [])
    already_redirected = set()
    for rc in redirect_chains:
        if isinstance(rc, dict) and rc.get("url"):
            already_redirected.add(normalize_url(rc["url"]))

    # Build set of active pages (have impressions/traffic) to avoid redirecting them
    audit_results = st.session_state.get("audit_results", [])
    active_pages = set()
    for r in audit_results:
        if r.get("impressions", 0) > 0 or r.get("clicks", 0) > 0:
            active_pages.add(normalize_url(r.get("url", "")))

    redirects = []
    for b in broken:
        url = b.get("url", "")
        norm = normalize_url(url)

        # Skip if redirect is already in place
        if norm in already_redirected:
            continue

        # Skip if page is actually active (may be a false positive from crawl)
        if norm in active_pages:
            continue

        rd = 0
        if page_authority is not None and not page_authority.empty:
            match = page_authority[page_authority["page"].apply(normalize_url) == norm]
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


def _generate_cannibal_rewrite(page_url: str, query: str, issues: list, context: str, rewrite_key: str):
    """
    Generate COMPLETE new body text for a page, fixing ALL detected issues.
    Sends: current content + all issues + target query + competing pages info.
    """
    from config import get_anthropic_key, has_anthropic_key
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    from utils.ai_generator import get_client, _parse_ai_json, ANTI_HALLUCINATION_RULES
    from utils.persistence import save
    from utils.page_profile import build_page_profile

    client = get_client(get_anthropic_key())
    prof = build_page_profile(page_url)

    current_body = prof["body_text"]
    word_count = prof["word_count"]
    page_type = prof["page_type"]
    title = prof["title"]
    h1 = prof["h1"]
    language = st.session_state.get("content_language", "Swedish")
    site_context = st.session_state.get("site_context", "")

    issues_text = "\n".join(f"- {i}" for i in issues) if issues else "No specific issues listed"

    # ── Build prompt context from page profile ────────────────

    # 1. Competing pages (from cannibalization)
    competing_pages = []
    audit_results = st.session_state.get("audit_results", [])
    audit_by_url = {normalize_url(r.get("url", "")): r for r in audit_results}
    for cannibal in prof["cannibalization"]:
        if cannibal.get("query", "").lower() == query.lower():
            for cp_url in cannibal.get("competing_pages", []):
                cp_audit = audit_by_url.get(normalize_url(cp_url), {})
                competing_pages.append(
                    f"  - {cp_url} title: \"{(cp_audit.get('title') or '')[:60]}\""
                )
            break
    competing_text = "\n".join(competing_pages[:5]) if competing_pages else "None found"

    # 2. Current internal links FROM this page
    existing_links_text = ""
    if prof["internal_links_out"]:
        link_items = []
        for lnk in prof["internal_links_out"][:10]:
            link_items.append(f"  - \"{lnk.get('anchor', '')}\" → {lnk.get('url', '')}")
        existing_links_text = "\n".join(link_items)
    if not existing_links_text:
        existing_links_text = "NO internal links found on this page"

    # 3. Related pages from topic clusters
    related_pages = []
    topic_clusters = st.session_state.get("topic_clusters", {})
    for cluster_info in prof["clusters"]:
        topic_name = cluster_info.get("topic", "")
        if isinstance(topic_clusters, dict):
            for cluster in topic_clusters.get("clusters", []):
                if cluster.get("topic") == topic_name:
                    for cp in cluster.get("pages", []):
                        cp_url = cp.get("page", "")
                        if normalize_url(cp_url) != prof["url"]:
                            cp_audit = audit_by_url.get(normalize_url(cp_url), {})
                            related_pages.append(
                                f"  - {cp_url} \"{(cp_audit.get('title') or cp_url.split('/')[-1])[:50]}\""
                            )

    # Cannibalized page link instructions
    cannibal_link_instruction = ""
    for cp_line in competing_pages:
        cp_url = cp_line.strip().split(" ")[1] if len(cp_line.strip().split(" ")) > 1 else ""
        if cp_url:
            cannibal_link_instruction += f"\n  - MUST LINK: <a href=\"{cp_url}\">{query}</a> (anchor = the cannibalized query)"

    # Add suggested anchors from GSC queries for related pages
    gsc_data = st.session_state.get("gsc_data")
    for i, rp in enumerate(related_pages):
        rp_url = rp.strip().split(" ")[1].strip('"') if len(rp.strip().split(" ")) > 1 else ""
        if rp_url:
            rp_norm = normalize_url(rp_url)
            if gsc_data is not None and hasattr(gsc_data, "groupby"):
                rp_gsc = gsc_data[gsc_data["page"].apply(normalize_url) == rp_norm]
                if not rp_gsc.empty:
                    top_query = rp_gsc.sort_values("impressions", ascending=False).iloc[0]["query"]
                    related_pages[i] = f"{rp} → suggested anchor: \"{top_query}\""

    related_text = "\n".join(related_pages[:10]) if related_pages else "No cluster-related pages found"
    if cannibal_link_instruction:
        related_text += "\n\n**CRITICAL LINKS (must include):**" + cannibal_link_instruction

    # 4. Top GSC queries
    gsc_queries_text = ""
    if prof["gsc_queries"]:
        gsc_lines = []
        for qr in prof["gsc_queries"][:10]:
            gsc_lines.append(
                f"  - \"{qr['query']}\" ({qr['impressions']} impr, {qr['clicks']} clicks, pos {qr['position']})"
            )
        gsc_queries_text = "\n".join(gsc_lines)
    if not gsc_queries_text:
        gsc_queries_text = f"  - \"{query}\" (primary target)"

    # 5. Products on this page
    products_text = ""
    if prof["products"]:
        prod_lines = []
        for prod in prof["products"][:8]:
            if isinstance(prod, dict):
                prod_lines.append(
                    f"  - {prod.get('name', '?')} — {prod.get('price', '?')} — {prod.get('url', '')}"
                )
        products_text = "\n".join(prod_lines)
    if not products_text:
        products_text = "No product data available — use generic product references from the store"

    prompt = f"""{ANTI_HALLUCINATION_RULES}

You are rewriting the BODY TEXT for an e-commerce category page.

## CRITICAL: KEYWORD FOCUS
The PRIMARY keyword for this page is: **{query}**
This keyword MUST:
- Appear in at least 2 of your H2 headings (naturally, not forced)
- Be used in the first sentence of the top text
- Be the SUBJECT of the text — the entire text is ABOUT "{query}"
- NOT be replaced with synonyms or generic terms like "masturbator" or "sexleksak"
If the page is about "pocket pussy", write about pocket pussy specifically.
If the page is about "dildo", write about dildos specifically.
Do NOT write generic category text that could apply to any product.

## PAGE INFO
URL: {page_url}
Page type: {page_type}
Current title: {title}
Current H1: {h1}
Current word count: {word_count}
Target query: {query}
Language: {language}
Site context: {site_context}

## DETECTED ISSUES (MUST ALL BE FIXED)
{issues_text}

## COMPETING PAGES (differentiate your text from these)
{competing_text}

## GSC QUERIES THIS PAGE SHOULD TARGET
{gsc_queries_text}

## CURRENT INTERNAL LINKS ON THIS PAGE
{existing_links_text}

## RELATED PAGES TO LINK TO (from topic cluster)
{related_text}

## REAL PRODUCTS ON THIS PAGE (use these, don't invent)
{products_text}

## CURRENT TEXT (this is what needs rewriting)
{current_body[:2000]}

## PAGE STRUCTURE (Magento category page)
A category page has TWO text areas separated by a product grid:

1. **TOP TEXT** (intro) — shown ABOVE the product grid
   - 80-150 words
   - Purpose: tell the visitor what this category is and why they should browse
   - Include primary keyword in first sentence
   - Warm, inviting tone — not a wall of text
   - Can include 1-2 key benefits or differentiators
   - NO FAQ, NO long explanations — save those for bottom text

2. **PRODUCT GRID** — we CANNOT change this (products with images, prices, names)

3. **BOTTOM TEXT** (footer) — shown BELOW the product grid
   - 600-1200 words — this is where the real SEO value lives
   - Structure with 3-5 H2 headings covering:
     * Buying guide / how to choose (what to look for, materials, features)
     * Product types / variants (explain the differences)
     * Expert tips / usage advice (show real knowledge)
     * Care and maintenance (practical value)
   - Internal links to related pages using <a href="URL">anchor</a>
   - End with FAQ section (3-5 questions from lower-volume GSC queries)
   - E-E-A-T: expert advice, material comparisons, specific brand knowledge

## WRITING STYLE — CRITICAL
The text MUST read like it was written by a real person who works at the store,
NOT like AI-generated content. Follow these rules strictly:

BANNED AI PATTERNS (never use these):
- "Sammanfattningsvis" / "Avslutningsvis" / "I slutändan"
- "Det är viktigt att notera/komma ihåg"
- "Oavsett om du ... eller ..."
- "Denna/Denna guide/I denna artikel"
- "Utforska vår/vårt" as opening sentence
- "Perfekt för dig som..."
- Starting 3+ sentences with same word
- Bullet points that all follow identical structure
- "Upptäck" as first word (overused in Swedish SEO)
- Generic filler like "Vi förstår att..." / "Vi erbjuder..."

REQUIRED STYLE:
- Write like a knowledgeable friend giving advice, not a brochure
- Mix short punchy sentences (5 words) with longer ones (25 words)
- Use "du/dig" directly — talk TO the reader
- Share opinions: "Vi gillar X för att..." / "Ärligt talat är Y bättre än Z"
- Include 1-2 unexpected details that show real expertise (e.g. "TPE-materialet
  är känsligt för oljor — använd ALLTID vattenbaserat glidmedel")
- Tone should match an ADULT STORE: direct, open, no prudishness, but not vulgar.
  Customers buying these products want practical honest advice, not marketing speak.
- Vary paragraph length: some 2 sentences, some 5 sentences
- If the cluster/pillar is about a specific product TYPE, write from experience
  with that type — not generic "there are many options" filler

## CONTENT RULES
1. NO keyword stuffing — primary keyword max 2x in top, max 5-6x in bottom (natural use across 1000 words)
2. Mention product NAMES and BRANDS — but NEVER specific prices (they change)
3. MUST be EVERGREEN — relevant regardless of which products are currently shown
4. MUST be DIFFERENT from competing pages
5. E-E-A-T: real product knowledge, material comparisons, honest recommendations
6. Language: {language}
7. For /rea/ sale pages: describe the CATEGORY of products on sale and WHY
   they're good value, NOT specific sale items or rotating discounts

## FAQ FORMAT
The FAQ in bottom_html must use visible HTML markup like this:
<h2>Vanliga frågor</h2>
<div itemscope itemtype="https://schema.org/FAQPage">
  <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
    <h3 itemprop="name">Question here?</h3>
    <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
      <p itemprop="text">Answer here.</p>
    </div>
  </div>
</div>

ALSO generate a separate faq_schema JSON-LD block for the FAQ questions.

## OUTPUT (JSON):
{{
    "top_html": "<p>Intro text above product grid...</p>",
    "top_word_count": 0,
    "bottom_html": "<h2>heading</h2><p>text...</p><h2>Vanliga frågor</h2><div itemscope itemtype='https://schema.org/FAQPage'>...</div>",
    "bottom_word_count": 0,
    "faq_schema": {{
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {{
                "@type": "Question",
                "name": "question?",
                "acceptedAnswer": {{
                    "@type": "Answer",
                    "text": "answer"
                }}
            }}
        ]
    }},
    "target_keyword": "{query}",
    "internal_links": [{{"anchor": "text", "url": "/path"}}],
    "issues_fixed": ["which issues from the list above were fixed"]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=6000,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    result = _parse_ai_json(message)
    st.session_state[rewrite_key] = result
    save(rewrite_key)


def _generate_cannibal_subcategory_meta(query: str, pages: list, row, ai_key: str):
    """
    Generate differentiated meta titles + descriptions for each page in a
    sub-category/brand-variant cannibalization conflict.
    Uses the existing generate_meta_suggestions() AI function.
    """
    from config import get_anthropic_key, has_anthropic_key
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    from utils.ai_generator import get_client, generate_meta_suggestions
    from utils.persistence import save

    client = get_client(get_anthropic_key())
    audit_results = st.session_state.get("audit_results", [])
    audit_by_url = {normalize_url(r.get("url", "")): r for r in audit_results}

    results = {}
    for p in pages:
        page_url = p.get("page", "")
        page_norm = normalize_url(page_url)
        audit = audit_by_url.get(page_norm, {})
        if not audit:
            # Minimal fallback if no audit data
            audit = {"url": page_url, "title": "", "h1": "", "h2s": [],
                     "word_count": 0, "page_type": "category"}

        # Extract path segments to suggest variant-specific keywords
        from urllib.parse import urlparse
        path = urlparse(page_url).path.rstrip("/")
        last_segment = path.split("/")[-1] if path else ""
        variant_kw = last_segment.replace("-", " ") if last_segment else ""

        # Build target keywords: generic query + variant-specific
        target_kws = [query]
        if variant_kw and variant_kw != query:
            target_kws.append(f"{variant_kw} {query}")
            target_kws.append(f"{query} {variant_kw}")

        try:
            meta_result = generate_meta_suggestions(
                client=client,
                page_data=audit,
                target_keywords=target_kws,
                site_context=st.session_state.get("site_context", ""),
                language=st.session_state.get("content_language", "Swedish"),
                n_variants=2,
            )
            results[page_url] = meta_result
        except Exception as e:
            results[page_url] = {"error": str(e), "variants": []}

    st.session_state[ai_key] = results
    save(ai_key)


def _validate_subcategory_quality(parent_url: str, child_pages: list):
    """
    For a sub-category split, check:
    1. Does the parent page link to each child?
    2. Are child titles differentiated from parent title?
    3. Is child content a near-duplicate of parent?
    Returns dict of issues.
    """
    from utils.page_profile import build_page_profile

    parent_profile = build_page_profile(parent_url)
    parent_norm = normalize_url(parent_url)
    parent_title = parent_profile["title"].lower().strip()
    parent_h1 = parent_profile["h1"].lower().strip()
    parent_word_count = parent_profile["word_count"]

    issues = []

    # Build set of parent's outbound link targets (from profile)
    parent_outbound = set()
    for lnk in parent_profile["internal_links_out"]:
        link_url = normalize_url(lnk.get("url", ""))
        if link_url:
            parent_outbound.add(link_url)

    for child in child_pages:
        child_url = child.get("page", "") if isinstance(child, dict) else child
        child_norm = normalize_url(child_url)
        if child_norm == parent_norm:
            continue  # skip self
        child_profile = build_page_profile(child_url)
        child_title = child_profile["title"].lower().strip()
        child_h1 = child_profile["h1"].lower().strip()
        child_wc = child_profile["word_count"]

        # Check 1: does parent link to child?
        has_link = child_norm in parent_outbound
        if not has_link:
            issues.append({
                "page": child_url,
                "severity": "high",
                "issue": f"Parent `{parent_url}` does NOT link to this sub-category",
                "fix": f"Add internal link from parent category to this sub-category",
            })

        # Check 2: title differentiated?
        if parent_title and child_title and parent_title == child_title:
            issues.append({
                "page": child_url,
                "severity": "high",
                "issue": "Title is IDENTICAL to parent category",
                "fix": "Rewrite title to include the sub-category variant term",
            })
        elif parent_title and child_title:
            # Same base: if child title only differs by 1-2 words it's near-dupe
            parent_words = set(parent_title.split())
            child_words = set(child_title.split())
            overlap = len(parent_words & child_words)
            if overlap >= len(parent_words) - 1 and overlap >= len(child_words) - 1:
                issues.append({
                    "page": child_url,
                    "severity": "medium",
                    "issue": "Title is nearly identical to parent — no variant differentiation",
                    "fix": "Rewrite to emphasize the sub-category variant",
                })

        # Check 3: content near-duplicate by word count similarity
        if parent_word_count > 100 and child_wc > 100:
            ratio = min(parent_word_count, child_wc) / max(parent_word_count, child_wc)
            if ratio > 0.9 and parent_h1 == child_h1:
                issues.append({
                    "page": child_url,
                    "severity": "medium",
                    "issue": f"Content size ({child_wc}w) near identical to parent ({parent_word_count}w) AND same H1 — suspected duplicate",
                    "fix": "Rewrite body to focus specifically on the variant",
                })

        # Check 4: child has very thin content
        if child_wc < 100:
            issues.append({
                "page": child_url,
                "severity": "high",
                "issue": f"Sub-category has thin content ({child_wc} words)",
                "fix": "Add editorial text specific to this variant (aim 300+ words)",
            })

    return issues


def _classify_orphans():
    """
    Cross-reference orphan list with traffic + backlinks + clusters.
    Returns dict with 4 buckets: delete, reconnect, redirect, investigate.

    - DELETE: orphan AND 0 traffic AND 0 backlinks AND not in any cluster
    - RECONNECT: orphan BUT has traffic OR is part of a topic cluster
    - REDIRECT: orphan AND 0 traffic BUT has backlinks (preserve link equity)
    - INVESTIGATE: anything that doesn't fit cleanly
    """
    sf_issues = st.session_state.get("sf_crawl_issues") or {}
    orphan_list = sf_issues.get("orphan_pages") or []
    if not orphan_list:
        return {"delete": [], "reconnect": [], "redirect": [], "investigate": []}

    audit_results = st.session_state.get("audit_results", [])
    audit_by_url = {normalize_url(r.get("url", "")): r for r in audit_results}

    page_authority = st.session_state.get("page_authority")
    auth_lookup = {}
    if page_authority is not None and not page_authority.empty:
        for _, row in page_authority.iterrows():
            auth_lookup[normalize_url(str(row.get("page", "")))] = int(row.get("referring_domains", 0))

    topic_clusters = st.session_state.get("topic_clusters", {})
    clustered_urls = set()
    if isinstance(topic_clusters, dict):
        for k in (topic_clusters.get("page_topics") or {}).keys():
            clustered_urls.add(normalize_url(k))

    gsc_data = st.session_state.get("gsc_data")
    gsc_pages = {}
    if gsc_data is not None and hasattr(gsc_data, "groupby") and not gsc_data.empty:
        for page, grp in gsc_data.groupby("page"):
            gsc_pages[normalize_url(str(page))] = {
                "impressions": int(grp["impressions"].sum()),
                "clicks": int(grp["clicks"].sum()),
            }

    buckets = {"delete": [], "reconnect": [], "redirect": [], "investigate": [], "needs_content": []}

    for o in orphan_list:
        url = o.get("url") if isinstance(o, dict) else o
        if not url:
            continue
        norm = normalize_url(url)
        audit = audit_by_url.get(norm) or {}
        rd = auth_lookup.get(norm, 0)
        gsc = gsc_pages.get(norm, {"impressions": 0, "clicks": 0})
        in_cluster = norm in clustered_urls
        word_count = audit.get("word_count", 0)
        page_type = audit.get("page_type", "unknown")

        signals = {
            "url": url,
            "impressions": gsc["impressions"],
            "clicks": gsc["clicks"],
            "referring_domains": rd,
            "in_cluster": in_cluster,
            "word_count": word_count,
            "page_type": page_type,
        }

        has_traffic = gsc["impressions"] >= 10 or gsc["clicks"] > 0
        has_backlinks = rd > 0
        has_content = word_count >= 200
        is_product = page_type == "product"

        # PRODUCTS ARE NEVER AUTO-DELETED — they can be sold, so the right
        # action for thin products is to add content + reconnect, not delete.
        if is_product and not has_content:
            signals["reason"] = (
                f"Product with thin content ({word_count}w) — add description in "
                f"Magento and assign to category. DO NOT DELETE."
            )
            buckets["needs_content"].append(signals)
        elif not has_traffic and not has_backlinks and not in_cluster and not has_content and not is_product:
            signals["reason"] = f"No traffic ({gsc['impressions']} impr), no backlinks, no cluster, thin ({word_count}w)"
            buckets["delete"].append(signals)
        elif has_backlinks and not has_traffic:
            signals["reason"] = f"Has {rd} backlinks but no traffic — 301 to closest live page to preserve equity"
            buckets["redirect"].append(signals)
        elif has_traffic or in_cluster:
            reasons = []
            if has_traffic:
                reasons.append(f"{gsc['impressions']} impr / {gsc['clicks']} clicks")
            if in_cluster:
                reasons.append("in topic cluster")
            if has_backlinks:
                reasons.append(f"{rd} backlinks")
            signals["reason"] = "Misclassified orphan: " + ", ".join(reasons) + " — needs internal link from category/related page"
            buckets["reconnect"].append(signals)
        else:
            signals["reason"] = f"Edge case: {gsc['impressions']} impr, {rd} bl, cluster={in_cluster}, {word_count}w"
            buckets["investigate"].append(signals)

    # Sort each bucket by impact (most impressions/backlinks first)
    buckets["reconnect"].sort(key=lambda x: -(x["impressions"] + x["referring_domains"] * 100))
    buckets["redirect"].sort(key=lambda x: -x["referring_domains"])
    buckets["delete"].sort(key=lambda x: x["url"])
    buckets["needs_content"].sort(key=lambda x: x["url"])
    return buckets


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
        # Only real blogs/faq — NOT info/corporate pages like /hjalp/, /jobb, /kontakt
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

    # Site validation summary
    site_val = st.session_state.get("_site_validation")
    if isinstance(site_val, dict) and site_val.get("overall_health_score") is not None:
        health = site_val.get("overall_health_score", 0)
        score_color = "#33dd88" if health >= 70 else "#ffaa33" if health >= 40 else "#ff4455"
        st.markdown(
            f"<div style='background:#0d0d15; border-left:4px solid {score_color}; padding:0.8rem; border-radius:0 6px 6px 0; margin-bottom:1rem;'>"
            f"<div style='font-size:0.9rem; color:#e8e8f0;'><strong>Site Health: {health}/100</strong></div>"
            f"<div style='font-size:0.8rem; color:#c8b4ff;'>{site_val.get('summary', '')}</div></div>",
            unsafe_allow_html=True,
        )

    # Ideal structure summary (if run)
    ideal = st.session_state.get("_ideal_structure")
    if isinstance(ideal, dict):
        n_clusters = len(ideal.get("clusters", []))
        n_merges = len(ideal.get("merge", []))
        n_deletes = len(ideal.get("delete", []))
        n_creates = len(ideal.get("create", []))
        st.markdown(
            f"<div style='background:#0d0d15; border:1px solid #5533ff; padding:0.6rem; border-radius:6px; margin-bottom:1rem;'>"
            f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:0.65rem; color:#5533ff; margin-bottom:0.3rem;'>AI IDEAL STRUCTURE</div>"
            f"<div style='font-size:0.8rem; color:#c8b4ff;'>"
            f"{n_clusters} ideal clusters · {n_merges} pages to merge · {n_deletes} to delete · {n_creates} to create</div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("💡 Run **Generate Ideal Structure** in Site Map to get AI-recommended merges, deletes, and new pages.")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "🔀 Merge",
        "➕ Create",
        "↗ Redirect",
        "🚫 Noindex",
        "🗑 Delete",
        "📝 Blogs review",
        "🧩 Topic Gaps",
    ])

    # ── TAB 1: CANNIBALIZATION ACTIONS ──────────────────────
    with tab1:
        st.markdown("### Keyword conflicts — what to do")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "Pages competing for the same query. Each conflict is classified automatically with "
            "concrete Magento instructions. Click an item to see what to do + generate new meta titles.</p>",
            unsafe_allow_html=True,
        )

        cannibal_df = st.session_state.get("cannibalization")
        if cannibal_df is None or cannibal_df.empty:
            st.info("No cannibalization data — run Step 5 in Run Pipeline.")
        else:
            all_work = cannibal_df[cannibal_df["severity"].isin(["severe", "moderate", "handled"])].copy()
            all_work = all_work[~all_work["merge_action"].str.contains("DIFFERENT INTENTS|Homepage involved", na=False)]

            # Split: items needing action vs already handled
            # Filter on severity="handled" (only set when FULLY resolved:
            # titles differentiated + content OK + links OK + quality OK).
            # NOT on already_differentiated which only checks titles.
            handled = all_work[all_work["severity"] == "handled"] if "severity" in all_work.columns else all_work.iloc[0:0]
            work = all_work[all_work["severity"] != "handled"] if "severity" in all_work.columns else all_work

            if len(handled) > 0:
                st.success(f"✅ {len(handled)} conflicts already have differentiated meta titles — no action needed. Showing only items that need work.")

            # Group by cannibal_type
            grouped = {}
            for _, row in work.iterrows():
                t = row.get("cannibal_type", "unknown")
                grouped.setdefault(t, []).append(row)

            type_ui = {
                "duplicate_categories": ("⚠ Duplicate categories — MERGE", "#ff6644",
                    "Two category pages target the same query. True cannibalization. "
                    "**Fix:** pick ONE winner, 301 redirect the loser, move products, update meta."),
                "category_vs_children": ("🌳 Category + sub-categories", "#33dd88",
                    "NORMAL. Parent category and its sub-categories both rank. "
                    "**Fix:** differentiate meta. Parent = generic, children = specific variant."),
                "category_vs_products": ("📦 Category + products", "#44bb88",
                    "NORMAL. A category and its products both rank for a generic query. "
                    "**Fix:** category meta targets generic, product meta targets product name."),
                "products_same_parent": ("🎯 Products under same category", "#5533ff",
                    "Products in the same category compete. "
                    "**Fix:** each product gets UNIQUE meta with its brand/variant."),
                "products_no_category": ("🏗 Missing category page", "#ffaa33",
                    "Products compete for a generic query but no category targets it. "
                    "**Fix:** CREATE a new category in Magento and assign the products."),
                "true_duplicate": ("🔀 True duplicates — merge", "#ff4455",
                    "Two similar pages compete. **Fix:** 301 redirect the loser to the winner."),
                "mixed": ("🔗 Mixed types", "#9b9bb8",
                    "Different page types compete. **Fix:** category owns generic query, products/blogs target specific variants."),
            }

            # Counts
            cols = st.columns(len(type_ui))
            for i, (tk, (label, color, _)) in enumerate(type_ui.items()):
                count = len(grouped.get(tk, []))
                if count > 0:
                    cols[i].metric(label.split(" ", 1)[0] + " " + label.split(" ", 1)[1][:20], count)
            st.markdown("---")

            for tk in type_ui:
                rows = grouped.get(tk, [])
                if not rows:
                    continue
                label, color, explanation = type_ui[tk]

                st.markdown(
                    f"<div style='border-left:4px solid {color}; padding:0.6rem 0.8rem; margin:1rem 0; background:#0d0d15; border-radius:0 4px 4px 0;'>"
                    f"<div style='font-weight:700; color:#e8e8f0; font-size:1.05rem;'>{label} ({len(rows)})</div>"
                    f"<div style='color:#c8b4ff; font-size:0.85rem; margin-top:0.3rem;'>{explanation}</div></div>",
                    unsafe_allow_html=True,
                )

                for row in sorted(rows, key=lambda r: -r.get("lost_clicks_estimate", 0))[:15]:
                    query = row["query"]
                    winner = row["recommended_winner"]
                    pages = row["pages_detail"]
                    lost = row.get("lost_clicks_estimate", 0)
                    parent = row.get("cannibal_parent_url")
                    action_text = row.get("cannibal_action", "")

                    with st.expander(f"'{query}' — {len(pages)} pages · {lost:,} lost clicks"):
                        # Pages table
                        st.markdown("**Pages competing for this query:**")
                        for p in pages:
                            page_url = p.get("page", "")
                            is_winner = normalize_url(page_url) == normalize_url(winner)
                            marker = " 🏆" if is_winner else ""
                            st.markdown(
                                f"- `{shorten_url(page_url)}` · pos {p.get('position','?')} · "
                                f"{p.get('clicks',0)} cl · {p.get('impressions',0):,} impr{marker}"
                            )

                        # Action instructions (rendered as markdown)
                        if action_text:
                            st.markdown("---")
                            st.markdown(action_text)

                        # Quality validation for category_vs_children
                        if tk == "category_vs_children" and parent:
                            issues = _validate_subcategory_quality(parent, pages)
                            if issues:
                                st.markdown("**🚨 Detected issues:**")
                                for iss in issues:
                                    sev_icon = "🔴" if iss["severity"] == "high" else "🟡"
                                    st.markdown(f"{sev_icon} `{shorten_url(iss['page'])}` — {iss['issue']}")
                                    st.caption(f"Fix: {iss['fix']}")

                        # AI meta generation button — available for ALL types
                        ai_key = f"_cannibal_meta_{stable_hash(query)}"
                        if ai_key in st.session_state:
                            meta_results = st.session_state[ai_key]
                            st.markdown("**✅ Generated meta (copy-paste into Magento):**")
                            for page_url, meta in meta_results.items():
                                variants = meta.get("variants", [])
                                if variants:
                                    best = variants[0]
                                    st.markdown(f"**`{shorten_url(page_url)}`**")
                                    st.code(
                                        f"Title: {best.get('title','')}\n"
                                        f"Description: {best.get('description','')}",
                                        language="text",
                                    )
                        else:
                            if st.button(
                                f"🤖 Generate differentiated meta titles for all {len(pages)} pages",
                                key=f"btn_{ai_key}",
                            ):
                                with st.spinner("AI generating meta per page..."):
                                    try:
                                        _generate_cannibal_subcategory_meta(query, pages, row, ai_key)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error: {e}")

                        # ── Rewrite content button per page with issues ──
                        # Only for pages that are NOT being redirected (redirect + rewrite = contradictory)
                        # Build set of pages that WILL be redirected (for suppressing rewrite button)
                        redirect_losers_set = set()
                        if tk in ("true_duplicate", "duplicate_categories"):
                            from utils.site_patterns import get_sale_patterns as _gsp
                            _sale_pats = _gsp()
                            from urllib.parse import urlparse as _up2
                            _winner_p = _up2(normalize_url(winner)).path.rstrip("/")
                            _winner_parent = "/".join(_winner_p.split("/")[:-1]) if "/" in _winner_p else ""
                            for rp in pages:
                                rp_norm = normalize_url(rp.get("page", ""))
                                rp_path = _up2(rp_norm).path.rstrip("/")
                                rp_parent = "/".join(rp_path.split("/")[:-1]) if "/" in rp_path else ""
                                if rp_norm == normalize_url(winner):
                                    continue
                                if any(sp in rp.get("page", "").lower() for sp in _sale_pats):
                                    continue
                                if _winner_p and rp_path.startswith(_winner_p + "/"):
                                    continue
                                if _winner_parent and rp_parent == _winner_parent and _winner_parent != "":
                                    continue  # sibling category
                                from utils.page_profile import build_page_profile as _bpp
                                if _bpp(rp.get("page", "")).get("page_type") == "product":
                                    continue
                                redirect_losers_set.add(rp_norm)

                        for p in pages:
                            p_url = p.get("page", "")
                            p_norm = normalize_url(p_url)
                            p_short = shorten_url(p_url)
                            rewrite_key = f"_cannibal_rewrite_{stable_hash(p_url + query)}"

                            # Collect all issues for this specific page from action_text
                            page_issues = []
                            if action_text and p_short in action_text:
                                page_issues.append("See issues above")
                            # Add quality verdict
                            q_key = f"_quality_{stable_hash(p_url)}"
                            q_data = st.session_state.get(q_key, {})
                            if isinstance(q_data, dict) and q_data.get("verdict") in ("REWRITE", "IMPROVE"):
                                page_issues.extend(q_data.get("main_issues", []))
                                page_issues.extend(q_data.get("specific_fixes", []))

                            if rewrite_key in st.session_state:
                                rw = st.session_state[rewrite_key]
                                has_split = isinstance(rw, dict) and (rw.get("top_html") or rw.get("bottom_html"))
                                has_single = isinstance(rw, dict) and rw.get("html") and not has_split

                                if has_split:
                                    st.markdown(f"**✅ Rewritten texts for `{p_short}`:**")

                                    # TOP TEXT
                                    top_html = rw.get("top_html", "")
                                    if top_html:
                                        st.markdown("**📌 TOP TEXT** (paste in Magento → Category → Description, ABOVE product grid)")
                                        st.markdown(
                                            f"<div style='background:#1a1a2e; border:1px solid #33dd88; border-radius:6px; padding:1rem; margin:0.5rem 0;'>{top_html}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        st.text_area(
                                            "Top text HTML (select all + copy)",
                                            value=top_html,
                                            height=120,
                                            key=f"ta_top_{rewrite_key}",
                                        )

                                    # BOTTOM TEXT — includes FAQ schema merged in
                                    bottom_html = rw.get("bottom_html", "")
                                    faq_schema = rw.get("faq_schema")
                                    if isinstance(faq_schema, dict) and faq_schema.get("mainEntity"):
                                        import json as _json
                                        schema_script = f'<script type="application/ld+json">\n{_json.dumps(faq_schema, ensure_ascii=False, indent=2)}\n</script>'
                                        bottom_html = bottom_html + "\n" + schema_script

                                    if bottom_html:
                                        st.markdown("**📌 BOTTOM TEXT + FAQ SCHEMA** (paste in Magento → Category → Description, BELOW product grid. Schema is included at the end.)")
                                        st.markdown(
                                            f"<div style='background:#1a1a2e; border:1px solid #5533ff; border-radius:6px; padding:1rem; margin:0.5rem 0;'>{rw.get('bottom_html', '')}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        st.text_area(
                                            "Bottom text + FAQ schema HTML (select all + copy — paste as ONE block)",
                                            value=bottom_html,
                                            height=350,
                                            key=f"ta_bottom_{rewrite_key}",
                                        )

                                    fixed = rw.get("issues_fixed", [])
                                    if fixed:
                                        st.caption("Issues fixed: " + " · ".join(fixed))

                                    combined = (top_html or "") + "\n\n<!-- PRODUCT GRID -->\n\n" + (bottom_html or "")
                                    st.download_button(
                                        f"⬇ Download all",
                                        data=combined,
                                        file_name=f"{p_url.split('/')[-1] or 'page'}_rewrite.html",
                                        mime="text/html",
                                        key=f"dl_{rewrite_key}",
                                    )

                                elif has_single:
                                    # Fallback for old format (single html field)
                                    st.markdown(f"**✅ Rewritten text for `{p_short}`** ({rw.get('word_count', '?')} words):")
                                    st.markdown(
                                        f"<div style='background:#1a1a2e; border:1px solid #2a2a40; border-radius:6px; padding:1rem; margin:0.5rem 0;'>{rw['html']}</div>",
                                        unsafe_allow_html=True,
                                    )
                                    st.text_area("HTML source", value=rw["html"], height=300, key=f"ta_{rewrite_key}")
                                    st.download_button(f"⬇ Download", data=rw["html"], file_name=f"{p_url.split('/')[-1]}_rewrite.html", mime="text/html", key=f"dl_{rewrite_key}")
                            elif page_issues or (isinstance(q_data, dict) and q_data.get("verdict") == "REWRITE"):
                                # Don't show rewrite for pages being redirected (contradictory)
                                if p_norm in redirect_losers_set:
                                    st.caption(f"↗ `{p_short}` will be 301 redirected — no rewrite needed")
                                elif st.button(f"📝 Rewrite content for {p_short}", key=f"btn_{rewrite_key}"):
                                    with st.spinner(f"AI rewriting content for {p_short}..."):
                                        try:
                                            _generate_cannibal_rewrite(p_url, query, page_issues, action_text, rewrite_key)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Error: {e}")

                        # For true_duplicate + duplicate_categories: show redirect instructions
                        # BUT skip pages that serve a different PURPOSE (sale/rea pages, filter views)
                        if tk in ("true_duplicate", "duplicate_categories"):
                            losers = [p["page"] for p in pages if normalize_url(p["page"]) != normalize_url(winner)]
                            # Filter out pages that should NOT be redirected:
                            # 1. Sale/discount pages (serve different purpose) — from config, not hardcoded
                            # 2. Sub-categories of the winner (they're children, not duplicates)
                            # 3. Product pages (they're products, not duplicate categories)
                            from utils.site_patterns import get_sale_patterns
                            sale_patterns = get_sale_patterns()
                            from urllib.parse import urlparse as _up
                            winner_url_path = _up(normalize_url(winner)).path.rstrip("/")

                            real_losers = []
                            skipped_losers = []
                            for l in losers:
                                l_lower = l.lower()
                                l_norm = normalize_url(l)
                                l_url_path = _up(l_norm).path.rstrip("/")
                                skip_reason = None

                                # Parent paths for sibling detection
                                winner_parent = "/".join(winner_url_path.split("/")[:-1]) if "/" in winner_url_path else ""
                                loser_parent = "/".join(l_url_path.split("/")[:-1]) if "/" in l_url_path else ""

                                if any(sp in l_lower for sp in sale_patterns):
                                    skip_reason = "sale/discount page — keep, differentiate meta + add link to main category"
                                elif winner_url_path and l_url_path.startswith(winner_url_path + "/"):
                                    skip_reason = "sub-category of winner — keep, differentiate meta + add link to parent"
                                elif winner_parent and loser_parent == winner_parent and winner_parent != "":
                                    # SIBLINGS: same parent directory (e.g. /dildos/klassisk-dildo + /dildos/dildo-maskin)
                                    skip_reason = f"sibling category under {winner_parent}/ — keep, each targets a different product type"
                                else:
                                    from utils.page_profile import build_page_profile
                                    l_profile = build_page_profile(l)
                                    if l_profile.get("page_type") == "product":
                                        skip_reason = "product page — keep, differentiate meta + ensure assigned to category"

                                if skip_reason:
                                    skipped_losers.append((l, skip_reason))
                                else:
                                    real_losers.append(l)

                            if skipped_losers:
                                st.info(
                                    f"**{len(skipped_losers)} page(s) kept (not redirected) — add links instead:**"
                                )
                                for s_url, reason in skipped_losers:
                                    st.markdown(f"- `{shorten_url(s_url)}` — {reason}")
                                    st.markdown(
                                        f"  → Add link to winner: `<a href=\"{winner}\">{query}</a>`"
                                    )

                            if real_losers:
                                st.markdown("**301 redirect (paste in Magento URL Rewrite Management):**")
                                for l in real_losers[:5]:
                                    st.code(f"{l}  →  {winner}", language="text")
                                if tk == "duplicate_categories":
                                    st.info("After redirect: move all products from loser category to winner category in Magento → Catalog → Categories.")

    # ── TAB 2: CREATE ─────────────────────────────────────────
    with tab2:
        creates = _pages_to_create()
        st.markdown(f"### {len(creates)} new pages/articles to create")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "Combined from: AI ideal structure + content roadmap + per-page plans.</p>",
            unsafe_allow_html=True,
        )
        if not creates:
            st.success("No new pages recommended")
        # Group by source
        by_source = {}
        for c in creates:
            by_source.setdefault(c.get("source", "other"), []).append(c)
        for source, items in by_source.items():
            source_labels = {
                "ideal_structure": "🏗 AI Ideal Structure",
                "content_roadmap": "📊 Content Roadmap (from topic clusters)",
                "page_plan": "📄 Per-page Implementation Plans",
            }
            st.markdown(f"#### {source_labels.get(source, source)} ({len(items)} items)")
            for c in items[:20]:
                label = c.get("url", "") if c.get("url", "").startswith("(") else f"`{c.get('url', '')}`"
                if c.get("already_exists"):
                    st.markdown(f"- ~~{label}~~ — **SKIP: {c['already_exists']}**")
                else:
                    st.markdown(f"- {label}")
                if c.get("keyword"):
                    st.markdown(f"  <div style='color:#c8b4ff; font-size:0.75rem; margin-left:1rem;'>Keywords: {c.get('keyword', '')}</div>", unsafe_allow_html=True)
                if c.get("why"):
                    st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>{c.get('why', '')[:200]}</div>", unsafe_allow_html=True)
                if c.get("link_from"):
                    st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>Link from: {c.get('link_from', '')}</div>", unsafe_allow_html=True)

    # ── TAB 3: REDIRECT ──────────────────────────────────────
    with tab3:
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

    # ── TAB 4: NOINDEX ───────────────────────────────────────
    with tab4:
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

    # ── TAB 5: DELETE ────────────────────────────────────────
    with tab5:
        # Smart orphan classification — distinguish real orphans from misclassified
        orphan_buckets = _classify_orphans()
        n_orphan_total = sum(len(v) for v in orphan_buckets.values())

        if n_orphan_total > 0:
            st.markdown(f"### 🧭 Smart orphan classification ({n_orphan_total} total)")
            st.markdown(
                "<p style='color:#9b9bb8; font-size:0.85rem;'>"
                "Cross-references SF orphan list with GSC traffic, Ahrefs backlinks, "
                "and topic clusters. NOT all orphans should be deleted — many just lost their internal link.</p>",
                unsafe_allow_html=True,
            )
            cols = st.columns(5)
            cols[0].metric("🗑 Delete (true orphan)", len(orphan_buckets["delete"]))
            cols[1].metric("🔗 Reconnect (misclassified)", len(orphan_buckets["reconnect"]))
            cols[2].metric("↗ Redirect (has backlinks)", len(orphan_buckets["redirect"]))
            cols[3].metric("📝 Needs content (products)", len(orphan_buckets["needs_content"]))
            cols[4].metric("❓ Investigate", len(orphan_buckets["investigate"]))

            if orphan_buckets["needs_content"]:
                with st.expander(f"📝 Products needing content ({len(orphan_buckets['needs_content'])}) — DO NOT delete", expanded=False):
                    st.info("These are PRODUCT pages with thin/missing content. They can still be sold — add descriptions in Magento and assign to the right category. Never auto-delete products.")
                    for o in orphan_buckets["needs_content"][:50]:
                        st.markdown(f"- `{o['url']}` ({o['word_count']}w)")
                        st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>{o['reason']}</div>", unsafe_allow_html=True)

            with st.expander(f"🔗 Reconnect ({len(orphan_buckets['reconnect'])}) — DO NOT delete", expanded=False):
                st.info("These pages have traffic, backlinks, or are in topic clusters. They lost their internal link but should be RECONNECTED via category navigation, not deleted.")
                for o in orphan_buckets["reconnect"][:50]:
                    st.markdown(f"- `{o['url']}` ({o['page_type']}, {o['word_count']}w)")
                    st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>{o['reason']}</div>", unsafe_allow_html=True)

            with st.expander(f"↗ Redirect ({len(orphan_buckets['redirect'])}) — preserve link equity", expanded=False):
                st.info("These pages have backlinks but zero traffic. 301-redirect them to the closest live, related page to preserve link equity. Do NOT just delete — you'd lose the backlinks.")
                for o in orphan_buckets["redirect"][:50]:
                    st.markdown(f"- `{o['url']}` ({o['referring_domains']} backlinks)")
                    st.markdown(f"  <div style='color:#9b9bb8; font-size:0.75rem; margin-left:1rem;'>{o['reason']}</div>", unsafe_allow_html=True)

            with st.expander(f"🗑 True orphans to delete ({len(orphan_buckets['delete'])})", expanded=False):
                st.warning("These have NO traffic, NO backlinks, NO cluster, and thin content. Safe to delete.")
                for o in orphan_buckets["delete"][:50]:
                    st.markdown(f"- `{o['url']}` ({o['page_type']}, {o['word_count']}w)")

            if orphan_buckets["investigate"]:
                with st.expander(f"❓ Investigate ({len(orphan_buckets['investigate'])})", expanded=False):
                    st.markdown("Edge cases — manual review needed.")
                    for o in orphan_buckets["investigate"][:50]:
                        st.markdown(f"- `{o['url']}` — {o['reason']}")
            st.markdown("---")

        deletes = _pages_to_delete()
        ideal_deletes = _pages_to_delete_ideal()
        st.markdown(f"### {len(deletes) + len(ideal_deletes)} pages to consider deleting")

        if ideal_deletes:
            st.markdown("#### 🏗 AI Ideal Structure recommendations")
            st.markdown(
                "<p style='color:#9b9bb8; font-size:0.85rem;'>Pages the AI recommends deleting based on site architecture review.</p>",
                unsafe_allow_html=True,
            )
            for d in ideal_deletes[:30]:
                st.markdown(f"- `{d.get('url', '')}` — {d.get('why', '')}")
            st.markdown("---")

        st.markdown("#### 📊 Data-driven candidates (no traffic, no backlinks, thin content)")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "Pages with: 0 clicks, <10 impressions, 0 backlinks, <200 words.</p>",
            unsafe_allow_html=True,
        )
        if not deletes:
            st.success("No clearly deletable pages from data analysis")
        for d in deletes[:30]:
            st.markdown(f"- `{d['url']}` ({d['page_type']}) · {d['word_count']} words · {d['impressions']} impressions")

    # ── TAB 6: BLOGS TO REVIEW ───────────────────────────────
    with tab6:
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

    # ── TAB 7: TOPIC GAPS ────────────────────────────────────
    with tab7:
        gaps = st.session_state.get("content_gaps", []) or []
        st.markdown(f"### {len(gaps)} topic clusters with content gaps")
        st.markdown(
            "<p style='color:#9b9bb8; font-size:0.85rem;'>"
            "Topics where the site underperforms: poor CTR despite impressions, "
            "topic split across too many pages, thin coverage, or missing backlinks. "
            "Source: topic cluster analysis (pipeline step 6).</p>",
            unsafe_allow_html=True,
        )
        if not gaps:
            st.info("No gaps found — run **Build Topic Clusters** in Run Pipeline first.")
        else:
            high = [g for g in gaps if isinstance(g, dict) and g.get("priority") == "high"]
            medium = [g for g in gaps if isinstance(g, dict) and g.get("priority") == "medium"]

            if high:
                st.markdown("#### 🔴 High priority")
                for g in high[:30]:
                    with st.expander(f"{g.get('topic','?')} · {g.get('impressions',0):,} impressions · {g.get('queries',0)} queries"):
                        for issue in g.get("issues", []):
                            st.markdown(f"- {issue}")
                        st.markdown(
                            "<div style='color:#9b9bb8; font-size:0.75rem; margin-top:0.5rem;'>"
                            "Action: review in Topic Clusters view for consolidation, new content, or link building.</div>",
                            unsafe_allow_html=True,
                        )

            if medium:
                st.markdown("#### 🟡 Medium priority")
                for g in medium[:30]:
                    with st.expander(f"{g.get('topic','?')} · {g.get('impressions',0):,} impressions · {g.get('queries',0)} queries"):
                        for issue in g.get("issues", []):
                            st.markdown(f"- {issue}")
