import streamlit as st

st.set_page_config(
    page_title="SEO Intelligence · Mshop",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS - clean dark professional theme
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Syne:wght@400;600;700;800&family=Inter:wght@300;400;500&display=swap');

/* Base */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Hide default streamlit elements */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* Background */
.stApp {
    background: #0a0a0f;
    color: #e8e8f0;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #0f0f1a;
    border-right: 1px solid #1e1e2e;
}

section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    font-family: 'Syne', sans-serif;
}

/* Page title */
h1, h2, h3 {
    font-family: 'Syne', sans-serif !important;
    font-weight: 700;
}

/* Metrics */
[data-testid="metric-container"] {
    background: #12121f;
    border: 1px solid #1e1e2e;
    border-radius: 8px;
    padding: 16px;
}

[data-testid="metric-container"] label {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.7rem !important;
    color: #6b6b8a !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
}

[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-family: 'Syne', sans-serif !important;
    font-size: 1.8rem !important;
    font-weight: 700;
    color: #c8b4ff !important;
}

/* Dataframes */
.stDataFrame {
    border: 1px solid #1e1e2e;
    border-radius: 8px;
}

/* Buttons */
.stButton > button {
    background: #5533ff;
    color: white;
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
    transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(85, 51, 255, 0.4);
}

/* Selectbox, inputs */
.stSelectbox > div > div,
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stTextArea > div > div > textarea {
    background: #12121f !important;
    border: 1px solid #1e1e2e !important;
    border-radius: 6px !important;
    color: #e8e8f0 !important;
    font-family: 'Inter', sans-serif;
}

/* Labels and text readability */
.stSelectbox label, .stTextInput label, .stNumberInput label,
.stTextArea label, .stRadio label, .stFileUploader label,
.stCheckbox label {
    color: #c8c8e0 !important;
    font-size: 0.85rem !important;
}

/* Radio button text */
.stRadio > div > label > div > p {
    color: #c8c8e0 !important;
}

/* General paragraph text */
.stMarkdown p {
    color: #d0d0e8;
}

/* Info/success/warning boxes text */
.stAlert p {
    color: #e8e8f0 !important;
}

/* Expander */
.streamlit-expanderHeader {
    background: #12121f !important;
    border: 1px solid #1e1e2e !important;
    border-radius: 6px !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.8rem;
}

/* Info/warning/success boxes */
.stAlert {
    border-radius: 6px;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    background: #0f0f1a;
    border-bottom: 1px solid #1e1e2e;
    gap: 4px;
}

.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #6b6b8a;
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

/* Status badge helper classes */
.badge-critical { color: #ff4455; font-weight: 600; }
.badge-warn { color: #ffaa33; font-weight: 600; }
.badge-ok { color: #33dd88; font-weight: 600; }
.badge-mono { font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; }

/* Progress */
.stProgress > div > div {
    background: #5533ff !important;
}

/* Spinner */
.stSpinner > div {
    border-top-color: #5533ff !important;
}
</style>
""", unsafe_allow_html=True)

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
