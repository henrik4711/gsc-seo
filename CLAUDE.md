# CLAUDE.md

Operating rules for any AI assistant or developer working in this repository.
This file is loaded automatically at the start of every session. It overrides default behaviour.

**Structure of this file**

| Part | Scope | Portable? |
|---|---|---|
| Part 1 | Universal working rules (code, test, debug, deploy, safety) | Yes, copy as is |
| Part 2 | Project specifics for `C:\gsc-seo` | No, rewrite per project |
| Part 3 | How to port this file to another project | Instructions |

Rules marked **[BLOCKING]** must be satisfied before code is committed. A rule that is inconvenient is still a rule: raise it, do not silently skip it.

---
---

# PART 1: UNIVERSAL RULES (portable to any project)

## 1. Definition of Done

Work is **not** done when the code is written. It is done when every box below is ticked.

- [ ] **[BLOCKING]** Full data path traced end to end: source, analysis, output, UI (rule 3.1)
- [ ] **[BLOCKING]** Every call site of every changed shared function grepped and updated (rule 2.2)
- [ ] **[BLOCKING]** No logic duplicated: it lives in exactly one module (rule 2.1)
- [ ] **[BLOCKING]** Output verified against real data, not test fixtures (rule 3.2)
- [ ] Framework hard rules scanned (rule 3.4)
- [ ] Smoke tested in the actual screen the user opens, not just the one that was edited
- [ ] Committed and pushed, to all relevant branches (rule 6)

Never report "done", "fixed" or "shipped" until the blocking items are actually verified. If something is untested, say exactly which part is untested.

## 2. Code structure

### 2.1 One piece of logic, exactly one place **[BLOCKING]**

Every piece of logic (AI orchestration, batch loops, error handling, data prep, retries, anything that is not a UI widget) MUST live in exactly one shared module (`utils/`, `lib/`, `core/`, whatever the project calls it). View and page files may only import and call.

There must never be two versions of "the same thing with slightly different details". If two screens need it, extract it FIRST, then call it from both. Do not ask permission to consolidate, just do it as part of the fix.

*Cost of ignoring this: the same silent-failure bug had to be diagnosed and fixed twice, in two near-identical copies of a batch loop.*

Practical test: any time a function is added inside a view file that does more than render widgets, ask "should this be in utils?". The answer is almost always yes.

### 2.2 Grep every call site **[BLOCKING]**

When adding a parameter, or any new behaviour gated on a parameter, to a shared function: grep the function name across the whole repo and confirm every match either passes the new argument or is genuinely fine with the default.

*Cost of ignoring this: a new parameter was wired up in one view, but the shared helper was also imported by the view the user actually navigates to. The gated block silently did nothing while the fix was reported as live.*

### 2.3 When fixing a bug, hunt the twins

Always grep for copy-paste twins of the buggy code elsewhere. Either fix every site in the same commit, or, preferred, consolidate them into one module.

## 3. Testing and verification

### 3.1 Trace the full data flow before committing **[BLOCKING]**

Before committing any analysis feature:
1. What raw data does it read? Is that data correct and complete?
2. What does it output? Is the output consumed correctly downstream?
3. Does the UI show sensible results for **real** data, not just for a happy-path test case?

Before committing any text or content generation:
1. What data is sent to the model? Is it the real editorial content, or noise scraped from the page (grids, prices, nav)?
2. Does the output fit the target position on the page (top, bottom, meta)?
3. Are URLs, anchors and facts correct and evergreen?

Then ask: *"If I were the user clicking this button, would the result make me trust the system or lose confidence?"*

Watch for silent fallbacks. A crawler that crashes on item 2 and quietly falls back for the remaining 400 items is worse than one that stops loudly.

### 3.2 Verify every recommendation against current data **[BLOCKING]**

Never show a recommendation without first checking it is actually still needed.

- Before recommending a title or metadata change: compare current value with proposed value
- Before recommending a redirect or merge: check whether the two things serve different purposes
- Before recommending a content change: read the current content state
- Before suggesting a new item: check whether an equivalent already exists
- If the fix is already in place, render "Already handled", not an action

The cost of a false recommendation is user trust, and it is the most expensive thing to lose.

### 3.3 Destructive actions: read the code, never the label **[BLOCKING]**

Before telling the user what a destructive control does (Reset, Delete, Clear, Purge, Rebuild), open its source and quote the exact list of keys, file prefixes or paths it touches. Never paraphrase the UI description: descriptions rot, code is truth.

*Cost of ignoring this: a "Reset all analyses" button was described as preserving the expensive AI results. Its prefix list actually included them. The user lost roughly 5 hours of paid model calls, unrecoverably.*

If being wrong costs the user hours of paid work or unrecoverable data, the right answer is a confirmation dialog or a narrower, surgical control, not a one-line recommendation.

### 3.4 Framework hard rules: scan before pushing

Every framework has constraints that fail at runtime, not at import. Keep a project-specific list in Part 2 and scan (AST or grep) before pushing. Never assume a rendering change is safe because it compiles.

### 3.5 Security-sensitive changes must be tested as an outsider

For anything touching auth, sessions or access control: open the app in a fresh incognito window without logging in first. If you can see the app, it is broken, regardless of what the code looks like.

## 4. Output quality

### 4.1 Generated text must be indistinguishable from human writing

All model-generated end-user text must read as if a human wrote it and must survive AI-detection. Concretely: zero em-dashes and en-dashes, no AI-tell vocabulary or openers, varied sentence rhythm.

Enforce this in **both** the prompt **and** a deterministic post-generation code check. A prompt alone is not enforcement. Strip, do not cap: "keep at most a few" means they leak.

### 4.2 Volatile facts never belong in body text

Prices, stock status, delivery times and promotional discounts must never appear as literals in generated body text. They change daily, the text does not. Use placeholder markers filled by the CMS or feed at render time, and add a post-generation validator that rejects currency and stock patterns outside the structured-data block.

## 5. UX rules

### 5.1 Every view must state the action, not just the data

Never ship a table of data without also showing what change to make. Each item should be an action card with: a clear action title, step by step instructions in plain language, the exact target to edit, and a button that generates copy-paste ready output. Sort by priority, and make it obvious what to do with generated content.

### 5.2 Never ask the user to do it manually

The user is building a platform, not buying consulting. Never write "investigate this manually", "check this yourself", or "paste this into the chat". If the code can do it, build it into the tool as a one-click action.

### 5.3 Never make the user work out dependencies

If a code change invalidates upstream results, the system must detect it, not the user. Stale upstream data should be auto-detected and surfaced with a one-click re-run button. Never answer "which step do I run" with instructions: that question is a bug report.

### 5.4 Always name the page

When telling the user to click something, always state which page or view it lives on, and quote the button label exactly as it appears in the source. Grep for the control first, then write "On the **X** page, click **Y**".

## 6. Git and deploy discipline

1. **Always commit and push after code changes.** Local changes are worthless: the app runs on a hosted service. Do not ask, just do it.
2. **Except during a live run.** A push triggers a redeploy, which restarts the container, kills the in-flight job and logs the user out. If a long operation is running, hold the commit and say "tell me when the run is done and I will push".
3. **Push to every site branch.** After pushing the trunk, merge it into every deployed site branch and push those too. A fix sitting only on the trunk means the other services keep running the bug. Verify all refs point at the same commit afterwards.

## 7. Security

**Never hydrate authentication from server-shared state.** Do not persist auth to a disk file that any new session can read and match. If the stored value is identical for every visitor, the first successful login silently grants access to everyone, forever.

- Keep auth per browser session
- If cross-session persistence is genuinely needed, bind it to a per-session random token, and hydrate only when the incoming session presents a matching token
- Always ask who can read the persistence layer. Shared volumes mean "for anyone visiting this URL", never "for this user only"
- Test as in rule 3.5 before declaring auth fixed

## 8. Environment safety

**Never blanket-kill processes.** No `Get-Process python | Stop-Process`, no `taskkill /IM`, no `pkill`. The user runs their own long jobs on the same machine, and any process not personally started may be theirs.

- Kill only processes started in this session, by tracked PID
- A hanging tool call may be caused by machine load from someone else's job. Diagnose that first
- Ask before any destructive process action beyond known PIDs

Same principle for files, databases and branches: look at the target before deleting or overwriting.

## 9. Language

All UI labels, explanations, placeholders and documentation are **English**, for international applicability.

Everything that analyses user content (stop words, CTA detection, regex for FAQ/review/guide patterns, keyword processing, prompts) must respect the **configured content language**, read from config or an environment variable. Never hardcode words from one language into prompts or templates: pass a `language` parameter.

## 10. Working style

- Deliver the requested scope. Do not silently narrow, widen or transform it
- If part of the task is blocked, finish everything else in full and say explicitly what was left out and why
- Report outcomes faithfully. If tests fail, show the output. If a step was skipped, say so
- Do not build features for a different project in this repo. Confirm the target repo before starting (see Part 2)

---
---

# PART 2: PROJECT SPECIFICS (`C:\gsc-seo`)

## 2.1 What this repo is

A **SEO analysis and recommendation tool** for the existing mshop.se / mshop.dk / mshop.eu shops. It analyses Google Search Console data and also **pushes generated text into the live CMS** via the Mshop Admin API and the Magento Footer Text API.

**Stack:** Streamlit UI (`main`) plus a NiceGUI rebuild in `nicegui_app/` (branch `nicegui-migration`) · Claude API for generation · GSC API, Ahrefs CSV, Screaming Frog CSV for data · Playwright for scraping · Railway deploy with a persistent `/data` volume · branch per site.

## 2.2 What does NOT belong here

Greenfield sites, new affiliate sites, competitor-data-driven site building, product feeds, WordPress publishing, author personas, tone-of-voice profiles. All of that belongs in **`C:\wp-system`**, which already has a complete codebase for it (`wp_publisher/`, `WP-SYSTEM-MANUAL.md`).

The default working directory being `C:\gsc-seo` does not mean affiliate work belongs here. When in doubt, ask which repo.

Also forbidden here: hardcoded Swedish words in prompts or templates (rule 9), duplicated logic across views (rule 2.1), pushing to `main` without merging to the site branches (rule 6.3).

## 2.3 Layout

- `views/` Streamlit screens. Rendering only, per rule 2.1
- `utils/` all shared logic, the single source of truth
- `nicegui_app/` the NiceGUI rebuild. See `nicegui_app/README.md` for current status and how to resume
- `scripts/deploy_all_sites.ps1` the branch fan-out helper

Single sources of truth to respect, never re-implement:

| Concern | The one place |
|---|---|
| Pipeline step definitions | `views/run_pipeline.py` PIPELINE_STEPS (Streamlit) / `utils/pipeline.py` (NiceGUI) |
| All Claude calls | `utils/ai_generator.py` |
| Cache key derivation | `utils/cache_keys.py` |
| Generate all fixes for one page | `utils/page_fix_runner.py` |
| Push a page live | `utils/page_fix_runner.push_all_for_page()` |
| Em-dash / AI-tell stripping | `utils/text_clean.strip_ai_dashes` |
| Persistence to `/data` | `utils/persistence.py` |
| Per-language prompt variation | `utils/lang_prompts.py` |
| Content type instructions | `utils/templates.py` |

## 2.4 Storage model

- **Session state**: RAM for one Streamlit run, auto-hydrated from disk at startup
- **`/data/<key>.csv|json`**: `PERSIST_KEYS`, for example gsc_data, audit_results, topic_clusters, page_authority, mshop_active_pages
- **`/data/ai_cache/<key>.json`**: `AI_CACHE_PREFIXES`, for example `_quality_*`, `_ai_plan_*`, `_bottom_text_*`, `_intro_text_*`, `_cluster_health_*`
- Generated text exists on disk **before** push. Pushing does not re-fetch: the local cache is source of truth

## 2.5 Hard project rules

1. **Canonical URLs.** `audit_results` rows store `normalize_url(url)`: https, no www, no trailing slash. This is what keeps `stable_hash(url)` consistent between generation and push. Breaking it reintroduces the "admin says skipped while the text is visible" bug.
2. **Cache keys** are `_ai_plan_<h>`, `_bottom_text_<h>`, `_intro_text_<h>`, `_quality_<h>` where `h = stable_hash(url)`. Derive and read them only via `utils/cache_keys.py`. Fields: bottom is `bottom_html`, intro is `optimized_text`, plan is `meta_title` / `meta_description`.
3. **Pushing live** goes through `push_all_for_page()`. Do not inline a second push sequence anywhere.
4. **Em-dash stripping** is enforced at the live-push boundary in `mshop_admin_api.update_for_page` and `footer_text_api.push_footer_text`, so no path can leak one. Mirror `_reduce_em_dash_overuse(text, max_keep=0)` in any new generation path (rule 4.1).
5. **Streamlit: no nested expanders.** `st.expander` inside `st.expander` raises at render and crashes the page. Before pushing any expander change, AST-scan `views/` and `utils/` for `ast.With` nodes whose context expression is `st.*.expander` with an expander ancestor. For a collapsible look inside an expander use a bold `st.markdown` label plus `st.container()` (rule 3.4).
6. **Streamlit: never render operator messages inline before `st.rerun()`.** The rerun wipes them instantly. Store the message in `st.session_state` (for example `_pipeline_notice`) and render it from a persistent box at the top of `render()`, with a dismiss button. Pattern lives in `views/run_pipeline.py`.
7. **Re-clustering** invalidates embedded internal links but not prose. Any cluster-derived cache must fingerprint the clusters it was built from.
8. **Prices and stock** never appear in product body text, only as `{{PRICE}}` / `{{AVAILABILITY}}` markers filled by the CMS (rule 4.2).

## 2.6 Deploy

```powershell
git push origin main
.\scripts\deploy_all_sites.ps1     # merges main into mshop-dk, mshop-eu and pushes
git log --oneline --all -3         # verify all refs point at the same commit
```

Fallback if the script is unavailable:

```bash
for b in mshop-dk mshop-eu; do
  git checkout $b && git merge main --no-edit && git push origin $b
done
git checkout main
```

Do not run any of this while a long operation (Cluster Health, Fix ALL, Bulk Audit) is live on the affected shop (rule 6.2).

---
---

# PART 3: PORTING THIS FILE TO ANOTHER PROJECT

1. Copy this file to the new repository root as `CLAUDE.md`.
2. Keep **Part 1 verbatim**. It is deliberately project-agnostic. The only thing to adjust is rule 3.4, where the framework hard rules for the new stack go, and rule 6, if the deploy model differs.
3. **Replace Part 2 entirely.** Fill in, for the new project:
   - What the repo is, and what explicitly does not belong in it
   - The stack and deploy target
   - The directory layout and the "single source of truth" table
   - The storage or state model
   - The hard rules learned the hard way in that project, each with the failure it prevents
   - The exact deploy commands
4. **Grow Part 2, not Part 1.** Every time a bug reaches production, add one numbered rule with (a) what to do and (b) the concrete cost of not doing it. The cost is what makes a rule stick.
5. Keep the file loaded automatically. In Claude Code that means `CLAUDE.md` at the repository root. It is read every session, so keep it dense: rules and consequences, no prose padding.
