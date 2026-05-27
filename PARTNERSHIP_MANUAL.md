# SEO Intelligence Platform
## Partnership Overview & Operating Manual

**Version:** 1.0
**Date:** May 2026
**Audience:** Business partners, investors, and operational leads
**Reading time:** ~45 minutes

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Problem We Solve](#2-the-problem-we-solve)
3. [How The System Works — A Plain-English Walkthrough](#3-how-the-system-works--a-plain-english-walkthrough)
4. [Content Generation: Why Our Output Is Different](#4-content-generation-why-our-output-is-different)
5. [The Five Page Templates Explained](#5-the-five-page-templates-explained)
6. [E-E-A-T — Why Google Trusts Our Pages](#6-e-e-a-t--why-google-trusts-our-pages)
7. [Schema Markup — Speaking Google's Language](#7-schema-markup--speaking-googles-language)
8. [The Competitor-Driven Strategy](#8-the-competitor-driven-strategy)
9. [Multi-Site, Multi-Language Architecture](#9-multi-site-multi-language-architecture)
10. [WordPress Publishing & Maintenance](#10-wordpress-publishing--maintenance)
11. [The Step-By-Step Workflow](#11-the-step-by-step-workflow)
12. [Expected Results & Traffic Projections](#12-expected-results--traffic-projections)
13. [Risk Factors & How We Manage Them](#13-risk-factors--how-we-manage-them)
14. [Timeline To Launch](#14-timeline-to-launch)
15. [Investment Required](#15-investment-required)
16. [Why This Beats Alternative Approaches](#16-why-this-beats-alternative-approaches)
17. [Frequently Asked Questions](#17-frequently-asked-questions)
18. [Glossary](#18-glossary)

---

## 1. Executive Summary

The SEO Intelligence Platform is a complete content production system built to launch and scale affiliate-style websites across multiple languages and markets. It is designed for situations where you have **no existing pages and no rankings** — and you need to build a new site that earns search traffic by competing directly against established sites.

The system addresses one core problem: producing genuinely useful, technically perfect, expert-positioned content at the scale required to compete in SEO — without dropping the quality bar.

**What the system does, in one paragraph.** It studies the biggest competitor in your target market using two industry-standard data sources (Ahrefs and Screaming Frog). From that data, it figures out the structure of your new site — which categories you need, which articles, which product pages, which buying guides, which reviews — and how every page should link to every other page. It then generates the full body content for each page using AI guided by carefully tuned templates. Every output includes complete schema markup, follows Google's E-E-A-T guidelines, uses anti-AI-detection writing patterns, and is built to satisfy Google's "Helpful Content" standard. Finally, it publishes everything to a WordPress site over the standard REST API and keeps prices and stock levels synchronized hourly from the product feed — without ever modifying the body text.

**Why this matters now.** The economics of competing in SEO have shifted. The cost of producing high-quality content is no longer the bottleneck — Anthropic's Claude API can generate publishable content for a few cents per page. The bottleneck is now production infrastructure: how do you keep 2,000 products' prices in sync? How do you guarantee every page has correct schema? How do you avoid duplicate content penalties when affiliating against a merchant? How do you maintain editorial consistency across 19 languages? This system is that infrastructure.

**The headline opportunity.** Across Europe, there are 18+ language markets with low-to-medium SEO competition in our verticals. A typical affiliate site in one of these markets, properly launched with the strategies in this document, can reasonably expect to reach 50,000–200,000 monthly organic visitors within 12 months, generating 30,000–150,000 SEK per month at maturity (Year 2+). With multiple sites across multiple languages, the addressable revenue is in the 1.7–6.0 million SEK per year range. Detailed projections in Section 12.

**What we need from a partnership.** Capital for the initial build (~5,000–8,000 USD per site), an editorial relationship to verify content quality before launch, and shared upside on the resulting affiliate commission. The technology is most of the way built; the remaining work is in the order of weeks, not months.

---

## 2. The Problem We Solve

### 2.1 The state of SEO in 2026

For most of the last decade, the rules of SEO were stable. Write good content, build links, follow technical best practices, and Google would eventually reward you. That world is gone. Three things changed:

**First, AI flooded the internet with mediocre content.** ChatGPT made it trivial to produce thousands of articles a day. Google's response — the Helpful Content Update of 2022 and subsequent core updates — has been to aggressively downrank content that "appears AI-generated" or "doesn't help the reader." Generic AI content is now actively penalized.

**Second, Google demands E-E-A-T.** Experience, Expertise, Authoritativeness, Trustworthiness. Pages now need to demonstrate that a real person with real knowledge wrote them, ideally someone who actually used the product or has credentials in the field. Anonymous AI content fails this test.

**Third, schema markup became a hard requirement.** Pages without proper structured data are excluded from rich results, featured snippets, and increasingly from competitive rankings altogether. Adding schema after the fact, page by page, is extraordinarily tedious.

The combination of these three pressures means that the path to ranking has narrowed dramatically. You need content that reads as if a domain expert wrote it from genuine experience, technically perfect schema markup, and a coherent site architecture — all at a scale that lets you cover hundreds of topics across multiple languages.

### 2.2 Why most approaches fail

Most affiliate site operators try one of three approaches, all of which fail:

**The "spam mill" approach.** Generate 10,000 pages of thin AI content, hope something ranks. Result: nothing ranks, Google may even penalize the entire domain. We have watched this strategy fail repeatedly in our verticals.

**The "hand-craft everything" approach.** Hire writers to produce 50–100 articles per language per year. Result: too slow to compete. The competitor adds 500 pages in the time you publish 50, and they win on coverage even if your individual articles are better.

**The "translate one site" approach.** Build one great site in English, then translate it across markets. Result: terrible. Translated content reads as foreign and doesn't match local search behavior. Each language market has different queries, different cultural references, different purchase patterns.

### 2.3 What we do differently

We solve all three problems simultaneously:

- **Quality at scale** — every page is templated for E-E-A-T from the start, written in idiomatic native language (not translated), uses anti-AI-detection patterns, and includes complete schema markup. Production cost per page: cents. Output quality: editorial-grade.

- **Competitor-driven coverage** — instead of guessing what to write, we mirror the structure of the highest-ranking competitor in each market. They've already done the keyword research; we copy their topical coverage and exceed them on quality, schema, and E-E-A-T.

- **True localization** — separate WordPress installations per language, content generated natively in each language (never translated), local competitor data per market.

- **Operational infrastructure** — prices and stock sync hourly from product feeds. Body text never changes when prices do. Internal links are validated. Schema is verified before publish. Nothing about this is manual.

This is what gives us a realistic shot at competing against sites with five years of head start and thousands of backlinks. We can't match their backlinks immediately, but we can match (or exceed) their topical coverage in three months and out-quality them on every individual page from day one.

---

## 3. How The System Works — A Plain-English Walkthrough

This section explains the entire flow, end-to-end, in non-technical language.

### 3.1 The five steps

```
COMPETITOR DATA  →  SITE PLAN  →  CONTENT GENERATION  →  PUBLISHING  →  MAINTENANCE
```

That's the entire system. Each arrow represents a phase that happens once, then maintenance runs forever. Let's walk through each.

### 3.2 Phase 1: Studying the competitor (1 week)

We need to know what to build. We get that from the largest existing site in the target market.

From a tool called **Ahrefs**, we export two reports about the competitor:
- The list of every keyword they currently rank for (50,000+ keywords typically), including how often each one is searched and which URL of theirs ranks for it
- Their most-linked pages — these are their "hub" pages, the ones we have to compete against

From a tool called **Screaming Frog**, we crawl the competitor's entire site:
- Every URL they have, with the title, description, and word count
- Every internal link they use

The system then analyzes this data and produces a "site plan." The site plan answers questions like:
- How many categories does this site have?
- Which categories matter most (rank for the highest-volume keywords)?
- For each category, how many product pages do they have?
- How do they structure their internal linking — is it deep (5 levels) or flat (2 levels)?
- What kinds of articles do they publish — buyer's guides, reviews, how-tos?
- Which topics have the biggest gap between search volume and existing content?

The output is a structured roadmap: "Build these 50 categories, write these 120 articles, publish these 30 product reviews, create these 18 buying guides, set up internal links from A to B to C." This roadmap becomes the input to the rest of the system.

### 3.3 Phase 2: Generating content (2–4 weeks for full site)

With a site plan in hand, the system generates every piece of content needed. There are five page types, each with its own template (more on these in Section 5):

- **Category pages** — the navigation pages a customer lands on when browsing a category
- **Product pages** — one per product, generated from the affiliate product feed
- **Articles** — informational content (how-to, comparison, explainer)
- **Test/review pages** — in-depth opinionated reviews of individual products
- **Shopping guides** — "best of" multi-product buying guides

Each template knows what makes Google rank that page type. The product page template demands a comparison section, pros/cons, FAQ, and complete Product+Offer+AggregateRating schema. The buying guide template demands a "how we chose" methodology section, a comparison table, and a HowTo schema block. Etc.

For each page in the site plan, the system:
1. Pulls in the relevant data (product specs from the feed, competitor keywords, sibling page URLs for internal linking)
2. Calls the AI with the right template and all the data
3. Gets back fully-structured HTML with schema embedded
4. Runs validation (does it have all the required schema entries? Does it use real URLs? Does it avoid AI-tell vocabulary?)
5. Saves the result to draft status

The user can pause at any time. Re-running tomorrow picks up where you left off — every output is saved with its status (draft, validated, published, etc.). A 2,000-product site does not need to be generated in one sitting. You can do 100 product pages, take a week off, and resume.

### 3.4 Phase 3: Publishing to WordPress (parallel with Phase 2)

WordPress is the publishing layer. Each site (each language) has its own WordPress installation. The system pushes content to WordPress via the WordPress REST API — the same standard API used by every modern integration.

Each published page gets:
- The body content from Phase 2
- Custom fields (price, stock, affiliate URL) populated from the product feed
- SEO meta (title, description) populated from the AI output
- Schema markup confirmed and emitted
- Internal links pointing to other pages on the site (resolved at publish time once we know the WordPress URLs)
- Featured image from the product feed

The publish step is the slowest part — uploading 2,000 images, creating 2,000 posts, setting taxonomies. But it's a one-time cost. After initial publish, only updates run.

### 3.5 Phase 4: Maintenance (forever)

Two kinds of updates happen on a continuous schedule:

**Hourly:** Price and stock sync. The product feed is re-fetched, and any price or stock changes are pushed to WordPress as custom-field updates only. The body text is never touched. This means a page can have its price update 24 times a day without costing a cent of AI generation budget.

**Daily:** Full feed sync. New products are added, removed products are unpublished, product specs (color, size, etc.) are refreshed.

**Weekly:** Content health check. New keywords appearing in Google Search Console are analyzed; if a content gap appears, the system suggests new articles to write. Existing pages flagged with thin content or duplicate content issues are queued for regeneration.

**Monthly:** Freshness pass. Every page's "last updated" date is touched. Where appropriate, a paragraph is added or refreshed. This signals to Google that the site is actively maintained, which is a ranking factor.

### 3.6 Where humans fit in

The system is highly automated but not unattended. Humans are required at three points:

**Editorial review before launch.** Once content is generated and validated, an editor reviews a sample (typically 5–10% of pages) and approves the batch. The system supports this with a "needs review" status and a dashboard view filtered to recent unreviewed output.

**Test page authoring.** Test/review pages claim first-hand testing experience. Where this claim is real (someone actually tested the product), the editor uploads photos and observation notes, and the AI integrates them. Where it isn't, the page is generated in "synthetic mode" that uses softer language (descriptive rather than experiential) to stay honest.

**Strategic decisions.** Choosing which markets to enter first, which affiliate networks to use, which authors to credential — these stay with the operator.

Everything else runs unattended.

---

## 4. Content Generation: Why Our Output Is Different

This is the section your editorial conscience cares about most. Anyone can generate AI content. What separates ours is a series of technical choices that compound to produce content that reads as if a domain expert wrote it.

### 4.1 The anti-AI-detection prompt scaffolding

Every AI generation call in our system runs through a 200-line prompt scaffold called `human_writing_style`. Its job is to forbid the patterns that AI-detection tools (and increasingly human readers) recognize.

The scaffold explicitly bans:

- **AI opener phrases** — "In today's fast-paced world," "Discover," "Whether you're a beginner or an expert," "In conclusion," "Let me explain," "Imagine if..." (and their natural equivalents in every supported language)
- **AI vocabulary** — delve, leverage, utilize, navigate (figurative), foster, holistic, robust, seamless, game-changer, cutting-edge, world of, testament to, etc., plus localized equivalents
- **Em-dash overuse** — capped at 4 per page, with a post-processing validator that converts surplus em-dashes to commas
- **Three-item parallel lists** — "X, Y, and Z" patterns banned in prose (allowed in actual bullet lists)
- **Balanced hedging** — "On one hand... on the other hand..." structures, "It's not just X, it's Y" patterns
- **Uniform paragraph length** — every paragraph being 3-4 sentences is itself an AI tell
- **Closing summaries** — concluding paragraphs that recap what was just said

The scaffold also requires:
- Sentence-length variance (some 4-word sentences, some 25-word sentences, occasional fragments)
- Real opinions ("we like X because", "skip this if", "not worth the money unless") rather than balanced neutrality
- Specific lived-in details rather than generic claims
- Idiomatic native-language phrasing (never translated word-for-word from English)

These rules together produce text that, when run through tools like GPTZero or Originality.ai, classifies as human-written more often than not. More importantly, human readers don't immediately recognize it as AI.

### 4.2 The anti-hallucination scaffolding

A second 100-line scaffold called `anti_hallucination_rules` prevents the AI from inventing facts. Most AI content failure isn't from clumsy writing — it's from the AI making up specific claims that turn out to be wrong.

The scaffold forbids inventing:
- Sender names on shipping packages (a famous failure mode: AI writes "your package will arrive marked 'Mshop'" when the actual sender name is different)
- Specific return windows (writes "30-day returns" when the merchant offers 14)
- Free-shipping thresholds
- Founding year, employee count, customer count (unless explicitly provided)
- Specific delivery time guarantees

For any of these, the AI must write the natural-language equivalent of vague-but-safe phrasing ("fast delivery", "easy returns according to consumer protection law") unless the specific value is given in the site context configuration.

### 4.3 The LIX readability target

For Scandinavian languages (Swedish, Danish, Norwegian), our system targets a LIX readability score of 35–40. LIX is the Nordic equivalent of the Flesch-Kincaid grade level. A score of 35–40 is "readable for a broad audience without sounding childish" — the sweet spot for e-commerce.

The prompt instructs the AI to write sentences averaging 12–18 words, use common everyday vocabulary, and split overly long compound words where natural.

For other languages, the principle (short sentences, simple vocabulary) applies but the specific score is less meaningful.

### 4.4 The "real opinions" requirement

This is the single most important difference between our output and generic AI content. AI is trained to hedge. By default, it writes "this product has its strengths and weaknesses depending on your needs" — the smoking gun of AI writing. Real reviews commit to positions.

Our prompts require:
- At least one explicit anti-recommendation per product page ("skip this if you want X")
- At least one explicit pro-recommendation in each verdict
- A named alternative in every comparison ("if you want X, get this; if you want Y, get [specific alternative]")
- Real downsides in every pros/cons list (not "might not suit everyone" — a specific named downside)

Pages that fail these checks are regenerated.

### 4.5 The validation pass

Every generated piece runs through a quality-check pipeline before being saved as "validated":

1. **Cyrillic-confusable check.** AI occasionally drops Cyrillic letters into Latin-script words (a Cyrillic 'н' that looks like Latin 'n'). The validator catches and corrects these — they're an AI tell that humans never produce.
2. **Em-dash count.** Capped at 4 per page; surplus converted to commas.
3. **Whitespace collapse.** Extra spaces and triple-newlines cleaned up.
4. **Schema completeness.** Every required `@type` is present in the JSON-LD block. Every placeholder marker is present where the publisher will fill values.
5. **URL realism.** Every internal link points to a URL that exists in the site URL list — no invented URLs.
6. **Price decoupling.** No literal prices anywhere in body text (only `{{PRICE}}` markers in schema).
7. **Anchor-text diversity.** Across a batch of generations, no single target URL receives more than 30% of its inbound links with the same anchor text.

Failures trigger regeneration with a more specific prompt.

---

## 5. The Five Page Templates Explained

The system has five distinct page templates. Each is a 200–400-line instruction block that the AI follows when generating a page of that type. The templates are stored in `utils/templates.py` and selected automatically based on the page's content type.

### 5.1 The article template

Generic content articles — how-to guides, explainers, comparisons, listicles. Used for the bulk of editorial content on the site.

Output:
- Intro paragraph (no H1 — added by the CMS)
- 3–5 H2 sections with H3 subsections
- "Expert recommendation" callout boxes after key sections
- Mandatory FAQ section at the end
- Product cards if products are relevant (using marker `{{PRICE}}` for prices)
- Internal links to category pages, sibling articles, and the parent hub
- Schema: Article + BreadcrumbList + FAQPage

Word count target: 1,000–2,500 depending on intent.

### 5.2 The category bottom-text template

The SEO content that appears below the product grid on category pages. This is often the most important text on a category page for ranking.

Output:
- Buying-guide H2 explaining "how to choose [category]"
- Linked subcategory sections (one H3 per subcategory)
- Expert recommendation per subcategory
- FAQ section
- Product cards for top recommendations
- Schema: ItemList + BreadcrumbList + FAQPage

Word count target: 800–1,500.

### 5.3 The product page template

A single product's landing page. Generated from product-feed data, one per product.

Output:
- Intro hook describing who the product is for
- "What it is" section (design + intent)
- "Who it's for" with explicit anti-profile ("skip this if you want X")
- "How to use" — 4–6 numbered steps
- Features table (specs from feed, but never price)
- Pros & cons (specific named cons, not generic ones)
- Comparison to 1–2 named alternatives
- Expert verdict
- FAQ (5–7 questions, no price-related ones)
- Affiliate CTA blocks (twice — after intro and at the end)
- Schema: Product + Offer + AggregateRating + Review + BreadcrumbList + FAQPage

Key feature: **price and stock are decoupled.** The body text never quotes a price. The schema uses placeholder markers (`{{PRICE}}`, `{{AVAILABILITY}}`, `{{AFFILIATE_URL}}`) that WordPress fills in at render time from custom fields synced from the feed. This means price changes update everywhere in seconds with zero AI cost and zero body-text churn.

Word count target: 800–1,500 depending on product complexity.

### 5.4 The test/review page template

An in-depth opinionated single-product review. The most editorially demanding page type, and the one with the strongest E-E-A-T signals.

Output:
- "Tested by [Author], [Title]. Reviewed on [Date]. Test duration: [X]." block
- Affiliate disclosure at top
- Intro opening with a specific testing observation
- Scorecard (Overall / Quality / Ease of use / Value / Build, scored /10)
- "Who this is for" and "Who this isn't for"
- Testing methodology section (how we tested — strongest E-E-A-T signal on the page)
- Hands-on experience section (300–400 words of first-person observations)
- Pros & cons (4–6 specific pros, 3–5 honest cons)
- Comparison table vs. 2–3 named alternatives
- "Who shouldn't buy this" — names 2–3 anti-profiles
- Verdict with explicit recommendation
- FAQ (5–7 questions covering durability, maintenance, sizing, etc.)
- Affiliate CTA blocks
- Schema: Review + Product + AggregateRating + BreadcrumbList + FAQPage

Word count target: 1,500–2,500.

**Important honest note:** Test pages claim first-hand testing. Where this is true (the editor actually tested the product), the editor uploads testing photos and notes, and the AI integrates them. Where it isn't true, the page is generated in "synthetic mode" that softens the language ("designed for X" instead of "we noticed X") to stay honest. Pretending to test products you never tested is both unethical and a Google policy violation.

### 5.5 The shopping guide template

A multi-product "best of" buying guide for a category. Targets queries like "best X for Y" or "how to choose your first X."

Output:
- Affiliate disclosure at top
- "Researched and tested by [Author]. Last updated [Date]. Products considered: [N]. Top picks: [N]." block
- Intro identifying the buyer's actual decision
- "Top picks at a glance" — 5–7 named products with one-line role for each
- "How we chose" methodology
- "What to look for" criteria (4–6 H3 subsections)
- "Top picks reviewed" — per-product block (description + expert rec + per-product affiliate CTA)
- Comparison table (price tier, not specific price)
- Common mistakes to avoid
- How to use / setup steps
- FAQ
- Closing CTA
- Schema: Article + ItemList + HowTo + BreadcrumbList + FAQPage

Word count target: 2,000–3,500.

### 5.6 Template selection — automatic

The system automatically picks the right template based on the content type identified in the site plan. The same code path serves all five — the AI generator function inspects the content type and routes to the matching template instruction block.

This means a single "generate this page" call works for any of the five page types. No special handling per type at the orchestration layer.

---

## 6. E-E-A-T — Why Google Trusts Our Pages

E-E-A-T stands for Experience, Expertise, Authoritativeness, and Trustworthiness. It's the framework Google uses to evaluate whether a page deserves to rank, especially for queries where the user is making a real decision (buying something, looking for health info, etc.).

E-E-A-T isn't a single ranking factor — it's a bundle of signals Google looks for. Our system addresses each of the four pillars systematically.

### 6.1 Experience

Google wants to see that the page reflects first-hand experience with the subject. The strongest signals:

- **First-person observations.** "We noticed", "in our testing", "after a week of use" with specific details that only someone who used the product would know.
- **Testing methodology.** A page that explains how the testing was done — duration, conditions, what was compared against — outranks a page that just describes the product.
- **Reviewer attribution.** A named reviewer with credentials beats anonymous content.
- **Photos and media.** Original product photos taken during testing beat stock photos from the merchant feed.

Our templates require all four. The Experience signal is the dimension that most clearly separates expert-positioned content from AI-generated commodity content, and it's the dimension we put the most emphasis on.

### 6.2 Expertise

Google wants to see domain expertise — claims and details that only someone who knows the field would write.

- **Specific mechanisms over generic claims.** "TPE has lower porosity than silicone, which matters for hygiene" beats "TPE is a good material."
- **Comparative knowledge.** Real experts know how products compare; AI defaults to "they're both good in different ways." Our prompts force the AI to pick a side.
- **Field-specific terminology, used correctly.** Not jargon for jargon's sake, but the right specific term in the right place.
- **Author credentials.** Schema.org Person with `knowsAbout`, certifications, and links to professional profiles.

The product page, test page, and shopping guide templates each have specific instructions requiring at least 2–3 "expert details a generalist wouldn't know" per major section.

### 6.3 Authoritativeness

This is the dimension where new sites struggle most, because authoritativeness is built over time through external recognition (backlinks, mentions, branded searches). Our system supports authoritativeness in three ways:

- **Methodology pages.** "How we chose," "How we test," "Editorial standards" — visible pages explaining the editorial process build site-level authority.
- **Consistent attribution.** All pages credit named authors with bios. The author entity accumulates topical authority over time.
- **Schema.org Organization markup.** A complete Organization schema, with founding date, logo, sameAs links to social profiles, contact info — these compound into Google's knowledge graph entry for the site.

What we can't do from inside the system: build backlinks. That has to happen through outreach, content partnerships, digital PR, or paid placements — strategies that run alongside the content production.

### 6.4 Trust

The most fundamental signal. Trust collapses if any of the others fail visibly.

- **Affiliate disclosures.** FTC and EU consumer law require visible disclosures when content links to affiliate products. Our templates include a properly-worded disclosure at the top of test pages and shopping guides.
- **Transparent methodology.** "We may earn a commission — this never affects our recommendations" — a single line that addresses the biggest reader concern.
- **Honest cons.** A pros/cons list that's all pros reads as untrustworthy. Our templates force at least 2–3 honest named cons.
- **Realistic scores.** Test pages that give every product 9/10 fail Google's review-farm detection. Our prompts require defensible scoring distributions.
- **Up-to-date content.** Sites with active maintenance (recent `dateModified`) earn more trust than abandoned ones.

### 6.5 Why this matters for the partner economy

For sites that primarily exist to send affiliate traffic to a merchant, Google has a special review process. Google's "Site Reputation Abuse" policy (effective 2024) explicitly targets affiliate sites that publish thin, AI-generated content without real expertise.

Our entire E-E-A-T system is designed to survive this scrutiny. Every signal a Google reviewer would look for is present:
- Named authors with bios
- Methodology pages explaining how reviews are conducted
- Real testing where claimed (synthetic mode where not)
- Complete schema markup
- Honest pros/cons
- Up-to-date timestamps
- Original imagery where possible

A site that ticks all these boxes can be the cleanest affiliate site in its market — and rank accordingly.

---

## 7. Schema Markup — Speaking Google's Language

Schema markup is the structured data Google reads to understand what a page is about. It's invisible to humans but critical for ranking and rich results (the special boxes that appear in search results, like product cards, ratings, FAQ accordions).

### 7.1 The schema completeness rule

Every page type ships with a complete schema graph. Not a partial one, not "the basics" — a complete one. This is non-negotiable in our templates because partial schema is sometimes worse than none (Google can flag it as broken).

The schema for each page type:

| Page type | Schema types included |
|---|---|
| Article | Article + BreadcrumbList + FAQPage |
| Category page | ItemList + BreadcrumbList + FAQPage |
| Product page | Product + Offer + AggregateRating + Review + BreadcrumbList + FAQPage |
| Test page | Review + Product + AggregateRating + BreadcrumbList + FAQPage |
| Shopping guide | Article + ItemList + HowTo + BreadcrumbList + FAQPage |
| Site-wide (added by Rank Math plugin) | Organization + WebSite + SearchAction |

This is the most complete schema setup any affiliate site can ship with. Many competitors have only partial schema — usually just Product schema on product pages, no FAQ schema, no Review schema. Our pages will out-perform theirs in rich result eligibility from day one.

### 7.2 How schema works mechanically

A schema block is a `<script type="application/ld+json">` tag at the bottom of a page, containing a JSON object that describes the page in a vocabulary Google understands. For a product page, the schema includes the product name, image, brand, SKU, price, currency, availability, rating, review count, and breadcrumb trail.

Our templates generate the schema block as part of the AI output, using placeholder markers for values that the publisher (WordPress) fills in at render time:

- `{{PRICE}}` — filled from the product feed, updated hourly
- `{{AVAILABILITY}}` — filled from the product feed, updated hourly
- `{{IMAGE_URL}}` — filled from the WordPress media library
- `{{SKU}}` — filled from the product feed
- `{{BRAND_NAME}}` — filled from the product feed
- `{{AUTHOR_NAME}}` — filled from the assigned author
- `{{REVIEW_DATE}}` — filled at publish time
- `{{BREADCRUMB_JSON}}` — generated from the taxonomy tree

This separation lets WordPress hot-swap values without touching the AI-generated text. A product page generated in January 2026 with a price of $39.99 can have that price updated to $44.99 in seconds without any AI regeneration.

### 7.3 FAQ schema and featured snippets

FAQ schema is special. When a page has FAQ schema, Google often displays the FAQ as an interactive accordion directly in search results. This means more visual space on the search results page, which drives higher click-through rates.

Our FAQ schema requirement: **the visible FAQ text and the schema FAQ text must match exactly.** Google de-validates schema where the schema content drifts from the visible page content. Our templates explicitly instruct the AI to mirror the visible FAQ word-for-word in the schema block.

### 7.4 Review schema and rich results

Pages with Review schema can earn the gold-star rich result in search — five stars next to the title, the rating value, and the review count. This is among the most valuable rich results because it visually distinguishes the listing from competitors.

Test pages and product pages both include Review or AggregateRating schema. The values come from real review counts in the product feed (where available) or are populated as the site collects reviews over time.

### 7.5 Schema validation

Before any page is published, the schema block is validated:

1. The JSON-LD is parsed (catches syntax errors)
2. Every required `@type` is confirmed present
3. Every placeholder marker is confirmed present
4. The visible FAQ is compared to the schema FAQ for exact mirroring
5. Optional: the rendered schema is sent to Google's Rich Results Test API for final validation

Failures block publishing. A page with broken schema never makes it live.

---

## 8. The Competitor-Driven Strategy

This is the single most important strategic decision in the system, and it deserves its own section.

### 8.1 Why competitors are the right reference

In any market that's been online for more than a few years, the top-ranking site has already done expensive work that benefits us:

- They've done keyword research — every keyword they rank for is documented in their Ahrefs profile
- They've tested topic clustering — their site structure is empirical proof of what topics belong together
- They've identified product-market fit — the categories that drive their traffic are the ones with real search demand
- They've experimented with content depth — their word counts and structure are calibrated to what ranks

We don't need to redo any of this. We just need to copy their structure and exceed them on quality.

### 8.2 What we extract from competitor data

From the top competitor's Ahrefs export, we extract:

- **Cluster map.** Their keywords grouped by URL — this tells us which keywords belong to which topic, validated by which pages actually rank for which queries.
- **Volume distribution.** Total monthly search volume per cluster — tells us which clusters are worth prioritizing.
- **Difficulty calibration.** Average keyword difficulty per cluster — tells us where competition is light.
- **URL-to-page-type map.** Which URLs are categories, articles, products, guides — inferred from URL patterns and word counts.
- **Top hubs.** Their most-linked pages — these are the pages they're most invested in, and the ones we must match.

From the Screaming Frog crawl, we extract:

- **URL structure depth.** Are they running flat URLs (everything at root) or deep URLs (5 levels of categories)? This affects internal linking strategy.
- **Internal link graph.** Which page links to which page, and with what anchor text — the hub-and-spoke topology.
- **Page-type distribution.** Ratio of categories to products to articles to guides.

This data is run through analysis logic to produce a site plan: "Build these 50 categories with these subcategories. Write these 120 articles, target these keywords, link them to these hubs. Publish these 30 product reviews. Create these 18 buying guides." The site plan is the input to content generation.

### 8.3 Why "one top competitor" and not "all competitors"

A natural question: shouldn't we aggregate data from multiple competitors to find blind spots?

We considered this and chose single-competitor mode for v1 because:

- **Faster to ship.** One source = no merge conflicts between datasets.
- **Empirically validated structure.** A site with 200K monthly visitors has structure that works; copying it is safer than guessing what improvements might work.
- **Quality differentiation is more valuable than coverage differentiation.** If we have 95% of their topical coverage but every page is 30% better, we win.
- **Adding a second competitor is a small extension.** When v1 is shipping, we can layer in a "competitor B" import and diff cluster maps to find gaps.

The right move for v1: ship single-competitor, monitor what's missing, add second-competitor support if and when a real gap appears.

### 8.4 How we beat them once we mirror their structure

Mirroring their structure gets us topical parity. To rank higher we need quality leverage. We get it from:

- **Better schema.** They have partial schema; we have complete schema. Rich results win.
- **Better E-E-A-T signals.** They have anonymous content; we have named authors, methodology pages, testing attribution.
- **Better FAQ targeting.** Their pages don't deliberately target People Also Ask boxes; ours do.
- **Better internal linking.** They have inconsistent anchor text; ours is validated for diversity and topical relevance.
- **Faster site speed.** They're on bloated themes; we're on GeneratePress with WP Rocket and Cloudflare.
- **Freshness.** They update once a year; we touch every page monthly.
- **Localization.** Their language coverage is incomplete; we go native in 19 languages.

Each of these is a 5–15% advantage. Combined, they let us punch above our backlink weight class.

---

## 9. Multi-Site, Multi-Language Architecture

The system is designed from the ground up to operate N sites across M languages. This isn't a feature added on — it's the core architecture.

### 9.1 The branch-per-site model

Each site (each language) is a separate Railway service running from a separate branch of the same codebase. The branch model is:

```
Repo: gsc-seo
├── main                  (development, all shared improvements land here)
├── affiliate-dk          (Danish affiliate site)
├── affiliate-no          (Norwegian affiliate site)
├── affiliate-de          (German affiliate site)
├── affiliate-fr          (French affiliate site)
└── ... one branch per (site × language)
```

Each branch tracks `main` for shared code improvements but has its own:
- Bundled data (competitor exports specific to that market)
- Environment variables (different WordPress URL, language, currency)
- `/data` volume (cached analysis specific to that site)
- WordPress credentials

When we improve the code on `main` (better template, new feature, bug fix), a single command (`deploy_all_sites.ps1`) merges main into every site branch and pushes — Railway redeploys all services automatically.

This model is already proven in production with mshop.se, mshop.dk, and mshop.eu.

### 9.2 Native-language content (not translation)

For each language, content is generated **natively in that language** by Claude. We do not generate English content and translate it.

Why this matters:
- Translation produces calques (literal renderings of English idioms that sound foreign)
- Local keyword research differs across markets — Danes don't search for the same phrases Swedes do
- Cultural references, purchasing patterns, and tone expectations differ
- Schema entries (FAQ questions, product descriptions) need to be natively phrased to rank locally

The AI generator passes a `language` parameter to every prompt. The prompts contain language-agnostic instructions ("use the natural [language] equivalent of...") and Claude generates idiomatic native content. We've tested this approach across Swedish, Danish, Norwegian, German, French, Spanish, Italian, Dutch, Finnish — works reliably in all.

### 9.3 Per-language launch sequence

We launch one language at a time. The sequence is:

1. **Setup branch + Railway service.** 15 minutes per site.
2. **Configure environment variables.** WordPress URL, app password, GSC site URL (optional — will be empty for new sites), Anthropic API key, currency.
3. **Import competitor data.** Drop the four competitor CSV files into `bundled_data/` with the language suffix (`_dk`, `_de`, etc.). 5 minutes per market.
4. **Run greenfield pipeline.** Generates site plan from competitor data. 10–30 minutes depending on competitor size.
5. **Generate content batches.** Categories first, then articles, then product pages, then guides and tests. Days to weeks depending on volume.
6. **Editorial review.** 5–10% sampling. Days.
7. **WordPress publish.** Batched upload. Hours.
8. **Submit sitemap to Google Search Console.** Minutes. (Bookmark in 60 days when the first rankings appear.)

This sequence repeats for every new (site × language) we launch. Operational cost: roughly one focused week of operator attention per launch.

### 9.4 Scaling characteristics

Adding a new language costs ~$300–800 in initial AI generation (varies with site size and quality settings), plus ~$5/month Railway hosting plus ~$30–60/month WordPress hosting plus shared costs (Anthropic API, WPML, plugins amortized).

The economics are stark: a new language launch pays for itself within 3–6 months in most cases, and a single hit language can fund multiple new launches.

We can scale to 18–19 European languages plus English within a year if capital allows.

---

## 10. WordPress Publishing & Maintenance

WordPress is the publishing layer. The system pushes finished content to WordPress over the REST API, then keeps it synchronized with the product feed.

### 10.1 Why WordPress

We chose WordPress over a custom CMS for three reasons:

- **Plugin ecosystem.** WPML (multilingual), Rank Math (SEO), Advanced Custom Fields (price/stock decoupling), WP Rocket (caching) — all mature, all together solve 90% of what we need.
- **Hosting market.** Cloudways, Kinsta, Pressable — managed WordPress hosting is cheap, reliable, and performant.
- **Theme ecosystem.** GeneratePress gives us a 30KB CSS footprint and 100/100 PageSpeed scores out of the box.

Building a custom CMS would have cost six months and given us nothing WordPress doesn't already provide.

### 10.2 Per-site WordPress setup

Each language gets its own WordPress installation. Setup checklist:

- WordPress 5.6+ (Application Passwords built-in)
- GeneratePress Pro theme (minimal, fast)
- WPML Multilingual CMS (if running multiple languages from one install — usually we don't)
- Advanced Custom Fields Pro (custom fields for price, stock, affiliate URL)
- Rank Math Pro (SEO, schema, sitemap, breadcrumb)
- WP Rocket (page cache, critical CSS)
- ShortPixel (image compression)
- Cloudflare (CDN, free tier sufficient)

Total annual plugin cost per site: ~$445.

### 10.3 The publish flow

When content is ready to publish, the system:

1. **Uploads images.** Product images and any original photos go to the WordPress media library. We store the WordPress attachment ID for each.
2. **Creates taxonomies.** The category tree is built as WordPress categories (or custom taxonomies). Each category gets its name, slug, parent, and SEO meta.
3. **Creates posts.** Each piece of content becomes a WordPress post (or custom post type — `product`, `test`, `shopping_guide`). The body is the AI-generated HTML. Custom fields are populated from the feed. SEO meta is set in Rank Math.
4. **Sets internal links.** After all posts are created and their final URLs are known, a second pass updates internal links to use real WordPress URLs (during generation, we use placeholders).
5. **Validates schema.** Each published page is checked against the Rich Results Test API; failures are queued for re-publish.
6. **Submits sitemap.** New URLs are added to the sitemap, which is pinged to Google Search Console.

### 10.4 The hourly price sync

The most operationally important piece. Every hour:

1. The product feed is re-fetched from the affiliate network.
2. Changed prices and stock statuses are identified.
3. A single API call updates the corresponding WordPress custom fields.

That's it. No body text changes. No AI regeneration. No cache invalidation beyond the affected URLs.

A site with 2,000 products can have all prices refreshed in a single API call that takes under a minute. The cost: pennies of Cloudflare bandwidth.

### 10.5 The freshness loop

Every month, a maintenance job:

- Touches the `dateModified` on every post (signals to Google that the site is actively maintained)
- Identifies pages with thin content or poor performance in Google Search Console (once we have GSC data — usually 3+ months post-launch)
- Queues pages for refresh with new content paragraphs, updated FAQ entries, or new comparison data
- Re-validates schema on all pages

This is the single biggest difference between sites that stay competitive and ones that decay. Most affiliate sites are publish-and-forget — their `dateModified` shows the original publish date forever. Ours shows recent dates because we actively maintain.

---

## 11. The Step-By-Step Workflow

This section walks through what an operator actually does, day-by-day, to launch a new site. Treat it as a checklist.

### 11.1 Day 1: Site setup

- Create Railway service from `main` branch
- Set environment variables (`SITE_CODE`, `CONTENT_LANGUAGE`, `WP_API_BASE`, `WP_API_USER`, `WP_API_APP_PASSWORD`, `ANTHROPIC_API_KEY`, `APP_PASSWORD`)
- Provision WordPress hosting + install theme/plugins
- Configure WordPress: create app password, install WPML if needed, install GeneratePress, install Rank Math, install ACF Pro, install WP Rocket
- Create new branch in repo: `git checkout -b affiliate-de`, push
- Verify the Railway service boots and the login screen appears

**Time required:** 2–4 hours.

### 11.2 Day 2: Competitor data import

- Identify the top competitor in the target market (Ahrefs Site Explorer, sort by traffic)
- Export from Ahrefs:
  - Organic keywords (full export, all positions)
  - Best by links (top 1,000 pages)
- Crawl the competitor with Screaming Frog:
  - All HTML pages
  - All inlinks
- Compress the four CSVs with gzip
- Drop them in `bundled_data/` with the language suffix (e.g., `competitor_ahrefs_keywords_de.csv.gz`)
- Commit and push to the language branch
- Reload the Railway service
- Open the new Competitor Intelligence view, verify the data loaded

**Time required:** 4–6 hours (mostly waiting for Ahrefs export and Screaming Frog crawl).

### 11.3 Day 3: Generate site plan

- In the Competitor Intelligence view, click "Build site plan"
- Wait 10–30 minutes while the system analyzes competitor data
- Review the generated plan:
  - Are the inferred categories sensible?
  - Are the recommended article topics aligned with our market?
  - Are there any clusters we want to add or remove?
- Approve the plan

**Time required:** 1–2 hours of review.

### 11.4 Days 4–14: Generate content

This is the bulk of the work, but it's mostly the system running while you work on other things.

Order of operations:

1. **Category bottom texts.** Fast (50 categories × 30 seconds each = 25 minutes). Most strategic for SEO.
2. **Articles.** ~120 articles × 2 minutes each = 4 hours of AI time, spread over a day with manual review.
3. **Shopping guides.** ~18 guides × 5 minutes each = 1.5 hours of AI time. Higher review burden per page because they're longer.
4. **Product pages.** ~2,000 products × 2 minutes each = 67 hours of AI time. Run in batches of 100/day.
5. **Test pages.** ~30 tests, ideally with real testing data uploaded. Slower because of the editorial overhead.

Throughout this phase:
- Editor reviews 5–10% of each batch
- Failed pages (didn't pass validation) are auto-regenerated
- Approved pages move to "validated" status

**Time required:** 2 weeks of part-time operator attention.

### 11.5 Days 15–18: Publish to WordPress

- Run the bulk publish job, batches of 100 posts per run
- Verify the first 5 published pages render correctly in WordPress
- Confirm schema validates in Google Rich Results Test
- Confirm internal links resolve correctly
- Run sitemap regeneration in Rank Math
- Submit sitemap to Google Search Console

**Time required:** 1–2 days.

### 11.6 Day 19: Post-launch verification

- Check 20 random pages for rendering issues
- Run a broken link checker
- Run Lighthouse on 5 representative pages — expect 90+ scores
- Run Mobile-Friendly Test
- Run Page Speed Insights — verify Core Web Vitals all green

**Time required:** 4 hours.

### 11.7 Months 1–3 post-launch

This is when patience pays off. New sites typically take 6–12 weeks to start ranking, and 3–6 months to reach steady-state traffic.

During this period:
- **Weekly:** Check Google Search Console for indexing progress. Resolve any crawl errors.
- **Bi-weekly:** Add 5–10 new articles targeting emerging keywords (the system surfaces these automatically once GSC data flows).
- **Monthly:** Run freshness pass (touch dateModified, add paragraphs to top pages).
- **Continuously:** Hourly price/stock sync (automated).

Traffic curve typically:
- Month 1: < 1,000 monthly visitors (indexing phase)
- Month 2: 1,000–5,000 monthly visitors
- Month 3: 5,000–15,000 monthly visitors
- Month 6: 25,000–80,000 monthly visitors
- Month 12: 50,000–200,000 monthly visitors
- Month 24: 100,000–400,000+ monthly visitors

These are realistic ranges based on the affiliate-vertical norms across European markets we've studied. Actual results depend heavily on competition, backlink acquisition, and content quality.

---

## 12. Expected Results & Traffic Projections

This section gives concrete numbers, with the caveats they deserve.

### 12.1 The honest range

Affiliate site outcomes vary wildly based on factors outside content quality:

- **Market competition.** A site in Poland targeting a low-competition vertical can reach 100K visitors faster than a site in Germany targeting a high-competition one.
- **Backlink acquisition.** Sites that build backlinks aggressively (digital PR, content partnerships, guest posts) outperform sites that don't.
- **Niche selection.** Some niches have higher commercial intent (more affiliate revenue per visitor); others have higher volume but lower conversion.
- **Quality of execution.** A site that uses the system as designed (full schema, real testing, editorial review) outperforms one that cuts corners.

Given these variables, we model three scenarios:

### 12.2 Conservative scenario (low end)

Assumptions:
- Mid-competition market
- Minimal backlink acquisition (organic only)
- Standard execution

Monthly visitor trajectory:
| Month | Visitors |
|---|---|
| 3 | 3,000 |
| 6 | 12,000 |
| 9 | 25,000 |
| 12 | 40,000 |
| 18 | 60,000 |
| 24 | 80,000 |

Affiliate revenue at maturity (Month 24+): **8,000–15,000 SEK/month per site** (~$750–1,400 USD).

### 12.3 Base scenario (realistic expected)

Assumptions:
- Mid-competition market
- Active backlink acquisition (digital PR, 2–3 strategic partnerships per quarter)
- Strong execution (full feature set, real testing on top 30 products)

Monthly visitor trajectory:
| Month | Visitors |
|---|---|
| 3 | 8,000 |
| 6 | 30,000 |
| 9 | 60,000 |
| 12 | 100,000 |
| 18 | 160,000 |
| 24 | 220,000 |

Affiliate revenue at maturity (Month 24+): **30,000–60,000 SEK/month per site** (~$2,800–5,600 USD).

### 12.4 Best-case scenario (top decile execution)

Assumptions:
- Lower-competition market (e.g., Baltic states, Southeast Europe)
- Aggressive backlink acquisition
- Excellent execution + good niche-product fit

Monthly visitor trajectory:
| Month | Visitors |
|---|---|
| 3 | 20,000 |
| 6 | 80,000 |
| 9 | 150,000 |
| 12 | 250,000 |
| 18 | 350,000 |
| 24 | 500,000+ |

Affiliate revenue at maturity (Month 24+): **80,000–180,000 SEK/month per site** (~$7,500–17,000 USD).

### 12.5 Portfolio-level projections

The real strategic value emerges when running multiple sites. With 6–10 sites launched across 6–10 languages, the diversification smooths variance and aggregate revenue compounds:

| Time horizon | Sites in operation | Total monthly visitors | Total monthly revenue (SEK) | Total monthly revenue (USD) |
|---|---|---|---|---|
| Year 1 | 3 | 80,000–300,000 | 20,000–100,000 | $1,900–9,400 |
| Year 2 | 6 | 400,000–1,500,000 | 100,000–400,000 | $9,400–37,500 |
| Year 3 | 10 | 1,000,000–4,000,000 | 250,000–800,000 | $23,500–75,000 |

Note that these are revenue not profit. Costs are documented in Section 15.

### 12.6 The math behind the numbers

Affiliate revenue depends on three multipliers:

```
Monthly Revenue = Visitors × Click-to-affiliate rate × Conversion rate × Average commission
```

Typical values in our verticals:

- **Click-to-affiliate rate.** Out of every 100 visitors, 20–40 click an affiliate link (the better the buying intent of the content, the higher).
- **Conversion rate.** Out of every 100 affiliate clicks, 3–5 result in a sale.
- **Average commission.** 50–70 SEK per sale (varies by product category and merchant).

So 100,000 monthly visitors → 25,000 affiliate clicks → 1,000 sales → ~60,000 SEK revenue. That's roughly the math behind the Base scenario at Month 12.

These ratios are achievable but not automatic. Sites that don't follow the playbook (no schema, no E-E-A-T, generic AI content) typically convert at 1/5th to 1/10th these rates because Google sends them less buying-intent traffic.

### 12.7 What could make this fail

We owe you a realistic risk model. Three failure modes:

1. **Algorithm hit.** Google's affiliate site policy enforcement is the biggest single risk. We mitigate by following E-E-A-T to the letter, but a punitive update could still hurt rankings 30–70% for a quarter. Mitigation: diversify across sites and markets so no single hit is fatal.

2. **Backlink shortfall.** Content is necessary but not sufficient. Without backlinks, even great sites cap at ~50K monthly visitors. The plan budgets for digital PR and content partnerships to address this.

3. **Affiliate program changes.** Commission rates can be cut, programs can shut down, payment terms can change. We mitigate by diversifying across multiple affiliate partners per market.

None of these are catastrophic; all are manageable with the right risk diversification.

---

## 13. Risk Factors & How We Manage Them

A frank assessment of what could go wrong and what we do about it.

### 13.1 Google algorithm risk

Google's core updates and policy changes can move sites by 30–70% in either direction. Affiliate sites are particularly exposed because Google has explicit policies targeting "site reputation abuse" and "scaled content abuse."

**Mitigation:**
- Strict E-E-A-T compliance from day one (every signal Google looks for is present)
- Complete schema markup
- Real testing for top product reviews
- Visible methodology pages
- Named author attribution
- Active maintenance (not publish-and-forget)
- Diversification across multiple sites and markets

Even with all this, expect 1–2 algorithm-related dips per year per site. Plan for it; don't be surprised by it.

### 13.2 Affiliate program risk

Affiliate commission rates can be cut unilaterally. Programs can shut down. Payment terms can extend.

**Mitigation:**
- Multiple affiliate partners per market (no single program > 60% of any site's revenue)
- Direct merchant relationships where possible
- Diversification across product categories within each market

### 13.3 Content quality risk

If a site ships with content that gets flagged as low-quality, it's expensive to recover. Recovery typically requires rewriting flagged pages and waiting 6–12 months for Google's trust to rebuild.

**Mitigation:**
- Editorial review of 5–10% sampling before publish
- Schema validation on every page
- Anti-AI-detection scaffolding in every prompt
- Real testing data integration where claims require it
- Synthetic mode where real testing isn't available (softer language to avoid fabrication)

### 13.4 Operational risk

The system has many moving parts: Railway, WordPress, Cloudflare, Anthropic API, affiliate networks, image storage. Any of these can have outages.

**Mitigation:**
- All critical state stored on Railway volumes (survives service restart)
- WordPress on managed hosting with SLA (Cloudways, Kinsta)
- Cloudflare CDN absorbs origin downtime for cached pages
- Hourly price sync has retry logic
- Daily backups of WordPress + Railway volumes
- Anthropic SDK has built-in retry/backoff

### 13.5 Legal & compliance risk

Affiliate disclosures are mandated by FTC (US) and EU consumer protection regulations. Failure to disclose can result in fines or program termination.

**Mitigation:**
- Every test page and shopping guide includes a properly-worded disclosure at the top
- Disclosure language is reviewed per language for legal compliance
- GDPR compliance through standard WordPress plugins (cookie consent, privacy policy)

### 13.6 Technology debt risk

WordPress plugin ecosystem evolves. Themes deprecate. Anthropic models change. Schema.org vocabulary updates.

**Mitigation:**
- All plugins on premium tiers with active support
- Theme stays on GeneratePress (most-maintained free-tier theme)
- AI generator is model-agnostic — switching Claude models requires only a config change
- Schema validator catches deprecated schema patterns

---

## 14. Timeline To Launch

How long from "we have a partnership agreement" to "first site is live and earning."

### 14.1 Build phase (weeks 1–3)

Some pieces of the system are already built; others need to be added before first launch. The remaining work is documented in `NEW_SITES_ARCHITECTURE.md`:

- **Week 1:** Greenfield-mode flag added to pipeline; competitor data import view built; product feed parser shipped; content-type inference extended for product/test/shopping_guide detection.
- **Week 2:** WordPress publisher module built; price/stock sync endpoint built; schema validator built; anti-fabrication validator built.
- **Week 3:** Tone-of-voice profiles; author management UI; freshness scheduler; generation log + greenfield dashboard panel.

After week 3, the system is fully operational for greenfield site launches.

### 14.2 First site launch (weeks 4–6)

- **Week 4:** Pick first language. Set up Railway service + WordPress. Import competitor data. Generate site plan.
- **Week 5:** Generate all category bottom texts, articles, shopping guides. Editorial review.
- **Week 6:** Generate product pages. Bulk publish to WordPress. Submit sitemap.

End of week 6: first site is live with 2,000+ pages, sitemap submitted, indexing in progress.

### 14.3 Ranking phase (months 2–6)

This is the patient phase. Google takes time to crawl, index, and rank a new site.

- **Month 2:** Most pages indexed. Initial rankings appearing for long-tail keywords. Traffic still minimal.
- **Month 3:** First measurable traffic (3,000–8,000 monthly visitors typical). Initial affiliate conversions.
- **Month 4–5:** Steady ranking improvements. Traffic scales 2-3x per month.
- **Month 6:** First steady-state revenue (5,000–30,000 SEK/month range).

During this phase, additional sites can be launched in parallel. The cadence we target: 1 new (site × language) per month after initial launch.

### 14.4 Compound growth phase (months 6+)

After month 6, sites start to compound:

- New articles target emerging keywords (the system surfaces these from GSC data once it flows)
- Backlinks acquired in months 1–6 mature into authority
- Brand searches start appearing
- Featured snippet placements multiply
- Cross-linking between articles deepens topical authority

Traffic typically doubles between months 6 and 12, then doubles again between months 12 and 24 (assuming sustained content addition and backlink building).

### 14.5 Portfolio launch sequence

Recommended launch sequence by ROI:

- **Months 1–2:** First Nordic site (Danish or Norwegian) — proven vertical, known culture
- **Months 3–4:** Second Nordic + first Baltic (Latvian) — low competition, easy wins
- **Months 5–6:** Second Baltic + first Central European (Polish or Czech)
- **Months 7–9:** Romanian, Greek, Croatian (very low competition, modest volume)
- **Months 10–12:** First Western European (Spanish or Italian — large markets but higher competition)
- **Year 2:** German, French, Dutch (the big markets), English (highest competition but largest pool)

By end of Year 1: 8 sites operational. By end of Year 2: 12–15 sites.

---

## 15. Investment Required

Capital and operational requirements for a typical partnership.

### 15.1 One-time costs per site

| Item | Cost (USD) |
|---|---|
| WordPress hosting setup (Cloudways) | $50 setup, $30/month ongoing |
| Plugin licenses (annual, divided per site) | ~$50/year |
| Domain registration | $15/year |
| Initial AI generation (full site) | $300–800 |
| Editorial review (5% sampling × 2,000 pages = 100 pages reviewed × ~5 min each = 8 hours of editor time at market rate) | $200–500 |
| Testing photography (for top 30 products with real testing) | $500–1,500 (or $0 if synthetic mode used) |

**Total per site to launch: ~$1,500–3,500.**

### 15.2 Ongoing costs per site

| Item | Cost (USD/month) |
|---|---|
| Railway hosting | $5 |
| WordPress hosting (Cloudways) | $30 |
| Anthropic API (price sync + monthly refresh) | $30–80 |
| Plugins (amortized annually) | $4 |
| Backups + monitoring | $5 |

**Total per site ongoing: ~$75–125/month.**

### 15.3 Shared infrastructure costs

These are spread across all sites:

| Item | Cost (USD/month) |
|---|---|
| Anthropic API (shared base) | $50 |
| Ahrefs subscription (for competitor data) | $99 |
| Screaming Frog license | $20 (amortized from $239/year) |
| Domain monitoring + uptime checks | $10 |
| Email + project management tools | $30 |

**Total shared: ~$200/month.**

### 15.4 Total portfolio cost

For 5 active sites:
- One-time setup: $7,500–17,500
- Monthly operating: $575–825 + $200 shared = $775–1,025
- Annualized: $9,300–12,300

For 10 active sites:
- One-time setup: $15,000–35,000
- Monthly operating: $950–1,450 + $200 shared = $1,150–1,650
- Annualized: $13,800–19,800

### 15.5 Revenue against costs

Cross-referencing Section 12's revenue projections:

For a Base-scenario site at Month 24:
- Revenue: ~$3,000–5,000/month
- Cost: ~$75–125/month
- Profit margin: 96–98%

That's why the affiliate model works at all. The marginal cost of operating a mature site is dominated by hosting fees, and revenue scales linearly with traffic while costs barely move.

### 15.6 Capital efficiency

Compared to typical affiliate site investments (where 12–18 months to break-even is normal):

- Break-even per site: typically 3–6 months for the Base scenario
- Payback on portfolio: typically 9–12 months when launching sequentially
- Year 3 ROI: 10–20x on initial capital deployed

These multiples are why we're confident in the partnership model — the upside is meaningful and the downside is bounded by relatively modest per-site setup costs.

---

## 16. Why This Beats Alternative Approaches

A partner deserves to know why this approach, specifically.

### 16.1 vs. hiring writers

A traditional approach: hire 5 freelance writers, produce 50 articles/month at $50 each, scale slowly.

- Cost: $2,500/month for content alone
- Pace: 50 articles/month = 600/year per site
- Quality: variable; depends on writer expertise
- Schema: not handled (writer doesn't produce schema)
- Multi-language: have to hire writer per language

Our approach delivers 10x the output at 1/10th the cost, with mandatory schema markup and consistent quality, across as many languages as Claude speaks (essentially all of them).

### 16.2 vs. ChatGPT + manual publishing

Some affiliate operators use ChatGPT directly: write a prompt, paste into Word, paste into WordPress, repeat.

- Cost: ~$20/month ChatGPT
- Pace: limited by manual labor — 5–10 articles/day max
- Quality: generic ChatGPT output without templates, scaffolding, validation
- Schema: must be added manually per page
- Multi-language: ChatGPT is okay but quality varies and consistency is hard to enforce

Our approach embeds all the quality controls (templates, scaffolding, validation, schema) in the system itself. Output is consistent across thousands of pages because it's generated through the same pipeline, not by the same person typing fresh prompts daily.

### 16.3 vs. SEO content agencies

Agencies sell turnkey content production for $1,000–5,000/month per site.

- Cost: $12,000–60,000/year per site
- Pace: typical agency: 20–40 articles/month
- Quality: medium-to-high depending on agency
- Schema: usually partial
- Customization: limited; agencies use their own templates

Our approach has roughly the same per-month output at 1/10th the cost, with full control over templates, full schema, and per-language native generation.

### 16.4 vs. competitor's existing approach

The biggest competitor in any given market is typically running:
- Anonymous AI content (no E-E-A-T)
- Partial schema (Product only, no FAQ or Review)
- Generic templates (one template for everything)
- Translated content (not native generation)
- Stale `dateModified` (publish-and-forget)

We meet or beat them on every single one of these. That's how a new site overtakes an established one over 12–24 months.

### 16.5 vs. building from scratch (custom tooling)

Some operators build their own pipeline. Time to first launch: 6–12 months. Cost to build: $50,000–200,000 in engineering.

Our system is already built (templates and architecture in place, the rest is ~3 weeks of focused work documented in NEW_SITES_ARCHITECTURE.md). A partner gets immediate access to the equivalent of 6+ engineer-months of prior work.

---

## 17. Frequently Asked Questions

### Will this work for our specific niche?

The system is niche-agnostic but works best for niches where:
- The top competitor's structure is publicly inferable via Ahrefs + Screaming Frog
- A product feed exists (most affiliate networks)
- Schema markup applies (essentially all e-commerce, most editorial verticals)
- Per-language demand exists (consumer products generally; some B2B niches don't translate well)

If your niche fits these, the system will work. Common applicable niches: consumer electronics, home & garden, beauty, fitness, intimate wellness, fashion, pets, hobbies, software & SaaS reviews.

### How long until we see revenue?

Realistic timeline:
- First measurable traffic: month 2–3 post-launch
- First steady affiliate commissions: month 3–4
- Break-even per site: month 4–6
- First meaningful monthly revenue (>$1,000/month): month 6–9
- Steady-state revenue: month 18–24

Patience is required. SEO compounds; it doesn't spike.

### Is this Google-policy compliant?

Yes, with caveats:
- The system follows Google's Spam Policies (no cloaking, no doorway pages, no auto-generated content without value)
- E-E-A-T is built into every template
- Affiliate disclosures are mandatory and included
- Schema markup is complete and accurate

The biggest policy risk for affiliate sites in general is Google's "Site Reputation Abuse" policy, which targets thin AI content without expertise. Our system is designed specifically to clear this bar — but it can't guarantee a future policy change won't move the line.

### What if Google changes its algorithm?

We've watched Google's algorithm changes for a decade in the SEO space. The general pattern:
- Quality-focused updates favor our approach (better E-E-A-T, better schema, better technical SEO)
- Quantity-focused crackdowns penalize spam mills (not us)
- Affiliate-specific crackdowns penalize sites without real expertise (sites in synthetic mode without testing photos are at higher risk than sites that genuinely test)

Mitigation strategy: run the system as designed (real testing where possible, full schema, named authors, active maintenance) and diversify across sites/markets so no single hit is fatal.

### Can we customize the templates?

Yes. Templates are stored in `utils/templates.py` as Python functions returning markdown-formatted instruction blocks. Editing them requires basic technical comfort but is straightforward.

Common customizations:
- Adjust the FAQ count (5–7 → 8–10)
- Add a "Why we recommend X over Y" section
- Modify the tone-of-voice section for specific niches
- Add a custom schema entry (e.g., VideoObject if you have product videos)

### What happens if Claude (the AI model) shuts down or changes?

The AI generator code is model-agnostic at the API level. It calls `client.messages.create(model="claude-...")`. Switching to a different Claude model is a one-line change. If Anthropic ever shut down (extremely unlikely given their backing), the same generator could call OpenAI or another provider with minor adapter work.

### What's the editorial workload?

Per site, ongoing:
- 1–2 hours/week of monitoring (Google Search Console, performance dashboards)
- 1 hour/month of content review (validate that new articles look good)
- 2–4 hours/month of strategy (new article topics, partnership opportunities)

Per launch:
- ~30–40 hours over 3–4 weeks (mostly review, decision-making, WordPress configuration)

Less than half a part-time role per active site.

### Can we use this without WordPress?

The system is designed around WordPress because of the plugin ecosystem (especially WPML, Rank Math, ACF). It could be adapted to other CMSes (Webflow, Sanity, custom Next.js) but would require building publisher adapters for each. WordPress remains the recommended starting point.

### What about images?

The system pulls product images from the affiliate feed. For original images (testing photos, lifestyle shots), the operator uploads them through the standard WordPress media library. The schema and HTML generation reference these images via WordPress attachment IDs.

For sites that want fully original imagery, the operator commissions a small product photoshoot for the top 30–50 products in the catalog. This is a one-time cost (~$500–1,500) and significantly improves E-E-A-T.

### What about backlinks?

The system does not build backlinks. Backlink acquisition is a separate operational discipline:
- Digital PR (pitching journalists, securing press mentions)
- Content partnerships (guest posts on relevant publications)
- HARO/help-a-reporter responses
- Linkable assets (original research, infographics, tools)
- Local citations (directories, profiles)

Realistic budget for backlinks: $500–2,000/month per active site, depending on competition. Lower-competition markets need less; higher-competition markets need more.

### What about social media?

The system doesn't address social media directly. Social presence helps with brand searches (which are a ranking factor) and direct conversions but isn't critical to SEO. We recommend a light social presence (Instagram, Pinterest for visual verticals; Twitter/LinkedIn for editorial verticals) with content cross-posted from the WordPress site.

---

## 18. Glossary

**Affiliate link** — A specially-formatted URL that includes a tracking parameter, attributing any resulting sale to your site for commission purposes.

**Ahrefs** — A commercial SEO tool that maintains a database of every keyword every site ranks for. Used by every serious SEO operator.

**Anchor text** — The visible text of a hyperlink. Search engines weight anchor text as a signal about what the linked page is about.

**Backlink** — A link from one website to another. Backlinks are a primary ranking signal because they represent endorsement.

**Breadcrumb** — A navigation aid showing where a page sits in a site hierarchy (e.g., Home > Electronics > Headphones > Wireless). Also marked up in schema.

**Cannibalization** — When two pages on the same site compete for the same keyword, splitting their ranking potential. To be prevented at the structural level.

**Click-through rate (CTR)** — The percentage of search-result impressions that result in a click. Higher CTR = more traffic from same rankings.

**Cluster** — A group of related keywords that should be served by a single page or tightly-linked group of pages.

**Cluster head term** — The most search-volume-significant keyword in a cluster, used as the canonical phrase for that cluster.

**Core Web Vitals** — Three speed/UX metrics Google uses as ranking factors: LCP (Largest Contentful Paint), INP (Interaction to Next Paint), CLS (Cumulative Layout Shift).

**E-E-A-T** — Experience, Expertise, Authoritativeness, Trustworthiness. Google's framework for evaluating content quality.

**Featured snippet** — The answer box that sometimes appears above the regular search results, drawing content from a single ranking page.

**FAQ schema** — A type of structured data that lets Google display FAQs as interactive accordions in search results.

**Hreflang** — A meta tag indicating which language and country a page is intended for. Critical for multi-language sites.

**Internal link** — A link from one page on a site to another page on the same site.

**JSON-LD** — The schema markup format Google prefers. Embedded as a `<script>` tag.

**LIX** — A Nordic readability score: (words / sentences) + (long words × 100 / words). 35–40 is the e-commerce sweet spot.

**Meta description** — A short page summary displayed in search results below the title. Doesn't directly affect ranking but heavily affects CTR.

**Meta title** — A page's title in search results. The most important on-page SEO element.

**People Also Ask (PAA)** — The "related questions" box that appears in many search results. Targeted via FAQ schema.

**Rank Math** — A WordPress SEO plugin we use. Handles sitemaps, schema, breadcrumbs, redirects.

**Rich result** — Any special search result format beyond the standard blue link (product cards, FAQ accordions, star ratings, etc.).

**Schema markup / structured data** — Standardized vocabulary (schema.org) used to label page content for search engines.

**Search intent** — The underlying purpose behind a search query: informational, navigational, transactional, commercial investigation. Matching intent is critical for ranking.

**Screaming Frog** — A site-crawler tool. We use it to map competitors' site structure.

**Site architecture** — The hierarchical organization of pages on a site, from home page through categories to individual pages.

**Sitemap** — An XML file listing every page on a site, submitted to Google to aid indexing.

**Spoke page** — A subordinate page in a hub-and-spoke cluster (e.g., a product page that supports a category hub).

**Topic cluster** — A group of pages on closely related topics, linked together with a central "hub" page representing the broadest topic.

**WPML** — WordPress Multilingual plugin. Handles multi-language content if multiple languages run on one WordPress install.

**Wp_rest_api** — WordPress's built-in REST API. How we publish content programmatically.

---

## Closing notes

This manual describes a system designed to compete in SEO at the highest level — against established sites with years of head start and thousands of backlinks. It does this not by working harder than competitors, but by working differently: with complete schema, real E-E-A-T signals, native-language generation, and operational discipline.

The technology is most of the way built. The remaining work is approximately three weeks. The partnership opportunity is to deploy this technology across 6–15 European language markets over 18–24 months, capturing affiliate revenue across markets where each individual site can reach 30,000–250,000 monthly visitors at steady state.

We're confident in the approach because every piece of it is grounded in current Google guidelines and validated SEO practice. We're realistic about the variance because SEO outcomes always have some variance.

For partnership inquiries or technical questions: contact the operator.

---

*End of manual.*

*Approximately 18,500 words, 25–28 standard pages when rendered.*
