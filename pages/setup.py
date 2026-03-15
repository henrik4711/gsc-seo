"""
Setup & Connect page
Handles GSC service account auth and site selection
"""

import streamlit as st
import json


def render():
    st.markdown("## 🔌 Setup & Connect")
    st.markdown(
        "<p style='color:#6b6b8a; margin-bottom:2rem;'>Konfigurer Google Search Console forbindelse og API-nøgler</p>",
        unsafe_allow_html=True
    )
    
    col1, col2 = st.columns([3, 2], gap="large")
    
    with col1:
        # ── GSC Connection ─────────────────────────────────────────
        st.markdown("### Google Search Console")
        
        connect_method = st.radio(
            "Forbindelsesmetode",
            ["🔑 Service Account JSON", "🧪 Demo-tilstand (ingen GSC krævet)"],
            horizontal=True
        )
        
        if "Demo" in connect_method:
            st.info("Demo-tilstand: Bruger syntetisk GSC-data til at demonstrere systemet")
            if st.button("✅ Aktivér Demo-tilstand", type="primary"):
                from utils.gsc_client import generate_demo_data
                demo_df = generate_demo_data()
                st.session_state["gsc_data"] = demo_df
                st.session_state["gsc_site"] = "https://mshop.se/ (DEMO)"
                st.session_state["demo_mode"] = True
                st.success(f"✅ Demo-data indlæst: {len(demo_df)} rækker")
                st.rerun()
        
        else:
            st.markdown("""
            <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1rem; margin-bottom:1rem; font-size:0.8rem; color:#6b6b8a; font-family:'IBM Plex Mono',monospace;">
            1. Google Cloud Console → IAM → Service Accounts<br>
            2. Opret nøgle (JSON format)<br>
            3. Tilføj service account email til GSC under "Indstillinger → Brugere og tilladelser"<br>
            4. Upload JSON-filen herunder
            </div>
            """, unsafe_allow_html=True)
            
            uploaded = st.file_uploader(
                "Upload Service Account JSON",
                type=["json"],
                help="Din Google service account credentials fil"
            )
            
            if uploaded:
                try:
                    creds = json.load(uploaded)
                    st.session_state["gsc_credentials"] = creds
                    
                    # Try to connect
                    from utils.gsc_client import build_gsc_service, list_properties
                    service = build_gsc_service(creds)
                    properties = list_properties(service)
                    st.session_state["gsc_service"] = service
                    st.session_state["gsc_properties"] = properties
                    st.success(f"✅ Forbundet! Fandt {len(properties)} GSC properties")
                except Exception as e:
                    st.error(f"❌ Fejl: {e}")
            
            # Site selector
            if "gsc_properties" in st.session_state:
                site = st.selectbox(
                    "Vælg GSC property",
                    st.session_state["gsc_properties"]
                )
                
                col_a, col_b = st.columns(2)
                with col_a:
                    days = st.number_input("Dage tilbage", min_value=7, max_value=180, value=90)
                with col_b:
                    min_imp = st.number_input("Min. impressions", min_value=5, max_value=500, value=10)
                
                if st.button("📥 Hent GSC Data", type="primary"):
                    with st.spinner("Henter data fra Google Search Console..."):
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
                            st.success(f"✅ {len(df):,} query/page kombinationer hentet")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Fejl ved datahentning: {e}")
        
        st.markdown("---")
        
        # ── Anthropic API Key ──────────────────────────────────────
        st.markdown("### Claude AI (Anthropic)")
        
        api_key = st.text_input(
            "Anthropic API Key",
            type="password",
            value=st.session_state.get("anthropic_key", ""),
            help="Bruges til meta-generering og content-forslag"
        )
        
        if api_key:
            st.session_state["anthropic_key"] = api_key
            st.success("✅ API-nøgle gemt")
        
        st.markdown("---")
        
        # ── Site Context ───────────────────────────────────────────
        st.markdown("### Site-kontekst (til AI)")
        
        site_context = st.text_area(
            "Beskriv webshoppen",
            value=st.session_state.get("site_context",
                "Mshop er en svensk/dansk webshop for voksenprodukter med 40+ års historie. "
                "Vi sælger vibratorer, dildoer, lingeri, glidmidler og SM-produkter. "
                "Tone: diskret, professionel, imødekommende. USPs: Fri frakt, hurtig levering, diskret forsendelse."
            ),
            height=100,
            help="AI'en bruger dette til at skræddersy meta-tekster og content"
        )
        
        language = st.selectbox(
            "Primært sprog for genereret indhold",
            ["Swedish", "Danish", "Norwegian", "English"],
            index=0
        )
        
        if st.button("💾 Gem indstillinger"):
            st.session_state["site_context"] = site_context
            st.session_state["content_language"] = language
            st.success("✅ Indstillinger gemt")
    
    with col2:
        # ── Status panel ───────────────────────────────────────────
        st.markdown("### System Status")
        
        def status_row(label, ok, detail=""):
            color = "#33dd88" if ok else "#ff4455"
            icon = "✅" if ok else "❌"
            st.markdown(
                f"<div style='display:flex; justify-content:space-between; padding:0.5rem 0; border-bottom:1px solid #1e1e2e;'>"
                f"<span style='font-size:0.85rem;'>{icon} {label}</span>"
                f"<span style='font-family:\"IBM Plex Mono\",monospace; font-size:0.75rem; color:{color};'>{detail}</span>"
                f"</div>",
                unsafe_allow_html=True
            )
        
        gsc_connected = "gsc_data" in st.session_state
        ai_ready = "anthropic_key" in st.session_state
        
        status_row("GSC Forbundet", gsc_connected,
                   st.session_state.get("gsc_site", "Ikke forbundet")[-30:] if gsc_connected else "Mangler")
        status_row("Claude AI", ai_ready, "API-nøgle sat" if ai_ready else "Mangler nøgle")
        status_row("Site-kontekst", "site_context" in st.session_state, 
                   "Konfigureret" if "site_context" in st.session_state else "Standard")
        
        if gsc_connected:
            df = st.session_state["gsc_data"]
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### GSC Data Summary")
            
            m1, m2 = st.columns(2)
            with m1:
                st.metric("Queries", f"{len(df):,}")
                st.metric("Sider", f"{df['page'].nunique():,}")
            with m2:
                st.metric("Impressions", f"{df['impressions'].sum():,.0f}")
                st.metric("Total klik", f"{df['clicks'].sum():,.0f}")
            
            avg_ctr = df["ctr"].mean() * 100
            avg_pos = df["position"].mean()
            
            st.markdown(f"""
            <div style="background:#12121f; border:1px solid #1e1e2e; border-radius:8px; padding:1rem; margin-top:1rem;">
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#6b6b8a; margin-bottom:0.5rem;">NØGLETAL</div>
                <div style="display:flex; gap:1rem;">
                    <div>
                        <div style="font-size:1.4rem; font-family:'Syne',sans-serif; font-weight:700; color:#c8b4ff;">{avg_ctr:.1f}%</div>
                        <div style="font-size:0.7rem; color:#6b6b8a;">Gns. CTR</div>
                    </div>
                    <div>
                        <div style="font-size:1.4rem; font-family:'Syne',sans-serif; font-weight:700; color:#c8b4ff;">{avg_pos:.1f}</div>
                        <div style="font-size:0.7rem; color:#6b6b8a;">Gns. position</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""
        <div style="background:#0d0d15; border:1px solid #1a1a2e; border-radius:8px; padding:1rem;">
            <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#5533ff; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.5rem;">WORKFLOW</div>
            <div style="font-size:0.8rem; color:#6b6b8a; line-height:1.8;">
                1. Forbind GSC ✓<br>
                2. CTR Analysis → find gaps<br>
                3. Page Auditor → check meta<br>
                4. Content Generator → AI-tekst<br>
                5. Action Plan → prioriteret liste
            </div>
        </div>
        """, unsafe_allow_html=True)
