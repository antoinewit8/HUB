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

# CSS pour supprimer les marges et forcer la hauteur
st.markdown("""
    <style>
        .block-container { padding-top: 1rem; padding-bottom: 0rem; }
        iframe { border-radius: 10px; border: 1px solid #333; }
    </style>
""", unsafe_allow_html=True)

st.title("🗺️ Carte de trajet manuelle")

# ─── Warm Up ──────────────────────────────────────────────────────────────────
def warm_up_server() -> bool:
    for attempt in range(1, 7):
        try:
            r = requests.get(f"{MAP_SERVER_URL}/health", timeout=10)
            if r.status_code == 200:
                return True
        except:
            pass
        time.sleep(10)
    return False

if "server_ready" not in st.session_state:
    with st.spinner("🔌 Démarrage du serveur carte..."):
        st.session_state["server_ready"] = warm_up_server()

if "calc" not in st.session_state:
    st.session_state["calc"] = None

# ─── Carte vide par défaut (France centrée) ───────────────────────────────────
DEFAULT_MAP_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8"/>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        html, body, #map { height: 100%; margin: 0; padding: 0; }
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        var map = L.map('map').setView([46.603354, 1.888334], 6);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap',
            maxZoom: 18
        }).addTo(map);
    </script>
</body>
</html>
"""

# ─── LAYOUT PRINCIPAL ─────────────────────────────────────────────────────────
col_form, col_map = st.columns([1, 3])

# ─── COLONNE GAUCHE : Formulaire ──────────────────────────────────────────────
with col_form:
    with st.container(border=True):
        st.subheader("📋 Paramètres")
        with st.form("form_carte"):
            origine     = st.text_input("📍 Départ",  placeholder="Ex : Dunkerque, France")
            destination = st.text_input("🏁 Arrivée", placeholder="Ex : Lyon, France")
            avoid_tolls    = st.checkbox("🚫 Éviter les péages")
            avoid_highways = st.checkbox("🚫 Éviter les autoroutes")
            submitted = st.form_submit_button("🗺️ Calculer", use_container_width=True)

    # ─── Résultats sous le formulaire ─────────────────────────────────────────
    if st.session_state["calc"]:
        c = st.session_state["calc"]
        with st.container(border=True):
            st.subheader("📊 Résultats")
            st.metric("📏 Distance", f"{c['distance_km']} km")
            st.metric("⏱️ Durée",    f"{c['duration_h']} h")
            st.metric("💶 Péages",   f"{c.get('prix_peage', 0.0)} €")

# ─── COLONNE DROITE : Carte ───────────────────────────────────────────────────
with col_map:

    # ── Traitement du formulaire ───────────────────────────────────────────────
    if submitted:
        if not origine.strip() or not destination.strip():
            st.error("❌ Renseignez le départ et l'arrivée.")
        else:
            with st.spinner("⏳ Calcul de l'itinéraire..."):
                try:
                    resp = requests.post(
                        f"{MAP_SERVER_URL}/api/recalculate",
                        json={
                            "origin":          origine.strip(),
                            "dest":            destination.strip(),
                            "avoid_tolls":     avoid_tolls,
                            "avoid_highways":  avoid_highways
                        },
                        timeout=60
                    )
                    if resp.status_code == 200:
                        st.session_state["calc"] = resp.json()
                        st.rerun()
                    else:
                        st.error(f"❌ Erreur serveur ({resp.status_code})")
                except Exception as e:
                    st.error(f"❌ Connexion impossible : {e}")

    # ── Affichage carte ────────────────────────────────────────────────────────
    if st.session_state["calc"]:
        calc = st.session_state["calc"]
        try:
            map_html_path = Path(__file__).parent.parent / "map.html"
            with open(map_html_path, "r", encoding="utf-8") as f:
                html_template = f.read()

            html_final = (
                html_template
                .replace("{{ route.origin }}",       origine)
                .replace("{{ route.dest }}",         destination)
                .replace("{{ route.polyline }}",     calc.get("polyline", ""))
                .replace("{{ route.distance_km }}", str(calc.get("distance_km", "")))
                .replace("{{ route.duration_h }}",  str(calc.get("duration_h", "")))
            )
            components.html(html_final, height=700, scrolling=False)

        except Exception as e:
            st.error(f"❌ Erreur chargement map.html : {e}")
            components.html(DEFAULT_MAP_HTML, height=700, scrolling=False)
    else:
        # Carte vide France par défaut
        components.html(DEFAULT_MAP_HTML, height=700, scrolling=False)
