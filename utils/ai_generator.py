"""
AI content generation: meta titles, descriptions, and landing page text
Uses Claude claude-sonnet-4-20250514 via Anthropic API
"""

import os
import json
import anthropic
import streamlit as st
from typing import Optional

from utils.footer_text_api import add_www_to_url


def _www_urls(urls):
    """Return urls transformed to https://www. form, preserving input order/filter."""
    if not urls:
        return urls
    return [add_www_to_url(u) for u in urls if u]


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

HUMAN_WRITING_STYLE = """
WRITING STYLE — the text MUST read like a real person wrote it, NOT AI.
This is a HARD requirement. Output that contains any banned pattern below
fails the brief and must be rewritten.

BANNED OPENERS / CLOSERS (never use):
- "Sammanfattningsvis" / "Avslutningsvis" / "I slutändan" / "In conclusion" / "To sum up"
- "Det är viktigt att notera/komma ihåg" / "It is important to note" / "Worth noting"
- "Oavsett om du ... eller ..." / "Whether you ... or ..." / "No matter if you …"
- "Denna guide" / "I denna artikel" / "In this guide" / "In this article"
- "Utforska vår/vårt" / "Discover our" / "Upptäck" / "Discover" as opening word
- "Perfekt för dig som..." / "Perfect for those who..." / "Ideal for anyone who…"
- "I dagens..." / "I dagens snabba..." / "In today's fast-paced …"
- "Indeed," / "Faktum är att" as a sentence opener
- "Are you looking for …?" as opener — never open with a rhetorical question
- "Welcome to" / "Välkommen till"

BANNED VOCABULARY (AI tells — never use):
- delve, leverage, utilize (use 'use'), navigate (in figurative sense),
  embark, unleash, harness, foster, facilitate, synergy, tapestry, realm,
  resonates with, paramount, plethora, myriad, robust (figurative),
  seamless, holistic, game-changer, cutting-edge, revolutionary,
  state-of-the-art, world-class, world of, in the realm of,
  testament to, treasure trove, kaleidoscope, symphony, journey
  (in figurative sense), elevate, transform (in figurative sense)
- "It's not just X, it's Y" sentence pattern — banned in ALL forms
- "Whether you're a beginner or an expert" and any "X or Y" hedge
- Hedging phrases: "It's worth noting", "Keep in mind that",
  "It goes without saying", "Needless to say", "Suffice it to say"

BANNED STRUCTURE (these scream AI):
- Em-dashes (—) used more than ONCE per ~150 words. Prefer commas, periods,
  parentheses. AI famously over-uses em-dashes.
- Three-item parallel lists in body prose ("X, Y, and Z") more than once
  per paragraph
- Every paragraph the same length (3-4 sentences each = AI tell)
- Every bullet point the same length and grammatical structure
- Every H2/H3 starting with the same part of speech (all gerunds, or all
  imperatives, or all nouns)
- Closing every section with a summary sentence
- Ending the whole article with "In conclusion / To sum up / Overall"

REQUIRED:
- Write like a knowledgeable friend who actually uses the product, NOT a
  brochure, textbook, or "content marketer". One specific, lived-in detail
  beats five generic claims.
- Sentence-length variance: mix 4-word jabs with 25-word ones, sometimes
  even a fragment. Don't average everything to 12-15 words.
- Use "du/dig" / "you" — talk TO the reader, not ABOUT them
- Real opinions: "Vi gillar X för att …" / "Ärligt talat är Y bättre" /
  "Honestly, Z is overrated" / "We don't recommend …"
- Include at least one unexpected expert detail per ~300 words — a tip,
  caveat, or counter-intuitive fact a generalist wouldn't know
- Vary paragraph length: some 1 sentence, some 4-5 sentences. Single-
  sentence paragraphs are fine when emphatic.
- Occasional contractions are fine in casual contexts ("don't", "it's")
- NEVER include specific prices (they change)
- Don't start adjacent sentences with the same word ("The" after "The")
- It's OK — preferred, even — to leave a sentence imperfect or slightly
  asymmetric. AI polishes everything to glassy uniformity; humans don't.
- For FAQ: use FAQPage schema microdata (itemscope/itemprop attributes)"""


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
{HUMAN_WRITING_STYLE}
{HUMAN_WRITING_STYLE}

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
        temperature=0,
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
{HUMAN_WRITING_STYLE}
{HUMAN_WRITING_STYLE}

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
        temperature=0,
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
        # Use EDITORIAL text (intro + bottom) for quality checks on category pages.
        # Full body_text includes product grid prices ("kr rea" x26 = product cards).
        _intro = (p.get("intro_text") or "")
        _bottom = (p.get("bottom_text") or "")
        _editorial = (_intro + " " + _bottom).strip().lower()
        full_body = _editorial if _editorial and len(_editorial) > 50 else (p.get("body_text") or "").lower()

        # ── Deterministic content quality checks (no AI needed) ──
        auto_flags = []
        word_count = p.get("word_count", 0)

        # 1. Keyword stuffing: any 2-3 word phrase repeated >5 times
        if full_body and word_count > 100:
            from collections import Counter
            words = full_body.split()
            bigrams = [f"{words[j]} {words[j+1]}" for j in range(len(words)-1)]
            trigrams = [f"{words[j]} {words[j+1]} {words[j+2]}" for j in range(len(words)-2)]
            bigram_counts = Counter(bigrams).most_common(5)
            trigram_counts = Counter(trigrams).most_common(5)
            stuffed = []
            for phrase, count in bigram_counts + trigram_counts:
                # Skip very common/generic phrases
                if count >= 6 and len(phrase) > 5:
                    stuffed.append(f"'{phrase}' x{count}")
            if stuffed:
                auto_flags.append(f"KEYWORD STUFFING: {', '.join(stuffed[:3])}")

        # 2. No product/brand mentions on category pages
        if p.get("page_type") == "category" and word_count > 200:
            # Check for brand names, product names, prices
            has_brand = any(b in full_body for b in ["fleshlight", "satisfyer", "tenga", "womanizer", "lovense", "we-vibe", "lelo"])
            has_price = any(p_word in full_body for p_word in [" kr", ":-", "pris"])
            if not has_brand and not has_price:
                auto_flags.append("NO PRODUCT/BRAND/PRICE mentions — generic text without real product references")

        # 3. Repetitive sentence structure (many sentences start the same way)
        if full_body and word_count > 200:
            sentences = [s.strip() for s in full_body.replace(".", ".\n").split("\n") if len(s.strip()) > 20]
            if len(sentences) >= 5:
                starts = [s[:20] for s in sentences]
                start_counts = Counter(starts)
                repetitive = [(s, c) for s, c in start_counts.most_common(3) if c >= 4]
                if repetitive:
                    auto_flags.append(f"REPETITIVE STRUCTURE: {repetitive[0][1]} sentences start with '{repetitive[0][0][:15]}...'")

        # 4. Very high word count but low information density (filler text)
        if word_count > 1000:
            unique_words = len(set(full_body.split()))
            ratio = unique_words / max(word_count, 1)
            if ratio < 0.25:
                auto_flags.append(f"LOW VOCABULARY DIVERSITY: {unique_words} unique words in {word_count} total ({ratio:.0%}) — likely filler/repetitive content")

        auto_flags_text = ""
        if auto_flags:
            auto_flags_text = "⚠️ AUTO-DETECTED ISSUES:\n" + "\n".join(f"- {f}" for f in auto_flags) + "\n"

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
            from utils.url_helpers import url_path as _url_path
            page_path = _url_path(url).lower()
            child_pages = [u for u in page_topics.keys()
                          if _url_path(u).lower().startswith(page_path + "/")]
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
            f"{auto_flags_text}"
            f"Target keywords: {', '.join(p.get('target_keywords', [])[:5])}\n"
            f"Text sample:\n{body}\n"
        )

    prompt = f"""You are a Google Search Quality Rater evaluating page content quality.
{ANTI_HALLUCINATION_RULES}
{HUMAN_WRITING_STYLE}
{HUMAN_WRITING_STYLE}

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
        temperature=0,
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
{HUMAN_WRITING_STYLE}
{HUMAN_WRITING_STYLE}

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
        temperature=0,
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
{HUMAN_WRITING_STYLE}
{HUMAN_WRITING_STYLE}

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
1. Is natural and converting — NOT SEO spam
2. Includes primary keywords naturally (density ~1-2%)
3. Covers all relevant LSI keywords from GSC data
4. Has clear structure with H2/H3 — short paragraphs (max 3-4 sentences)
5. Includes social proof, USPs and CTA
6. Uses a discreet, respectful tone appropriate for the product category
7. **E-E-A-T signals**: Write with expertise (specific details, not generic claims), reference experience ("we have helped thousands of customers"), build trust (guarantees, returns, secure payment)
8. **Helpful Content**: Every paragraph must help the reader — guide decisions, compare options, address concerns. No filler text.
9. Include at least one FAQ section (3-5 questions) and one comparison/buying guide section
10. Use bullet lists or numbered lists where it improves scannability

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
        temperature=0,
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

{HUMAN_WRITING_STYLE}

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
- Apply the WRITING STYLE rules above without exception

## OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "paragraph": "The plain text paragraph with the anchor text naturally embedded",
  "html": "<p>The paragraph with <a href='{target_url}'>anchor text</a> as HTML</p>"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        temperature=0,
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

{HUMAN_WRITING_STYLE}

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
- Apply the WRITING STYLE rules above without exception — output that
  contains banned patterns must be rewritten

## OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "optimized_text": "The full optimized text with keywords integrated",
  "keywords_integrated": ["list", "of", "keywords", "that", "were", "integrated"],
  "word_count": 0
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        temperature=0,
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

{HUMAN_WRITING_STYLE}

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
- Apply the WRITING STYLE rules above without exception. Critically:
  do NOT open with "Upptäck/Discover", "I dagens", "Välkommen",
  "Are you looking for", or any banned opener.

## OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "optimized_text": "The rewritten intro paragraph",
  "keywords_integrated": ["list", "of", "keywords", "integrated"],
  "word_count": 0
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        temperature=0,
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

{HUMAN_WRITING_STYLE}

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
- Apply the WRITING STYLE rules above. Vary answer length — don't make
  every answer the same number of sentences or the same structure.
  Real-person FAQs have some short blunt answers and some longer ones.

## OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "faq_items": [
    {{"question": "...", "answer": "..."}}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        temperature=0,
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

{HUMAN_WRITING_STYLE}

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
- H2 / H3 headings must follow the WRITING STYLE rules: do NOT make every
  heading start with the same part of speech (e.g. all gerunds), do NOT
  use banned vocabulary in headings, and avoid the AI listicle look ("5
  Best …", "Top 7 …", "Ultimate Guide to …"). Headings should look like
  what a domain expert would actually write.

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
        temperature=0,
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

{ANTI_HALLUCINATION_RULES}
{HUMAN_WRITING_STYLE}

## ARTICLE DETAILS
Title: {title}
Content type: {content_type}
Target keywords: {', '.join(keywords[:10])}
Site context: {site_context}
Language: {language}
{outline_text}

## REQUIREMENTS
- Write in markdown format with proper H1, H2, H3 headings
- Include an engaging intro, well-structured sections, and a conclusion-
  style closing paragraph (but do NOT label it "Conclusion" / "Slutsats"
  / "Avslutningsvis" — just close the topic naturally)
- Naturally integrate target keywords (1-2% density). NEVER stuff.
- Include a FAQ section at the end with 3-5 relevant questions
- Write in {language}
- Aim for 1000-2000 words depending on content type
- Apply the WRITING STYLE rules above without exception. The article will
  be reviewed by AI-detection tools — if it contains banned vocabulary,
  banned openers, em-dash overuse, or uniform paragraph/sentence rhythm,
  it fails the brief. Genuine expertise and real, specific details are
  the strongest signals of human authorship — include them.

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
        temperature=0,
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

{HUMAN_WRITING_STYLE}

## ARTICLE
Title: {title}
Target keywords: {', '.join(keywords[:10])}
Site context: {site_context}
Language: {language}

## REQUIREMENTS
Title: 50-60 chars, primary keyword early, compelling. NO banned openers
("Upptäck/Discover", "I dagens", "Welcome to"). NO listicle clichés
("5 Best …", "Ultimate …"). Don't start with "Buy/Köp" either.
Description: 140-160 chars, includes primary keyword, has CTA. NO banned
vocabulary, NO em-dash overuse, NO "It's not just X, it's Y" pattern.
Write in {language}

## OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "meta_title": "...",
  "meta_description": "..."
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        temperature=0,
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
        temperature=0,
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
        url_list = f"\n\n## ALL PAGES ON THIS SITE (use these exact URLs in your recommendations)\n{chr(10).join(_www_urls(all_site_urls[:200]))}"

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
        temperature=0,
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
        url_section = f"\n\n## ALL SITE URLs (use these for internal links — do NOT invent URLs)\n{chr(10).join(_www_urls(all_site_urls[:150]))}"

    prompt = f"""You are a senior content writer for an e-commerce site.
Write a complete, CMS-ready article following the EXACT HTML format specified below.

{ANTI_HALLUCINATION_RULES}
{HUMAN_WRITING_STYLE}

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
- Intro paragraph (100-150 words) — NO H1 tag, NO banned openers
- 3-5 H2 main sections with H3 subsections for product categories
- Each H3 subsection: product description + expert recommendation (xmx--high-emphasis)
- Product carousel cards after recommendation sections using real product data
- FAQ at the end (3-5 questions as regular H3 + p, not accordion). Vary
  answer length — short blunt answers and longer ones, not all uniform.
- Closing paragraph with a soft CTA mentioning discreet shipping and
  customer service. Do NOT label it "Slutsats" / "Conclusion" / "To sum up".
- Internal links to related categories using real URLs
- Naturally integrate target keywords (1-2% density). NEVER stuff.
- Apply the WRITING STYLE rules above without exception. This article will
  be read by Google and by AI-detection tools — banned vocabulary, em-dash
  overuse, listicle clichés, or uniform rhythm fail the brief.

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
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_ai_json(message)


# ──────────────────────────────────────────────────────────────────────
# UNIFIED page content generator — single source of truth for ALL views
# ──────────────────────────────────────────────────────────────────────

def _required_items_for_page(prof: dict, audit_by_url: dict) -> tuple[list, list]:
    """
    Build the canonical "MUST appear" lists for the AI body-text prompt.

    The prompt already has many sections (GSC queries, cluster links,
    cannibal targets, hierarchy). This consolidates the most critical
    items into two flat lists that get injected as a NON-NEGOTIABLE
    checklist at the top of the prompt, AND validated programmatically
    after generation so the system can auto-retry on misses.

    Returns:
        (required_keywords, required_links)
        - required_keywords: list[str] — exact phrases that must appear
          (case-insensitive) somewhere in top_html + bottom_html.
        - required_links: list[dict] — each {"url", "anchor", "reason"}
          where the URL must appear in an href= attribute.
    """
    from utils.ui_helpers import normalize_url as _nu

    # ── Required KEYWORDS ────────────────────────────────────
    # Source 1: top GSC queries this page already gets impressions for —
    #           must keep covering them.
    # Source 2: missing keywords from content_audit.keyword_coverage —
    #           the audit explicitly flagged these as gaps.
    # Source 3: primary query (always).
    required_kws_raw = []
    primary = (prof.get("primary_query") or "").strip()
    if primary:
        required_kws_raw.append(primary)

    for q in prof.get("gsc_queries", [])[:8]:
        kw = (q.get("query") or "").strip()
        if kw:
            required_kws_raw.append(kw)

    # Pull missing keywords from the underlying audit row
    page_audit = audit_by_url.get(prof.get("url", ""), {}) or {}
    content_audit = page_audit.get("content_audit") or {}
    kw_coverage = content_audit.get("keyword_coverage") or {}
    for kw in (kw_coverage.get("missing") or [])[:10]:
        if isinstance(kw, str) and kw.strip():
            required_kws_raw.append(kw.strip())

    # Dedup case-insensitively, preserve order, cap to keep prompt sane.
    seen = set()
    required_keywords = []
    for kw in required_kws_raw:
        k = kw.lower().strip()
        if k and k not in seen:
            seen.add(k)
            required_keywords.append(kw)
    required_keywords = required_keywords[:12]

    # ── Required LINKS ──────────────────────────────────────
    # Source 1: cluster_link_outgoing (architectural — spoke→pillar etc.)
    # Source 2: cannibal_link_targets (resolves cannibalization conflicts)
    # Source 3: hierarchy parent (when this page has a URL parent on site)
    required_links = []
    seen_urls = set()
    self_norm = _nu(prof.get("url", ""))

    for r in prof.get("cluster_link_outgoing", []) or []:
        u = _nu(r.get("to_url", ""))
        if not u or u == self_norm or u in seen_urls:
            continue
        seen_urls.add(u)
        required_links.append({
            "url": r.get("to_url", ""),
            "anchor": r.get("anchor", ""),
            "reason": f"cluster {r.get('type', '')} ({r.get('cluster_topic', '')})",
        })

    for r in prof.get("cannibal_link_targets", []) or []:
        u = _nu(r.get("link_target", ""))
        if not u or u == self_norm or u in seen_urls:
            continue
        seen_urls.add(u)
        required_links.append({
            "url": r.get("link_target", ""),
            "anchor": r.get("query", ""),
            "reason": f"cannibal target ({r.get('link_target_reason', '')})",
        })

    return required_keywords, required_links[:8]


def _missing_required(html: str, required_keywords: list, required_links: list) -> tuple[list, list]:
    """
    Inspect generated HTML and return what's still missing.

    Returns:
        (missing_keywords, missing_links) — the items NOT found in html.
        - keywords: case-insensitive substring match against full text
        - links: substring match of normalized URL against any href= value
    """
    import re
    from utils.ui_helpers import normalize_url as _nu

    html_text = (html or "").lower()
    # Strip tags for keyword checking — keywords should appear in prose,
    # not just in alt= or hidden meta. But include hrefs/alt so an anchor
    # like "klassisk dildo" still counts as keyword presence.
    plain = re.sub(r"<[^>]+>", " ", html_text)
    href_blob = " ".join(re.findall(r'href=["\']([^"\']+)["\']', html_text))
    visible_blob = plain + " " + href_blob

    missing_kws = []
    for kw in required_keywords or []:
        if kw and kw.lower() not in visible_blob:
            missing_kws.append(kw)

    href_norms = {_nu(h) for h in re.findall(r'href=["\']([^"\']+)["\']', html or "")}
    missing_links = []
    for link in required_links or []:
        url = link.get("url", "")
        if not url:
            continue
        if _nu(url) not in href_norms:
            missing_links.append(link)

    return missing_kws, missing_links


def generate_page_content(
    url: str,
    target_query: str = None,
    validation_fixes: list | None = None,
    _attempt: int = 1,
    _max_attempts: int = 3,
) -> dict:
    """
    Generate COMPLETE body text (top + bottom + FAQ) for any page.

    Uses build_page_profile(url) to gather ALL data, then builds the full
    prompt with every rule (keyword focus, competing pages, GSC queries,
    hierarchy links, products with images, FAQ schema, writing style, etc.).

    Parameters
    ----------
    url : str
        The page URL to generate content for.
    target_query : str, optional
        Primary keyword to focus on. If None, uses profile's primary_query.
    validation_fixes : list[str], optional
        Issues detected in the previous generation (e.g. "Only 2 internal links",
        "1/3 target keywords missing: finger vibrator", "LIX 47 — too difficult").
        These are injected into the prompt as hard requirements to fix.

    Returns
    -------
    dict with keys: top_html, bottom_html, faq_schema, internal_links,
                    issues_fixed, top_word_count, bottom_word_count,
                    target_keyword
    """
    from config import get_anthropic_key, has_anthropic_key
    if not has_anthropic_key():
        raise ValueError("Anthropic API key missing")
    from utils.page_profile import build_page_profile
    from utils.ui_helpers import normalize_url
    from urllib.parse import urlparse as _up

    client = get_client(get_anthropic_key())
    prof = build_page_profile(url)

    # ── Core page data ──
    current_body = prof["body_text"]
    word_count = prof["word_count"]
    page_type = prof["page_type"]
    title = prof["title"]
    h1 = prof["h1"]
    language = st.session_state.get("content_language", "Swedish")
    site_context = st.session_state.get("site_context", "")

    query = target_query or prof["primary_query"] or h1 or title.split("|")[0].strip()

    # ── Auto-detected issues ──
    issues = prof.get("auto_issues", [])
    issues_text = "\n".join(f"- {i}" for i in issues) if issues else "No specific issues listed"

    # ── 1. Competing pages (from cannibalization) ──
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

    # ── 2. Current internal links FROM this page ──
    existing_links_text = ""
    if prof["internal_links_out"]:
        link_items = []
        for lnk in prof["internal_links_out"][:10]:
            link_items.append(f"  - \"{lnk.get('anchor', '')}\" → {lnk.get('url', '')}")
        existing_links_text = "\n".join(link_items)
    if not existing_links_text:
        existing_links_text = "NO internal links found on this page"

    # ── 3. Related pages from topic clusters ──
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

    # ── 3b. Hierarchy links (parent + children + brand pages) ──
    page_path = _up(prof["url"]).path.rstrip("/")
    page_segments = [s for s in page_path.split("/") if s]

    hierarchy_text = ""
    hier_lines = []

    # Parent page (one level up)
    if len(page_segments) >= 2:
        parent_path = "/" + "/".join(page_segments[:-1])
        parent_url = prof["url"].split("//")[0] + "//" + _up(prof["url"]).netloc + parent_path
        parent_audit = audit_by_url.get(normalize_url(parent_url), {})
        if parent_audit:
            parent_title = (parent_audit.get("title") or "").split("|")[0].split("»")[0].strip()
            hier_lines.append(f"  PARENT (link UP): <a href=\"{parent_url}\">{parent_title or parent_path.split('/')[-1]}</a>")

    # Child pages (if this is a pillar)
    if prof["is_pillar"] and prof["child_pages"]:
        hier_lines.append(f"  CHILDREN (link DOWN — this page is a PILLAR with {len(prof['child_pages'])} sub-pages):")
        for child_url in prof["child_pages"][:8]:
            child_audit = audit_by_url.get(normalize_url(child_url), {})
            child_title = (child_audit.get("title") or "").split("|")[0].split("»")[0].strip()
            child_name = child_url.split("/")[-1].replace("-", " ")
            hier_lines.append(f"    <a href=\"{child_url}\">{child_title or child_name}</a>")

    # Brand pages (detect from products + check if brand page exists)
    brand_names = set()
    for prod in prof["products"][:20]:
        if isinstance(prod, dict):
            name = (prod.get("name") or "").lower()
            for brand in ["fleshlight", "tenga", "satisfyer", "womanizer", "lovense", "we-vibe", "lelo", "fun factory", "doll king"]:
                if brand in name:
                    brand_names.add(brand)
    if brand_names:
        for brand in sorted(brand_names):
            brand_slug = brand.replace(" ", "-")
            for pattern in [f"/alla/{brand_slug}", f"/{brand_slug}", f"/brands/{brand_slug}"]:
                brand_url = prof["url"].split("//")[0] + "//" + _up(prof["url"]).netloc + pattern
                if audit_by_url.get(normalize_url(brand_url)):
                    hier_lines.append(f"  BRAND PAGE: <a href=\"{brand_url}\">{brand.title()}</a>")
                    break

    if hier_lines:
        hierarchy_text = "\n## HIERARCHY LINKS (site architecture)\n" + "\n".join(hier_lines)
        hierarchy_text += "\n\nInclude these links naturally in the text. Parent link can go in intro or first paragraph. Child/brand links spread across the bottom text."

    related_text += hierarchy_text

    # ── 4. Top GSC queries ──
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

    # ── 5. Products on this page (with images) ──
    products_text = ""
    products_with_images = []
    if prof["products"]:
        prod_lines = []
        for prod in prof["products"][:8]:
            if isinstance(prod, dict):
                name = prod.get("name", "?")
                p_url = prod.get("url", "")
                image = prod.get("image", "")
                prod_line = f"  - {name} — {prod.get('price', '?')} — {p_url}"
                if image:
                    prod_line += f" — IMAGE: {image}"
                    products_with_images.append({"name": name, "url": p_url, "image": image})
                prod_lines.append(prod_line)
        products_text = "\n".join(prod_lines)
    if not products_text:
        products_text = "No product data available — use generic product references from the store"

    # Build image instruction
    images_instruction = ""
    if products_with_images:
        images_instruction = (
            "\n\n## PRODUCT IMAGES (include 2-3 in bottom text)\n"
            "Google rewards pages with relevant images. Include 2-3 product images\n"
            "in the bottom text using this format:\n"
            '<figure><a href="PRODUCT_URL"><img src="IMAGE_URL" alt="PRODUCT NAME" '
            'width="300" loading="lazy"></a><figcaption>Short description</figcaption></figure>\n\n'
            "Available images:\n"
        )
        for pi in products_with_images[:5]:
            images_instruction += f'  - {pi["name"]}: <img src="{pi["image"]}" alt="{pi["name"]}">\n'
            images_instruction += f'    Link to: {pi["url"]}\n'
        images_instruction += (
            "\nPlace images between text sections (after an H2), not at the end.\n"
            "Use descriptive alt text with the product name. Add width='300' and loading='lazy'."
        )

    # ── Build existing-images block (preserve images from current page) ──
    existing_editorial_images = prof.get("editorial_images", []) or []
    if existing_editorial_images:
        _lines = [f"The current page has {len(existing_editorial_images)} editorial image(s) that MUST be kept:"]
        for i, ei in enumerate(existing_editorial_images, 1):
            _lines.append(
                f"  {i}. section={ei.get('section','bottom')} | "
                f"src={ei.get('src','')} | alt={ei.get('alt','')} | "
                f"link_href={ei.get('link_href','')} | caption={ei.get('caption','')}"
            )
        existing_images_block = "\n".join(_lines)
    else:
        existing_images_block = "(No existing editorial images on this page — nothing to preserve.)"

    # ── Cannibal link targets — pages this page should link TO ──
    cannibal_targets = prof.get("cannibal_link_targets", []) or []
    if cannibal_targets:
        _lines = ["Pages this page CONFLICTS with — add a contextual link to the recommended target:"]
        for i, ct in enumerate(cannibal_targets[:5], 1):
            _lines.append(
                f"  {i}. query='{ct['query']}' (intent={ct['query_intent']}) "
                f"→ link to {ct['link_target']} (priority {ct['link_target_priority']}, "
                f"reason: {ct['link_target_reason']})"
            )
        cannibal_targets_block = "\n".join(_lines)
    else:
        cannibal_targets_block = "(No cannibal link targets for this page.)"

    # ── Cluster link recommendations involving this page ──
    out_recs = prof.get("cluster_link_outgoing", []) or []
    if out_recs:
        _lines = [f"This page should add {len(out_recs)} new link(s) (cluster topology):"]
        for i, r in enumerate(out_recs[:8], 1):
            _lines.append(
                f"  {i}. [{r['type'].upper()}] → {r['to_url']} "
                f"with anchor '{r['anchor']}' (cluster: {r['cluster_topic']}) — {r['reason']}"
            )
        cluster_links_block = "\n".join(_lines)
    else:
        cluster_links_block = "(No new cluster links recommended for this page.)"

    # ── Structural signals — tell AI what container layout to respect ──
    struct = prof.get("structural_signals", {}) or {}
    struct_block = (
        f"Body classes: {struct.get('body_classes', [])}\n"
        f"Intro container(s) found: {struct.get('found_intro_classes', [])}\n"
        f"Bottom container(s) found: {struct.get('found_bottom_classes', [])}\n"
        f"Has #category-description id: {struct.get('has_category_description_id', False)}"
    )

    # ── Required keywords + links — programmatically validated post-generation ──
    required_keywords, required_links = _required_items_for_page(prof, audit_by_url)

    required_kw_block = ""
    if required_keywords:
        required_kw_block = (
            "════════════════════════════════════════════════════════════\n"
            "## ⛔ HARD REQUIREMENT — REQUIRED KEYWORDS (ALL MUST APPEAR)\n"
            "════════════════════════════════════════════════════════════\n"
            f"There are {len(required_keywords)} keywords below. Each one "
            "MUST appear at least once (case-insensitive) inside top_html "
            "or bottom_html. After you finish, the output is parsed and "
            "checked — ANY missing keyword causes IMMEDIATE rejection and "
            "regeneration. Do not skip even one. Treat this as a checklist:\n\n"
            + "\n".join(f"  [ ] {kw}" for kw in required_keywords)
            + "\n\nBefore returning your JSON, mentally tick each box and "
            "confirm the keyword appears in your text. Weave each into a "
            "natural sentence — do NOT keyword-stuff and do NOT just list "
            "them. Where possible, use the keyword inside an H2 heading or "
            "the first paragraph of its section.\n"
            "════════════════════════════════════════════════════════════\n"
        )

    required_link_block = ""
    if required_links:
        link_lines = []
        for r in required_links:
            link_lines.append(
                f"  [ ] <a href=\"{r['url']}\">{r['anchor']}</a>  "
                f"— reason: {r['reason']}"
            )
        required_link_block = (
            "════════════════════════════════════════════════════════════\n"
            "## ⛔ HARD REQUIREMENT — REQUIRED INTERNAL LINKS (ALL MUST APPEAR)\n"
            "════════════════════════════════════════════════════════════\n"
            f"There are {len(required_links)} links below. Each ONE must "
            "appear in your output as a real <a href=\"...\">anchor</a> tag "
            "with the EXACT URL shown — copy the URL character-for-character. "
            "The anchor text can be the suggestion or a close natural variant. "
            "After generation the href values are programmatically checked — "
            "any missing required URL triggers IMMEDIATE rejection and "
            "regeneration. Treat this as a checklist:\n\n"
            + "\n".join(link_lines)
            + "\n\nBefore returning your JSON, mentally tick each box and "
            "confirm the URL appears as an href. Place each link in a "
            "contextually relevant sentence — never dump them in a list. "
            "Vertical-up (spoke→pillar) goes in bottom_html. Horizontal "
            "(sibling→sibling) goes wherever it fits naturally.\n"
            "════════════════════════════════════════════════════════════\n"
        )

    # ── Validation-feedback block — shown at top of prompt so model can't miss it ──
    validation_block = ""
    if validation_fixes:
        lines = "\n".join(f"- {v}" for v in validation_fixes)
        validation_block = f"""
## RETRY — PREVIOUS ATTEMPT HAD THESE VALIDATION FAILURES
Your previous output for THIS page was rejected because of these issues.
You MUST fix ALL of them in this rewrite — the text will be validated again.

{lines}

Concretely, when you rewrite the text:
- If "internal links" count was below target, add more internal links to related site pages — aim for the top of the 8–12 range.
- If target keywords were missing, work each missing keyword into a natural sentence (ideally in an H2 or its first paragraph).
- If LIX is too high (>40), shorten sentences (aim for 12–18 words avg), prefer common everyday words over compound/technical ones, and break up long compounds when natural. Target LIX 35–40.
- If LIX is too low (<30), the text reads as childish — mix in some longer sentences and more varied vocabulary.
- If FAQ was missing, include a real FAQ section with 4–6 Q&A pairs.
- If broken/non-indexable URLs were linked, only link to URLs that appear in the allowed internal links list below.

"""

    # ── Build the full prompt ──
    prompt = f"""{ANTI_HALLUCINATION_RULES}

You are rewriting the BODY TEXT for an e-commerce category page.
{validation_block}
{required_kw_block}
{required_link_block}
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
URL: {url}
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
{images_instruction}

## EXISTING IMAGES IN CURRENT TEXT — CRITICAL (DO NOT LOSE THESE)
{existing_images_block}
Rules for the images listed above:
1. You MUST reproduce EVERY image above in the new text — do NOT remove any
2. Use the EXACT same src URL and alt text — do NOT change, paraphrase, or invent image URLs
3. Respect the "section" hint (intro = TOP TEXT, bottom = BOTTOM TEXT)
4. Wrap each image exactly as given — if a link_href is shown, wrap with
   <a href="LINK_HREF"><img src="SRC" alt="ALT" loading="lazy"></a>; if a
   caption is shown, wrap in <figure>...<figcaption>CAPTION</figcaption></figure>
5. Place each image at a NATURAL position (after a relevant H2 or paragraph),
   not clustered at top/bottom
6. You may also add NEW product images from the PRODUCT IMAGES list above, but
   NEVER invent image URLs that aren't in either list

## CANNIBAL LINK TARGETS — add these contextual links to resolve conflicts
{cannibal_targets_block}
For EACH cannibal target above, add ONE in-body link to that URL with an
anchor that matches the query intent. This breaks cannibalization without
removing either page.

## CLUSTER LINK RECOMMENDATIONS — strengthen topical authority
{cluster_links_block}
Add EACH link recommended above into the new text. Vertical-up links (spoke→pillar)
go in the BOTTOM TEXT; horizontal links (sibling→sibling) go wherever they fit
naturally. Use the EXACT anchor text shown — don't paraphrase.

## STRUCTURAL SIGNALS — what containers exist on this page
{struct_block}
Use this to know what kind of page you are rewriting and where text lives.

## CURRENT TEXT (this is what needs rewriting)
{current_body[:15000]}

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
   - 800-2000 words — this is where the real SEO value lives
   - Structure with 3-5 H2 headings covering:
     * Buying guide / how to choose (what to look for, materials, features)
     * Product types / variants (explain the differences)
     * Expert tips / usage advice (show real knowledge)
     * Care and maintenance (practical value)
   - Internal links to related pages using <a href="URL">anchor</a>
   - End with FAQ section (3-5 questions from lower-volume GSC queries)
   - E-E-A-T: expert advice, material comparisons, specific brand knowledge

## WRITING STYLE — CRITICAL
{HUMAN_WRITING_STYLE}

## LINK ANCHOR RULES (critical)
Every internal link MUST have a UNIQUE anchor text that matches the TARGET page:
- Link to /klassisk-dildo → anchor "klassisk dildo" (NOT just "dildo")
- Link to /amor-black → anchor "Fun Factory Amor" (product name, NOT "dildo")
- Link to /uppblasbar-dildo → anchor "uppblåsbar dildo" (specific variant)
- Link to /rea/billig-pocket-pussy → anchor "billiga pocket pussy" (sale variant)
NEVER use the same anchor text for different link targets.
NEVER use just the generic primary keyword as anchor for sub-pages.
Each anchor should help Google understand what the TARGET page is about.

## CONTENT RULES
1. NO keyword stuffing — primary keyword max 2x in top, max 5-6x in bottom (natural use across 1000 words)
2. Mention product NAMES and BRANDS — but NEVER specific prices (they change).
   This includes FAQ answers — do NOT mention price ranges like "1000-3000 kr".
   Instead say "priserna varierar beroende på funktioner och kvalitet".
3. MUST be EVERGREEN — relevant regardless of which products are currently shown
4. MUST be DIFFERENT from competing pages
5. E-E-A-T + TRUST: real product knowledge, material comparisons, honest recommendations.
   Show EXPERIENCE (e.g. "Vi har sålt sexleksaker i 40 år"), build TRUST (return policy,
   discreet shipping), and provide genuine VALUE to the customer (help them choose right)
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
    "keywords_integrated": ["list of target/GSC keywords you actually integrated naturally in top_html or bottom_html"],
    "products_featured": ["list of product names you mentioned or featured in the body"],
    "issues_fixed": ["which issues from the list above were fixed"]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=6000,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    result = _parse_ai_json(message) or {}

    # Tag the result so callers (validation UI, missed-items display)
    # can see exactly what was required regardless of whether the AI
    # met every requirement.
    if isinstance(result, dict):
        result["_required_keywords"] = required_keywords
        result["_required_links"] = required_links
        result["_attempt"] = _attempt
        result["_max_attempts"] = _max_attempts

    # Auto-retry on missed required items — every caller (Quick Wins,
    # Action Plan, batch flows) gets this for free.
    if isinstance(result, dict) and not result.get("error") and _attempt < _max_attempts:
        full_html = (result.get("top_html") or "") + " " + (result.get("bottom_html") or "")
        missing_kws, missing_links = _missing_required(full_html, required_keywords, required_links)
        if missing_kws or missing_links:
            new_fixes = list(validation_fixes or [])
            if missing_kws:
                new_fixes.append(
                    f"REQUIRED keyword(s) STILL missing — you MUST add each of these as natural prose: "
                    + ", ".join(f"\"{k}\"" for k in missing_kws)
                )
            for ml in missing_links:
                new_fixes.append(
                    f"REQUIRED link STILL missing — add this exact href: "
                    f"<a href=\"{ml['url']}\">{ml['anchor']}</a> (reason: {ml['reason']})"
                )
            return generate_page_content(
                url,
                target_query=target_query,
                validation_fixes=new_fixes,
                _attempt=_attempt + 1,
                _max_attempts=_max_attempts,
            )

    return result


# DEPRECATED: Use generate_page_content(url, target_query) instead.
# This older function lacks: top/bottom split, FAQ schema, product images,
# hierarchy links, unique anchors, keyword focus, competing pages context.
# Kept for backward compatibility — will be removed in a future release.
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
        subcats = "\n\n## SUBCATEGORY PAGES (MUST link to ALL of these)\n" + "\n".join(_www_urls(subcategory_urls[:20]))

    siblings = ""
    if sibling_urls:
        siblings = "\n\n## SIBLING/RELATED CATEGORIES (cross-link to these)\n" + "\n".join(_www_urls(sibling_urls[:15]))

    url_list = ""
    if all_site_urls:
        url_list = f"\n\n## ALL SITE URLs\n{chr(10).join(_www_urls(all_site_urls[:150]))}"

    bottom_word_count = len(current_bottom_text.split()) if current_bottom_text else 0
    intro_word_count = len(current_intro_text.split()) if current_intro_text else 0
    prompt = f"""You are a senior SEO copywriter.
Rewrite the category page bottom text following the EXACT format below.
{ANTI_HALLUCINATION_RULES}
{HUMAN_WRITING_STYLE}
{HUMAN_WRITING_STYLE}

## CRITICAL REQUIREMENTS — YOU MUST FOLLOW THESE
1. You MUST include AT LEAST 8-12 internal links in the text. Use ALL subcategory URLs and at least 3 sibling URLs from the lists below.
2. You MUST link every product card to its actual product URL using <a href="PRODUCT_URL"> wrapping the entire card.
3. Product cards MUST include the actual product image with <img src="IMAGE_URL" alt="PRODUCT_NAME">.
4. Product cards MUST show the actual price in <strong>Pris: PRICE</strong>.
5. Every <h3> subcategory section MUST link to that subcategory's URL.

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
        temperature=0,
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
    from utils.url_helpers import url_path as _url_path_fc, path_is_descendant as _pid_fc
    child_pages = []
    for other_url in page_topics.keys():
        if _pid_fc(other_url, url):
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
        from utils.url_helpers import url_segments as _usegs, paths_are_siblings as _psibs
        sibling_pages = []
        for other_url in page_topics.keys():
            if other_url != url and _psibs(other_url, url):
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
    ctr_gaps_for_page: list = None,
    cannibal_link_targets: list = None,
    cluster_link_outgoing: list = None,
    structural_signals: dict = None,
    editorial_images: list = None,
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
    # Send more text to AI for pillar/large pages, less for small pages
    text_cap = 4000 if word_count > 500 else 2000
    body_snippet = _clean_body_text(page_data, text_cap)
    text_is_fragment = word_count > 0 and len(body_snippet.split()) < word_count * 0.7
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
    links_to_remove = (linking.get("details") or {}).get("links_to_remove") or []
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

    # Inbound anchor text quality (from SF link map)
    linking_details = (content_audit.get("linking") or {}).get("details", {}) if content_audit else {}
    inbound_anchors = linking_details.get("inbound_anchor_stats", {})
    inbound_info = ""
    if inbound_anchors:
        inbound_info = (f"\nInbound links: {inbound_anchors.get('total', 0)} total — "
                        f"{inbound_anchors.get('descriptive', 0)} descriptive, "
                        f"{inbound_anchors.get('generic', 0)} generic, "
                        f"{inbound_anchors.get('empty', 0)} empty anchors")

    # Add actual inbound anchor texts from profile (aggregated from sf_link_map)
    from utils.page_profile import build_page_profile
    _profile = build_page_profile(url)
    if _profile["internal_links_in"]:
        anchor_counts = {}
        for lt in _profile["internal_links_in"][:100]:
            a = (lt.get("anchor", "") or "").strip()
            if a:
                anchor_counts[a] = anchor_counts.get(a, 0) + 1
        if anchor_counts:
            top_anchors = sorted(anchor_counts.items(), key=lambda x: -x[1])[:10]
            anchor_list = ", ".join(f'"{a}" ({c}x)' for a, c in top_anchors)
            inbound_info += f"\nTop inbound anchor texts: {anchor_list}"

    # Category-specific data
    intro_words = page_data.get("intro_word_count", 0)
    bottom_words = page_data.get("bottom_word_count", 0)
    product_count = page_data.get("product_count", 0)
    has_faq = page_data.get("has_faq", False)
    has_buying_guide = page_data.get("has_buying_guide", False)

    # Search intent from Ahrefs
    search_intent = page_data.get("search_intent", "")
    intent_scores = page_data.get("intent_scores", {})
    intent_info = ""
    if search_intent:
        intent_info = (f"\nSearch intent: {search_intent.upper()} "
                       f"(informational: {intent_scores.get('informational', 0)}%, "
                       f"commercial: {intent_scores.get('commercial', 0)}%, "
                       f"transactional: {intent_scores.get('transactional', 0)}%)")

    # Ahrefs keywords (supplement GSC with volume data)
    ahrefs_kws = page_data.get("ahrefs_keywords", [])

    # Content quality verdict (from profile)
    quality_info = ""
    if _profile["quality_verdict"]:
        quality_info = f"\nAI content quality verdict: {_profile['quality_verdict']} ({_profile['quality_score']}/10) — {_profile['quality_summary']}"

    # ── Cannibal link targets (intent + cluster aware) ──
    cannibal_link_info = ""
    if cannibal_link_targets:
        lines = []
        for ct in cannibal_link_targets[:5]:
            lines.append(
                f"- query \"{ct.get('query','')}\" (intent={ct.get('query_intent','')}) "
                f"→ link to {ct.get('link_target','')} "
                f"[priority {ct.get('link_target_priority',5)}: {ct.get('link_target_reason','')}]"
            )
        if lines:
            cannibal_link_info = "\nCANNIBAL link targets (add these contextual links to resolve conflicts):\n" + "\n".join(lines)

    # ── Cluster-based linking recommendations for this page ──
    cluster_link_info = ""
    if cluster_link_outgoing:
        lines = []
        for r in cluster_link_outgoing[:8]:
            lines.append(
                f"- [{r.get('type','').upper()}] add link to {r.get('to_url','')} "
                f"with anchor '{r.get('anchor','')}' (cluster: {r.get('cluster_topic','')}) — {r.get('reason','')}"
            )
        if lines:
            cluster_link_info = "\nCLUSTER link recommendations (add these to strengthen topical authority):\n" + "\n".join(lines)

    # ── Structural signals (CMS template containers) ──
    structural_info = ""
    if structural_signals:
        structural_info = (
            f"\nCMS template signals — body classes: {structural_signals.get('body_classes', [])}; "
            f"intro container(s): {structural_signals.get('found_intro_classes', [])}; "
            f"bottom container(s): {structural_signals.get('found_bottom_classes', [])}"
        )

    # ── Editorial images on the page (must be preserved in any rewrite) ──
    editorial_image_info = ""
    if editorial_images:
        editorial_image_info = (
            f"\nEditorial images currently on the page ({len(editorial_images)}) — "
            f"any rewrite plan MUST preserve them (same src + alt)."
        )

    # CTR gap opportunities for this page
    ctr_gap_info = ""
    if ctr_gaps_for_page:
        top_gaps = sorted(ctr_gaps_for_page, key=lambda g: -g.get("lost_clicks_estimate", 0))[:5]
        gap_lines = []
        for g in top_gaps:
            gap_lines.append(
                f"- \"{g.get('query', '')}\" pos {g.get('position', '?'):.1f}, "
                f"CTR gap {g.get('ctr_gap_pct', 0):.0f}%, "
                f"~{g.get('lost_clicks_estimate', 0)} lost clicks"
            )
        if gap_lines:
            ctr_gap_info = "\nCTR gap analysis shows these keyword opportunities:\n" + "\n".join(gap_lines)

    # Site-level validation context (informs per-page recommendations)
    site_validation = st.session_state.get("_site_validation")
    site_context_info = ""
    if isinstance(site_validation, dict):
        health = site_validation.get("overall_health_score", 0)
        critical = site_validation.get("critical_issues", [])[:3]
        structural = site_validation.get("structural_problems", [])[:3]
        site_context_info = f"\n\n## SITE-LEVEL CONTEXT (informs per-page recommendations)\nSite health score: {health}/100\n"
        if critical:
            site_context_info += f"Critical site issues: {'; '.join(critical)}\n"
        if structural:
            site_context_info += f"Structural problems: {'; '.join(structural)}\n"
        site_context_info += "When recommending changes for this page, respect these site-level issues — don't suggest fixes that conflict with them."

    # Ideal structure context — is this page scheduled for merge/delete? (from profile)
    if _profile["ideal_action"] == "merge_from":
        site_context_info += f"\n\n## CRITICAL: THIS PAGE IS SCHEDULED FOR MERGE\nAI Ideal Structure recommends: {_profile['ideal_detail']}\n**DO NOT** recommend content improvements for this page. Instead recommend: copy unique content to the merge target, set up 301 redirect, update internal links."
    elif _profile["ideal_action"] == "merge_to":
        site_context_info += f"\n\n## NOTE: THIS PAGE WILL RECEIVE MERGED CONTENT\n{_profile['ideal_detail']}\nRecommendations for this page should account for the additional content coming in."
    elif _profile["ideal_action"] == "delete":
        site_context_info += f"\n\n## CRITICAL: THIS PAGE IS SCHEDULED FOR DELETION\nAI Ideal Structure recommends deleting this page.\nReason: {_profile['ideal_detail']}\n**DO NOT** recommend content improvements. Instead recommend: delete the page, set up 301 redirect to a related page if it has any backlinks."

    # Data quality warnings (from scraper validation)
    data_warnings = page_data.get("_data_warnings", [])
    data_warning_section = ""
    if data_warnings:
        data_warning_section = "\n\n## ⚠ DATA QUALITY WARNINGS\nThe data below may be incomplete. Consider these warnings:\n" + "\n".join(f"- {w}" for w in data_warnings) + "\nIf word count is 0 but the page has a title, the content may not have been captured correctly. Do NOT assume the page is empty — state that data may be incomplete."

    # Include site URLs so AI uses real URLs in link recommendations
    url_list_section = ""
    if all_site_urls:
        url_list_section = f"\n\n## ALL PAGES ON THIS SITE (use these exact URLs when recommending internal links)\n{chr(10).join(_www_urls(all_site_urls[:200]))}"

    prompt = f"""You are a senior SEO strategist reviewing a single page. Based on ALL the data below, create a precise implementation plan with ONLY actions that are correct and relevant for THIS specific page.
{ANTI_HALLUCINATION_RULES}
{HUMAN_WRITING_STYLE}
{HUMAN_WRITING_STYLE}

IMPORTANT: When recommending internal links, use the EXACT URLs from the site URL list below. Do NOT invent or guess URLs.{url_list_section}{data_warning_section}

## PAGE DATA
URL: {url}
Page type: {page_type}
Title: "{title}" ({len(title)} chars)
Meta description: "{meta_desc}" ({len(meta_desc)} chars)
H1: "{h1}"
H2s: {', '.join(h2s) if h2s else 'None'}
H3s: {', '.join(page_data.get('h3s', [])[:10]) if page_data.get('h3s') else 'None'}
Word count: {word_count}
Internal links on page: {link_count}
Schema types present: {', '.join(schema_types) if schema_types else 'None'}
{f"Intro text: {intro_words} words (above product grid)" if page_type == "category" else ""}
{f"Bottom text: {bottom_words} words (below product grid)" if page_type == "category" else ""}
{f"Products on page: {product_count}" if product_count else ""}
{f"Has FAQ section: {'Yes' if has_faq else 'No'}" if page_type == "category" else ""}
{f"Has buying guide: {'Yes' if has_buying_guide else 'No'}" if page_type == "category" else ""}
{quality_info}{intent_info}{ctr_gap_info}{cannibal_link_info}{cluster_link_info}{structural_info}{editorial_image_info}

## EXISTING INTERNAL LINKS ON THIS PAGE (already present — do NOT suggest these again)
{_format_existing_links(page_data)}

## SCORES & METRICS
Meta score: {meta_score if meta_score is not None else 'not audited'}/100
Content score: {content_score if content_score is not None else 'not audited'}/100
Impressions: {impressions:,}
Lost clicks estimate: {lost_clicks:.0f}
Referring domains (backlinks): {referring_domains}
Total backlinks: {backlinks}
Authority score: {authority_score}{inbound_info}
Site context: {site_context}
Language: {language}
{site_context_info}

## TOPIC CLUSTER CONTEXT (this page's role in the site's topic structure)
{_format_cluster_context(page_data, topic_clusters)}

## GSC KEYWORDS (sorted by impressions, these are queries users search to find this page)
{', '.join(target_keywords)}

## AHREFS KEYWORDS (with search volume — use these if GSC keywords are weak)
{', '.join(ahrefs_kws) if ahrefs_kws else 'None'}

## MISSING KEYWORDS (from audit — keywords in GSC but NOT found on page text)
{', '.join(missing_kws) if missing_kws else 'None'}

## MISSING TOPIC SECTIONS (subtopics not covered in page text)
{', '.join(missing_subtopics) if missing_subtopics else 'None'}

## LINKS TO REVIEW (pointing to pages outside topic cluster — be CONSERVATIVE, only recommend removal if clearly harmful to topical focus. Many cross-cluster links are valid for user navigation.)
{chr(10).join(f"- {l['url']} (anchor: '{l['anchor']}')" for l in links_to_remove) if links_to_remove else 'None'}

## CURRENT PAGE TEXT ({len(body_snippet.split())} of {word_count} words shown){' — FRAGMENT: only partial text shown, full page has more content' if text_is_fragment else ''}{' — NOTE: text is empty, possibly due to JS rendering issues. Do NOT assume page has no content.' if not body_snippet and word_count == 0 and title else ''}
{body_snippet if body_snippet else '(no text captured)'}

## YOUR TASK
Create a step-by-step implementation plan. For each step, be SPECIFIC — tell the user exactly what to change and why.

CRITICAL RULES:
1. CONTENT-TOPIC ALIGNMENT (evaluate FIRST): Read the CURRENT PAGE TEXT and compare it to the page's TARGET KEYWORDS and TOPIC CLUSTER. Does the text ACTUALLY discuss the right topic? If the text talks about a different topic than what the page should rank for, flag this as the #1 priority — the content needs refocusing, not just keyword insertion.
2. KEYWORD RELEVANCE: Only include keywords that a user searching for them would expect to find on THIS specific page. A keyword for subcategory A does NOT belong on subcategory B. Be STRICT about this.
3. Do NOT recommend adding a keyword to H1 if H1 already contains it (handle Swedish/Danish chars: ä=a, ö=o, å=a)
4. INTERNAL LINKS — ADD new links, REVIEW flagged links:
   - Check EXISTING LINKS: do NOT recommend adding links already present
   - Check LINKS TO REVIEW: only recommend removing a link if it clearly damages topical focus AND has no user navigation value. Most cross-cluster links are FINE — users need to navigate between categories. Be VERY conservative with removal.
   - **LINK TARGET VALIDATION**: When choosing a target URL for an anchor text, the anchor must match the TARGET PAGE'S TOPIC, not a brand name.
     * If anchor is "penispumpar" → target MUST be a category page containing "penispump" in URL (e.g. /sexleksaker/sexleksaker-for-honom/penispumpar), NOT a brand page like /alla/bathmate
     * If anchor is "vibratorer" → target MUST be /sexleksaker/vibratorer, NOT /alla/lelo (which is a brand)
     * Brand pages (/alla/BRAND) should only be linked with the brand name as anchor text (e.g. "Bathmate" → /alla/bathmate is OK)
     * Generic category anchors must link to generic category pages
   - PREFER CATEGORY pages over product pages for new links
   - Use EXACT URLs from the site URL list. Do NOT invent URLs.
   - Before suggesting a link, ask: "If user clicks this anchor, will they land on a page about exactly that topic?" If the target is a brand page but anchor is a category term, the answer is NO — choose a different target.
5. META TITLE: MUST be under 60 chars (max 65). Primary keyword first. If current title is over 60 chars, you MUST generate a new optimized title and set meta_changed=true. Never leave the title field empty.
6. META DESCRIPTION: MUST be 140-160 chars (max 165). Include primary keyword + CTA. If current description is over 165 chars or under 120 chars, you MUST generate a new one and set meta_changed=true. Never leave the description field empty.
7. ALWAYS populate meta_title AND meta_description fields in the response, even if no change is needed (use current values). If ANY change is needed, set meta_changed=true.
8. Only suggest schema types appropriate for this page type
9. Be honest: if the page is already good, say so. Don't invent problems.
10. Each step must have a time estimate in minutes
11. For content steps: specify EXACTLY what text to add, which H2 heading, and where
12. If keywords indicate topics not covered by ANY existing page, suggest a NEW article/blog
13. For thin/generic/off-topic text: specify which sections need rewriting and what angle to take
14. BACKLINKS: If high impressions but few referring domains, recommend link building.
15. CLUSTER CONTEXT: All recommendations must fit the page's role:
    - PILLAR pages: must overview ALL child topics, link DOWN to each child
    - SPOKE pages: must go deep on THIS specific subtopic, link UP to hub, cross-link to siblings
    - Anchor texts must be contextually appropriate for the cluster relationship
16. E-E-A-T: If the page lacks trust signals (no FAQ, no buying guide, no expert voice, no reviews), recommend adding them.
17. SEARCH INTENT ALIGNMENT: Check the Search intent data. If the dominant intent is TRANSACTIONAL but the content reads like an informational guide, flag this — the content needs to be rewritten for purchase intent (product comparisons, CTAs, buying guidance). If intent is INFORMATIONAL but page is thin product listing, recommend adding educational content.
18. PROTECT HIGH-PERFORMING PAGES: If a page has position 1-3 for its main keywords, do NOT recommend major content rewrites or structural changes. Only suggest incremental improvements (adding FAQ, improving meta, adding internal links). Changing content on a page that already ranks well is HIGH RISK.

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
        temperature=0,
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
        temperature=0,
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
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return _parse_ai_json(message)
