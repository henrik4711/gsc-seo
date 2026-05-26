# Multi-Site Setup — mshop.se / mshop.dk / mshop.eu / future shops

Practical reference for running this codebase as multiple isolated SEO services, one per shop, on Railway.

---

## Architecture

```
GitHub repo: henrik4711/gsc-seo
├─ branch: main          ← shared development branch
├─ branch: mshop-dk      ← tracks main + DK-specific bundled data
└─ branch: mshop-eu      ← tracks main + EU-specific bundled data

Railway project: gsc-seo
├─ Service: mshop-se     ← watches main         · SITE_CODE=se · FOOTER_TEXT_STORE_ID=1
├─ Service: mshop-dk     ← watches mshop-dk     · SITE_CODE=dk · FOOTER_TEXT_STORE_ID=2
└─ Service: mshop-eu     ← watches mshop-eu     · SITE_CODE=eu · FOOTER_TEXT_STORE_ID=3
```

**Key principles:**

1. **One service per shop.** Each has its own Railway service, its own `/data` volume, its own env vars, its own login password.
2. **One branch per non-SE shop.** SE runs from `main`. DK, EU each have their own branch that merges from `main` regularly.
3. **Shared code via merge.** Development happens on `main`. The `deploy_all_sites.ps1` script merges `main` into every shop branch and pushes — Railway redeploys all services automatically.
4. **Per-shop bundled data via `SITE_CODE`.** Files in `bundled_data/` are suffixed with the shop code (`_se`, `_dk`, `_eu`). At startup, each service reads its `SITE_CODE` env var and loads only matching files. Other shops' files sit on disk harmlessly.
5. **Mshop Admin API is multi-tenant.** Same URL for all shops. `FOOTER_TEXT_STORE_ID` (1=SE, 2=DK, 3=EU, 4=DE) selects the target shop in each API payload.

---

## Env vars per shop

### Shared across all services (copy from `mshop-se`)

| Variable | Notes |
|---|---|
| `ANTHROPIC_API_KEY` | Same Anthropic account for all shops |
| `GSC_CREDENTIALS_JSON` | Same Google service account (added as user to each GSC property separately) |
| `MSHOP_ADMIN_API_BASE` | Same base URL — multi-tenant. Confirmed with admin: option A. |
| `FOOTER_TEXT_API` | Same URL |
| `FOOTER_TEXT_API_USER` | Same Basic auth user |
| `FOOTER_TEXT_API_PASS` | Same Basic auth pass |

### Shop-specific

| Variable | mshop-se | mshop-dk | mshop-eu |
|---|---|---|---|
| `APP_PASSWORD` | (SE pw) | (DK pw) | (EU pw) |
| `GSC_SITE_URL` | `sc-domain:mshop.se` | `sc-domain:mshop.dk` | `sc-domain:mshop.eu` |
| `SITE_CONTEXT` | Swedish description | Danish description | English description |
| `CONTENT_LANGUAGE` | `Swedish` | `Danish` | `English` |
| `FOOTER_TEXT_STORE_ID` | `1` | `2` | `3` |
| `SITE_CODE` | `se` | `dk` | `eu` |

`SITE_CODE` is the critical multi-site switch — it tells the unpack code which bundled files to load. Without it set, the service defaults to `se` with a warning, so an mshop-se deploy that forgets to set it keeps working.

---

## Adding a new shop (e.g. mshop.de)

### 1. Git branch (1 min)

```powershell
cd C:\gsc-seo
git checkout main
git pull
git checkout -b mshop-de
git push -u origin mshop-de
```

### 2. Railway service (5 min)

1. Railway → project → **+ Create** → **Deploy from GitHub repo** → `henrik4711/gsc-seo`
2. Settings → Service Name = `mshop-de`
3. Settings → Source → Branch = `mshop-de`
4. Settings → Volumes → + New Volume → Mount Path = `/data` · Size = 5 GB

### 3. Variables (5 min)

Copy the 6 shared variables from another service. Add the 6 shop-specific:

```
APP_PASSWORD         = <unique password>
GSC_SITE_URL         = sc-domain:mshop.de
SITE_CONTEXT         = (German description)
CONTENT_LANGUAGE     = German
FOOTER_TEXT_STORE_ID = 4
SITE_CODE            = de
```

### 4. Google Search Console (3 min)

1. Search Console → select `mshop.de` property
2. Settings → Users and permissions → Add user
3. Add the service account email (find it in `GSC_CREDENTIALS_JSON`'s `client_email` field)
4. Restricted permission

### 5. Update `deploy_all_sites.ps1`

Add `"mshop-de"` to the `$branches` array.

### 6. First run

1. Open the new Railway URL
2. Login with `APP_PASSWORD`
3. Setup & Connect → verify all System Status indicators green
4. Sync Mshop active pages → confirm DE-specific categories returned (not SE)
5. Fetch GSC Data → ⚡ Run Pipeline → Run All

---

## Daily workflow

### When code changes are made on `main`

```powershell
cd C:\gsc-seo
.\scripts\deploy_all_sites.ps1
```

The script:
1. Pulls `main` from remote
2. Merges `main` into each shop branch (`mshop-dk`, `mshop-eu`)
3. Pushes each branch
4. Returns to your starting branch

Railway redeploys all services automatically (~2 min per service).

### When a single shop needs an update only

```powershell
git checkout mshop-dk
# make changes
git commit -am "DK-only tweak"
git push origin mshop-dk
```

Don't merge shop-specific work back to `main` unless it's broadly applicable.

---

## Bundled data per shop

Bundled data (`bundled_data/`) holds large preprocessed datasets — Screaming Frog crawls and Ahrefs exports — that ship with the repo via git so the app boots with realistic data instead of a cold start.

### Convention

```
bundled_data/
├─ sf_pages_se.csv.gz            ← only on main + mshop-se (loaded by SE service)
├─ sf_inlinks_se.csv.gz          ← only on main + mshop-se
├─ sf_link_map_se.json.gz        ← only on main + mshop-se
├─ ahrefs_backlinks_se.csv.gz    ← only on main + mshop-se
├─ ahrefs_best_by_links_se.csv.gz
├─ ahrefs_organic_keywords_se.csv.gz
│
├─ sf_pages_dk.csv.gz            ← only on mshop-dk (when DK gets its first crawl)
├─ sf_inlinks_dk.csv.gz
└─ ... (DK Ahrefs files, future)

bundled_data/sf_pages_eu.csv.gz  ← only on mshop-eu (when EU gets its first crawl)
```

### How it loads

`utils/persistence.py:_resolve_bundled_path()` reads `SITE_CODE`, then:
1. Looks for `bundled_data/<stem>_<site_code><ext>` (the shop-specific file).
2. If that exists, loads it.
3. SE-only legacy fallback to unsuffixed filenames (`sf_pages.csv.gz`) for backward compat — other shops get no fallback.
4. Returns `None` and skips load otherwise. The service starts with empty `sf_pages` / `page_authority` state (everything still works, just no preloaded backlinks/crawl).

### Adding new bundled data for a shop

When DK eventually has its own SF crawl + Ahrefs export:

```powershell
git checkout mshop-dk

# Drop the files into bundled_data/ with the _dk suffix
# (gzip them if not already compressed)
gzip sf_pages_dk.csv          # produces sf_pages_dk.csv.gz
gzip ahrefs_backlinks_dk.csv  # etc.

# Move into bundled_data/
mv sf_pages_dk.csv.gz bundled_data/
mv ahrefs_backlinks_dk.csv.gz bundled_data/

git add bundled_data/sf_pages_dk.csv.gz bundled_data/ahrefs_backlinks_dk.csv.gz
git commit -m "Add DK SF + Ahrefs bundled data"
git push origin mshop-dk
```

The files live ONLY on the `mshop-dk` branch — `main` never gets them merged back, so the mshop-se service is unaffected.

---

## Push to Magento — multi-tenant model

The Mshop Admin API is a single endpoint that handles all shops. Each request payload includes `storeId`:

- `1` = mshop.se
- `2` = mshop.dk
- `3` = mshop.eu
- `4` = mshop.de

The system reads `FOOTER_TEXT_STORE_ID` env var on each service and embeds that number in every push (intro text, meta title/desc, bottom text, etc.) so each service only writes to its own shop.

**If pushes from mshop-dk land on mshop.se:** `FOOTER_TEXT_STORE_ID` is wrong. Should be `2`, not `1`. Check Railway env vars on the mshop-dk service.

---

## Troubleshooting

### "Login virker ikke" / Login fails
- `APP_PASSWORD` env var not set on this service, or value typed wrong.
- Tip: set distinct passwords per service so you always know which one is which.

### GSC dropdown shows wrong site (e.g. only SE on the DK service)
- Service account not added as user to the DK property in Google Search Console.
- Fix: Search Console → DK property → Settings → Users and permissions → Add user with the service account email (find in `GSC_CREDENTIALS_JSON` → `client_email`).

### Sync Mshop active pages returns SE categories on DK service
- `FOOTER_TEXT_STORE_ID` set to `1` instead of `2`. Fix in Railway Variables.

### Sync returns 0 pages
- Auth wrong (`FOOTER_TEXT_API_USER` / `FOOTER_TEXT_API_PASS`), or `MSHOP_ADMIN_API_BASE` wrong, or the shop doesn't have any active categories yet.

### Page authority is contaminated with SE data on DK service
- `SITE_CODE` not set or set wrong on the DK service. Should be `dk`. After setting, restart the service so `_unpack_bundled_data` re-evaluates.

### Cluster Health crashes
- Various edge cases fixed over time (see git log around `2026-05-26`). If a crash persists, click Retry on the failing cluster — the popover under "Stack trace (for debugging)" shows the full traceback.

### Deploy script conflicts on merge
- Happens once when bundled files are renamed/restructured on `main`. Resolve with `git checkout --theirs <file>` to take main's version, then `git add` + commit + push.

---

## Files in this setup

| File | Purpose |
|---|---|
| `utils/persistence.py` | `_unpack_bundled_data`, `_resolve_bundled_path` — the `SITE_CODE` loader logic |
| `scripts/deploy_all_sites.ps1` | One-command sync of all shop branches from main |
| `bundled_data/*_<site>.<ext>` | Per-shop preprocessed datasets |
| `utils/mshop_admin_api.py` | Multi-tenant push client — uses `FOOTER_TEXT_STORE_ID` |
| `utils/footer_text_api.py` | Bottom-text push, same multi-tenant model |

---

## Memory / cost ballpark per service

- Disk: ~500 MB-2 GB depending on bundled data size (`/data` volume)
- Memory: ~512 MB-1 GB Streamlit runtime
- Anthropic cost: ~$10-30 per full pipeline run on a 1000-page site
- Railway hosting: ~$5/month per service
