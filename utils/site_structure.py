"""Framework-free site-structure table — shared by site validation + exports.

Ported from views/site_map_export._build_site_structure. Delegates to the
already-decoupled utils/page_profile.build_page_profile (state()-based), so
the only change from the view copy is reading ``_no_cluster_needed`` through
state() instead of st.session_state. One row per unique URL with every metric
site validation / ideal structure need.

(The Streamlit view keeps its own copy until it is ported; this util is the
source of truth for the NiceGUI flow. See feedback_shared_logic_in_utils.)
"""

from __future__ import annotations

from urllib.parse import urlparse

import pandas as pd

from utils.state import state
from utils.ui_helpers import normalize_url as _norm_url


def build_site_structure(audit_results, gsc_data, topic_clusters, page_authority=None) -> pd.DataFrame:
    """One row per URL with page type, cluster, GSC + authority + audit metrics."""
    from utils.page_profile import build_page_profile

    rows = []
    audit_by_url = {_norm_url(r["url"]): r for r in audit_results}
    audited_set = set(audit_by_url.keys())

    # URLs the user marked "no cluster needed" — via state(), not st.
    _no_cluster_set = {
        _norm_url(u) for u in (state().get("_no_cluster_needed") or [])
    }

    raw_urls = set(r["url"] for r in audit_results)
    if gsc_data is not None and hasattr(gsc_data, "page"):
        raw_urls.update(gsc_data["page"].unique().tolist())

    # Deduplicate by param-stripped URL, keeping the shortest variant.
    seen_norm = {}
    for url in raw_urls:
        norm = _norm_url(url)
        if norm not in seen_norm or len(url) < len(seen_norm[norm]):
            seen_norm[norm] = url
    all_urls = set(seen_norm.values())

    for url in sorted(all_urls):
        parsed = urlparse(url)
        path = parsed.path.rstrip("/") or "/"
        depth = len([p for p in path.split("/") if p])
        parent_parts = path.strip("/").split("/")[:-1]
        parent_url = f"https://{parsed.netloc}/{'/'.join(parent_parts)}" if parent_parts else ""

        profile = build_page_profile(url)

        cluster_names = [c.get("topic", "") for c in profile["clusters"][:3]]
        url_norm = _norm_url(url)
        # First-match sentinel ordering (same as the view): not-audited →
        # product → no-cluster-needed, so the "unclustered" metric is honest.
        if not cluster_names and url_norm not in audited_set:
            cluster_names = ["(not audited yet)"]
        elif not cluster_names and profile.get("page_type") == "product":
            cluster_names = ["(product — n/a)"]
        elif not cluster_names and url_norm in _no_cluster_set:
            cluster_names = ["(no cluster needed)"]

        avg_pos = None
        if profile["gsc_queries"]:
            positions = [q["position"] for q in profile["gsc_queries"] if q.get("position")]
            avg_pos = round(sum(positions) / len(positions), 1) if positions else None

        audit = audit_by_url.get(_norm_url(url), {})

        rows.append({
            "URL": url,
            "Path": path,
            "Depth": depth,
            "Page Type": profile["page_type"],
            "Parent URL": parent_url,
            "Cluster(s)": " | ".join(cluster_names) if cluster_names else "",
            "Primary Keyword": profile["primary_query"],
            "Impressions": profile["total_impressions"],
            "Clicks": profile["total_clicks"],
            "Avg Position": avg_pos,
            "Backlinks (domains)": profile["referring_domains"],
            "Meta Score": audit.get("meta_score", ""),
            "Content Score": audit.get("content_score", ""),
            "AI Quality": f"{profile['quality_score']}/10 {profile['quality_verdict']}" if profile["quality_verdict"] else "",
            "Word Count": profile["word_count"],
            "Links Out": profile["internal_links_out_count"],
            "Links In": profile["internal_links_in_count"],
            "Title": profile["title"][:80],
            "H1": profile["h1"][:80],
        })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Depth", "URL"])
