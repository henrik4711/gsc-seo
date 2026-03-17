"""
AI content generation: meta titles, descriptions, and landing page text
Uses Claude claude-sonnet-4-20250514 via Anthropic API
"""

import os
import anthropic
import streamlit as st
from typing import Optional


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
    
    import json
    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    raw = raw.replace("```json", "").replace("```", "").strip()
    
    result = json.loads(raw)
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
    
    import json
    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


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
    import json

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

    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


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
    
    import json
    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


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
    import json

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

    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def generate_keyword_text(
    client: anthropic.Anthropic,
    missing_keywords: list,
    existing_text: str,
    page_type: str,
    site_context: str = "",
    language: str = "Swedish",
) -> dict:
    """Generate optimized text paragraphs that naturally integrate missing keywords."""
    import json

    prompt = f"""You are a senior SEO copywriter. Rewrite or extend the following text to naturally integrate missing keywords.

## CONTEXT
Page type: {page_type}
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

    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def generate_keyword_faq(
    client: anthropic.Anthropic,
    missing_subtopics: list,
    keywords: list,
    site_context: str = "",
    language: str = "Swedish",
) -> dict:
    """Generate FAQ Q&A pairs targeting uncovered subtopics."""
    import json

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

    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


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
    import json

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

    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


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
    import json

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

    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def generate_article_meta(
    client: anthropic.Anthropic,
    title: str,
    keywords: list,
    site_context: str = "",
    language: str = "Swedish",
) -> dict:
    """Generate optimized meta title and description for a new article."""
    import json

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

    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def generate_action_plan(
    client: anthropic.Anthropic,
    audit_results: list,
    site_url: str,
) -> dict:
    """
    Generate prioritized action plan from all audit results
    """
    # Build summary of issues - convert numpy types to native Python
    import json

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
    
    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)
