"""The SEO flow — one framework-agnostic definition of the whole pipeline.

This is the single source of truth for "what are the steps, in what order,
grouped how, and how do we know a step is done" (goals #2 understandable +
consistent, #5 no duplication). The NiceGUI control center renders this; a
later Streamlit shim can render the same list. No st.* / no ui.* here.

Each step's ``run`` is a thin call into already-shared logic in utils/ (the
same functions the live Streamlit app uses today) — it takes a Progress and
reads/writes state(). Steps whose orchestration still lives inside the
Streamlit view (bulk audit, the big AI planning calls) have ``run=None`` and
are shown as "port pending" rather than pretending to work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from utils.progress import Progress, NULL


# ── step model ───────────────────────────────────────────────────────

@dataclass
class Step:
    id: str
    title: str
    description: str
    phase: str
    state_key: Optional[str] = None            # key in state() signalling "done"
    run: Optional[Callable] = None             # run(progress: Progress) -> None
    kind: str = "run"                          # "run" | "data" (interactive page)
    page: Optional[str] = None                 # route for data/view steps
    optional: bool = False                     # optional input (skippable)
    done_fn: Optional[Callable] = None         # custom done-check(store) -> bool


PHASES = [
    "1 · Connect & import",
    "2 · Understand the site",
    "3 · Find opportunities",
    "4 · Plan & act",
]


# ── run wrappers (thin calls into shared utils logic) ────────────────
# Each mirrors what views/run_pipeline.py does today, minus Streamlit: read
# inputs from state(), call the shared logic, write results + persist.

def _run_fetch_gsc(progress: Progress = NULL) -> None:
    from utils.state import state
    from utils.persistence import save_key
    from utils.gsc_client import build_gsc_service, fetch_gsc_data
    s = state()
    creds = s.get("gsc_credentials")
    site = s.get("gsc_site") or s.get("gsc_site_url")
    if not creds or not site:
        raise ValueError("GSC not connected — connect credentials + pick a property first")
    with progress.spinner("Fetching Google Search Console data…"):
        service = build_gsc_service(creds)
        s["gsc_service"] = service
        s["gsc_data"] = fetch_gsc_data(service, site)
        s["gsc_site"] = site
    save_key("gsc_data"); save_key("gsc_site")


def _run_build_authority(progress: Progress = NULL) -> None:
    import pandas as pd
    from utils.state import state
    from utils.persistence import save_key
    from utils.ahrefs_import import build_page_authority
    s = state()
    bbl = s.get("ahrefs_best_by_links")
    if bbl is None or getattr(bbl, "empty", True):
        s["page_authority"] = pd.DataFrame()   # done-but-empty (optional input)
        progress.done("No Ahrefs authority data — skipped (optional)")
        return
    s["page_authority"] = build_page_authority(
        best_by_links_df=bbl, backlinks_df=s.get("ahrefs_backlinks")
    )
    save_key("page_authority")


def _run_clusters(progress: Progress = NULL) -> None:
    from utils.clustering import generate_topic_clusters
    with progress.spinner("Building topic clusters from the keyword universe…"):
        generate_topic_clusters()


def _run_ctr_gaps(progress: Progress = NULL) -> None:
    from utils.state import state
    from utils.persistence import save_key
    from utils.gsc_client import identify_ctr_gaps
    s = state()
    df = s.get("gsc_data")
    if df is None or getattr(df, "empty", True):
        raise ValueError("GSC data not loaded — run 'Fetch GSC data' first")
    s["ctr_gaps"] = identify_ctr_gaps(df, gap_threshold=-5)
    save_key("ctr_gaps")


def _run_cannibalization(progress: Progress = NULL) -> None:
    from utils.state import state
    from utils.persistence import save_key
    from utils.cannibalization import (
        detect_cannibalization, get_page_cannibalization_summary,
        get_cannibalization_clusters,
    )
    s = state()
    df = s.get("gsc_data")
    if df is None or getattr(df, "empty", True):
        raise ValueError("GSC data not loaded — run 'Fetch GSC data' first")
    with progress.spinner("Detecting keyword cannibalization…"):
        cdf = detect_cannibalization(df, min_impressions=10)
    s["cannibalization"] = cdf
    s["cannibal_page_summary"] = get_page_cannibalization_summary(cdf)
    s["cannibal_clusters"] = get_cannibalization_clusters(cdf)
    save_key("cannibalization")


def _run_bulk_audit(progress: Progress = NULL) -> None:
    from utils.audit_runner import run_bulk_audit
    run_bulk_audit(progress)


def _run_cluster_health(progress: Progress = NULL) -> None:
    from utils.state import state
    from utils.cluster_health_runner import run_all_clusters
    s = state()
    if not (s.get("topic_clusters") or {}).get("clusters"):
        raise ValueError("Build topic clusters first")

    def _cb(i, n, topic):
        progress.step(f"Cluster {i}/{n} — {str(topic)[:60]}", pct=(i / n if n else None))

    s["_cluster_health_summary"] = run_all_clusters(progress_cb=_cb)


def _run_quality(progress: Progress = NULL) -> None:
    from utils.state import state
    from utils.quality_check_runner import (
        run_until_done, eligible_pages, eligibility_diagnosis,
    )
    audit = state().get("audit_results", []) or []
    if not audit:
        raise ValueError("Run bulk audit first")
    eligible = eligible_pages(audit)
    if not eligible:
        raise ValueError(eligibility_diagnosis(audit))

    def _on_progress(done, tot):
        progress.step(f"AI quality — {done}/{tot} categories", pct=(done / tot if tot else None))

    run_until_done(audit, on_progress=_on_progress)


def _run_cluster_linking(progress: Progress = NULL) -> None:
    from utils.state import state
    from utils.persistence import save
    from utils.cluster_linking import generate_cluster_link_recommendations
    s = state()
    clusters = (s.get("topic_clusters") or {}).get("clusters", [])
    if not clusters:
        raise ValueError("Build topic clusters first")
    recs = generate_cluster_link_recommendations(
        clusters, s.get("audit_results", []) or [], s.get("sf_link_map", {}) or {}
    )
    s["cluster_link_recommendations"] = recs
    try:
        save("cluster_link_recommendations")
    except Exception:
        pass


def _quality_done(s) -> bool:
    from utils.quality_check_runner import eligible_pages, already_checked_count
    eligible = eligible_pages(s.get("audit_results", []) or [])
    return bool(eligible) and already_checked_count(eligible) >= len(eligible)


# ── the flow ─────────────────────────────────────────────────────────

STEPS = [
    # Phase 1 — Connect & import
    Step("fetch_gsc", "Fetch GSC data",
         "Pull your Search Console queries — the keywords you already rank for.",
         PHASES[0], state_key="gsc_data", run=_run_fetch_gsc),
    Step("import_competitors", "Import competitor keywords",
         "Upload each competitor's Ahrefs export. Brand terms stripped, unioned "
         "into one keyword universe — this is where the extra ~5x keywords come from.",
         PHASES[0], state_key="keyword_universe", kind="data", page="/keywords"),
    Step("build_authority", "Build page authority",
         "Optional: Ahrefs backlinks → per-page authority so we don't touch your "
         "strongest URLs carelessly.",
         PHASES[0], state_key="page_authority", run=_run_build_authority, optional=True),
    Step("import_crawl", "Import crawl (Screaming Frog)",
         "Optional: upload a Screaming Frog crawl for broken links / orphans / redirects.",
         PHASES[0], state_key="sf_crawl_issues", kind="data", optional=True),  # port pending

    # Phase 2 — Understand the site
    Step("clusters", "Build topic clusters",
         "Group the whole keyword universe into topics. Competitor gaps are tagged "
         "as opportunities.",
         PHASES[1], state_key="topic_clusters", run=_run_clusters),
    Step("bulk_audit", "Audit pages",
         "Scrape every live category/CMS page for text, headings, keyword coverage.",
         PHASES[1], state_key="audit_results", run=_run_bulk_audit),
    Step("cluster_health", "Cluster health review",
         "Strategic per-cluster AI review before any per-page writing.",
         PHASES[1], state_key="_cluster_health_summary", run=_run_cluster_health),

    # Phase 3 — Find opportunities
    Step("ctr_gaps", "CTR gaps",
         "Pages with impressions but weak clicks — title/meta rewrites.",
         PHASES[2], state_key="ctr_gaps", run=_run_ctr_gaps),
    Step("cannibalization", "Cannibalization",
         "Multiple pages fighting for the same keyword.",
         PHASES[2], state_key="cannibalization", run=_run_cannibalization),
    Step("keyword_gaps", "Keyword gaps",
         "The payoff: searches competitors rank for and you don't, as content "
         "opportunities prioritized by volume.",
         PHASES[2], state_key="keyword_universe", kind="view", page="/gaps"),
    Step("content_quality", "AI content quality",
         "Assess each eligible category's text: keep / improve / rewrite.",
         PHASES[2], state_key=None, run=_run_quality, done_fn=_quality_done),

    # Phase 4 — Plan & act
    Step("cluster_linking", "Internal linking plan",
         "Vertical + horizontal internal-link recommendations per cluster.",
         PHASES[3], state_key="cluster_link_recommendations", run=_run_cluster_linking),
    Step("site_validation", "Site validation",
         "AI review of overall structure + health score.",
         PHASES[3], state_key="_site_validation"),        # port pending
    Step("ideal_structure", "Ideal structure",
         "AI proposes the ideal cluster/merge/delete/create map.",
         PHASES[3], state_key="_ideal_structure"),        # port pending
    Step("gap_analysis", "Migration plan",
         "Phased plan from current to ideal structure.",
         PHASES[3], state_key="_gap_analysis"),           # port pending
    Step("plan_validation", "Plan validation",
         "Cross-check all per-page plans against site issues.",
         PHASES[3], state_key="_plan_validation"),        # port pending
]


# ── status helpers (pure — read a store dict) ────────────────────────

def _nonempty(v) -> bool:
    if v is None:
        return False
    if hasattr(v, "empty"):              # DataFrame
        return not v.empty
    if isinstance(v, dict):
        # cluster/summary dicts count as done only if they carry content
        if "clusters" in v:
            return bool(v.get("clusters"))
        if "total" in v:
            return int(v.get("total", 0) or 0) > 0
        return bool(v)
    if hasattr(v, "__len__"):
        return len(v) > 0
    return bool(v)


def is_done(step: Step, store) -> bool:
    if step.done_fn:
        try:
            return bool(step.done_fn(store))
        except Exception:
            return False
    if not step.state_key:
        return False
    return _nonempty(store.get(step.state_key))


def is_ready(step: Step) -> bool:
    """Can this step be triggered from the UI yet (logic ported)?"""
    return step.run is not None or step.kind in ("data", "view")


def step_count(step: Step, store) -> str:
    """Short human count for a done step (e.g. '1,204 queries')."""
    if not step.state_key:
        return "done"
    v = store.get(step.state_key)
    if isinstance(v, dict) and "clusters" in v:
        return f"{len(v.get('clusters', []))} clusters"
    if hasattr(v, "empty"):
        return f"{len(v):,} rows" if not v.empty else "empty"
    if hasattr(v, "__len__") and not isinstance(v, (str, dict)):
        return f"{len(v):,} items"
    return "done"


def steps_by_phase():
    """Ordered [(phase, [steps])] for grouped rendering."""
    return [(p, [s for s in STEPS if s.phase == p]) for p in PHASES]


def remaining_runnable(store):
    """Runnable steps (have a run fn) not yet done, in flow order."""
    return [s for s in STEPS if s.run is not None and not is_done(s, store)]
