# app.py
# Point d'entrée principal — Page d'accueil du Hub Transport

import streamlit as st
from core.config  import APP_NAME, VERSION
from core.session import init_session

# ── Configuration de la page ─────────────────────────────────
st.set_page_config(
    page_title = APP_NAME,
    page_icon  = "🚛",
    layout     = "wide",
    initial_sidebar_state = "expanded",
)

# ── Initialisation session ────────────────────────────────────
init_session()

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/truck.png", width=60)
    st.title(APP_NAME)
    st.caption(f"Version {VERSION}")
    st.divider()
    st.markdown("### 🗺️ Navigation")
    st.markdown("""
    Utilise le menu ci-dessus  
    pour accéder à tes outils.
    """)
    st.divider()
    st.caption("© 2025 — Transport Hub")

# ── Page d'accueil ────────────────────────────────────────────
st.title("🏠 Tableau de bord général")
st.markdown(f"Bienvenue sur ton **{APP_NAME}** — Sélectionne un outil dans le menu à gauche.")
st.divider()

# ── Cartes des modules disponibles ───────────────────────────
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.info("### 🚛 TX-FLEX\nAnalyse de flotte\net performance")

with col2:
    st.warning("### ⛽ Carburant\nSuivi consommation\net anomalies")

with col3:
    st.error("### 💶 Facturation\nContrôle péages\net badges")

with col4:
    st.success("### 🔧 Entretien\nAlertes révisions\net maintenance")

st.divider()

# ── Zone KPIs futurs ──────────────────────────────────────────
st.markdown("### 📊 KPIs du jour")
st.caption("🔜 Cette zone affichera tes chiffres clés une fois les modules connectés.")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Camions actifs",    "—", help="Données à connecter")
k2.metric("Alertes en cours",  "—", help="Données à connecter")
k3.metric("Km parcourus",      "—", help="Données à connecter")
k4.metric("Coût carburant",    "—", help="Données à connecter")
