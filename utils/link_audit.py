"""
Stale internal-link detection across the per-page AI text cache.

When the cluster structure changes (e.g. raising max keywords from 28 to
66 clusters), the hub/spoke relationships and anchor expectations shift,
so internal links baked into already-generated text can become wrong.

This module is the FREE (no-AI) detection pass: it reads each page's
cached generated HTML (bottom_html + intro), runs the existing
cluster-link-direction validator against the CURRENT clusters, and
reports which pages have link issues. Fixing/pushing is a separate step.
"""

from utils.ui_helpers import normalize_url


# issue-string prefix -> stable type key (mirrors the three patterns in
# utils.ai_generator._validate_cluster_link_directions)
def _classify(issue: str) -> str:
    if issue.startswith("HUB→SPOKE"):
        return "hub_spoke_anchor"
    if issue.startswith("SPOKE missing hub link"):
        return "missing_hub_link"
    if issue.startswith("SPOKE→HUB anchor mismatch"):
        return "anchor_mismatch"
    return "other"


def scan_cached_link_issues(audit_results: list, topic_clusters: dict) -> dict:
    """Scan every page's CACHED generated text for internal-link issues
    against the CURRENT cluster structure. No AI calls.

    Returns:
      {
        "scanned": int,          # pages that had cached text to check
        "with_issues": int,
        "pages": [               # only pages WITH issues, most issues first
            {"url", "page_type", "issues": [str], "n_issues": int},
        ],
        "by_type": {"hub_spoke_anchor": n, "missing_hub_link": n,
                    "anchor_mismatch": n, "other": n},
      }
    """
    result = {
        "scanned": 0,
        "with_issues": 0,
        "pages": [],
        "by_type": {"hub_spoke_anchor": 0, "missing_hub_link": 0,
                    "anchor_mismatch": 0, "other": 0},
    }
    if not audit_results or not topic_clusters:
        return result

    # Lazy imports — keep this a leaf module (ai_generator imports
    # topical_scope, so importing the validator at top level risks cycles).
    try:
        from utils.ai_generator import _validate_cluster_link_directions
        from utils.cache_keys import get_generated_content
    except Exception:
        return result

    audit_by_url = {normalize_url(r.get("url", "")): r
                    for r in audit_results if r.get("url")}

    for r in audit_results:
        url = r.get("url", "")
        if not url:
            continue
        cached = get_generated_content(url)
        full_html = " ".join(
            part for part in (cached.get("bottom_html", ""),
                              cached.get("intro_html", "")) if part
        ).strip()
        if not full_html:
            continue  # nothing we generated/can repush for this page
        result["scanned"] += 1

        try:
            issues = _validate_cluster_link_directions(
                url, full_html, topic_clusters, audit_by_url,
            )
        except Exception:
            issues = []
        if not issues:
            continue

        result["with_issues"] += 1
        for iss in issues:
            result["by_type"][_classify(iss)] += 1
        result["pages"].append({
            "url": url,
            "page_type": r.get("page_type", "unknown"),
            "issues": issues,
            "n_issues": len(issues),
        })

    result["pages"].sort(key=lambda p: -p["n_issues"])
    return result
