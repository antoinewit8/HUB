"""
Page Streamlit : Optimisateur Lavages Citernes
Croise le fichier missions (CA CIT) avec le fichier lavages par N° Dossier.
Recherche par localité de déchargement → affiche les lavages associés + carte.
"""

import streamlit as st
import pandas as pd
import os
import sys
import unicodedata
import re
from collections import Counter

st.set_page_config(
    page_title="Optimisateur Lavages CIT",
    page_icon="🪣",
    layout="wide",
)

# ─── Style ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600;700&family=Barlow:wght@400;500;600&display=swap');

:root {
  --bg:            #f5f3f0;
  --surface:       #faf9f7;
  --surface-alt:   #eeebe6;
  --border:        #d4cfc8;
  --border-strong: #b0a99f;
  --ink:           #1c1a17;
  --ink-2:         #4a4540;
  --ink-3:         #7a736a;
  --accent:        #1e3a5f;
  --accent-dim:    #e4eaf2;
  --font-ui:       'Barlow Condensed', 'Arial Narrow', sans-serif;
  --font-body:     'Barlow', system-ui, sans-serif;
}

[data-testid="stAppViewContainer"] {
  background: var(--bg) !important;
  font-family: var(--font-body);
  color: var(--ink);
}
[data-testid="stSidebar"] {
  background: var(--surface) !important;
  border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] * { color: var(--ink) !important; }

h1, h2, h3 {
  font-family: var(--font-ui);
  color: var(--ink);
  font-weight: 700;
}
.stMarkdown { color: var(--ink); }

/* ── KPI ─────────────────────────────────────────────────────────── */
.kpi-box {
  background: var(--surface);
  border: 1px solid var(--border);
  border-top: 2px solid var(--accent);
  border-radius: 2px;
  padding: 0.75rem 1rem;
  margin-bottom: 0.5rem;
}
.kpi-box .kpi-val {
  font-family: var(--font-ui);
  font-size: 2.1rem;
  font-weight: 700;
  color: var(--ink);
  line-height: 1;
  letter-spacing: -0.01em;
}
.kpi-box .kpi-lbl {
  font-family: var(--font-ui);
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--ink-3);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-top: 0.25rem;
}

/* ── Station cards ───────────────────────────────────────────────── */
.lavage-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 2px;
  padding: 0.65rem 0.9rem;
  margin-bottom: 0.35rem;
  display: grid;
  grid-template-columns: 2.2rem 1fr;
  gap: 0 0.7rem;
  align-items: start;
}
.lavage-card .rank {
  font-family: var(--font-ui);
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--ink-3);
  line-height: 1.2;
}
.lavage-card .station {
  font-family: var(--font-ui);
  font-weight: 600;
  font-size: 0.95rem;
  color: var(--ink);
}
.lavage-card .localite {
  font-size: 0.82rem;
  color: var(--ink-2);
  margin-top: 0.1rem;
}
.lavage-card .count {
  font-family: var(--font-ui);
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--ink-3);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  margin-top: 0.2rem;
}

/* ── Section titles ──────────────────────────────────────────────── */
.section-title {
  font-family: var(--font-ui);
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--ink-3);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.35rem;
  margin: 1.4rem 0 0.75rem 0;
}

/* ── Tabs ────────────────────────────────────────────────────────── */
[data-baseweb="tab-list"] {
  background: var(--surface-alt) !important;
  border-bottom: 1px solid var(--border-strong) !important;
  border-radius: 0 !important;
  gap: 0 !important;
}
[data-baseweb="tab"] {
  font-family: var(--font-ui) !important;
  font-size: 0.75rem !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.09em !important;
  color: var(--ink-3) !important;
  border-radius: 0 !important;
  border-bottom: 2px solid transparent !important;
  padding: 0.5rem 1.1rem !important;
}
[aria-selected="true"][data-baseweb="tab"] {
  color: var(--accent) !important;
  border-bottom-color: var(--accent) !important;
  background: transparent !important;
}

/* ── Buttons ─────────────────────────────────────────────────────── */
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button {
  font-family: var(--font-ui) !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.07em !important;
  font-size: 0.75rem !important;
  background: var(--accent) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 2px !important;
  padding: 0.45rem 1.1rem !important;
}
[data-testid="stButton"] button:hover,
[data-testid="stDownloadButton"] button:hover {
  background: #162d4a !important;
}

/* ── Inputs / selects ────────────────────────────────────────────── */
[data-baseweb="select"] > div,
[data-baseweb="input"] > div {
  border-radius: 2px !important;
  border-color: var(--border) !important;
  background: var(--surface) !important;
  font-family: var(--font-body) !important;
  font-size: 0.875rem !important;
}

/* ── Misc ────────────────────────────────────────────────────────── */
hr { border-color: var(--border) !important; opacity: 1 !important; }

[data-testid="stAlert"] {
  border-radius: 2px !important;
  font-family: var(--font-body) !important;
  font-size: 0.875rem !important;
}

[data-testid="stHeading"] h2 {
  font-family: var(--font-ui) !important;
  font-size: 1.4rem !important;
  font-weight: 700 !important;
  color: var(--ink) !important;
  letter-spacing: 0.01em !important;
}

[data-testid="stCaptionContainer"] {
  color: var(--ink-3) !important;
  font-size: 0.82rem !important;
}

/* Dataframe header */
[data-testid="stDataFrame"] thead th {
  font-family: var(--font-ui) !important;
  font-size: 0.72rem !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.08em !important;
  color: var(--ink-2) !important;
  background: var(--surface-alt) !important;
}
</style>
""", unsafe_allow_html=True)

# ─── Normalisation texte ──────────────────────────────────────────────────────
def normalize(text: str) -> str:
    if not text:
        return ""
    text = str(text).upper().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"['\-–]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# ─── Chargement données ───────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_data(missions_bytes, lavages_bytes):
    import io
    df_m = pd.read_excel(io.BytesIO(missions_bytes), dtype=str)
    df_l = pd.read_excel(io.BytesIO(lavages_bytes), dtype=str)

    df_m.columns = df_m.columns.str.strip()
    df_l.columns = df_l.columns.str.strip()

    df_m["N° Dossier"] = df_m["N° Dossier"].str.strip()
    df_l["N° Dossier"] = df_l["N° Dossier"].str.strip()

    if "Date chargement" in df_m.columns:
        df_m["Date chargement"] = pd.to_datetime(df_m["Date chargement"], errors="coerce")
    if "Date" in df_l.columns:
        df_l["Date"] = pd.to_datetime(df_l["Date"], errors="coerce")

    df_m["_localite_norm"] = df_m["Localité déchargement"].apply(normalize)
    df_l["_localite_lavage_norm"] = df_l["Localité"].apply(normalize)

    return df_m, df_l

# ─── Géocodage nominatim ──────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=86400)
def geocode_location(query: str):
    import urllib.request, json
    url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={urllib.parse.quote(query)}&format=json&limit=1"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CB-Transport-Hub/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None

import urllib.parse

# ─── Header ──────────────────────────────────────────────────────────────────
st.markdown("## 🪣 Optimisateur Lavages Citernes")
st.caption("Croisez les missions citernes avec les lavages associés — trouvez les stations par localité de déchargement")
st.divider()

# ─── Upload fichiers ─────────────────────────────────────────────────────────
col_up1, col_up2 = st.columns(2)
with col_up1:
    missions_file = st.file_uploader(
        "📋 Fichier Missions (CA CIT)",
        type=["xlsx", "xls"],
        key="missions",
        help="Fichier CA_CIT_25-ajd avec toutes les missions citernes"
    )
with col_up2:
    lavages_file = st.file_uploader(
        "🧼 Fichier Lavages",
        type=["xlsx", "xls"],
        key="lavages",
        help="Fichier liste_lavages avec N° Dossier et stations"
    )

if not missions_file or not lavages_file:
    st.info("👆 Chargez les deux fichiers Excel pour démarrer")
    st.stop()

# ─── Chargement ──────────────────────────────────────────────────────────────
with st.spinner("Chargement et croisement des données..."):
    try:
        df_m, df_l = load_data(missions_file.read(), lavages_file.read())
    except Exception as e:
        st.error(f"Erreur chargement : {e}")
        st.stop()

# ─── KPIs globaux ────────────────────────────────────────────────────────────
total_missions         = len(df_m)
total_lavages          = len(df_l)
dossiers_avec_lavage   = len(set(df_m["N° Dossier"]) & set(df_l["N° Dossier"]))
nb_localites           = df_m["Localité déchargement"].nunique()

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{total_missions:,}</div><div class="kpi-lbl">Missions CIT</div></div>', unsafe_allow_html=True)
with k2:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{total_lavages:,}</div><div class="kpi-lbl">Lavages enregistrés</div></div>', unsafe_allow_html=True)
with k3:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{dossiers_avec_lavage:,}</div><div class="kpi-lbl">Dossiers avec lavage</div></div>', unsafe_allow_html=True)
with k4:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{nb_localites:,}</div><div class="kpi-lbl">Localités déchargement</div></div>', unsafe_allow_html=True)

st.divider()

# ─── Recherche ───────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Recherche par localité de déchargement</div>', unsafe_allow_html=True)

localites_list = sorted(df_m["Localité déchargement"].dropna().unique().tolist())

col_search, col_pays = st.columns([3, 1])
with col_search:
    query = st.selectbox(
        "Localité de déchargement",
        options=[""] + localites_list,
        index=0,
        help="Tapez pour filtrer la liste"
    )
with col_pays:
    pays_filter = st.selectbox(
        "Filtrer par pays",
        ["Tous"] + sorted(df_m["Pays déchargement"].dropna().unique().tolist())
    )

with st.expander("Filtres avancés", expanded=False):
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        produit_filter = st.multiselect(
            "Produit transporté",
            options=sorted(df_m["Produit"].dropna().unique().tolist()),
        )
    with col_f2:
        client_filter = st.multiselect(
            "Client facturation",
            options=sorted(df_m["Client facturation"].dropna().unique().tolist()),
        )
    with col_f3:
        date_range = st.date_input(
            "Période",
            value=[],
            help="Laisser vide = toutes les dates"
        )

if not query:
    st.info("Sélectionnez ou tapez une localité de déchargement pour voir les lavages associés")
    st.stop()

# ─── Filtrage missions ────────────────────────────────────────────────────────
query_norm = normalize(query)
mask = df_m["_localite_norm"].str.contains(query_norm, na=False, regex=False)

if pays_filter != "Tous":
    mask &= df_m["Pays déchargement"].str.strip() == pays_filter
if produit_filter:
    mask &= df_m["Produit"].isin(produit_filter)
if client_filter:
    mask &= df_m["Client facturation"].isin(client_filter)
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    d_from, d_to = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    mask &= df_m["Date chargement"].between(d_from, d_to)

df_missions_filtre = df_m[mask].copy()

if df_missions_filtre.empty:
    st.warning(f"Aucune mission trouvée pour « {query} »")
    st.stop()

# ─── Croisement avec lavages ──────────────────────────────────────────────────
dossiers_ids      = df_missions_filtre["N° Dossier"].unique()
df_lavages_match  = df_l[df_l["N° Dossier"].isin(dossiers_ids)].copy()

# ─── Résultats header ────────────────────────────────────────────────────────
st.markdown(f'<div class="section-title">Résultats — {query}</div>', unsafe_allow_html=True)

r1, r2, r3 = st.columns(3)
with r1:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{len(df_missions_filtre)}</div><div class="kpi-lbl">Missions trouvées</div></div>', unsafe_allow_html=True)
with r2:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{len(df_lavages_match)}</div><div class="kpi-lbl">Lavages associés</div></div>', unsafe_allow_html=True)
with r3:
    nb_stations = df_lavages_match["Nom 1"].nunique() if not df_lavages_match.empty else 0
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{nb_stations}</div><div class="kpi-lbl">Stations distinctes</div></div>', unsafe_allow_html=True)

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_lavages, tab_carte, tab_missions, tab_stats = st.tabs([
    "Lavages", "Carte", "Missions", "Statistiques"
])

# ── Tab Lavages ───────────────────────────────────────────────────────────────
with tab_lavages:
    if df_lavages_match.empty:
        st.info("Aucun lavage enregistré pour ces dossiers.")
    else:
        st.markdown('<div class="section-title">Stations les plus utilisées</div>', unsafe_allow_html=True)

        station_counts = (
            df_lavages_match
            .groupby(["Nom 1", "Localité", "Code postal"])
            .size()
            .reset_index(name="Nb lavages")
            .sort_values("Nb lavages", ascending=False)
        )

        for i, (_, row) in enumerate(station_counts.head(10).iterrows()):
            pct = int(row["Nb lavages"] / len(df_lavages_match) * 100)
            st.markdown(f"""
            <div class="lavage-card">
              <div class="rank">#{i+1}</div>
              <div>
                <div class="station">{row['Nom 1']}</div>
                <div class="localite">{row['Localité']} — {row['Code postal']}</div>
                <div class="count">{row['Nb lavages']} lavage(s) · {pct}%</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Détail des lavages</div>', unsafe_allow_html=True)

        cols_mission_merge = [c for c in [
            "N° Dossier", "Date chargement", "Localité chargement",
            "Localité déchargement", "Produit", "Client facturation"
        ] if c in df_missions_filtre.columns]

        df_detail = df_lavages_match.merge(
            df_missions_filtre[cols_mission_merge],
            on="N° Dossier",
            how="left"
        )

        cols_show = [c for c in [
            "N° Dossier", "Date", "Nom 1", "Localité", "Code postal",
            "Chauffeur", "Tracteur", "Remorque", "Prix",
            "Localité chargement", "Localité déchargement", "Produit", "Client facturation"
        ] if c in df_detail.columns]

        st.dataframe(
            df_detail[cols_show].sort_values("Date", ascending=False)
            if "Date" in df_detail.columns else df_detail[cols_show],
            use_container_width=True,
            hide_index=True,
        )

        import io as _io
        buf = _io.BytesIO()
        df_detail[cols_show].to_excel(buf, index=False, engine="openpyxl")
        st.download_button(
            "Exporter les lavages (Excel)",
            data=buf.getvalue(),
            file_name=f"lavages_{normalize(query).replace(' ','_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ── Tab Carte ─────────────────────────────────────────────────────────────────
with tab_carte:
    st.markdown('<div class="section-title">Carte des stations de lavage</div>', unsafe_allow_html=True)

    if df_lavages_match.empty:
        st.info("Aucun lavage à afficher sur la carte.")
    else:
        station_counts = (
            df_lavages_match
            .groupby(["Nom 1", "Localité", "Code postal"])
            .size()
            .reset_index(name="Nb lavages")
            .sort_values("Nb lavages", ascending=False)
        )

        geocoded = []
        progress_bar = st.progress(0, text="Géocodage des stations...")
        total_s = len(station_counts)

        for i, (_, row) in enumerate(station_counts.iterrows()):
            search_q = f"{row['Nom 1']}, {row['Localité']}, {row['Code postal']}"
            coords = geocode_location(search_q)
            if coords is None:
                coords = geocode_location(f"{row['Localité']}, {row['Code postal']}")
            if coords:
                geocoded.append({
                    "nom":      row["Nom 1"],
                    "localite": row["Localité"],
                    "cp":       row["Code postal"],
                    "nb":       int(row["Nb lavages"]),
                    "lat":      coords[0],
                    "lon":      coords[1],
                })
            progress_bar.progress((i + 1) / total_s, text=f"Géocodage {i+1}/{total_s}")

        progress_bar.empty()

        if not geocoded:
            st.warning("Impossible de géocoder les stations pour cette localité.")
        else:
            df_geo = pd.DataFrame(geocoded)
            dest_coords = geocode_location(f"{query}, France") or geocode_location(query)

            try:
                import pydeck as pdk

                layer_stations = pdk.Layer(
                    "ScatterplotLayer",
                    data=df_geo,
                    get_position="[lon, lat]",
                    get_radius=5000,
                    get_fill_color=[30, 58, 95, 200],      # accent slate
                    get_line_color=[255, 255, 255, 180],
                    stroked=True,
                    line_width_min_pixels=1,
                    pickable=True,
                    auto_highlight=True,
                )
                layer_stations_text = pdk.Layer(
                    "TextLayer",
                    data=df_geo,
                    get_position="[lon, lat]",
                    get_text="nom",
                    get_size=12,
                    get_color=[28, 26, 23, 220],            # ink
                    get_anchor="middle",
                    get_alignment_baseline="'bottom'",
                    get_pixel_offset=[0, -10],
                )

                layers = [layer_stations, layer_stations_text]

                if dest_coords:
                    df_dest = pd.DataFrame([{
                        "lat":   dest_coords[0],
                        "lon":   dest_coords[1],
                        "nom":   f"Déchargement : {query}",
                        "label": query.upper(),
                    }])
                    layer_dest = pdk.Layer(
                        "ScatterplotLayer",
                        data=df_dest,
                        get_position="[lon, lat]",
                        get_radius=10000,
                        get_fill_color=[180, 30, 30, 230],  # rouge statut
                        get_line_color=[255, 255, 255, 255],
                        stroked=True,
                        line_width_min_pixels=2,
                        pickable=True,
                    )
                    layer_dest_text = pdk.Layer(
                        "TextLayer",
                        data=df_dest,
                        get_position="[lon, lat]",
                        get_text="label",
                        get_size=13,
                        get_color=[180, 30, 30, 255],
                        get_anchor="middle",
                        get_alignment_baseline="'bottom'",
                        get_pixel_offset=[0, -14],
                        font_weight=800,
                    )
                    layers += [layer_dest, layer_dest_text]

                center_lat = dest_coords[0] if dest_coords else df_geo["lat"].mean()
                center_lon = dest_coords[1] if dest_coords else df_geo["lon"].mean()

                view = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=5, pitch=0)

                tooltip = {
                    "html": "<b>{nom}</b><br>{localite} ({cp})<br>{nb} lavage(s)",
                    "style": {
                        "background": "#faf9f7",
                        "color": "#1c1a17",
                        "font-size": "13px",
                        "padding": "8px",
                        "border": "1px solid #d4cfc8",
                        "border-radius": "2px",
                    }
                }

                deck = pdk.Deck(
                    layers=layers,
                    initial_view_state=view,
                    tooltip=tooltip,
                    map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                )
                st.pydeck_chart(deck)
                st.caption("● Stations de lavage (bleu slate)   ● Localité de déchargement (rouge)")

            except ImportError:
                st.map(df_geo.rename(columns={"lat": "latitude", "lon": "longitude"}))

            with st.expander("Stations géocodées"):
                st.dataframe(df_geo[["nom", "localite", "cp", "nb", "lat", "lon"]], hide_index=True)

# ── Tab Missions ──────────────────────────────────────────────────────────────
with tab_missions:
    st.markdown('<div class="section-title">Missions vers cette localité</div>', unsafe_allow_html=True)

    cols_m = [c for c in [
        "N° Dossier", "Date chargement", "Localité chargement", "C.P. chargement",
        "Pays chargement", "Localité déchargement", "C.P. déchargement",
        "Produit", "Client facturation", "Prix transport", "Total des ventes"
    ] if c in df_missions_filtre.columns]

    st.dataframe(
        df_missions_filtre[cols_m].sort_values("Date chargement", ascending=False)
        if "Date chargement" in df_missions_filtre.columns
        else df_missions_filtre[cols_m],
        use_container_width=True,
        hide_index=True
    )

# ── Tab Stats ─────────────────────────────────────────────────────────────────
with tab_stats:
    st.markdown('<div class="section-title">Analyse des lavages</div>', unsafe_allow_html=True)

    if df_lavages_match.empty:
        st.info("Pas de données pour les statistiques.")
    else:
        station_counts_stats = (
            df_lavages_match
            .groupby(["Nom 1", "Localité", "Code postal"])
            .size()
            .reset_index(name="Nb lavages")
            .sort_values("Nb lavages", ascending=False)
        )

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.markdown("**Répartition par station**")
            st.bar_chart(station_counts_stats.set_index("Nom 1")["Nb lavages"].head(10))
        with col_s2:
            st.markdown("**Produits transportés**")
            prod_counts = df_missions_filtre["Produit"].value_counts().head(10)
            st.bar_chart(prod_counts)

        if "Chauffeur" in df_lavages_match.columns:
            st.markdown("**Top chauffeurs (lavages)**")
            chauf = df_lavages_match["Chauffeur"].value_counts().head(10).reset_index()
            chauf.columns = ["Chauffeur", "Nb lavages"]
            st.dataframe(chauf, hide_index=True, use_container_width=True)

        if "Date" in df_lavages_match.columns:
            st.markdown("**Évolution mensuelle des lavages**")
            df_tmp = df_lavages_match.copy()
            df_tmp["Mois"] = pd.to_datetime(df_tmp["Date"], errors="coerce").dt.to_period("M").astype(str)
            monthly = df_tmp.groupby("Mois").size().reset_index(name="Nb lavages")
            st.bar_chart(monthly.set_index("Mois"))
