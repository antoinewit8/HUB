import streamlit as st
import streamlit.components.v1 as components
import requests
import time
import os
from dotenv import load_dotenv
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

MAP_SERVER_URL = os.environ.get("MAP_SERVER_URL", "https://cartes-bot.onrender.com")

st.set_page_config(page_title="Carte Manuelle", page_icon="🗺️", layout="wide")
st.title("🗺️ Carte de trajet manuelle")
st.caption("Calcule et visualise un itinéraire PTV interactif")

# ─── Warm Up ──────────────────────────────────────────────────────────────────
def warm_up_server() -> bool:
    for attempt in range(1, 7):
        try:
            r = requests.get(f"{MAP_SERVER_URL}/health", timeout=10)
            if r.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(10)
    return False

if "server_ready" not in st.session_state:
    with st.spinner("🔌 Démarrage du serveur... (30-60 sec si inactif)"):
        st.session_state["server_ready"] = warm_up_server()

if not st.session_state["server_ready"]:
    st.error("❌ Serveur de cartes inaccessible.")
    st.info(f"💡 Vérifie : `{MAP_SERVER_URL}`")
    st.stop()

# ─── INIT STATE ───────────────────────────────────────────────────────────────
if "map_url" not in st.session_state:
    st.session_state["map_url"] = f"{MAP_SERVER_URL}/carte/default"
    st.session_state["calc"] = None

# ─── LAYOUT ───────────────────────────────────────────────────────────────────
col_form, col_map = st.columns([1, 2])

# ───────────────── FORMULAIRE ─────────────────
with col_form:
    st.subheader("📋 Paramètres")

    with st.form("form_carte"):
        origine     = st.text_input("📍 Départ", placeholder="Ex : Dunkerque, France")
        destination = st.text_input("🏁 Arrivée", placeholder="Ex : Lyon, France")

        avoid_tolls    = st.checkbox("🚫 Éviter les péages")
        avoid_highways = st.checkbox("🚫 Éviter les autoroutes")

        submitted = st.form_submit_button("🗺️ Calculer", use_container_width=True)

    # ─── AFFICHAGE DES RÉSULTATS ───
    if st.session_state["calc"]:
        calc = st.session_state["calc"]

        st.markdown("---")
        st.success("✅ Itinéraire calculé")

        st.metric("📏 Distance", f"{calc['distance_km']} km")
        st.metric("⏱️ Durée",    f"{calc['duration_h']} h")
        st.metric("💶 Péages",   f"{calc.get('prix_peage', 0.0)} €")

        st.caption(f"🔗 [Ouvrir en plein écran]({st.session_state['map_url']})")

    # Reset serveur
    if st.button("🔄 Reset serveur"):
        st.session_state["server_ready"] = False
        st.rerun()


# ───────────────── CARTE ─────────────────
with col_map:
    st.subheader("🗺️ Carte interactive")
    components.iframe(src=st.session_state["map_url"], height=650)


# ───────────────── TRAITEMENT ─────────────────
if submitted:

    if not origine.strip() or not destination.strip():
        st.error("❌ Merci de renseigner le départ et l'arrivée.")
        st.stop()

    # ─── 1. CALCUL ITINÉRAIRE ───
    with st.spinner("⏳ Calcul itinéraire..."):
        try:
            resp_calc = requests.post(
                f"{MAP_SERVER_URL}/api/recalculate",
                json={
                    "origin": origine.strip(),
                    "dest": destination.strip(),
                    "avoid_tolls": avoid_tolls,
                    "avoid_highways": avoid_highways,
                },
                timeout=60
            )

            if resp_calc.status_code != 200:
                st.error(f"❌ Erreur calcul : {resp_calc.text}")
                st.stop()

            calc = resp_calc.json()

        except requests.exceptions.Timeout:
            st.warning("⏳ Timeout serveur → retry...")
            st.session_state["server_ready"] = False
            st.rerun()

        except requests.exceptions.ConnectionError:
            st.error("❌ Connexion serveur impossible")
            st.stop()

    # ─── 2. CRÉATION CARTE ───
    with st.spinner("🗺️ Génération carte..."):
        try:
            resp_map = requests.post(
                f"{MAP_SERVER_URL}/api/create_route",
                json={
                    "origin": origine.strip(),
                    "dest": destination.strip(),
                    "distance_km": calc["distance_km"],
                    "duration_h": calc["duration_h"],
                    "polyline": calc["polyline"],
                    "prix_peage": calc.get("prix_peage", 0.0),
                    "pref_waypoints": calc.get("pref_waypoints", []),
                },
                timeout=30
            )

            if resp_map.status_code != 200:
                st.error("❌ Erreur création carte")
                st.stop()

            map_data = resp_map.json()
            route_id = map_data["id"]

            # ✅ UPDATE STATE (clé du fonctionnement)
            st.session_state["map_url"] = f"{MAP_SERVER_URL}/carte?id={route_id}"
            st.session_state["calc"] = calc

            st.rerun()

        except Exception as e:
            st.error(f"❌ Erreur : {e}")
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
