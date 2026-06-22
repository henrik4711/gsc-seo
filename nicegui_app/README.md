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
- [ ] Phase 1: decouple `utils/persistence.py` to `state()` so `load_all()`
      can hydrate the NiceGUI store from `/data`
- [ ] Port first real view (candidate: Dashboard)
- [ ] Decide NiceGUI storage scope (client vs user) + Railway start command
