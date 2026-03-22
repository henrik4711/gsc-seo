# SEO Intelligence Platform — Teknisk Brief för SEO-specialist

## 1. Systemöversikt

Vi har byggt en AI-driven SEO-analysplattform som kombinerar data från Google Search Console, Ahrefs, och Screaming Frog till en enda pipeline som:

1. Analyserar hela sajten (1153 sidor för mshop.se)
2. Bygger AI-genererade topic clusters baserade på sökdata
3. Identifierar alla strukturella problem (orphan pages, kannibalisering, länkstruktur)
4. Designar den IDEALA sajtstrukturen baserat på keyword-demand
5. Genererar konkreta implementeringsplaner per sida
6. Producerar CMS-redo HTML-text med produkter, interna länkar och FAQ

Systemet körs på Railway (Python/Streamlit) med persistent caching på disk-volym.

---

## 2. Datakällor & Integration

### Google Search Console (API)
- Hämtar query + page-level data (90 dagar)
- 4298 queries, 1153 sidor, 1.78M impressions, 91K klick
- Beräknar CTR-gap mot position-benchmarks
- Identifierar förlorade klick per sida/keyword
- Brand-keywords filtreras automatiskt (keywords som förekommer på 30%+ av sidor)

### Ahrefs (CSV-import)
- Best by Links: referring domains, backlinks, authority score per sida
- Backlinks: individuella backlinks med anchor text och DR
- Organic Keywords: sökvolym och keyword difficulty
- URL-normalisering: http/https, www, trailing slash, tracking params

### Screaming Frog (CSV-import)
- All Pages (internal_html.csv): status codes, word count, crawl depth, inlinks count, meta data
- Används för: orphan page-validering (SF inlinks inkluderar navigation som vår scraper strippar)

### Playwright Browser Scraping
- Headless Chrome renderar JavaScript
- Dismissar cookie consent automatiskt
- Extraherar content från `div.xmx-page-content` (site-specifik selector)
- Resultat: body text, interna länkar med anchor text, H1/H2/H3, schema types, bilder utan alt

---

## 3. Topic Cluster-system

### AI-baserad klustring (ersätter regelbaserad)
Tidigare: word-overlap gruppering → 508 brusiga kluster
Nu: Claude AI analyserar top 150 keywords semantiskt → 31 meningsfulla kluster

Varje kluster definierar:
- **Hub/pillar page** — bred överblick, 3000-5000 ord target
- **Spoke pages** — specifika subtopics, 1500-3000 ord
- **Supporting articles** — blogg/guide-innehåll
- **Search intent** — commercial, informational, mixed
- **Suggested hub URL** — vilken befintlig sida som bör vara hub

### Kluster-hälsokontroll
AI utvärderar hela klustret:
- Vertikal länkning: hub→spoke och spoke→hub
- Horisontell länkning: spoke↔spoke cross-links
- Keyword-distribution: rätt keyword på rätt sida
- Kannibalisering: keywords som konkurrerar inom klustret
- Content gaps: subtopics utan sida

---

## 4. Page Auditor — Vad vi mäter per sida

### Meta-analys
- Title: längd (50-60 chars), keyword i title, CTA-signaler
- Description: längd (140-160 chars), keyword, USP
- Score: 0-100 regelbaserad

### Content-analys
- Word count med page type-targets:
  - Pillar: 3000-5000 ord (Google 2026 best practice)
  - Category: 1500-3000 ord
  - Blog: 1500-3000 ord
- Keyword coverage: vilka target keywords finns/saknas i texten
- Topic coverage: vilka subtopics täcks/saknas
- AI Quality Check: KEEP (7-10), IMPROVE (4-6), REWRITE (1-3)
  Utvärderar: helpfulness, originality, depth, readability, E-E-A-T, cluster fit, standalone value

### Länkanalys
- Interna länkar ut (från content area, exkl. navigation)
- Interna länkar in (korskontrollerat mot SF data)
- Anchor text-kvalitet
- Hub↔spoke länkstatus
- Cross-cluster vs same-cluster ratio

### Teknisk analys
- Schema markup (Product, FAQPage, BreadcrumbList, Organization)
- Page type-klassificering (category, product, blog, faq)
- Backlinks (referring domains, authority score från Ahrefs)
- Canonical URL

---

## 5. Orphan Page-detektion (4 datakällor)

En sida klassificeras som orphan baserat på ALLA tillgängliga data:

| Datakälla | Vad den kontrollerar | Resultat |
|-----------|---------------------|----------|
| Vår scraper | Content-länkar (utan nav) | Links In = 0? |
| SF All Pages | Inlinks inkl. navigation | SF inlinks > 0 → INTE orphan |
| GSC | Impressions | I Google → lägre severity |
| Ahrefs | Referring domains | Har backlinks → lägre severity |

### Severity-nivåer
- **CRITICAL**: Ingen hittar denna sida — inga content-links, inte i nav, inte i Google, inga backlinks
- **HIGH**: Har backlinks men Google visar den inte
- **MEDIUM**: Google hittade den (via sitemap) men inga länkvägar
- **LOW**: Google känner till den, behöver contextual content-länkar för SEO-value

### Aktuellt resultat (mshop.se)
- Från 714 (rådata) → 235 (efter param-normalisering) → färre efter SF-filtrering
- Varje orphan har: förslag på vilken sida som bör länka dit + anchor text

---

## 6. Ideal Site Structure — AI-designad arkitektur

### Hur det fungerar
3 sekventiella AI-anrop:

1. **Cluster design** — Analyserar top 80 keywords, designar 20-40 kluster med hub + spokes
2. **Merge/delete/create** — Vilka sidor ska slås ihop, tas bort, skapas
3. **Keyword assignments** — Vilket keyword hör hemma på vilken sida + estimerad ny score

### Resultat för mshop.se
- 32 rekommenderade kluster (från 508 regelbaserade)
- Estimerad score: 78/100 (från nuvarande 2-3/100)
- 5 sidor att merga
- 4 sidor att ta bort
- 8 nya sidor att skapa

### Gap Analysis
AI jämför nuvarande vs ideal och skapar migreringsplan:
- 4 faser, 16-20 veckor
- Quick wins (noll risk)
- Högriskändringar som kräver 301-redirect-planering
- Estimerad trafikpåverkan: -10-15% initialt, +40-60% inom 8-12 veckor

---

## 7. Implementation Guide — AI-genererade åtgärdsplaner

### Per-sida AI-analys
Claude AI får ALL data om en sida och returnerar en komplett plan:

**Input till AI:**
- URL, title, meta, H1, H2s, word count, page type
- Alla interna länkar med anchor text (befintliga)
- Topic cluster context (pillar/spoke-roll, parent, siblings, children)
- GSC keywords (sorterade efter impressions)
- Missing keywords
- Backlink-data
- Alla sidor på sajten (för korrekta länk-rekommendationer)

**Output:**
- Primary keyword (AI-valt, inte brand)
- Meta title + description (nuvarande vs rekommenderad)
- Steg-för-steg implementeringsplan med tidsestimat
- Nya content-förslag (artiklar att skapa)
- Sektioner att omskriva (med anledning)

### Text-generering
- **Intro text** (ovan produktgrid): 80-150 ord, primary keyword i första meningen
- **Bottom text** (under produktgrid): 800-1500 ord med:
  - Köpguide med H2-sektioner
  - Underkategorier med länkade H3s
  - Expert-rekommendationer (xmx--high-emphasis format)
  - Produktkort med riktiga bilder, priser, URLs
  - FAQ-sektion
  - Trust signals (40+ år, diskret frakt, Trustpilot)
- **Hela artiklar**: 1500-2500 ord HTML med produkter och interna länkar

### Content-regler (inbyggda i AI-prompts)
- E-E-A-T: experience, expertise, authority, trust
- Helpful Content: varje stycke måste hjälpa läsaren fatta beslut
- Cluster fit: pillar överblickar alla child-topics, spoke går djupt
- Länkhygien: bara länkar inom kluster (vertikalt + horisontalt)
- Nudging: normalisering, social proof, friktionsreducering
- INTE: keyword-stuffing, generisk filler, upprepningar

---

## 8. Site-specifik HTML-generering

### Mshop-template
AI genererar HTML som matchar exakt Mshops CMS-format:

```html
<!-- H3 med länkad underkategori -->
<h3 style="font-size:25px"><a href="/sexleksaker/vibratorer">
  <strong>Vibratorer</strong></a></h3>

<!-- Expert-rekommendation -->
<p class="xmx--high-emphasis">– Välj en vibrator om du vill
  uppleva intensiv stimulering med varierade program.</p>

<!-- Produktkarusell -->
<div class="xmx-carousel">
  <div class="xmx-carousel-container">
    <div class="xmx-carousel-elements">
      <a href="/satisfyer-pro-2">
        <div class="xmx-carousel-element">
          <img src="product-image.jpg" alt="Satisfyer Pro 2">
          <div class="xmx-name">Satisfyer Pro 2</div>
          <div class="xmx-short-description">
            Tryckvågor... Pris: 399 kr</div>
        </div>
      </a>
    </div>
  </div>
</div>
```

### Produktdata
- Scrapas live från kategorisidan vid text-generering
- Riktiga produktnamn, bilder, priser, URLs
- Inbäddas som karusell-kort i texten

---

## 9. Validering & Kvalitetssäkring — 5-stegs AI-pipeline

### Steg 1: Sajtvalidering
- AI analyserar hela sajtstrukturen
- Score: 0-100
- Identifierar: orphan pages, kluster-problem, länkstruktur, kannibalisering

### Steg 2: Ideal struktur
- AI designar optimal arkitektur baserat på keyword-demand
- 32 kluster med hub/spoke-arkitektur
- Sidor att merga, ta bort, skapa

### Steg 3: Gap-analys
- AI jämför nuvarande vs ideal
- 4-fas migrationsplan med risk-bedömning
- Estimerad trafik-impact

### Steg 4: Planvalidering
- AI kontrollerar alla implementeringsplaner mot problemen
- Coverage: täcker planerna ALLA kritiska problem?
- Konflikter: motarbetar några planer varandra?
- Sekvens: rätt ordning?
- Saknade åtgärder: vad ingen plan adresserar

### Steg 5: Manuell implementering med Dashboard
- Dashboard visar exakt vad du ska göra härnäst
- Fas-progress (Phase 0-4)
- Top 20 sidor sorterade efter impact
- Status per sida: NOT STARTED / PLAN READY / TEXT READY

---

## 10. Teknisk Stack & Arkitektur

### Stack
- **Frontend**: Streamlit (Python) — intern tool, inte SaaS
- **AI**: Anthropic Claude Sonnet (alla analyser + content-generering)
- **Scraping**: Playwright (headless Chrome) med requests-fallback
- **Data**: GSC API, Ahrefs CSV, Screaming Frog CSV
- **Lagring**: Railway-volym med individuella JSON-filer per AI-resultat
- **Hosting**: Railway (Docker container)

### Caching-arkitektur
```
/data/
├── gsc_data.csv              # GSC-data (1.14 MB)
├── audit_results.json        # Alla scrapade sidor (1.64 MB)
├── topic_clusters.json       # AI-kluster (3.75 MB)
├── sf_pages.csv              # Screaming Frog (13.88 MB)
├── page_authority.csv        # Ahrefs (0.25 MB)
└── ai_cache/                 # AI-resultat (individuella filer)
    ├── _quality_a1b2c3.json  # Quality check per sida
    ├── _ai_plan_d4e5f6.json  # Implementation plan per sida
    ├── _site_validation.json # Sajtvalidering
    ├── _ideal_structure.json # Ideal struktur
    └── ... (2000+ filer)
```

### URL-normalisering
- `normalize_url()`: http→https, strip www, trailing slash, lowercase
- `stable_hash()`: MD5-baserad (deterministisk över restarts, till skillnad från Python's `hash()`)
- `_norm_url()`: strip query params + fragments för jämförelse
- `_clean_body_text()`: strip navigation/meny/trust-bar från body text

### Pipeline-flöde
```
GSC Data ──→ AI Clusters ──→ Page Audit ──→ AI Quality Check
                                    ↓
                            Site Map Export
                                    ↓
                        ┌── Validation (3/100)
                        ├── Ideal Structure (78/100)
                        ├── Gap Analysis (migration plan)
                        └── Plan Validation (coverage check)
                                    ↓
                            Implementation Guide
                                    ↓
                    ┌── Generate intro text
                    ├── Generate bottom text (with products)
                    ├── Generate full articles
                    └── Generate schema markup
                                    ↓
                              Copy to CMS
```

---

## Sammanfattning: Vad gör detta system unikt?

1. **Cluster-aware AI** — Ingen annan tool förstår att varje sida existerar i ett kluster-hierarki och att rekommendationer måste passa in i den strukturen

2. **End-to-end pipeline** — Från rå GSC-data till CMS-redo HTML med produkter i ett enda system

3. **AI-first analys** — Regelbaserade SEO-verktyg (keyword density, word count) ger opålitliga resultat. Claude AI utvärderar som Google gör — med förståelse, inte mönstermatchning

4. **5-stegs validering** — Diagnos → Design → Gap → Plan → Verifiering. Ingen annan tool gör alla fem

5. **Sajt-specifik output** — Genererar HTML i exakt det format CMS:et kräver, med riktiga produkter, bilder och priser

6. **Alla datakällor integrerade** — GSC + Ahrefs + Screaming Frog + live scraping i en enda analys

### Nuvarande status (mshop.se)
- Sajtstruktur-score: 3/100 (target 78/100)
- 31 AI-genererade topic clusters
- 235 orphan pages identifierade med fix-förslag
- Implementeringsplaner genererade för top 10 sidor
- 4-fas migrationsplan: 16-20 veckor, estimerad +40-60% organisk trafik
