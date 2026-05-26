# SEO Intelligence Platform — System Description

## Purpose
Python/Streamlit-based SEO analysis tool for e-commerce sites (currently Magento 1.9, ~1,500 active SKUs). Identifies SEO problems and generates actionable recommendations based on existing content, keywords, internal linking, and topic cluster architecture.

## Architecture
- **Frontend**: Streamlit (Python)
- **AI**: Anthropic Claude Sonnet 4 (via API)
- **Hosting**: Railway with persistent /data volume
- **Data sources**: Google Search Console, Ahrefs CSV exports, Screaming Frog CSV exports, live page scraping (Playwright)

---

## Data Input — What Goes In

### 1. Google Search Console (API)
- Every query + page combination with: clicks, impressions, CTR, average position
- Typically 4,000+ queries across 1,150+ pages
- 90-day rolling window
- **URLs normalized at source**: https, no www, no params, no trailing slash, lowercase

### 2. Ahrefs (CSV exports, 3 files)
- **Best by Links**: Page-level authority (referring domains, backlinks, DR, authority score)
- **Backlinks**: Individual backlinks with source URL, anchor text, DR, dofollow/nofollow
- **Organic Keywords**: Keywords with search volume, keyword difficulty, CPC, and **search intent** (informational/commercial/transactional boolean per keyword)
- **URLs normalized at source**

### 3. Screaming Frog (CSV exports, 2 files)
- **All Pages**: Every crawled URL with status code, title, meta description, H1, word count, crawl depth, canonical URL, indexability, response time, near-duplicate matches, text-to-HTML ratio
- **All Inlinks**: Every internal link with source, target, anchor text (can be 2GB+, parsed in chunks)
- **URLs normalized at source**

### 4. Live Page Scraping (Playwright headless Chrome)
- Full rendered HTML (JavaScript executed)
- Extracts: title, meta description, H1, H2s, H3s, body text (up to 8,000 chars), internal links with anchors, external links, images without alt, schema types (JSON-LD)
- **Category pages get deep analysis**: editorial text separated into intro (above product grid) and bottom text (below grid), product count, product links, has FAQ, has buying guide
- **Screaming Frog fallback**: if Playwright crashes (common after 1000+ pages), uses SF data for title/meta/word count
- **Browser auto-restart**: detects crashed Playwright instance and restarts

---

## Analysis Pipeline — What We Check

### A. URL & Crawl Infrastructure
| Check | Method | Data Source |
|-------|--------|-------------|
| Broken links (4xx/5xx) | Status code check | SF All Pages |
| Redirect chains | 3xx detection | SF All Pages |
| Orphan pages (0 internal links) | Cross-check 4 sources: SF inlinks, SF All Pages inlink count, GSC impressions, Ahrefs backlinks | SF + GSC + Ahrefs |
| Deep pages (>3 clicks from home) | Crawl depth | SF All Pages |
| Canonical mismatches | canonical URL != page URL | SF All Pages |
| Faceted/parameter URLs | Magento 1.9 patterns: SID=, dir=, limit=, mode=, order=, p=, product_list | SF All Pages |
| Near-duplicate content | SF near-duplicate matching | SF All Pages |
| Non-indexable pages | Indexability status check | SF All Pages |
| Slow pages (>2s) | Response time | SF All Pages |

### B. Keyword & Content Analysis
| Check | Method | Data Source |
|-------|--------|-------------|
| Missing keywords | Keywords from GSC not found in page text (Unicode NFC normalized) | GSC + scraper |
| Keyword coverage % | Count of target keywords found in full text, H1, H2, intro | GSC + scraper |
| Content-cluster mismatch | Checks if >50% of ANOTHER cluster's core terms appear in page text | Topic clusters + scraper |
| Pillar spoke coverage | Checks if pillar page text mentions each spoke topic by name/terms | Topic clusters + scraper |
| Content volume | Word count against targets (pillar: 3000-5000, category: 1500-3000, blog: 1500+) | Scraper |
| AI semantic validation | Claude reads page text and evaluates if content matches the page's target topic and keywords | AI (Claude) |
| AI content quality | KEEP/IMPROVE/REWRITE verdict on 7 dimensions: helpfulness, originality, depth, readability, E-E-A-T, cluster fit, standalone value | AI (Claude) |

### C. Search Intent
| Check | Method | Data Source |
|-------|--------|-------------|
| Dominant intent per page | Template-first: page_type (category/product = transactional, blog/FAQ = informational). Ahrefs intent data as secondary signal, weighted by volume | Ahrefs organic keywords + page classifier |
| Intent mismatch detection | Flags when template intent != keyword intent (e.g., category page with informational keywords) | Combined |
| E-commerce bias | Purchase intent (transactional + commercial) weighted higher: 30%+ purchase = commercial | Ahrefs |

### D. Internal Linking
| Check | Method | Data Source |
|-------|--------|-------------|
| Outgoing links + anchors | From page scrape | Scraper |
| Incoming links + anchors | From SF link map | SF All Inlinks |
| Hub → spoke links | Checks if hub links to all spoke pages | Cluster data + link map |
| Spoke → hub backlinks | Checks if spokes link back to hub | Cluster data + link map |
| Horizontal spoke ↔ spoke | Checks sibling cross-linking within cluster | Cluster data + link map |
| Missing cluster crosslinks | Pages in same cluster not linked | Topic clusters + scraper |
| Links to REMOVE | Links pointing outside topic cluster + URL hierarchy flagged for removal | Topic clusters + scraper |
| Anchor text quality (outbound) | Checks if anchors contain cluster terms | Scraper + clusters |
| Anchor text quality (inbound) | Descriptive vs generic vs empty anchor stats | SF link map |
| Anchor-cluster relevance | Checks if inbound anchors contain page's target keywords | SF link map + GSC |

### E. Topic Clusters
| Check | Method | Data Source |
|-------|--------|-------------|
| Cluster building | AI-powered grouping of GSC queries into topic clusters | AI (Claude) + GSC |
| Hub page identification | Shallowest URL in cluster | URL structure |
| Cannibalization detection | Multiple pages ranking for same query, with brand keyword filtering | GSC |
| Cannibalization resolution | Intent-aware: different intents = "don't merge", same intent = redirect recommendation with backlink-informed winner selection | GSC + Ahrefs + URL pattern |
| Cluster health | AI evaluates entire cluster: hub quality, spoke coverage, linking completeness, keyword distribution, cannibalization | AI (Claude) |

### F. Meta & Technical SEO
| Check | Method | Data Source |
|-------|--------|-------------|
| Meta title quality | Length (50-60 chars), keyword presence, CTA signals | Scraper |
| Meta description quality | Length (140-160 chars), keyword presence, CTA/USP | Scraper |
| Meta score (0-100) | Weighted scoring of title + description issues | Scraper |
| Schema types present | JSON-LD parsing (@type detection) | Scraper |
| Missing schema | BreadcrumbList, FAQ, Organization, AggregateRating | Scraper |

### G. E-E-A-T & Trust
| Check | Method | Data Source |
|-------|--------|-------------|
| Schema trust signals | BreadcrumbList, FAQ, Organization, AggregateRating presence | Scraper |
| Author attribution | HTML class/meta author detection | Scraper |
| Freshness/date | Last modified header or meta tag | Scraper + SF |
| AI E-E-A-T evaluation | Claude evaluates: experience, expertise, authority, trust signals in content | AI (Claude) |
| AI recommends trust elements | FAQ section, buying guide, expert voice, reviews when missing | AI (Claude) |

---

## AI Usage — Where Claude Is Involved

| Function | What AI Does | Model | Tokens |
|----------|-------------|-------|--------|
| Topic clustering | Groups 4000+ GSC queries into 20-40 topic clusters | Sonnet 4 | 8000 |
| Content quality assessment | KEEP/IMPROVE/REWRITE verdict per page (batch of 5) | Sonnet 4 | 3000 |
| Implementation plan | Step-by-step SEO plan per page with time estimates | Sonnet 4 | 3000 |
| Cluster health | Evaluates entire cluster: linking, gaps, cannibalization | Sonnet 4 | 4096 |
| Category bottom text | Generates CMS-ready HTML with E-E-A-T, FAQ, products, internal links | Sonnet 4 | 6000 |
| Blog article | Full article with product recommendations, expert voice | Sonnet 4 | 8000 |
| Meta suggestions | 3 variants of optimized title + description | Sonnet 4 | 2000 |
| Content audit | Keyword gap analysis with structure recommendations | Sonnet 4 | 2000 |
| Site validation | Overall site architecture health score | Sonnet 4 | 3000 |
| Ideal structure | Redesigned cluster architecture with merge/delete/create | Sonnet 4 | 4000 |
| Keyword filtering | AI filters keywords by relevance to specific page | Sonnet 4 | 1500 |

### Anti-hallucination rules
All AI prompts that assess page state include mandatory rules:
- Must base claims ONLY on provided data
- Must quote actual values ("Title is 45 chars") not invent problems
- If title/meta/content exists in data, must NOT say "missing"
- Must read page text before assessing content quality
- Fragment flag shown when AI sees partial text

### AI prompt data completeness
Implementation plan prompt receives:
- URL, page type, title, meta description, H1, H2s, word count
- Up to 4000 chars of page text (was 1500, increased for pillar pages)
- Fragment flag when text is truncated
- All GSC keywords + Ahrefs keywords with volume
- Missing keywords + missing topic sections
- Links to REMOVE (unrelated cluster links)
- Search intent (template-first) with mismatch flag
- Existing internal links with anchors
- Inbound anchor quality stats (descriptive/generic/empty)
- Meta score, content score, AI quality verdict
- Impressions, lost clicks, position
- Referring domains, backlinks, authority score
- Category-specific: intro/bottom word count, product count, FAQ, buying guide
- Topic cluster context (pillar/spoke role, child pages, siblings)
- Data quality warnings (when scrape is incomplete)
- All site URLs (for AI to use exact URLs in link recommendations)

### Prompt rules (18 rules)
1. Content-topic alignment evaluated FIRST
2. Keyword relevance (strict per-page)
3. No duplicate keyword recommendations
4. Internal links: BOTH add AND remove
5-6. Meta title/description requirements
7. Meta always shown first if needs improvement
8. Schema type appropriateness
9. Honest assessment (don't invent problems)
10. Time estimates per step
11. Specific content placement instructions
12. New article suggestions for uncovered topics
13. Thin/off-topic content rewrite guidance
14. Backlink recommendations when authority gap exists
15. Cluster context (pillar/spoke role)
16. E-E-A-T recommendations
17. Search intent alignment check
18. PROTECT high-ranking pages (position 1-3 = incremental only)

---

## Output — What We Recommend

### Per-page implementation plan
- Primary keyword identification
- Meta title + description (optimized or "current OK")
- Step-by-step actions with time estimates (meta, content, links, schema, structure)
- Specific text to add, which H2 section, where on page
- Links to add (with exact URLs from site)
- Links to REMOVE (outside topic cluster)
- New content to create (blog/guide/FAQ with target keywords)
- Sections to rewrite (with problem description + suggested angle)

### Generated content
- Category bottom text: CMS-ready HTML with E-E-A-T, FAQ, buying guide, product carousels, internal links
- Blog articles: Full HTML with expert recommendations, product cards, internal links
- All content uses exact product data (names, prices, images, URLs)
- All internal links use real URLs from site (never invented)

### Cannibalization resolution
- Brand keywords filtered out (domain name + navigational queries)
- Intent-aware merge advice:
  - Different intents (blog vs category) = "don't merge, differentiate + cross-link"
  - Homepage involved = "never redirect to homepage"
  - Same intent = KEEP/REDIRECT recommendation with backlink-informed winner
  - Step-by-step merge instructions

### Crawl/indexation issues
- Broken links, redirect chains, orphan pages (severity classified)
- Canonical mismatches, faceted URLs (Magento 1.9 specific)
- Near-duplicate content with consolidation advice
- Non-indexable pages, thin pages, deep pages, slow pages

---

## Known Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| Clusters based on GSC queries only | Pages not ranking are invisible to clustering | Ahrefs keywords sent as supplement |
| AI is non-deterministic | Same page may get slightly different recommendations | JSON output format, could add temperature=0 |
| No NLP semantic understanding | Keyword matching is string-based, not meaning-based | AI semantic validation as second layer |
| Playwright can crash on Railway | Some pages fail to scrape | Auto-restart + SF data fallback |
| Body text capped at 4000/8000 chars | Long pillar pages partially analyzed | Fragment flag warns AI and user |
| No conversion/revenue data | Can't weight pages by business value | Uses impressions + clicks as proxy |
| Self-referencing clusters | System builds and evaluates own clusters | Recommendation: define clusters manually, system evaluates |

---

## Technical Details

### URL Normalization
Single canonical function applied at ALL data entry points:
- https (never http)
- Removes www
- Strips ALL query params and fragments
- Strips trailing slash
- Lowercase
- Applied when loading: GSC, Ahrefs, SF, scraper, persistence from disk

### Data Persistence
- All data saved to Railway /data volume as CSV (DataFrames) and JSON
- AI results cached as individual files in /data/ai_cache/
- URL columns re-normalized on every load from disk
- Bundled data shipped as .gz in git, auto-decompressed on first deploy

### Memory Efficiency
- SF All Inlinks (2.4 GB) parsed in 200K-row chunks
- Deduplicates source→target pairs on the fly
- Link map deduplicates to unique pairs only
- Result: 5.3M rows → ~870K unique pairs
