"""
AI content generation: meta titles, descriptions, and landing page text
Uses Claude claude-sonnet-4-20250514 via Anthropic API
"""

import os
import json
import anthropic
import streamlit as st
from typing import Optional


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
    current_title = page_data.get("title") or "No title"
    current_desc = page_data.get("meta_description") or "No description"
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

## CURRENT SITUATION
URL: {url}{cat_context}
Current title: {current_title} ({len(current_title)} chars)
Current meta description: {current_desc} ({len(current_desc)} chars)
H1: {h1}
H2s: {', '.join(h2s) if h2s else 'None'}
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
    body = page_data.get("body_text", "")[:4000]
    url = page_data.get("url", "")
    
    prompt = f"""You are an SEO content analyst. Analyze this landing page and its keyword coverage.

URL: {url}
GSC keywords driving traffic: {', '.join(gsc_queries[:20])}
Target focus keywords: {', '.join(target_keywords)}

CURRENT CONTENT (excerpt):
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


def assess_content_quality(
    client: anthropic.Anthropic,
    url: str,
    body_text: str,
    page_type: str,
    target_keywords: list,
    site_context: str = "",
    language: str = "Swedish",
) -> dict:
    """Assess existing page text quality for both users and Google."""
    prompt = f"""You are a senior SEO content strategist and UX copywriter. Evaluate this page's EXISTING text quality — not just keyword presence, but whether the text is actually good.

## PAGE
URL: {url}
Page type: {page_type}
Site context: {site_context}
Target keywords: {', '.join(target_keywords[:10])}

## EXISTING TEXT
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
    existing = page_data.get("body_text", "")[:2000]
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

    prompt = f"""You are a senior SEO copywriter specialized in e-commerce.

## CONTEXT
URL: {url}
Site: {site_context}
Primary keywords: {', '.join(target_keywords[:5])}
All GSC search queries we rank for: {', '.join(gsc_queries[:25])}
Current H2 structure: {', '.join(h2s) if h2s else 'None'}
Existing content (excerpt): {existing[:1000]}
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
) -> dict:
    """Generate a complete article as HTML matching Mshop's exact format."""
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

    prompt = f"""You are a senior content writer for Mshop.se, Scandinavia's leading adult webshop.
Write a complete, CMS-ready article following the EXACT HTML format specified below.

## ARTICLE DETAILS
Title: {title}
Content type: {content_type}
Target keywords: {', '.join(keywords[:10])}
This article supports/links from: {link_from_url}
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


def generate_page_implementation_plan(
    client: anthropic.Anthropic,
    page_data: dict,
    site_context: str = "",
    all_site_urls: list = None,
    language: str = "Swedish",
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
    body_snippet = (page_data.get("body_text") or page_data.get("intro_text") or "")[:1500]
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

    # Internal links this page has
    internal_links = page_data.get("internal_links", 0)
    link_count = internal_links if isinstance(internal_links, int) else len(internal_links)

    # Include site URLs so AI uses real URLs in link recommendations
    url_list_section = ""
    if all_site_urls:
        url_list_section = f"\n\n## ALL PAGES ON THIS SITE (use these exact URLs when recommending internal links)\n{chr(10).join(all_site_urls[:200])}"

    prompt = f"""You are a senior SEO strategist reviewing a single page. Based on ALL the data below, create a precise implementation plan with ONLY actions that are correct and relevant for THIS specific page.

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
Meta score: {meta_score}/100
Content score: {content_score}/100
Impressions: {impressions:,}
Lost clicks estimate: {lost_clicks:.0f}
Site context: {site_context}
Language: {language}

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
1. Only include RELEVANT missing keywords — keywords that a user searching for them would expect to find on THIS page. Filter out keywords that belong on other pages.
2. Do NOT recommend adding a keyword to H1 if H1 already contains it (handle Swedish chars: ä=a, ö=o, å=a)
3. For internal links: only suggest links to pages that are topically related. Use EXACT URLs from the site URL list. Do NOT invent URLs.
4. Meta title MUST be under 60 chars. Primary keyword should be the most important keyword for THIS page (not a brand name)
5. Only suggest schema types that are appropriate for this page type (no Product schema on category pages)
6. Be honest: if the page is already good, say so. Don't invent problems.
7. Each step must have a time estimate in minutes
8. For content steps: specify EXACTLY what text to add, which H2 heading to use, and where on the page it should go (intro, bottom, new section)
9. If keywords indicate topics not covered by ANY page on the site, suggest a NEW article/blog post to create — include suggested title, target keywords, and which existing page should link to it
10. For existing text that is thin, generic, or low quality: specify which paragraphs/sections need rewriting and what angle to take

## OUTPUT FORMAT (JSON only):
{{
  "primary_keyword": "the single most important keyword for this page",
  "steps": [
    {{
      "action": "Short action title",
      "time_minutes": 5,
      "detail": "What is wrong / current state",
      "instruction": "Exactly what to do, step by step. For content: specify which H2 section, what to write about, which keywords to include. For links: include the full target URL.",
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
            "lost_clicks": _to_native(r.get("lost_clicks_estimate", 0)),
            "position": _to_native(r.get("position", 0)),
            "ctr_gap": _to_native(r.get("ctr_gap_pct", 0)),
            "meta_score": _to_native(r.get("meta_score", 100)),
            "content_score": _to_native(r.get("content_score", 100)),
            "top_keywords": [str(k) for k in r.get("target_keywords", [])[:3]],
            "issues": [str(i) for i in r.get("issues", [])[:3]],
        })

    prompt = f"""You are an SEO strategist for {site_url}. Create a prioritized action plan based on these audit results:

{json.dumps(summary_data, ensure_ascii=False, indent=2)}

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
