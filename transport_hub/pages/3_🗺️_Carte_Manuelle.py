"""
Carte Manuelle — la carte s'ouvre dans un nouvel onglet, en plein écran.

La page du HUB ne sert plus qu'à lancer la carte : un bouton ouvre map.html
seul dans un nouvel onglet, sans rien de Streamlit autour (même système que
l'Optimisateur Lavages CIT). Le départ, l'arrivée, les étapes et les options
se définissent toujours directement dans map.html.
"""

import json
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

PAGE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {
  --ap-bg: #f5f5f7; --ap-text: #1d1d1f; --ap-sub: #6e6e73; --ap-soft: #e8e8ed; --ap-blue: #0071e3;
  --ap-font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", "Helvetica Neue", Arial, sans-serif;
}
.stApp, [data-testid="stAppViewContainer"] { background: var(--ap-bg) !important; }
[data-testid="stMain"] *:not([data-testid="stIconMaterial"]):not([class*="material-symbols"]),
section.main *:not([data-testid="stIconMaterial"]):not([class*="material-symbols"]) { font-family: var(--ap-font); }
[data-testid="stHeader"] { background: transparent !important; }
.block-container, [data-testid="stMainBlockContainer"] { max-width: 1100px !important; padding-top: 2.5rem !important; }
[data-testid="stMain"] p, [data-testid="stMain"] label, section.main p { color: var(--ap-text); }
[data-testid="stMain"] [data-testid="stCaptionContainer"] p { color: var(--ap-sub); }

.ap-hero h1 { font-size: 48px; font-weight: 700; letter-spacing: -0.03em; line-height: 1.05; color: var(--ap-text);
  margin: 0 0 .5rem; padding: 0; }
.ap-hero p { font-size: 21px; line-height: 1.38; color: var(--ap-sub); margin: 0 0 1.75rem; max-width: 46ch; }
.ap-section { font-size: 24px; font-weight: 600; letter-spacing: -0.015em; color: var(--ap-text);
  border-top: 1px solid #e5e5ea; padding-top: 1.4rem; margin: 2.2rem 0 1rem; }
.ap-list { margin: 0 !important; padding: 0 !important; list-style: none; max-width: 62ch; }
.ap-list li { margin: 0 !important; }
.ap-list li { font-size: 15px; line-height: 1.5; color: var(--ap-text); padding: 9px 0; border-bottom: .5px solid #e5e5ea; }
.ap-list li b { font-weight: 600; }
.ap-list li span { color: var(--ap-sub); }
.ap-statut { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: var(--ap-sub); margin-top: 6px; }
.ap-statut i { width: 8px; height: 8px; border-radius: 50%; background: #34c759; }
.ap-statut.off i { background: #ff9f0a; }

[data-testid="stMain"] .stDownloadButton > button {
  border-radius: 980px; border: none; background: var(--ap-soft); min-height: 42px; padding: 0 20px; }
[data-testid="stMain"] .stDownloadButton > button p { color: var(--ap-blue) !important; font-weight: 500; }
[data-testid="stMain"] .stDownloadButton > button:hover { background: #dedee3; }
[data-testid="stMain"] iframe { border: none; }
</style>
"""
st.markdown(PAGE_CSS, unsafe_allow_html=True)


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


def bouton_ouvrir(page_html: str):
    """Bouton qui ouvre la carte seule dans un nouvel onglet (page autonome, sans Streamlit autour)."""
    contenu = json.dumps(page_html).replace("</", "<\\/")
    components.html(f"""
<style>
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", "Helvetica Neue", Arial, sans-serif; }}
  button {{ height: 48px; padding: 0 28px; border: none; border-radius: 980px; background: #0071e3; color: #fff;
           font: 500 17px -apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", "Helvetica Neue", Arial, sans-serif;
           cursor: pointer; transition: background .15s, transform .1s; }}
  button:hover {{ background: #0077ed; }}
  button:active {{ transform: scale(.98); }}
  p {{ margin: 10px 0 0 4px; font-size: 13px; color: #6e6e73; }}
</style>
<button id="ouvrir">Ouvrir la carte plein écran</button>
<p id="msg">S’ouvre dans un nouvel onglet.</p>
<script>
const PAGE = {contenu};
document.getElementById('ouvrir').addEventListener('click', () => {{
  const url = URL.createObjectURL(new Blob([PAGE], {{ type: 'text/html' }}));
  const w = window.open(url, '_blank');
  document.getElementById('msg').textContent = w
    ? 'Carte ouverte dans un nouvel onglet. Recliquez pour en ouvrir une autre.'
    : 'Le navigateur a bloqué l’ouverture : autorisez les fenêtres pop-up pour le HUB, ou téléchargez la carte ci-dessous.';
}});
</script>
""", height=90)


# ─── Page ────────────────────────────────────────────────────────────────────
st.markdown('<div class="ap-hero"><h1>Carte manuelle</h1>'
            '<p>Itinéraires poids lourds, péages et kilomètres par pays, traversées. '
            'La carte s’ouvre en plein écran dans un nouvel onglet.</p></div>',
            unsafe_allow_html=True)

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
except FileNotFoundError:
    st.error("map.html introuvable à la racine du projet.")
    st.stop()
except Exception as e:
    st.error(f"Erreur chargement map.html : {e}")
    st.stop()

bouton_ouvrir(html_final)

if server_ready:
    st.markdown('<div class="ap-statut"><i></i>Serveur carte prêt</div>', unsafe_allow_html=True)
else:
    st.markdown(f'<div class="ap-statut off"><i></i>Le serveur carte ({MAP_SERVER_URL}) n’a pas répondu au réveil. '
                'Le premier calcul peut échouer : relancez-le une fois.</div>', unsafe_allow_html=True)

st.write("")
c1, _ = st.columns([1, 2])
with c1:
    st.download_button("Télécharger la carte (HTML)", html_final.encode("utf-8"),
                       file_name="carte_manuelle.html", mime="text/html", use_container_width=True)
st.caption("Le fichier HTML s’ouvre dans n’importe quel navigateur, sans le HUB. "
           "Il utilise le même serveur carte pour les calculs.")

st.markdown('<div class="ap-section">Dans la carte</div>', unsafe_allow_html=True)
st.markdown(
    '<ul class="ap-list">'
    '<li><b>Départ et arrivée</b> <span>: tapez une adresse ou des coordonnées, ou cliquez sur la carte.</span></li>'
    '<li><b>Étapes</b> <span>: clic droit sur la carte, ou recherche d’adresse en bas du panneau.</span></li>'
    '<li><b>Distance et péage</b> <span>: un clic sur la case affiche le détail par pays.</span></li>'
    '<li><b>Traversées</b> <span>: choisissez la ligne de ferry ou de navette dans le bloc dédié.</span></li>'
    '<li><b>Plan ou Satellite</b> <span>: dans la barre en bas de la carte, avec les types de routes et les restrictions PL.</span></li>'
    '</ul>',
    unsafe_allow_html=True,
)
