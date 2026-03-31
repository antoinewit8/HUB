# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, date
from core.config  import APP_NAME, VERSION
from core.session import init_session

# ── Configuration ─────────────────────────────────────────────
st.set_page_config(
    page_title = APP_NAME,
    page_icon  = "🚛",
    layout     = "wide",
    initial_sidebar_state = "expanded",
)
init_session()

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/truck.png", width=60)
    st.title(APP_NAME)
    st.caption(f"Version {VERSION}")
    st.divider()

    # 🔧 Paramètres interactifs
    st.markdown("### ⚙️ Paramètres")
    nb_camions = st.number_input("Camions actifs", min_value=0, value=0, step=1)
    cout_carburant = st.number_input("Coût carburant (€)", min_value=0.0, value=0.0, step=50.0, format="%.2f")
    km_parcourus = st.number_input("Km parcourus", min_value=0, value=0, step=100)
    nb_alertes = st.number_input("Alertes en cours", min_value=0, value=0, step=1)

    st.divider()

    # 📝 Notes rapides
    st.markdown("### 📝 Notes du jour")
    if "notes" not in st.session_state:
        st.session_state.notes = []

    nouvelle_note = st.text_input("Ajouter une note")
    if st.button("➕ Ajouter") and nouvelle_note:
        st.session_state.notes.append({
            "heure": datetime.now().strftime("%H:%M"),
            "note": nouvelle_note
        })
        st.rerun()

    st.divider()
    st.caption("© 2025 — Transport Hub")

# ── Page d'accueil ────────────────────────────────────────────
st.title("🏠 Tableau de bord général")
st.markdown(f"Bienvenue sur ton **{APP_NAME}** — Sélectionne un outil dans le menu à gauche.")
st.divider()

# ── Cartes modules (cliquables vers les pages) ───────────────
col1, col2, col3 = st.columns(3)

with col1:
    st.info("### 🚛 TX-FLEX\nAnalyse de flotte et performance")
    if st.button("Ouvrir TX-FLEX", use_container_width=True):
        st.switch_page("pages/1_🚛_Analyse_TX_FLEX.py")

with col2:
    st.warning("### 🗺️ Calcul KM\nDistances et itinéraires")
    if st.button("Ouvrir Calcul KM", use_container_width=True):
        st.switch_page("pages/2_🗺️_Calcul_KM.py")

with col3:
    st.error("### 🗺️ Carte Manuelle\nVisualisation trajets")
    if st.button("Ouvrir Carte", use_container_width=True):
        st.switch_page("pages/3_🗺️_Carte_Manuelle.py")

st.divider()

# ── KPIs dynamiques ───────────────────────────────────────────
st.markdown("### 📊 KPIs du jour")

k1, k2, k3, k4 = st.columns(4)
k1.metric("🚛 Camions actifs",   nb_camions)
k2.metric("⚠️ Alertes en cours", nb_alertes,     delta=f"{nb_alertes}" if nb_alertes > 3 else None, delta_color="inverse")
k3.metric("🛣️ Km parcourus",     f"{km_parcourus:,}".replace(",", " "))
k4.metric("⛽ Coût carburant",    f"{cout_carburant:,.2f} €".replace(",", " "))

# ── Jauge simple (ratio coût/km) ─────────────────────────────
if km_parcourus > 0:
    ratio = cout_carburant / km_parcourus
    st.divider()
    st.markdown("### 💡 Indicateur coût/km")
    col_g1, col_g2 = st.columns([1, 3])
    col_g1.metric("€/km", f"{ratio:.3f}")
    with col_g2:
        if ratio < 0.3:
            st.success(f"✅ Excellent — {ratio:.3f} €/km")
        elif ratio < 0.5:
            st.warning(f"⚠️ Attention — {ratio:.3f} €/km")
        else:
            st.error(f"🔴 Trop élevé — {ratio:.3f} €/km")

# ── Notes du jour ─────────────────────────────────────────────
if st.session_state.notes:
    st.divider()
    st.markdown("### 📝 Notes du jour")
    for i, n in enumerate(st.session_state.notes):
        col_n, col_x = st.columns([10, 1])
        col_n.markdown(f"**{n['heure']}** — {n['note']}")
        if col_x.button("❌", key=f"del_{i}"):
            st.session_state.notes.pop(i)
            st.rerun()
