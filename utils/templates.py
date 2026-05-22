"""
HTML templates for blog articles and category content.
Used by AI generator to produce CMS-ready HTML.

Language-agnostic: the `language` parameter is interpolated into the
prompt text and Claude generates the natural {language} equivalent of
every example phrase (FAQ headers, expert recommendations, anchor text,
etc.). No per-language vocabulary dicts to maintain — the same templates
drive Swedish, Danish, English, German, French, Spanish, Norwegian,
Italian, Dutch, Finnish, … any language Claude speaks.
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
                <div class="xmx-short-description">PRODUCT_DESCRIPTION<br><strong>Pris: PRODUCT_PRICE</strong></div>
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

### DO NOT:
- Do NOT add <h1> — the CMS adds that
- Do NOT use generic stock photo URLs — use real product image URLs
- Do NOT use markdown — output PURE HTML
- Do NOT wrap in <html><body> tags
- Do NOT write walls of text — keep paragraphs short and scannable
- Do NOT use generic filler — every sentence must add value
- Do NOT use generic anchor text like "click here" / "read more" or
  their {language} equivalents — anchor text must describe the target.
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
- Product cards in xmx-carousel format with real product data

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
"""


# ── Back-compat module-level constants ──────────────────────────────
# Default to Swedish for legacy callers; new code should call the
# functions above with an explicit `language`.

BLOG_TEMPLATE_INSTRUCTIONS = blog_template_instructions()
CATEGORY_BOTTOM_TEXT_INSTRUCTIONS = category_bottom_text_instructions()
