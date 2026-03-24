# pages/3_🗺️_Carte_Manuelle.py

import streamlit as st
import streamlit.components.v1 as components
import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

MAP_SERVER_URL = os.environ.get("MAP_SERVER_URL", "http://localhost:8000")

st.set_page_config(page_title="Carte Manuelle", page_icon="🗺️", layout="wide")
st.title("🗺️ Carte de trajet manuelle")
st.caption("Calcule et visualise un itinéraire PTV interactif")

# ─────────────────────────────────────────────
# WARM UP (Render free tier)
# ─────────────────────────────────────────────
def warm_up_server() -> bool:
    """Réveille le serveur Render si endormi."""
    for attempt in range(1, 7):
        try:
            r = requests.get(f"{MAP_SERVER_URL}/health", timeout=10)
            if r.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(10)
    return False

# ── Warm up au chargement de la page (1 seule fois par session) ──
if "server_ready" not in st.session_state:
    with st.spinner("🔌 Connexion au serveur de cartes (Render)..."):
        ok = warm_up_server()
        st.session_state["server_ready"] = ok

if not st.session_state["server_ready"]:
    st.error("❌ Serveur de cartes inaccessible.")
    st.info(f"💡 Vérifie que le service Render est bien déployé : `{MAP_SERVER_URL}`")
    st.stop()

# ─────────────────────────────────────────────
# FORMULAIRE
# ─────────────────────────────────────────────
with st.form("form_carte"):
    col1, col2 = st.columns(2)
    with col1:
        origine = st.text_input("📍 Départ", placeholder="Ex : Dunkerque, France")
    with col2:
        destination = st.text_input("🏁 Arrivée", placeholder="Ex : Lyon, France")

    col3, col4 = st.columns(2)
    with col3:
        avoid_tolls    = st.checkbox("🚫 Éviter les péages",     value=False)
    with col4:
        avoid_highways = st.checkbox("🚫 Éviter les autoroutes", value=False)

    submitted = st.form_submit_button("🗺️ Calculer et afficher", use_container_width=True)

# ─────────────────────────────────────────────
# TRAITEMENT
# ─────────────────────────────────────────────
if submitted:
    if not origine.strip() or not destination.strip():
        st.error("❌ Merci de renseigner le départ et l'arrivée.")
        st.stop()

    # ── Étape 1 : recalculate ─────────────────────────────────
    with st.spinner("⏳ Calcul de l'itinéraire via PTV..."):
        try:
            resp_calc = requests.post(
                f"{MAP_SERVER_URL}/api/recalculate",
                json={
                    "origin":         origine.strip(),
                    "dest":           destination.strip(),
                    "avoid_tolls":    avoid_tolls,
                    "avoid_highways": avoid_highways,
                },
                timeout=60   # 60s car Render peut être lent
            )

            if resp_calc.status_code != 200:
                st.error(f"❌ Erreur calcul ({resp_calc.status_code}) : {resp_calc.text}")
                st.stop()

            calc = resp_calc.json()

        except requests.exceptions.Timeout:
            # Render s'est rendormi entre le warm_up et le calcul
            st.warning("⏳ Serveur lent, nouvelle tentative...")
            st.session_state["server_ready"] = False
            st.rerun()

        except requests.exceptions.ConnectionError:
            st.error(f"❌ Connexion perdue : `{MAP_SERVER_URL}`")
            st.stop()

    # ── Étape 2 : create_route ────────────────────────────────
    with st.spinner("🗺️ Génération de la carte..."):
        try:
            resp_map = requests.post(
                f"{MAP_SERVER_URL}/api/create_route",
                json={
                    "origin":         origine.strip(),
                    "dest":           destination.strip(),
                    "distance_km":    calc["distance_km"],
                    "duration_h":     calc["duration_h"],
                    "polyline":       calc["polyline"],
                    "prix_peage":     calc.get("prix_peage", 0.0),
                    "pref_waypoints": calc.get("pref_waypoints", []),
                },
                timeout=30
            )

            if resp_map.status_code != 200:
                st.error(f"❌ Erreur création carte ({resp_map.status_code})")
                st.stop()

            map_data = resp_map.json()
            route_id = map_data["id"]
            map_url  = f"{MAP_SERVER_URL}/carte?id={route_id}"

        except Exception as e:
            st.error(f"❌ Erreur génération carte : {e}")
            st.stop()

    # ── Métriques ─────────────────────────────────────────────
    st.success("✅ Itinéraire calculé !")

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("📏 Distance", f"{calc['distance_km']} km")
    col_b.metric("⏱️ Durée",    f"{calc['duration_h']} h")
    col_c.metric("💶 Péages",   f"{calc.get('prix_peage', 0.0)} €")

    # ── Carte iframe ──────────────────────────────────────────
    st.markdown("---")
    st.subheader("🗺️ Carte interactive")

    col_link, col_reset = st.columns([4, 1])
    with col_link:
        st.caption(f"🔗 [Ouvrir en plein écran]({map_url})")
    with col_reset:
        if st.button("🔄 Réinitialiser le serveur"):
            st.session_state["server_ready"] = False
            st.rerun()

    components.iframe(src=map_url, height=650, scrolling=False)

    # ── Debug ─────────────────────────────────────────────────
    with st.expander("🔧 Détails techniques"):
        st.json({
            "route_id":       route_id,
            "map_url":        map_url,
            "origin":         origine,
            "destination":    destination,
            "avoid_tolls":    avoid_tolls,
            "avoid_highways": avoid_highways,
        })
