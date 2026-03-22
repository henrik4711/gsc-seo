"""
AI content generation: meta titles, descriptions, and landing page text
Uses Claude claude-sonnet-4-20250514 via Anthropic API
"""

import os
import json
import anthropic
import streamlit as st
from typing import Optional


# ── Anti-hallucination rules injected into all prompts that assess page state ──
# These prevent AI from contradicting the data it is given.
ANTI_HALLUCINATION_RULES = """
CRITICAL — ACCURACY RULES (never violate these):
- Base ALL claims ONLY on the data provided below. Do NOT assume or invent page state.
- If Title is not "" (empty), the page HAS a title. Do NOT say "missing title" or "no title".
- If Meta description is not "" (empty), the page HAS a meta description. Do NOT say "missing description".
- If Word count > 0, the page has content. Do NOT say "empty page" or "no content".
- If H1 is not "" (empty), the page HAS an H1. Do NOT say "lacks H1" or "missing H1".
- If body text/content excerpt is provided, READ it before assessing content quality.
- NEVER say a page is "completely empty" unless word count is literally 0 AND title is "" AND meta description is "".
- When stating what is wrong, quote the ACTUAL current value. Example: "Title is 85 chars (too long)" not just "title needs fixing".
- If something looks fine, say it is fine. Do NOT invent problems."""


def _strip_nav_text(text: str) -> str:
    """Remove navigation/header/trust-bar text from any string."""
    import re
    if not text:
        return ""

    patterns = [
        # Mshop trust bar / header fragments
        r'\d+\s*(?:kr frakt|dagars? (?:leverans|öppet köp))[^.]*',
        r'\d+\s*(?:omdömen|recensioner|stjärnor)[^.]*',
        r'(?:Fri (?:frakt )?över|Spara upp till)\s*\d+[^.]*',
        r'100%\s*diskret[^.]*',
        r'(?:Shoppa efter (?:märke|stil)\s*)+',
        r'(?:Alla\s+)?(?:erbjudanden[a-z]*|Kategorier|Produkter|Populära (?:sökord|produkter)|Sök förslag)\s*',
        r'(?:Varukorg|Vinterrea|REA)\s*',
        r'Mshop\.se\s*(?:0\s*)?',
        r'(?:Hjälp & Kontakt|Våra butiker)\s*',
        r'(?:Intimleksaker|Underkläder & Förspel|Hälsotek)\s*',
        r'(?:Basques & Bodies|Klänningar & Kjolar|Catsuits & Bodystockings)\s*',
        r'(?:Sexiga Underkläder|Bondage|Rollspel)\s*',
        r'(?:Effekt|Kroppsdel|Hälsa & Sexhjälpmedel)\s*',
        r'Njutning på dina villkor\.?\s*',
        r'Alla Sexdockor\s*',
        r'(?:Lägg i varukorg|Köp hela kitet)\s*',
    ]
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)

    # Remove repeated short capitalized fragments (menu items)
    cleaned = re.sub(r'(?:\b[A-ZÅÄÖ][a-zåäö]+\b\s+){5,}', ' ', cleaned)
    # Clean multiple spaces
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
    return cleaned


def _clean_body_text(page_data, max_chars: int = 1500) -> str:
    """
    Get clean editorial text from a page dict or raw string.
    Strips navigation, header, trust-bar text.
    """
    # Accept raw string too
    if isinstance(page_data, str):
        return _strip_nav_text(page_data)[:max_chars]

    # Best: use specific editorial text fields
    intro = page_data.get("intro_text") or ""
    bottom = page_data.get("bottom_text") or ""
    if intro or bottom:
        combined = (intro + "\n\n" + bottom).strip()
        return _strip_nav_text(combined)[:max_chars]

    body = page_data.get("body_text") or page_data.get("full_body_text") or ""
    if not body:
        return ""

    cleaned = _strip_nav_text(body)

    # Find where real content starts — first sentence with >40 chars
    import re
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    for sent in sentences:
        if len(sent) > 40 and not any(nav in sent.lower() for nav in ['shoppa', 'varukorg', 'populära', 'omdömen', 'kundvagn', 'checkout']):
            idx = cleaned.index(sent) if sent in cleaned else 0
            return cleaned[idx:idx + max_chars].strip()

    return cleaned[:max_chars].strip()


def _parse_ai_json(message) -> dict:
    """Safely parse JSON from an AI response. Returns dict or raises with clear error."""
    if not message.content:
        raise ValueError("AI returned an empty response — try again.")
    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from mixed text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
        raise ValueError(
            f"AI returned invalid JSON. First 200 chars: {raw[:200]}..."
        )


def get_client(api_key: str = "") -> anthropic.Anthropic:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("No Anthropic API key provided. Set ANTHROPIC_API_KEY env var or enter key in Setup.")
    return anthropic.Anthropic(api_key=key)


def generate_meta_suggestions(
    client: anthropic.Anthropic,
    page_data: dict,
    target_keywords: list,
    site_context: str = "",
    language: str = "Swedish",
    n_variants: int = 3,
) -> dict:
    """
    Generate optimized meta title and description variants
    """
    current_title = page_data.get("title") or ""
    current_desc = page_data.get("meta_description") or ""
    url = page_data.get("url", "")
    h1 = page_data.get("h1") or ""
    h2s = page_data.get("h2s", [])[:5]
    page_type = page_data.get("page_type", "unknown")

    # Category-specific context
    cat_context = ""
    if page_type == "category":
        cat_audit = page_data.get("content_audit", {})
        stats = cat_audit.get("content_stats", {})
        cat_context = f"""
Page type: CATEGORY PAGE (shows products in a grid)
Products on the page: {stats.get('product_count', '?')}
Editorial words (intro+bottom): {stats.get('total_editorial', '?')}
Has FAQ: {'Yes' if stats.get('has_faq') else 'No'}
Has buying guide: {'Yes' if stats.get('has_buying_guide') else 'No'}
IMPORTANT: Meta for category pages should focus on category intent (browse/explore), not single-product intent."""
    elif page_type == "product":
        cat_context = "\nPage type: PRODUCT PAGE (single product)\nIMPORTANT: Meta should focus on product-specific features and purchase intent."
    elif page_type == "blog":
        cat_context = "\nPage type: BLOG/GUIDE\nIMPORTANT: Meta should focus on informational intent and value for the reader."

    prompt = f"""You are a senior SEO specialist and conversion optimization expert for an e-commerce webshop.
{ANTI_HALLUCINATION_RULES}

## CURRENT SITUATION
URL: {url}{cat_context}
Current title: "{current_title}" ({len(current_title)} chars)
Current meta description: "{current_desc}" ({len(current_desc)} chars)
H1: "{h1}"
H2s: {', '.join(h2s) if h2s else 'None'}
Word count: {page_data.get('word_count', 0)}
Impressions: {page_data.get('impressions', 0):,}
Lost clicks estimate: {page_data.get('lost_clicks_estimate', 0):.0f}
Average position: {page_data.get('position', 0):.1f}
Referring domains: {page_data.get('referring_domains', 0)}
Target keywords from GSC: {', '.join(target_keywords)}
Site context: {site_context}

## TASK
Generate {n_variants} variants of improved meta title + description.

### TITLE REQUIREMENTS (critical):
- 50-60 characters (NEVER over 65)
- Primary keyword as early as possible (preferably words 1-3)
- One concrete benefit or USP
- Avoid: "Buy", "Order" as first word (Google can add that)
- Language: {language}

### META DESCRIPTION REQUIREMENTS (critical):
- 140-160 characters (NEVER over 165)
- Include primary keyword naturally
- Strong CTA: free shipping, fast delivery, discreet shipping, wide selection
- Create curiosity/FOMO or solve a problem
- Include specific differentiating details
- Language: {language}

## OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "analysis": "Brief analysis of what's wrong with the current meta (2-3 sentences)",
  "variants": [
    {{
      "title": "...",
      "title_chars": 0,
      "description": "...",
      "description_chars": 0,
      "strategy": "What is the strategy behind this variant (1 sentence)"
    }}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    result = _parse_ai_json(message)
    # Fill in char counts if model didn't
    for v in result.get("variants", []):
        v["title_chars"] = len(v.get("title", ""))
        v["description_chars"] = len(v.get("description", ""))
    
    return result


def generate_content_audit(
    client: anthropic.Anthropic,
    page_data: dict,
    target_keywords: list,
    gsc_queries: list,
) -> dict:
    """
    Analyse existing page content for keyword gaps and SEO opportunities
    """
    body = _clean_body_text(page_data, 4000)
    url = page_data.get("url", "")
    title = page_data.get("title") or ""
    meta_desc = page_data.get("meta_description") or ""
    h1 = page_data.get("h1") or ""
    h2s = page_data.get("h2s", [])[:10]
    page_type = page_data.get("page_type", "unknown")
    word_count = page_data.get("word_count", 0)
    impressions = page_data.get("impressions", 0)

    body_word_count = len(body.split()) if body else 0
    prompt = f"""You are an SEO content analyst. Analyze this landing page and its keyword coverage.
{ANTI_HALLUCINATION_RULES}

URL: {url}
Page type: {page_type}
Title: "{title}" ({len(title)} chars)
Meta description: "{meta_desc}" ({len(meta_desc)} chars)
H1: "{h1}"
H2s: {', '.join(h2s) if h2s else 'None'}
Total word count: {word_count}
Impressions: {impressions:,}
GSC keywords driving traffic: {', '.join(gsc_queries[:20])}
Target focus keywords: {', '.join(target_keywords)}

CURRENT CONTENT ({body_word_count} words — excerpt):
{body}

## TASK: Perform a keyword gap analysis

Return ONLY JSON (no markdown):
{{
  "keyword_coverage": [
    {{"keyword": "...", "present": true/false, "context": "Where/how it is used or missing"}}
  ],
  "missing_topics": ["Topics that should be covered but are not"],
  "thin_content": true/false,
  "content_issues": ["List of specific content issues"],
  "opportunities": ["Specific opportunities to improve SEO content"],
  "recommended_structure": {{
    "suggested_h1": "...",
    "suggested_sections": ["H2 section 1", "H2 section 2", "..."]
  }},
  "overall_score": 0-100,
  "summary": "2-3 sentences about the page's SEO content status"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return _parse_ai_json(message)


def assess_content_quality_batch(
    client: anthropic.Anthropic,
    pages: list,
    site_context: str = "",
    language: str = "Swedish",
    topic_clusters: dict = None,
) -> list:
    """
    Batch assess content quality for multiple pages in a single call.
    Evaluates up to 5 pages at once to reduce API calls.
    Includes cluster context so AI can assess if text supports the topic structure.
    """
    page_sections = []
    for i, p in enumerate(pages):
        body = _clean_body_text(p, 800)

        # Get cluster context for this page
        cluster_info = ""
        if topic_clusters:
            page_topics = topic_clusters.get("page_topics", {})
            url = p.get("url", "")
            topics = page_topics.get(url, [])
            if topics:
                topic_names = [t.get("topic", "") for t in topics[:5]]
                cluster_info = f"Topic cluster(s): {', '.join(topic_names)}\n"

            # Is this a pillar page?
            from urllib.parse import urlparse
            page_path = urlparse(url).path.lower().rstrip("/")
            child_pages = [u for u in page_topics.keys()
                          if urlparse(u).path.lower().rstrip("/").startswith(page_path + "/")]
            if child_pages:
                cluster_info += f"PILLAR page with {len(child_pages)} child pages\n"
                cluster_info += f"Child pages: {', '.join(c.split('/')[-1] for c in child_pages[:8])}\n"

        internal_links = p.get("internal_links", 0)
        link_count = internal_links if isinstance(internal_links, int) else len(internal_links)
        page_sections.append(
            f"### PAGE {i+1}\n"
            f"URL: {p.get('url', '')}\n"
            f"Page type: {p.get('page_type', 'unknown')}\n"
            f"Title: \"{(p.get('title') or '')[:80]}\" ({len(p.get('title') or '')} chars)\n"
            f"Meta description: \"{(p.get('meta_description') or '')[:80]}\" ({len(p.get('meta_description') or '')} chars)\n"
            f"H1: \"{(p.get('h1') or '')[:80]}\"\n"
            f"Word count: {p.get('word_count', 0)}\n"
            f"Internal links: {link_count}\n"
            f"Impressions: {p.get('impressions', 0):,}\n"
            f"{cluster_info}"
            f"Target keywords: {', '.join(p.get('target_keywords', [])[:5])}\n"
            f"Text sample:\n{body}\n"
        )

    prompt = f"""You are a Google Search Quality Rater evaluating page content quality.
{ANTI_HALLUCINATION_RULES}

For EACH page below, assess the text quality using Google's Helpful Content guidelines.

## SITE CONTEXT
{site_context}
Language: {language}

## PAGES TO EVALUATE
{chr(10).join(page_sections)}

## EVALUATE EACH PAGE ON:
1. **Helpfulness**: Does the text actually help the user? Does it answer questions, guide decisions, or provide unique value? Or is it generic filler anyone could write?
2. **Originality**: Is this unique content with real insights? Or is it template text / obvious AI spam / keyword-stuffed?
3. **Depth**: Does it cover the topic thoroughly? Or is it thin and superficial?
4. **Readability**: Is it well-structured, easy to scan, clear language? Or is it a wall of repetitive text?
5. **E-E-A-T**: Does it show experience, expertise? Does it feel like it was written by someone who knows the products? Or is it generic marketing fluff?
6. **Cluster fit**: If this is a PILLAR page, does the text provide a comprehensive overview that links to and summarizes ALL child topics? If it's a SPOKE page, does it go deep on its specific subtopic and reference the pillar? Does the text make sense in the context of the site's topic structure?
7. **Standalone value**: Would this text make sense on its own? Does it have a clear purpose and structure? Or does it feel like it was written just for SEO with no real reader in mind?

## VERDICTS:
- **KEEP** (7-10): Good content, minor improvements only
- **IMPROVE** (4-6): Has value but needs specific fixes
- **REWRITE** (1-3): Poor quality, should be replaced entirely

## OUTPUT (JSON only):
{{
  "assessments": [
    {{
      "url": "page URL",
      "verdict": "KEEP|IMPROVE|REWRITE",
      "score": 0,
      "summary": "1-2 sentences explaining the verdict",
      "main_issues": ["issue 1", "issue 2"],
      "specific_fixes": ["exact fix 1", "exact fix 2"]
    }}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    result = _parse_ai_json(message)
    return result.get("assessments", [])


def assess_content_quality(
    client: anthropic.Anthropic,
    url: str,
    body_text: str,
    page_type: str,
    target_keywords: list,
    site_context: str = "",
    language: str = "Swedish",
    page_data: dict = None,
) -> dict:
    """Assess existing page text quality for both users and Google."""
    text_word_count = len(body_text.split()) if body_text else 0
    pd = page_data or {}
    title = pd.get("title") or ""
    meta_desc = pd.get("meta_description") or ""
    h1 = pd.get("h1") or ""
    h2s = pd.get("h2s", [])[:10]
    full_word_count = pd.get("word_count", text_word_count)
    impressions = pd.get("impressions", 0)
    internal_links = pd.get("internal_links", 0)
    link_count = internal_links if isinstance(internal_links, int) else len(internal_links)

    prompt = f"""You are a senior SEO content strategist and UX copywriter. Evaluate this page's EXISTING text quality — not just keyword presence, but whether the text is actually good.
{ANTI_HALLUCINATION_RULES}

## PAGE
URL: {url}
Page type: {page_type}
Title: "{title}" ({len(title)} chars)
Meta description: "{meta_desc}" ({len(meta_desc)} chars)
H1: "{h1}"
H2s: {', '.join(h2s) if h2s else 'None'}
Total word count: {full_word_count}
Internal links: {link_count}
Impressions: {impressions:,}
Site context: {site_context}
Target keywords: {', '.join(target_keywords[:10])}

## EXISTING TEXT ({text_word_count} words — excerpt)
{body_text[:3000]}

## EVALUATE THESE DIMENSIONS (score each 1-10):

1. **User value**: Does the text actually HELP the customer? Does it answer their questions, guide their decision, or provide useful information? Or is it generic filler?
2. **Readability**: Is it well-written, clear, and easy to scan? Or is it a wall of text, awkward phrasing, or robot-generated?
3. **Conversion support**: Does it build trust, address objections, and guide toward action? Or does it just exist without purpose?
4. **Google quality (E-E-A-T)**: Does it demonstrate expertise, experience, authority? Does it have depth, specificity, and unique insights? Or is it thin/generic content that any site could have?
5. **SEO integration**: Are keywords used naturally, or do they feel forced? Is keyword density reasonable?
6. **Structure**: Are headings logical? Is the content well-organized with clear sections?

## OUTPUT FORMAT (JSON only, no markdown):
{{
  "verdict": "KEEP|IMPROVE|REWRITE",
  "verdict_reason": "One clear sentence explaining the verdict",
  "overall_score": 0,
  "scores": {{
    "user_value": {{"score": 0, "comment": "..."}},
    "readability": {{"score": 0, "comment": "..."}},
    "conversion": {{"score": 0, "comment": "..."}},
    "google_quality": {{"score": 0, "comment": "..."}},
    "seo_integration": {{"score": 0, "comment": "..."}},
    "structure": {{"score": 0, "comment": "..."}}
  }},
  "biggest_problems": ["Problem 1", "Problem 2", "Problem 3"],
  "specific_fixes": [
    "Exact fix 1: what to change and where",
    "Exact fix 2: what to change and where"
  ],
  "rewrite_sections": ["Section/paragraph that should be rewritten and why"]
}}

IMPORTANT:
- VERDICT = KEEP means text is good (score >= 7), no major changes needed
- VERDICT = IMPROVE means text has value but needs specific fixes (score 4-6)
- VERDICT = REWRITE means text is poor quality and should be replaced (score <= 3)
- Be honest and specific — generic feedback is useless
- Language of analysis: English. Language of the content being analyzed: {language}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


def generate_landing_page_text(
    client: anthropic.Anthropic,
    page_data: dict,
    target_keywords: list,
    gsc_queries: list,
    site_context: str = "",
    language: str = "Swedish",
    tone: str = "Professional but approachable",
) -> dict:
    """
    Generate a full optimized landing page text
    """
    url = page_data.get("url", "")
    h2s = page_data.get("h2s", [])
    existing = _clean_body_text(page_data, 2000)
    page_type = page_data.get("page_type", "unknown")

    # Page-type specific instructions
    type_instruction = ""
    if page_type == "category":
        intro_words = page_data.get("intro_word_count", 0)
        bottom_words = page_data.get("bottom_word_count", 0)
        product_count = page_data.get("product_count", 0)
        type_instruction = f"""
## PAGE TYPE: CATEGORY
This page shows {product_count} products in a grid.
Current intro text: {intro_words} words (ABOVE grid)
Current bottom text: {bottom_words} words (BELOW grid)

IMPORTANT for category pages:
- Intro (above grid): 80-150 words, explain the category, help the customer understand the selection
- Bottom text (below grid): 200-400 words with buying guide, FAQ, and deeper keyword coverage
- Text should NOT describe individual products (product pages do that)
- Focus on: What are the differences between types? What should one look for? Who is the target audience?
"""
    elif page_type == "product":
        type_instruction = """
## PAGE TYPE: PRODUCT
Focus on product-specific features, benefits and use cases.
"""
    elif page_type == "blog":
        type_instruction = """
## PAGE TYPE: BLOG/GUIDE
Focus on informational value, E-E-A-T signals and depth.
"""

    title = page_data.get("title") or ""
    meta_desc = page_data.get("meta_description") or ""
    h1 = page_data.get("h1") or ""
    impressions = page_data.get("impressions", 0)
    word_count = page_data.get("word_count", 0)
    link_count = page_data.get("internal_link_count", 0)

    existing_word_count = len(existing.split()) if existing else 0
    prompt = f"""You are a senior SEO copywriter specialized in e-commerce.
{ANTI_HALLUCINATION_RULES}

## CONTEXT
URL: {url}
Title: "{title}" ({len(title)} chars)
Meta description: "{meta_desc}" ({len(meta_desc)} chars)
H1: "{h1}"
Total word count: {word_count}
Internal links: {link_count}
Impressions: {impressions:,}
Site: {site_context}
Primary keywords: {', '.join(target_keywords[:5])}
All GSC search queries we rank for: {', '.join(gsc_queries[:25])}
Current H2 structure: {', '.join(h2s) if h2s else 'None'}
Existing content ({existing_word_count} words — excerpt): {existing[:1000]}
Tone of voice: {tone}
Language: {language}
{type_instruction}
## TASK
Write optimized landing page content that:
1. Is natural and converting - NOT SEO spam
2. Includes primary keywords naturally (density ~1-2%)
3. Covers all relevant LSI keywords from GSC data
4. Has clear structure with H2/H3
5. Includes social proof, USPs and CTA
6. Uses a discreet, respectful tone appropriate for the product category

Return ONLY JSON:
{{
  "intro_paragraph": "Category intro text (80-120 words)",
  "sections": [
    {{
      "h2": "Section heading",
      "content": "Section content (60-100 words)",
      "h3_subsections": [
        {{"h3": "Optional subheading", "content": "..."}}
      ]
    }}
  ],
  "buying_guide_snippet": "Short guide section helping the customer choose (80-100 words)",
  "faq_items": [
    {{"question": "...", "answer": "..."}}
  ],
  "seo_notes": "Notes for the editor about keyword placement (2-3 bullet points)"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return _parse_ai_json(message)


def generate_link_text(
    client: anthropic.Anthropic,
    source_url: str,
    target_url: str,
    anchor_text: str,
    placement_context: str,
    keywords: list,
    site_context: str = "",
    language: str = "Swedish",
) -> dict:
    """Generate a natural paragraph containing an internal link with proper anchor text."""
    prompt = f"""You are a senior SEO copywriter. Write a short, natural paragraph (2-3 sentences) that can be inserted into an existing page to create an internal link.

## CONTEXT
Source page: {source_url}
Target page to link to: {target_url}
Anchor text to use: {anchor_text}
Where to place it: {placement_context}
Related keywords: {', '.join(keywords[:10])}
Site context: {site_context}
Language: {language}

## REQUIREMENTS
- The paragraph must read naturally and fit the page context
- Include the link with the exact anchor text provided
- Do NOT be spammy or over-optimized
- Write in {language}

## OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "paragraph": "The plain text paragraph with the anchor text naturally embedded",
  "html": "<p>The paragraph with <a href='{target_url}'>anchor text</a> as HTML</p>"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


def generate_keyword_text(
    client: anthropic.Anthropic,
    missing_keywords: list,
    existing_text: str,
    page_type: str,
    site_context: str = "",
    language: str = "Swedish",
) -> dict:
    """Generate optimized text paragraphs that naturally integrate missing keywords."""
    # Page-type specific guidance
    type_guide = ""
    if page_type == "category":
        type_guide = "\nThis is a CATEGORY page (product listing). Text should help customers browse and choose, NOT describe individual products."
    elif page_type == "product":
        type_guide = "\nThis is a PRODUCT page. Text should focus on features, benefits, and use cases for this specific product."
    elif page_type == "blog":
        type_guide = "\nThis is a BLOG/GUIDE page. Text should be informational, in-depth, and demonstrate expertise."

    prompt = f"""You are a senior SEO copywriter. Rewrite or extend the following text to naturally integrate missing keywords.

## CONTEXT
Page type: {page_type}{type_guide}
Site context: {site_context}
Language: {language}

Missing keywords to integrate: {', '.join(missing_keywords[:15])}

Current text (excerpt):
{existing_text[:2000]}

## REQUIREMENTS
- Keep the tone and style consistent with the existing text
- Integrate as many missing keywords as possible, naturally
- Do NOT keyword-stuff or make the text sound forced
- Add 1-3 new paragraphs if needed to cover the keywords
- Write in {language}

## OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "optimized_text": "The full optimized text with keywords integrated",
  "keywords_integrated": ["list", "of", "keywords", "that", "were", "integrated"],
  "word_count": 0
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


def generate_intro_rewrite(
    client: anthropic.Anthropic,
    missing_keywords: list,
    existing_intro: str,
    page_type: str,
    url: str = "",
    site_context: str = "",
    language: str = "Swedish",
) -> dict:
    """Rewrite ONLY the intro/first paragraph to include missing keywords."""
    type_guide = ""
    if page_type == "category":
        type_guide = "This is a CATEGORY page. The intro sits ABOVE the product grid and should explain the category in 80-150 words."
    elif page_type == "product":
        type_guide = "This is a PRODUCT page. The intro should hook the buyer with the product's key benefit."
    elif page_type == "blog":
        type_guide = "This is a BLOG/GUIDE page. The intro should state the problem and promise a solution."

    prompt = f"""You are a senior SEO copywriter. Rewrite ONLY the intro paragraph of this page.

## CONTEXT
URL: {url}
Page type: {page_type}
{type_guide}
Site context: {site_context}
Language: {language}

Keywords that MUST appear in the intro: {', '.join(missing_keywords[:8])}

Current intro text:
{existing_intro[:1000]}

## REQUIREMENTS
- Rewrite ONLY the intro paragraph (80-150 words)
- The PRIMARY keyword must appear in the first sentence
- Include as many missing keywords as naturally possible
- Make it engaging — this is the first thing the customer reads
- Do NOT be spammy. The text must sound natural and helpful.
- Write in {language}

## OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "optimized_text": "The rewritten intro paragraph",
  "keywords_integrated": ["list", "of", "keywords", "integrated"],
  "word_count": 0
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


def generate_keyword_faq(
    client: anthropic.Anthropic,
    missing_subtopics: list,
    keywords: list,
    site_context: str = "",
    language: str = "Swedish",
) -> dict:
    """Generate FAQ Q&A pairs targeting uncovered subtopics."""
    n_items = min(max(len(missing_subtopics), 3), 8)

    prompt = f"""You are a senior SEO content specialist. Generate FAQ items targeting subtopics that are missing or poorly covered on the page.

## CONTEXT
Site context: {site_context}
Language: {language}

Uncovered subtopics: {', '.join(missing_subtopics[:10])}
Related keywords to include: {', '.join(keywords[:15])}

## REQUIREMENTS
- Generate {n_items} FAQ Q&A pairs
- Each question should target one or more uncovered subtopics
- Each answer should naturally include relevant keywords
- Answers should be 2-4 sentences, informative and helpful
- Write in {language}

## OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "faq_items": [
    {{"question": "...", "answer": "..."}}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


def generate_article_outline(
    client: anthropic.Anthropic,
    title: str,
    keywords: list,
    content_type: str,
    supporting_page: str,
    site_context: str = "",
    language: str = "Swedish",
) -> dict:
    """Generate a detailed article outline with H2/H3 structure and word targets."""
    prompt = f"""You are a senior SEO content strategist. Create a detailed article outline.

## ARTICLE DETAILS
Title: {title}
Content type: {content_type}
Target keywords: {', '.join(keywords[:10])}
This article supports hub page: {supporting_page}
Site context: {site_context}
Language: {language}

## REQUIREMENTS
- Create a structured outline with H2 sections and H3 subsections
- Include word count targets per section
- Note which keywords to include in each section
- The outline should support the hub page through internal linking
- Content type "{content_type}" should guide the structure (e.g. how-to = step-by-step, comparison = feature table, etc.)

## OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "outline": {{
    "h1": "{title}",
    "sections": [
      {{
        "h2": "Section heading",
        "h3s": ["Subsection 1", "Subsection 2"],
        "word_target": 200,
        "keywords_to_include": ["keyword1", "keyword2"]
      }}
    ]
  }},
  "total_word_target": 1500
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


def generate_article_full(
    client: anthropic.Anthropic,
    title: str,
    keywords: list,
    outline: dict | None,
    content_type: str,
    site_context: str = "",
    language: str = "Swedish",
) -> dict:
    """Generate a complete article in markdown."""
    outline_text = ""
    if outline:
        outline_text = f"\n\nFollow this outline:\n{json.dumps(outline, ensure_ascii=False, indent=2)}"

    prompt = f"""You are a senior SEO copywriter. Write a complete, high-quality article.

## ARTICLE DETAILS
Title: {title}
Content type: {content_type}
Target keywords: {', '.join(keywords[:10])}
Site context: {site_context}
Language: {language}
{outline_text}

## REQUIREMENTS
- Write in markdown format with proper H1, H2, H3 headings
- Include an engaging intro, well-structured sections, and a conclusion
- Naturally integrate target keywords (1-2% density)
- Include a FAQ section at the end with 3-5 relevant questions
- Write in {language}
- Aim for 1000-2000 words depending on content type
- Make it genuinely useful and well-written, not SEO spam

## OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "markdown": "# Title\\n\\n## Section...\\n\\nFull article in markdown",
  "word_count": 0,
  "meta_title": "Optimized meta title (50-60 chars)",
  "meta_description": "Optimized meta description (140-160 chars)"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


def generate_article_meta(
    client: anthropic.Anthropic,
    title: str,
    keywords: list,
    site_context: str = "",
    language: str = "Swedish",
) -> dict:
    """Generate optimized meta title and description for a new article."""
    prompt = f"""You are a senior SEO specialist. Generate an optimized meta title and description for a new article.

## ARTICLE
Title: {title}
Target keywords: {', '.join(keywords[:10])}
Site context: {site_context}
Language: {language}

## REQUIREMENTS
Title: 50-60 chars, primary keyword early, compelling
Description: 140-160 chars, includes primary keyword, has CTA
Write in {language}

## OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "meta_title": "...",
  "meta_description": "..."
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


def ai_generate_clusters(
    client: anthropic.Anthropic,
    keywords_data: list,
    site_context: str = "",
    language: str = "Swedish",
) -> dict:
    """
    AI generates topic clusters from keyword data.
    Replaces word-overlap algorithm with semantic understanding.
    Returns format compatible with the rest of the system.
    """
    prompt = f"""You are a senior SEO architect. Group these search keywords into topic clusters for an e-commerce site.

## SITE CONTEXT
{site_context}
Language: {language}

## KEYWORDS (sorted by impressions — keyword: impressions, clicks, position, pages)
{chr(10).join(f"- {kw['keyword']}: {kw['impressions']} impr, {kw['clicks']} clicks, pos {kw['position']}, pages: {', '.join(str(p) for p in kw.get('pages', [])[:2])}" for kw in keywords_data[:150])}

## YOUR TASK
Group ALL these keywords into 30-60 topic clusters.

Rules:
1. Each cluster = one topic with clear commercial or informational intent
2. Brand keywords → assign to relevant product cluster
3. No overlapping clusters — each keyword in exactly ONE cluster
4. At least 3 keywords per cluster
5. Cluster name = main product category (e.g. "vibratorer", "dildos")

## OUTPUT (JSON — be CONCISE, no extra whitespace):
{{"clusters":[{{"topic":"name","intent":"commercial","terms":["term1","term2"],"keywords":["kw1","kw2","kw3"],"hub":"suggested hub URL","impressions":0}}],"summary":"2 sentences"}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    ai_result = _parse_ai_json(message)

    # Convert AI format to system format (compatible with rest of pipeline)
    # Also enrich with actual GSC data
    system_clusters = []
    page_topics = {}

    # Build keyword→pages mapping from input data
    kw_pages = {}
    for kw in keywords_data:
        kw_pages[kw["keyword"]] = kw.get("pages", [])

    for c in ai_result.get("clusters", []):
        cluster_keywords = c.get("keywords", c.get("queries", []))
        cluster_terms = c.get("terms", c.get("core_terms", []))

        # Find pages from keyword data
        cluster_page_urls = set()
        for kw in cluster_keywords:
            for page_url in kw_pages.get(kw, []):
                cluster_page_urls.add(page_url)

        pages_list = []
        for page_url in cluster_page_urls:
            pages_list.append({
                "page": page_url,
                "query_count": sum(1 for kw in cluster_keywords if page_url in kw_pages.get(kw, [])),
                "total_clicks": 0,
                "total_impressions": 0,
                "avg_position": 0,
            })

            if page_url not in page_topics:
                page_topics[page_url] = []
            page_topics[page_url].append({
                "topic": c.get("topic", ""),
                "queries_in_topic": sum(1 for kw in cluster_keywords if page_url in kw_pages.get(kw, [])),
                "clicks": 0,
            })

        system_clusters.append({
            "topic": c.get("topic", ""),
            "core_terms": cluster_terms,
            "query_count": len(cluster_keywords),
            "queries": cluster_keywords,
            "total_clicks": c.get("clicks", c.get("total_clicks", 0)),
            "total_impressions": c.get("impressions", c.get("total_impressions", 0)),
            "pages": pages_list,
            "page_count": len(pages_list),
            "is_split": len(pages_list) > 3,
            "search_intent": c.get("intent", c.get("search_intent", "mixed")),
            "suggested_hub_url": c.get("hub", c.get("suggested_hub_url", "")),
        })

    # Build overlap matrix
    overlap_matrix = []
    for url, topics in page_topics.items():
        topic_names = set(t["topic"] for t in topics)
        for other_url, other_topics in page_topics.items():
            if other_url <= url:
                continue
            other_names = set(t["topic"] for t in other_topics)
            shared = topic_names & other_names
            if shared:
                overlap_matrix.append({
                    "page_1": url,
                    "page_2": other_url,
                    "shared_topics": len(shared),
                    "topic_names": list(shared),
                })

    return {
        "clusters": system_clusters,
        "page_topics": page_topics,
        "overlap_matrix": overlap_matrix,
        "ai_summary": ai_result.get("summary", ""),
        "unassigned_keywords": ai_result.get("unassigned_keywords", []),
    }


def evaluate_cluster_health(
    client: anthropic.Anthropic,
    cluster_data: dict,
    site_context: str = "",
    language: str = "Swedish",
    all_site_urls: list = None,
) -> dict:
    """
    AI evaluates an entire topic cluster: structure, linking, keyword distribution,
    content coverage, and hub-spoke relationships.
    """
    # Include actual site URLs so AI can reference real pages
    url_list = ""
    if all_site_urls:
        url_list = f"\n\n## ALL PAGES ON THIS SITE (use these exact URLs in your recommendations)\n{chr(10).join(all_site_urls[:200])}"

    prompt = f"""You are a senior SEO architect specializing in topic cluster strategy (Google 2026 best practices).

Evaluate this ENTIRE topic cluster and identify problems + fixes. You must check EVERY aspect of cluster health.

IMPORTANT: When recommending links or page references, use the EXACT URLs from the site URL list below. Do NOT invent URLs.

## SITE CONTEXT
{site_context}
Language: {language}{url_list}

## CLUSTER OVERVIEW
Topic: {cluster_data.get('topic', '')}
Core terms: {', '.join(cluster_data.get('core_terms', []))}
Total queries: {cluster_data.get('query_count', 0)}
Total impressions: {cluster_data.get('total_impressions', 0):,}
Total clicks: {cluster_data.get('total_clicks', 0):,}

## HUB/PILLAR PAGE
URL: {cluster_data.get('hub_url', 'Not identified')}
Title: {cluster_data.get('hub_title', '')}
H1: {cluster_data.get('hub_h1', '')}
Word count: {cluster_data.get('hub_word_count', 0)}
Internal links out: {cluster_data.get('hub_outlinks', 0)}
Content snippet: {cluster_data.get('hub_content', '')[:500]}

## SPOKE/CLUSTER PAGES ({len(cluster_data.get('spokes', []))} pages)
{json.dumps(cluster_data.get('spokes', []), ensure_ascii=False, indent=1)}

## INTERNAL LINK MAP WITHIN CLUSTER
Hub links TO these spokes: {json.dumps(cluster_data.get('hub_to_spoke_links', []), ensure_ascii=False)}
Spokes linking BACK to hub: {json.dumps(cluster_data.get('spoke_to_hub_links', []), ensure_ascii=False)}
Horizontal links between spokes: {json.dumps(cluster_data.get('horizontal_links', []), ensure_ascii=False)}

## KEYWORD DISTRIBUTION
Hub page keywords: {', '.join(cluster_data.get('hub_keywords', [])[:10])}
Per-spoke keywords:
{json.dumps(cluster_data.get('spoke_keywords', {{}}), ensure_ascii=False, indent=1)}

## CANNIBALIZATION WITHIN CLUSTER
Keywords appearing on multiple pages in this cluster:
{json.dumps(cluster_data.get('cannibalized_keywords', []), ensure_ascii=False, indent=1)}

## YOUR EVALUATION
Check ALL of these and report issues + fixes:

1. **Hub/Pillar Quality**: Is the hub page comprehensive enough (3000-5000 words)? Does it cover ALL subtopics at summary level? Does the H1/title target the right head keyword?

2. **Vertical Linking (Hub ↔ Spoke)**:
   - Does the hub link DOWN to every spoke page? Which spokes are missing a link FROM the hub?
   - Does every spoke link UP/BACK to the hub? Which spokes are missing a link TO the hub?

3. **Horizontal Linking (Spoke ↔ Spoke)**: Are related spokes cross-linked? Which pairs should link to each other but don't?

4. **Keyword Distribution**:
   - Is each keyword assigned to the RIGHT page?
   - Are there keywords on spoke pages that should be on the hub (or vice versa)?
   - Any cannibalization where the same keyword is targeted by multiple pages?

5. **Content Gaps**: What subtopics are NOT covered by any page in the cluster? What new pages should be created?

6. **Content Quality**: Are spoke pages deep enough (1500-3000 words)? Do they have proper H2/H3 structure?

7. **Overall Cluster Health Score**: Rate the cluster 1-100 based on completeness, linking, keyword distribution, and content quality.

## OUTPUT (JSON only):
{{
  "health_score": 0,
  "health_summary": "2-3 sentences about the cluster's overall health",
  "hub_assessment": {{
    "is_adequate": true/false,
    "issues": ["issue 1", "issue 2"],
    "fixes": ["fix 1", "fix 2"]
  }},
  "vertical_linking": {{
    "hub_to_spoke_missing": ["spoke URL that hub should link to but doesn't"],
    "spoke_to_hub_missing": ["spoke URL that doesn't link back to hub"],
    "fixes": ["fix 1"]
  }},
  "horizontal_linking": {{
    "missing_connections": [{{"from": "url", "to": "url", "why": "reason"}}],
    "fixes": ["fix 1"]
  }},
  "keyword_issues": {{
    "misplaced_keywords": [{{"keyword": "kw", "current_page": "url", "should_be_on": "url", "reason": "why"}}],
    "cannibalization": [{{"keyword": "kw", "pages": ["url1", "url2"], "fix": "what to do"}}],
    "fixes": ["fix 1"]
  }},
  "content_gaps": {{
    "missing_subtopics": ["subtopic that needs a new page"],
    "thin_pages": [{{"url": "url", "word_count": 0, "target": 1500}}],
    "fixes": ["fix 1"]
  }},
  "priority_actions": [
    {{
      "action": "What to do",
      "page": "Which page",
      "impact": "high/medium/low",
      "time_minutes": 0
    }}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


def generate_full_article_html(
    client: anthropic.Anthropic,
    title: str,
    keywords: list,
    content_type: str,
    products: list = None,
    link_from_url: str = "",
    tone_sample: str = "",
    site_context: str = "",
    language: str = "Swedish",
    all_site_urls: list = None,
    cluster_context: str = "",
) -> dict:
    """Generate a complete article as CMS-ready HTML."""
    from utils.templates import BLOG_TEMPLATE_INSTRUCTIONS

    products_section = ""
    if products:
        product_lines = []
        for p in products[:8]:
            product_lines.append(
                f"  - Name: {p.get('name','')}\n"
                f"    Price: {p.get('price','')}\n"
                f"    Image: {p.get('image_url','')}\n"
                f"    URL: {p.get('product_url','')}\n"
                f"    Description: {p.get('description','')}"
            )
        products_section = f"""

## REAL PRODUCTS TO FEATURE (use these exact names, images, URLs, prices)
{chr(10).join(product_lines)}

Feature 3-5 of these products naturally in the article using the product card HTML format from the template instructions."""

    url_section = ""
    if all_site_urls:
        url_section = f"\n\n## ALL SITE URLs (use these for internal links — do NOT invent URLs)\n{chr(10).join(all_site_urls[:150])}"

    prompt = f"""You are a senior content writer for an e-commerce site.
Write a complete, CMS-ready article following the EXACT HTML format specified below.

## ARTICLE DETAILS
Title: {title}
Content type: {content_type}
Target keywords: {', '.join(keywords[:10])}
This article supports/links from: {link_from_url}
{f"Cluster context: {cluster_context}" if cluster_context else ""}
Site: {site_context}
Language: {language}

{BLOG_TEMPLATE_INSTRUCTIONS}
{products_section}{url_section}

## CONTENT REQUIREMENTS
- 1500-2500 words total
- Intro paragraph (100-150 words) — NO H1 tag
- 3-5 H2 main sections with H3 subsections for product categories
- Each H3 subsection: product description + expert recommendation (xmx--high-emphasis)
- Product carousel cards after recommendation sections using real product data
- FAQ at the end (3-5 questions as regular H3 + p, not accordion)
- Conclusion with CTA mentioning discreet shipping and customer service
- Internal links to related categories using real URLs
- Naturally integrate target keywords (1-2% density)

## OUTPUT FORMAT (JSON only):
{{
  "html": "<p>Intro paragraph...</p>\\n<h2>Section...</h2>\\n<p>Content...</p>",
  "word_count": 0,
  "meta_title": "SEO title (50-60 chars)",
  "meta_description": "Meta description (140-160 chars)",
  "keywords_used": ["list of keywords naturally included"],
  "products_featured": ["product names included in article"]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


def generate_category_bottom_text(
    client: anthropic.Anthropic,
    url: str,
    page_title: str,
    h1: str,
    current_bottom_text: str,
    target_keywords: list,
    subcategory_urls: list = None,
    sibling_urls: list = None,
    products: list = None,
    all_site_urls: list = None,
    site_context: str = "",
    language: str = "Swedish",
    current_intro_text: str = "",
    impressions: int = 0,
) -> dict:
    """Generate optimized category bottom text with all keywords, links, and products."""
    from utils.templates import CATEGORY_BOTTOM_TEXT_INSTRUCTIONS

    products_section = ""
    if products:
        product_lines = []
        for p in products[:6]:
            product_lines.append(
                f"  - Name: {p.get('name','')}, Price: {p.get('price','')}, "
                f"Image: {p.get('image_url','')}, URL: {p.get('product_url','')}, "
                f"Desc: {p.get('description','')}"
            )
        products_section = f"\n\n## TOP PRODUCTS TO FEATURE\n{chr(10).join(product_lines)}"

    subcats = ""
    if subcategory_urls:
        subcats = "\n\n## SUBCATEGORY PAGES (MUST link to ALL of these)\n" + "\n".join(subcategory_urls[:20])

    siblings = ""
    if sibling_urls:
        siblings = "\n\n## SIBLING/RELATED CATEGORIES (cross-link to these)\n" + "\n".join(sibling_urls[:15])

    url_list = ""
    if all_site_urls:
        url_list = f"\n\n## ALL SITE URLs\n{chr(10).join(all_site_urls[:150])}"

    bottom_word_count = len(current_bottom_text.split()) if current_bottom_text else 0
    intro_word_count = len(current_intro_text.split()) if current_intro_text else 0
    prompt = f"""You are a senior SEO copywriter.
Rewrite the category page bottom text following the EXACT format below.
{ANTI_HALLUCINATION_RULES}

## PAGE
URL: {url}
Title: "{page_title}"
H1: "{h1}"
Impressions: {impressions:,}
Language: {language}
Site: {site_context}

## ALL KEYWORDS THAT MUST APPEAR IN THE TEXT
{', '.join(target_keywords[:25])}

## CURRENT INTRO TEXT ({intro_word_count} words — above product grid, do NOT repeat this content)
{current_intro_text[:800] if current_intro_text else '(no intro text)'}

## CURRENT BOTTOM TEXT ({bottom_word_count} words — rewrite this if quality is poor)
{current_bottom_text[:2000]}

{CATEGORY_BOTTOM_TEXT_INSTRUCTIONS}
{subcats}{siblings}{products_section}{url_list}

## OUTPUT (JSON only):
{{
  "html": "<h2>Guide section...</h2>\\n<p>Content...</p>\\n<h2>FAQ...</h2>",
  "word_count": 0,
  "keywords_integrated": ["list of keywords naturally included"],
  "internal_links_added": ["URLs linked to in the text"],
  "products_featured": ["product names included"]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


def _format_cluster_context(page_data: dict, topic_clusters: dict = None) -> str:
    """Build cluster context showing this page's role in the topic structure."""
    if not topic_clusters:
        return "(no cluster data available)"

    url = page_data.get("url", "")
    page_topics = topic_clusters.get("page_topics", {})
    topics = page_topics.get(url, [])

    if not topics:
        return "(this page is not in any topic cluster)"

    from urllib.parse import urlparse
    parsed = urlparse(url)
    page_path = parsed.path.lower().rstrip("/")
    site_origin = f"{parsed.scheme}://{parsed.netloc}"

    lines = []

    # This page's topics
    topic_names = [t.get("topic", "") for t in topics[:5]]
    lines.append(f"Topics this page covers: {', '.join(topic_names)}")

    # Is this a pillar?
    child_pages = []
    for other_url in page_topics.keys():
        other_path = urlparse(other_url).path.lower().rstrip("/")
        if other_path != page_path and other_path.startswith(page_path + "/"):
            child_pages.append(other_url)

    if child_pages:
        lines.append(f"PILLAR PAGE — has {len(child_pages)} child/spoke pages:")
        for cp in child_pages[:10]:
            cp_short = cp.replace(site_origin, "")
            cp_topics = [t.get("topic", "") for t in page_topics.get(cp, [])[:2]]
            lines.append(f"  Child: {cp_short} (topics: {', '.join(cp_topics)})")
        lines.append("As a pillar, this page should: overview ALL child topics, link DOWN to each child, provide comprehensive category guidance")
    else:
        # Find parent/hub page
        path_parts = page_path.strip("/").split("/")
        if len(path_parts) >= 2:
            parent_path = "/" + "/".join(path_parts[:-1])
            parent_url = f"{site_origin}{parent_path}"
            lines.append(f"SPOKE PAGE — parent/hub: {parent_url}")
            lines.append("As a spoke, this page should: go DEEP on its specific subtopic, link UP to parent hub, cross-link to sibling pages")

        # Find siblings
        sibling_pages = []
        for other_url in page_topics.keys():
            other_path = urlparse(other_url).path.lower().rstrip("/")
            if other_url != url and len(other_path.strip("/").split("/")) == len(path_parts):
                other_parts = other_path.strip("/").split("/")
                if len(other_parts) >= 2 and other_parts[:-1] == path_parts[:-1]:
                    sibling_pages.append(other_url)
        if sibling_pages:
            lines.append(f"Sibling pages ({len(sibling_pages)}): {', '.join(s.replace(site_origin, '') for s in sibling_pages[:8])}")

    return "\n".join(lines)


def _format_existing_links(page_data: dict) -> str:
    """Format existing internal links for the AI prompt."""
    links = page_data.get("internal_links", [])
    if isinstance(links, int):
        return f"(count only: {links} links, no detail available)"
    if not links:
        return "(no links found)"

    # Derive site origin from page URL for shortening
    from urllib.parse import urlparse
    page_url = page_data.get("url", "")
    parsed = urlparse(page_url)
    site_origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else ""

    # Show unique links with anchors
    seen = set()
    lines = []
    for l in links:
        url = l.get("url", "")
        anchor = l.get("anchor", "")
        if url and url not in seen:
            seen.add(url)
            short = url.replace(site_origin, "") if site_origin else url
            lines.append(f"  [{anchor[:40]}] → {short}")
    if len(lines) > 30:
        return "\n".join(lines[:30]) + f"\n  ... and {len(lines) - 30} more links"
    return "\n".join(lines) if lines else "(no links found)"


def generate_page_implementation_plan(
    client: anthropic.Anthropic,
    page_data: dict,
    site_context: str = "",
    all_site_urls: list = None,
    language: str = "Swedish",
    topic_clusters: dict = None,
) -> dict:
    """
    Generate a complete, verified implementation plan for a single page.
    AI evaluates ALL data (meta, content, keywords, links, structure) and
    returns only actions that make sense for this specific page.
    """
    url = page_data.get("url", "")
    title = page_data.get("title") or ""
    meta_desc = page_data.get("meta_description") or ""
    h1 = page_data.get("h1") or ""
    h2s = page_data.get("h2s", [])[:10]
    page_type = page_data.get("page_type", "unknown")
    word_count = page_data.get("word_count", 0)
    body_snippet = _clean_body_text(page_data, 1500)
    target_keywords = page_data.get("target_keywords", [])[:15]
    impressions = page_data.get("impressions", 0)
    lost_clicks = page_data.get("lost_clicks_estimate", 0)

    # Content audit data
    content_audit = page_data.get("content_audit") or {}
    kw_coverage = content_audit.get("keyword_coverage") or {}
    missing_kws = kw_coverage.get("missing", [])[:30]
    topic_coverage = content_audit.get("topic_coverage") or {}
    missing_subtopics = [
        s.get("topic", "") for s in (topic_coverage.get("subtopics") or [])
        if s.get("status") in ("missing", "partial")
    ][:10]
    linking = content_audit.get("linking") or {}
    link_suggestions = linking.get("link_fix_suggestions") or []
    missing_crosslinks = linking.get("missing_crosslinks") or []
    schema_types = page_data.get("schema_types", [])
    trust = content_audit.get("trust") or {}
    meta_score = page_data.get("meta_score")
    content_score = page_data.get("content_score")

    # Backlink data
    referring_domains = page_data.get("referring_domains", 0)
    backlinks = page_data.get("backlinks", 0)
    authority_score = page_data.get("authority_score", 0)

    # Internal links this page has
    internal_links = page_data.get("internal_links", 0)
    link_count = internal_links if isinstance(internal_links, int) else len(internal_links)

    # Category-specific data
    intro_words = page_data.get("intro_word_count", 0)
    bottom_words = page_data.get("bottom_word_count", 0)
    product_count = page_data.get("product_count", 0)
    has_faq = page_data.get("has_faq", False)
    has_buying_guide = page_data.get("has_buying_guide", False)

    # Content quality verdict (if previously assessed)
    from utils.ui_helpers import stable_hash as _sh
    quality_key = f"_quality_{_sh(url)}"
    quality = st.session_state.get(quality_key)
    quality_info = ""
    if quality:
        quality_info = f"\nAI content quality verdict: {quality.get('verdict', '?')} ({quality.get('score', '?')}/10) — {quality.get('summary', '')}"

    # Include site URLs so AI uses real URLs in link recommendations
    url_list_section = ""
    if all_site_urls:
        url_list_section = f"\n\n## ALL PAGES ON THIS SITE (use these exact URLs when recommending internal links)\n{chr(10).join(all_site_urls[:200])}"

    prompt = f"""You are a senior SEO strategist reviewing a single page. Based on ALL the data below, create a precise implementation plan with ONLY actions that are correct and relevant for THIS specific page.
{ANTI_HALLUCINATION_RULES}

IMPORTANT: When recommending internal links, use the EXACT URLs from the site URL list below. Do NOT invent or guess URLs.{url_list_section}

## PAGE DATA
URL: {url}
Page type: {page_type}
Title: "{title}" ({len(title)} chars)
Meta description: "{meta_desc}" ({len(meta_desc)} chars)
H1: "{h1}"
H2s: {', '.join(h2s) if h2s else 'None'}
Word count: {word_count}
Internal links on page: {link_count}
Schema types present: {', '.join(schema_types) if schema_types else 'None'}
{f"Intro text: {intro_words} words (above product grid)" if page_type == "category" else ""}
{f"Bottom text: {bottom_words} words (below product grid)" if page_type == "category" else ""}
{f"Products on page: {product_count}" if product_count else ""}
{f"Has FAQ section: {'Yes' if has_faq else 'No'}" if page_type == "category" else ""}
{f"Has buying guide: {'Yes' if has_buying_guide else 'No'}" if page_type == "category" else ""}
{quality_info}

## EXISTING INTERNAL LINKS ON THIS PAGE (already present — do NOT suggest these again)
{_format_existing_links(page_data)}

## SCORES & METRICS
Meta score: {meta_score if meta_score is not None else 'not audited'}/100
Content score: {content_score if content_score is not None else 'not audited'}/100
Impressions: {impressions:,}
Lost clicks estimate: {lost_clicks:.0f}
Referring domains (backlinks): {referring_domains}
Total backlinks: {backlinks}
Authority score: {authority_score}
Site context: {site_context}
Language: {language}

## TOPIC CLUSTER CONTEXT (this page's role in the site's topic structure)
{_format_cluster_context(page_data, topic_clusters)}

## GSC KEYWORDS (sorted by impressions, these are queries users search to find this page)
{', '.join(target_keywords)}

## MISSING KEYWORDS (from audit — keywords in GSC but NOT found on page text)
{', '.join(missing_kws) if missing_kws else 'None'}

## MISSING TOPIC SECTIONS (subtopics not covered in page text)
{', '.join(missing_subtopics) if missing_subtopics else 'None'}

## CURRENT PAGE TEXT (first 1500 chars)
{body_snippet}

## YOUR TASK
Create a step-by-step implementation plan. For each step, be SPECIFIC — tell the user exactly what to change and why.

CRITICAL RULES:
1. KEYWORD RELEVANCE: Only include keywords that a user searching for them would expect to find on THIS specific page. Example: "clitoris vibrator" does NOT belong on a men's sex toy page. "dildo köp" is generic and belongs on the dildo category page, not a subcategory. Be STRICT about this.
2. Do NOT recommend adding a keyword to H1 if H1 already contains it (handle Swedish chars: ä=a, ö=o, å=a)
3. INTERNAL LINKS: Check the EXISTING LINKS list above first. Do NOT recommend adding links that already exist. Only suggest NEW links. PREFER CATEGORY pages over individual product pages — link to /sexleksaker/vibratorer (category) not /satisfyer-pro-2 (product). Use EXACT URLs from the site URL list. Do NOT invent URLs. Verify anchor texts are descriptive.
4. META TITLE: Must be under 60 chars. Primary keyword first. Not a brand name.
5. META DESCRIPTION: Must be 140-160 chars. Include primary keyword + CTA.
6. ALWAYS show meta title + description as the FIRST step if they need improvement.
7. Only suggest schema types appropriate for this page type (no Product schema on category pages)
8. Be honest: if the page is already good, say so. Don't invent problems.
9. Each step must have a time estimate in minutes
10. For content steps: specify EXACTLY what text to add, which H2 heading, and where on the page
11. If keywords indicate topics not covered by ANY existing page, suggest a NEW article/blog
12. For thin/generic text: specify which sections need rewriting and what angle to take
13. VALIDATION: Before including any keyword in your plan, ask yourself: "Would a user searching THIS keyword expect to land on THIS page?" If not, exclude it.
14. BACKLINKS: If the page has high impressions but few or zero referring domains, recommend building backlinks. This is often the single biggest factor for improving rankings.
15. CLUSTER CONTEXT: Check the TOPIC CLUSTER CONTEXT section. All recommendations must fit the page's role:
    - PILLAR pages: recommend content that overviews ALL child topics, links DOWN to each child
    - SPOKE pages: recommend deep content on THIS specific subtopic, link UP to hub, cross-link to siblings
    - New articles must fill gaps in the cluster structure, not duplicate existing pages
    - Anchor texts must be contextually appropriate for the cluster relationship

## OUTPUT FORMAT (JSON only):

IMPORTANT: meta_title and meta_description MUST always be included in the response, even if unchanged.

{{
  "primary_keyword": "the single most important keyword for this page",
  "meta_title": "Optimized meta title under 60 chars (or current if fine)",
  "meta_title_chars": 0,
  "meta_description": "Optimized meta description 140-160 chars (or current if fine)",
  "meta_description_chars": 0,
  "meta_changed": true,
  "steps": [
    {{
      "action": "Short action title",
      "time_minutes": 5,
      "detail": "What is wrong / current state",
      "instruction": "Exactly what to do. For content: specify H2 section + placement. For links: use CATEGORY URLs only.",
      "type": "meta|content|links|schema|structure|new_content"
    }}
  ],
  "new_content_suggestions": [
    {{
      "type": "blog|guide|faq|category",
      "suggested_title": "Title for the new article",
      "target_keywords": ["kw1", "kw2"],
      "why": "Why this content is needed and what search intent it serves",
      "link_from": "URL of existing page that should link to this new content"
    }}
  ],
  "text_rewrites": [
    {{
      "section": "Which section/paragraph needs rewriting",
      "current_problem": "Why the current text is bad",
      "suggested_angle": "What the new text should focus on"
    }}
  ],
  "overall_assessment": "2-3 sentences about this page's SEO status and priority"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


def filter_relevant_keywords(
    client: anthropic.Anthropic,
    url: str,
    page_title: str,
    h1: str,
    all_keywords: list,
    page_type: str = "",
) -> dict:
    """Use AI to filter keywords by relevance to a specific page."""
    prompt = f"""You are an SEO expert. Given a specific page, determine which keywords are RELEVANT to that page and which are NOT.

## PAGE
URL: {url}
Title: {page_title}
H1: {h1}
Page type: {page_type}

## KEYWORDS TO EVALUATE
{', '.join(all_keywords[:40])}

## TASK
For each keyword, decide: should this keyword be on THIS specific page, or does it belong on a DIFFERENT page?

Rules:
- A keyword is RELEVANT if a user searching for it would expect to find it on THIS page
- A keyword is NOT relevant if it clearly belongs on a different page (e.g. "dildo" belongs on a dildo page, not a "for men" page, UNLESS it's specifically "dildo for men")
- Brand keywords (site name) are NOT relevant unless this is the homepage
- Generic keywords that apply to the whole site are NOT relevant to a specific subpage

Return ONLY JSON:
{{
  "relevant": ["keyword1", "keyword2"],
  "not_relevant": ["keyword3", "keyword4"],
  "primary_keyword": "the single most important keyword for this page"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


def generate_schema_markup(
    page_type: str,
    url: str,
    title: str = "",
    description: str = "",
    h1: str = "",
    faq_items: list = None,
    breadcrumb_items: list = None,
    site_name: str = "",
    site_url: str = "",
) -> dict:
    """Generate JSON-LD schema markup based on page type and content."""
    schemas = []

    # BreadcrumbList — always recommended
    if breadcrumb_items:
        bc_items = []
        for i, item in enumerate(breadcrumb_items, 1):
            bc_items.append({
                "@type": "ListItem",
                "position": i,
                "name": item.get("name", ""),
                "item": item.get("url", ""),
            })
        schemas.append({
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": bc_items,
        })
    else:
        # Auto-generate from URL path
        from urllib.parse import urlparse
        parsed = urlparse(url)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if parts:
            bc_items = [{
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": f"{parsed.scheme}://{parsed.netloc}/",
            }]
            for i, part in enumerate(parts, 2):
                name = part.replace("-", " ").replace("_", " ").title()
                path = "/".join(parts[:i-1])
                bc_items.append({
                    "@type": "ListItem",
                    "position": i,
                    "name": name,
                    "item": f"{parsed.scheme}://{parsed.netloc}/{path}/",
                })
            schemas.append({
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": bc_items,
            })

    # FAQPage — if FAQ items exist
    if faq_items:
        faq_entities = []
        for faq in faq_items:
            q = faq.get("question", "")
            a = faq.get("answer", "")
            if q and a:
                faq_entities.append({
                    "@type": "Question",
                    "name": q,
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": a,
                    }
                })
        if faq_entities:
            schemas.append({
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": faq_entities,
            })

    # Organization — for homepage
    if page_type == "homepage" or url.rstrip("/").count("/") <= 3:
        if site_name:
            schemas.append({
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": site_name,
                "url": site_url or url,
            })

    # WebPage — general
    schemas.append({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title or h1,
        "description": description,
        "url": url,
    })

    return {
        "schemas": schemas,
        "json_ld": "\n".join([
            f'<script type="application/ld+json">\n{json.dumps(s, ensure_ascii=False, indent=2)}\n</script>'
            for s in schemas
        ]),
        "types": [s["@type"] for s in schemas],
    }


def generate_action_plan(
    client: anthropic.Anthropic,
    audit_results: list,
    site_url: str,
) -> dict:
    """
    Generate prioritized action plan from all audit results
    """
    # Build summary of issues - convert numpy types to native Python
    def _to_native(val):
        if hasattr(val, 'item'):
            return val.item()
        return val

    summary_data = []
    for r in audit_results[:20]:  # Cap for token limit
        summary_data.append({
            "url": str(r.get("url", "")),
            "page_type": str(r.get("page_type", "unknown")),
            "lost_clicks": _to_native(r.get("lost_clicks_estimate", 0)),
            "position": _to_native(r.get("position", 0)),
            "impressions": _to_native(r.get("impressions", 0)),
            "ctr_gap": _to_native(r.get("ctr_gap_pct", 0)),
            "meta_score": _to_native(r.get("meta_score")) if r.get("meta_score") is not None else "not audited",
            "content_score": _to_native(r.get("content_score")) if r.get("content_score") is not None else "not audited",
            "word_count": _to_native(r.get("word_count", 0)),
            "referring_domains": _to_native(r.get("referring_domains", 0)),
            "authority_score": _to_native(r.get("authority_score", 0)),
            "top_keywords": [str(k) for k in r.get("target_keywords", [])[:3]],
            "issues": [str(i) for i in r.get("issues", [])[:3]],
        })

    # Technical issues summary from Screaming Frog
    crawl_issues = st.session_state.get("sf_crawl_issues", {})
    tech_summary = ""
    if crawl_issues:
        tech_counts = {k: len(v) for k, v in crawl_issues.items() if v}
        if tech_counts:
            tech_summary = f"\n\n## TECHNICAL ISSUES (from Screaming Frog crawl)\n" + "\n".join(
                f"- {k.replace('_', ' ').title()}: {v}" for k, v in tech_counts.items()
            )

    prompt = f"""You are an SEO strategist for {site_url}. Create a prioritized action plan based on these audit results:

{json.dumps(summary_data, ensure_ascii=False, indent=2)}{tech_summary}

Return ONLY JSON:
{{
  "executive_summary": "3-4 sentences about the overall SEO situation and potential",
  "estimated_monthly_clicks_gain": 0,
  "priority_actions": [
    {{
      "priority": 1,
      "url": "...",
      "action": "What needs to be done",
      "reason": "Why this is important",
      "estimated_impact": "Estimated click gain",
      "effort": "Low/Medium/High",
      "type": "meta|content|technical"
    }}
  ],
  "quick_wins": ["Actions that can be done in under 30 min"],
  "strategic_recommendations": ["Larger strategic changes (1-3 months)"]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return _parse_ai_json(message)
