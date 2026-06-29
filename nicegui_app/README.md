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

## Run locally

```bash
pip install -r requirements.txt          # from repo root: nicegui_app/requirements.txt
pip install -r ../requirements.txt       # shared logic deps (pandas, etc.)
APP_PASSWORD=dev python -m nicegui_app.main
# open http://localhost:8080  (password: dev)
```

## What the pilot proves

1. **Reuse** — the dashboard calls `utils.persistence.get_storage_info()`
   directly, no Streamlit involved.
2. **State abstraction** — `utils.state.bind(app.storage.client)` per client
   connection; logic that reads `state()` works unchanged.
3. **No rerun** — the counter updates one label in place; no full-script
   re-execution.

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
      `cannibalization` (10). Also removed the dead `import streamlit` left in
      `gsc_client.py`. **The logic layer is now 100% framework-free** — the only
      utils still importing streamlit are the Bucket A/A′ UI files
      (`action_ui`, `footer_push_ui`, `mshop_admin_push_ui`, `page_deeplink`,
      `ui_helpers`) + the two boundary modules (`errors` fallback, `progress`
      adapter).
- [ ] Port views to NiceGUI (Bucket A/A′ UI + the ~40 `views/`), using
      `components.py` — the remaining work.
- [ ] Production wiring: add `nicegui` to root requirements + Railway start
      command; set a real `NICEGUI_STORAGE_SECRET`.
