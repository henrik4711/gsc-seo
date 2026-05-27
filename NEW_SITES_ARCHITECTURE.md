# New-Sites Architecture — Greenfield Affiliate-Style Sites

**Use case:** Henrik launches a new affiliate/SEO site in a market where he has **no existing pages**. The site is built from scratch using the biggest competitor's data as the SEO baseline. Content is generated, validated, and pushed to a per-language WordPress installation. Affiliate links to the merchant earn commission on every referred sale.

**Companion documents:** `MULTISITE_SETUP.md` (Railway/branch model), `AFFILIATE_SITE_PLAN.md` (revenue projections, plugin choices).

---

## 1. Big picture

```
┌────────────────────────────────────────────────────────────────────┐
│                    GREENFIELD PIPELINE                              │
│                                                                     │
│  COMPETITOR INPUT                                                   │
│  ├─ Ahrefs export from top competitor   (ranking keywords + URLs)   │
│  ├─ Screaming Frog crawl of competitor  (site structure + linking)  │
│  └─ Optional: product feed              (catalog data)              │
│           │                                                          │
│           ▼                                                          │
│  EXTRACT competitor architecture                                     │
│  ├─ Cluster map (which queries belong together)                     │
│  ├─ URL → topic map (what each page targets)                        │
│  ├─ Internal link graph (hub/spoke structure)                       │
│  └─ Content-type per page (category / article / product / guide)    │
│           │                                                          │
│           ▼                                                          │
│  GENERATE site plan for THIS new site (one language at a time)      │
│  ├─ Category tree to create                                         │
│  ├─ Article roadmap (per cluster: articles + tests + guides)        │
│  ├─ Internal linking plan (siblings, parent, child)                 │
│  ├─ Product list (from feed) — one entry per product                │
│  └─ Per-page page-type assignment                                   │
│           │                                                          │
│           ▼                                                          │
│  GENERATE content (AI, with templates from utils/templates.py)      │
│  ├─ Category bottom text             (category_bottom_text_instr)   │
│  ├─ Articles                         (blog_template_instructions)   │
│  ├─ Product pages                    (product_page_instructions)    │
│  ├─ Test/review pages                (test_page_instructions)       │
│  └─ Shopping guides                  (shopping_guide_instructions)  │
│           │                                                          │
│           ▼                                                          │
│  PUBLISH to per-language WordPress site                             │
│  ├─ One WP install per language (de / fr / it / es / ...)           │
│  ├─ REST API + Application Password authentication                  │
│  ├─ ACF fields for price / stock / affiliate URL (hot-swap layer)   │
│  └─ Rank Math fills meta + breadcrumb + schema injection            │
│           │                                                          │
│           ▼                                                          │
│  TRACK + RESUME                                                     │
│  ├─ Every output saved to /data with a status (draft/published/...)│
│  ├─ Dashboard shows: created, drafted, published, last updated     │
│  └─ Pipeline resumable at any step — pause / restart safe          │
└────────────────────────────────────────────────────────────────────┘
```

The system can manage **N sites × M languages**. Each site = one Railway service + one branch + one `/data` volume + one WP installation. The same code drives all of them via env vars (`SITE_CODE`, `CONTENT_LANGUAGE`, `WP_API_BASE`, `WP_API_USER`, `WP_API_APP_PASSWORD`, `COMPETITOR_DOMAIN`).

---

## 2. Competitor data ingestion

### 2.1 What we import

Two CSV exports + one optional file from the **top competitor** in the target market:

| File | Source | Purpose | Status |
|---|---|---|---|
| `competitor_ahrefs_organic_keywords.csv` | Ahrefs → Site Explorer → Organic keywords → Export | Tells us EVERY keyword the competitor ranks for, with search volume, position, URL, intent | **NEW** |
| `competitor_ahrefs_best_by_links.csv` | Ahrefs → Best by links → Export | Tells us their most authoritative pages — the hubs we have to compete against | **NEW** |
| `competitor_sf_pages.csv` | Screaming Frog → Internal → HTML → Export | Tells us their full URL structure, titles, H1s, word counts, depth | **NEW** |
| `competitor_sf_inlinks.csv` | Screaming Frog → Bulk export → All Inlinks | Tells us their internal link graph — hub/spoke clustering | **NEW** |

**Important difference from current SE/DK/EU setup:** the existing `link_authority.py` view treats Ahrefs/SF as data about the user's *own* site. For greenfield sites we add a **competitor mode** where the same parsers fill different session-state keys (`competitor_ahrefs_*`, `competitor_sf_*`) and a different analyzer extracts *opportunity* data instead of *risk* data.

### 2.2 Where the parsing code lives

```
utils/competitor_import.py            (NEW — wrapper around existing parsers)
  ├─ parse_competitor_ahrefs_keywords(file_bytes)
  ├─ parse_competitor_ahrefs_best_by_links(file_bytes)
  ├─ parse_competitor_sf_pages(file_bytes_or_path)
  ├─ parse_competitor_sf_inlinks(file_bytes_or_path)
  └─ build_competitor_intelligence(...)
        Returns a dict:
        {
          "clusters": [...],            # Inferred from URL slugs + keyword grouping
          "url_to_topic": {url: ...},   # Each competitor URL → topic
          "url_to_page_type": {url: ...}, # category / article / product / guide / test
          "internal_link_graph": {...}, # hub/spoke from sf_inlinks
          "top_hubs": [...],            # most-linked pages (the ones we MUST also have)
          "missing_for_us": [...],      # topics they cover, we don't
          "keyword_volume_total": int,
        }
```

The existing `utils/ahrefs_import.py` and `utils/screaming_frog_import.py` parsers are **reused as-is** — they don't care whose data they parse. The new module is a thin adapter that points them at competitor session keys + adds the competitor-specific intelligence builder.

### 2.3 View

A new view tab inside `views/link_authority.py` (or a new view `views/competitor.py`):

```
COMPETITOR INTELLIGENCE
├─ Tab 1: Upload competitor data
│   ├─ Drop the 4 CSVs here (or place in data/ with `competitor_` prefix
│   │   for auto-detection — same pattern as own SF/Ahrefs)
│   └─ Button: "Build competitor intelligence"
│
├─ Tab 2: Clusters they own
│   ├─ List of inferred clusters with total monthly volume
│   ├─ Per cluster: ranking URLs, keywords, intent, depth
│   └─ Filter: "topics worth attacking" (vol > X, KD < Y)
│
├─ Tab 3: Site structure they use
│   ├─ Hub pages (most internally linked) — we must match these
│   ├─ URL depth distribution — guides our own slug depth
│   └─ Page-type breakdown (category vs article vs product)
│
└─ Tab 4: Our site plan (DERIVED FROM COMPETITOR)
    ├─ Category tree we need
    ├─ Articles we need (with target keywords + cluster assignment)
    ├─ Tests we need (per high-value product)
    ├─ Shopping guides we need (per cluster with multi-product intent)
    └─ Internal-linking plan
```

### 2.4 Why "top competitor" not "all competitors"

Henrik's stated approach: take the biggest competitor and use them as the **baseline**. Rationale:
- Top competitors have already done the keyword research for us
- They've already tested which clusters convert (they exist because the structure works)
- Faster to ship — N=1 source means no merge conflicts between competitor datasets
- We out-rank by being more thorough (better E-E-A-T, more schema, fresher content), not by finding gaps they missed

We can layer in a SECOND competitor later by re-running the import with a different prefix (`competitor_b_*`) and diffing the cluster maps — but v1 = single source.

---

## 3. Product feed import

### 3.1 What a feed looks like

Affiliate sites get product data via one of:
- **XML feed** (most common — Google Merchant XML, Awin XML, Tradedoubler XML)
- **CSV feed** (some networks)
- **JSON feed** (newer networks, direct merchant APIs)

The schema varies but every feed contains some superset of:
```
id, name, description, brand, category_path, price, currency,
stock_status, availability_date, image_url, additional_image_urls,
product_url (merchant), affiliate_url, gtin, mpn, size, color,
material, age_group, gender, condition, rating_value, review_count
```

### 3.2 Where the parsing code goes (when we build it)

```
utils/product_feed.py                  (NEW — to be built)
  ├─ parse_feed(file_or_url, format='auto') -> list[ProductFeedItem]
  │     - Auto-detects XML / CSV / JSON
  │     - Normalizes field names across feed formats
  │     - Returns a list of dicts with canonical keys
  │
  ├─ ProductFeedItem (dataclass / TypedDict):
  │     {
  │       "feed_id": str,           # The merchant's stable ID
  │       "name": str,
  │       "slug": str,              # We derive — used for our URL
  │       "description_raw": str,   # The merchant's text (NEVER published as-is)
  │       "brand": str,
  │       "category_path": list[str], # ["Electronics", "Headphones", "Wireless"]
  │       "images": list[str],
  │       "specs": dict[str, str],  # Material, weight, dimensions, etc.
  │       "merchant_url": str,
  │       "affiliate_url": str,
  │       "gtin": str,
  │       "rating": float,
  │       "review_count": int,
  │       # Volatile fields (refreshed daily, NEVER touch body text):
  │       "price_current": str,
  │       "price_original": str,
  │       "currency": str,
  │       "stock_status": str,      # 'in_stock' / 'out_of_stock' / 'preorder'
  │     }
  │
  ├─ map_to_categories(items, competitor_intelligence) -> dict
  │     - Match each product to our category tree using:
  │       1. feed category_path (strongest signal)
  │       2. competitor URL→topic map (which competitor category does the
  │          equivalent product live in)
  │       3. AI fallback when neither matches confidently
  │     - Returns {product_id: our_category_slug}
  │
  └─ sync_volatile_fields(items, since=last_sync) -> list[VolatileUpdate]
        Returns ONLY price + stock changes since last sync.
        These flow straight to the WP layer — body text is never touched.
```

### 3.3 Storage on /data

```
/data/feed/
  ├─ feed_<site>.json.gz       # Full normalized feed (refreshed nightly)
  ├─ feed_<site>_volatile.json # Price + stock only (refreshed hourly)
  └─ feed_<site>_history/      # Daily snapshots for rollback / change detection
      └─ feed_<site>_<YYYY-MM-DD>.json.gz
```

### 3.4 Refresh cadence

| Field | Refresh frequency | Trigger |
|---|---|---|
| Catalog (full feed) | Daily | Cron at 03:00 site-time |
| Price | Hourly | Cron — only push changed prices to WP |
| Stock | Hourly | Same cron, same push |
| Description body | Never (manual regeneration only) | Editor flag |

This is the **decoupling guarantee** — body text never changes when prices/stock change. The WP layer renders price + stock via ACF fields populated from the volatile feed, and the body text contains `{{PRICE}}` only inside the schema block, never in visible prose.

---

## 4. Product text generation

### 4.1 What the generator does

For each `ProductFeedItem` from the feed:

```
generate_product_page(
    item: ProductFeedItem,
    category: dict,           # Our category — slug, parent, siblings, hub
    siblings: list,            # Other products in same subcategory (for "compares to")
    competitor_text: str,      # Optional: competitor's product page text (for de-duplication)
    site_context: str,
    language: str,
    tone_profile: dict,        # See 4.2
) -> dict:
    {
      "html": "...",           # Body HTML using product_page_instructions template
      "schema_block": "...",   # The JSON-LD <script> tail
      "meta_title": "...",
      "meta_description": "...",
      "tone_used": "...",      # For audit log
      "internal_links_used": [...],
      "affiliate_url_marker": "{{AFFILIATE_URL}}",
      "price_marker": "{{PRICE}}",
      "stock_marker": "{{AVAILABILITY}}",
    }
```

The template (`utils/templates.py:product_page_instructions`) embeds every placeholder marker; this function fills in the AI body and leaves the markers untouched so WP can substitute them at render time.

### 4.2 Tone-of-voice per product category

This is the **"100% styr på"** part from Henrik's spec — different products need different registers. Naive AI sites use one voice everywhere; that signals mass production to Google.

Tone is chosen per **category branch**, not per product. Stored as part of the category tree configuration:

```python
# In persistence: /data/category_tree.json
{
  "categories": {
    "electronics/headphones": {
      "name": "Headphones",
      "tone_profile": "technical_friendly",
      "parent": "electronics",
      ...
    },
    "intimate/lubricants": {
      "name": "Lubricants",
      "tone_profile": "intimate_normalizing",
      ...
    },
    "luxury/watches": {
      "name": "Watches",
      "tone_profile": "premium_aspirational",
      ...
    }
  }
}

# Tone profiles defined once in utils/tone_profiles.py
TONE_PROFILES = {
  "everyday_warm":          "...prompt fragment...",
  "technical_friendly":     "...prompt fragment...",
  "premium_aspirational":   "...prompt fragment...",
  "intimate_normalizing":   "...prompt fragment...",
  "beginner_reassuring":    "...prompt fragment...",
  "expert_authoritative":   "...prompt fragment...",
}
```

Each profile is a short paragraph (3-5 lines) appended to the AI prompt's tone section. The `product_page_instructions` template's existing "Tone of Voice — adapt to the product's category" section calls this out — the generator just feeds the profile fragment into the {language} interpolation.

**Why category-level, not product-level?**
- Per-product tone selection requires per-product AI judgement → expensive + inconsistent
- Category-level lets the editor curate ~20-50 profiles total across the site
- Sibling products end up with consistent voice — Google sees coherent category writing
- Override exists for outliers (rare): add `tone_profile_override` to the product feed item

### 4.3 Price + stock decoupling — the contract

This is the single most important rule for affiliate sites:

```
┌──────────────────────────────────────────────────────────────────┐
│  GOLDEN RULE                                                      │
│                                                                   │
│  Body text NEVER contains a literal price.                        │
│  Body text NEVER contains a literal stock status.                 │
│  Both are rendered by the CMS via ACF fields from the feed.       │
│                                                                   │
│  AI body output ONLY uses markers in the schema block:            │
│    {{PRICE}}        - filled by WP at render time                 │
│    {{AVAILABILITY}} - filled by WP at render time                 │
│    {{CURRENCY}}     - per-site env var                            │
│                                                                   │
│  Result: feed refreshes update prices everywhere in seconds       │
│  without touching a single line of body text. No AI re-runs.     │
└──────────────────────────────────────────────────────────────────┘
```

Enforced by:
- The templates explicitly forbid hardcoded prices
- A post-generation validator scans the body for currency symbols + numeric
  patterns matching `\d+[\.,]?\d* (kr|EUR|€|USD|\$|PLN|...)` and rejects the
  output if found anywhere outside the schema block
- The publisher refuses to push if the body contains a literal price

---

## 5. WordPress publishing pipeline

### 5.1 One WP install per (site × language)

Henrik's requirement: "egen wp installation pr. sprog, site". Concrete mapping:

```
Henrik's planning unit          → Railway service       → WP site
─────────────────────────────────────────────────────────────────
Nordic-DK affiliate site (DK)   → mshop-dk-affiliate    → dk.example.com
Nordic-NO affiliate site (NO)   → mshop-no-affiliate    → no.example.com
EU-DE affiliate site (DE)       → eu-de-affiliate       → de.example.com
EU-FR affiliate site (FR)       → eu-fr-affiliate       → fr.example.com
... etc, 1 service per language
```

Each Railway service has these new env vars:

```
WP_API_BASE              = https://dk.example.com/wp-json
WP_API_USER              = wp_publisher
WP_API_APP_PASSWORD      = (WP application password, NOT main login pw)
WP_AFFILIATE_REL         = nofollow sponsored
COMPETITOR_DOMAIN        = e.g. biggest-competitor.dk  (for cross-checks)
```

### 5.2 Publisher module

```
utils/wp_publisher.py                  (NEW — to be built)
  ├─ class WPPublisher:
  │     - authenticate()                # uses WP_API_APP_PASSWORD
  │     - upload_image(url_or_bytes)    # returns attachment_id
  │     - ensure_category(slug, name, parent) -> term_id
  │     - upsert_product(item, body_html, schema_html) -> post_id
  │     - upsert_article(item, body_html, schema_html, type) -> post_id
  │       (type = "article" / "test" / "shopping_guide")
  │     - update_acf_fields(post_id, fields)
  │     - update_rank_math_meta(post_id, title, description, focus_kw)
  │     - sync_price_stock(items)        # ONLY price + stock — never body
  │     - set_internal_links(graph)      # after all posts uploaded, second pass
  │     - delete_or_unpublish(post_id)
  │
  └─ POST_STATE_FILE = /data/wp_state_<site>.json
        {
          "posts": {
            "feed_id_or_slug": {
              "wp_post_id": 12345,
              "wp_url": "https://...",
              "type": "product",
              "status": "draft" | "published" | "needs_review",
              "created_at": "...",
              "last_body_update": "...",   # changes ONLY when AI re-runs
              "last_price_sync": "...",    # changes hourly
              "last_full_audit": "...",
              "current_schema_version": 1,
              "validation_warnings": [...]
            }
          }
        }
```

Every push updates the state file. The Dashboard reads it for "what we have done, when" overviews. The Resume logic reads it for "what's left to do" lists.

### 5.3 WP-side dependencies

The receiving WP install needs:
- WordPress 5.6+ (Application Passwords built-in)
- Advanced Custom Fields Pro (for `price_current`, `price_original`, `stock_status`, `affiliate_url`, `affiliate_url_alt`, `gtin`, `brand`, `product_specs` repeater)
- Rank Math Pro (for meta + breadcrumb schema)
- A custom theme/child theme registering `product`, `test`, and `shopping_guide` custom post types
- An endpoint extension for the hourly price/stock sync (see 5.4)

These are theme/plugin work — covered by `AFFILIATE_SITE_PLAN.md` Phase 3.

### 5.4 Hourly volatile sync — separate endpoint

The full upsert is heavy. Price+stock get their own lightweight endpoint:

```
PUT /wp-json/gsc-seo/v1/volatile
Body: [{"feed_id": "X", "price_current": "...", "stock_status": "..."}, ...]
```

This updates ACF fields only — no post body, no schema regeneration, no cache bust beyond the affected URLs. Cron runs it hourly. Body text is untouched, exactly per the decoupling rule.

### 5.5 Schema injection

The body HTML from the generator already contains a `<script type="application/ld+json">` block at the end (every template adds it). When WP renders:

1. ACF fills in the volatile placeholders (`{{PRICE}}`, `{{AVAILABILITY}}`, `{{AFFILIATE_URL}}`, `{{IMAGE_URL}}`, `{{SKU}}`, `{{BRAND_NAME}}`)
2. The theme renders the breadcrumb separately + injects the `{{BREADCRUMB_JSON}}` it built from the WP taxonomy
3. Rank Math's own schema engine adds Organization + WebSite schema sitewide
4. The page ends up with a complete schema graph that Google validates

The validator that runs pre-publish (see section 7) checks the rendered schema via Google's Rich Results Test API before flipping status from draft to published.

---

## 6. Multi-site / multi-language — one at a time

Henrik's words: "et ad gangen". The system runs one site at a time per Railway service. Branch model from `MULTISITE_SETUP.md` applies:

```
Repo: gsc-seo
├─ main                 (development)
├─ affiliate-dk         (Danish affiliate site)
├─ affiliate-no         (Norwegian affiliate site)
├─ affiliate-de         (German affiliate site)
├─ affiliate-fr         (French affiliate site)
└─ ...                  (one branch per language)
```

Per branch:
- Own `bundled_data/` files (suffix `_<lang>` — same convention as `_se`/`_dk`/`_eu`)
- Own competitor data (one top competitor per language market)
- Own WP credentials (different `WP_API_BASE`)
- Own GSC property (when the new site starts ranking — initially the property won't exist yet, that's fine, the system has demo mode + works without GSC)
- Own product feed source (might be the same affiliate network feed scoped to the language market, or a different merchant entirely)

**`deploy_all_sites.ps1` extends naturally** — add the new branches to the `$branches` array. Henrik already understands this model.

Cross-branch sharing of code happens via `git merge main` — same workflow as today.

---

## 7. Stepwise execution + resume

Henrik's requirement: "jeg skal kunne lave noget - stoppe - og køre igen senere". The system needs durable state for every step.

### 7.1 Current state

The existing pipeline (Run Pipeline view, `views/run_pipeline.py`) is already step-based:
- Each step writes its output to `st.session_state` AND to `/data` via `utils/persistence.py`
- A step's "done" flag (`gsc_data`, `topic_clusters`, `audit_results`, etc.) is checked on load
- Restarting the app reloads state and resumes at the first incomplete step

### 7.2 What needs extending for greenfield sites

Five new persistent state objects:

```
/data/
├─ competitor_intelligence.json    # Built once per competitor import
├─ site_plan.json                  # Category tree + roadmap derived from competitor
├─ generation_log.json             # Per-output: status, timestamps, AI cost
├─ wp_state_<site>.json            # Per-WP-post: post_id, url, sync timestamps
└─ feed_<site>.json.gz             # Latest full product feed
```

`generation_log.json` is the new piece:

```json
{
  "outputs": [
    {
      "id": "category-headphones-bottom-text",
      "type": "category_bottom",
      "target_path": "/electronics/headphones",
      "language": "Danish",
      "status": "draft" | "ai_running" | "ai_failed" | "needs_review" | "validated" | "published",
      "created_at": "2026-05-27T14:00:00Z",
      "last_updated": "2026-05-27T15:30:00Z",
      "ai_cost_usd": 0.42,
      "validation_results": {
        "schema_valid": true,
        "lix_score": 38,
        "ai_detection_score": 0.12,
        "internal_link_count": 8,
        "broken_link_count": 0
      },
      "wp_post_id": 12345,
      "regeneration_count": 0
    },
    ...
  ]
}
```

### 7.3 New Dashboard panel

A new section on `views/dashboard.py`:

```
GREENFIELD PROGRESS — affiliate-de.example.com
├─ Site plan
│   ├─ Categories defined:   45 / 45
│   ├─ Articles planned:     120
│   ├─ Tests planned:         30
│   ├─ Shopping guides:       18
│   └─ Products from feed:  2,400
│
├─ Content created
│   ├─ Category bottom texts:  42 / 45  ████████████████░  93%
│   ├─ Articles:               87 / 120 ███████████░░░░░░  73%
│   ├─ Tests:                  12 / 30  █████░░░░░░░░░░░░  40%
│   ├─ Shopping guides:         6 / 18  █████░░░░░░░░░░░░  33%
│   └─ Product pages:        1,200 / 2,400 ████████░░░░░░░  50%
│
├─ Published to WP
│   ├─ Published:           1,340 / 1,367 created
│   ├─ Drafts pending:         15
│   ├─ Needs review:           12
│   └─ Last publish:        2 hours ago
│
└─ Last activity
    ├─ Hourly price sync:   12 min ago ✓
    ├─ Daily feed refresh:   3 hrs ago ✓
    └─ Cluster health run:   1 day ago ✓
```

Every number is clickable → drills into the relevant view.

### 7.4 Stop / resume safety

- Long generations stream to disk every N items (existing `_save_batch` pattern in the bulk audit)
- A killed AI call leaves status `ai_running` with a timestamp — on restart, items in `ai_running` for >10 minutes are reset to `draft` and the user can retry
- WP push uses idempotent upsert by `feed_id` / `slug` — re-running never duplicates posts
- Price-sync writes a `last_price_sync` timestamp; the next sync only sends deltas

---

## 8. Schema completeness checklist

Every page type that ships gets validated against this checklist (automated via `utils/schema_validator.py` — new). The validator runs after AI generation and before WP push.

| Page type | Required @type | Required graph members | Required placeholders |
|---|---|---|---|
| Article | Article | Article, BreadcrumbList, FAQPage | CANONICAL_URL, PUBLISH_DATE, MODIFY_DATE, AUTHOR_NAME, ORG_NAME, ORG_LOGO, BREADCRUMB_JSON |
| Category bottom | ItemList | ItemList, BreadcrumbList, FAQPage | CATEGORY_URL, CATEGORY_NAME, PARENT_CATEGORY_URL, PARENT_CATEGORY_NAME |
| Product page | Product | Product, Offer, AggregateRating, BreadcrumbList, FAQPage | PRODUCT_NAME, IMAGE_URL, SKU, BRAND_NAME, CURRENCY, PRICE, AVAILABILITY, RATING_VALUE, REVIEW_COUNT, ORG_NAME, CANONICAL_URL, BREADCRUMB_JSON, AFFILIATE_URL |
| Test page | Review | Review (with itemReviewed=Product), BreadcrumbList, FAQPage | (Product placeholders) + REVIEWER_NAME, REVIEW_DATE, SCORE_OVERALL |
| Shopping guide | Article + ItemList | Article, ItemList, HowTo, BreadcrumbList, FAQPage | CANONICAL_URL, AUTHOR_NAME, ORG_NAME, ORG_LOGO, HERO_IMAGE_URL, PUBLISH_DATE, MODIFY_DATE, BREADCRUMB_JSON |

Sitewide (added by Rank Math in WP, not by us):
- Organization
- WebSite + SearchAction
- LocalBusiness (if applicable)

The validator:
1. Parses the AI output's JSON-LD block
2. Confirms every required `@type` is present in `@graph`
3. Confirms every required placeholder marker (`{{NAME}}`) is present where the schema expects a value
4. Confirms FAQ Q/A in schema mirror the visible FAQ exactly (Google deranks divergence)
5. Optional: hits Google's Rich Results Test API for a final validate pass before WP push

---

## 9. What needs building (vs. what's already done)

| Component | Status |
|---|---|
| Templates: article, category bottom | ✅ Already in `utils/templates.py` |
| Templates: product, test, shopping_guide | ✅ Added 2026-05-27 |
| Template selector `select_template(content_type)` | ✅ Added 2026-05-27 |
| Multi-site infra (branch + Railway service per site) | ✅ Existing — see `MULTISITE_SETUP.md` |
| Multi-language prompts (language parameter through every generator) | ✅ Existing — see `utils/lang_prompts.py` |
| Stepwise pipeline + /data persistence | ✅ Existing — see `views/run_pipeline.py` + `utils/persistence.py` |
| Anti-AI-detection + E-E-A-T prompt scaffolding | ✅ Existing — see `utils/ai_generator.py` `human_writing_style()` |
| **Competitor data ingestion** | ❌ Not built — section 2 |
| **Product feed parser** | ❌ Not built — section 3 |
| **Tone-of-voice profiles + per-category routing** | ❌ Not built — section 4.2 |
| **Price/stock decoupling validator** | ❌ Not built — section 4.3 |
| **WP publisher** | ❌ Not built — section 5 |
| **Volatile sync endpoint** | ❌ Not built — section 5.4 |
| **Generation log + greenfield dashboard panel** | ❌ Not built — section 7.2-7.3 |
| **Schema validator** | ❌ Not built — section 8 |

The unbuilt items are roughly 2-3 weeks of focused work. Suggested build order (so each step unblocks the next):

1. **Competitor import** (2.x) — without it we don't know what site to build
2. **Schema validator** (8) — catches template regressions before they ship
3. **Product feed parser** (3) — unlocks product pages + price sync
4. **Tone-of-voice profiles** (4.2) — wires into existing AI generator
5. **WP publisher** (5) — the output destination
6. **Generation log + dashboard panel** (7.2-7.3) — visibility and resume
7. **Volatile sync endpoint** (5.4) — operational layer for price/stock

---

## 10. Cost ballpark per site

Assuming one mid-size site (50 categories, 2000 products, 100 articles, 30 tests, 18 shopping guides) at first launch:

| Item | One-off | Monthly |
|---|---|---|
| Claude API — first generation pass (everything) | ~$200-400 | — |
| Claude API — incremental (regenerations, new content) | — | ~$30-100 |
| Railway hosting (1 service) | — | ~$5 |
| WP hosting (Cloudways) | — | ~$28-56 |
| WP plugins (one-time annual amortized) | — | ~$40 |
| Domain + SSL | ~$15/yr | — |
| Affiliate-network membership (some networks free, some take cut) | varies | — |

Generation cost dominates the first month then drops fast. Hosting + ongoing AI is well under $200/month per site at steady state. Revenue projections in `AFFILIATE_SITE_PLAN.md` section 7.3.

---

## 11. Open questions Henrik should answer before we build

These shape the implementation — better answered up front than retrofitted:

1. **Which affiliate network(s) provide the product feeds?** Format dictates the parser (Awin = XML, Tradedoubler = XML, Daisycon = XML, Skimlinks = JSON, etc.).
2. **Will every language have its OWN merchant**, or do multiple languages send affiliate traffic to the SAME merchant (e.g. EU-wide site → ships to all of EU from one warehouse)?
3. **Which WP hosting provider** — Cloudways/Kinsta/Pressable/something else? Affects deploy + plugin config but not our code.
4. **Top competitor per language** — do we already have Ahrefs + SF data for them, or do we need to capture it for each new language?
5. **How aggressive on schema?** Some affiliate sites avoid Review schema to dodge Google's "stricter for affiliates" policies. Our default is full schema everywhere — confirm before launch.
6. **Affiliate disclosure language** — required by FTC/EU consumer law. Per-language disclosures need legal review before publish.

None of these block starting on the implementation order in section 9 — they decide details inside specific modules.
