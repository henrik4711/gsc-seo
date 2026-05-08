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
    """Try to auto-connect GSC using env var credentials.

    Builds the service, lists properties, and pre-selects the env site URL
    so the Fetch GSC Data button becomes available. Errors are captured into
    session state so the UI can show them — never swallow silently.
    """
    creds = st.session_state.get("gsc_credentials")
    site_url = st.session_state.get("gsc_site_url", os.environ.get("GSC_SITE_URL", ""))
    if not creds:
        return
    if "gsc_service" in st.session_state:
        return
    try:
        from utils.gsc_client import build_gsc_service, list_properties
        service = build_gsc_service(creds)
        properties = list_properties(service)
        st.session_state["gsc_service"] = service
        st.session_state["gsc_properties"] = properties
        st.session_state.pop("gsc_auto_connect_error", None)
        if site_url and site_url in properties and "gsc_site" not in st.session_state:
            st.session_state["gsc_site"] = site_url
            st.session_state["demo_mode"] = False
            try:
                from utils.persistence import save_key
                save_key("gsc_site")
            except Exception:
                pass
    except Exception as e:
        st.session_state["gsc_auto_connect_error"] = str(e)


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
                try:
                    from utils.persistence import save_key
                    save_key("gsc_data")
                    save_key("gsc_site")
                except Exception:
                    pass
                st.success(f"Demo data loaded: {len(demo_df)} rows")
                st.rerun()

        else:
            # Check if credentials came from env var
            has_env_creds = bool(os.environ.get("GSC_CREDENTIALS_JSON"))

            if has_env_creds and "gsc_credentials" in st.session_state:
                st.success("GSC credentials loaded from environment variable (GSC_CREDENTIALS_JSON)")

                auto_err = st.session_state.get("gsc_auto_connect_error")
                if auto_err:
                    st.error(
                        "Could not connect to Google Search Console with the env credentials.\n\n"
                        f"**Error:** {auto_err}\n\n"
                        "Common causes:\n"
                        "- The service account email is not added in GSC under "
                        "**Settings → Users and permissions** for this property\n"
                        "- `GSC_CREDENTIALS_JSON` is malformed (must be the full service-account JSON, not a path)\n"
                        "- Temporary network/SSL issue — try again"
                    )

                if "gsc_properties" not in st.session_state:
                    if st.button("Connect to GSC now", type="primary", key="gsc_manual_connect"):
                        st.session_state.pop("gsc_service", None)
                        st.session_state.pop("gsc_auto_connect_error", None)
                        with st.spinner("Connecting to Google Search Console..."):
                            try:
                                from utils.gsc_client import build_gsc_service, list_properties
                                service = build_gsc_service(st.session_state["gsc_credentials"])
                                properties = list_properties(service)
                                st.session_state["gsc_service"] = service
                                st.session_state["gsc_properties"] = properties
                                env_site = st.session_state.get(
                                    "gsc_site_url", os.environ.get("GSC_SITE_URL", "")
                                )
                                if env_site and env_site in properties and "gsc_site" not in st.session_state:
                                    st.session_state["gsc_site"] = env_site
                                    st.session_state["demo_mode"] = False
                                st.success(f"Connected — found {len(properties)} GSC properties")
                                st.rerun()
                            except Exception as e:
                                st.session_state["gsc_auto_connect_error"] = str(e)
                                st.error(f"Connection failed: {e}")
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

        # Site patterns configuration
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Site URL Patterns")
        st.caption("Configure URL patterns used for page type classification. Defaults work for most English-language sites. Add your language-specific terms as comma-separated lists.")

        from utils.site_patterns import PRESETS
        current_patterns = st.session_state.get("site_patterns") or {}

        preset_choice = st.selectbox(
            "Load preset",
            ["(custom / keep current)"] + list(PRESETS.keys()),
            key="sp_preset",
        )
        if preset_choice != "(custom / keep current)":
            if st.button(f"Apply preset: {preset_choice}", key="sp_apply_preset"):
                st.session_state["site_patterns"] = dict(PRESETS[preset_choice])
                from utils.persistence import save
                save("site_patterns") if "site_patterns" in st.session_state else None
                st.success(f"Preset '{preset_choice}' applied. Re-run bulk audit or Re-classify to apply.")
                st.rerun()

        with st.expander("Edit patterns manually", expanded=False):
            def _list_input(label, key, help_text=""):
                current = current_patterns.get(key, [])
                text = st.text_area(
                    label,
                    value=", ".join(current) if isinstance(current, list) else "",
                    help=help_text,
                    key=f"sp_{key}",
                    height=68,
                )
                return [x.strip() for x in text.split(",") if x.strip()]

            new_patterns = {}
            new_patterns["category_patterns_extra"] = _list_input(
                "Extra category path patterns",
                "category_patterns_extra",
                "E.g. /shop-now/, /store/, /sortiment/",
            )
            new_patterns["info_patterns_extra"] = _list_input(
                "Extra info/corporate page patterns",
                "info_patterns_extra",
                "Static pages in your language. E.g. /hjalp, /kontakt, /villkor (Swedish).",
            )
            new_patterns["flat_category_keywords"] = _list_input(
                "Flat URL category keywords",
                "flat_category_keywords",
                "For sites using flat URLs without /category/ prefix. E.g. sexleksaker, elektronik, mode.",
            )
            new_patterns["local_patterns"] = _list_input(
                "Local/store location patterns",
                "local_patterns",
                "City or store paths to treat as location pages. E.g. /stockholm, /copenhagen, /butik.",
            )
            new_patterns["faceted_params_extra"] = _list_input(
                "Extra faceted URL query parameters",
                "faceted_params_extra",
                "Query params to flag as facets (defaults already include SID, dir, limit, mode, order, p, sort, view).",
            )

            if st.button("Save site patterns", key="sp_save"):
                # Only keep non-empty lists
                cleaned = {k: v for k, v in new_patterns.items() if v}
                st.session_state["site_patterns"] = cleaned
                from utils.persistence import save
                save("site_patterns")
                st.success("Site patterns saved. Re-run bulk audit or Re-classify to apply.")
                st.rerun()

        # Storage debug info
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Disk Storage")
        from utils.persistence import get_storage_info
        storage = get_storage_info()
        if storage.get("available"):
            for key, info in storage.get("files", {}).items():
                if key == "ai_cache":
                    status_row(f"AI Cache ({info.get('count', 0)} files)", True, f"{info.get('size_mb', 0)} MB")
                else:
                    status_row(key, True, f"{info.get('size_mb', 0)} MB")
            st.markdown(f"<div style='font-size:0.72rem; color:#6b6b8a;'>Total: {storage.get('total_mb', 0)} MB</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='color:#ff4455;'>Volume /data NOT available</div>", unsafe_allow_html=True)

        # Scraper status — requests + BeautifulSoup, no Playwright
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Scraper Status")
        try:
            import requests as _req  # noqa
            from bs4 import BeautifulSoup as _bs  # noqa
            status_row("Scraper (requests + BeautifulSoup)", True, "Ready — no JS rendering needed for Magento")
        except Exception as e:
            status_row("Scraper", False, f"Missing dependency: {str(e)[:80]}")

        # ── RESET ALL DATA ─────────────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Reset All Data")
        st.markdown("<p style='color:#ff4455; font-size:0.8rem;'>Clears ALL cached data and forces fresh start. Bundled Ahrefs + SF data will auto-reload.</p>", unsafe_allow_html=True)
        if st.button("RESET ALL DATA", type="secondary", key="btn_reset_all"):
            import shutil
            from utils.persistence import DATA_DIR, AI_CACHE_DIR, PERSIST_KEYS
            # Clear session state (keep only credentials + settings)
            keep_keys = {"gsc_credentials", "gsc_service", "gsc_properties", "gsc_site_url",
                         "gsc_site", "anthropic_key", "site_context", "content_language",
                         "demo_mode", "_persistence_loaded"}
            for key in list(st.session_state.keys()):
                if key not in keep_keys:
                    del st.session_state[key]
            # Clear disk (keep settings, delete everything else)
            if os.path.isdir(DATA_DIR):
                for f in os.listdir(DATA_DIR):
                    path = os.path.join(DATA_DIR, f)
                    if f in ("site_context.txt", "content_language.txt", "gsc_site.txt"):
                        continue  # Keep settings
                    try:
                        if os.path.isdir(path):
                            shutil.rmtree(path)
                        else:
                            os.remove(path)
                    except Exception:
                        pass
            # Force bundled data to re-unpack on next load
            st.session_state.pop("_persistence_loaded", None)
            st.success("All data cleared. Refresh the page to restart.")
            st.rerun()

        if gsc_connected:
            df = st.session_state["gsc_data"]

            # Check if data was loaded from cache
            from utils.persistence import _volume_available, _file_path
            cached_path = _file_path("gsc_data", "dataframe") if _volume_available() else ""
            if cached_path and os.path.exists(cached_path):
                import datetime
                mod_time = os.path.getmtime(cached_path)
                cache_date = datetime.datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M")
                st.markdown(
                    f"<div style='font-size:0.72rem; color:#6b6b8a; font-family:\"IBM Plex Mono\",monospace; margin:0.5rem 0;'>"
                    f"GSC data cached: {cache_date}</div>",
                    unsafe_allow_html=True,
                )

            if st.button("Refresh GSC Data", key="btn_refresh_gsc"):
                service = st.session_state.get("gsc_service")
                site = st.session_state.get("gsc_site", "")
                if service and site:
                    with st.spinner("Fetching fresh GSC data..."):
                        try:
                            from utils.gsc_client import fetch_gsc_data
                            fresh_df = fetch_gsc_data(service, site)
                            st.session_state["gsc_data"] = fresh_df
                            from utils.persistence import save_key
                            save_key("gsc_data")
                            st.success(f"Refreshed: {len(fresh_df):,} rows")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                elif st.session_state.get("gsc_credentials") and site:
                    with st.spinner("Reconnecting + fetching..."):
                        try:
                            from utils.gsc_client import build_gsc_service, fetch_gsc_data
                            service = build_gsc_service(st.session_state["gsc_credentials"])
                            st.session_state["gsc_service"] = service
                            fresh_df = fetch_gsc_data(service, site)
                            st.session_state["gsc_data"] = fresh_df
                            from utils.persistence import save_key
                            save_key("gsc_data")
                            st.success(f"Refreshed: {len(fresh_df):,} rows")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                else:
                    st.warning("No GSC service available. Re-enter credentials above.")

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
