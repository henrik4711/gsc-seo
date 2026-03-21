"""
Shared UI helpers for consistent next-step guidance across pages.
"""

import streamlit as st
from urllib.parse import urlparse


def stable_hash(text: str) -> str:
    """Deterministic hash that stays the same across process restarts."""
    import hashlib
    return hashlib.md5(text.encode()).hexdigest()[:8]


def shorten_url(url: str) -> str:
    """Strip the domain from a URL, returning just the path."""
    parsed = urlparse(url)
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def normalize_url(url: str) -> str:
    """
    Normalize a URL for consistent matching across the entire system.
    Handles: http/https, www, trailing slashes, case, relative URLs.
    """
    if not url:
        return ""
    u = str(url).strip()
    # Convert relative to absolute (assume https + www.mshop.se for now)
    if u.startswith("/") and not u.startswith("//"):
        u = "https://www.mshop.se" + u
    # Standardize protocol
    u = u.replace("http://", "https://")
    # Keep www (it's part of the canonical URL for mshop.se)
    # Remove trailing slash
    u = u.rstrip("/")
    # Lowercase
    u = u.lower()
    # Remove fragment (#section)
    if "#" in u:
        u = u[:u.index("#")]
    # Remove tracking params but keep meaningful query strings
    if "?" in u:
        base, query = u.split("?", 1)
        # Remove common tracking params
        import re
        params = query.split("&")
        clean_params = [p for p in params if not re.match(r"^(utm_|itm_|ref=|fbclid|gclid)", p)]
        u = base + ("?" + "&".join(clean_params) if clean_params else "")
    return u


STEP_ORDER = [
    ("gsc_data",          "1. Setup & Connect",    "Connect GSC and add API keys"),
    ("page_authority",    "2. Upload Ahrefs",      "Upload Ahrefs CSV files for backlink data"),
    ("ctr_gaps",          "3. CTR Analysis",       "Click 'Analyze CTR Gaps' to find underperformers"),
    ("cannibalization",   "4. Cannibalization",    "Click 'Analyze Cannibalization' to find keyword conflicts"),
    ("topic_clusters",    "5. Topic Clusters",     "Click 'Build Topic Clusters' to group keywords"),
    ("audit_results",     "6. Page Auditor",       "Click 'Run Audit' to check meta and content"),
    ("linking_fixes",     "7. Internal Linking",   "Review and fix internal linking issues"),
    ("keyword_fixes",     "8. Missing Keywords",   "Fill keyword gaps with AI-generated text"),
    ("new_articles",      "9. New Articles",       "Plan and generate new articles"),
    ("clusters_checked",  "10. Cluster Health",     "AI evaluates topic cluster health"),
    ("generated_content", "11. Content Generator",  "Select a page and generate AI-optimized content"),
    ("sitemap_viewed",    "12. Site Map",             "Export complete site structure + AI validation"),
    ("tasks_viewed",      "13. All Tasks",            "Review unified task list across all analyses"),
    ("action_plan",       "14. Implementation",      "Step-by-step fix guide for every page"),
]


def show_next_step():
    """Show a box at the bottom telling the user what to do next."""
    for state_key, step_name, description in STEP_ORDER:
        if state_key not in st.session_state:
            st.markdown(f"""
            <div style="margin-top:2rem; padding:1rem; background:#0d0d1a; border:1px solid #5533ff; border-radius:8px;">
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#5533ff; letter-spacing:0.1em; margin-bottom:0.3rem;">
                    NEXT STEP
                </div>
                <div style="font-size:0.9rem; color:#e8e8f0; font-weight:600;">
                    {step_name}
                </div>
                <div style="font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;">
                    {description}
                </div>
            </div>
            """, unsafe_allow_html=True)
            return
    # All done
    st.markdown("""
    <div style="margin-top:2rem; padding:1rem; background:#0d1a0d; border:1px solid #33dd88; border-radius:8px;">
        <div style="font-size:0.9rem; color:#33dd88; font-weight:600;">
            Pipeline complete! All steps finished.
        </div>
    </div>
    """, unsafe_allow_html=True)


def show_missing_step(step_name: str, description: str):
    """Show a warning that a previous step needs to be completed first."""
    st.warning(f"Go to **{step_name}** first: {description}")
