# SEO Intelligence Platform — Brugermanual

**Version:** 1.0 · Maj 2026
**Sprog:** Dansk
**Målgruppe:** Helt nye brugere — ingen forudgående erfaring med systemet kræves.

Dette dokument er en komplet manual til SEO Intelligence Platform. Læs det fra start til slut første gang du bruger systemet. Bagefter kan du bruge indholdsfortegnelsen til at finde præcis det du har brug for.

---

## Indholdsfortegnelse

**Del 1 — Hvad systemet er og kan**
- 1.1 Hvad er SEO Intelligence Platform?
- 1.2 Hvad gør systemet konkret?
- 1.3 Hvilke data trækker systemet ind?
- 1.4 Hvad bruges AI (Claude) til?
- 1.5 Hvad får man ud i den anden ende?
- 1.6 Begrænsninger og hvad systemet IKKE gør

**Del 2 — Kom i gang (første gang)**
- 2.1 Login
- 2.2 Sidebar og navigationsprincip
- 2.3 Begrebsoversigt for begyndere
- 2.4 Den anbefalede rækkefølge

**Del 3 — Trin-for-trin gennemgang af hver side**
- 3.1 Dashboard
- 3.2 ⚡ Run Pipeline (ét-klik kørsel)
- 3.3 ⚡ Quick Wins
- 3.4 🗺 Topical Map
- 3.5 🧹 Site Cleanup
- 3.6 Trin 1 — Setup & Connect
- 3.7 Trin 2 — Upload Ahrefs
- 3.8 Trin 3 — CTR Analysis
- 3.9 Trin 4 — Cannibalization
- 3.10 Trin 5 — Topic Clusters
- 3.11 Trin 6 — Page Auditor
- 3.12 Trin 7 — Internal Linking
- 3.13 Trin 8 — Missing Keywords
- 3.14 Trin 9 — New Articles
- 3.15 Trin 10 — Cluster Health
- 3.16 Trin 11 — Content Generator
- 3.17 Trin 12 — Site Map
- 3.18 Trin 13 — All Tasks
- 3.19 Trin 14 — Implementation

**Del 4 — Alle indstillinger og hvorfor de findes**
- 4.1 Globale indstillinger (Setup & Connect)
- 4.2 Site URL Patterns
- 4.3 Indstillinger pr. side
- 4.4 Filtre der findes igen og igen
- 4.5 Reset og refresh — hvornår bruges hvad?

**Del 5 — Typiske arbejdsforløb**
- 5.1 Førstegangskørsel (komplet site-analyse)
- 5.2 Ugentlig vedligeholdelse
- 5.3 "Jeg har 30 minutter — hvad gør jeg?"
- 5.4 Når en konkret side skal forbedres

**Del 6 — Fejlfinding og FAQ**
- 6.1 Login virker ikke
- 6.2 GSC vil ikke forbinde
- 6.3 AI giver fejl eller tomme svar
- 6.4 Et trin er gråt og kan ikke køres
- 6.5 Resultater ser forkerte ud

**Del 7 — Ordliste**

---

# Del 1 — Hvad systemet er og kan

## 1.1 Hvad er SEO Intelligence Platform?

SEO Intelligence Platform er et internt SEO-værktøj bygget specifikt til e-commerce. Det kombinerer tre datakilder — Google Search Console, Ahrefs og Screaming Frog — med Anthropic Claude AI, og fortæller dig **præcis hvad der skal ændres på hver side på dit website**, hvorfor, og **genererer det indhold du skal indsætte**.

Forskellen fra traditionelle SEO-værktøjer (Semrush, Ahrefs, Surfer):

| Traditionelle værktøjer | Dette system |
|--|--|
| Viser data og dashboards | Fortæller dig hvad du skal gøre |
| Du tolker selv og handler | Systemet skriver det færdige indhold |
| Analyserer sider isoleret | Forstår klyngestruktur (pillar/spoke) |
| Generisk rådgivning | Specifik HTML klar til CMS |

Systemet kører som webapp i din browser. Hosting er Railway og data ligger i et persistent volume — alt du laver gemmes automatisk og overlever genstart.

## 1.2 Hvad gør systemet konkret?

Systemet løser ti hovedopgaver:

1. **Henter dine data** fra Google Search Console (GSC) automatisk via API — du behøver ikke at eksportere noget.
2. **Identificerer dårlig CTR** — sider der rangerer godt men ikke får klik, så du kan rette meta-tekster og hente "tabte klik".
3. **Finder kannibalisering** — når to af dine egne sider konkurrerer på samme søgeord og stjæler klik fra hinanden.
4. **Bygger emneklynger (topic clusters)** — AI'en grupperer alle dine søgeord i 20-40 emner og identificerer pillar-sider og spoke-sider.
5. **Auditerer hver side dybdegående** — meta, indhold, ord, links, schema, billeder, intern struktur.
6. **Finder manglende interne links** — både links der mangler INDAD og links der bør tilføjes UDAD.
7. **Finder manglende søgeord** — keywords du rangerer på, men som ikke findes i sidens tekst.
8. **Foreslår nye artikler** — emner hvor du har huller i klyngen.
9. **Genererer færdigt indhold** — meta-titler, meta-beskrivelser, bundtekster, hele blogartikler — i præcis det sprog og den tone du sætter op.
10. **Leverer en prioriteret handlingsliste** — så du ved hvad du skal gøre først.

## 1.3 Hvilke data trækker systemet ind?

### Google Search Console (live via API)
Hver enkelt kombination af søgning + side med klik, eksponeringer, CTR og position. Typisk 4.000+ søgninger på 1.150+ sider. 90 dages rullende vindue. **URL'erne normaliseres automatisk** (https, ingen www, ingen parametre, ingen trailing slash, lowercase) så data altid matcher på tværs af kilder.

### Ahrefs (CSV-eksport, 3 filer)
- **Best by Links** — autoritet på sideniveau (referring domains, backlinks, DR, authority score)
- **Backlinks** — alle individuelle backlinks med kilde-URL, anchor text, DR, dofollow/nofollow
- **Organic Keywords** — søgeord med søgevolumen, KD, CPC og **søgehensigt** (informational/commercial/transactional)

### Screaming Frog (CSV-eksport, 2 filer)
- **All Pages** — hver crawlet URL med status code, title, meta description, H1, ordtælling, crawl depth, canonical, indexability, response time, near-duplicate matches
- **All Inlinks** — hvert internt link med source, target, anchor text (kan være 2 GB+, parses i bidder)

### Live scraping (BeautifulSoup + requests)
Når Page Auditor kører, henter den selv siderne live og udtrækker title, meta, H1-H3, body-tekst (op til 8.000 tegn), interne links, eksterne links, billeder uden alt-tekst, og schema-typer (JSON-LD). Kategorisider får ekstra analyse: introtekst (over produktgrid) og bundtekst (under grid), produkttælling, FAQ-detektion, buying guide-detektion.

### Bundlede data
SF- og Ahrefs-eksporter ligger som komprimerede `.gz`-filer i `bundled_data/` i git. Første gang appen starter, pakkes de automatisk ud i `/data/`. Du behøver derfor ikke at uploade noget for at komme i gang — det er allerede der.

## 1.4 Hvad bruges AI (Claude) til?

Systemet bruger Anthropic Claude Sonnet 4 til disse funktioner:

| Funktion | Hvad AI'en gør | Token-budget |
|--|--|--|
| Topic clustering | Grupperer 4000+ GSC-søgninger i 20-40 emner | 8.000 |
| Indholdskvalitet | KEEP/IMPROVE/REWRITE-dom på 7 dimensioner | 3.000 |
| Implementation plan | Trin-for-trin SEO-plan pr. side | 3.000 |
| Cluster health | Evaluerer hele klyngens linking og dækning | 4.096 |
| Bundtekst kategori | Genererer CMS-klar HTML med E-E-A-T, FAQ, produkter | 6.000 |
| Blogartikel | Fuld artikel med produktanbefalinger | 8.000 |
| Meta-forslag | 3 varianter af title + description | 2.000 |
| Content audit | Keyword gap-analyse + strukturforslag | 2.000 |
| Site validation | Samlet sundhedsscore for arkitekturen | 3.000 |
| Ideel struktur | Forslag til merges, deletes, creates | 4.000 |
| Keyword-filtrering | AI udvælger relevante keywords pr. side | 1.500 |

**Anti-hallucinationsregler.** Alle AI-prompts der vurderer en sides tilstand indeholder regler om at AI'en KUN må basere udsagn på data der gives med, KUN må citere faktiske værdier (ikke opfinde problemer), og IKKE må sige "mangler" hvis title/meta findes. Når AI'en kun ser delvis tekst, vises et "fragment flag" så både AI og bruger ved at vurderingen er begrænset.

## 1.5 Hvad får man ud i den anden ende?

Output fra systemet falder i fire kategorier:

**1. Per-side implementeringsplan**
- Primært søgeord identificeret
- Optimeret meta-title + description (eller "current OK")
- Trin-for-trin handlinger med tidsestimater (meta, indhold, links, schema, struktur)
- Specifik tekst der skal tilføjes, hvilken H2, hvor på siden
- Links der skal tilføjes (med rigtige URL'er fra dit site)
- Links der skal **fjernes** (peger uden for emneklyngen)

**2. Færdigt genereret indhold**
- Kategori-bundtekst: CMS-klar HTML med E-E-A-T, FAQ, buying guide, produktkaruseller, interne links
- Blogartikler: Fuld HTML med ekspertvinkel, produktkort, interne links
- Alt bruger reelle produktdata (navne, priser, billeder, URL'er)
- Alle interne links bruger rigtige URL'er fra dit site — aldrig opfundne

**3. Kannibaliseringsløsninger**
- Brand-keywords filtreret væk
- Hensigtsbevidst merge-rådgivning: forskellig hensigt = "differentier og krydslink", samme hensigt = redirect med backlink-informeret vinder
- Trin-for-trin merge-instruktioner

**4. Crawl-/indekseringsproblemer**
- Brudte links, redirect-kæder, forældreløse sider (severitetsklassificeret)
- Canonical mismatches, faceted URLs (Magento 1.9-specifikt)
- Near-duplicate content med konsolideringsråd
- Ikke-indekserbare sider, tynde sider, dybe sider, langsomme sider

## 1.6 Begrænsninger og hvad systemet IKKE gør

Vær ærlig over for dig selv om hvad værktøjet ikke kan:

| Begrænsning | Konsekvens | Hvad du kan gøre |
|--|--|--|
| Klynger bygges kun fra GSC-søgninger | Sider der ikke rangerer endnu er "usynlige" for klyngen | Ahrefs-keywords sendes som supplement; suppler manuelt |
| AI er ikke-deterministisk | Samme side kan få lidt forskellige anbefalinger | Kør igen for at få "second opinion" |
| Ingen semantisk NLP | Keyword-matching er string-baseret, ikke betydningsbaseret | AI'ens semantiske validering er andet lag |
| Body-tekst capped ved 4.000/8.000 tegn | Lange pillar-sider analyseres kun delvist | Fragment flag advarer AI og bruger |
| Ingen konvertering/omsætning | Kan ikke vægte sider efter forretningsværdi | Bruger eksponeringer + klik som proxy |
| Selvrefererende klynger | Systemet bygger og evaluerer egne klynger | Definér klyngerne manuelt, lad systemet evaluere |

---

# Del 2 — Kom i gang (første gang)

## 2.1 Login

Når du åbner appen møder du en password-prompt:

```
🔒 SEO Intelligence Platform
Password: [______________] [Login]
```

Password sættes af administratoren via Railway-miljøvariablen `APP_PASSWORD`. Appen **nægter at starte** hvis variablen ikke er sat — det er et bevidst sikkerhedsvalg, så data aldrig ved en fejl bliver offentligt eksponeret.

**Vigtigt:** Login er pr. browser-session. Hvis du lukker browseren skal du logge ind igen. Det betyder også at lange AI-batches (timer) skal køre i en åben fane — luk ikke browseren midt i.

## 2.2 Sidebar og navigationsprincip

Når du er logget ind ser du:

- **Top-bar** — titel "SEO Intelligence Platform"
- **Venstre sidebar** — navigationsmenu med 19 sider
- **Hoveddel** — den valgte sides indhold

### Sidebar-struktur

```
SEO PIPELINE
FOLLOW THE STEPS IN ORDER

  Dashboard
  ⚡ Run Pipeline
  ⚡ Quick Wins
  🗺 Topical Map
  🧹 Site Cleanup
  1. Setup & Connect
  2. Upload Ahrefs
  3. CTR Analysis
  4. Cannibalization
  5. Topic Clusters
  6. Page Auditor
  7. Internal Linking
  8. Missing Keywords
  9. New Articles
  10. Cluster Health
  11. Content Generator
  12. Site Map
  13. All Tasks
  14. Implementation

PIPELINE 7/19
✓ Setup
✓ Upload Ahrefs
✓ CTR Analysis
>> Cannibalization     ← næste skridt
   ...

NEXT STEP
Find keyword conflicts

CACHED ON DISK · 234 MB · 18 datasets
```

**Læsenøgle:**
- ✓ (grøn) = trinnet er fuldført, data findes
- >> (lilla) = anbefalede næste skridt
- (gråt) = endnu ikke kørt
- Tallet 7/19 = hvor langt du er

**Tip:** Du KAN klikke ind på et hvilket som helst trin når som helst, men sider der mangler data viser tydeligt hvilke trin du skal køre først. Systemet håndterer afhængighederne — du behøver ikke at huske rækkefølgen.

## 2.3 Begrebsoversigt for begyndere

| Begreb | Forklaring |
|--|--|
| **GSC** | Google Search Console — Googles eget værktøj der viser hvilke søgninger der bringer trafik til dit site |
| **Impressions** | Antal gange en søgning viste din side i resultaterne |
| **CTR** | Click-Through Rate — % af impressions der blev til klik |
| **Position** | Gennemsnitlig placering i Google for en søgning (1 = top) |
| **Cannibalization** | Når to af DINE egne sider konkurrerer på samme søgeord |
| **Topic cluster** | Gruppe relaterede sider: pillar (hub) + spokes (støttesider) |
| **Pillar / Hub** | Hovedsiden i en klynge — bredt emne, mange interne links ind |
| **Spoke** | Støtteside under en pillar — specifikt undertema |
| **Authority** | Backlink-kvalitet (referring domains × DR) |
| **DR** | Domain Rating (Ahrefs) — domænets samlede autoritet 0-100 |
| **Meta title** | Sidens titel som vises i Google (50-60 tegn) |
| **Meta description** | Beskrivelse under titlen i Google (140-160 tegn) |
| **Schema** | JSON-LD struktureret data der hjælper Google forstå siden |
| **Orphan page** | Side uden indgående interne links |
| **Faceted URL** | Filter-URL fra fx kategorisider (`?color=red&size=large`) |
| **Canonical** | "Den officielle" URL hvis flere URL'er viser samme indhold |
| **Crawl depth** | Antal klik fra forsiden til en side (lav = bedre) |
| **E-E-A-T** | Googles kvalitetsmål: Experience, Expertise, Authoritativeness, Trust |

## 2.4 Den anbefalede rækkefølge

Første gang du bruger systemet:

1. **Setup & Connect** — forbind GSC + indtast API-nøgle (5 min)
2. **Run Pipeline → Run All** — kør alt automatisk (30-60 min, ingen overvågning kræves)
3. **Dashboard** — se overblik når pipeline er færdig
4. **Quick Wins** — fix de første 5-10 sider med højest impact
5. **Action Plan (Implementation)** — gennemgå AI-planer side for side

For ugentlig brug: gå direkte til **Dashboard** → følg "Next Step"-anbefalingen.

---

# Del 3 — Trin-for-trin gennemgang af hver side

## 3.1 Dashboard

**Hvad:** Read-only overblik over hele dit site. Viser sundhedsscore, kritiske problemer, hvad du skal gøre nu, og fremgang gennem alle faser.

**Hvad du ser:**
- **Site Health Score** (0-100) — sammenligning af nuværende vs. mål
- **Critical Issues** — liste over kritiske problemer fra site validation
- **Next Action** — præcis hvad du skal lave + link til den side hvor det gøres
- **Phase Progress** — 4 faser med fuldførelsesprocent
- **Top 20 Pages by Impact** — sider sorteret efter tabte klik

**Knapper:** Ingen handlingsknapper — kun navigationslinks til Phase-specifikke sider.

**Indstillinger:** Ingen — alt beregnes automatisk.

**Krav før den giver mening:** GSC-data + Page Audit + Site Validation.

**Brug det til:** Det første du tjekker hver dag. Hvis "Next Action" siger noget — gør det.

## 3.2 ⚡ Run Pipeline (ét-klik kørsel)

**Hvad:** Centralt kontrolpanel hvor du kan starte hele pipelinen — eller individuelle trin — fra ét sted. Viser status (færdig/ikke kørt) og hvor gammel hver datakilde er.

**Hvad du gør:**
- Klik **Run All** for at køre trin 1-10 i rækkefølge — tager 30-60 min afhængigt af site-størrelse
- Eller klik enkeltvis på hvert trin hvis du kun vil opdatere ét
- Hvert trin viser ✓ Done eller ✗ Not run og alder på data

**Knapper:**
- **Run All** — kører hele pipelinen
- Pr. trin: **Run step X** — kører kun det trin

**Indstillinger:** Ingen pr. side — hvert trin har sine egne parametre i sin egen view.

**Hvornår bruges Run Pipeline:**
- Førstegangsopsætning
- Når GSC-data er over en uge gammel
- Når du har lavet store ændringer på sitet og vil have en frisk vurdering

**Vigtigt:** Pipelinen kan tage lang tid (30-60 min). Hold browser-fanen åben mens den kører — appen er pr. session, lukker du fanen mister du fremdriften (selvom AI-resultater gemmes løbende).

## 3.3 ⚡ Quick Wins

**Hvad:** Konsolideret view der viser site-dækkende prioriteter (ikke-klyngede sider, tynde sider, manglende blog-indhold, klyngeudvidelse). Du arbejder med én side ad gangen og får konkrete forslag.

**Hvad du gør:**
- Vælg URL fra dropdown
- Eller filtrér prioritetshandlinger efter kategori (unclustered, thin, blog gaps, cluster expansion)
- Klik **Generate** på de funktioner du vil have (meta, bundtekst, ny artikel, etc.)
- Approve/reject AI-forslag
- Kopiér færdigt indhold til CMS

**Knapper pr. handling:**
- **Assign to cluster** — AI foreslår bedste klyngematch for en ikke-klynget side
- **Mark as no cluster** — markér side som bevidst forældreløs (fx FAQ)
- **Generate meta suggestions** — 3 varianter af title + description
- **Generate bottom text with products & links** — fuld bundtekst med produkter
- **Rewrite intro** — AI omskriver intro med manglende keywords
- **Generate FAQ** — FAQ-sektion til manglende undertemaer

**Indstillinger:**
- **Tone of voice** — Professional / Discrete / Energetic / Informative
- **Meta variants count** — 1-5 (slider)
- **Custom keywords** — komma-separeret liste der overskriver auto-keywords

**Krav:** Page Audit (trin 6) + Topic Clusters (trin 5) + Anthropic API-nøgle.

**Pris:** $0,05-$0,50 pr. side.

## 3.4 🗺 Topical Map

**Hvad:** Visuelt diagram af hver emneklynge som et directed graph. Du kan SE hvilke sider der hører sammen, hvilke links der findes (grøn), og hvilke der mangler (rød).

**Hvad du ser:**
- Hub-side i centrum (større node)
- Spoke-sider omkring (mindre noder)
- **Grønne linjer** = link findes (bekræftet via Screaming Frog eller audit)
- **Røde linjer** = link mangler, bør tilføjes
- Anchor text vises på linjer
- Topkeywords vises på noder

**Hvad du gør:**
- Vælg klynge fra dropdown
- Zoom ind/ud
- Klik **View linking recommendations** for at se konkrete handlinger

**Indstillinger:**
- Cluster-dropdown
- Zoom-kontroller

**Krav:** Topic Clusters (trin 5) + Page Audit (trin 6). Screaming Frog inlinks er valgfri men giver mere præcise linkdata.

**Brug det til:** Hurtigt at se "hvilke links mangler i denne klynge?" uden at læse en tabel.

## 3.5 🧹 Site Cleanup

**Hvad:** Alle site-dækkende oprydningshandlinger ét sted: merges, deletes, redirects, noindex, klyngeopgaver. Hver handling kommer med begynder-venlig forklaring og Magento-specifik trin-for-trin guide.

**Faner:**

1. **Merge / Consolidate** — hvis kannibalisering er fundet
   - Viser konkurrerende sidepar + anbefaling (KEEP winner, REDIRECT loser)
   - Backlink-risiko (HIGH/MEDIUM/LOW)
   - Trin-for-trin Magento-instruktioner

2. **Delete / 301 Redirect** — forældreløse, meget tynde, brudte sider
   - Severity-badge (CRITICAL/HIGH/MEDIUM/LOW)
   - Instruktion: "I Magento → Catalog → Pages → Delete" eller "Sæt 301 til forælder"

3. **Noindex** — faceted URLs, near-duplicates, salgssider
   - Noindex-kode klar til kopi+paste

4. **Unclustered Pages** — sider ikke i nogen klynge
   - Klyngeforslag
   - Klik for at tildele eller markere "ingen klynge nødvendig"

**Indstillinger:**
- Severity-filter
- Sidetypefilter (category/product/blog/etc.)

**Krav:** Cannibalization (trin 4) + Screaming Frog crawl-issues (trin 3) + Page Authority (valgfri).

**Pris:** Ingen for visning. AI bruges kun ved klik på "Assign to cluster".

## 3.6 Trin 1 — Setup & Connect

**Hvad:** Den vigtigste konfigurationsside. Her forbinder du GSC, indtaster API-nøgle, beskriver dit site, vælger sprog, og kan nulstille data.

### Sektion: Google Search Console

To forbindelsesmetoder:

**A. Service Account JSON (anbefalet, produktion)**
1. Google Cloud Console → IAM → Service Accounts
2. Opret nøgle (JSON-format)
3. Tilføj service account-email i GSC under Settings → Users and permissions
4. Upload JSON-filen i UI'et — ELLER sæt `GSC_CREDENTIALS_JSON`-env var i Railway

Når forbundet, vis en dropdown med alle GSC-properties du har adgang til. Vælg dit site.

**B. Demo mode**
Genererer syntetisk GSC-data så du kan teste systemet uden rigtige data. Klik **Activate Demo mode**.

### Sektion: Hent GSC-data

Når GSC er forbundet:
- **Days back** — 7-180 dage (default: 90)
- **Min. impressions** — 5-500 (default: 10) — filtrerer støj væk

Klik **Fetch GSC Data**. Tager 30 sek - 2 min afhængigt af site-størrelse. Resultatet gemmes på disk og indlæses automatisk ved næste login.

### Sektion: Claude AI (Anthropic)
Indtast Anthropic API-nøgle. Eller sæt `ANTHROPIC_API_KEY`-env var. Uden den virker INGEN AI-funktioner.

### Sektion: Site Context
Beskriv din webshop i fri tekst (én lille paragraf). AI'en bruger det til at tilpasse meta-tekster og indhold. Eksempel:

> An online store selling consumer electronics. We carry headphones, laptops, smartwatches. Tone: helpful, knowledgeable, friendly. USPs: Free shipping, easy returns, expert reviews.

Vælg **Primary language for generated content** fra dropdown (Engelsk, Dansk, Svensk, Norsk, Tysk, etc.). Klik **Save settings**.

### Højre kolonne: System Status
Viser real-time status:
- GSC Connected (grøn/rød)
- Claude AI (Ready/Missing)
- Site context (Configured/Default)
- Hver env var (Set/Not set)

### Sektion: Site URL Patterns
Konfigurer URL-mønstre der bruges til sidetypeklassificering (category/blog/info/etc.). Default virker for de fleste engelsksprogede sites — for dansk/svensk/norsk skal du muligvis tilføje sprog-specifikke ord.

**Knap: Load preset** — vælg fra fx "Swedish e-commerce" preset.

**Manuel redigering (expander):**
- Extra category path patterns
- Extra info/corporate page patterns
- Flat URL category keywords
- Local/store location patterns
- Extra faceted URL query parameters

Komma-separerede lister. Gemmes med **Save site patterns**. Du skal køre Page Auditor igen for at den nye klassificering anvendes.

### Knap: Refresh bundled data (SF + Ahrefs)
Re-unpacker SF + Ahrefs `.gz`-filer fra `bundled_data/`. **Bevarer:** audit results, AI quality verdicts, GSC data, cannibalization, alle trin 7+ analyser. Brug efter `git push` af friske bundled-filer.

### Knap: RESET ALL DATA
**Farligt.** Rydder alt cached data og tvinger frisk start. Kun credentials + settings + auth bevares. Brug kun hvis du vil starte helt forfra eller har korrupt data.

## 3.7 Trin 2 — Upload Ahrefs (Link Authority)

**Hvad:** Upload backlink + crawl-data. Beregner page authority, finder brudte links, forældreløse sider og en risikomappe (hvilke sider er "for værdifulde" til at ændre uden eftertanke).

**Hvad du uploader (eller auto-loader fra `data/`):**
- **Best by Links** (Ahrefs Site Explorer → Best by Links)
- **Backlinks** (Ahrefs → Backlinks, filter: Live + Dofollow)
- **Organic Keywords** (Ahrefs, valgfri — supplerer GSC)
- **All Inlinks** (Screaming Frog → bulk export)
- **All Pages** (Screaming Frog → crawl export)

**Knapper:**
- **Build Page Authority** — beregner autoritetsscore pr. side
- **Analyze Crawl Data** — finder brudte links, forældreløse, langsomme, faceted, canonicals, duplikater, redirect-kæder, tynde sider

**Output:**
- **Authority Table** — 10-point score pr. side, referring domains, backlinks
- **Risk Map** — sider markeret HIGH (rør ikke), MEDIUM (forsigtig), LOW (sikker at optimere)
- **Backlink Overview** — top backlinks efter DR, anchor text-fordeling
- **Crawl Issues** — brudte (4xx/5xx), forældreløse, langsomme, faceted, canonical, duplikater, kæder, tynde, dybe sider

**Indstillinger:** Auto-detection fra `data/` ELLER manuel upload.

**Pris:** Ingen. Ren databehandling.

## 3.8 Trin 3 — CTR Analysis

**Hvad:** Finder søgeord hvor du rangerer godt (position 1-20) men har lav CTR. Det er de hurtigste klikgevinster — tweak meta-teksten og du henter klik.

**Filtre (alle sliders):**
- **CTR Gap Threshold** (default -25%) — vis kun søgninger med CTR mindst dette under forventet
- **Min. impressions** — filtrer støj
- **Max. position** — fokus på top 20
- **Min. lost clicks** — vis kun søgninger der taber >N klik/måned

**Output:**
- **Query-level table** — side, søgeord, position, faktisk vs. forventet CTR, estimerede tabte klik
- **Page-level table** — aggregeret pr. side med top-søgeord
- **Scatter plot** — position vs. CTR
- **Bar chart** — top 15 sider efter tabte klik
- **Add to Audit Queue** — vælg top-sider og send dem til Page Auditor

**Krav:** GSC-data (trin 1).

**Pris:** Ingen.

## 3.9 Trin 4 — Cannibalization

**Hvad:** Finder søgeord hvor flere af DINE sider rangerer og dermed splitter klikkene. Anbefaler om der skal merges/redirectes baseret på hensigt.

**Knap:** **Analyze Cannibalization** — kør detektion.

**Filtre:**
- Min. impressions
- Severity (severe/moderate/mild)

**Output:**
- Total kannibaliserede søgeord, antal severe, tabte klik, sider involveret
- **Pages with Most Conflicts** — hvilke sider konkurrerer mest
- **Page Pairs** — expandere der viser to konkurrerende sider, fælles søgeord, anbefaling (MERGE vs. DIFFERENTIATE baseret på hensigt)
- **All Keywords** — detaljeret keyword-liste med anbefalet vinder + merge-handling

**Intelligens:**
- Brand-søgeord filtreres væk (domænenavn + navigationssøgninger)
- Forsiden involveret = "redirect aldrig til forside"
- Forskellig hensigt (blog vs. kategori) = "merge ikke, differentier + krydslink"
- Samme hensigt = KEEP/REDIRECT med backlink-informeret vindervalg

**Krav:** GSC-data + Page Authority (valgfri).

**Pris:** Ingen.

## 3.10 Trin 5 — Topic Clusters

**Hvad:** AI organiserer alle dine søgeord i 40-80 meningsfulde emnegrupper. Identificerer hub-sider (pillars) og spoke-sider. Finder huller (emner uden side).

**Knap:** **Build AI Clusters (anbefalet)** — Claude analyserer søgeord semantisk.

**Indstilling:**
- **Max keywords slider** — 250-5000 (default 500)
  - 500 = ~1 min, ~$0,10
  - 1000-3000 = 2-8 min, højere pris
  - Højere tal = færre uklyngede sider men dyrere og langsommere

**Output:**
- 40-80 klynger, hver med:
  - Klyngenavn (emnet)
  - Antal sider
  - Antal søgeord
  - Hub-side (pillar)
  - Spoke-sider (støttesider)
- **Content gaps** — emner uden side
- **Content roadmap** — liste over nye artikler der bør skrives + estimeret trafikmulighed
- **Page-to-cluster mapping** — bruges af alle andre views

**Krav:** GSC-data (trin 1).

**Pris:** $0,10-$1,00 pr. kørsel. Streamet — ingen timeout-risiko.

## 3.11 Trin 6 — Page Auditor

**Hvad:** Scraper hver side på dit website, udtrækker meta/indhold/struktur, vurderer kvalitet mod søgeord, finder problemer. Det største og vigtigste trin.

**Knapper:**
- **Re-scrape ALL pages (force)** — re-scanner alle sider i GSC. Brug efter du har rettet sider.
- **Scrape NEW pages only** — kun nye sider der ikke er auditerede endnu.
- **Quick audit** — kun meta + struktur, dropper deep content analysis.
- **Detailed audit** — fuld analyse inkl. content gaps, keyword coverage, linking, schema.

**Indstillinger:**
- Scraping mode (Quick/Detailed)
- Pagination 10 sider/side

**Output pr. side:**
- **Page type** — CATEGORY / PRODUCT / BLOG / FAQ / UNKNOWN
- **Meta scores** — Title/description kvalitet (0-100)
- **Content score** — keyword coverage, læsbarhed, struktur (0-100)
- **Issues** — manglende H1, tynd content, ingen keywords i intro, etc.
- **Target keywords** — top-søgeord fra GSC for denne side
- **Linking analysis** — interne links til stede + anbefalede manglende
- **Content audit** — keyword coverage, topic coverage, anbefalede sektioner
- **AI quality verdict** — KEEP / IMPROVE / REWRITE med forklaring

**Krav:** GSC-data (trin 1).

**Pris:** $0,10-$0,30 pr. side for deep audit. Batch for hele sitet kan koste $2-$10.

## 3.12 Trin 7 — Internal Linking

**Hvad:** Action-liste hvor hvert kort = ét link du skal tilføje eller rette. Klik AI-knap, få paragraf klar til CMS.

**Filtre:**
- Prioritet (high/medium/low)
- Kilde (audit / cluster overlap / low link count)

**Knapper pr. kort:**
- **Generate link paragraph** — AI skriver kontekstparagraf med linket indlejret

**Output pr. kort:**
- Side der har brug for linket
- Målside at linke til
- Foreslået anchor text + placering (intro / body / H2)
- Hvorfor (delte emner, klyngestruktur, lavt link count)
- Impressions på kildesiden

**Krav:** Page Audit + Topic Clusters + API-nøgle.

**Pris:** $0,05-$0,10 pr. genereret link.

## 3.13 Trin 8 — Missing Keywords

**Hvad:** Hvert kort = én side med søgeordshuller. Viser manglende keywords, nuværende tekstkvalitet, AI-knapper til at omskrive sektioner.

**Knapper:**
- **Review existing text quality** — AI bedømmer tekst (score 0-10, verdict KEEP/IMPROVE/REWRITE)
- **Write optimized text** — AI omskriver siden med manglende søgeord integreret
- **Rewrite intro** — omskriver intro
- **Generate FAQ** — FAQ-sektion til manglende undertemaer

**Filtre:** Prioritet (high/medium/low).

**Output pr. side:**
- Manglende søgeord
- Manglende undertemaer (sektioner der bør findes)
- Trin-for-trin instruktioner
- Kvalitetsreview (når klikket): verdict + score + breakdown (user value, læsbarhed, conversion, E-E-A-T, SEO-integration, struktur)
- Største problemer + specifikke fixes
- AI-genereret omskrevet tekst / intro / FAQ

**Krav:** Page Audit + API-nøgle.

**Pris:** $0,10-$0,30 pr. side-vurdering. $0,05-$0,15 pr. tekstgenerering.

## 3.14 Trin 9 — New Articles

**Hvad:** Hvert kort = én artikel du bør skrive. AI genererer outline → fuld artikel → meta tags.

**Knapper:**
1. **Generate outline** — H1 + H2-sektioner med ordmål
2. **Generate full article** — komplet 1500-2500 ords artikel (markdown)
3. **Generate meta tags** — title + description
4. **Download article** — gem som .md

**Output pr. artikel:**
- Foreslået titel
- Target keywords (3-6)
- Content type (Blog / Buying guide / How-to)
- Estimerede impressions
- Hub-side (hvilken kategori at linke fra/til)
- Internal linking plan
- Outline (H1 + word target + H2-sektioner + H3-undersektioner)
- Fuld artikel (markdown klar til CMS)
- Meta tags

**Krav:** Topic Clusters + content roadmap (genereret i trin 5) + API-nøgle.

**Pris:** $0,50-$1,00 pr. artikel. Streamet — tager 60-90 sek.

## 3.15 Trin 10 — Cluster Health

**Hvad:** AI vurderer hver topic cluster: er sider linket korrekt (hub-spoke)? Misplaced keywords? Manglende undertemaer? Cannibalization indenfor klyngen?

**Knapper:**
- **Evaluate top 5 clusters** — kører AI på de 5 største klynger (~30 sek pr. klynge, ~5 min total)
- **Evaluate this cluster** — pr. klynge i expander
- **Clear all cached evaluations** — reset cache

**Output pr. klynge:**
- Health score 0-100 (grøn >70, gul 40-70, rød <40)
- Hub/pillar-vurdering
- Vertikal linking (hub→spoke + spoke→hub) — manglende vises rød
- Horisontal linking (spoke↔spoke) — isolerede spokes flagges
- Keyword distribution — misplaced + cannibalization i klyngen
- Content gaps — manglende undertemaer
- Priority actions — eksakte trin (fx "Tilføj link fra /category/sofas til /category/sofas/leather-sofas")

**Krav:** Topic Clusters + Page Audit + SF inlinks (valgfri men anbefalet).

**Pris:** $0,30-$0,50 pr. klynge. Cache forhindrer gen-kørsel.

## 3.16 Trin 11 — Content Generator

**Hvad:** Vælg én URL, generér meta-titler/beskrivelser, analysér keyword gaps, eller skriv fuld landing page-tekst.

**Tre faner (kan køres uafhængigt):**

1. **Meta Title + Description**
   - Viser nuværende meta (hvis tilgængelig)
   - **Generate meta suggestions** — N varianter (slider 1-5)
   - Copy-ready export

2. **Keyword Gap Analysis**
   - **Analyze keyword gaps** — score, coverage %, manglende keywords, anbefalet H1 + sektioner

3. **Landing Page Text**
   - **Tone of voice** (Professional / Discrete / Energetic / Informative)
   - **Generate landing page text** — intro + sektioner + buying guide + FAQ
   - Markdown export + download

**Indstillinger:**
- URL-vælger
- Meta variants count 1-5
- Custom keywords (komma-separeret, overskriver auto)
- Tone

**Krav:** Page Audit (anbefalet) + GSC + API-nøgle.

**Pris:** $0,05 pr. meta-variant. $0,10-$0,15 pr. gap-analyse. $0,30-$0,50 pr. landing page-tekst.

## 3.17 Trin 12 — Site Map

**Hvad:** Komplet Excel-eksport over hver side + metrics + klynge + handlinger. Kan også køre AI-validering af samlet site-arkitektur.

**Knapper:**
- **Build & Download Site Map** — genererer Excel-workbook
- **AI Validation** (valgfri) — Claude reviewer den fulde site-struktur og foreslår optimeringer

**Output (Excel-ark):**
1. **Site Structure** — hver side, impressions, klik, autoritet, ordtælling, klynge, depth, parent, issues
2. **Topic Clusters** — klyngeliste, sider pr. klynge, hub + spokes, manglende links
3. **Missing Keywords** — sider med lav keyword coverage
4. **Cannibalization** — konkurrerende sider pr. søgeord
5. **Crawl Issues** — brudte, forældreløse, dybe, tynde
6. **Actions** — merge/delete/create

**Krav:** GSC + Page Audit + Topic Clusters + Link Authority (alle anbefalet).

**Pris:** $0,20 for AI-validering (hvis klikket).

## 3.18 Trin 13 — All Tasks

**Hvad:** Master-checkliste der samler ALLE handlinger fra alle views, sorteret efter impact. Ét sted at se "hvad gør jeg nu?"

**Filtre:**
- Kategori (Technical / Meta / Content / Linking / Structural)
- Prioritet (HIGH / MEDIUM / LOW)
- **Show completed** toggle

**Knap pr. opgave:**
- **Mark done** checkbox (persisterer)

**Output:**
- Combineret task-liste fra:
  - Crawl issues (brudte links, forældreløse, langsomme)
  - Meta fixes (lave meta-scores)
  - Content improvements (keyword gaps, kvalitetsproblemer)
  - Linking actions (klynge-linking, interne links)
  - Structural changes (merges, deletes, creates, klynge-tildelinger)
- Pr. opgave: URL, kategori, prioritet, type, action-beskrivelse, impressions, kilde

**Krav:** Alle pipeline-trin (1-10).

**Pris:** Ingen.

## 3.19 Trin 14 — Implementation (Action Plan)

**Hvad:** Komplet trin-for-trin implementeringsguide pr. side. Sorteret efter impact (tabte klik). Genererer også nye artikelforslag + fuld sidetekst.

**Knapper:**
- **Generate next 10 plans** — kører AI på 10 ikke-vurderede sider (~20 sek/side, ~5 min total)
- **Clear all cached plans** — reset cache
- Pr. side:
  - **Generate AI plan** (hvis ikke cached)
  - **Regenerate meta variants**
  - **Generate bottom text with products & links**
  - **Rewrite section** (pr. tekst-omskrivning)
  - **Generate full article** (pr. ny artikel)

**Output pr. side:**
- Impact score (farvekodet: rød >1000, gul >200, grå lav)
- Implementation plan (3-15 trin):
  - Type + tidsestimat (CONTENT/META/LINKS/SCHEMA/STRUCTURE)
  - Action + detaljeret instruktion
  - Baggrund (hvorfor)
- Meta-forslag — viser før/efter med tegntælling
- New content to create — titel, keywords, hvorfor, hvor at linke fra
- Sections to rewrite — nuværende tekstuddrag + ny vinkel
- Generate complete page text — intro + bundtekst
- AI quality assessment — verdict + begrundelse
- Backlink status — referring domains-badge (OK/LOW/NONE/CRITICAL)

**Krav:** Page Audit + CTR Analysis (valgfri) + API-nøgle.

**Pris:** $0,20-$0,40 pr. plan. $0,50-$1,00 hvis du genererer nye artikler + fuld sidetekst. Batch på 10 = $3-$5.

---

# Del 4 — Alle indstillinger og hvorfor de findes

Dette afsnit dækker hver eneste indstilling der kan justeres i appen, og forklarer hvorfor den findes så du kan træffe informerede valg.

## 4.1 Globale indstillinger (Setup & Connect)

### APP_PASSWORD (env var)
**Hvad:** Password til at logge ind på appen.
**Hvorfor:** Beskytter kundedata. Appen nægter at starte uden — bevidst sikkerhedsvalg så data aldrig kan blive offentligt eksponeret ved en konfigurationsfejl.
**Hvor:** Railway → Settings → Variables → `APP_PASSWORD`.

### ANTHROPIC_API_KEY (env var eller UI-input)
**Hvad:** API-nøgle til Anthropic Claude.
**Hvorfor:** Krævet for ALLE AI-funktioner. Uden den virker kun rene data-views.
**Hvor:** Railway env var eller `Setup & Connect → Claude AI`.

### GSC_CREDENTIALS_JSON (env var) / UI-upload
**Hvad:** Service account JSON til Google Search Console.
**Hvorfor:** Giver appen lov til at hente GSC-data automatisk uden manuel eksport.
**Hvor:** Railway env var (anbefalet i produktion) eller upload i UI.

### GSC_SITE_URL (env var)
**Hvad:** Forvalgt GSC-property-URL.
**Hvorfor:** Springer property-valg over hvis du kun har ét site.
**Hvor:** Railway env var.

### SITE_CONTEXT (env var eller UI)
**Hvad:** Fri tekst der beskriver din webshop til AI'en.
**Hvorfor:** AI'en tilpasser meta, indhold og tone efter dette. Generisk default findes, men jo bedre du beskriver dit site, jo mere relevant bliver outputtet.
**Justering:** Skriv 2-4 sætninger om: hvad du sælger, hvem din målgruppe er, tone of voice, USPs.

### CONTENT_LANGUAGE (env var eller UI)
**Hvad:** Sprog som AI'en skriver på.
**Hvorfor:** Alt genereret indhold (meta, bundtekster, artikler, FAQ) skrives på dette sprog.
**Valg:** Engelsk, Dansk, Svensk, Norsk, Tysk, Spansk, Fransk, Italiensk og flere.
**Vigtigt:** UI'et forbliver altid engelsk — kun output-sprog justeres.

### Days back (GSC-fetch)
**Hvad:** Hvor mange dage GSC-data der hentes.
**Hvorfor:** 90 dage giver godt overblik uden at trække for meget historisk støj. Højere = mere data men også mere ældre/irrelevant data.
**Range:** 7-180. Default 90.

### Min. impressions (GSC-fetch)
**Hvad:** Filtrerer søgninger med færre end N impressions.
**Hvorfor:** Long-tail med 1-2 visninger er støj. 10+ er solid signal.
**Range:** 5-500. Default 10.

## 4.2 Site URL Patterns

Disse indstillinger fortæller systemet hvordan dine URL'er klassificeres til sidetype.

### category_patterns_extra
**Hvad:** Yderligere URL-stier der skal genkendes som kategorisider.
**Hvorfor:** Default patterns (`/category/`, `/c/`) virker for de fleste, men hvis du bruger fx `/sortiment/`, `/shop-now/`, `/store/` skal de tilføjes.
**Eksempel:** `/sortiment/, /shop-now/, /store/`

### info_patterns_extra
**Hvad:** Statiske info/firma-sider på dit sprog.
**Hvorfor:** Default kender `/about`, `/contact`, men ikke svenske/danske ord.
**Eksempel for svensk:** `/hjalp, /kontakt, /villkor`
**Eksempel for dansk:** `/hjælp, /kontakt, /betingelser, /levering`

### flat_category_keywords
**Hvad:** Søgeord der identificerer en kategori i flat URL-struktur (uden `/category/`-præfiks).
**Hvorfor:** Mange e-commerce-sites bruger `/sexleksaker` ikke `/category/sexleksaker`. Disse keywords fortæller systemet at sådanne URL'er ER kategorier.
**Eksempel:** `sexleksaker, elektronik, mode`

### local_patterns
**Hvad:** By-/butiks-stier der skal behandles som lokationssider.
**Hvorfor:** Lokationssider har andre SEO-krav end produktsider.
**Eksempel:** `/stockholm, /copenhagen, /butik`

### faceted_params_extra
**Hvad:** Query-parametre der flagges som facets.
**Hvorfor:** Defaults inkluderer allerede SID, dir, limit, mode, order, p, sort, view (Magento 1.9-standard). Tilføj egne hvis du bruger ekstra filter-parametre.
**Eksempel:** `farve, storrelse, materiale`

### Presets
**Hvad:** Forudfyldte sæt af patterns for sprog/branche.
**Hvorfor:** Genvej for nye sites. Klik **Apply preset** og du har 80% derhjemme.
**Tilgængelige:** Engelsk e-commerce, Svensk e-commerce, Dansk e-commerce, m.fl.

## 4.3 Indstillinger pr. side

### Topic Clusters: Max keywords slider
**Hvad:** Hvor mange søgeord AI'en analyserer.
**Hvorfor:** Mere = bedre klyngedækning, men dyrere og langsommere.
**Sweet spot:**
- Lille site (under 200 sider): 500
- Mellem site (200-1000 sider): 1000-2000
- Stort site (1000+ sider): 3000-5000
**Range:** 250-5000. Default 500.

### Page Auditor: Quick vs. Detailed
**Hvad:** Hvor dyb auditen er.
**Hvorfor:**
- Quick = kun meta + struktur, hurtigt og gratis
- Detailed = fuld content/keyword/linking-analyse, koster AI-kald

### Page Auditor: Re-scrape ALL vs. Scrape NEW
**Hvad:** Hvilke sider der scrapes.
**Hvorfor:**
- Re-scrape ALL = brug efter du har rettet sider og vil have frisk vurdering
- Scrape NEW = brug når der er kommet nye sider på sitet

### CTR Analysis-filtre
| Filter | Hvad det gør | Hvornår justere |
|--|--|--|
| CTR Gap Threshold | Vis kun søgninger med CTR ≥ N% under forventet | Sænk til -10% for at se flere "lette" gevinster, hæv til -40% for kun de største |
| Min. impressions | Filtrer støj | Hæv for større sites, sænk for mindre |
| Max. position | Fokus på top N | Hæv hvis du vil se long-tail muligheder ud over top 20 |
| Min. lost clicks | Vis kun søgninger der taber ≥ N klik/måned | Hæv til 50+ for kun de største muligheder |

### Cannibalization-filtre
| Filter | Hvad det gør |
|--|--|
| Min. impressions | Filtrer støj |
| Severity | Severe (klart problem) / Moderate / Mild |

### Content Generator: Meta variants count
**Hvad:** Antal meta-forslag AI'en genererer.
**Hvorfor:** Flere varianter = mere at vælge mellem, men koster mere.
**Range:** 1-5. Default 3.

### Content Generator: Tone of voice
**Hvad:** Tonen i genereret indhold.
**Værdier:**
- **Professional** — neutral, troværdig, lidt formel
- **Discrete** — afdæmpet, faktuel, mindst muligt salgs-sprog (godt til følsomme kategorier)
- **Energetic** — entusiastisk, salgs-orienteret, livligt
- **Informative** — undervisende, faktuelt, blog-style

### Content Generator: Custom keywords
**Hvad:** Komma-separeret liste der overskriver auto-detected keywords fra GSC.
**Hvorfor:** Brug når GSC ikke har dækning endnu (ny side) eller når du vil tvinge fokus til bestemte termer.

### Internal Linking-filtre
- **Prioritet** (high/medium/low)
- **Kilde** (audit / cluster overlap / low link count)

### Missing Keywords-filtre
- **Prioritet** (high/medium/low)

### New Articles-filtre
- **Prioritet** (high/medium/low)

### Site Cleanup-filtre
- **Severity** (CRITICAL/HIGH/MEDIUM/LOW)
- **Page type** (category/product/blog/etc.)

### All Tasks-filtre
- **Kategori** (Technical/Meta/Content/Linking/Structural) — multiselect
- **Prioritet** (HIGH/MEDIUM/LOW) — multiselect
- **Show completed** toggle

## 4.4 Filtre der findes igen og igen

Disse filtre dukker op på tværs af mange sider — værd at forstå én gang for alle:

**Prioritet (high/medium/low)** — beregnes typisk ud fra:
- Antal tabte klik (impact)
- Hvor mange søgninger der berøres
- Severitet af problemet

**Pagination (10-20/side)** — næsten alle lister er pagineret. Brug pile/dropdown nederst på listen.

**Severity (CRITICAL/HIGH/MEDIUM/LOW)** — bruges for crawl-issues og site cleanup:
- CRITICAL = blokerer indeksering (broken, noindex på vigtige sider)
- HIGH = stort traffik-tab (forældreløs side med mange impressions)
- MEDIUM = vigtigt men ikke akut
- LOW = nice-to-have

## 4.5 Reset og refresh — hvornår bruges hvad?

### Refresh GSC Data
**Bruges:** Når du vil have friske GSC-tal.
**Effekt:** Henter sidste 90 dages data igen. Erstatter eksisterende gsc_data. Andre analyser (clusters, audit) påvirkes IKKE direkte men giver nu et lidt forældet billede.
**Pris:** Ingen.

### Refresh bundled data (SF + Ahrefs)
**Bruges:** Efter du har `git push`'et nye `bundled_data/*.gz`-filer.
**Effekt:** Pakker SF + Ahrefs-filer ud igen. **BEVARER:** audit results, AI quality verdicts, GSC data, cannibalization, alle trin 7+. Sletter kun bundled filer + page_authority (rebuilds).
**Pris:** Ingen.

### Run Pipeline → Run All
**Bruges:** Komplet site-refresh — alt fra trin 1 til 10.
**Effekt:** Sliter ikke, men kører alle analyser igen og overskriver med nye resultater.
**Pris:** Variabel — typisk $5-$20 pr. fuld kørsel.

### Page Auditor: Re-scrape ALL
**Bruges:** Du har lavet meta/content-ændringer og vil se om de virker.
**Effekt:** Re-scraper hver side. Sletter gamle audit-resultater.
**Pris:** $2-$10 afhængigt af sitestørrelse.

### Clear all cached AI plans (Action Plan)
**Bruges:** AI-anbefalinger virker forældede.
**Effekt:** Sletter cached AI implementation plans. Næste klik på "Generate" kalder Claude igen.
**Pris:** Ingen (men næste regenerering koster).

### Clear all cached evaluations (Cluster Health)
**Bruges:** Du har lavet store linking-ændringer og vil have ny vurdering.
**Effekt:** Sletter cached cluster health-vurderinger.

### RESET ALL DATA (FARLIG)
**Bruges:** Sidste udvej. Korrupt data eller du vil starte helt forfra.
**Effekt:** Sletter ALT cached data. Beholder kun: credentials, site context, content language, gsc_site, authenticated. Bundled data (SF + Ahrefs) auto-genoplades på næste sidefornyelse.
**Pris:** Ingen direkte, men du skal genskabe ALT — let $20+ at få tilbage.

---

# Del 5 — Typiske arbejdsforløb

## 5.1 Førstegangskørsel (komplet site-analyse)

**Tid:** 1-2 timer aktivt arbejde + 30-60 min ventetid.
**Pris:** $10-$30.

1. **Setup & Connect** (5 min)
   - Indtast Anthropic API-nøgle
   - Upload GSC service account JSON ELLER bekræft env var
   - Vælg GSC-property
   - Skriv site context (3-4 sætninger)
   - Vælg sprog
   - Vælg Site URL Patterns preset (eller juster manuelt)
   - Klik **Save settings**

2. **Hent GSC-data** (1-2 min)
   - Days back: 90, Min impressions: 10
   - Klik **Fetch GSC Data**

3. **Run Pipeline → Run All** (30-60 min)
   - Lad fanen være åben
   - Tjek tilbage hvert 10. minut

4. **Dashboard** (5 min)
   - Læs site health score
   - Læs critical issues
   - Læs "Next Action"

5. **Quick Wins** (15 min)
   - Tag de 5 mest impactfulde sider
   - Generér meta + bundtekst
   - Kopiér til CMS

6. **Site Cleanup** (20 min)
   - Gennemgå Merge/Consolidate-fanen
   - Gennemgå Delete/Redirect-fanen
   - Gennemgå Noindex-fanen

7. **Action Plan** (resten af tiden)
   - Klik **Generate next 10 plans**
   - Implementér page-by-page

## 5.2 Ugentlig vedligeholdelse

**Tid:** 30-60 min.
**Pris:** $2-$5.

1. **Refresh GSC Data** (Setup & Connect)
2. **Run Pipeline** → kør kun trin 3 (CTR), 4 (Cannibalization), 6 (Page Auditor: NEW pages only)
3. **Dashboard** — læs "Next Action"
4. **All Tasks** — afmærk hvad du har lavet i sidste uge
5. **Action Plan** — generér 5-10 nye planer

## 5.3 "Jeg har 30 minutter — hvad gør jeg?"

1. **Dashboard** (1 min) — se Next Action
2. Følg Next Action — typisk én af:
   - **Quick Wins** for én side → kopiér meta + bundtekst
   - **All Tasks** → kryds 3 opgaver af
   - **Site Cleanup** → fix 1-2 noindex/redirect-handlinger

## 5.4 Når en konkret side skal forbedres

1. **Quick Wins** — vælg URL fra dropdown
2. Gennemgå alle faner: Meta, Keyword Gap, Bundtekst
3. Generér det du har brug for
4. Kopiér til CMS
5. (Valgfri) **Page Auditor** → Re-scrape ALL → se om scores forbedres

ELLER for dybdegående:

1. **Implementation (Action Plan)** — find sidens kort
2. Klik **Generate AI plan** hvis ikke cached
3. Følg trin-for-trin
4. Klik **Generate bottom text with products & links**
5. Kopiér HTML til Magento

---

# Del 6 — Fejlfinding og FAQ

## 6.1 Login virker ikke
- **Symptom:** Røde fejl "Wrong password" eller "Configuration error: APP_PASSWORD env var is not set"
- **Fix:** Tjek `APP_PASSWORD`-env var i Railway. Lokalt: `$env:APP_PASSWORD='dev'` før streamlit starter.

## 6.2 GSC vil ikke forbinde
- **Symptom:** "Could not connect to Google Search Console with the env credentials"
- **Tjek:**
  - Service account-email er tilføjet i GSC under Settings → Users and permissions for denne property
  - `GSC_CREDENTIALS_JSON` er fuld JSON, ikke en filsti
  - Midlertidigt netværksproblem — prøv igen om et minut
- **Test:** Klik **Connect to GSC now** for at forsøge igen.

## 6.3 AI giver fejl eller tomme svar
- **Tjek:**
  - `ANTHROPIC_API_KEY` er sat og gyldig
  - Du har kredit på Anthropic-kontoen
  - Anthropic API ikke er nede (sjældent)
- **Hvis tomt svar:** Prøv igen — Claude er ikke-deterministisk og enkelte requests kan fejle. Cache mister 0 resultater, kun den fejlede.

## 6.4 Et trin er gråt og kan ikke køres
- **Symptom:** "Run requires data from step X"
- **Fix:** Systemet håndterer afhængigheder — gå tilbage til det refererede tidligere trin og kør det først. Sidebar viser hvilke trin der er færdige med ✓ og hvilke der mangler.

## 6.5 Resultater ser forkerte ud
- **Tjek:**
  - Hvornår blev GSC-data sidst hentet? (vises i Setup & Connect → GSC data cached: TIMESTAMP)
  - Hvornår blev Page Auditor sidst kørt? Hvis du har lavet ændringer skal du **Re-scrape ALL**.
  - URL-normalisering: alle URL'er normaliseres ved load — hvis du ser dubletter med/uden trailing slash er det en bug, rapportér.

---

# Del 7 — Ordliste

| Term | Forklaring |
|--|--|
| **AI cache** | Lokalt lager af Claude-resultater så samme spørgsmål ikke koster penge to gange |
| **Anchor text** | Den klikbare tekst i et hyperlink |
| **Audit queue** | Liste over sider udvalgt til Page Auditor |
| **Bundled data** | Forhåndsudpakkede SF/Ahrefs-eksporter der følger med git |
| **Cannibalization** | Når dine egne sider konkurrerer på samme keyword |
| **Canonical** | "Den officielle" URL hvis flere URL'er viser samme indhold |
| **Cluster** | Gruppe af relaterede sider (pillar + spokes) |
| **Crawl depth** | Antal klik fra forsiden til en side |
| **CTR** | Click-Through Rate — % impressions der blev klik |
| **DR** | Domain Rating (Ahrefs autoritetsscore 0-100) |
| **E-E-A-T** | Experience, Expertise, Authoritativeness, Trust (Googles kvalitetsmål) |
| **Faceted URL** | Filter-URL med query-parametre (`?color=red`) |
| **Fragment flag** | Advarsel når AI kun ser delvis sidetekst |
| **GSC** | Google Search Console |
| **Hub / Pillar** | Hovedsiden i en cluster |
| **Impressions** | Antal gange siden vistes i søgeresultater |
| **JSON-LD** | Format for struktureret data (Schema) |
| **LIX** | Læsbarhedsindeks (lavt = let, højt = svært) |
| **Lost clicks** | Estimerede klik mistet pga. lav CTR |
| **Meta description** | Beskrivelsen under titlen i Google (140-160 tegn) |
| **Meta title** | Sidens titel i Google (50-60 tegn) |
| **Noindex** | HTML-tag der fortæller Google ikke at indeksere siden |
| **Normalisering** | Standardisering af URL'er (https, no www, no params, lowercase) |
| **Orphan page** | Side uden indgående interne links |
| **Page authority** | Beregnet score baseret på backlinks + DR |
| **Pipeline** | De 14 trin fra Setup til Implementation |
| **Position** | Gennemsnitlig placering i Google (1 = top) |
| **Quick win** | Side hvor lille ændring giver stor trafikgevinst |
| **Redirect chain** | URL → URL → URL i stedet for direkte |
| **Risk map** | Klassificering af sider efter "rør ikke / vær forsigtig / fri leg" |
| **Scrape** | At hente en sides indhold programmatisk |
| **Severity** | Hvor kritisk et problem er (CRITICAL/HIGH/MEDIUM/LOW) |
| **SF / Screaming Frog** | Crawl-værktøj der eksporterer CSV |
| **Site context** | Fri tekst der beskriver din webshop til AI'en |
| **Spoke** | Støtteside i en cluster |
| **Thin content** | Side med for lidt tekst (typisk under 300 ord) |
| **Tone of voice** | Stil på AI-genereret tekst (Professional/Discrete/Energetic/Informative) |
| **URL normalization** | Se "Normalisering" |
| **Verdict** | AI'ens dom: KEEP / IMPROVE / REWRITE |

---

**Sidste råd:**

Systemet er designet så **du aldrig behøver at gætte hvad det næste skridt er**. Sidebarens grønne ✓ og lilla >> guider dig altid. Dashboardet fortæller dig hvad du skal gøre nu. All Tasks samler alt på ét sted.

Stol på det. Følg sidebarens rækkefølge første gang. Bagefter går du direkte til Dashboard hver dag og lader Next Action styre din arbejdstid.

Held og lykke.
