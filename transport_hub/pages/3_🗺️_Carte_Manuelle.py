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
    st.stop()

# ─── INIT STATE ───────────────────────────────────────────────────────────────
if "map_url" not in st.session_state:
    st.session_state["map_url"] = f"{MAP_SERVER_URL}/carte/default"
    st.session_state["calc"] = None

# ─── LAYOUT ───────────────────────────────────────────────────────────────────
col_form, col_map = st.columns([1, 2])

# ───────────────── FORMULAIRE (Gauche) ─────────────────
with col_form:
    st.subheader("📋 Paramètres")

    with st.form("form_carte"):
        origine     = st.text_input("📍 Départ", placeholder="Ex : Dunkerque, France")
        destination = st.text_input("🏁 Arrivée", placeholder="Ex : Lyon, France")
        avoid_tolls    = st.checkbox("🚫 Éviter les péages")
        avoid_highways = st.checkbox("🚫 Éviter les autoroutes")
        submitted = st.form_submit_button("🗺️ Calculer", use_container_width=True)

    if st.session_state["calc"]:
        calc = st.session_state["calc"]
        st.markdown("---")
        st.success("✅ Itinéraire calculé")
        st.metric("📏 Distance", f"{calc['distance_km']} km")
        st.metric("⏱️ Durée",    f"{calc['duration_h']} h")
        st.metric("💶 Péages",   f"{calc.get('prix_peage', 0.0)} €")
        st.caption(f"🔗 [Ouvrir en plein écran]({st.session_state['map_url']})")

    if st.button("🔄 Reset serveur"):
        st.session_state["server_ready"] = False
        st.rerun()

# ───────────────── TRAITEMENT (Logique) ─────────────────
if submitted:
    if not origine.strip() or not destination.strip():
        st.error("❌ Merci de renseigner le départ et l'arrivée.")
    else:
        with st.spinner("⏳ Calcul itinéraire..."):
            try:
                # 1. Calcul
                resp_calc = requests.post(
                    f"{MAP_SERVER_URL}/api/recalculate",
                    json={
                        "origin": origine.strip(),
                        "dest": destination.strip(),
                        "avoid_tolls": avoid_tolls,
                        "avoid_highways": avoid_highways,
                    }, timeout=60
                )
                if resp_calc.status_code == 200:
                    calc = resp_calc.json()
                    
                    # 2. Création de la route sur le serveur
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
                        }, timeout=30
                    )
                    
                    if resp_map.status_code == 200:
                        route_id = resp_map.json()["id"]
                        # ON DÉFINIT L'URL DE LA CARTE VISUELLE
                        st.session_state["map_url"] = f"{MAP_SERVER_URL}/carte?id={route_id}"
                        st.session_state["calc"] = calc
                        st.rerun()
                else:
                    st.error(f"Erreur serveur : {resp_calc.text}")
            except Exception as e:
                st.error(f"Erreur : {e}")

# ───────────────── CARTE (Droite) ─────────────────
# ───────────────── CARTE (Droite) ─────────────────
with col_map:
    st.subheader("🗺️ Carte interactive")
    
    if st.session_state["calc"]:
        calc = st.session_state["calc"]
        try:
            # 1. On lit ton fichier map.html qui est sur ton ordinateur
            with open("map.html", "r", encoding="utf-8") as f:
                html_template = f.read()
            
            # 2. On injecte les données du calcul directement dans le code HTML
            # On remplace les balises {{ ... }} par les vraies valeurs du calcul
            html_final = html_template.replace("{{ route.origin }}", origine if origine else "Départ")\
                                      .replace("{{ route.dest }}", destination if destination else "Arrivée")\
                                      .replace("{{ route.polyline }}", calc.get("polyline", "")) # Très important pour dessiner la route
            
            # 3. On affiche le HTML directement (SANS passer par l'URL Render)
            components.html(html_final, height=700, scrolling=False)
            
        except FileNotFoundError:
            st.error("❌ Le fichier 'map.html' est introuvable. Place-le dans le même dossier que ce script.")
    else:
        st.info("💡 Saisissez un itinéraire et cliquez sur Calculer pour afficher la carte.")
# ── DEBUG (Bas) ─────────────────────────────────────────────────────────────
if st.session_state["calc"]:
    with st.expander("🔧 Détails techniques"):
        st.json({
            "map_url": st.session_state["map_url"],
            "calc_data": st.session_state["calc"]
        })
