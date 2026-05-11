import streamlit as st
from datetime import datetime
import os, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

try:
    from config import APP_NAME, VERSION
except ImportError:
    APP_NAME = "Transport Hub"
    VERSION = "1.0.0"

try:
    from session import init_session
    init_session()
except Exception:
    pass

st.set_page_config(
    page_title="Transport Hub -- CB Groupe",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
)

# === METS TES VRAIES CHAINES BASE64 ICI ===
LOGO_B64  = "/9j/4AAQSkZJRgABAQAAAQABAAD/4gHYSUNDX1..." # Remets ton vrai logo
TRUCK_B64 = "/9j/4AAQSkZJRgABAQEAYABgAAD//gA7Q1JEQV..." # Remets ton vrai camion

# ============================================================
# BLOC 1 : CSS GLOBAL (Avec la nouvelle animation et polices augmentées)
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@300;400;500;600;700&family=Barlow+Condensed:wght@400;600;700;800&display=swap');

* { box-sizing: border-box; }

.stApp { background: #060b12; font-family: 'Barlow', sans-serif; }
.stDeployButton, #MainMenu, footer, header, .stToolbar { display: none !important; }

section[data-testid="stSidebar"] {
    background: #080e17 !important;
    border-right: 1px solid rgba(255,255,255,0.05) !important;
}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label { color: #8898aa !important; }

.block-container { padding: 0 !important; max-width: 100% !important; }

.cb-hero-wrap {
    position: relative;
    width: 100%;
    height: 55vh;
    min-height: 400px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}
.cb-hero-bg {
    position: absolute;
    inset: 0;
    background-size: cover;
    background-position: center 42%;
    filter: blur(6px) brightness(0.22) saturate(0.6);
    transform: scale(1.08);
    z-index: 0;
}
.cb-hero-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(
        180deg,
        rgba(6,11,18,0.55) 0%,
        rgba(6,11,18,0.2) 28%,
        rgba(6,11,18,0.35) 60%,
        rgba(6,11,18,0.95) 90%,
        rgba(6,11,18,1.0) 100%
    );
    z-index: 1;
}
.cb-hero-topbar {
    position: relative;
    z-index: 3;
    padding: 2rem 2.8rem 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
}
.cb-logo img {
    height: 64px;
    width: auto;
    display: block;
    border-radius: 9px;
}
.cb-hero-live {
    display: flex;
    align-items: center;
    gap: 7px;
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    color: rgba(255,255,255,0.3);
}
.cb-live-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #2ecc71;
    box-shadow: 0 0 8px #2ecc71;
    animation: blink 2.2s ease-in-out infinite;
}
@keyframes blink {
    0%,100% { opacity: 1; }
    50% { opacity: 0.3; }
}
.cb-hero-center {
    position: relative;
    z-index: 3;
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 0 2rem;
}
.cb-hero-eyebrow {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.85rem;
    font-weight: 700;
    letter-spacing: 5px;
    text-transform: uppercase;
    color: rgba(255,255,255,0.4);
    margin-bottom: 1rem;
}
.cb-hero-title {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: clamp(4rem, 8vw, 8rem);
    font-weight: 800;
    line-height: 0.88;
    color: #ffffff;
    letter-spacing: -2px;
    margin-bottom: 1.5rem;
    text-shadow: 0 4px 60px rgba(0,0,0,0.9), 0 0 120px rgba(0,0,0,0.6);
}
.cb-hero-sub {
    font-size: 1.15rem;
    font-weight: 300;
    color: rgba(255,255,255,0.6);
    letter-spacing: 0.5px;
    max-width: 500px;
    line-height: 1.65;
}

/* SECTION OUTILS & CARTES */
.cb-tools-section {
    background: #060b12;
    padding: 2.8rem 3rem 5rem;
}
.cb-tools-label {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 4.5px;
    text-transform: uppercase;
    color: rgba(255,255,255,0.25);
    margin-bottom: 1.8rem;
}
.cb-tool-grid {
    display: grid;
    /* Cases plus larges et espacées pour l'effet de pop-out */
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.8rem; 
}
.cb-tool-card {
    background: #0b1420;
    padding: 2.5rem 2rem;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.06);
    cursor: pointer;
    /* Transition ultra fluide pour l'animation */
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    height: 100%;
}
/* SUPER ANIMATION AU SURVOL */
.cb-tool-card:hover {
    background: #112236;
    transform: translateY(-10px) scale(1.02);
    box-shadow: 0 20px 40px rgba(0,0,0,0.6), 0 0 20px rgba(46, 204, 113, 0.15);
    border-color: rgba(255,255,255,0.2);
}
.cb-tool-name {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.8rem; /* Police largement augmentée */
    font-weight: 700;
    color: #e8f0fb;
    margin: 0;
}
.cb-tool-desc {
    font-size: 1.05rem; /* Police augmentée */
    font-weight: 400;
    color: rgba(255,255,255,0.5);
    line-height: 1.55;
    margin: 0;
}
.cb-tool-arrow {
    margin-top: auto; /* Pousse la flèche tout en bas */
    padding-top: 1.5rem;
    font-size: 0.85rem;
    font-weight: 700;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    color: rgba(255,255,255,0.15);
    transition: color 0.18s;
}
.cb-tool-card:hover .cb-tool-arrow { color: #2ecc71; /* La flèche devient verte au survol ! */ }
</style>
""", unsafe_allow_html=True)

# ============================================================
# BLOC 2 : BACKGROUND IMAGE
# ============================================================
st.markdown(f"""<style>.cb-hero-bg {{ background-image: url('data:image/jpeg;base64,{TRUCK_B64}'); }}</style>""", unsafe_allow_html=True)

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown(f"""
    <div style="padding:1.2rem 0 0.8rem; display:flex; align-items:center; gap:0.8rem;">
        <img src="data:image/jpeg;base64,{LOGO_B64}" style="height:42px; border-radius:7px;" />
        <div>
            <div style="font-size:0.62rem; color:#2a3a4d; letter-spacing:2.5px; text-transform:uppercase; font-family:'Barlow Condensed',sans-serif; font-weight:700;">Transport Hub</div>
            <div style="font-size:0.7rem; color:#1a2535; font-family:'Barlow',sans-serif;">v{VERSION}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()
    st.markdown('<p style="color:#2a3a4d; font-size:0.62rem; letter-spacing:3px; text-transform:uppercase; padding:0 0 0.5rem; font-family:Barlow,sans-serif; font-weight:700;">Navigation</p>', unsafe_allow_html=True)

    nav_pages = [
        ("Analyse TX-FLEX", "pages/1___Analyse_TX_FLEX.py"),
        ("Calcul KM",       "pages/2____Calcul_KM.py"),
        ("Carte Manuelle",  "pages/3____Carte_Manuelle.py"),
        ("Prix Gasoil",     "pages/5___Prix_Gasoil.py"),
    ]
    for label, path in nav_pages:
        try:
            st.page_link(path, label=label, use_container_width=True)
        except Exception:
            pass

    st.divider()
    st.markdown(f'<p style="color:#111925; font-size:0.7rem;">{datetime.now().strftime("%A %d %B %Y")}</p>', unsafe_allow_html=True)

# ============================================================
# BLOC 3 : HTML DE LA PAGE PRINCIPALE (Titre + Grille)
# ============================================================
# 1. On définit la liste des outils avec l'URL exacte vers laquelle on veut naviguer
tools = [
    ("Analyse TX-FLEX", "Analyse de flotte, performance et rentabilité transport", "Analyse_TX_FLEX"),
    ("Calcul KM",       "Distances PTV et optimisation des itinéraires", "Calcul_KM"),
    ("Carte Manuelle",  "Visualisation interactive des trajets sur carte", "Carte_Manuelle"),
    ("Prix Gasoil",     "Suivi des prix carburant et tendances", "Prix_Gasoil"),
]

# 2. On génère le HTML des cartes (maintenant cliquables via <a href="...">)
cards_html = ""
for name, desc, link in tools:
    cards_html += f"""
    <a href="{link}" target="_self" style="text-decoration: none;">
        <div class="cb-tool-card">
            <p class="cb-tool-name">{name}</p>
            <p class="cb-tool-desc">{desc}</p>
            <div class="cb-tool-arrow">Ouvrir &rarr;</div>
        </div>
    </a>
    """

# 3. On injecte le TOUT en une seule fois (bannière + grille)
st.markdown(f"""
<div class="cb-hero-wrap">
    <div class="cb-hero-bg"></div>
    <div class="cb-hero-overlay"></div>

    <div class="cb-hero-topbar">
        <div class="cb-logo">
            <img src="data:image/jpeg;base64,{LOGO_B64}" alt="CB Groupe" />
        </div>
        <div class="cb-hero-live">
            <span class="cb-live-dot"></span>
            {datetime.now().strftime('%H:%M')} &nbsp;&middot;&nbsp; Système actif
        </div>
    </div>

    <div class="cb-hero-center">
        <p class="cb-hero-eyebrow">CB Groupe &mdash; Transport &amp; Logistique</p>
        <h1 class="cb-hero-title">Transport<br>Hub</h1>
        <p class="cb-hero-sub">Outils internes de gestion<br>et d'optimisation des transports</p>
    </div>
</div>

<div class="cb-tools-section">
    <p class="cb-tools-label">Modules disponibles</p>
    <div class="cb-tool-grid">
        {cards_html}
    </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# BLOC 4 : Grille d'outils
# ============================================================
tools = [
    ("Analyse TX-FLEX", "Analyse de flotte, performance et rentabilite transport",  "pages/1___Analyse_TX_FLEX.py"),
    ("Calcul KM",       "Distances PTV et optimisation des itineraires",            "pages/2____Calcul_KM.py"),
    ("Carte Manuelle",  "Visualisation interactive des trajets sur carte",          "pages/3____Carte_Manuelle.py"),
    ("Prix Gasoil",     "Suivi des prix carburant et tendances",                    "pages/5___Prix_Gasoil.py"),
]

cards = ""
for name, desc, _ in tools:
    cards += f"""<div class="cb-tool-card">
        <p class="cb-tool-name">{name}</p>
        <p class="cb-tool-desc">{desc}</p>
        <div class="cb-tool-arrow">Ouvrir &rarr;</div>
    </div>"""

st.markdown(f"""
<div class="cb-tools-section">
    <p class="cb-tools-label">Modules disponibles</p>
    <div class="cb-tool-grid">{cards}</div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# BLOC 5 : Liens de navigation Streamlit (sous la grille)
# ============================================================
cols = st.columns(4)
for i, (label, desc, path) in enumerate(tools):
    with cols[i]:
        try:
            st.page_link(path, label=label, use_container_width=True)
        except Exception:
            pass
