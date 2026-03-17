"""
Setup & Connect page
Handles GSC service account auth and site selection.
Credentials can come from Railway env vars or manual UI input.
"""

import os
import streamlit as st
import json
from config import get_anthropic_key, has_anthropic_key


def _auto_connect_gsc():
    """Try to auto-connect GSC using env var credentials."""
    if "gsc_data" in st.session_state:
        return  # already connected
    creds = st.session_state.get("gsc_credentials")
    site_url = st.session_state.get("gsc_site_url", os.environ.get("GSC_SITE_URL", ""))
    if not creds or not site_url:
        return
    if "gsc_service" in st.session_state:
        return
    try:
        from utils.gsc_client import build_gsc_service, list_properties
        service = build_gsc_service(creds)
        properties = list_properties(service)
        st.session_state["gsc_service"] = service
        st.session_state["gsc_properties"] = properties
        # Auto-fetch if site URL matches a property
        if site_url in properties:
            from utils.gsc_client import fetch_gsc_data
            df = fetch_gsc_data(service, site_url)
            st.session_state["gsc_data"] = df
            st.session_state["gsc_site"] = site_url
            st.session_state["demo_mode"] = False
    except Exception:
        pass  # silently fail, user can connect manually


def render():
    _auto_connect_gsc()

    st.markdown("## Setup & Connect")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:2rem;'>Configure Google Search Console connection and API keys</p>",
        unsafe_allow_html=True
    )

    # Show env var status banner
    env_vars = {
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "GSC_CREDENTIALS_JSON": bool(os.environ.get("GSC_CREDENTIALS_JSON")),
        "GSC_SITE_URL": bool(os.environ.get("GSC_SITE_URL")),
        "SITE_CONTEXT": bool(os.environ.get("SITE_CONTEXT")),
        "CONTENT_LANGUAGE": bool(os.environ.get("CONTENT_LANGUAGE")),
    }
    any_env = any(env_vars.values())
    if any_env:
        found = [k for k, v in env_vars.items() if v]
        st.success(f"Environment variables loaded: {', '.join(found)}")

    col1, col2 = st.columns([3, 2], gap="large")

    with col1:
        # ── GSC Connection ─────────────────────────────────────────
        st.markdown("### Google Search Console")

        connect_method = st.radio(
            "Connection method",
            ["Service Account JSON", "Demo mode (no GSC required)"],
            horizontal=True
        )

        if "Demo" in connect_method:
            st.info("Demo mode: Uses synthetic GSC data to demonstrate the system")
            if st.button("Activate Demo mode", type="primary"):
                from utils.gsc_client import generate_demo_data
                demo_df = generate_demo_data()
                st.session_state["gsc_data"] = demo_df
                st.session_state["gsc_site"] = "https://demo-store.example.com/ (DEMO)"
                st.session_state["demo_mode"] = True
                st.success(f"Demo data loaded: {len(demo_df)} rows")
                st.rerun()

        else:
            # Check if credentials came from env var
            has_env_creds = bool(os.environ.get("GSC_CREDENTIALS_JSON"))

            if has_env_creds and "gsc_credentials" in st.session_state:
                st.success("GSC credentials loaded from environment variable (GSC_CREDENTIALS_JSON)")
            else:
                st.markdown("""
                <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1rem; margin-bottom:1rem; font-size:0.8rem; color:#9b9bb8; font-family:'IBM Plex Mono',monospace;">
                1. Google Cloud Console &rarr; IAM &rarr; Service Accounts<br>
                2. Create key (JSON format)<br>
                3. Add the service account email in GSC under "Settings &rarr; Users and permissions"<br>
                4. Upload the JSON file below OR set the GSC_CREDENTIALS_JSON env var in Railway
                </div>
                """, unsafe_allow_html=True)

                uploaded = st.file_uploader(
                    "Upload Service Account JSON",
                    type=["json"],
                    help="Your Google service account credentials file"
                )

                if uploaded:
                    try:
                        creds = json.load(uploaded)
                        st.session_state["gsc_credentials"] = creds
                        from utils.gsc_client import build_gsc_service, list_properties
                        service = build_gsc_service(creds)
                        properties = list_properties(service)
                        st.session_state["gsc_service"] = service
                        st.session_state["gsc_properties"] = properties
                        st.success(f"Connected! Found {len(properties)} GSC properties")
                    except Exception as e:
                        st.error(f"Error: {e}")

            # Site selector
            if "gsc_properties" in st.session_state:
                # Pre-select env var site if available
                properties = st.session_state["gsc_properties"]
                env_site = st.session_state.get("gsc_site_url", "")
                default_idx = 0
                if env_site in properties:
                    default_idx = properties.index(env_site)

                site = st.selectbox(
                    "Select GSC property",
                    properties,
                    index=default_idx
                )

                col_a, col_b = st.columns(2)
                with col_a:
                    days = st.number_input("Days back", min_value=7, max_value=180, value=90)
                with col_b:
                    min_imp = st.number_input("Min. impressions", min_value=5, max_value=500, value=10)

                if st.button("Fetch GSC Data", type="primary"):
                    with st.spinner("Fetching data from Google Search Console..."):
                        try:
                            from utils.gsc_client import fetch_gsc_data
                            df = fetch_gsc_data(
                                st.session_state["gsc_service"],
                                site,
                                days=days,
                                min_impressions=min_imp
                            )
                            st.session_state["gsc_data"] = df
                            st.session_state["gsc_site"] = site
                            st.session_state["demo_mode"] = False

                            # Auto-save GSC data to volume
                            from utils.persistence import save_key
                            save_key("gsc_data")
                            save_key("gsc_site")

                            st.success(f"{len(df):,} query/page combinations fetched")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error fetching data: {e}")

        st.markdown("---")

        # ── Anthropic API Key ──────────────────────────────────────
        st.markdown("### Claude AI (Anthropic)")

        if os.environ.get("ANTHROPIC_API_KEY"):
            st.success("API key loaded from environment variable (ANTHROPIC_API_KEY)")
        else:
            api_key = st.text_input(
                "Anthropic API Key",
                type="password",
                value=st.session_state.get("anthropic_key", ""),
                help="Used for meta generation and content suggestions. Set ANTHROPIC_API_KEY env var in Railway."
            )
            if api_key:
                st.session_state["anthropic_key"] = api_key
                st.success("API key saved")

        st.markdown("---")

        # ── Site Context ───────────────────────────────────────────
        st.markdown("### Site Context (for AI)")

        default_context = (
            "An online store selling consumer electronics and accessories. "
            "We carry headphones, laptops, smartwatches, keyboards and more. "
            "Tone: helpful, knowledgeable, friendly. USPs: Free shipping, easy returns, expert reviews."
        )

        site_context = st.text_area(
            "Describe the webshop",
            value=st.session_state.get("site_context", default_context),
            height=100,
            help="The AI uses this to tailor meta texts and content. Can be set via SITE_CONTEXT env var."
        )

        lang_options = ["English", "Swedish", "Danish", "Norwegian", "German", "French", "Spanish"]
        current_lang = st.session_state.get("content_language", "English")
        lang_idx = lang_options.index(current_lang) if current_lang in lang_options else 0

        language = st.selectbox(
            "Primary language for generated content",
            lang_options,
            index=lang_idx
        )

        if st.button("Save settings"):
            st.session_state["site_context"] = site_context
            st.session_state["content_language"] = language

            from utils.persistence import save_key
            save_key("site_context")
            save_key("content_language")

            st.success("Settings saved")

    with col2:
        # ── Status panel ───────────────────────────────────────────
        st.markdown("### System Status")

        def status_row(label, ok, detail=""):
            color = "#33dd88" if ok else "#ff4455"
            icon = "+" if ok else "X"
            st.markdown(
                f"<div style='display:flex; justify-content:space-between; padding:0.5rem 0; border-bottom:1px solid #1e1e2e;'>"
                f"<span style='font-size:0.85rem; color:#d0d0e8;'>{icon} {label}</span>"
                f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.75rem; color:{color};'>{detail}</span>"
                f"</div>",
                unsafe_allow_html=True
            )

        gsc_connected = "gsc_data" in st.session_state
        ai_ready = has_anthropic_key()

        status_row("GSC Connected", gsc_connected,
                   st.session_state.get("gsc_site", "Not connected")[-30:] if gsc_connected else "Missing")
        status_row("Claude AI", ai_ready, "Ready" if ai_ready else "Missing key")
        status_row("Site context", "site_context" in st.session_state,
                   "Configured" if "site_context" in st.session_state else "Default")

        # Env var overview
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Railway Environment Variables")
        env_list = [
            ("ANTHROPIC_API_KEY", bool(os.environ.get("ANTHROPIC_API_KEY"))),
            ("GSC_CREDENTIALS_JSON", bool(os.environ.get("GSC_CREDENTIALS_JSON"))),
            ("GSC_SITE_URL", bool(os.environ.get("GSC_SITE_URL"))),
            ("SITE_CONTEXT", bool(os.environ.get("SITE_CONTEXT"))),
            ("CONTENT_LANGUAGE", bool(os.environ.get("CONTENT_LANGUAGE"))),
        ]
        for name, is_set in env_list:
            status_row(name, is_set, "Set" if is_set else "Not set")

        if gsc_connected:
            df = st.session_state["gsc_data"]
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### GSC Data Summary")

            m1, m2 = st.columns(2)
            with m1:
                st.metric("Queries", f"{len(df):,}")
                st.metric("Pages", f"{df['page'].nunique():,}")
            with m2:
                st.metric("Impressions", f"{df['impressions'].sum():,.0f}")
                st.metric("Total clicks", f"{df['clicks'].sum():,.0f}")

            avg_ctr = df["ctr"].mean() * 100
            avg_pos = df["position"].mean()

            st.markdown(f"""
            <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1rem; margin-top:1rem;">
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#6b6b8a; margin-bottom:0.5rem;">KEY METRICS</div>
                <div style="display:flex; gap:1rem;">
                    <div>
                        <div style="font-size:1.4rem; font-family:'Syne',sans-serif; font-weight:700; color:#c8b4ff;">{avg_ctr:.1f}%</div>
                        <div style="font-size:0.7rem; color:#6b6b8a;">Avg. CTR</div>
                    </div>
                    <div>
                        <div style="font-size:1.4rem; font-family:'Syne',sans-serif; font-weight:700; color:#c8b4ff;">{avg_pos:.1f}</div>
                        <div style="font-size:0.7rem; color:#6b6b8a;">Avg. position</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""
        <div style="background:#0d0d15; border:1px solid #1a1a2e; border-radius:8px; padding:1rem;">
            <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#5533ff; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.5rem;">WORKFLOW</div>
            <div style="font-size:0.8rem; color:#9b9bb8; line-height:1.8;">
                1. Connect GSC<br>
                2. CTR Analysis &rarr; find gaps<br>
                3. Page Auditor &rarr; check meta<br>
                4. Content Generator &rarr; AI text<br>
                5. Action Plan &rarr; prioritized list
            </div>
        </div>
        """, unsafe_allow_html=True)
