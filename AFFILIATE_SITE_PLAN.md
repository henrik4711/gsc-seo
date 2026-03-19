# Affiliate SEO Site — Complete Build Plan

## Project Overview

Build a multi-language WordPress affiliate site that ranks for adult product keywords across 10-20 markets. All purchase traffic is sent to Mshop.se/dk/EU via affiliate links. Content is 100% AI-generated from our SEO analysis system, validated for quality, and uploaded via WordPress REST API.

**Revenue model:** Affiliate commission on every sale referred to Mshop
**Competitive advantage:** SEO-optimized from day one using our analysis pipeline — every page, link, keyword, and article is pre-validated before publish.

---

## Phase 1: Foundation (Week 1)

### 1.1 WordPress Setup

**Hosting:**
- Cloudways (DigitalOcean $28/mo) or Kinsta — fast, scalable, managed
- Separate staging environment for testing before publish
- CDN: Cloudflare free tier (caching + security)
- SSL: Let's Encrypt (automatic via host)

**WordPress config:**
- PHP 8.2+, Redis object cache, OPcache enabled
- Disable comments, pingbacks, XML-RPC
- Minimal plugins (see 1.3)

**Domain strategy (per language):**
- Option A: Subdirectories — `site.com/se/`, `site.com/dk/`, `site.com/en/` (recommended — all authority on one domain)
- Option B: Subdomains — `se.site.com`, `dk.site.com` (easier to manage separately)
- Option C: Separate domains per country (most expensive, hardest to build authority)
- **Recommendation: Option A** — one strong domain, subdirectories per language

### 1.2 Theme

**GeneratePress Pro** ($59/year) or **Kadence Pro** ($149/year)
- Lightweight (<50KB CSS), fast, SEO-friendly
- Full control over HTML output
- No page builder bloat
- Easy to customize via child theme

**Why not a premium theme?**
- Most premium themes add 500KB+ of CSS/JS we don't need
- We control the HTML structure via templates — theme just provides the shell

### 1.3 Plugins (minimal)

| Plugin | Purpose | Cost |
|--------|---------|------|
| Rank Math Pro | SEO: schema, sitemap, redirects, breadcrumbs | $59/yr |
| WPML | Multi-language (10-20 languages) | $99/yr |
| Advanced Custom Fields Pro | Custom product fields | $49/yr |
| WP All Import Pro | Bulk CSV/XML import (alternative to API) | $99/yr |
| Redirection | 301 redirect management | Free |
| ShortPixel | Image optimization (auto-compress uploads) | $4.99/mo |
| WP Rocket | Caching + performance | $59/yr |

**Total plugin cost: ~$420/year**

### 1.4 Custom Post Types

**Product CPT:**
```
Post type: 'product'
Fields (ACF):
  - product_name (text)
  - product_price (text, e.g. "299 kr")
  - product_original_price (text, for showing discount)
  - product_image (image upload or URL)
  - product_gallery (gallery field, multiple images)
  - product_description (wysiwyg)
  - product_short_description (textarea, 1-2 sentences)
  - affiliate_link (url — link to mshop.se product page)
  - affiliate_link_dk (url — link to mshop.dk)
  - affiliate_link_eu (url — link to EU store)
  - product_brand (taxonomy)
  - product_category (taxonomy — maps to our topic clusters)
  - product_rating (number, 1-5)
  - product_features (repeater: feature_name + feature_value)
  - seo_keywords (textarea — target keywords from our analysis)
  - source_url (url — original mshop.se URL for tracking)
```

**Category taxonomy:**
```
Taxonomy: 'product_category' (hierarchical)
Structure mirrors our topic clusters:
  - Sexleksaker
    - Vibratorer
      - Klitorisvibratorer
      - G-punktsvibratorer
      - Rabbitvibratorer
      - Magic Wand
    - Dildos
      - Klassisk Dildo
      - Realistisk Dildo
      - G-punkt Dildo
    - Sexleksaker för Honom
      - Masturbatorer
      - Penisringar
      - Prostatavibratorer
    - Sexleksaker för Henne
    - Sexleksaker för Par
    - BDSM
  - Apotek
    - Glidmedel
    - Kondomer
```

---

## Phase 2: Content Pipeline (Week 1-2)

### 2.1 Product Scraper

**Script: `scrape_mshop_products.py`**

Input: Mshop.se sitemap or category pages
Output: JSON/CSV with all product data

```
For each product page:
  1. Scrape: name, price, images (all), description, brand, category
  2. Download all product images to local storage
  3. Extract product features/specs
  4. Get affiliate link structure (mshop.se/PRODUCT-SLUG?ref=AFFILIATE_ID)
  5. Map to our category taxonomy

Output per product:
{
  "name": "Satisfyer Pro 2",
  "slug": "satisfyer-pro-2",
  "price": "399 kr",
  "images": ["url1.jpg", "url2.jpg"],
  "description": "Original Mshop description...",
  "brand": "Satisfyer",
  "category_path": "Sexleksaker > Vibratorer > Lufttrycksvibratorer",
  "features": [{"name": "Material", "value": "Silikon"}],
  "affiliate_url_se": "https://www.mshop.se/satisfyer-pro-2?ref=XXXXX",
  "affiliate_url_dk": "https://www.mshop.dk/satisfyer-pro-2?ref=XXXXX",
  "source_url": "https://www.mshop.se/satisfyer-pro-2"
}
```

**Volume estimate:** ~2000-5000 products depending on scope

### 2.2 AI Content Rewriting

**CRITICAL: All product texts MUST be unique — not copied from Mshop.se**

**Script: `rewrite_product_content.py`**

For each product:
1. Send original description + product data to Claude
2. Generate UNIQUE description (different structure, different words, same facts)
3. Generate SEO-optimized meta title + description
4. Generate FAQ items (2-3 per product)
5. Validate: run plagiarism check against original

**AI prompt strategy:**
```
"You are a product copywriter for a Swedish adult product review/affiliate site.
Rewrite this product description to be:
- 100% unique (NOT copied from source)
- Written as a REVIEW/RECOMMENDATION, not a store listing
- Include: who this product is for, key benefits, how to use, pros/cons
- Tone: warm, knowledgeable, helpful — like a trusted friend recommending
- Include affiliate CTA: 'Köp hos Mshop' with the affiliate link
- Language: {language}
- 200-400 words"
```

### 2.3 Category Content Generation

**Uses our existing `generate_category_bottom_text()` function**

For each category:
1. Get all subcategories and products
2. Get target keywords from our SEO analysis
3. Generate:
   - Intro text (100-150 words)
   - Buying guide H2 section (300-500 words)
   - Subcategory H3 sections with links
   - Product recommendations with real product cards
   - FAQ section (3-5 questions)
   - Trust signals
4. Total: 800-1500 words per category page

### 2.4 Article/Blog Generation

**Uses our existing `generate_full_article_html()` function**

Article types from our content roadmap:
- **How-to guides:** "Hur väljer man rätt vibrator" (from missing content analysis)
- **Comparison articles:** "Satisfyer vs Womanizer" (from keyword data)
- **Beginner guides:** "Sexleksaker för nybörjare" (from search intent)
- **Category guides:** "Bästa sexleksakerna för män 2026" (from cluster gaps)

Each article:
1. Get target keywords + related products from analysis
2. Scrape relevant products for the article
3. Generate 1500-2500 word article in Mshop HTML format
4. Include real product cards with affiliate links
5. Include internal links to category pages + other articles
6. Generate meta title + description

**Volume:** 50-100 articles for initial launch, growing over time

---

## Phase 3: WordPress Templates (Week 2)

### 3.1 Template Files to Create

```
theme/
├── single-product.php          # Individual product page
├── archive-product.php         # Category listing (product grid)
├── taxonomy-product_category.php  # Category page with bottom text
├── single-post.php             # Blog article (already exists, customize)
├── template-parts/
│   ├── product-card.php        # Reusable product card component
│   ├── product-grid.php        # Product grid layout
│   ├── affiliate-button.php    # "Köp hos Mshop" button
│   ├── breadcrumb.php          # SEO breadcrumbs
│   └── faq-section.php         # FAQ with schema markup
├── functions.php               # CPT registration, ACF fields
└── style.css                   # Minimal custom CSS
```

### 3.2 Product Page Template (`single-product.php`)

```
Structure:
- Breadcrumb (auto-generated, schema)
- H1: Product name
- Product image gallery (left) + Product info (right)
  - Price (with original price if discount)
  - Short description
  - Rating stars
  - "Köp hos Mshop →" affiliate button (prominent, branded)
  - Product features table
- Full description (AI-rewritten, unique)
- FAQ section (with FAQPage schema)
- Related products (same category)
- Internal links to category + related articles

Schema markup (auto-generated by Rank Math):
- Product schema (name, image, price, availability)
- BreadcrumbList
- FAQPage (if FAQ exists)
- Review/Rating
```

### 3.3 Category Page Template (`taxonomy-product_category.php`)

```
Structure:
- Breadcrumb
- H1: Category name
- Intro text (ACF field, AI-generated)
- Filter/sort options (by price, rating, brand)
- Product grid (responsive: 2 cols mobile, 3 tablet, 4 desktop)
  - Product card: image, name, price, rating, "Se produkt →"
- Bottom SEO text (ACF field, AI-generated 800-1500 words)
  - Buying guide
  - Subcategory links
  - Product recommendations
  - FAQ

Schema markup:
- ItemList (product listing)
- BreadcrumbList
- FAQPage
```

### 3.4 Article Template (`single-post.php`)

```
Structure:
- Breadcrumb
- H1: Article title
- Author + date + reading time
- Table of contents (auto from H2s)
- Article content (AI-generated HTML, pasted directly)
  - Product cards embedded
  - Internal links to categories + other articles
- Related articles (same topic cluster)
- CTA: "Utforska alla [category] hos Mshop"

Schema markup:
- Article
- BreadcrumbList
- FAQPage (if FAQ in article)
```

### 3.5 SEO Template Checklist

Every page type must have:
- [ ] Canonical URL
- [ ] Breadcrumb with BreadcrumbList schema
- [ ] Open Graph tags (title, description, image)
- [ ] Twitter Card tags
- [ ] Hreflang tags (all languages)
- [ ] Next/prev for paginated categories
- [ ] Proper H1 > H2 > H3 hierarchy
- [ ] Alt text on all images
- [ ] Internal links to parent, siblings, children
- [ ] Structured data validated via Google Rich Results Test

---

## Phase 4: API Upload Pipeline (Week 2-3)

### 4.1 WordPress REST API Integration

**Script: `wp_uploader.py`**

```python
# Authentication: Application Passwords (built into WP 5.6+)
# Endpoint: https://site.com/wp-json/wp/v2/

Pipeline:
1. Upload images → get attachment IDs
2. Create/update product_category terms → get term IDs
3. Create/update products with all ACF fields
4. Create/update posts (articles) with content
5. Set featured images, categories, tags
6. Update Rank Math SEO fields via API
```

### 4.2 Upload Order (dependency chain)

```
Step 1: Upload all product images
        → Store image_id mapping: original_url → wp_attachment_id

Step 2: Create category taxonomy tree
        → Store category mapping: slug → wp_term_id

Step 3: Upload products (requires image_ids + category_ids)
        → For each product:
           - Create post (type: product)
           - Set ACF fields (price, affiliate links, etc.)
           - Assign categories
           - Set featured image
           - Set Rank Math meta (title, description, focus keyword)

Step 4: Generate + upload category content
        → For each category:
           - Generate intro + bottom text via AI
           - Update category description field
           - Or create a "category landing page" as a regular page

Step 5: Generate + upload articles
        → For each article from content roadmap:
           - Generate full article with products
           - Create post
           - Set categories + tags
           - Set internal links (requires knowing other post URLs)

Step 6: Internal link validation
        → Crawl entire site
        → Run our SEO analysis pipeline
        → Fix any issues found
```

### 4.3 Incremental Updates

```
Daily/weekly sync script:
1. Check Mshop for new/updated products
2. Scrape changes
3. AI rewrite new content
4. Upload via API
5. Run SEO validation
6. Alert if issues found
```

---

## Phase 5: Multi-Language (Week 3-4)

### 5.1 Translation Strategy

**NOT just translation — LOCALIZATION**

For each language:
1. Translate all UI/template text
2. AI rewrite ALL product descriptions in target language (not translate — REWRITE for local market)
3. AI generate ALL category texts in target language
4. AI generate ALL articles in target language
5. Adjust: prices (local currency), shipping info, legal disclaimers
6. Local keyword research (what do DANES search for vs SWEDES?)

### 5.2 Language Priority (by ROI — low competition first)

**Wave 1 — Nordic (launch, week 1-2). You know the market, Mshop ships directly.**

| # | Language | Market | Population | Competition | Affiliate target |
|---|----------|--------|-----------|-------------|-----------------|
| 1 | Danish (da) | Denmark | 5.9M | Medium | mshop.dk |
| 2 | Norwegian (nb) | Norway | 5.4M | Medium | mshop.se (ships to NO) |
| 3 | Finnish (fi) | Finland | 5.5M | Low | mshop.se (ships to FI) |

**Wave 2 — Baltic (month 2). Near zero SEO competition.**

| # | Language | Market | Population | Competition | Affiliate target |
|---|----------|--------|-----------|-------------|-----------------|
| 4 | Latvian (lv) | Latvia | 1.8M | Very low | EU partner |
| 5 | Lithuanian (lt) | Lithuania | 2.8M | Very low | EU partner |
| 6 | Estonian (et) | Estonia | 1.3M | Very low | EU partner |

**Wave 3 — Central Europe (month 3). Big markets, liberal culture, low SEO competition.**

| # | Language | Market | Population | Competition | Affiliate target |
|---|----------|--------|-----------|-------------|-----------------|
| 7 | Polish (pl) | Poland | 38M | Medium | EU partner |
| 8 | Czech (cs) | Czech Republic | 10.7M | Low | EU partner |
| 9 | Hungarian (hu) | Hungary | 10M | Low | EU partner |

**Wave 4 — Southeast Europe (month 4). No competitors at all.**

| # | Language | Market | Population | Competition | Affiliate target |
|---|----------|--------|-----------|-------------|-----------------|
| 10 | Romanian (ro) | Romania | 19M | Very low | EU partner |
| 11 | Greek (el) | Greece | 10.7M | Very low | EU partner |
| 12 | Croatian (hr) | Croatia (+Serbia/Bosnia) | 4M (+11M) | Very low | EU partner |
| 13 | Slovenian (sl) | Slovenia | 2.1M | Zero | EU partner |

**Wave 5 — Western Europe (month 5-6). Big markets, harder competition.**

| # | Language | Market | Population | Competition | Affiliate target |
|---|----------|--------|-----------|-------------|-----------------|
| 14 | Spanish (es) | Spain | 47M | High | EU partner |
| 15 | Italian (it) | Italy | 60M | High | EU partner |
| 16 | French (fr) | France/Belgium/CH | 68M+ | High | EU partner |
| 17 | Dutch (nl) | Netherlands/Belgium | 24M | Medium-high | EU partner |
| 18 | German (de) | Germany/Austria/CH | 100M+ | High | EU partner |

**Wave 6 — English (month 6+). Biggest potential, hardest competition.**

| # | Language | Market | Population | Competition | Affiliate target |
|---|----------|--------|-----------|-------------|-----------------|
| 19 | English (en) | UK/Ireland/Global | 70M+ EU | Very high | EU partner |

**Swedish (sv) — special case:**
Do NOT compete with Mshop.se on their own market. Only add Swedish if Mshop specifically wants it as a content/SEO partner site.

**Total addressable population: ~500M+ across EU**

### 5.3 WPML Configuration

```
- Translation management: all content via WPML String Translation
- URL structure: /se/, /dk/, /en/, /de/ etc.
- Hreflang: automatic via WPML
- Language switcher: in header + footer
- SEO: each language gets unique meta titles/descriptions
- Sitemaps: per-language sitemaps submitted to Google
```

### 5.4 Per-Language Content Pipeline

```
For each new language:
1. Set up WPML language
2. Run keyword research for that market (Google Keyword Planner or Ahrefs)
3. Map keywords to existing category/product structure
4. AI generate ALL product descriptions (not translate — write fresh)
5. AI generate ALL category texts with local keywords
6. AI generate articles targeting local search terms
7. Upload via API with language flag
8. Run SEO analysis pipeline for that language
9. Fix issues
10. Submit sitemap to Google
```

---

## Phase 6: SEO Analysis Integration (Week 3-4)

### 6.1 Standalone Analysis Pipeline

**Branch our current system into a standalone Python script**

```
seo_pipeline/
├── analyze.py              # Main CLI script
├── config.yaml             # Site config (URL, API keys, language)
├── analyzers/
│   ├── keyword_analyzer.py    # From our topic_clusters.py
│   ├── content_validator.py   # From our category_analyzer.py
│   ├── link_checker.py        # From our internal_linking.py
│   ├── cluster_health.py      # From our cluster_health.py
│   └── page_auditor.py        # From our page_auditor.py
├── generators/
│   ├── article_generator.py   # From our ai_generator.py
│   ├── category_text.py       # Category bottom text generator
│   └── product_rewriter.py    # Product description rewriter
├── uploaders/
│   ├── wp_api.py              # WordPress REST API client
│   └── image_uploader.py      # Image upload + optimization
└── reports/
    └── report_generator.py    # HTML/PDF report of all issues
```

### 6.2 Pre-Publish Validation

**Before any content goes live, run this checklist automatically:**

```
For each page:
[ ] Meta title: 50-60 chars, contains primary keyword
[ ] Meta description: 140-160 chars, contains primary keyword, has CTA
[ ] H1: contains primary keyword, matches search intent
[ ] Content: meets word count target for page type
[ ] Keywords: all target keywords naturally integrated
[ ] Internal links: links to parent, children, siblings
[ ] Hub-spoke: links to/from pillar page
[ ] Images: all have alt text with keyword
[ ] Schema: correct type for page type
[ ] Affiliate links: working, correct destination
[ ] Canonical: self-referencing
[ ] Hreflang: points to correct language variants
[ ] No duplicate content: unique vs. Mshop.se original
[ ] No keyword cannibalization within own site
```

### 6.3 Ongoing Monitoring

```
Weekly automated script:
1. Fetch GSC data for new site
2. Run full analysis pipeline
3. Identify: new keyword opportunities, ranking drops, content gaps
4. Auto-generate new articles for uncovered topics
5. Email report with actions needed
```

---

## Phase 7: Launch & Scale (Week 4+)

### 7.1 Launch Checklist

```
Pre-launch:
[ ] All products uploaded with unique descriptions
[ ] All categories have intro + bottom text
[ ] 20-30 initial articles published
[ ] All internal links validated
[ ] Schema markup validated (Google Rich Results Test)
[ ] Sitemaps submitted to Google Search Console
[ ] Google Analytics 4 + affiliate tracking set up
[ ] Robots.txt reviewed
[ ] Page speed: Core Web Vitals all green
[ ] Mobile responsive tested
[ ] Affiliate links tested (correct tracking IDs)
[ ] GDPR: cookie consent + privacy policy
[ ] 404 page with search + popular categories

Post-launch (first month):
[ ] Monitor Google indexing (Search Console)
[ ] Track affiliate conversions
[ ] Publish 2-3 new articles per week
[ ] Monitor rankings for top keywords
[ ] Fix any crawl errors
[ ] Build initial backlinks (guest posts, directories)
```

### 7.2 Content Calendar

```
Week 1-2:  Launch Wave 1 (DK + NO + FI) with 30 articles each
Month 2:   Launch Wave 2 (LV + LT + EE) with 20 articles each
Month 3:   Launch Wave 3 (PL + CZ + HU) with 30 articles each
Month 4:   Launch Wave 4 (RO + GR + HR + SI) with 20 articles each
Month 5-6: Launch Wave 5 (ES + IT + FR + NL + DE) with 30 articles each
Month 6+:  Launch Wave 6 (EN) with 50 articles
Ongoing:   5-10 new articles per language per month based on ranking data
```

### 7.3 Revenue Projections (conservative, 12% commission)

```
Assumptions:
- 2000 products, 50 categories, 50-100 articles per language
- 12% affiliate commission
- Average order: 400-600 SEK (varies by market)
- Conversion rate: 3-5% of affiliate clicks
- Average commission per sale: ~60 SEK

Wave 1 — Nordic (DK + NO + FI):
  Month 3-6:    3,000-10,000 SEK/month
  Month 6-12:  15,000-40,000 SEK/month
  Year 2:      30,000-70,000 SEK/month

Wave 2 — Baltic (LV + LT + EE):
  Month 4-6:    1,000-3,000 SEK/month (small markets but zero competition)
  Month 6-12:   5,000-15,000 SEK/month
  Year 2:      10,000-25,000 SEK/month

Wave 3 — Central Europe (PL + CZ + HU):
  Month 5-8:    2,000-8,000 SEK/month
  Month 8-12:  15,000-40,000 SEK/month
  Year 2:      30,000-80,000 SEK/month (Poland alone is huge)

Wave 4 — Southeast (RO + GR + HR + SI):
  Month 6-9:    1,000-5,000 SEK/month
  Month 9-12:   8,000-20,000 SEK/month
  Year 2:      15,000-40,000 SEK/month

Wave 5 — Western Europe (ES + IT + FR + NL + DE):
  Month 8-12:   5,000-20,000 SEK/month
  Year 2:      40,000-120,000 SEK/month (big markets, slow start)

Wave 6 — English:
  Month 9-12:   2,000-10,000 SEK/month
  Year 2:      15,000-50,000 SEK/month

TOTAL ALL MARKETS:
  Month 6:     15,000-40,000 SEK/month
  Month 12:    60,000-150,000 SEK/month
  Year 2:      140,000-385,000 SEK/month
  Year 3:      250,000-600,000 SEK/month (compound growth)

Conservative annual income at maturity (year 2-3):
  Low estimate:   1.7M SEK/year (~170,000 EUR)
  Mid estimate:   3.5M SEK/year (~350,000 EUR)
  High estimate:  6.0M SEK/year (~600,000 EUR)
```

### 7.4 Ongoing Costs

```
Monthly:
- Hosting (Cloudways, scales with traffic):    500-2,000 SEK
- WPML (19 languages):                        ~200 SEK
- Rank Math Pro:                               ~50 SEK
- ShortPixel (image optimization):             ~50 SEK
- Claude API (content generation + updates):   1,000-5,000 SEK
- Domain + SSL:                                ~100 SEK/year
- GSC API / Ahrefs (keyword research):         ~1,000 SEK

Total: ~3,000-8,000 SEK/month
Profit margin at maturity: 95%+
```

### 7.5 Risk Factors

```
HIGH RISK:
- Google algorithm update targeting affiliate/AI sites
  Mitigation: genuine E-E-A-T signals, unique reviews, not just rewritten specs

MEDIUM RISK:
- Mshop changes affiliate terms or commission rate
  Mitigation: diversify to multiple affiliate partners per market
- Competitor enters same low-competition markets
  Mitigation: first-mover advantage + more content + better SEO

LOW RISK:
- Content quality issues (AI hallucination)
  Mitigation: pre-publish validation pipeline
- Technical downtime
  Mitigation: managed hosting with uptime SLA
```

---

## Technical Architecture Summary

```
┌─────────────────────────────────────────────────────┐
│                    DATA FLOW                         │
│                                                      │
│  Mshop.se ──scrape──→ Product Data ──AI rewrite──→  │
│                              │                       │
│  GSC Data ──analyze──→ SEO Analysis                  │
│                              │                       │
│  Keyword Research ──→ Content Strategy               │
│                              │                       │
│           ┌──────────────────┼──────────────────┐    │
│           ▼                  ▼                  ▼    │
│     Products           Categories          Articles  │
│     (unique text)      (bottom text)       (full)    │
│           │                  │                  │    │
│           └──────── WP REST API ────────────────┘    │
│                          │                           │
│                    WordPress Site                     │
│                    /se/ /dk/ /en/                     │
│                          │                           │
│              Affiliate links → Mshop.se              │
│                          │                           │
│                    Commission ← Sales                │
└─────────────────────────────────────────────────────┘
```

---

## File Inventory (what to build)

| # | File | Purpose | Effort |
|---|------|---------|--------|
| 1 | `scrape_mshop_products.py` | Scrape all products from mshop.se | 1 day |
| 2 | `rewrite_product_content.py` | AI rewrite all product descriptions | 1 day |
| 3 | `generate_category_content.py` | Generate all category texts | 1 day (mostly done) |
| 4 | `generate_articles.py` | Generate all articles from roadmap | 1 day (mostly done) |
| 5 | `wp_uploader.py` | Upload everything to WordPress via API | 2 days |
| 6 | `translate_content.py` | AI generate content for each language | 2 days |
| 7 | `wp-theme/functions.php` | Register CPT + ACF fields | 1 day |
| 8 | `wp-theme/single-product.php` | Product page template | 1 day |
| 9 | `wp-theme/taxonomy-product_category.php` | Category page template | 1 day |
| 10 | `wp-theme/template-parts/*.php` | Reusable components | 1 day |
| 11 | `seo_validator.py` | Pre-publish SEO validation | 1 day (mostly done) |
| 12 | `sync_updates.py` | Daily/weekly product sync | 1 day |

**Total: ~15 working days for first language, +3-5 days per additional language**

---

## Decision Points (before starting)

1. **Domain name** — What domain? New or existing?
2. **Affiliate agreement** — Confirm commission structure with Mshop
3. **Which markets first** — SE + DK, or start with one?
4. **Product scope** — All 2000+ products or start with top categories?
5. **Hosting provider** — Cloudways, Kinsta, or other?
6. **Budget for Claude API** — Content generation costs ~$50-200 for initial batch
7. **Legal** — GDPR compliance, affiliate disclosure requirements per country
