# SEO Intelligence Platform · Mshop

CTR Gap Optimizer - finder sider der underperformer ift. organisk position og genererer AI-forbedrede meta-tekster og landingpage-indhold.

## Pipeline

```
GSC API → CTR Gap Analysis → Page Auditor → AI Content Generator → Action Plan
```

## Setup

### 1. Installér dependencies
```bash
pip install -r requirements.txt
```

### 2. Google Search Console Service Account
1. Gå til [Google Cloud Console](https://console.cloud.google.com)
2. Opret et projekt (eller brug eksisterende)
3. Aktivér **Google Search Console API**
4. IAM & Admin → Service Accounts → Opret ny
5. Opret JSON-nøgle og download
6. Tilføj service account email i GSC:
   - GSC → Indstillinger → Brugere og tilladelser → Tilføj bruger
   - Sæt rolle: **Begrænset** (read-only er nok)

### 3. Anthropic API Key
- Hent fra [console.anthropic.com](https://console.anthropic.com)

### 4. Kør appen
```bash
streamlit run app.py
```

## Deploy på Railway

```bash
# Tilføj Procfile:
echo "web: streamlit run app.py --server.port=\$PORT --server.address=0.0.0.0" > Procfile

# Push til Railway
railway up
```

## Filstruktur

```
seo_optimizer/
├── app.py                    # Main entry point + navigation
├── requirements.txt
├── pages/
│   ├── setup.py              # GSC connection + API keys
│   ├── ctr_analysis.py       # CTR gap finder + visualisering
│   ├── page_auditor.py       # Landing page scraping + meta audit
│   ├── content_generator.py  # AI meta + landingpage generering
│   └── action_plan.py        # Prioriteret handlingsplan
└── utils/
    ├── gsc_client.py          # GSC API + CTR benchmark logic
    ├── page_scraper.py        # BeautifulSoup scraping + meta eval
    └── ai_generator.py        # Claude API calls
```

## CTR Benchmarks

Systemet bruger industri-gennemsnitlige CTR-benchmarks per position:

| Position | Forventet CTR |
|----------|--------------|
| 1        | 28.7%        |
| 2        | 15.7%        |
| 3        | 11.0%        |
| 5        | 6.5%         |
| 10       | 3.0%         |

Sider der er >25% under deres benchmark flagges som gaps.

## Features

- **CTR Gap Detection**: Sammenligner faktisk CTR med position-baseret benchmark
- **Estimerede tabte klik**: `(expected_ctr - actual_ctr) × impressions`
- **Meta Audit**: Tjekker title-længde (50-60 tegn), description (140-160 tegn), keyword-tilstedeværelse, CTA-signals
- **AI Meta Variants**: 3 varianter med forskellig strategi (Claude claude-sonnet-4-20250514)
- **Keyword Gap Analyse**: Kortlægger hvilke GSC-keywords der mangler på siden
- **Landingpage Tekst**: Komplet optimeret tekst med H2-struktur, FAQ, buying guide
- **Action Plan**: Prioriteret liste med effort/impact estimater
