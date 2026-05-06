"""
Page Streamlit : Optimisateur Trajets Vides CIT
Je viens de décharger en X → quels sont les meilleurs endroits pour aller recharger ?
Score = fréquence historique × prix moyen × (1 / distance estimée)
"""

import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import re
import math

st.set_page_config(
    page_title="Optimisateur Trajets Vides",
    page_icon="🚛",
    layout="wide",
)

# ─── Style ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

[data-testid="stAppViewContainer"] { background: #080e14; }
[data-testid="stSidebar"] { background: #060b10; }
* { font-family: 'IBM Plex Sans', sans-serif; }

.hero {
    background: linear-gradient(135deg, #0d1f2d 0%, #080e14 60%);
    border: 1px solid rgba(0,255,136,0.15);
    border-radius: 16px;
    padding: 1.8rem 2rem;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: '';
    position: absolute;
    top: -50%; left: -10%;
    width: 300px; height: 300px;
    background: radial-gradient(circle, rgba(0,255,136,0.04) 0%, transparent 70%);
    pointer-events: none;
}
.hero h1 {
    font-family: 'IBM Plex Mono', monospace;
    color: #00ff88;
    font-size: 1.6rem;
    margin: 0 0 0.3rem 0;
    letter-spacing: -0.5px;
}
.hero p { color: #5a8a6a; font-size: 0.88rem; margin: 0; }

.kpi-card {
    background: #0d1a24;
    border: 1px solid rgba(0,255,136,0.1);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    text-align: center;
}
.kpi-card .val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.8rem;
    font-weight: 600;
    color: #00ff88;
}
.kpi-card .lbl {
    font-size: 0.72rem;
    color: #3d6b52;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-top: 2px;
}

.reco-card {
    background: #0d1a24;
    border: 1px solid rgba(0,255,136,0.08);
    border-radius: 12px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.6rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    transition: border-color 0.2s;
    position: relative;
}
.reco-card.top1 { border-color: rgba(0,255,136,0.4); background: #0d2219; }
.reco-card.top2 { border-color: rgba(0,200,100,0.25); }
.reco-card.top3 { border-color: rgba(0,160,80,0.2); }

.reco-rank {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.4rem;
    font-weight: 600;
    color: #00ff88;
    min-width: 2rem;
    text-align: center;
}
.reco-rank.dim { color: #1e4a30; }

.reco-body { flex: 1; }
.reco-loc {
    font-size: 1rem;
    font-weight: 600;
    color: #e0ffe8;
    font-family: 'IBM Plex Mono', monospace;
    letter-spacing: 0.3px;
}
.reco-pays { font-size: 0.78rem; color: #3d6b52; margin-top: 1px; }

.reco-metrics {
    display: flex;
    gap: 1.2rem;
    margin-top: 0.5rem;
    flex-wrap: wrap;
}
.metric-chip {
    background: rgba(0,255,136,0.05);
    border: 1px solid rgba(0,255,136,0.1);
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.75rem;
    color: #5abf7a;
    font-family: 'IBM Plex Mono', monospace;
}
.metric-chip.green { color: #00ff88; border-color: rgba(0,255,136,0.25); }
.metric-chip.orange { color: #ffaa44; border-color: rgba(255,170,68,0.25); background: rgba(255,170,68,0.05); }
.metric-chip.blue { color: #44aaff; border-color: rgba(68,170,255,0.25); background: rgba(68,170,255,0.05); }

.score-bar-bg {
    background: #0a1a12;
    border-radius: 3px;
    height: 4px;
    margin-top: 0.4rem;
    overflow: hidden;
}
.score-bar {
    height: 100%;
    border-radius: 3px;
    background: linear-gradient(90deg, #00ff88, #00cc66);
    transition: width 0.5s ease;
}

.section-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #3d6b52;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin: 1.5rem 0 0.8rem 0;
    border-bottom: 1px solid rgba(0,255,136,0.08);
    padding-bottom: 0.4rem;
}

.badge-optimal {
    position: absolute;
    top: 0.7rem; right: 0.8rem;
    background: #00ff88;
    color: #080e14;
    font-size: 0.65rem;
    font-weight: 700;
    font-family: 'IBM Plex Mono', monospace;
    padding: 2px 8px;
    border-radius: 20px;
    letter-spacing: 1px;
}

.search-box input {
    background: #0d1a24 !important;
    border: 1px solid rgba(0,255,136,0.2) !important;
    color: #e0ffe8 !important;
    font-family: 'IBM Plex Mono', monospace !important;
}
</style>
""", unsafe_allow_html=True)

# ─── Utilitaires ─────────────────────────────────────────────────────────────
def normalize(text: str) -> str:
    if not text:
        return ""
    text = str(text).upper().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"['\-–]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def haversine_km(lat1, lon1, lat2, lon2):
    """Distance à vol d'oiseau en km."""
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

# ─── Géocodage ───────────────────────────────────────────────────────────────
import urllib.request as _ureq
import urllib.parse as _uparse
import json as _json

def _photon(query: str):
    url = f"https://photon.komoot.io/api/?q={_uparse.quote(query)}&limit=1&lang=fr"
    try:
        req = _ureq.Request(url, headers={"User-Agent": "CB-Transport-Hub/1.0"})
        with _ureq.urlopen(req, timeout=5) as r:
            data = _json.loads(r.read())
        ft = data.get("features", [])
        if ft:
            c = ft[0]["geometry"]["coordinates"]
            return float(c[1]), float(c[0])
    except Exception:
        pass
    return None

def _nominatim(query: str):
    url = f"https://nominatim.openstreetmap.org/search?q={_uparse.quote(query)}&format=json&limit=1"
    try:
        req = _ureq.Request(url, headers={"User-Agent": "CB-Transport-Hub/1.0"})
        with _ureq.urlopen(req, timeout=5) as r:
            data = _json.loads(r.read())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None

@st.cache_data(show_spinner=False, ttl=86400)
def geocode(query: str):
    return _photon(query) or _nominatim(query)

def geocode_ville(ville: str, cp: str = "", pays: str = "") -> tuple:
    PAYS_MAP = {"F":"France","B":"Belgium","BE":"Belgium","NL":"Netherlands",
                "D":"Germany","L":"Luxembourg","E":"Spain","I":"Italy",
                "CH":"Switzerland","A":"Austria","GB":"United Kingdom"}
    pays_label = PAYS_MAP.get(pays.upper(), pays)
    ville_exp = re.sub(r'\bST\b', 'SAINT', ville, flags=re.IGNORECASE)
    ville_exp = re.sub(r'\bSTE\b', 'SAINTE', ville_exp, flags=re.IGNORECASE)
    for v in ([ville_exp, ville] if ville_exp != ville else [ville]):
        for q in filter(None, [
            f"{v}, {cp}, {pays_label}" if cp and pays_label else None,
            f"{v}, {pays_label}" if pays_label else None,
            v,
        ]):
            r = geocode(q)
            if r:
                return r
    return None

# ─── Chargement données ───────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_missions(missions_bytes, lavages_bytes):
    """Charge missions + joint Remorque/Tracteur/Chauffeur depuis lavages pour chaîner par véhicule."""
    import io
    df = pd.read_excel(io.BytesIO(missions_bytes), dtype=str)
    df.columns = df.columns.str.strip()
    df["Date chargement"] = pd.to_datetime(df["Date chargement"], errors="coerce")
    df["Prix transport"] = pd.to_numeric(df["Prix transport"], errors="coerce")
    df["Total des ventes"] = pd.to_numeric(df["Total des ventes"], errors="coerce")
    df["N° Dossier"] = df["N° Dossier"].str.strip()

    # Joindre les IDs véhicule depuis le fichier lavages
    df_l = pd.read_excel(io.BytesIO(lavages_bytes), dtype=str)
    df_l.columns = df_l.columns.str.strip()
    df_l["N° Dossier"] = df_l["N° Dossier"].str.strip()
    vehicule = df_l[["N° Dossier","Remorque","Tracteur","Chauffeur"]].drop_duplicates("N° Dossier")
    df = df.merge(vehicule, on="N° Dossier", how="left")

    df["_loc_ch_norm"] = df["Localité chargement"].apply(normalize)
    df["_loc_dech_norm"] = df["Localité déchargement"].apply(normalize)
    df = df.dropna(subset=["Date chargement"]).sort_values("Date chargement").reset_index(drop=True)
    return df


# ─── Header ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
    <h1>🚛 OPTIMISATEUR TRAJETS VIDES</h1>
    <p>Je viens de décharger en X — où aller recharger pour maximiser l'efficacité ?</p>
</div>
""", unsafe_allow_html=True)

# ─── Upload ───────────────────────────────────────────────────────────────────
col_u1, col_u2 = st.columns(2)
with col_u1:
    missions_file = st.file_uploader(
        "📋 Fichier Missions CA CIT",
        type=["xlsx","xls"],
        help="Fichier CA_CIT_25-ajd"
    )
with col_u2:
    lavages_file = st.file_uploader(
        "🧼 Fichier Lavages",
        type=["xlsx","xls"],
        help="Fichier liste_lavages — permet de chaîner les missions par véhicule (Remorque/Tracteur)"
    )

if not missions_file:
    st.info("👆 Chargez le fichier missions pour démarrer")
    st.stop()

missions_bytes = missions_file.read()
lavages_bytes  = lavages_file.read() if lavages_file else None

if lavages_bytes is None:
    st.warning("⚠️ Sans le fichier lavages, les recommandations seront moins précises (pas de chaînage par véhicule)")

with st.spinner("⏳ Chargement et analyse des enchaînements historiques..."):
    if lavages_bytes:
        df = load_missions(missions_bytes, lavages_bytes)
    else:
        import io as _io2
        df_tmp = pd.read_excel(_io2.BytesIO(missions_bytes), dtype=str)
        df_tmp.columns = df_tmp.columns.str.strip()
        df_tmp["Date chargement"] = pd.to_datetime(df_tmp["Date chargement"], errors="coerce")
        df_tmp["Prix transport"] = pd.to_numeric(df_tmp["Prix transport"], errors="coerce")
        df_tmp["Total des ventes"] = pd.to_numeric(df_tmp["Total des ventes"], errors="coerce")
        df_tmp["N° Dossier"] = df_tmp["N° Dossier"].str.strip()
        df_tmp["_loc_ch_norm"] = df_tmp["Localité chargement"].apply(normalize)
        df_tmp["_loc_dech_norm"] = df_tmp["Localité déchargement"].apply(normalize)
        df_tmp["Remorque"] = None
        df = df_tmp.dropna(subset=["Date chargement"]).sort_values("Date chargement").reset_index(drop=True)

# KPIs globaux
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f'<div class="kpi-card"><div class="val">{len(df):,}</div><div class="lbl">Missions</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="kpi-card"><div class="val">{df["Localité déchargement"].nunique():,}</div><div class="lbl">Lieux déchargement</div></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="kpi-card"><div class="val">{df["Localité chargement"].nunique():,}</div><div class="lbl">Lieux chargement</div></div>', unsafe_allow_html=True)
with c4:
    avg_prix = df["Prix transport"].mean()
    st.markdown(f'<div class="kpi-card"><div class="val">{avg_prix:,.0f}€</div><div class="lbl">Prix moyen mission</div></div>', unsafe_allow_html=True)

st.divider()

# ─── Recherche ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">📍 LIEU DE DÉCHARGEMENT</div>', unsafe_allow_html=True)

lieux_dech = sorted(df["Localité déchargement"].dropna().unique().tolist())

col_s1, col_s2, col_s3 = st.columns([3, 1, 1])
with col_s1:
    lieu_choisi = st.selectbox(
        "Je viens de décharger à...",
        [""] + lieux_dech,
        help="Sélectionnez ou tapez le lieu de déchargement"
    )
with col_s2:
    fenetre_jours = st.selectbox("Fenêtre max (jours)", [3, 7, 14], index=0,
        help="Nombre de jours max après déchargement pour trouver le prochain chargement du même véhicule")
with col_s3:
    nb_recos = st.selectbox("Nb recommandations", [5, 10, 15, 20], index=1)

with st.expander("🎛️ Filtres avancés"):
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        pays_filtre = st.multiselect("Pays de rechargement",
            options=sorted(df["Pays chargement"].dropna().unique().tolist()))
    with col_f2:
        prix_min = st.number_input("Prix min mission rechargement (€)", value=0, step=50)

if not lieu_choisi:
    st.info("👆 Choisissez un lieu de déchargement pour voir les recommandations")
    st.stop()

# ─── Calcul recommandations ───────────────────────────────────────────────────
loc_norm = normalize(lieu_choisi)

# Missions déchargeant en ce lieu — match exact normalisé
df_dech = df[df["_loc_dech_norm"] == loc_norm].copy()
if df_dech.empty:
    df_dech = df[df["_loc_dech_norm"].str.contains(loc_norm, na=False, regex=False)].copy()

if df_dech.empty:
    st.warning(f"Aucune mission trouvée pour « {lieu_choisi} »")
    st.stop()

# Pour chaque date de déchargement, trouver les chargements dans la fenêtre
with st.spinner(f"🔍 Analyse de {len(df_dech)} missions vers {lieu_choisi}..."):

    has_vehicle = df["Remorque"].notna().any()
    records = []

    for _, row in df_dech.iterrows():
        date_ref = row["Date chargement"]
        if pd.isna(date_ref):
            continue

        rem = row.get("Remorque")
        trac = row.get("Tracteur")

        if has_vehicle and pd.notna(rem) and rem:
            # ── Méthode précise : prochaine mission du même véhicule (Remorque) ──
            next_m = df[
                (df["Remorque"] == rem) &
                (df["Date chargement"] > date_ref) &
                (df["Date chargement"] <= date_ref + pd.Timedelta(days=fenetre_jours))
            ].head(1)
        else:
            # ── Fallback : fenêtre temporelle resserrée (J+1 seulement) ──
            next_day = df[
                (df["Date chargement"] > date_ref) &
                (df["Date chargement"] <= date_ref + pd.Timedelta(days=1))
            ]
            next_m = next_day.head(1) if not next_day.empty else pd.DataFrame()

        for _, nrow in next_m.iterrows():
            loc_ch = str(nrow["Localité chargement"] or "").strip()
            if not loc_ch or normalize(loc_ch) == loc_norm:
                continue
            prix = nrow["Prix transport"]
            if prix_min > 0 and (pd.isna(prix) or prix < prix_min):
                continue
            if pays_filtre and nrow["Pays chargement"] not in pays_filtre:
                continue
            records.append({
                "loc_ch":  loc_ch,
                "cp_ch":   str(nrow["C.P. chargement"] or "").strip(),
                "pays_ch": str(nrow["Pays chargement"] or "").strip(),
                "delta_j": (nrow["Date chargement"] - date_ref).days,
                "prix":    prix,
                "ventes":  nrow["Total des ventes"],
                "produit": str(nrow["Produit"] or "").strip(),
                "client":  str(nrow["Client facturation"] or "").strip(),
            })

    mode_label = "véhicule (Remorque)" if has_vehicle else "fenêtre temporelle J+1 (pas de fichier lavages)"
    st.caption(f"ℹ️ Chaînage par {mode_label} — {len(records)} enchaînements analysés")

if not records:
    st.warning("Pas d'enchaînements trouvés dans cette fenêtre temporelle.")
    st.stop()

df_rec = pd.DataFrame(records)

# Agrégation par lieu de chargement
agg = df_rec.groupby(["loc_ch","cp_ch","pays_ch"]).agg(
    frequence      = ("prix", "count"),
    prix_moyen     = ("prix", "mean"),
    ventes_moyennes= ("ventes", "mean"),
    delta_moyen    = ("delta_j", "mean"),
    prix_max       = ("prix", "max"),
).reset_index()

# Géocoder le lieu de déchargement pour calcul distance
cp_dech_ref  = df_dech["C.P. déchargement"].mode().iloc[0] if not df_dech["C.P. déchargement"].mode().empty else ""
pays_dech_ref = df_dech["Pays déchargement"].mode().iloc[0] if not df_dech["Pays déchargement"].mode().empty else ""

coords_dech = geocode_ville(lieu_choisi, cp_dech_ref, pays_dech_ref)

# Géocoder les destinations de rechargement (top 30 max pour perf)
top_candidates = agg.sort_values("frequence", ascending=False).head(30)

geocoded_ch = {}
with st.spinner("📡 Géocodage des lieux de rechargement..."):
    for _, row in top_candidates.iterrows():
        k = row["loc_ch"]
        if k not in geocoded_ch:
            coords = geocode_ville(row["loc_ch"], row["cp_ch"], row["pays_ch"])
            geocoded_ch[k] = coords

# Calcul score composite
def compute_score(row):
    freq   = row["frequence"]
    prix   = row["prix_moyen"] if not pd.isna(row["prix_moyen"]) else 0
    delta  = row["delta_moyen"] if row["delta_moyen"] > 0 else 0.5

    # Distance
    coords = geocoded_ch.get(row["loc_ch"])
    if coords and coords_dech:
        dist_km = haversine_km(coords_dech[0], coords_dech[1], coords[0], coords[1])
        dist_km = max(dist_km, 20)  # min 20km — évite score artificiel sur même zone
    else:
        dist_km = 500  # valeur neutre si non géocodé

    # Score : fréquence × prix × (1/distance) × (1/delta)
    # Normaliser prix sur base 1000€
    score = (freq * (prix / 1000) * (300 / dist_km) * (1 / delta))
    return score, dist_km

scores = []
dists  = []
for _, row in top_candidates.iterrows():
    s, d = compute_score(row)
    scores.append(s)
    dists.append(d)

top_candidates = top_candidates.copy()
top_candidates["score"]    = scores
top_candidates["dist_km"]  = dists
top_candidates = top_candidates.sort_values("score", ascending=False).head(nb_recos).reset_index(drop=True)

# Normaliser score pour barre visuelle
max_score = top_candidates["score"].max()
top_candidates["score_pct"] = (top_candidates["score"] / max_score * 100).round(0).astype(int)

# ─── Affichage recommandations ────────────────────────────────────────────────
st.markdown(f'<div class="section-label">🎯 RECOMMANDATIONS APRÈS DÉCHARGEMENT À {lieu_choisi.upper()}</div>', unsafe_allow_html=True)

nb_missions_dech = len(df_dech)
r1, r2, r3 = st.columns(3)
with r1:
    st.markdown(f'<div class="kpi-card"><div class="val">{nb_missions_dech}</div><div class="lbl">Missions historiques</div></div>', unsafe_allow_html=True)
with r2:
    st.markdown(f'<div class="kpi-card"><div class="val">{len(top_candidates)}</div><div class="lbl">Destinations proposées</div></div>', unsafe_allow_html=True)
with r3:
    best_prix = top_candidates.iloc[0]["prix_moyen"] if len(top_candidates) > 0 else 0
    st.markdown(f'<div class="kpi-card"><div class="val">{best_prix:,.0f}€</div><div class="lbl">Prix moyen #1</div></div>', unsafe_allow_html=True)

st.markdown("")

PAYS_FLAGS = {
    "F":"🇫🇷","B":"🇧🇪","BE":"🇧🇪","NL":"🇳🇱","D":"🇩🇪",
    "L":"🇱🇺","E":"🇪🇸","I":"🇮🇹","CH":"🇨🇭","A":"🇦🇹",
    "GB":"🇬🇧","PL":"🇵🇱",
}

for i, row in top_candidates.iterrows():
    rank = i + 1
    css_class = "top1" if rank == 1 else ("top2" if rank == 2 else ("top3" if rank == 3 else ""))
    rank_display = f"#{rank:02d}"
    flag = PAYS_FLAGS.get(row["pays_ch"], "🌍")
    dist_str = f"{row['dist_km']:.0f} km" if row['dist_km'] < 499 else "dist. inconnue"
    delta_str = f"J+{row['delta_moyen']:.1f}"
    prix_str  = f"{row['prix_moyen']:,.0f}€" if not pd.isna(row['prix_moyen']) else "N/A"
    freq_str  = f"{int(row['frequence'])}x"
    badge = '<span class="badge-optimal">OPTIMAL</span>' if rank == 1 else ""

    st.markdown(f"""
    <div class="reco-card {css_class}">
        <div class="reco-rank {'dim' if rank > 3 else ''}">{rank_display}</div>
        <div class="reco-body">
            <div class="reco-loc">{flag} {row['loc_ch']}</div>
            <div class="reco-pays">{row['cp_ch']} — {row['pays_ch']}</div>
            <div class="reco-metrics">
                <span class="metric-chip green">💶 {prix_str}</span>
                <span class="metric-chip blue">📏 {dist_str}</span>
                <span class="metric-chip">{delta_str} en moyenne</span>
                <span class="metric-chip orange">📊 {freq_str} dans l'historique</span>
            </div>
            <div class="score-bar-bg">
                <div class="score-bar" style="width:{row['score_pct']}%"></div>
            </div>
        </div>
        {badge}
    </div>
    """, unsafe_allow_html=True)

# ─── Carte ────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">🗺️ CARTE DES DESTINATIONS</div>', unsafe_allow_html=True)

map_data = []
for i, row in top_candidates.iterrows():
    coords = geocoded_ch.get(row["loc_ch"])
    if coords:
        map_data.append({
            "nom":   row["loc_ch"],
            "pays":  row["pays_ch"],
            "lat":   coords[0],
            "lon":   coords[1],
            "score": int(row["score_pct"]),
            "prix":  f"{row['prix_moyen']:,.0f}€" if not pd.isna(row['prix_moyen']) else "N/A",
            "freq":  int(row["frequence"]),
            "dist":  f"{row['dist_km']:.0f} km",
            "rang":  i + 1,
        })

if map_data:
    try:
        import pydeck as pdk

        df_map = pd.DataFrame(map_data)

        # Rayon fixe — tous les points à taille identique
        df_map["radius"] = 500
        df_map["color"] = df_map["rang"].apply(
            lambda r: [0, 255, 136, 230] if r == 1 else
                      ([0, 200, 100, 210] if r <= 3 else [0, 160, 80, 180])
        )

        layers = [
            pdk.Layer(
                "ScatterplotLayer", data=df_map,
                get_position="[lon, lat]",
                get_radius="radius",
                get_fill_color="color",
                get_line_color=[255, 255, 255, 100],
                stroked=True, line_width_min_pixels=1,
                pickable=True, auto_highlight=True,
            ),
            pdk.Layer(
                "TextLayer", data=df_map,
                get_position="[lon, lat]",
                get_text="nom",
                get_size=13,
                get_color=[220, 255, 230, 220],
                get_anchor="middle",
                get_alignment_baseline="'bottom'",
                get_pixel_offset=[0, -14],
            ),
        ]

        # Point de déchargement (rouge)
        if coords_dech:
            df_origin = pd.DataFrame([{
                "lat": coords_dech[0], "lon": coords_dech[1],
                "label": lieu_choisi.upper(), "nom": f"Déchargement : {lieu_choisi}",
            }])
            layers.append(pdk.Layer(
                "ScatterplotLayer", data=df_origin,
                get_position="[lon, lat]", get_radius=10000,
                get_fill_color=[220, 30, 30, 240],
                get_line_color=[255, 255, 255, 200],
                stroked=True, line_width_min_pixels=2, pickable=True,
            ))
            layers.append(pdk.Layer(
                "TextLayer", data=df_origin,
                get_position="[lon, lat]", get_text="label",
                get_size=14, get_color=[255, 80, 80, 255],
                get_anchor="middle", get_alignment_baseline="'bottom'",
                get_pixel_offset=[0, -16], font_weight=800,
            ))

        center_lat = coords_dech[0] if coords_dech else df_map["lat"].mean()
        center_lon = coords_dech[1] if coords_dech else df_map["lon"].mean()

        deck = pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(
                latitude=center_lat, longitude=center_lon, zoom=5, pitch=0),
            tooltip={
                "html": "<b>#{rang} — {nom}</b><br>💶 {prix} &nbsp;|&nbsp; 📏 {dist}<br>📊 {freq}x dans l'historique",
                "style": {"background": "#080e14", "color": "#00ff88",
                          "font-size": "13px", "padding": "10px",
                          "font-family": "IBM Plex Mono, monospace"}
            },
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        )

        st.pydeck_chart(deck, use_container_width=True, height=550)
        st.markdown(
            "<small style='color:#3d6b52'>🔴 Lieu de déchargement &nbsp;|&nbsp; "
            "🟢 Destinations recommandées (taille = score)</small>",
            unsafe_allow_html=True
        )

    except ImportError:
        st.map(pd.DataFrame(map_data).rename(columns={"lat":"latitude","lon":"longitude"}))

# ─── Tableau détail ───────────────────────────────────────────────────────────
with st.expander("📋 Tableau complet des recommandations"):
    df_display = top_candidates[["loc_ch","cp_ch","pays_ch","frequence",
                                  "prix_moyen","ventes_moyennes","delta_moyen",
                                  "dist_km","score_pct"]].copy()
    df_display.columns = ["Lieu chargement","CP","Pays","Fréquence hist.",
                           "Prix moyen (€)","Ventes moy. (€)","Délai moyen (j)",
                           "Distance (km)","Score (%)"]
    df_display["Prix moyen (€)"] = df_display["Prix moyen (€)"].round(0)
    df_display["Ventes moy. (€)"] = df_display["Ventes moy. (€)"].round(0)
    df_display["Délai moyen (j)"] = df_display["Délai moyen (j)"].round(1)
    df_display["Distance (km)"] = df_display["Distance (km)"].round(0)
    st.dataframe(df_display, hide_index=True, use_container_width=True)

    import io as _io
    buf = _io.BytesIO()
    df_display.to_excel(buf, index=False, engine="openpyxl")
    st.download_button(
        "📥 Exporter (Excel)",
        data=buf.getvalue(),
        file_name=f"recos_{normalize(lieu_choisi).replace(' ','_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ─── Analyse produits ─────────────────────────────────────────────────────────
with st.expander("🧪 Produits typiquement chargés après ce déchargement"):
    produits = df_rec.groupby("produit").agg(
        nb=("prix","count"),
        prix_moy=("prix","mean")
    ).sort_values("nb", ascending=False).head(15).reset_index()
    produits.columns = ["Produit","Nb missions","Prix moyen (€)"]
    produits["Prix moyen (€)"] = produits["Prix moyen (€)"].round(0)
    st.dataframe(produits, hide_index=True, use_container_width=True)
