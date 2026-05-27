"""
HTML templates for blog articles, category content, product pages,
test/review pages, and shopping guides.
Used by AI generator to produce CMS-ready HTML.

Language-agnostic: the `language` parameter is interpolated into the
prompt text and Claude generates the natural {language} equivalent of
every example phrase (FAQ headers, expert recommendations, anchor text,
etc.). No per-language vocabulary dicts to maintain — the same templates
drive Swedish, Danish, English, German, French, Spanish, Norwegian,
Italian, Dutch, Finnish, … any language Claude speaks.

SCHEMA POLICY
-------------
Every template embeds a complete JSON-LD <script type="application/ld+json">
block tailored to the page type, because Google needs schema to compete on
heavy-traffic verticals. Required schema per page type:

  - article         : Article + BreadcrumbList + FAQPage
  - category_bottom : ItemList + BreadcrumbList + FAQPage
  - product_page    : Product + Offer + AggregateRating + Review + BreadcrumbList + FAQPage
  - test_page       : Review + Product + AggregateRating + BreadcrumbList + FAQPage
  - shopping_guide  : HowTo (or ItemList) + Article + BreadcrumbList + FAQPage

PRICE + STOCK DECOUPLING
------------------------
Product and test templates render price + stock + availability via
**marker placeholders** (`{{PRICE}}`, `{{STOCK}}`, `{{AVAILABILITY}}`)
inside the schema and in the visible CTA only. The descriptive body
text never quotes a price or stock figure, so the CMS can hot-swap
those values on every product without regenerating the AI text.

AFFILIATE LINKS
---------------
Product CTAs use `rel="nofollow sponsored"` and the marker
`{{AFFILIATE_URL}}` so the publisher template can inject the
tracked link without touching body content. Body internal links use
real on-site URLs only.
"""


def blog_template_instructions(language: str = "Swedish") -> str:
    """Build the blog-article HTML template instructions for the given language."""
    return f"""
## ARTICLE HTML FORMAT — FOLLOW THIS EXACTLY

### Structure:
- Start with intro <p> paragraph (NO H1 — CMS adds that automatically)
- Use <h2> for main sections (3-5 sections)
- Use <h3 style="font-size:25px"> for subsections and product categories:
  <h3 style="font-size:25px"><a href="/CATEGORY-URL"><strong>Product Category Name</strong></a></h3>
- After each subsection, add an expert recommendation:
  <p class="xmx--high-emphasis">– [Expert recommendation with specific, actionable advice].</p>
- MUST end with FAQ section: a <h2> with the natural {language} equivalent
  of "Frequently asked questions" (e.g. "Vanliga frågor" in Swedish,
  "Ofte stillede spørgsmål" in Danish, "Häufig gestellte Fragen" in
  German, "Foire aux questions" in French), followed by 3-5 <h3>
  questions + <p> answers.

### Content Quality (Google Helpful Content):
- Every paragraph MAX 3-4 sentences — scannable, not walls of text
- Use <ul>/<ol> lists for comparisons, features, tips (min 2 lists per article)
- Include at least one comparison section (e.g. "Type A vs Type B — which suits you?")
- Every section must HELP the reader — not just describe, but GUIDE decisions
- Address real concerns and hesitations honestly
- Include practical tips: how to use, how to choose, what to avoid

### E-E-A-T Signals (critical for Google):
- **Experience**: Write from first-hand knowledge in natural {language}.
  Use phrasing meaning "we have tested ...", "our experience shows ..." —
  rendered idiomatically, not translated word-for-word from English.
- **Expertise**: Specific details only an expert knows — not generic claims.
- **Authority**: Reference store expertise, customer service, years of experience.
- **Trust**: Mention guarantees, return policy, secure payment, discreet shipping.

### Product Recommendations:
- Use this product card format:
  <div class="xmx-carousel">
    <div class="xmx-carousel-container">
      <div class="xmx-carousel-elements">
        <a href="PRODUCT_URL">
          <div class="xmx-carousel-element">
            <div class="xmx-carousel-card xmx-carousel-card--768-3 xmx-carousel-card--1024-3 xmx-carousel-card--1280-3">
              <div class="xmx-image">
                <img src="PRODUCT_IMAGE_URL" alt="PRODUCT_NAME" width="96" height="152">
              </div>
              <div class="xmx-carousel-card-text">
                <div class="xmx-name">PRODUCT_NAME</div>
                <div class="xmx-short-description">PRODUCT_DESCRIPTION<br><strong>Pris: {{{{PRICE}}}}</strong></div>
              </div>
            </div>
          </div>
        </a>
      </div>
    </div>
  </div>

### Internal Links:
- Link category and product names to their actual pages
- Use the EXACT URLs provided in the site URL list — do NOT invent URLs
- Absolute URLs in href must include the https://www. prefix exactly as listed
- Link relevant terms naturally in body text (2-5 internal links per 500 words)
- Every link must have descriptive anchor text matching the target page's topic,
  written in {language}.

### Tone of Voice:
- Warm, knowledgeable — like a trusted friend with expert knowledge
- Slightly playful but respectful, never clinical or crude
- Use the informal "you" form natural to {language} (e.g. "du" in
  Scandinavian, "tú" in Spanish, "du" in German if brand-appropriate).
- Expert recommendations: specific, actionable, not vague
- Be genuinely helpful — guide the reader to make the right choice
- Normalize the topic — remove shame and stigma where applicable

### Schema Markup (Article + BreadcrumbList + FAQPage):
Append a single <script type="application/ld+json"> block AT THE END of the
HTML output. Use `@graph` to combine all three types. Use the placeholders
`{{{{CANONICAL_URL}}}}`, `{{{{PUBLISH_DATE}}}}`, `{{{{MODIFY_DATE}}}}`,
`{{{{AUTHOR_NAME}}}}`, `{{{{ORG_NAME}}}}`, `{{{{ORG_LOGO}}}}` — the publisher
fills these in. Mirror the FAQ questions/answers exactly from the visible FAQ
HTML so Google validates them as identical.

### DO NOT:
- Do NOT add <h1> — the CMS adds that
- Do NOT use generic stock photo URLs — use real product image URLs
- Do NOT use markdown — output PURE HTML
- Do NOT wrap in <html><body> tags
- Do NOT write walls of text — keep paragraphs short and scannable
- Do NOT use generic filler — every sentence must add value
- Do NOT use generic anchor text like "click here" / "read more" or
  their {language} equivalents — anchor text must describe the target.
- Do NOT hardcode prices — always use the `{{{{PRICE}}}}` marker so the
  CMS can update prices without touching body text.
"""


def category_bottom_text_instructions(language: str = "Swedish") -> str:
    """Build the category-page bottom-text HTML template instructions for the given language."""
    return f"""
## CATEGORY PAGE BOTTOM TEXT FORMAT

This is the SEO content that appears BELOW the product grid on category pages.
It is the most important text for Google on category pages.

### Structure:
- NO H1 (CMS has that above the product grid)
- Start with a <h2> buying-guide section. The heading should be the
  natural {language} equivalent of "How to choose [category]?" or
  "Guide to [category]" — written idiomatically, not translated literally.
- Use <h3 style="font-size:25px"> with linked subcategory names:
  <h3 style="font-size:25px"><a href="/SUBCATEGORY-URL"><strong>Subcategory Name</strong></a></h3>
- After each subcategory section, add an expert recommendation in the
  pattern "Choose [product type] if you [benefit]" — rendered in natural
  {language}, wrapped in <p class="xmx--high-emphasis">– ….</p>
- Add a FAQ section with <h2> heading using the natural {language}
  equivalent of "Frequently asked questions about [category]",
  and 3-5 <h3> questions with <p> answers.
- Add product carousel cards for top recommended products
- End with trust signals

### INTERNAL LINKING RULES (critical for Google):
- ONLY link to pages that belong in this page's topic cluster:
  - Child/subcategory pages (vertical DOWN)
  - Parent/hub page (vertical UP)
  - Sibling pages in same category (horizontal)
- Do NOT link to unrelated categories — keep the cluster tight.
- Every link must have descriptive anchor text in {language} that
  matches the target page's topic.
- REMOVE/don't include links that would confuse Google about this page's topic
- Check the SUBCATEGORY and SIBLING URL lists — link to ALL of these, they are the cluster

### E-E-A-T & GOOGLE HELPFUL CONTENT (critical):
- **Experience**: Write as if from someone who has tested and used these
  products. Use {language} phrasings meaning "our experience shows ...",
  "we have helped thousands of customers ..." — natively, not translated.
- **Expertise**: Include specific, detailed advice that only an expert
  would know. Generic claims ("X is good") fail; specific mechanisms
  ("this curved tip targets X more directly") pass — in {language}.
- **Authority**: Reference the store's experience, expert staff, customer
  reviews. Use real authority signals — years in business, customer
  satisfaction, expert support.
- **Trust**: Mention discreet shipping, secure payment, return policy,
  quality guarantees. Build trust through specifics, not generic claims.

### HELPFUL CONTENT (Google's standard):
- Every paragraph must HELP the reader make a decision or learn something
- Answer the questions a real customer would have BEFORE buying
- Address common concerns and hesitations honestly
- Compare product types to help the customer choose the RIGHT one
- Include practical tips: how to use, how to clean, what material to choose
- Don't just describe products — guide the customer through their decision

### NUDGING & CONVERSION:
- Subtle nudging toward trying products — never pushy.
- Address fears/taboos directly with {language} phrasings meaning "it's
  completely normal that ...", "many people experience that ..." — natively.
- Social proof: {language} for "our most popular", "thousands of satisfied
  customers" — natively phrased.
- Reduce friction: mention easy returns, discreet packaging, expert support.

### Content Requirements:
- 800-1500 words total
- ALL relevant keywords must be naturally integrated (never stuffed)
- ALL subcategory pages must be linked with descriptive anchor text
- ALL sibling category pages should be cross-linked where relevant
- Use the EXACT URLs from the site URL list — do NOT invent URLs
- Absolute URLs in href must include the https://www. prefix exactly as listed
- Expert quotes in xmx--high-emphasis format
- Product cards in xmx-carousel format with real product data — use
  `{{{{PRICE}}}}` placeholder, never a hardcoded price

### READABILITY — Target LIX 35-40 (Scandinavian readability index):
LIX = (words / sentences) + (long words × 100 / words), where long words have >6 characters.
35-40 is the sweet spot for e-commerce: readable for a broad audience without sounding childish.
To stay in range:
- Short sentences (avg 12-18 words). Break up anything longer with a period.
- Prefer common everyday {language} words over compound/technical ones
  (e.g. the {language} equivalent of "use" instead of "implement", or
  "choose" instead of "select").
- Split long compound words when natural — but keep proper {language}
  compounds intact where they read better than separated forms.
- Mix sentence lengths — not all short (LIX <25 reads as childish), not all long (LIX >45 reads as academic)
- FAQ answers can be slightly shorter/simpler than body text — that's fine

Note: LIX is calibrated for Scandinavian languages. For other languages
the same principle applies — shorter sentences, common everyday words —
but the absolute LIX number is less meaningful.

### Schema Markup (ItemList + BreadcrumbList + FAQPage):
Append a single <script type="application/ld+json"> block AT THE END.
- ItemList: each subcategory becomes one ListItem with position + url + name.
- FAQPage: mirror the visible FAQ Q/A exactly.
- Use placeholders `{{{{CATEGORY_URL}}}}`, `{{{{CATEGORY_NAME}}}}`,
  `{{{{PARENT_CATEGORY_URL}}}}`, `{{{{PARENT_CATEGORY_NAME}}}}`.

### Tone of Voice:
- Warm, knowledgeable — like a trusted expert friend
- Use the informal "you" form natural to {language}.
- Genuinely helpful — guide the customer, don't just list keywords
- Normalize exploring the topic — remove shame and stigma where applicable
- NEVER keyword-stuff or sound robotic or AI-generated

### DO NOT:
- Do NOT add <h1>
- Do NOT use markdown — pure HTML only
- Do NOT wrap in <html><body>
- Do NOT invent URLs — use only real URLs from the site URL list
- Do NOT write generic filler text — every sentence must add value
- Do NOT link to pages outside this topic cluster
- Do NOT use generic anchor text like "click here" / "read more" or
  their {language} equivalents.
- Do NOT repeat the same information in different words (Google detects this)
- Do NOT hardcode prices in product cards — use `{{{{PRICE}}}}` marker
"""


# ──────────────────────────────────────────────────────────────────────
# NEW TEMPLATES (added 2026-05-27 for greenfield affiliate-style sites)
# ──────────────────────────────────────────────────────────────────────


def product_page_instructions(language: str = "Swedish") -> str:
    """Build the single-product-page HTML template instructions.

    Produces a complete product page body. Designed for affiliate sites
    where price + stock change daily and the body text must NOT need
    regeneration when they do. Uses marker placeholders for everything
    volatile, so the CMS layer can hot-swap values.
    """
    return f"""
## PRODUCT PAGE HTML FORMAT — FOLLOW THIS EXACTLY

The output is the full product page BODY (everything between header and
footer). The CMS layer renders price, stock, and the affiliate CTA on
top of this body using template variables — the AI text below must NOT
quote a price figure or stock status anywhere in the body. Use the
marker `{{{{PRICE}}}}` only inside the schema block.

### Structure (in order):
1. Intro paragraph (60-100 words) — hook + who this product is for + 1
   specific benefit. NO H1, NO banned openers, NO "Discover/Upptäck",
   NO marketing imperatives. Talk to ONE specific reader.
2. <h2> with the natural {language} equivalent of "What [Product Name] is" —
   a 100-150 word explanation of the product's design and intent.
3. <h2> with the natural {language} equivalent of "Who [Product Name] is
   for" — 100-150 words on the specific buyer profile + the 2-3 use cases
   the product handles best, AND one use case where the buyer should pick
   something else. Real reviews say "skip this if you want X". Commit.
4. <h2> with the natural {language} equivalent of "How to use [Product
   Name]" — 4-6 practical, specific steps. Use <ol>. Each step ≤ 25
   words. Include at least one tip a generalist wouldn't know.
5. <h2> with the natural {language} equivalent of "Features &
   specifications" — render specs as a <table>:
   <table class="product-specs">
     <tr><td>Material</td><td>...</td></tr>
     <tr><td>Size</td><td>...</td></tr>
     <tr><td>Weight</td><td>...</td></tr>
     ...
   </table>
   List ALL spec rows the product feed provides. NEVER list price or stock here.
6. <h2> with the natural {language} equivalent of "Pros & cons" — TWO
   <ul> lists. 3-5 specific pros, 2-3 honest cons. AI hedges; humans
   commit — name a real downside (size, learning curve, material care,
   battery life, etc.). Generic ("might not suit everyone") fails.
7. <h2> with the natural {language} equivalent of "How [Product Name]
   compares" — 100-150 words comparing to 1-2 named alternatives the
   buyer is likely also considering. Pick a side: "If you want X, get
   this. If you want Y, get [alternative]."
8. <h2> with the natural {language} equivalent of "Our verdict" — a
   <p class="xmx--high-emphasis">– …</p> expert recommendation (40-60
   words) summarizing who should buy and why.
9. <h2> with the natural {language} equivalent of "Frequently asked
   questions" — 4-6 <h3> + <p> Q/A blocks. Mix question types: usage,
   maintenance, compatibility, sizing, returns. NO price questions in body
   text (price changes — use the FAQ for product-care questions instead).
10. Affiliate CTA block (visible HTML, placed both AFTER step 2 and at the
    very end):
    <div class="affiliate-cta">
      <a href="{{{{AFFILIATE_URL}}}}" class="affiliate-button" rel="nofollow sponsored" target="_blank">
        [{language} equivalent of "Buy at [merchant_name]"]
      </a>
      <p class="affiliate-trust">[Trust line in {language}: discreet
      delivery, return policy, secure payment — written generically per
      the OPERATIONAL FACTS rules]</p>
    </div>

### E-E-A-T Signals (Google ranking factor #1 for affiliate/review content):
- **Experience**: at least 3 first-hand observations in {language} —
  "we noticed X", "in our testing", "after a week of use". Each must
  reference a SPECIFIC detail (texture, sound level, charging time,
  weight in hand) — generic experience claims fail.
- **Expertise**: include 2-3 details only a domain expert would know.
  Compare materials, mechanisms, manufacturing — not just specs.
- **Authority**: cite category authority in {language} ("among the most
  recommended [category] of 2026", "the manufacturer X has produced
  [category] since YYYY"). Only cite facts present in source data.
- **Trust**: use OPERATIONAL FACTS rules — vague-but-safe trust language
  unless specific values are given in site context.

### Nudging & conversion (subtle, never pushy):
- Place ONE soft nudge in intro ({language} equivalent of "thousands of
  buyers report ...", "the bestselling [subcategory] in 2026 ...") —
  only if backed by source data.
- Address ONE common hesitation per ~300 words ({language} equivalent of
  "it's completely normal to feel ...", "the most common worry is X — here's
  why it isn't a problem").
- The "Our verdict" block is the strongest nudge — commit to a
  recommendation. Wishy-washy verdicts ("might suit some buyers")
  underperform.

### Internal Links:
- Link to the parent category page (using its real URL).
- Link to 2-3 sibling products in the same subcategory.
- Link to 1 relevant article/guide if the cluster has one.
- Anchor text: descriptive, in {language}, matches target page topic.
- Use ONLY URLs from the provided ALL SITE URLs list. Never invent.
- All internal links: regular <a href> — NO rel="nofollow".

### Schema Markup (Product + Offer + AggregateRating + Review +
###                  BreadcrumbList + FAQPage):

Append a SINGLE <script type="application/ld+json"> block at the very
end of the HTML (after the closing CTA), using @graph. The publisher
template injects `{{{{PRICE}}}}`, `{{{{AVAILABILITY}}}}`, `{{{{RATING_VALUE}}}}`,
`{{{{REVIEW_COUNT}}}}`, `{{{{IMAGE_URL}}}}`, `{{{{BRAND_NAME}}}}`,
`{{{{SKU}}}}`, `{{{{CURRENCY}}}}`, `{{{{CANONICAL_URL}}}}`,
`{{{{PRODUCT_NAME}}}}`, `{{{{BREADCRUMB_JSON}}}}`. Structure:

<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@graph": [
    {{
      "@type": "Product",
      "@id": "{{{{CANONICAL_URL}}}}#product",
      "name": "{{{{PRODUCT_NAME}}}}",
      "image": "{{{{IMAGE_URL}}}}",
      "description": "[Short product description here, max 200 chars,
        in {language}]",
      "sku": "{{{{SKU}}}}",
      "brand": {{"@type": "Brand", "name": "{{{{BRAND_NAME}}}}"}},
      "offers": {{
        "@type": "Offer",
        "url": "{{{{CANONICAL_URL}}}}",
        "priceCurrency": "{{{{CURRENCY}}}}",
        "price": "{{{{PRICE}}}}",
        "availability": "{{{{AVAILABILITY}}}}",
        "seller": {{"@type": "Organization", "name": "{{{{ORG_NAME}}}}"}}
      }},
      "aggregateRating": {{
        "@type": "AggregateRating",
        "ratingValue": "{{{{RATING_VALUE}}}}",
        "reviewCount": "{{{{REVIEW_COUNT}}}}"
      }}
    }},
    {{
      "@type": "BreadcrumbList",
      "itemListElement": {{{{BREADCRUMB_JSON}}}}
    }},
    {{
      "@type": "FAQPage",
      "mainEntity": [
        {{"@type": "Question", "name": "[Q1 in {language}]",
          "acceptedAnswer": {{"@type": "Answer", "text": "[A1 in {language}]"}}}}
        /* MIRROR EVERY FAQ FROM THE VISIBLE HTML — text must match exactly */
      ]
    }}
  ]
}}
</script>

The FAQ schema must mirror the visible FAQ block word-for-word. Google
de-validates schema where text drifts from on-page content.

### Tone of Voice — adapt to the product's category:
- Mass-market everyday products: friendly, practical, warm
- Premium/luxury products: refined, considered, slightly aspirational
- Health/intimate products: warm, normalizing, non-clinical, never crude
- Technical/specialist products: confident, specific, expert
- Beginner-oriented products: reassuring, step-by-step, no jargon

The system supplies a `product_category` and `product_tone` hint per
product — match the register of the category. Generic uniform voice
across all products is the strongest signal of AI mass-production and
fails on E-E-A-T.

### DO NOT:
- Do NOT add <h1> — CMS adds that
- Do NOT quote a price anywhere in body text — only in schema via `{{{{PRICE}}}}`
- Do NOT quote stock status anywhere in body text — same reason
- Do NOT use markdown — pure HTML only
- Do NOT wrap in <html><body>
- Do NOT include affiliate links inside body sentences — only in the CTA blocks
- Do NOT invent specs, materials, or features not in the source product data
- Do NOT mirror the source merchant's exact product description — write
  fresh, structurally different text (this matters for affiliate sites:
  Google penalizes duplicate content vs. the merchant)
- Do NOT use generic anchor text or banned vocabulary
- Do NOT write "[Product Name] is the perfect choice for everyone" or
  any universal-appeal claim — Google detects this as low-trust copy
"""


def test_page_instructions(language: str = "Swedish") -> str:
    """Build the product test/review HTML template instructions.

    A TEST page is a deep, opinionated single-product review (1500-2500
    words). Different from the product page: longer, more first-person
    experience, scored, explicitly comparative.
    """
    return f"""
## PRODUCT TEST / REVIEW HTML FORMAT — FOLLOW THIS EXACTLY

This is a FULL TEST/REVIEW of a single product. Distinct from a product
landing page: longer (1500-2500 words), first-person experience-driven,
scored, comparative. The output is the article body.

### Structure (in order):
1. Intro (80-120 words) — open with a SPECIFIC observation from testing
   (sound, weight, finish, first use). NO H1. NO banned openers.
2. <h2> "[{language} equivalent of: At a glance]" — a scorecard:
   <div class="test-scorecard">
     <table>
       <tr><th>[Overall]</th><td>{{{{SCORE_OVERALL}}}}/10</td></tr>
       <tr><th>[Quality]</th><td>{{{{SCORE_QUALITY}}}}/10</td></tr>
       <tr><th>[Ease of use]</th><td>{{{{SCORE_EASE}}}}/10</td></tr>
       <tr><th>[Value for money]</th><td>{{{{SCORE_VALUE}}}}/10</td></tr>
       <tr><th>[Build]</th><td>{{{{SCORE_BUILD}}}}/10</td></tr>
     </table>
     <p class="test-verdict-short"><strong>[{language} equiv. of:
       Short verdict — 1 sentence]</strong></p>
   </div>
   The AI proposes provisional scores; the editor reviews before publish.
3. <h2> "[Who this is for / Who should buy]" — 120-180 words committing
   to a SPECIFIC reader profile and one explicit anti-profile ("skip this
   if ..."). No hedging.
4. <h2> "[Testing methodology]" — 120-180 words on HOW we tested. This is
   the strongest E-E-A-T signal — describe the test conditions, duration,
   environment, what we compared against. Be specific.
5. <h2> "[What it's like in practice / Hands-on experience]" — 300-400
   words first-person testing notes. Use {language} phrasings meaning
   "during the first session we noticed ...", "after a week ...", "we
   compared this directly to ...". Specific observations only.
6. <h2> "[Pros & cons]" — TWO <ul> lists. 4-6 specific pros, 3-5 honest
   cons. Each item ≤ 15 words. Real downsides only — name them.
7. <h2> "[Comparison with alternatives]" — a <table> comparing this
   product to 2-3 named alternatives. Columns: Name, Best for, Price
   tier, Key differentiator. Rows: this product + 2-3 alternatives.
   Each "Best for" cell must commit to one reader profile.
8. <h2> "[Who shouldn't buy this]" — 80-120 words. THIS section is what
   separates expert reviews from AI mass content. Name 2-3 specific
   reader profiles for whom this product is wrong, and where they
   should look instead. Internal-link to those alternatives.
9. <h2> "[Verdict]" — 150-200 words committing to a recommendation.
   Final paragraph wrapped in <p class="xmx--high-emphasis">– …</p>.
10. <h2> "[Frequently asked questions]" — 5-7 <h3> + <p> Q/A. Cover:
    usage, durability, maintenance, compatibility, sizing/fit, what
    you wish you'd known. NO price questions in body — price changes.
11. Affiliate CTA (placed after section 2 AND at the very end):
    <div class="affiliate-cta">
      <a href="{{{{AFFILIATE_URL}}}}" class="affiliate-button"
         rel="nofollow sponsored" target="_blank">
        [{language} equivalent of "Buy at [merchant_name]"]
      </a>
      <p class="affiliate-trust">[Trust line in {language}]</p>
    </div>

### Author/Reviewer attribution (E-E-A-T critical):
Include an author block AFTER the intro:
<div class="test-author">
  <p><strong>[{language} for: Tested by]</strong>
     {{{{AUTHOR_NAME}}}}, {{{{AUTHOR_TITLE}}}}.
     [{language} for: Reviewed on]
     {{{{TEST_DATE}}}}.
     [{language} for: Test duration]:
     {{{{TEST_DURATION}}}}.</p>
</div>

### E-E-A-T Signals (the entire purpose of test pages):
- **Experience**: at least 6 first-hand observations across the body —
  not vague claims, specific sensory or functional details.
- **Expertise**: reference comparison to similar products in the
  category, manufacturing details, material science where relevant.
- **Authority**: the reviewer's role and the testing methodology section
  carry this — write them as if signed off by a domain expert.
- **Trust**: name the testing conditions and disclose the affiliate
  relationship transparently in a small disclosure line at the top:
  <p class="affiliate-disclosure"><small>[{language} disclosure: "We may
  earn a commission on purchases via our links — this does not affect our
  testing or scores."]</small></p>

### Nudging:
- One soft nudge in the verdict ({language} equivalent of "if you've been
  considering [category], this is one we keep recommending").
- The scorecard does the heavy lifting — make sure scores are
  defensible. Inflated scores destroy trust over time.

### Internal Links:
- Link to the product's category page (parent).
- Link to each named comparison alternative (siblings).
- Link to 1-2 relevant shopping guides if available.
- Use ONLY URLs from the provided site URL list.
- All internal links: <a href> with no rel attribute.
- Affiliate links: ONLY in the CTA blocks. NEVER in body sentences.

### Schema Markup (Review + Product + AggregateRating + BreadcrumbList +
###                  FAQPage):

Append a single <script type="application/ld+json"> block at the very
end. Use @graph. Required placeholders: same as product page, plus
`{{{{REVIEWER_NAME}}}}`, `{{{{REVIEW_DATE}}}}`, `{{{{SCORE_OVERALL}}}}`,
`{{{{SCORE_BEST}}}}=10`, `{{{{SCORE_WORST}}}}=1`. Structure:

<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@graph": [
    {{
      "@type": "Review",
      "itemReviewed": {{
        "@type": "Product",
        "name": "{{{{PRODUCT_NAME}}}}",
        "image": "{{{{IMAGE_URL}}}}",
        "brand": {{"@type": "Brand", "name": "{{{{BRAND_NAME}}}}"}},
        "sku": "{{{{SKU}}}}",
        "offers": {{
          "@type": "Offer",
          "url": "{{{{CANONICAL_URL}}}}",
          "priceCurrency": "{{{{CURRENCY}}}}",
          "price": "{{{{PRICE}}}}",
          "availability": "{{{{AVAILABILITY}}}}"
        }},
        "aggregateRating": {{
          "@type": "AggregateRating",
          "ratingValue": "{{{{RATING_VALUE}}}}",
          "reviewCount": "{{{{REVIEW_COUNT}}}}"
        }}
      }},
      "reviewRating": {{
        "@type": "Rating",
        "ratingValue": "{{{{SCORE_OVERALL}}}}",
        "bestRating": "10",
        "worstRating": "1"
      }},
      "name": "[Review title in {language}]",
      "author": {{"@type": "Person", "name": "{{{{REVIEWER_NAME}}}}"}},
      "datePublished": "{{{{REVIEW_DATE}}}}",
      "publisher": {{"@type": "Organization", "name": "{{{{ORG_NAME}}}}"}},
      "reviewBody": "[80-150 char summary of verdict, in {language}]"
    }},
    {{
      "@type": "BreadcrumbList",
      "itemListElement": {{{{BREADCRUMB_JSON}}}}
    }},
    {{
      "@type": "FAQPage",
      "mainEntity": [/* MIRROR every visible FAQ Q/A in {language} */]
    }}
  ]
}}
</script>

### Tone of Voice:
- First-person plural ("we") consistently — never first-person singular.
- Confident, committed. Test reviews that hedge underperform.
- Slightly more formal than category bottom-text — this is editorial,
  not catalog copy.
- Adapt register to product category (see product_page_instructions).

### DO NOT:
- Do NOT add <h1>
- Do NOT quote a price in body — only in schema via `{{{{PRICE}}}}`
- Do NOT inflate scores to look enthusiastic (Google detects review-farm
  patterns where every product scores 9-10).
- Do NOT mirror the merchant's marketing copy — this is editorial.
- Do NOT write a glowing verdict if cons are significant. Cons in the
  pros/cons section and zero cons in the verdict = AI tell.
- Do NOT include affiliate links inside paragraph text.
- Do NOT use generic anchor text or banned vocabulary.
- Do NOT skip the methodology section — it is the strongest E-E-A-T
  signal on this page type.
"""


def shopping_guide_instructions(language: str = "Swedish") -> str:
    """Build the shopping-guide HTML template instructions.

    A shopping guide covers a category-wide buying decision (e.g.
    "Best X for Y in 2026", "How to choose your first X"). Different from
    the article template: more structured around buyer-journey, scored
    product comparison matrix, explicit "best for" recommendations.
    """
    return f"""
## SHOPPING GUIDE HTML FORMAT — FOLLOW THIS EXACTLY

A shopping guide is a category-wide buying-decision page. Its job is
to (1) help the buyer self-identify a use case, (2) explain the
selection criteria, (3) match each criteria to a specific named product
that wins on that criterion. Length: 2000-3500 words.

### Structure (in order):
1. Intro (100-150 words) — open by naming the buyer's actual decision,
   not the category. Use a {language} construction meaning "if you're
   choosing your first [category]...", "if your current [category] no
   longer ...". NO H1, NO banned openers.
2. <h2> "[{language} equivalent of: Our top picks at a glance]" — a
   summary box with 5-7 named products and one-line role for each:
   <ul class="guide-toppicks">
     <li><strong>Best overall:</strong> <a href="/PRODUCT-URL">Product Name</a> — one-line why</li>
     <li><strong>Best for beginners:</strong> ...</li>
     <li><strong>Best premium:</strong> ...</li>
     <li><strong>Best value:</strong> ...</li>
     <li><strong>Best for [specific use case]:</strong> ...</li>
     /* etc. */
   </ul>
3. <h2> "[{language} equivalent of: How we chose]" — 150-200 words on the
   selection methodology. This is the second-strongest E-E-A-T signal
   after testing methodology on review pages. Be specific: how many
   products considered, what criteria, who tested.
4. <h2> "[{language} equivalent of: What to look for in a {{category}}]"
   — the buying criteria explained as 4-6 <h3 style="font-size:25px">
   subsections. Each subsection: 80-120 words explaining the criterion +
   one expert-rec line wrapped in <p class="xmx--high-emphasis">– …</p>.
   Cover: material/build, sizing/fit, key features, maintenance,
   budget tiers, common compatibility issues.
5. <h2> "[{language} equivalent of: Top picks reviewed]" — for EACH
   top-pick product from step 2, add a sub-block:
   <h3 style="font-size:25px"><a href="/PRODUCT-URL"><strong>Product Name</strong></a></h3>
   <p><strong>[Best for:]</strong> [specific buyer profile in {language}]</p>
   <p>[80-150 words on what makes this the pick for this role.
   Specific observations — material, behavior in use, one detail you
   notice after a week.]</p>
   <p class="xmx--high-emphasis">– [Expert recommendation: who this
   suits + one honest caveat.]</p>
   /* Affiliate CTA per product */
   <div class="affiliate-cta">
     <a href="{{{{AFFILIATE_URL_<PRODUCT_KEY>}}}}" class="affiliate-button"
        rel="nofollow sponsored" target="_blank">
       [{language} for "See [Product Name] at [merchant]"]
     </a>
   </div>
6. <h2> "[{language} equivalent of: Comparison table]" — a <table>
   with columns: Name, Best for, Material, Key feature, Price tier
   ($ / $$ / $$$ — NOT a specific price). Rows: all top picks.
7. <h2> "[{language} equivalent of: Common mistakes to avoid]" — 150-200
   words on 3-4 specific mistakes new buyers make. Mistakes are
   high-trust content — they signal real expertise.
8. <h2> "[{language} equivalent of: How to use your new {{category}}]"
   — 6-10 step <ol> for first use / setup / care.
9. <h2> "[{language} equivalent of: Frequently asked questions]" —
   6-8 <h3> + <p> Q/A. Cover: how to choose between A and B, when to
   replace, what accessories you need, sizing, compatibility, returns
   policy, where to start as a beginner.
10. Closing soft CTA paragraph — recap the top pick + invite to explore
    the category page (internal link).

### Author/Reviewer attribution:
After the intro:
<div class="guide-author">
  <p><strong>[{language} for: Researched and tested by]</strong>
     {{{{AUTHOR_NAME}}}}, {{{{AUTHOR_TITLE}}}}.
     [{language} for: Last updated]
     {{{{LAST_UPDATED}}}}. [{language} for: Products considered]:
     {{{{PRODUCTS_CONSIDERED}}}}. [{language} for: Top picks selected]:
     {{{{PRODUCTS_SELECTED}}}}.</p>
</div>

### Affiliate disclosure (top of page):
<p class="affiliate-disclosure"><small>[{language} disclosure: "Some
links on this page are affiliate links — we may earn a commission on
purchases. This never affects which products we recommend."]</small></p>

### E-E-A-T Signals (this page type's competitive moat):
- **Experience**: each top pick must include at least 2 specific
  first-hand observations ("in a week of testing", "the trigger
  responds in ...", "the texture feels ...").
- **Expertise**: the "What to look for" section is the place to flex
  domain expertise. Mention details a generalist comparison post
  wouldn't include.
- **Authority**: "How we chose" + "Common mistakes" + the author block.
- **Trust**: disclosure at top + transparent methodology + honest cons
  inside each top-pick block.

### Nudging:
- Each top pick converts on its own CTA — make every "Best for: X"
  line ring true to a specific reader.
- One soft global nudge near the end ({language} equivalent of "the
  buyer's market has shifted — these are the products worth your
  attention in 2026").
- The comparison table reduces decision friction — keep it short
  and decisive.

### Internal Links:
- Link to the category hub page.
- Link to each top-pick product's own page (the body link in <h3>).
- Affiliate links only in the CTA blocks.
- Link to 2-3 supporting articles if available (e.g. "[category]
  for beginners", "how to care for your [category]").
- All site URLs from the provided list — never invent.

### Schema Markup (Article + HowTo + ItemList + BreadcrumbList + FAQPage):

Append a single <script type="application/ld+json"> at the very end:

<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@graph": [
    {{
      "@type": "Article",
      "@id": "{{{{CANONICAL_URL}}}}#article",
      "headline": "[Guide title in {language}]",
      "image": "{{{{HERO_IMAGE_URL}}}}",
      "author": {{"@type": "Person", "name": "{{{{AUTHOR_NAME}}}}"}},
      "publisher": {{"@type": "Organization", "name": "{{{{ORG_NAME}}}}",
        "logo": {{"@type": "ImageObject", "url": "{{{{ORG_LOGO}}}}"}}}},
      "datePublished": "{{{{PUBLISH_DATE}}}}",
      "dateModified": "{{{{MODIFY_DATE}}}}"
    }},
    {{
      "@type": "ItemList",
      "itemListElement": [
        {{"@type": "ListItem", "position": 1, "url": "[product-1 url]",
          "name": "[product-1 name]"}}
        /* MIRROR every top pick from the visible HTML */
      ]
    }},
    {{
      "@type": "HowTo",
      "name": "[How to choose [category] — in {language}]",
      "step": [
        {{"@type": "HowToStep", "name": "[Step 1 name in {language}]",
          "text": "[Step 1 text in {language}]"}}
        /* MIRROR every step from the visible setup/care section */
      ]
    }},
    {{
      "@type": "BreadcrumbList",
      "itemListElement": {{{{BREADCRUMB_JSON}}}}
    }},
    {{
      "@type": "FAQPage",
      "mainEntity": [/* MIRROR every visible FAQ Q/A */]
    }}
  ]
}}
</script>

### Tone of Voice:
- Confident, editorial — "these are the picks we keep coming back to".
- First-person plural ("we"). Never "I".
- Adapt register to the category (see product_page_instructions).
- Direct and decisive — "skip this one if X" beats "you may prefer X".

### DO NOT:
- Do NOT add <h1>
- Do NOT quote specific prices anywhere — use price tier ($ / $$ / $$$).
- Do NOT mirror generic top-10 listicle format ("5 Best ...", "Top 7 ...")
  in the title or H2s — Google penalizes thin listicles.
- Do NOT include affiliate links inside paragraph text.
- Do NOT have every top pick score 9-10 — that signals review-farm.
- Do NOT use generic anchor text or banned vocabulary.
- Do NOT use markdown — pure HTML only.
- Do NOT wrap in <html><body>.
- Do NOT skip the methodology section — it is the page's E-E-A-T anchor.
"""


# ──────────────────────────────────────────────────────────────────────
# Template selector
# ──────────────────────────────────────────────────────────────────────


# Canonical content-type names. The values in topic_clusters
# (_infer_content_type) map onto these via CONTENT_TYPE_ALIASES below.
TEMPLATE_KINDS = (
    "article",          # generic blog article (how-to, comparison, listicle, explainer, guide)
    "category_bottom",  # category-page bottom SEO text
    "product_page",     # single-product landing page body
    "test_page",        # in-depth product test/review
    "shopping_guide",   # multi-product buying guide
)


# Map free-form content_type strings (from topic_clusters, user input,
# WP custom-post-types, etc.) onto the canonical TEMPLATE_KINDS above.
# Add to this dict when new aliases show up — never silently fall back.
CONTENT_TYPE_ALIASES = {
    # Article variants (all share the blog template — content_type itself
    # is passed in as a hint INSIDE the prompt to shape outline).
    "article": "article",
    "blog": "article",
    "how-to": "article",
    "guide": "article",
    "comparison": "article",
    "listicle": "article",
    "explainer": "article",

    # Category bottom-text
    "category": "category_bottom",
    "category_bottom": "category_bottom",

    # Product pages
    "product": "product_page",
    "product_page": "product_page",

    # Test / review pages
    "test": "test_page",
    "test_page": "test_page",
    "review": "test_page",

    # Shopping guides (distinct from generic guides — multi-product
    # buying decision pages with comparison matrices)
    "shopping-guide": "shopping_guide",
    "shopping_guide": "shopping_guide",
    "buying-guide": "shopping_guide",
    "buyers-guide": "shopping_guide",
    "best-of": "shopping_guide",
}


def select_template(content_type: str, language: str = "Swedish") -> str:
    """Return the right template-instruction block for a content_type.

    Falls back to `article` if the content_type is unrecognized — never
    raises. Unknown types are logged via the AI generator's
    `_template_fallback_count` for visibility.
    """
    if not content_type:
        return blog_template_instructions(language)
    kind = CONTENT_TYPE_ALIASES.get(content_type.strip().lower(), "article")
    if kind == "category_bottom":
        return category_bottom_text_instructions(language)
    if kind == "product_page":
        return product_page_instructions(language)
    if kind == "test_page":
        return test_page_instructions(language)
    if kind == "shopping_guide":
        return shopping_guide_instructions(language)
    return blog_template_instructions(language)


# ── Back-compat module-level constants ──────────────────────────────
# Default to Swedish for legacy callers; new code should call the
# functions above with an explicit `language`.

BLOG_TEMPLATE_INSTRUCTIONS = blog_template_instructions()
CATEGORY_BOTTOM_TEXT_INSTRUCTIONS = category_bottom_text_instructions()
PRODUCT_PAGE_INSTRUCTIONS = product_page_instructions()
TEST_PAGE_INSTRUCTIONS = test_page_instructions()
SHOPPING_GUIDE_INSTRUCTIONS = shopping_guide_instructions()
