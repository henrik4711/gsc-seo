import os
import streamlit as st
from config import init_from_env
from utils.persistence import load_all, save_all, get_storage_info

st.set_page_config(
    page_title="SEO Intelligence Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Password protection ──────────────────────────────────────
# Set APP_PASSWORD env var on Railway to enable.
# Without it, the app is open (for local dev).
_app_password = os.environ.get("APP_PASSWORD", "")
if _app_password:
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.markdown("## 🔒 SEO Intelligence Platform")
        pw = st.text_input("Password", type="password", key="login_pw")
        if st.button("Login", type="primary"):
            if pw == _app_password:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Wrong password")
        st.stop()

# Custom CSS - dark theme with high contrast text
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Syne:wght@400;600;700;800&family=Inter:wght@300;400;500&display=swap');

/* ── GLOBAL TEXT COLOR OVERRIDE ─────────────────────────── */
html, body, [class*="css"],
.stApp, .stApp * {
    font-family: 'Inter', sans-serif;
    color: #e8e8f0;
}

/* Hide default streamlit elements */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header [data-testid="stToolbar"] {
    visibility: hidden;
}
header [data-testid="stDecoration"] {
    visibility: hidden;
}
/* Force the running indicator visible with bright styling */
header {
    background: transparent !important;
    visibility: visible !important;
}
header [data-testid="stStatusWidget"] {
    visibility: visible !important;
    background: #1a1a2e !important;
    border: 2px solid #ff4455 !important;
    border-radius: 8px !important;
    padding: 6px 12px !important;
    opacity: 1 !important;
}
header [data-testid="stStatusWidget"] label,
header [data-testid="stStatusWidget"] span,
header [data-testid="stStatusWidget"] div,
header [data-testid="stStatusWidget"] p {
    color: #ff4455 !important;
    visibility: visible !important;
}
header [data-testid="stStatusWidget"] svg {
    fill: #ff4455 !important;
    visibility: visible !important;
    filter: none !important;
}
header [data-testid="stStatusWidget"] button {
    color: #ff4455 !important;
    border-color: #ff4455 !important;
    background: #12121f !important;
    visibility: visible !important;
}

/* Background */
.stApp {
    background: #0a0a0f;
}

/* ── ALL TEXT: force light on dark ───────────────────────── */
p, span, label, div, li, td, th, a,
.stMarkdown, .stMarkdown p, .stMarkdown span, .stMarkdown li,
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
    color: #e8e8f0 !important;
}

h1, h2, h3, h4 {
    font-family: 'Syne', sans-serif !important;
    font-weight: 700;
    color: #f0f0ff !important;
}

/* ── Sidebar ────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: #0f0f1a;
    border-right: 1px solid #1e1e2e;
}

section[data-testid="stSidebar"] * {
    color: #d0d0e8 !important;
}

section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    font-family: 'Syne', sans-serif;
    color: #f0f0ff !important;
}

/* ── Radio buttons ──────────────────────────────────────── */
.stRadio label, .stRadio p, .stRadio span,
.stRadio > div > label > div,
.stRadio > div > label > div > p,
[data-testid="stRadio"] label,
[data-testid="stRadio"] p {
    color: #e0e0f0 !important;
}

/* ── All form labels ────────────────────────────────────── */
.stSelectbox label, .stTextInput label, .stNumberInput label,
.stTextArea label, .stRadio label, .stFileUploader label,
.stCheckbox label, .stSlider label,
[data-testid="stWidgetLabel"] label,
[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] span {
    color: #d0d0e8 !important;
    font-size: 0.85rem !important;
}

/* ── Inputs ─────────────────────────────────────────────── */
.stSelectbox > div > div,
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stTextArea > div > div > textarea,
[data-baseweb="select"] > div,
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea {
    background: #12121f !important;
    border: 1px solid #2a2a40 !important;
    border-radius: 6px !important;
    color: #f0f0ff !important;
}

/* Selectbox dropdown text */
[data-baseweb="select"] span,
[data-baseweb="menu"] li,
[data-baseweb="menu"] div,
[role="listbox"] li,
[role="option"] span {
    color: #e8e8f0 !important;
}

/* ── File uploader ──────────────────────────────────────── */
[data-testid="stFileUploader"] div,
[data-testid="stFileUploader"] span,
[data-testid="stFileUploader"] p,
[data-testid="stFileUploader"] label,
[data-testid="stFileUploader"] small {
    color: #d0d0e8 !important;
}

[data-testid="stFileUploaderDropzone"] {
    background: #12121f !important;
    border: 1px dashed #3a3a5c !important;
}

/* ── Metrics ────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: #12121f;
    border: 1px solid #1e1e2e;
    border-radius: 8px;
    padding: 16px;
}

[data-testid="metric-container"] label {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.7rem !important;
    color: #9b9bb8 !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
}

[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-family: 'Syne', sans-serif !important;
    font-size: 1.8rem !important;
    font-weight: 700;
    color: #c8b4ff !important;
}

/* ── Dataframes ─────────────────────────────────────────── */
.stDataFrame {
    border: 1px solid #1e1e2e;
    border-radius: 8px;
}

/* ── Buttons ────────────────────────────────────────────── */
.stButton > button {
    background: #5533ff;
    color: white !important;
    border: none;
    border-radius: 6px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    font-weight: 500;
    letter-spacing: 0.05em;
    padding: 8px 20px;
    transition: all 0.2s ease;
}

.stButton > button:hover {
    background: #7755ff;
    color: white !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(85, 51, 255, 0.4);
}

.stButton > button span {
    color: white !important;
}

/* ── Alert boxes (info, success, warning, error) ────────── */
.stAlert, .stAlert *,
[data-testid="stAlert"], [data-testid="stAlert"] * {
    color: #f0f0ff !important;
}

.stAlert {
    border-radius: 6px;
}

/* ── Expander ───────────────────────────────────────────── */
.streamlit-expanderHeader,
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary span {
    background: #12121f !important;
    border: 1px solid #1e1e2e !important;
    border-radius: 6px !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.8rem;
    color: #e0e0f0 !important;
}

[data-testid="stExpander"] div[data-testid="stExpanderDetails"],
[data-testid="stExpander"] div[data-testid="stExpanderDetails"] * {
    color: #d0d0e8 !important;
}

/* ── Tabs ───────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: #0f0f1a;
    border-bottom: 1px solid #1e1e2e;
    gap: 4px;
}

.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #9b9bb8 !important;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border-radius: 6px 6px 0 0;
}

.stTabs [aria-selected="true"] {
    background: #12121f !important;
    color: #c8b4ff !important;
    border-bottom: 2px solid #5533ff !important;
}

/* ── Status badges ──────────────────────────────────────── */
.badge-critical { color: #ff4455 !important; font-weight: 600; }
.badge-warn { color: #ffaa33 !important; font-weight: 600; }
.badge-ok { color: #33dd88 !important; font-weight: 600; }
.badge-mono { font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; }

/* ── Progress / Spinner ─────────────────────────────────── */
.stProgress > div > div {
    background: #5533ff !important;
}

.stSpinner > div {
    border-top-color: #5533ff !important;
}

/* (running indicator styles are in header section above) */

/* ── Tooltip / help icons ───────────────────────────────── */
[data-testid="stTooltipIcon"] svg {
    fill: #9b9bb8 !important;
}

/* ── Separator / divider ────────────────────────────────── */
hr {
    border-color: #1e1e2e !important;
}
</style>
""", unsafe_allow_html=True)

# Load environment variables (Railway) into session state
init_from_env()

# Load persisted data from volume (audit results, SF data, Ahrefs, etc.)
load_all()

# ── Deep-link from ECN2: ?url=https://... ─────────────────────────
_ecn2_url = st.query_params.get("url")
if _ecn2_url and not st.session_state.get("_ecn2_handled"):
    from utils.ui_helpers import normalize_url as _nu_ecn
    _ecn2_url_norm = _nu_ecn(_ecn2_url)
    st.session_state["_ecn2_url"] = _ecn2_url_norm
    st.session_state["_ecn2_handled"] = True
    # Pre-fill audit queue so Page Auditor picks it up
    st.session_state["audit_queue"] = [_ecn2_url_norm]
    # Pre-fill content generator target
    st.session_state["generate_for_url"] = _ecn2_url_norm
    # Navigate to Page Auditor if audit data exists, otherwise Setup
    if "audit_results" in st.session_state:
        st.session_state["selected_page"] = "6. Page Auditor"
    elif "gsc_data" in st.session_state:
        st.session_state["selected_page"] = "6. Page Auditor"
    else:
        st.session_state["selected_page"] = "1. Setup & Connect"

# Header
st.markdown("""
<div style="padding: 2rem 0 1rem 0; border-bottom: 1px solid #1e1e2e; margin-bottom: 2rem;">
    <div style="font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; color: #5533ff; letter-spacing: 0.2em; text-transform: uppercase; margin-bottom: 0.4rem;">
        ⚡ SEO INTELLIGENCE PLATFORM
    </div>
    <h1 style="margin: 0; font-size: 2rem; background: linear-gradient(135deg, #e8e8f0 0%, #c8b4ff 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
        SEO Intelligence Platform
    </h1>
    <p style="color: #6b6b8a; margin: 0.5rem 0 0 0; font-size: 0.9rem;">
        Analyze CTR gaps, audit pages, validate topic clusters &amp; generate AI-powered content
    </p>
</div>
""", unsafe_allow_html=True)

# Show ECN2 deep-link banner (dismissible)
if st.session_state.get("_ecn2_url") and not st.session_state.get("_ecn2_dismissed"):
    _ecn2_col1, _ecn2_col2 = st.columns([10, 1])
    with _ecn2_col1:
        st.info(f"URL modtaget fra ECN2: **{st.session_state['_ecn2_url']}**")
    with _ecn2_col2:
        if st.button("X", key="dismiss_ecn2"):
            st.session_state["_ecn2_dismissed"] = True
            st.rerun()

# ── Pipeline step definitions ──────────────────────────────────────
STEPS = [
    ("Dashboard",             "dashboard",    "dashboard_viewed",  "What to do next"),
    ("⚡ Run Pipeline",        "run_pipeline", "_run_pipeline_viewed", "One-click run all steps"),
    ("⚡ Quick Wins",          "quick_wins",   "_quick_wins_viewed", "One page at a time + new articles + technical — everything in one place"),
    ("🧹 Site Cleanup",        "site_cleanup", "_site_cleanup_viewed", "All site-wide fixes: merge, delete, redirect, noindex, create, clusters"),
    ("1. Setup & Connect",    "setup",        "gsc_data",          "Connect GSC + API keys"),
    ("2. Upload Ahrefs",      "ahrefs",       "page_authority",    "Upload backlink data"),
    ("3. CTR Analysis",       "ctr",          "ctr_gaps",          "Find underperformers"),
    ("4. Cannibalization",    "cannibal",     "cannibalization",   "Find keyword conflicts"),
    ("5. Topic Clusters",     "topics",       "topic_clusters",    "Group keywords into topics"),
    ("6. Page Auditor",       "auditor",      "audit_results",     "Check meta + content"),
    ("7. Internal Linking",   "linking",      "linking_fixes",     "Fix internal links"),
    ("8. Missing Keywords",   "keywords",     "keyword_fixes",     "Fill keyword gaps"),
    ("9. New Articles",       "articles",     "new_articles",      "Plan new content"),
    ("10. Cluster Health",    "health",       "clusters_checked",  "AI cluster evaluation"),
    ("11. Content Generator", "content",      "generated_content", "AI-generated content"),
    ("12. Site Map",          "sitemap",      "sitemap_viewed",    "Export & AI validate"),
    ("13. All Tasks",         "tasks",        "tasks_viewed",      "Unified priority list"),
    ("14. Implementation",    "action",       "action_plan",       "Step-by-step fix guide"),
]

# Figure out which step the user should be on
def _next_step_index():
    for i, (_, _, state_key, _) in enumerate(STEPS):
        if state_key not in st.session_state:
            return i
    return len(STEPS) - 1

next_idx = _next_step_index()

# Sidebar navigation
with st.sidebar:
    st.markdown("""
    <div style="padding: 0.5rem 0 0.8rem 0; border-bottom: 1px solid #1e1e2e; margin-bottom: 0.8rem;">
        <div style="font-family: 'Syne', sans-serif; font-size: 1rem; font-weight: 700; color: #e8e8f0;">
            SEO Pipeline
        </div>
        <div style="font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: #5533ff; letter-spacing: 0.1em; margin-top: 0.2rem;">
            FOLLOW THE STEPS IN ORDER
        </div>
    </div>
    """, unsafe_allow_html=True)

    page_labels = [s[0] for s in STEPS]
    # Persistent navigation — survives re-renders during long operations
    if "selected_page" not in st.session_state:
        st.session_state["selected_page"] = page_labels[next_idx]

    # Ensure stored page is valid
    if st.session_state["selected_page"] not in page_labels:
        st.session_state["selected_page"] = page_labels[next_idx]

    page = st.radio(
        "", page_labels,
        index=page_labels.index(st.session_state["selected_page"]),
        label_visibility="collapsed",
        key="nav_radio",
    )

    # Only update if user actually clicked a different page
    if page != st.session_state.get("_last_rendered_page"):
        st.session_state["selected_page"] = page
    st.session_state["_last_rendered_page"] = page

    st.markdown("---")

    # Pipeline progress
    done_count = sum(1 for _, _, key, _ in STEPS if key in st.session_state)
    st.markdown(f"""
    <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#5533ff; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.5rem;">
        PIPELINE {done_count}/{len(STEPS)}
    </div>
    """, unsafe_allow_html=True)

    for i, (label, _, state_key, hint) in enumerate(STEPS):
        done = state_key in st.session_state
        is_next = (i == next_idx) and not done
        if done:
            color = "#33dd88"
            marker = "OK"
        elif is_next:
            color = "#5533ff"
            marker = ">>"
        else:
            color = "#3a3a5c"
            marker = "  "
        st.markdown(
            f"<div style='font-size:0.72rem; color:{color}; padding:2px 0; font-family:\"IBM Plex Mono\",monospace;'>"
            f"{marker} {label}</div>",
            unsafe_allow_html=True,
        )

    # Next step hint
    if next_idx < len(STEPS):
        _, _, _, hint = STEPS[next_idx]
        st.markdown(f"""
        <div style="margin-top:1rem; padding:0.8rem; background:#12121f; border:1px solid #2a2a40; border-radius:6px;">
            <div style="font-family:'IBM Plex Mono',monospace; font-size:0.6rem; color:#5533ff; margin-bottom:0.3rem;">NEXT STEP</div>
            <div style="font-size:0.8rem; color:#c8b4ff;">{hint}</div>
        </div>
        """, unsafe_allow_html=True)

    # Volume storage info
    storage = get_storage_info()
    if storage.get("available") and storage.get("files"):
        st.markdown(f"""
        <div style="margin-top:1rem; padding:0.5rem; background:#0d0d15; border:1px solid #1e1e2e; border-radius:6px;">
            <div style="font-family:'IBM Plex Mono',monospace; font-size:0.55rem; color:#33dd88; letter-spacing:0.1em;">
                CACHED ON DISK · {storage['total_mb']:.1f} MB · {len(storage['files'])} datasets
            </div>
        </div>
        """, unsafe_allow_html=True)

# Route to pages
selected = page.split(". ", 1)[1] if ". " in page else page
if "Dashboard" in selected:
    from views import dashboard
    dashboard.render()
elif "Run Pipeline" in selected:
    from views import run_pipeline
    run_pipeline.render()
elif "Quick Wins" in selected:
    from views import quick_wins
    quick_wins.render()
elif "Site Cleanup" in selected:
    from views import site_cleanup
    site_cleanup.render()
elif "Setup" in selected:
    from views import setup
    setup.render()
elif "Ahrefs" in selected:
    from views import link_authority
    link_authority.render()
elif "CTR" in selected:
    from views import ctr_analysis
    ctr_analysis.render()
elif "Cannibalization" in selected:
    from views import cannibalization
    cannibalization.render()
elif "Topic" in selected:
    from views import topic_clusters
    topic_clusters.render()
elif "Auditor" in selected:
    from views import page_auditor
    page_auditor.render()
elif "Internal Linking" in selected:
    from views import internal_linking
    internal_linking.render()
elif "Missing Keywords" in selected:
    from views import missing_keywords
    missing_keywords.render()
elif "New Articles" in selected:
    from views import new_articles
    new_articles.render()
elif "Cluster Health" in selected:
    from views import cluster_health
    cluster_health.render()
elif "Content" in selected:
    from views import content_generator
    content_generator.render()
elif "Site Map" in selected:
    from views import site_map_export
    site_map_export.render()
elif "All Tasks" in selected:
    from views import unified_tasks
    unified_tasks.render()
elif "Implementation" in selected:
    from views import action_plan
    action_plan.render()

# Auto-save any AI results generated during this render
from utils.persistence import save_ai_cache
save_ai_cache()
