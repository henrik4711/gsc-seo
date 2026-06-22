# Streamlit → NiceGUI Migration Plan

> Status: **PLANNING ONLY — no code written yet.**
> Purpose: a durable reference we can return to. Decouple the business logic
> from Streamlit first; a NiceGUI port becomes a small, view-by-view job afterwards.
>
> Numbers verified twice. `st.` token counts use word-boundary matching to
> avoid false positives (`request.execute`, `list.append`). State counts use the
> unambiguous string `session_state` to stay **alias-agnostic** — several logic
> files import `streamlit as _st` locally inside functions, which a `st\.`-only
> regex silently undercounts. Last verified: 2026-06-19.
>
> Caveat: plain `session_state` counts include the odd comment/docstring mention,
> so per-file figures are slight upper bounds — fine for relative weighting.

---

## 1. Why this, and why decouple before porting

The pain (`st.rerun`, the sea of `session_state`) is a **symptom of Streamlit's
execution model**: the whole script re-runs top-to-bottom on every interaction,
so all state must live in `st.session_state` and you call `st.rerun()` to force
redraws.

NiceGUI uses a **persistent server-side model** (like a real web app): state is
just Python objects that live across interactions, and widgets call callbacks
that update only the elements that changed. `rerun` and most of the
`session_state` bookkeeping **disappear as a problem**.

But — and this is the key finding — the logic is **not cleanly separated** from
Streamlit today. The blocker is not "widgets inside logic"; it is **ambient
state**: logic functions read their inputs out of `st.session_state` as a global
instead of receiving them as arguments:

```python
# utils/page_profile.py — the pattern, repeated everywhere
audit    = st.session_state.get("audit_results", [])
gsc_df   = st.session_state.get("gsc_data")
clusters = st.session_state.get("topic_clusters", {})
language = st.session_state.get("content_language", "Swedish")
```

The same ~10 keys (`topic_clusters`, `gsc_data`, `audit_results`,
`page_authority`, `content_language`, `site_context`, plus per-URL caches) are
read across many files. That is BOTH what makes the code unportable AND what
ties it to Streamlit's rerun model.

**Therefore: decouple first (framework-agnostic state), then port the GUI.**
The decoupling improves the code on its own and de-risks the eventual port.

---

## 2. Verified metrics (2026-06-19)

| Metric | Value |
|---|---|
| Python files total | 68 |
| Files importing `streamlit` | 46 (**only 1 is a genuine dead import** — see below) |
| `session_state` references (alias-agnostic) | **1,038** (utils 210 / views 779 / app.py 33) |
| `.rerun()` calls (alias-agnostic) | 126 |
| `st.cache_data` / `cache_resource` / `secrets` | **0** (none used anywhere) |

Two implications:
- The last row means there is **no Streamlit caching layer to replace** — one
  less thing to abstract.
- `views/` holds **779 of the 1,038** `session_state` references — the bulk of
  the work lives in the presentation layer (handled in the port phase, not
  decoupling).

> Several logic files import `streamlit as _st` *locally inside functions*
> (`cannibalization` 8×, `page_fix_runner` 10×, `category_analyzer` 2×,
> `topical_scope` 2×). A first pass that only matched `st.` undercounted these.
> The coupling is therefore scattered inside function bodies, not just at module
> top-level — keep that in mind when decoupling.

---

## 3. File classification (all of `utils/`)

### Bucket A — true UI files (the presentation boundary)
These genuinely contain widgets and belong in the presentation layer. They are
**not** decoupled; they get rewritten during the NiceGUI port, view-by-view.

| File | real `st.` |
|---|---|
| `utils/footer_push_ui.py` | 58 |
| `utils/mshop_admin_push_ui.py` | 55 |
| `utils/action_ui.py` | 14 |
| `utils/ui_helpers.py` | 12 |

### Bucket A′ — hybrid (UI + logic mixed, must be SPLIT)
Real widgets AND logic in one file. Split the logic out (down to Bucket C) and
leave the render half in the UI layer.

| File | real `st.` | Note |
|---|---|---|
| `utils/errors.py` | 13 | `report_error()` (logic: enqueue) vs `render_system_messages()` (UI). See §6. |
| `utils/page_deeplink.py` | 8 | URL/deeplink building (logic) vs the link widgets (UI). |

### Bucket B — pure logic, ports for free
The 17 already-clean files **plus 1 dead-import file**.

- Already clean (17): `__init__`, `ahrefs_import`, `cluster_linking`,
  `diagnostics`, `footer_text_api`, `html_cache`, `html_extractors`,
  `lang_prompts`, `link_audit`, `mshop_admin_api`, `page_scraper`,
  `product_scraper`, `screaming_frog_import`, `templates`, `text_clean`,
  `topic_clusters`, `url_helpers`.
- **Genuine dead import — delete one line (1):** `gsc_client.py`. Imports
  `streamlit as st` (line 6) but the only `st.`-looking token is
  `request.execute` (a false positive); streamlit is never used.

> Correction from the second verification pass: `category_analyzer.py` and
> `topical_scope.py` are **NOT** dead imports — they use `streamlit as _st`
> locally inside functions, so they belong in Bucket C below. Only `gsc_client`
> is genuinely deletable.

### Bucket C — logic with ambient state (THE decoupling work)
`session_state` usage, alias-agnostic, ordered by weight:

| File | `session_state` refs | uses `_st` alias |
|---|---|---|
| `utils/persistence.py` | 33 | – |
| `utils/page_profile.py` | 30 | – |
| `utils/cluster_health_runner.py` | 24 | – |
| `utils/ai_generator.py` (4,991 lines) | 20 | – |
| `utils/page_fix_runner.py` | 19 | yes (10×) |
| `utils/quality_check_runner.py` | 16 | – |
| `utils/cannibalization.py` (1,041 lines) | 10 | yes (8×) |
| `utils/audit_refresh.py` | 7 | – |
| `utils/content_freshness.py` | 4 | – |
| `utils/topical_scope.py` | 4 | yes (2×) |
| `utils/cache_keys.py` | 3 | – |
| `utils/category_analyzer.py` (2,271 lines) | 3 | yes (2×) |
| `utils/freshness.py` | 3 | – |
| `utils/site_patterns.py` | 3 | – |
| `utils/action_status.py` | 1 | – |
| `utils/cluster_suggest.py` | 1 | – |

Note: the large files (`ai_generator`, `cannibalization`, `category_analyzer`)
still have **modest** coupling relative to their size — repeated `.get()` calls
on the same handful of keys, not deep entanglement.

> `views/` (~40 files) holds **779 of the 1,038** `session_state` refs and most
> of the 126 `rerun` calls. Those are handled in the **NiceGUI port phase**, NOT
> the decoupling phase. Decoupling only frees the *logic*.

---

## 4. The `Store` design (Phase 0)

### What the logic actually needs from `session_state`
Measured against `persistence.py` (the heaviest file). Exactly these operations:

| Operation | Example |
|---|---|
| `key in store` | `if key in st.session_state` |
| `store[key] = v` | `st.session_state[key] = df` |
| `store[key]` | `data = st.session_state[key]` |
| `store.get(k, default)` | `st.session_state.get("mshop_active_pages")` |
| `store.keys()` | `list(st.session_state.keys())` |
| `store.pop(k, None)` | `st.session_state.pop("mshop_active_pages", None)` |

That is exactly a `MutableMapping`. And `st.session_state` **already is one** —
so the Streamlit backend is near-identity; we only add one indirection layer.

### `utils/state.py` (new, small)

```python
# utils/state.py — framework-agnostic access to app state.
# Logic calls state() and knows NOTHING about Streamlit or NiceGUI.
import contextvars

# A ContextVar (not a plain global) so it still works when NiceGUI later
# runs multiple clients concurrently in one process. In Streamlit it's set
# once per script-run; in NiceGUI once per client connection.
_active: contextvars.ContextVar = contextvars.ContextVar("app_state")

def bind(store) -> None:
    """Bind the active state backend. Called at app startup."""
    _active.set(store)

def state():
    """Return the active MutableMapping. Replaces st.session_state."""
    try:
        return _active.get()
    except LookupError:
        raise RuntimeError("state backend not bound — call bind() at startup")
```

### Binding — the only thing that differs between frameworks

```python
# app.py (Streamlit) — at the very top, before anything else runs:
from utils.state import bind
bind(st.session_state)          # session_state IS already a MutableMapping

# Later, NiceGUI — per client connection:
bind(app.storage.client)        # or a per-client dict
```

The logic only ever sees `state()`. It never changes between frameworks — that
is the entire payoff.

> Streamlit note: a plain module global would also work for Streamlit (each
> session runs in its own ScriptRunner thread, and `st.session_state` is itself a
> context-aware proxy). We choose a `ContextVar` so the *same* accessor is
> forward-compatible with NiceGUI's concurrency without a rewrite.

### `utils/progress.py` (for the runner files, not persistence)
`persistence.py` uses only `print()`. But the runner files use
`st.spinner`/`st.progress`/`st.toast`. They get a neutral no-op protocol:

```python
# utils/progress.py
class Progress:                       # no-op default — works outside any GUI
    def step(self, msg, pct=None): pass
    def done(self, msg=""): pass

NULL = Progress()
# Streamlit impl wraps st.progress/st.status; NiceGUI impl wraps
# ui.linear_progress/ui.notification. Logic takes: progress: Progress = NULL
```

Phase 0 changes **no behaviour** — it just adds two files nobody calls yet.

---

## 5. `persistence.py` before/after (Phase 1 anchor)

Purely mechanical: `import streamlit as st` → `from utils.state import state`,
and `st.session_state` → `state()`. Behaviour 100% identical in Streamlit.

**Before** (lines 11, 566–584):
```python
import streamlit as st
...
def save(key: str, value=None):
    if value is not None:
        st.session_state[key] = value
    elif key not in st.session_state:
        return
    if not _volume_available():
        return
    data = st.session_state[key]
    ...
```

**After:**
```python
from utils.state import state
...
def save(key: str, value=None):
    s = state()
    if value is not None:
        s[key] = value
    elif key not in s:
        return
    if not _volume_available():
        return
    data = s[key]
    ...
```

Repeated for the ~33 `session_state` sites in the file. No logic moves, no
disk/file code changes, and **no public signature changes** —
`save`/`save_key`/`save_all`/`save_ai_cache`/`load_all` stay identical, so all
14 calling views keep working untouched.

---

## 6. Known complication: logic → UI dependency via `errors.py`

`persistence.py` imports `from utils.errors import report_error` (lines 467,
504, 517, 545, …) but `errors.py` is a UI file (13 real widgets: `st.toast`,
`st.expander`, `st.error`, `st.button`, …). That drags Streamlit back into the
logic through the back door.

Fix (first step of Phase 1): split `errors.py` into

- **logic half** — `report_error()` enqueues into `state()["_errors"]`. Stays
  callable from logic, no widgets.
- **UI half** — `render_system_messages()` draws the panel. Lives in the
  presentation layer.

Until this split lands, `persistence.py` is not truly Streamlit-free.

---

## 7. Phased rollout (no big-bang)

| Phase | Scope | Risk |
|---|---|---|
| **0** | Add `utils/state.py` + `utils/progress.py`. Add `bind(st.session_state)` at top of `app.py`. Delete the 1 dead `import streamlit` line in `gsc_client.py`. | ~none (additive) |
| **1** | `persistence.py` → `state()`. Split `errors.py` (report vs render). | low (mechanical, signatures stable) |
| **2** | Small Bucket C files: `cache_keys`, `action_status`, `cluster_suggest`, `site_patterns`, `freshness`, `content_freshness`, `topical_scope`, `category_analyzer`. 1–4 sites each (watch the `_st` local imports in `topical_scope`/`category_analyzer`). | low |
| **3** | Runner files: `quality_check_runner`, `cluster_health_runner`, `page_fix_runner` (`_st` 10×), `audit_refresh`, `page_profile`. Use `state()` + inject `Progress`. | medium |
| **4** | Large analysis files: `ai_generator` (20 refs), `cannibalization` (10 refs, `_st` 8×). Critical, so last. | medium |
| **5 (later)** | NiceGUI port of the presentation layer (`views/` + Bucket A/A′ UI halves), view-by-view. Only starts after 0–4: all logic is framework-free. | the real project |

After Phases 0–4, **all logic is Streamlit-free while still running on
Streamlit**. The NiceGUI port (Phase 5) then touches only presentation.

---

## 8. Process constraints (project rules)

- **Multi-branch:** every change to `main` must also merge into `mshop-dk` and
  `mshop-eu` (and future site branches) so all Railway services stay in sync.
  The phased approach helps: each phase is a small, testable commit with stable
  signatures, so merge conflicts stay minimal.
- **Test the full data flow before committing** each phase: e.g. Phase 1
  round-trip — `save("topic_clusters", x)` → restart → `load_all()` → same data.
- **Phase 0/1 is null-risk in Streamlit** because `state()` returns the very
  same `st.session_state` object.

---

## 9. Open decisions (for later)

- Confirm NiceGUI state scope: `app.storage.client` (per browser tab) vs
  `app.storage.user` (per authenticated user) vs `app.storage.general`. Must
  match today's per-session semantics — and respect the no-global-auth rule
  (no server-shared auth hydration).
- Whether to do the NiceGUI port on a throwaway branch with ONE pilot view
  (e.g. Dashboard) before committing to the full port.
- Auth model in NiceGUI (Streamlit's session model goes away).
