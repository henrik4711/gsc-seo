"""
Mshop HTML templates for blog articles and category content.
Used by AI generator to produce CMS-ready HTML.
"""

BLOG_TEMPLATE_INSTRUCTIONS = """
## MSHOP HTML FORMAT — FOLLOW THIS EXACTLY

### Structure:
- Start with intro <p> paragraph (NO H1 — CMS adds that automatically)
- Use <h2> for main sections
- Use <h3 style="font-size:25px"> with linked category name for product subsections:
  <h3 style="font-size:25px"><a href="/CATEGORY-URL"><strong>Product Category Name</strong></a></h3>
- After each subsection, add an expert recommendation in this format:
  <p class="xmx--high-emphasis">– Välj en [product type] om du vill [benefit]. [Additional recommendation].</p>

### Product Recommendations:
- After each major section, add a product carousel placeholder:
  <div class="lazy-clerk" id="lazy-clerk-UNIQUE-ID"
        data-template="@mshop-2-0-TEMPLATE-NAME"
        data-labels='["LABEL"]'
        data-after-render="initializeClerkSwiper"></div>
- If you don't know the Clerk template name, use this product card format instead:
  <div class="xmx-carousel">
    <div class="xmx-carousel-container">
      <div class="xmx-carousel-elements">
        <!-- One card per product: -->
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
- Link category names to their pages: <a href="/sexleksaker/vibratorer">vibratorer</a>
- Use the EXACT URLs provided in the site URL list
- Link relevant terms naturally in body text

### Tone of Voice:
- Warm, knowledgeable, Swedish — like a trusted friend who happens to be a sexologist
- Slightly playful but respectful, never clinical or crude
- Use "du/dig" (informal Swedish addressing)
- Expert recommendations start with "– Välj en..."
- Be genuinely helpful — guide the customer to make the right choice
- Mention discreet shipping, customer service when relevant
- Use Swedish throughout

### DO NOT:
- Do NOT add <h1> — the CMS adds that
- Do NOT use generic stock photo URLs — use real product image URLs from the product data
- Do NOT use markdown — output PURE HTML
- Do NOT wrap in <html><body> tags — output only the content HTML
"""

CATEGORY_CONTENT_TEMPLATE_INSTRUCTIONS = """
## MSHOP CATEGORY PAGE HTML FORMAT

### Structure:
- Intro text in <p> tags (80-150 words, explains the category)
- Use xmx grid for layout if needed:
  <div class="xmx-section">
    <div class="xmx-page">
      <div class="xmx-title-area">
        <div class="xmx-title-area-label">Section label</div>
        <div class="xmx-title-area-title">
          <h2 class="xmx-title-area-headline">Section Title</h2>
        </div>
      </div>
    </div>
  </div>
- Bottom text with buying guide and FAQ (300-500 words)

### Tone: Same as blog — warm, knowledgeable, helpful, Swedish, "du/dig"
### DO NOT add <h1> — CMS handles that
"""
