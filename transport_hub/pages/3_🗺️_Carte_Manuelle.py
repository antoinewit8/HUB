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
            if r.status_code == 200: return True
        except: pass
        time.sleep(10)
    return False

if "server_ready" not in st.session_state:
    with st.spinner("🔌 Démarrage du serveur..."):
        st.session_state["server_ready"] = warm_up_server()

# ─── INIT STATE ───────────────────────────────────────────────────────────────
if "calc" not in st.session_state:
    st.session_state["calc"] = None

# ─── LAYOUT ───────────────────────────────────────────────────────────────────
col_form, col_map = st.columns([1, 2])

with col_form:
    st.subheader("📋 Paramètres")
    with st.form("form_carte"):
        origine     = st.text_input("📍 Départ", placeholder="Ex : Dunkerque, France")
        destination = st.text_input("🏁 Arrivée", placeholder="Ex : Lyon, France")
        avoid_tolls    = st.checkbox("🚫 Éviter les péages")
        avoid_highways = st.checkbox("🚫 Éviter les autoroutes")
        submitted = st.form_submit_button("🗺️ Calculer", use_container_width=True)

    if st.session_state["calc"]:
        c = st.session_state["calc"]
        st.markdown("---")
        st.metric("📏 Distance", f"{c['distance_km']} km")
        st.metric("⏱️ Durée", f"{c['duration_h']} h")
        st.metric("💶 Péages", f"{c.get('prix_peage', 0.0)} €")

# ─── TRAITEMENT & CARTE ─────────────────
with col_map:
    st.subheader("🗺️ Carte interactive")
    
    if submitted:
        if not origine.strip() or not destination.strip():
            st.error("❌ Renseignez le départ et l'arrivée.")
        else:
            with st.spinner("⏳ Calcul en cours..."):
                try:
                    resp = requests.post(f"{MAP_SERVER_URL}/api/recalculate", json={
                        "origin": origine.strip(), "dest": destination.strip(),
                        "avoid_tolls": avoid_tolls, "avoid_highways": avoid_highways
                    }, timeout=60)
                    if resp.status_code == 200:
                        st.session_state["calc"] = resp.json()
                        st.rerun()
                    else:
                        st.error("Erreur de calcul sur le serveur.")
                except Exception as e:
                    st.error(f"Erreur connexion : {e}")

    # AFFICHAGE DE LA CARTE (Injection directe du HTML)
    if st.session_state["calc"]:
        calc = st.session_state["calc"]
        try:
            # On lit ton fichier map.html local
            with open("map.html", "r", encoding="utf-8") as f:
                html_template = f.read()
            
            # On injecte les données dans le HTML
            # Attention : ces clés {{ route.xxx }} doivent être présentes dans ton map.html
            html_final = html_template.replace("{{ route.origin }}", origine)\
                                      .replace("{{ route.dest }}", destination)\
                                      .replace("{{ route.polyline }}", calc.get("polyline", ""))\
                                      .replace("{{ route.distance_km }}", str(calc.get("distance_km", "")))\
                                      .replace("{{ route.duration_h }}", str(calc.get("duration_h", "")))
            
            # On affiche le code HTML directement sans passer par l'URL Render
            components.html(html_final, height=700, scrolling=False)
        except Exception as e:
            st.error(f"Erreur chargement map.html : {e}")
    else:
        st.info("Calculez un trajet pour voir la carte.")
