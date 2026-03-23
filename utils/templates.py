"""
HTML templates for blog articles and category content.
Used by AI generator to produce CMS-ready HTML.
"""

BLOG_TEMPLATE_INSTRUCTIONS = """
## ARTICLE HTML FORMAT — FOLLOW THIS EXACTLY

### Structure:
- Start with intro <p> paragraph (NO H1 — CMS adds that automatically)
- Use <h2> for main sections (3-5 sections)
- Use <h3 style="font-size:25px"> for subsections and product categories:
  <h3 style="font-size:25px"><a href="/CATEGORY-URL"><strong>Product Category Name</strong></a></h3>
- After each subsection, add an expert recommendation:
  <p class="xmx--high-emphasis">– [Expert recommendation with specific, actionable advice].</p>
- MUST end with FAQ section: <h2>Vanliga frågor</h2> with 3-5 <h3> questions + <p> answers

### Content Quality (Google Helpful Content):
- Every paragraph MAX 3-4 sentences — scannable, not walls of text
- Use <ul>/<ol> lists for comparisons, features, tips (min 2 lists per article)
- Include at least one comparison section (e.g. "Type A vs Type B — which suits you?")
- Every section must HELP the reader — not just describe, but GUIDE decisions
- Address real concerns and hesitations honestly
- Include practical tips: how to use, how to choose, what to avoid

### E-E-A-T Signals (critical for Google):
- **Experience**: Write from first-hand knowledge. "Vi har testat...", "Vår erfarenhet visar..."
- **Expertise**: Specific details only an expert knows — not generic claims
- **Authority**: Reference store expertise, customer service, years of experience
- **Trust**: Mention guarantees, return policy, secure payment, discreet shipping

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
- Link relevant terms naturally in body text (2-5 internal links per 500 words)
- Every link must have descriptive anchor text matching the target page's topic

### Tone of Voice:
- Warm, knowledgeable — like a trusted friend with expert knowledge
- Slightly playful but respectful, never clinical or crude
- Use "du/dig" (informal Scandinavian addressing)
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
- Do NOT use generic anchor text like "click here" or "read more"
"""

CATEGORY_BOTTOM_TEXT_INSTRUCTIONS = """
## CATEGORY PAGE BOTTOM TEXT FORMAT

This is the SEO content that appears BELOW the product grid on category pages.
It is the most important text for Google on category pages.

### Structure:
- NO H1 (CMS has that above the product grid)
- Start with a <h2> buying guide section: "Hur väljer man [category]?"
  or "Guide till [category]" — help the customer choose
- Use <h3 style="font-size:25px"> with linked subcategory names:
  <h3 style="font-size:25px"><a href="/SUBCATEGORY-URL"><strong>Subcategory Name</strong></a></h3>
- After each subcategory section, add expert recommendation:
  <p class="xmx--high-emphasis">– Välj [product type] om du [benefit].</p>
- Add a FAQ section with <h2>Vanliga frågor om [category]</h2>
  and 3-5 H3 questions with <p> answers
- Add product carousel cards for top recommended products
- End with trust signals

### INTERNAL LINKING RULES (critical for Google):
- ONLY link to pages that belong in this page's topic cluster:
  - Child/subcategory pages (vertical DOWN)
  - Parent/hub page (vertical UP)
  - Sibling pages in same category (horizontal)
- Do NOT link to unrelated categories (e.g. don't link from /sexleksaker-for-man to /julkalender)
- Every link must have descriptive anchor text that matches the target page's topic
- REMOVE/don't include links that would confuse Google about this page's topic
- Check the SUBCATEGORY and SIBLING URL lists — link to ALL of these, they are the cluster

### E-E-A-T & GOOGLE HELPFUL CONTENT (critical):
- **Experience**: Write as if from someone who has tested and used these products.
  Use phrases like "vår erfarenhet visar", "vi har hjälpt tusentals kunder"
- **Expertise**: Include specific, detailed advice that only an expert would know.
  Not "vibratorer är bra" but "en G-punktsvibrator med böjd topp ger mer riktad stimulering"
- **Authority**: Reference the store's experience, expert staff, customer reviews.
  Use real authority signals — years in business, customer satisfaction, expert support.
- **Trust**: Mention discreet shipping, secure payment, return policy, quality guarantees.
  Build trust through specifics, not generic claims.

### HELPFUL CONTENT (Google's standard):
- Every paragraph must HELP the reader make a decision or learn something
- Answer the questions a real customer would have BEFORE buying
- Address common concerns and hesitations honestly
- Compare product types to help the customer choose the RIGHT one
- Include practical tips: how to use, how to clean, what material to choose
- Don't just describe products — guide the customer through their decision

### NUDGING & CONVERSION:
- Subtle nudging toward trying products — never pushy
- Address fears/taboos directly: "det är helt normalt att...", "många män upplever att..."
- Social proof: "vår mest populära", "tusentals nöjda kunder"
- Reduce friction: mention easy returns, discreet packaging, expert support

### Content Requirements:
- 800-1500 words total
- ALL relevant keywords must be naturally integrated (never stuffed)
- ALL subcategory pages must be linked with descriptive anchor text
- ALL sibling category pages should be cross-linked where relevant
- Use the EXACT URLs from the site URL list — do NOT invent URLs
- Expert quotes in xmx--high-emphasis format
- Product cards in xmx-carousel format with real product data

### Tone of Voice:
- Warm, knowledgeable — like a trusted expert friend
- "du/dig" addressing, slightly playful but respectful
- Genuinely helpful — guide the customer, don't just list keywords
- Normalize exploring sexuality — remove shame and stigma
- NEVER keyword-stuff or sound robotic or AI-generated

### DO NOT:
- Do NOT add <h1>
- Do NOT use markdown — pure HTML only
- Do NOT wrap in <html><body>
- Do NOT invent URLs — use only real URLs from the site URL list
- Do NOT write generic filler text — every sentence must add value
- Do NOT link to pages outside this topic cluster
- Do NOT use generic anchor text like "klicka här" or "läs mer"
- Do NOT repeat the same information in different words (Google detects this)
"""
