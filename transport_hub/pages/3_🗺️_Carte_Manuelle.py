"""
Carte Manuelle — la page n'affiche plus que la carte.

Le départ, l'arrivée, les étapes et les options se définissent directement dans
map.html. Aucun widget Streamlit : pas de rerun, donc pas d'état perdu ni de
marqueur fantôme.
"""

import os
import time
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from jinja2 import Template

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
MAP_SERVER_URL = os.environ.get("MAP_SERVER_URL", "https://hub-m36x.onrender.com").rstrip("/")

st.set_page_config(page_title="Carte Manuelle", page_icon="🗺️", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; }
      header, #MainMenu, footer { display: none !important; }
      section[data-testid="stMain"] > div:first-child { padding: 0 !important; }
      div[data-testid="stVerticalBlock"] { gap: 0 !important; }
      iframe[title="streamlit.components.v1.html"],
      iframe[title="components.html"] {
          display: block !important; border: none !important;
          width: 100% !important; height: calc(100vh - 8px) !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=600, show_spinner=False)
def warm_up_server(url: str) -> bool:
    """Render s'endort sur le plan gratuit : on le réveille une fois par session."""
    for _ in range(3):
        try:
            if requests.get(f"{url}/health", timeout=12).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(4)
    return False


with st.spinner("Réveil du serveur carte…"):
    server_ready = warm_up_server(MAP_SERVER_URL)

try:
    map_html_path = Path(__file__).parent.parent / "map.html"
    template = Template(map_html_path.read_text(encoding="utf-8"))

    # Carte vide : map.html gère lui-même départ, arrivée, étapes et options.
    html_final = template.render(
        route={"origin": "", "dest": "", "polyline": []},
        route_id="manual",
        server_url=MAP_SERVER_URL,
    )
    components.html(html_final, height=1000, scrolling=False)

except FileNotFoundError:
    st.error("map.html introuvable à la racine du projet.")
except Exception as e:
    st.error(f"Erreur chargement map.html : {e}")

if not server_ready:
    st.warning(
        f"Le serveur carte ({MAP_SERVER_URL}) n'a pas répondu au réveil. "
        "Le premier calcul peut échouer, relancez-le une fois.",
        icon="⚠️",
    )
