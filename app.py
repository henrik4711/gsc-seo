import streamlit as st
from config import init_from_env

st.set_page_config(
    page_title="SEO Intelligence · Mshop",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
header {visibility: hidden;}

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

# Header
st.markdown("""
<div style="padding: 2rem 0 1rem 0; border-bottom: 1px solid #1e1e2e; margin-bottom: 2rem;">
    <div style="font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; color: #5533ff; letter-spacing: 0.2em; text-transform: uppercase; margin-bottom: 0.4rem;">
        ⚡ SEO INTELLIGENCE PLATFORM
    </div>
    <h1 style="margin: 0; font-size: 2rem; background: linear-gradient(135deg, #e8e8f0 0%, #c8b4ff 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
        CTR Gap Optimizer
    </h1>
    <p style="color: #6b6b8a; margin: 0.5rem 0 0 0; font-size: 0.9rem;">
        Find pages where click-through rate underperforms their organic position · Generate AI-powered fixes
    </p>
</div>
""", unsafe_allow_html=True)

# Sidebar navigation
with st.sidebar:
    st.markdown("""
    <div style="padding: 1rem 0; border-bottom: 1px solid #1e1e2e; margin-bottom: 1rem;">
        <div style="font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; color: #5533ff; letter-spacing: 0.15em; text-transform: uppercase;">
            NAVIGATION
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    page = st.radio(
        "",
        ["🔌  Setup & Connect", "📊  CTR Analysis", "🔬  Page Auditor", "✍️  Content Generator", "📋  Action Plan"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.markdown("""
    <div style="font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; color: #3a3a5c; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.5rem;">
        PIPELINE STATUS
    </div>
    """, unsafe_allow_html=True)
    
    # Show session state pipeline status
    steps = {
        "GSC Connected": "gsc_data" in st.session_state,
        "CTR Analysis Done": "ctr_gaps" in st.session_state,
        "Pages Audited": "audit_results" in st.session_state,
        "Content Generated": "generated_content" in st.session_state,
    }
    for step, done in steps.items():
        icon = "✅" if done else "⭕"
        st.markdown(f"<div style='font-size:0.75rem; color: {'#33dd88' if done else '#3a3a5c'}; padding: 2px 0;'>{icon} {step}</div>", unsafe_allow_html=True)

# Route to pages
if "Setup" in page:
    from views import setup
    setup.render()
elif "CTR Analysis" in page:
    from views import ctr_analysis
    ctr_analysis.render()
elif "Page Auditor" in page:
    from views import page_auditor
    page_auditor.render()
elif "Content Generator" in page:
    from views import content_generator
    content_generator.render()
elif "Action Plan" in page:
    from views import action_plan
    action_plan.render()
