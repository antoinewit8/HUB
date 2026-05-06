"""
Page plein écran : Carte des lavages citernes
Ouvre la carte pydeck en layout fullscreen depuis l'optimisateur lavages.
"""

import streamlit as st
import pandas as pd
import urllib.parse
import os, sys

st.set_page_config(
    page_title="Carte Lavages — Plein Écran",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Style plein écran ────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0a1520; }
[data-testid="stSidebar"] { display: none; }
[data-testid="collapsedControl"] { display: none; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding: 0.5rem 1rem 0 1rem !important; max-width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# ─── Récupération des paramètres URL ─────────────────────────────────────────
params = st.query_params
localite = params.get("localite", "")

# ─── Imports géocodage ────────────────────────────────────────────────────────
import urllib.request as _ureq
import json as _json

def _photon_call(query: str):
    url = f"https://photon.komoot.io/api/?q={urllib.parse.quote(query)}&limit=1&lang=fr"
    try:
        req = _ureq.Request(url, headers={"User-Agent": "CB-Transport-Hub/1.0"})
        with _ureq.urlopen(req, timeout=6) as r:
            data = _json.loads(r.read())
        features = data.get("features", [])
        if features:
            coords = features[0]["geometry"]["coordinates"]
            return float(coords[1]), float(coords[0])
    except Exception:
        pass
    return None

def _nominatim_call(query: str):
    url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={urllib.parse.quote(query)}&format=json&limit=1"
    )
    try:
        req = _ureq.Request(url, headers={"User-Agent": "CB-Transport-Hub/1.0"})
        with _ureq.urlopen(req, timeout=6) as r:
            data = _json.loads(r.read())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None

def geocode(query: str):
    return _photon_call(query) or _nominatim_call(query)

# ─── Normalisation ST → SAINT ─────────────────────────────────────────────────
import re as _re
import unicodedata

def normalize_ville(text: str) -> str:
    t = _re.sub(r'\bST\b', 'SAINT', text, flags=_re.IGNORECASE)
    t = _re.sub(r'\bSTE\b', 'SAINTE', t, flags=_re.IGNORECASE)
    return t

# ─── Chargement données depuis session_state ou upload ───────────────────────
st.markdown(f"### 🗺️ Carte des lavages — **{localite or 'Localité non précisée'}**")
col_back, col_title = st.columns([1, 8])
with col_back:
    st.page_link("pages/11_Optimisateur_Lavages_CIT.py", label="← Retour", icon="↩️")

if not localite:
    st.warning("Aucune localité passée en paramètre. Ouvrez cette page depuis l'optimisateur lavages.")
    st.stop()

# Upload des fichiers (nécessaires car pas de session partagée entre pages)
st.caption("Les fichiers doivent être rechargés pour cette vue plein écran.")
col_u1, col_u2 = st.columns(2)
with col_u1:
    missions_file = st.file_uploader("📋 Fichier Missions", type=["xlsx","xls"], key="pf_missions")
with col_u2:
    lavages_file  = st.file_uploader("🧼 Fichier Lavages",  type=["xlsx","xls"], key="pf_lavages")

if not missions_file or not lavages_file:
    st.info("👆 Rechargez les deux fichiers pour afficher la carte.")
    st.stop()

# ─── Chargement ──────────────────────────────────────────────────────────────
import io as _io

@st.cache_data(show_spinner=False)
def load_for_map(m_bytes, l_bytes, localite_query):
    df_m = pd.read_excel(_io.BytesIO(m_bytes), dtype=str)
    df_l = pd.read_excel(_io.BytesIO(l_bytes), dtype=str)
    df_m.columns = df_m.columns.str.strip()
    df_l.columns = df_l.columns.str.strip()
    df_m["N° Dossier"] = df_m["N° Dossier"].str.strip()
    df_l["N° Dossier"] = df_l["N° Dossier"].str.strip()

    # Filtre localité
    mask = df_m["Localité déchargement"].str.upper().str.strip() == localite_query.upper().strip()
    df_mf = df_m[mask]
    ids = df_mf["N° Dossier"].unique()
    df_lm = df_l[df_l["N° Dossier"].isin(ids)]

    # Stats stations
    station_counts = df_lm.groupby(["Nom 1","Localité","Code postal"]).size().reset_index(name="nb")

    # Pays
    pays_dech = df_mf["Pays déchargement"].dropna().mode()
    pays_str  = pays_dech.iloc[0].strip() if not pays_dech.empty else ""
    cp_dech   = df_mf["C.P. déchargement"].dropna().mode()
    cp_str    = cp_dech.iloc[0].strip() if not cp_dech.empty else ""

    return station_counts, pays_str, cp_str, len(df_mf), len(df_lm)

with st.spinner("Chargement des données..."):
    station_counts, pays_str, cp_str, nb_missions, nb_lavages = load_for_map(
        missions_file.read(), lavages_file.read(), localite
    )

PAYS_MAP_GEO = {
    "F":"France","B":"Belgium","BE":"Belgium","D":"Germany",
    "NL":"Netherlands","L":"Luxembourg","E":"Spain","I":"Italy",
    "GB":"United Kingdom","CH":"Switzerland","A":"Austria",
    "PL":"Poland","CZ":"Czech Republic",
}
pays_label = PAYS_MAP_GEO.get(pays_str.upper(), pays_str)

# KPIs compacts
k1, k2, k3 = st.columns(3)
k1.metric("Missions", nb_missions)
k2.metric("Lavages", nb_lavages)
k3.metric("Stations", station_counts["Nom 1"].nunique())

# ─── Géocodage ───────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=86400)
def geocode_cached(q):
    return geocode(q)

with st.spinner("Géocodage des stations..."):
    geocoded = []
    for _, row in station_counts.iterrows():
        q1 = f"{row['Nom 1']}, {row['Localité']}, {row['Code postal']}"
        coords = geocode_cached(q1) or geocode_cached(f"{row['Localité']}, {row['Code postal']}")
        if coords:
            geocoded.append({
                "nom": row["Nom 1"], "localite": row["Localité"],
                "cp": row["Code postal"], "nb": int(row["nb"]),
                "lat": coords[0], "lon": coords[1],
            })

    # Point de déchargement
    loc_exp = normalize_ville(localite)
    dest_coords = None
    for attempt in [
        f"{loc_exp}, {cp_str}, {pays_label}",
        f"{loc_exp}, {pays_label}",
        loc_exp,
        f"{localite}, {pays_label}",
        localite,
    ]:
        dest_coords = geocode(attempt)
        if dest_coords:
            break

if not geocoded and not dest_coords:
    st.error("Impossible de géocoder les données pour cette localité.")
    st.stop()

# ─── Carte pydeck plein écran ─────────────────────────────────────────────────
try:
    import pydeck as pdk

    df_geo  = pd.DataFrame(geocoded) if geocoded else pd.DataFrame()
    layers  = []

    if not df_geo.empty:
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=df_geo,
            get_position="[lon, lat]", get_radius=5000,
            get_fill_color=[74, 144, 217, 210],
            get_line_color=[255, 255, 255, 180],
            stroked=True, line_width_min_pixels=1,
            pickable=True, auto_highlight=True,
        ))
        layers.append(pdk.Layer(
            "TextLayer", data=df_geo,
            get_position="[lon, lat]", get_text="nom",
            get_size=13, get_color=[220, 235, 255, 220],
            get_anchor="middle", get_alignment_baseline="'bottom'",
            get_pixel_offset=[0, -12],
        ))

    if dest_coords:
        df_dest = pd.DataFrame([{
            "lat": dest_coords[0], "lon": dest_coords[1],
            "label": localite.upper(), "nom": f"Déchargement : {localite}",
        }])
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=df_dest,
            get_position="[lon, lat]", get_radius=10000,
            get_fill_color=[220, 30, 30, 240],
            get_line_color=[255, 255, 255, 255],
            stroked=True, line_width_min_pixels=2, pickable=True,
        ))
        layers.append(pdk.Layer(
            "TextLayer", data=df_dest,
            get_position="[lon, lat]", get_text="label",
            get_size=15, get_color=[255, 80, 80, 255],
            get_anchor="middle", get_alignment_baseline="'bottom'",
            get_pixel_offset=[0, -16], font_weight=800,
        ))

    center_lat = dest_coords[0] if dest_coords else (df_geo["lat"].mean() if not df_geo.empty else 46.8)
    center_lon = dest_coords[1] if dest_coords else (df_geo["lon"].mean() if not df_geo.empty else 2.3)

    view = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=5, pitch=0)

    tooltip = {
        "html": "<b>{nom}</b><br>{localite} ({cp})<br>🧼 {nb} lavage(s)",
        "style": {"background": "#0e1b28", "color": "#e8f4fd", "font-size": "14px", "padding": "10px"}
    }

    deck = pdk.Deck(
        layers=layers, initial_view_state=view, tooltip=tooltip,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )

    # Carte pleine hauteur
    st.pydeck_chart(deck, use_container_width=True, height=750)

    st.markdown(
        "<small>🔵 Stations de lavage &nbsp;|&nbsp; 🔴 Localité de déchargement</small>",
        unsafe_allow_html=True
    )

except ImportError:
    if not df_geo.empty:
        st.map(df_geo.rename(columns={"lat":"latitude","lon":"longitude"}))
