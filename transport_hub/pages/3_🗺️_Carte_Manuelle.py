import streamlit as st
import streamlit.components.v1 as components
import requests
import time
import os
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

MAP_SERVER_URL = os.environ.get("MAP_SERVER_URL", "https://cartes-bot.onrender.com")

st.set_page_config(page_title="Carte Manuelle", page_icon="🗺️", layout="wide")

# Supprime TOUS les paddings Streamlit autour de la carte
st.markdown("""
    <style>
        .block-container { padding: 0 !important; margin: 0 !important; }
        header { display: none !important; }
        #MainMenu { display: none !important; }
        footer { display: none !important; }
    </style>
""", unsafe_allow_html=True)

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

# ─── Formulaire COMPACT en haut ───────────────────────────────────────────────
with st.form("form_carte", clear_on_submit=False):
    c1, c2, c3, c4, c5 = st.columns([3, 3, 1, 1, 1])
    with c1:
        origine = st.text_input("📍 Départ", placeholder="Ex : Dunkerque, France", label_visibility="collapsed")
    with c2:
        destination = st.text_input("🏁 Arrivée", placeholder="Ex : Lyon, France", label_visibility="collapsed")
    with c3:
        avoid_tolls = st.checkbox("🚫 Péages")
    with c4:
        avoid_highways = st.checkbox("🚫 Autoroutes")
    with c5:
        submitted = st.form_submit_button("🗺️ Calculer", use_container_width=True)

# ─── Traitement ───────────────────────────────────────────────────────────────
if submitted:
    if not origine.strip() or not destination.strip():
        st.error("❌ Renseignez le départ et l'arrivée.")
    else:
        with st.spinner("⏳ Calcul en cours..."):
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

# ─── Affichage carte PLEIN ÉCRAN ──────────────────────────────────────────────
if st.session_state["calc"]:
    calc = st.session_state["calc"]
    try:
        map_html_path = Path(__file__).parent.parent / "map.html"
        with open(map_html_path, "r", encoding="utf-8") as f:
            html_template = f.read()

        html_final = (
            html_template
            .replace("{{ route.origin }}",      origine)
            .replace("{{ route.dest }}",        destination)
            .replace("{{ route.polyline }}",    str(calc.get("polyline", "[]")))
            .replace("{{ route.distance_km }}", str(calc.get("distance_km", "")))
            .replace("{{ route.duration_h }}",  str(calc.get("duration_h", "")))
            .replace("{{ route.prix_peage }}",  str(calc.get("prix_peage", "0.0")))
        )

        # Hauteur = viewport complet moins la barre formulaire (~80px)
        components.html(html_final, height=820, scrolling=False)

    except Exception as e:
        st.error(f"❌ Erreur chargement map.html : {e}")
else:
    st.info("👆 Renseignez un départ et une arrivée puis cliquez sur Calculer.")
