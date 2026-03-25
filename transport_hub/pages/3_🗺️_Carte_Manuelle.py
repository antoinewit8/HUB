import streamlit as st
import streamlit.components.v1 as components
import requests
import time
import os
from dotenv import load_dotenv
from pathlib import Path
from jinja2 import Template

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

MAP_SERVER_URL = os.environ.get("MAP_SERVER_URL", "https://hub-m36x.onrender.com")

st.set_page_config(page_title="Carte Manuelle", page_icon="🗺️", layout="wide")

# ─── CSS AGRESSIF ─────────────────────────────────────────────────────────────
st.markdown("""
    <style>
        .block-container { 
            padding: 0 !important; 
            margin: 0 !important;
            max-width: 100% !important;
        }
        header { display: none !important; }
        #MainMenu { display: none !important; }
        footer { display: none !important; }
        section[data-testid="stMain"] > div:first-child {
            padding: 0 !important;
        }
        div[data-testid="stVerticalBlock"] {
            gap: 0rem !important;
        }
        iframe {
            display: block !important;
            border: none !important;
        }
        iframe[title="components.html"] {
            height: 100vh !important;
            min-height: 100vh !important;
            width: 100% !important;
        }
    </style>
""", unsafe_allow_html=True)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def format_location(loc: str) -> str:
    loc = loc.strip()
    if "," in loc:
        return loc
    return f"{loc}, Belgium"

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

# ─── CARTE ────────────────────────────────────────────────────────────────────
if st.session_state["calc"]:
    calc     = st.session_state["calc"]
    _origine = st.session_state.get("origine", "")
    _dest    = st.session_state.get("dest",    "")

    try:
        map_html_path = Path(__file__).parent.parent / "map.html"
        with open(map_html_path, "r", encoding="utf-8") as f:
            html_template = f.read()

        template   = Template(html_template)
        html_final = template.render(
            route={
                "origin":            _origine,
                "dest":              _dest,
                "polyline":          calc.get("polyline", []),
                "polyline_current":  calc.get("polyline", []),
                "polyline_original": calc.get("polyline", []),
                "distance_km":       calc.get("distance_km", ""),
                "duration_h":        calc.get("duration_h", ""),
                "prix_peage":        calc.get("prix_peage", 0.0),
            },
            route_id   = calc.get("route_id", "manual"),
            server_url = MAP_SERVER_URL
        )

        components.html(html_final, height=1800, scrolling=False)

    except Exception as e:
        st.error(f"❌ Erreur chargement map.html : {e}")

else:
    # ─── Formulaire ───────────────────────────────────────────────────────────
    st.markdown("<div style='height:30vh'></div>", unsafe_allow_html=True)

    with st.form("form_carte", clear_on_submit=False):
        st.markdown("### 🗺️ Calculer un itinéraire")
        c1, c2 = st.columns(2)
        with c1:
            origine = st.text_input("📍 Départ", placeholder="Ex : Liège, Belgium")
        with c2:
            destination = st.text_input("🏁 Arrivée", placeholder="Ex : Nieuport, Belgium")

        c3, c4, c5 = st.columns([1, 1, 2])
        with c3:
            avoid_tolls = st.checkbox("🚫 Éviter péages")
        with c4:
            avoid_highways = st.checkbox("🚫 Éviter autoroutes")
        with c5:
            submitted = st.form_submit_button("🗺️ Calculer l'itinéraire", use_container_width=True)

    if submitted:
        if not origine.strip() or not destination.strip():
            st.error("❌ Renseignez le départ et l'arrivée.")
        else:
            with st.spinner("⏳ Calcul en cours..."):
                try:
                    payload = {
                        "origin":         format_location(origine),
                        "dest":           format_location(destination),
                        "avoid_tolls":    avoid_tolls,
                        "avoid_highways": avoid_highways
                    }
                    resp = requests.post(
                        f"{MAP_SERVER_URL}/api/recalculate",
                        json=payload,
                        timeout=60
                    )

                    if resp.status_code == 200:
                        st.session_state["calc"]    = resp.json()
                        st.session_state["origine"] = format_location(origine)
                        st.session_state["dest"]    = format_location(destination)
                        st.rerun()
                    else:
                        st.error(f"❌ Erreur serveur ({resp.status_code}) : {resp.text[:200]}")
                except Exception as e:
                    st.error(f"❌ Connexion impossible : {e}")
