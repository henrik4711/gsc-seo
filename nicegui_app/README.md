# NiceGUI front-end (pilot)

Staging app for the Streamlit → NiceGUI migration. See
[`../NICEGUI_MIGRATION_PLAN.md`](../NICEGUI_MIGRATION_PLAN.md) for the full plan.

## Core rule: reuse, don't copy

This app contains **no business logic of its own**. It imports the shared
`utils/` package and reaches state through the framework-agnostic
`utils.state` accessor. The Streamlit app (`../app.py`) keeps running
unchanged. We port this to `main` only when it reaches feature parity.

```
Streamlit (app.py)  ─┐
                     ├─►  utils/  (shared logic — single source of truth)
NiceGUI (this app)  ─┘        ▲
                              │ reads state() instead of st.session_state
                     utils/state.py  ←─ bind(st.session_state)  in Streamlit
                                      ←─ bind(app.storage.client) in NiceGUI
```

## Why the folder is `nicegui_app/` and not `nicegui/`

A top-level package named `nicegui` would shadow the installed NiceGUI
library and break `import nicegui`.

## Patterns adopted from wp-system (the live NiceGUI app)

After studying `C:\wp-system\wp_publisher\nicegui`:

- **`components.py`** — the Streamlit→NiceGUI idiom cheat-sheet (`banner`,
  `notify_ok/err`, `simple_table`, `page_header`, `run_job`). Every view imports
  these so the port stays consistent. Foundation for the view-port phase.
- **`run_job(fn, …)`** — wraps `run.io_bound` + a spinner notification so slow
  AI/scrape/IO calls run OFF the event loop and never freeze other clients.
  This is the NiceGUI answer for the multi-hour AI batches.
- **State resolver fix** — `state.bind()` now takes a *resolver*
  (`lambda: app.storage.client`) re-resolved on every `state()` call, so it is
  correct inside event callbacks/background tasks (separate async contexts),
  not just the page builder. The earlier "bind a captured object at render"
  approach worked only by closure luck.
- **Already had, didn't copy** — wp's `batch_state.py` checkpoint/resume is
  already covered by our `persistence.py` (`_fix_history`, `_fix_failure_count`,
  `_recheck_history`) + per-item `save_ai_cache()`.
- **Kept our auth gate** — wp_publisher has none; ours is correct for customer
  data.

## Run locally (via `.env`)

```bash
cp ../.env.example ../.env               # fill in APP_PASSWORD, ANTHROPIC_API_KEY, GSC, Mshop…
pip install -r requirements.txt          # nicegui + python-dotenv
pip install -r ../requirements.txt       # shared logic deps (pandas, anthropic, …)
python -m nicegui_app.main               # http://localhost:8080
```

`main.py` loads `../.env` (python-dotenv) before importing anything that reads
env at import time. `.env`, `*.json` and `data/` are gitignored — secrets never
get committed. Set `DATA_DIR=./data` locally so persistence works off the
Railway `/data` mount. On Railway there is no `.env`; set the same keys as env
vars. Full list + notes: [`../.env.example`](../.env.example).

GSC credentials: either `GSC_CREDENTIALS_JSON` (inline, one line) or
`GSC_CREDENTIALS_FILE` (path to the service-account JSON, gitignored). The
NiceGUI app hydrates GSC creds/site + site context + language from env into
`state()` on first authenticated page load (`_ensure_loaded` → `_hydrate_from_env`);
the Anthropic key is read from env directly by `config.get_anthropic_key()`.

## App structure

| File | Responsibility |
|---|---|
| `main.py` | dotenv load, auth gate (`APP_PASSWORD`, fail-closed), `_ensure_loaded` (load_all + env hydration), routes → page `render()` |
| `layout.py` | `page_shell(active)` — header + left nav (`NAV`) + centered column, applies theme. One entry per page. |
| `theme.py` | one dark theme (purple accent, Syne + IBM Plex Mono), applied by `page_shell`. |
| `components.py` | Streamlit→NiceGUI idiom helpers (`banner`, `notify_ok/err`, `run_job`, `simple_table`, `page_header`). |
| `pages/flow.py` | the flow control center (`/flow`) — renders `utils/pipeline.py` as phases → steps with status + Run + "Run all remaining". |
| `pages/keywords.py` | `/keywords` — import competitor Ahrefs, build the keyword universe. |
| `pages/gaps.py` | `/gaps` — gap opportunities + new-content opportunity clusters. |

Shared logic added this cycle (all framework-free, in `utils/`):
`keyword_universe.py`, `clustering.py`, `pipeline.py` (flow registry — single
source of truth for the steps), `audit_runner.py`, `site_structure.py`,
`planning_runner.py`.

## Status / next steps

- [x] Phase 0 foundation: `utils/state.py`, `utils/progress.py`
- [x] NiceGUI skeleton + auth gate + reuse proof
- [x] Phase 1a: decouple `utils/persistence.py` to `state()`; `app.py` binds
      `st.session_state` at startup (identity binding — Streamlit unchanged).
      Verified: save→disk + load round-trip under a plain-dict (NiceGUI) store.
- [x] Phase 1b: `utils/errors.py` report/get/clear use the bound store
      (works under Streamlit AND NiceGUI); render stays Streamlit-only.
- [x] Phase 2: small Bucket C files decoupled to `state()` — `cache_keys`,
      `action_status`, `cluster_suggest`, `site_patterns`, `freshness`,
      `content_freshness`, `topical_scope`, `category_analyzer`.
- [x] Phase 3: runner files decoupled — `page_profile`, `cluster_health_runner`,
      `quality_check_runner`, `audit_refresh` (pure state() swaps) and
      `page_fix_runner` (state() + `Progress` injection for its st.spinner/
      st.error; `default_progress()` auto-detects Streamlit so callers and the
      paid Fix-ALL batch are unchanged).
- [x] Phase 4: large analysis files decoupled — `ai_generator` (20),
      `cannibalization` (10). **The logic layer is now 100% framework-free.**

### Rebuild cycle (2026-07-07) — Henrik's 5 goals

Goals: (1) import competitor Ahrefs keywords with ALL keywords, (2) an
understandable/consistent flow, (3) a much nicer GUI, (4) everything
resumable, (5) everything modular / no duplicated code. **Targeted at
mshop.dk** (Danish competitors, e.g. Sinful). Branch: `nicegui-migration`.

- [x] **Keyword universe** (`utils/keyword_universe.py`) — GSC + own Ahrefs +
      per-competitor Ahrefs, unioned + brand-stripped (own + global safety
      net), gap detection. Import page `/keywords`. *Goal 1.*
- [x] **Universe drives clustering** (`utils/clustering.py`) — separate own/gap
      quotas so competitor gaps aren't crowded out; clusters tagged
      `gap_keywords` / `is_opportunity`.
- [x] **Flow control center** (`utils/pipeline.py` + `pages/flow.py`) — 4
      phases, 16 steps, per-step status, resumable "Run all remaining". *Goals
      2, 4.*
- [x] **Keyword gaps view** (`pages/gaps.py`) — the payoff: opportunities +
      opportunity clusters. *Goal 1.*
- [x] **Bulk audit ported** (`utils/audit_runner.py`) — Mshop API/GSC URL
      source, disk-checkpointed resumable scrape.
- [x] **Phase-4 AI planning ported** (`utils/site_structure.py`,
      `utils/planning_runner.py`) — site validation, ideal structure, migration
      plan, plan validation.
- [x] **Dark theme** (`theme.py`). *Goal 3.*
- [x] **Local `.env` support** — dotenv + `DATA_DIR` override + env hydration.
- **Verified:** pure logic unit-tested (universe/brand-strip/clustering
      quotas/registry status/site-structure/hallucination filter); real page
      bodies render (auth-free preview harness screenshots of `/flow`, `/gaps`).
- **NOT yet live-tested:** the AI calls (clustering, cluster health, content
      quality, the 4 planning steps) + scraping — faithful ports of the working
      Streamlit code, but need a run with a real API key + data. → **next: live
      test on mshop.dk via `.env`.**

### Still to build

- [ ] **Screaming Frog import** — the one remaining "port pending" step
      (`import_crawl` in `utils/pipeline.py`).
- [ ] **Per-page content generation + Mshop push** — the Bucket A UI files
      (`action_ui`, `footer_push_ui`, `mshop_admin_push_ui`) not yet ported.
- [ ] Remaining `views/` ports (dashboard detail, cannibalization view, etc.).
- [ ] Production wiring: add `nicegui` + `python-dotenv` to root requirements +
      Railway start command; set a real `NICEGUI_STORAGE_SECRET`.
- [ ] Known local quirk: browser login+`ui.navigate.reload()` reconnect can
      loop in *automated* browsers (real Chrome is fine). If it bites locally,
      add a dev auth bypass.

### Key commits (branch `nicegui-migration`)

`836e36d` universe+import · `c441c4c` flow control center · `6aed302` gaps
view + audit port + theme · `bf109e4` phase-4 planning port · `824dfa1` local
`.env` support.
