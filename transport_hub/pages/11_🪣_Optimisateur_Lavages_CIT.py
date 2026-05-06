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
[data-testid="stAppViewContainer"] { background: #0e1b28; }
[data-testid="stSidebar"] { background: #0a1520; }
h1, h2, h3, .stMarkdown { color: #e8f4fd; }

.kpi-box {
    background: linear-gradient(145deg, #152a3e, #0e1b28);
    border: 1px solid rgba(74,144,217,0.2);
    border-radius: 12px;
    padding: 1rem 1.2rem;
    text-align: center;
    margin-bottom: 0.5rem;
}
.kpi-box .kpi-val { font-size: 1.9rem; font-weight: 700; color: #4a90d9; }
.kpi-box .kpi-lbl { font-size: 0.78rem; color: #8aa4bc; text-transform: uppercase; letter-spacing: 1px; }

.lavage-card {
    background: #152a3e;
    border: 1px solid rgba(74,144,217,0.15);
    border-left: 3px solid #4a90d9;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.5rem;
    font-size: 0.88rem;
    color: #cde;
}
.lavage-card .station { font-weight: 600; color: #6bb8f0; font-size: 0.95rem; }
.lavage-card .meta { color: #8aa4bc; font-size: 0.8rem; }

.section-title {
    color: #e8f4fd;
    font-size: 1.1rem;
    font-weight: 600;
    border-bottom: 1px solid rgba(74,144,217,0.2);
    padding-bottom: 0.4rem;
    margin: 1.2rem 0 0.8rem 0;
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

    # Nettoyage colonnes
    df_m.columns = df_m.columns.str.strip()
    df_l.columns = df_l.columns.str.strip()

    # Nettoyage N° Dossier
    df_m["N° Dossier"] = df_m["N° Dossier"].str.strip()
    df_l["N° Dossier"] = df_l["N° Dossier"].str.strip()

    # Parsing dates
    if "Date chargement" in df_m.columns:
        df_m["Date chargement"] = pd.to_datetime(df_m["Date chargement"], errors="coerce")
    if "Date" in df_l.columns:
        df_l["Date"] = pd.to_datetime(df_l["Date"], errors="coerce")

    # Déduire le pays du lavage depuis le code postal
    # CP 4 chiffres = NL ou BE, 5 chiffres = FR/DE/etc.
    def detect_pays_lavage(cp):
        cp = str(cp).strip()
        if len(cp) == 4 and cp.isdigit():
            return "NL/BE"
        elif len(cp) == 5 and cp.isdigit():
            return "FR/DE/ES"
        return "Autre"
    df_l["_pays_lavage"] = df_l["Code postal"].apply(detect_pays_lavage)

    # Normalisation localité pour recherche
    df_m["_localite_norm"] = df_m["Localité déchargement"].apply(normalize)
    df_l["_localite_lavage_norm"] = df_l["Localité"].apply(normalize)

    return df_m, df_l

# ─── Géocodage (Photon/Komoot en priorité, fallback Nominatim) ───────────────
import urllib.request as _ureq
import urllib.parse as _uparse
import json as _json

def _photon_call(query: str):
    """Photon (Komoot) — OSM, sans clé, fonctionne sur Streamlit Cloud."""
    url = f"https://photon.komoot.io/api/?q={_uparse.quote(query)}&limit=1&lang=fr"
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
    """Nominatim fallback."""
    url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={_uparse.quote(query)}&format=json&limit=1"
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

def _geocode_raw(query: str):
    """Essaie Photon puis Nominatim."""
    result = _photon_call(query)
    if result:
        return result
    return _nominatim_call(query)

@st.cache_data(show_spinner=False, ttl=86400)
def geocode_location(query: str):
    """Géocode une station — résultat mis en cache."""
    return _geocode_raw(query)

def geocode_dest(query: str):
    """Géocode la destination — sans cache pour ne pas bloquer sur None."""
    return _geocode_raw(query)

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
with st.spinner("⏳ Chargement et croisement des données..."):
    try:
        df_m, df_l = load_data(missions_file.read(), lavages_file.read())
    except Exception as e:
        st.error(f"❌ Erreur chargement : {e}")
        st.stop()

# ─── KPIs globaux ────────────────────────────────────────────────────────────
total_missions = len(df_m)
total_lavages  = len(df_l)
dossiers_avec_lavage = len(set(df_m["N° Dossier"]) & set(df_l["N° Dossier"]))
nb_localites = df_m["Localité déchargement"].nunique()

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
st.markdown('<div class="section-title">🔍 Recherche par localité de déchargement</div>', unsafe_allow_html=True)

# Autocomplete : liste triée des localités
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

# Filtre produit optionnel
with st.expander("🎛️ Filtres avancés", expanded=False):
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

col_f4, _ = st.columns([2, 2])
with col_f4:
    pays_lavage_opts = ["Tous"] + sorted(df_l["_pays_lavage"].dropna().unique().tolist())
    pays_lavage_filter = st.selectbox(
        "🌍 Filtrer lavages par zone géographique",
        pays_lavage_opts,
        help="NL/BE = Pays-Bas/Belgique (CP 4 chiffres) | FR/DE/ES = France/Allemagne (CP 5 chiffres)"
    )

if not query:
    st.info("👆 Sélectionnez ou tapez une localité de déchargement pour voir les lavages associés")
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
    st.warning(f"⚠️ Aucune mission trouvée pour « {query} »")
    st.stop()

# ─── Croisement avec lavages ──────────────────────────────────────────────────
dossiers_ids = df_missions_filtre["N° Dossier"].unique()
df_lavages_raw = df_l[df_l["N° Dossier"].isin(dossiers_ids)].copy()

# Joindre les infos mission pour calculer le timing du lavage
df_lavages_raw = df_lavages_raw.merge(
    df_missions_filtre[["N° Dossier", "Date chargement",
                         "Pays chargement", "Pays déchargement",
                         "C.P. chargement", "C.P. déchargement"]],
    on="N° Dossier", how="left"
)

# Classifier chaque lavage : avant ou après déchargement
# Logique : CP 4 chiffres du lavage = zone NL/BE
#           Si pays chargement = NL/BE et lavage en NL/BE → avant déchargement
#           Sinon → après déchargement (lavage proche du lieu de livraison)
def classify_lavage(row):
    cp_lav = str(row.get("Code postal", "") or "").strip()
    pays_ch = str(row.get("Pays chargement", "") or "").strip().upper()
    pays_dech = str(row.get("Pays déchargement", "") or "").strip().upper()

    # CP 4 chiffres = zone NL/BE
    lav_zone_nl_be = len(cp_lav) == 4 and cp_lav.isdigit()
    # Chargement en NL/BE
    ch_nl_be = pays_ch in ("NL", "B", "BE")

    if lav_zone_nl_be and ch_nl_be:
        return "avant"   # lavage en transit avant livraison
    elif not lav_zone_nl_be and not ch_nl_be:
        return "apres"   # lavage après livraison, zone cohérente
    elif lav_zone_nl_be and not ch_nl_be:
        return "avant"   # lavage en zone nord alors que chargement au sud → avant
    else:
        return "apres"   # lavage en zone sud alors que chargement au nord → après livraison

df_lavages_raw["timing"] = df_lavages_raw.apply(classify_lavage, axis=1)
df_lavages_raw = df_lavages_raw.drop(
    columns=["Date chargement", "Pays chargement", "Pays déchargement",
             "C.P. chargement", "C.P. déchargement"],
    errors="ignore"
)

df_lavages_match = df_lavages_raw.copy()

# ─── Résultats ───────────────────────────────────────────────────────────────
st.markdown(f"### 📍 Résultats pour : **{query}**")

r1, r2, r3 = st.columns(3)
with r1:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{len(df_missions_filtre)}</div><div class="kpi-lbl">Missions trouvées</div></div>', unsafe_allow_html=True)
with r2:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{len(df_lavages_match)}</div><div class="kpi-lbl">Lavages associés</div></div>', unsafe_allow_html=True)
with r3:
    nb_stations = df_lavages_match["Nom 1"].nunique()
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{nb_stations}</div><div class="kpi-lbl">Stations distinctes</div></div>', unsafe_allow_html=True)

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_lavages, tab_carte, tab_missions, tab_stats = st.tabs([
    "🧼 Lavages", "🗺️ Carte", "📋 Missions", "📊 Statistiques"
])

# ── Tab Lavages ───────────────────────────────────────────────────────────────
with tab_lavages:
    if df_lavages_match.empty:
        st.info("Aucun lavage enregistré pour ces dossiers.")
    else:
        # Résumé par station
        st.markdown('<div class="section-title">🏆 Stations les plus utilisées</div>', unsafe_allow_html=True)
        station_counts = df_lavages_match.groupby(["Nom 1", "Localité", "Code postal"]).size().reset_index(name="Nb lavages")
        station_counts = station_counts.sort_values("Nb lavages", ascending=False)

        for _, row in station_counts.head(10).iterrows():
            pct = int(row["Nb lavages"] / len(df_lavages_match) * 100)
            st.markdown(f"""
            <div class="lavage-card">
                <div class="station">🏭 {row['Nom 1']}</div>
                <div>📍 {row['Localité']} ({row['Code postal']})</div>
                <div class="meta">✅ {row['Nb lavages']} lavage(s) — {pct}% du total</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">📄 Détail des lavages</div>', unsafe_allow_html=True)

        # Merge pour avoir le contexte mission
        # On sélectionne uniquement les colonnes utiles côté missions, sans "Chauffeur"
        # (déjà présent dans df_lavages_match) pour éviter les conflits de colonnes dupliquées
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
            df_detail[cols_show].sort_values("Date", ascending=False) if "Date" in df_detail.columns else df_detail[cols_show],
            use_container_width=True,
            hide_index=True,
        )

        # Export
        import io as _io
        buf = _io.BytesIO()
        df_detail[cols_show].to_excel(buf, index=False, engine="openpyxl")
        st.download_button(
            "📥 Exporter les lavages (Excel)",
            data=buf.getvalue(),
            file_name=f"lavages_{normalize(query).replace(' ','_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ── Tab Carte ─────────────────────────────────────────────────────────────────
with tab_carte:
    st.markdown('<div class="section-title">🗺️ Carte des stations de lavage</div>', unsafe_allow_html=True)

    if df_lavages_match.empty:
        st.info("Aucun lavage à afficher sur la carte.")
    else:
        # Filtre avant/après déchargement
        col_toggle1, col_toggle2, _ = st.columns([1, 1, 3])
        with col_toggle1:
            show_avant = st.checkbox("🟢 Lavages avant déchargement", value=True,
                help="Lavages effectués en transit, avant livraison (ex: NL → FR)")
        with col_toggle2:
            show_apres = st.checkbox("🔵 Lavages après déchargement", value=True,
                help="Lavages effectués après livraison, à proximité du lieu de déchargement")

        df_carte = df_lavages_match.copy()
        if not show_avant:
            df_carte = df_carte[df_carte["timing"] != "avant"]
        if not show_apres:
            df_carte = df_carte[df_carte["timing"] != "apres"]

        # Géocoder les stations filtrées
        stations_unique = df_carte.groupby(["Nom 1","Localité","Code postal","timing"]).size().reset_index(name="Nb lavages")

        geocoded = []
        progress_bar = st.progress(0, text="Géocodage des stations...")
        total_s = len(stations_unique)

        for i, (_, row) in enumerate(stations_unique.iterrows()):
            search_q = f"{row['Nom 1']}, {row['Localité']}, {row['Code postal']}"
            coords = geocode_location(search_q)
            if coords is None:
                coords = geocode_location(f"{row['Localité']}, {row['Code postal']}")
            if coords:
                timing = row.get("timing", "apres")
                geocoded.append({
                    "nom": row["Nom 1"],
                    "localite": row["Localité"],
                    "cp": row["Code postal"],
                    "nb": int(row["Nb lavages"]),
                    "timing": timing,
                    "lat": coords[0],
                    "lon": coords[1],
                })
            progress_bar.progress((i + 1) / total_s, text=f"Géocodage {i+1}/{total_s}")

        progress_bar.empty()

        if not geocoded:
            st.warning("Impossible de géocoder les stations pour cette localité.")
        else:
            df_geo = pd.DataFrame(geocoded)

            # Géocoder la localité de déchargement cible
            # On récupère le pays réel depuis les missions filtrées
            pays_dech = df_missions_filtre["Pays déchargement"].dropna().mode()
            pays_dech_str = pays_dech.iloc[0].strip() if not pays_dech.empty else ""

            PAYS_MAP_GEO = {
                "F": "France", "B": "Belgium", "BE": "Belgium",
                "D": "Germany", "NL": "Netherlands", "L": "Luxembourg",
                "E": "Spain", "I": "Italy", "GB": "United Kingdom",
                "CH": "Switzerland", "A": "Austria", "PL": "Poland",
                "CZ": "Czech Republic", "SK": "Slovakia", "H": "Hungary",
            }
            pays_label = PAYS_MAP_GEO.get(pays_dech_str.upper(), pays_dech_str)

            cp_dech = df_missions_filtre["C.P. déchargement"].dropna().mode()
            cp_str = cp_dech.iloc[0].strip() if not cp_dech.empty else ""

            # Normalisation du nom : ST → SAINT, STE → SAINTE
            import re as _re
            query_expanded = _re.sub(r'\bST\b', 'SAINT', query, flags=_re.IGNORECASE)
            query_expanded = _re.sub(r'\bSTE\b', 'SAINTE', query_expanded, flags=_re.IGNORECASE)

            # Tentatives de géocodage par ordre de précision
            dest_coords = None
            attempts = []
            for q in ([query_expanded, query] if query_expanded != query else [query]):
                if cp_str and pays_label:
                    attempts.append(f"{q}, {cp_str}, {pays_label}")
                if pays_label:
                    attempts.append(f"{q}, {pays_label}")
                attempts.append(q)

            debug_results = []
            for attempt in attempts:
                dest_coords = geocode_dest(attempt)
                debug_results.append((attempt, dest_coords))
                if dest_coords:
                    break

            with st.expander("🔧 Debug géocodage destination", expanded=dest_coords is None):
                for att, res in debug_results:
                    icon = "✅" if res else "❌"
                    st.write(f"{icon} `{att}` → `{res}`")
                if dest_coords is None:
                    st.error("Toutes les tentatives ont échoué — Nominatim ne reconnaît pas cette localité.")

            # Carte MapLibre via st.map (fallback simple)
            # Utiliser pydeck pour une carte plus riche
            try:
                import pydeck as pdk

                # Séparer les deux catégories
                df_apres = df_geo[df_geo["timing"] == "apres"].copy() if not df_geo.empty else pd.DataFrame()
                df_avant = df_geo[df_geo["timing"] == "avant"].copy() if not df_geo.empty else pd.DataFrame()

                layers = []

                # Layer lavages APRÈS déchargement (bleu)
                if not df_apres.empty:
                    layers.append(pdk.Layer(
                        "ScatterplotLayer", data=df_apres,
                        get_position="[lon, lat]", get_radius=5000,
                        get_fill_color=[74, 144, 217, 220],
                        get_line_color=[255, 255, 255, 180],
                        stroked=True, line_width_min_pixels=1,
                        pickable=True, auto_highlight=True,
                    ))
                    layers.append(pdk.Layer(
                        "TextLayer", data=df_apres,
                        get_position="[lon, lat]", get_text="nom",
                        get_size=12, get_color=[180, 220, 255, 220],
                        get_anchor="middle", get_alignment_baseline="'bottom'",
                        get_pixel_offset=[0, -10],
                    ))

                # Layer lavages AVANT déchargement (vert)
                if not df_avant.empty:
                    layers.append(pdk.Layer(
                        "ScatterplotLayer", data=df_avant,
                        get_position="[lon, lat]", get_radius=5000,
                        get_fill_color=[46, 184, 92, 220],
                        get_line_color=[255, 255, 255, 180],
                        stroked=True, line_width_min_pixels=1,
                        pickable=True, auto_highlight=True,
                    ))
                    layers.append(pdk.Layer(
                        "TextLayer", data=df_avant,
                        get_position="[lon, lat]", get_text="nom",
                        get_size=12, get_color=[160, 255, 180, 220],
                        get_anchor="middle", get_alignment_baseline="'bottom'",
                        get_pixel_offset=[0, -10],
                    ))

                # Layer point déchargement (rouge vif + contour blanc + label)
                if dest_coords:
                    df_dest = pd.DataFrame([{
                        "lat": dest_coords[0],
                        "lon": dest_coords[1],
                        "nom": f"Déchargement : {query}",
                        "label": query.upper(),
                    }])
                    layer_dest = pdk.Layer(
                        "ScatterplotLayer",
                        data=df_dest,
                        get_position="[lon, lat]",
                        get_radius=10000,
                        get_fill_color=[220, 30, 30, 240],
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
                        get_size=14,
                        get_color=[255, 80, 80, 255],
                        get_anchor="middle",
                        get_alignment_baseline="'bottom'",
                        get_pixel_offset=[0, -14],
                        font_weight=800,
                    )
                    layers.append(layer_dest)
                    layers.append(layer_dest_text)

                if dest_coords is None:
                    st.warning(f"⚠️ Point de déchargement non géocodé pour « {query} » — seules les stations de lavage sont affichées.")

                center_lat = dest_coords[0] if dest_coords else df_geo["lat"].mean()
                center_lon = dest_coords[1] if dest_coords else df_geo["lon"].mean()

                view = pdk.ViewState(
                    latitude=center_lat,
                    longitude=center_lon,
                    zoom=5,
                    pitch=0,
                )

                tooltip = {
                    "html": "<b>{nom}</b><br>{localite} ({cp})<br>🧼 {nb} lavage(s)",
                    "style": {"background": "#0e1b28", "color": "#e8f4fd", "font-size": "13px", "padding": "8px"}
                }

                deck = pdk.Deck(
                    layers=layers,
                    initial_view_state=view,
                    tooltip=tooltip,
                    map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
                )
                st.pydeck_chart(deck, use_container_width=True, height=600)

                # Légende
                st.markdown("""
                <small>
                🔵 Lavage après déchargement &nbsp;|&nbsp;
                🟢 Lavage avant chargement (en transit) &nbsp;|&nbsp;
                🔴 Localité de déchargement
                </small>
                """, unsafe_allow_html=True)

                # Bouton plein écran via page dédiée
                map_params = urllib.parse.urlencode({"localite": query})
                st.markdown(
                    f'<a href="/12_Carte_Lavage?{map_params}" target="_blank">'
                    f'<button style="margin-top:0.5rem;padding:0.4rem 1rem;background:#4a90d9;'
                    f'color:white;border:none;border-radius:6px;cursor:pointer;font-size:0.85rem;">'
                    f'🗺️ Ouvrir la carte en plein écran</button></a>',
                    unsafe_allow_html=True,
                )

            except ImportError:
                # Fallback st.map
                st.map(df_geo.rename(columns={"lat": "latitude", "lon": "longitude"}))

            # Tableau récapitulatif géocodé
            with st.expander("📋 Stations géocodées"):
                st.dataframe(df_geo[["nom","localite","cp","nb","lat","lon"]], hide_index=True)

# ── Tab Missions ──────────────────────────────────────────────────────────────
with tab_missions:
    st.markdown('<div class="section-title">📋 Missions vers cette localité</div>', unsafe_allow_html=True)

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
    st.markdown('<div class="section-title">📊 Analyse des lavages</div>', unsafe_allow_html=True)

    if df_lavages_match.empty:
        st.info("Pas de données pour les statistiques.")
    else:
        col_s1, col_s2 = st.columns(2)

        with col_s1:
            st.markdown("**Répartition par station**")
            st.bar_chart(
                station_counts.set_index("Nom 1")["Nb lavages"].head(10)
            )

        with col_s2:
            st.markdown("**Produits transportés (missions concernées)**")
            prod_counts = df_missions_filtre["Produit"].value_counts().head(10)
            st.bar_chart(prod_counts)

        # Chauffeurs les plus actifs
        if "Chauffeur" in df_lavages_match.columns:
            st.markdown("**Top chauffeurs (lavages)**")
            chauf = df_lavages_match["Chauffeur"].value_counts().head(10).reset_index()
            chauf.columns = ["Chauffeur", "Nb lavages"]
            st.dataframe(chauf, hide_index=True, use_container_width=True)

        # Evol temporelle par station
        if "Date" in df_lavages_match.columns:
            st.markdown("**Évolution mensuelle des lavages**")

            # Sélecteur station
            stations_dispo = ["Toutes les stations"] + sorted(
                df_lavages_match["Nom 1"].dropna().unique().tolist()
            )
            station_sel = st.selectbox("📍 Choisir une station", stations_dispo, key="stat_station")

            df_tmp = df_lavages_match.copy()
            if station_sel != "Toutes les stations":
                df_tmp = df_tmp[df_tmp["Nom 1"] == station_sel]

            df_tmp["Mois"] = pd.to_datetime(df_tmp["Date"], errors="coerce").dt.to_period("M").astype(str)
            monthly = df_tmp.groupby("Mois").size().reset_index(name="Nb lavages")
            st.bar_chart(monthly.set_index("Mois"))

            # KPI station sélectionnée
            if station_sel != "Toutes les stations" and not df_tmp.empty:
                pct_total = len(df_tmp) / len(df_lavages_match) * 100
                avg_month = len(df_tmp) / max(monthly["Mois"].nunique(), 1)
                sc1, sc2, sc3 = st.columns(3)
                sc1.metric("Total lavages", len(df_tmp))
                sc2.metric("% du total", f"{pct_total:.1f}%")
                sc3.metric("Moy / mois", f"{avg_month:.1f}")
