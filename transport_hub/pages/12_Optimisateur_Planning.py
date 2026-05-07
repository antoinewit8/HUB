"""
Page Streamlit : Optimisateur Trajets Vides CIT
Je viens de décharger en X → quels sont les meilleurs endroits pour aller recharger ?
Score = fréquence historique × prix moyen × (1 / distance routière PTV) × (1 / délai)

Corrections v2 :
- Géocodage via PTV (géocodage par CP+pays prioritaire, fallback by-text)
- Date déchargement = Date chargement + 1j approximation (colonne manquante dans le fichier)
  → Si tu as une vraie colonne "Date déchargement", remplace DATE_DECH_COL ci-dessous
- Score distance : valeur neutre = médiane si non géocodé (plus de biais vers 500km)
- Déduplication reco par (remorque, trajet) : fréquence = nb trajets distincts
- Fenêtre weekend étendue : si déchargement vendredi/samedi, fenêtre +2j supplémentaires
- Mode "score manuel" : je tape ma propre destination, je vois le score vs historique
- Affichage chauffeur / remorque dans les détails
- Calcul distance routière PTV sur les top candidats (pas juste haversine)

v3 :
- Conseil IA (Claude API) si le lieu de déchargement est hors historique
"""

import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import re
import math
import os
import sys
import time
import json
import urllib.request as _ureq_ai

# ─── Import PTV (gestion imports relatifs du package) ────────────────────────
import importlib.util as _ilu
import types as _types

def _load_ptv(project_root: str):
    if "modules" not in sys.modules:
        pkg = _types.ModuleType("modules")
        pkg.__path__ = [project_root]
        pkg.__package__ = "modules"
        sys.modules["modules"] = pkg

    for mod_name, filename in [
        ("modules.route_optimizer", "route_optimizer.py"),
        ("modules.villes_jalons",   "villes_jalons.py"),
    ]:
        if mod_name not in sys.modules:
            path = os.path.join(project_root, filename)
            if os.path.exists(path):
                spec = _ilu.spec_from_file_location(mod_name, path)
                mod  = _ilu.module_from_spec(spec)
                mod.__package__ = "modules"
                sys.modules[mod_name] = mod
                try:
                    spec.loader.exec_module(mod)
                except Exception:
                    pass

    ptv_path = os.path.join(project_root, "ptv_router_km.py")
    if not os.path.exists(ptv_path):
        return None
    spec = _ilu.spec_from_file_location("modules.ptv_router_km", ptv_path)
    mod  = _ilu.module_from_spec(spec)
    mod.__package__ = "modules"
    sys.modules["modules.ptv_router_km"] = mod
    spec.loader.exec_module(mod)
    return mod

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOTS = [_HERE, os.path.dirname(_HERE)]

PTV_AVAILABLE = False
_ptv_mod = None
for _root in _ROOTS:
    if os.path.exists(os.path.join(_root, "ptv_router_km.py")):
        try:
            _ptv_mod = _load_ptv(_root)
            if _ptv_mod:
                PTV_AVAILABLE = True
                break
        except Exception:
            pass

if PTV_AVAILABLE and _ptv_mod:
    geocode_by_postal_code = _ptv_mod.geocode_by_postal_code
    _geocode_by_text       = _ptv_mod._geocode_by_text
    calculate_km_route     = _ptv_mod.calculate_km_route
    PAYS_TO_ISO            = _ptv_mod.PAYS_TO_ISO
    GPS_FIXES              = _ptv_mod.GPS_FIXES
else:
    PAYS_TO_ISO = {}
    GPS_FIXES   = {}

# ─── Config colonne date déchargement ────────────────────────────────────────
DATE_DECH_COL = None  # ex: "Date déchargement"

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Optimisateur Trajets Vides",
    page_icon="🚛",
    layout="wide",
)

# ─── Style ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700&family=Barlow:wght@300;400;500&display=swap');

[data-testid="stAppViewContainer"] { background: #0f1117; }
[data-testid="stSidebar"] { background: #090c12; }
* { font-family: 'Barlow', sans-serif; }

.hero {
    background: #141821;
    border: 1px solid #252b3b;
    border-radius: 8px;
    padding: 1.6rem 2rem;
    margin-bottom: 1.5rem;
}
.hero h1 {
    font-family: 'Barlow Condensed', sans-serif;
    color: #e8eaf0;
    font-size: 2rem;
    font-weight: 700;
    margin: 0 0 0.25rem 0;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.hero p { color: #5c6480; font-size: 0.9rem; margin: 0; }
.hero .badge-ptv {
    display: inline-block;
    background: #1a2e1a;
    border: 1px solid #2d5a2d;
    color: #5abf5a;
    font-size: 0.7rem;
    font-family: 'Barlow Condensed', sans-serif;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 2px 10px;
    border-radius: 3px;
    margin-top: 0.6rem;
}
.hero .badge-ptv.off {
    background: #2a1a1a;
    border-color: #5a2d2d;
    color: #bf5a5a;
}

.kpi-row { display: flex; gap: 1rem; margin-bottom: 1.2rem; }
.kpi {
    background: #141821;
    border: 1px solid #252b3b;
    border-radius: 6px;
    padding: 0.9rem 1.2rem;
    flex: 1;
}
.kpi .val {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 2rem;
    font-weight: 700;
    color: #c8cfe8;
    line-height: 1;
}
.kpi .lbl {
    font-size: 0.7rem;
    color: #3d4560;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-top: 4px;
}

.section-title {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.75rem;
    color: #3d4560;
    text-transform: uppercase;
    letter-spacing: 2.5px;
    margin: 1.8rem 0 0.8rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #1e2433;
}

.reco-wrap { display: flex; flex-direction: column; gap: 0.5rem; }

.reco {
    background: #141821;
    border: 1px solid #1e2433;
    border-radius: 6px;
    padding: 0.9rem 1.1rem;
    display: grid;
    grid-template-columns: 3rem 1fr auto;
    align-items: center;
    gap: 0.8rem;
}
.reco.r1 { border-color: #2d5a3d; background: #131d17; }
.reco.r2 { border-color: #253a2d; }
.reco.r3 { border-color: #1e2e25; }

.reco-num {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.6rem;
    font-weight: 700;
    color: #2a3050;
    text-align: center;
    line-height: 1;
}
.reco.r1 .reco-num { color: #4abf6a; }
.reco.r2 .reco-num { color: #3a8a52; }
.reco.r3 .reco-num { color: #2d6640; }

.reco-main {}
.reco-loc {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.15rem;
    font-weight: 600;
    color: #c8cfe8;
    letter-spacing: 0.3px;
    text-transform: uppercase;
}
.reco-sub { font-size: 0.78rem; color: #3d4560; margin-top: 2px; }

.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 0.5rem; }
.chip {
    font-size: 0.72rem;
    font-family: 'Barlow Condensed', sans-serif;
    font-weight: 600;
    letter-spacing: 0.5px;
    padding: 2px 9px;
    border-radius: 3px;
    border: 1px solid;
}
.chip.green  { color: #4abf6a; border-color: #2d5a3d; background: #111a14; }
.chip.blue   { color: #4a8abf; border-color: #1e3a5a; background: #11151a; }
.chip.gray   { color: #5c6480; border-color: #252b3b; background: #141821; }
.chip.orange { color: #bf8a4a; border-color: #5a3d1e; background: #1a1511; }
.chip.purple { color: #9a80d0; border-color: #3a2d5a; background: #141220; }

.score-track {
    width: 80px;
    height: 3px;
    background: #1e2433;
    border-radius: 2px;
    overflow: hidden;
    margin-top: 0.5rem;
}
.score-fill {
    height: 100%;
    border-radius: 2px;
    background: #4abf6a;
}

.badge-best {
    background: #4abf6a;
    color: #0a1410;
    font-size: 0.6rem;
    font-family: 'Barlow Condensed', sans-serif;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 2px 7px;
    border-radius: 2px;
    white-space: nowrap;
}

.ia-panel {
    background: #100f1a;
    border: 1px solid #2d2550;
    border-radius: 8px;
    padding: 1.4rem 1.6rem;
    margin: 0.5rem 0 1.5rem;
}
.ia-panel-title {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.1rem;
    font-weight: 700;
    color: #b8a8e8;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 0.4rem;
}
.ia-panel-sub {
    font-size: 0.85rem;
    color: #5c5080;
    line-height: 1.5;
}
.ia-result {
    background: #0e1518;
    border: 1px solid #1e3a2d;
    border-radius: 8px;
    padding: 1.4rem 1.6rem;
    margin-top: 0.8rem;
}
.ia-result-header {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.75rem;
    color: #3d5040;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #1e3a2d;
}
.proximity-title {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.75rem;
    color: #3d4560;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin: 1.5rem 0 0.6rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #1e2433;
}

.manual-score-box {
    background: #141821;
    border: 1px solid #252b3b;
    border-radius: 8px;
    padding: 1.4rem 1.6rem;
    margin-top: 1rem;
}
.manual-score-box h3 {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.2rem;
    font-weight: 700;
    color: #c8cfe8;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0 0 1rem;
}

.score-gauge {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin: 1rem 0;
}
.gauge-bar-bg {
    flex: 1;
    height: 8px;
    background: #1e2433;
    border-radius: 4px;
    overflow: hidden;
}
.gauge-bar {
    height: 100%;
    border-radius: 4px;
    transition: width 0.6s ease;
}
.gauge-val {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 2rem;
    font-weight: 700;
    min-width: 60px;
    text-align: right;
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
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return R * 2 * math.asin(math.sqrt(a))

# ─── Conseil IA : contexte + appel API ───────────────────────────────────────
def build_db_context(df, lieu_inconnu: str) -> str:
    """Résumé statistique de la base pour alimenter Claude API (~800 tokens)."""
    lines = []
    lines.append(f"BASE DE DONNÉES TRANSPORT CIT — {len(df):,} missions")
    lines.append(f"Lieu demandé (hors historique) : {lieu_inconnu}")
    lines.append("")

    top_dech = df["Localité déchargement"].value_counts().head(20)
    lines.append("TOP 20 LIEUX DE DÉCHARGEMENT :")
    for loc, cnt in top_dech.items():
        lines.append(f"  - {loc} ({cnt} missions)")
    lines.append("")

    top_ch = df["Localité chargement"].value_counts().head(20)
    lines.append("TOP 20 LIEUX DE CHARGEMENT :")
    for loc, cnt in top_ch.items():
        lines.append(f"  - {loc} ({cnt} missions)")
    lines.append("")

    try:
        prix_pays = (
            df.groupby("Pays chargement")["Prix transport"]
            .agg(["mean","count"]).round(0)
            .sort_values("count", ascending=False).head(10)
        )
        lines.append("PRIX MOYEN PAR PAYS DE CHARGEMENT :")
        for pays, row in prix_pays.iterrows():
            lines.append(f"  - {pays} : {row['mean']:,.0f}€ moy. ({int(row['count'])} missions)")
        lines.append("")
    except Exception:
        pass

    try:
        paires = (
            df[["Localité déchargement","Localité chargement","Prix transport"]]
            .dropna(subset=["Localité déchargement","Localité chargement"])
            .groupby(["Localité déchargement","Localité chargement"])
            .agg(nb=("Prix transport","count"), prix_moy=("Prix transport","mean"))
            .reset_index()
            .sort_values("nb", ascending=False)
            .head(15)
        )
        lines.append("TOP 15 CORRIDORS (déchargement → chargement) :")
        for _, r in paires.iterrows():
            lines.append(
                f"  - {r['Localité déchargement']} → {r['Localité chargement']} "
                f"({int(r['nb'])}×, {r['prix_moy']:,.0f}€ moy.)"
            )
        lines.append("")
    except Exception:
        pass

    try:
        p_min = df["Prix transport"].quantile(0.1)
        p_med = df["Prix transport"].median()
        p_max = df["Prix transport"].quantile(0.9)
        lines.append(f"PRIX : P10={p_min:,.0f}€ | Médiane={p_med:,.0f}€ | P90={p_max:,.0f}€")
    except Exception:
        pass

    return "\n".join(lines)


def conseil_ia_lieu_inconnu(df, lieu_inconnu: str, api_key: str) -> str:
    """Appelle Claude API et retourne les recommandations texte."""
    context = build_db_context(df, lieu_inconnu)

    system_prompt = (
        "Tu es un expert en optimisation de transport routier de marchandises. "
        "Tu analyses les données historiques d'une flotte de camions (CIT) pour donner "
        "des conseils opérationnels concrets. Tes réponses sont directes, chiffrées, "
        "orientées décision. Tu n'utilises pas de formules creuses ni d'introduction inutile."
    )
    user_prompt = (
        f"Un camion vient de décharger à : **{lieu_inconnu}**\n"
        f"Ce lieu n'apparaît PAS dans l'historique de la base.\n\n"
        f"Voici le contexte statistique de notre base de données :\n\n{context}\n\n"
        f"Sur la base de ces données historiques :\n"
        f"1. Quels lieux de rechargement seraient les plus logiques depuis {lieu_inconnu} ? "
        f"(tenir compte de la proximité géographique avec les corridors connus)\n"
        f"2. Quels corridors de la base sont les plus proches géographiquement ?\n"
        f"3. Quel prix de transport peut-on espérer dans cette zone ?\n"
        f"4. Points de vigilance pour ce déchargement hors-réseau ?\n\n"
        f"Format : réponse concise en 4 paragraphes numérotés, sans introduction."
    )

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    data = json.dumps(payload).encode("utf-8")
    req = _ureq_ai.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with _ureq_ai.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    return result["content"][0]["text"]


PAYS_MAP_DISPLAY = {
    "F":"France","B":"Belgium","BE":"Belgium","NL":"Netherlands",
    "D":"Germany","L":"Luxembourg","E":"Spain","I":"Italy",
    "CH":"Switzerland","A":"Austria","GB":"United Kingdom","PL":"Poland",
}
PAYS_FLAGS = {
    "F":"🇫🇷","B":"🇧🇪","BE":"🇧🇪","NL":"🇳🇱","D":"🇩🇪",
    "L":"🇱🇺","E":"🇪🇸","I":"🇮🇹","CH":"🇨🇭","A":"🇦🇹",
    "GB":"🇬🇧","PL":"🇵🇱",
}

# ─── Géocodage ───────────────────────────────────────────────────────────────
import urllib.request as _ureq
import urllib.parse as _uparse

def _photon(query: str):
    url = f"https://photon.komoot.io/api/?q={_uparse.quote(query)}&limit=1&lang=fr"
    try:
        req = _ureq.Request(url, headers={"User-Agent": "CB-Transport-Hub/1.0"})
        with _ureq.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
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
            data = json.loads(r.read())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None

@st.cache_data(show_spinner=False, ttl=86400)
def geocode_ptv_cached(ville: str, cp: str, pays: str):
    ville_exp = re.sub(r'\bST\b', 'SAINT', ville, flags=re.IGNORECASE)
    ville_exp = re.sub(r'\bSTE\b', 'SAINTE', ville_exp, flags=re.IGNORECASE)

    if PTV_AVAILABLE:
        fix_key = ville.strip().lower()
        if fix_key in GPS_FIXES:
            return GPS_FIXES[fix_key]

        if cp and pays:
            pays_label = PAYS_MAP_DISPLAY.get(pays.upper(), pays).lower()
            country_iso = PAYS_TO_ISO.get(pays_label)
            if not country_iso:
                country_iso = pays.upper() if len(pays) == 2 else None
            if country_iso and cp:
                r = geocode_by_postal_code(cp, country_iso)
                if r:
                    return r

        pays_label = PAYS_MAP_DISPLAY.get(pays.upper(), pays) if pays else ""
        for v in ([ville_exp, ville] if ville_exp != ville else [ville]):
            for q in filter(None, [
                f"{v}, {cp}, {pays_label}" if cp and pays_label else None,
                f"{v}, {pays_label}" if pays_label else None,
                v,
            ]):
                r = _geocode_by_text(q)
                if r:
                    return r
    else:
        pays_label = PAYS_MAP_DISPLAY.get(pays.upper(), pays) if pays else ""
        for v in ([ville_exp, ville] if ville_exp != ville else [ville]):
            for q in filter(None, [
                f"{v}, {cp}, {pays_label}" if cp and pays_label else None,
                f"{v}, {pays_label}" if pays_label else None,
                v,
            ]):
                r = _photon(q) or _nominatim(q)
                if r:
                    return r
    return None

@st.cache_data(show_spinner=False, ttl=3600)
def get_ptv_distance_km(lat1, lon1, lat2, lon2):
    if not PTV_AVAILABLE:
        return None
    try:
        result = calculate_km_route(lat1, lon1, lat2, lon2, calculer_peage=False)
        if result and result.get("km"):
            return float(result["km"])
    except Exception:
        pass
    return None

# ─── Chargement données ───────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_missions(missions_bytes, lavages_bytes):
    import io
    df = pd.read_excel(io.BytesIO(missions_bytes), dtype=str)
    df.columns = df.columns.str.strip()
    df["Date chargement"] = pd.to_datetime(df["Date chargement"], errors="coerce")
    df["Prix transport"]  = pd.to_numeric(df["Prix transport"],  errors="coerce")
    df["Total des ventes"]= pd.to_numeric(df["Total des ventes"],errors="coerce")
    df["N° Dossier"]      = df["N° Dossier"].str.strip()

    if lavages_bytes:
        df_l = pd.read_excel(io.BytesIO(lavages_bytes), dtype=str)
        df_l.columns = df_l.columns.str.strip()
        df_l["N° Dossier"] = df_l["N° Dossier"].str.strip()
        vehicule = df_l[["N° Dossier","Remorque","Tracteur","Chauffeur"]].drop_duplicates("N° Dossier")
        df = df.merge(vehicule, on="N° Dossier", how="left")
    else:
        df["Remorque"] = None
        df["Tracteur"] = None
        df["Chauffeur"] = None

    if DATE_DECH_COL and DATE_DECH_COL in df.columns:
        df["_date_dech"] = pd.to_datetime(df[DATE_DECH_COL], errors="coerce")
    else:
        df["_date_dech"] = df["Date chargement"]

    df["_loc_ch_norm"]   = df["Localité chargement"].apply(normalize)
    df["_loc_dech_norm"] = df["Localité déchargement"].apply(normalize)
    df["_dow_dech"]      = df["_date_dech"].dt.dayofweek

    df = df.dropna(subset=["Date chargement"]).sort_values("Date chargement").reset_index(drop=True)
    return df

# ─── Header ──────────────────────────────────────────────────────────────────
ptv_badge = (
    '<span class="badge-ptv">✓ PTV Routing actif</span>'
    if PTV_AVAILABLE else
    '<span class="badge-ptv off">⚠ PTV indisponible — géocodage OSM</span>'
)
st.markdown(f"""
<div class="hero">
    <h1>🚛 Optimisateur Planning</h1>
    <p>Je viens de décharger en X — où aller recharger pour maximiser l'efficacité ?</p>
    {ptv_badge}
</div>
""", unsafe_allow_html=True)

# ─── Upload ───────────────────────────────────────────────────────────────────
col_u1, col_u2 = st.columns(2)
with col_u1:
    missions_file = st.file_uploader("📋 Fichier Missions CA CIT", type=["xlsx","xls"])
with col_u2:
    lavages_file  = st.file_uploader(
        "🧼 Fichier Lavages",
        type=["xlsx","xls"],
        help="Permet le chaînage par Remorque/Tracteur — fortement recommandé"
    )

if not missions_file:
    st.info("👆 Chargez le fichier missions pour démarrer")
    st.stop()

missions_bytes = missions_file.read()
lavages_bytes  = lavages_file.read() if lavages_file else None

if not lavages_bytes:
    st.warning("⚠️ Sans le fichier lavages, pas de chaînage par véhicule — recommandations moins précises")

with st.spinner("⏳ Chargement et analyse des enchaînements historiques..."):
    df = load_missions(missions_bytes, lavages_bytes)

has_vehicle = df["Remorque"].notna().any()

# ─── KPIs ─────────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
kpis = [
    (f"{len(df):,}",                          "Missions"),
    (f"{df['Localité déchargement'].nunique():,}", "Lieux déchargement"),
    (f"{df['Localité chargement'].nunique():,}",   "Lieux chargement"),
    (f"{df['Prix transport'].mean():,.0f}€",        "Prix moyen"),
]
for col, (val, lbl) in zip([c1,c2,c3,c4], kpis):
    with col:
        st.markdown(f'<div class="kpi"><div class="val">{val}</div><div class="lbl">{lbl}</div></div>',
                    unsafe_allow_html=True)

st.divider()

# ─── Sélection lieu de déchargement ──────────────────────────────────────────
st.markdown('<div class="section-title">📍 Lieu de déchargement</div>', unsafe_allow_html=True)

lieux_dech = sorted(df["Localité déchargement"].dropna().unique().tolist())
col_s1, col_s2, col_s3 = st.columns([3, 1, 1])
with col_s1:
    # Champ libre + suggestions : si l'utilisateur tape quelque chose qui n'est pas dans
    # la liste, on l'accepte quand même (d'où le "" comme premier choix + allow_new_value)
    lieu_choisi = st.selectbox(
        "Je viens de décharger à...",
        [""] + lieux_dech,
        help="Si le lieu n'est pas dans la liste, tapez-le directement — le conseil IA prendra le relais."
    )
with col_s2:
    fenetre_jours = st.selectbox("Fenêtre max (jours)", [3, 7, 14], index=0)
with col_s3:
    nb_recos = st.selectbox("Nb recommandations", [5, 10, 15, 20], index=1)

# Saisie libre si hors liste
if lieu_choisi == "":
    lieu_libre = st.text_input(
        "Ou saisir un lieu hors liste",
        placeholder="ex: Metz, Namur, Stuttgart...",
        help="Pour un lieu non présent dans l'historique, le conseil IA analysera les corridors proches."
    )
    if lieu_libre.strip():
        lieu_choisi = lieu_libre.strip()

with st.expander("🎛️ Filtres avancés"):
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        pays_filtre = st.multiselect("Pays de rechargement",
            options=sorted(df["Pays chargement"].dropna().unique().tolist()))
    with col_f2:
        prix_min = st.number_input("Prix min mission (€)", value=0, step=50)
    with col_f3:
        use_ptv_dist = st.checkbox(
            "Distance routière PTV (top 10)",
            value=PTV_AVAILABLE,
            disabled=not PTV_AVAILABLE,
        )

if not lieu_choisi:
    st.info("👆 Choisissez ou saisissez un lieu de déchargement pour voir les recommandations")
    st.stop()

# ─── Calcul recommandations ───────────────────────────────────────────────────
loc_norm = normalize(lieu_choisi)

df_dech = df[df["_loc_dech_norm"] == loc_norm].copy()
if df_dech.empty:
    df_dech = df[df["_loc_dech_norm"].str.contains(loc_norm, na=False, regex=False)].copy()

# ─── MODE CONSEIL IA — lieu hors historique ───────────────────────────────────
if df_dech.empty:
    st.markdown(f"""
    <div class="ia-panel">
        <div class="ia-panel-title">⚡ Lieu hors historique — Conseil IA</div>
        <div class="ia-panel-sub">
            <strong style="color:#9a80d0">« {lieu_choisi} »</strong>
            n'apparaît pas dans la base ({df['Localité déchargement'].nunique()} lieux connus).
            Claude analyse les corridors proches pour suggérer les meilleures options de rechargement.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Clé API depuis secrets ou saisie manuelle
    api_key_ia = None
    try:
        api_key_ia = st.secrets.get("ANTHROPIC_API_KEY") or st.secrets.get("anthropic_api_key")
    except Exception:
        pass

    if not api_key_ia:
        api_key_ia = st.text_input(
            "🔑 Clé API Anthropic",
            type="password",
            placeholder="sk-ant-...",
            help="Ajoutez ANTHROPIC_API_KEY dans vos secrets Streamlit pour ne plus voir ce champ"
        )

    col_ia1, col_ia2 = st.columns([1, 3])
    with col_ia1:
        run_ia = st.button("🤖 Analyser avec l'IA", type="primary", use_container_width=True)
    with col_ia2:
        st.caption(
            f"Base : {len(df):,} missions · "
            f"{df['Localité déchargement'].nunique()} lieux de déchargement connus · "
            f"{df['Localité chargement'].nunique()} lieux de chargement connus"
        )

    if run_ia:
        if not api_key_ia:
            st.error("Clé API requise pour activer le conseil IA.")
        else:
            with st.spinner("🧠 Claude analyse les corridors proches..."):
                try:
                    conseil = conseil_ia_lieu_inconnu(df, lieu_choisi, api_key_ia)

                    st.markdown('<div class="ia-result"><div class="ia-result-header">💬 Recommandations IA</div>', unsafe_allow_html=True)
                    st.markdown(conseil)
                    st.markdown('</div>', unsafe_allow_html=True)

                    # ── Lieux historiques les plus proches (géocodage haversine) ──
                    coords_inconnu = geocode_ptv_cached(lieu_choisi, "", "F")
                    if coords_inconnu:
                        top_dech_connus = df["Localité déchargement"].value_counts().head(50).index.tolist()
                        proximites = []
                        for loc in top_dech_connus:
                            cp_ref   = df[df["Localité déchargement"] == loc]["C.P. déchargement"].mode()
                            cp_ref   = cp_ref.iloc[0] if not cp_ref.empty else ""
                            pays_ref = df[df["Localité déchargement"] == loc]["Pays déchargement"].mode()
                            pays_ref = pays_ref.iloc[0] if not pays_ref.empty else "F"
                            coords_loc = geocode_ptv_cached(loc, cp_ref, pays_ref)
                            if coords_loc:
                                d = haversine_km(
                                    coords_inconnu[0], coords_inconnu[1],
                                    coords_loc[0], coords_loc[1]
                                )
                                proximites.append((loc, d))

                        if proximites:
                            proximites.sort(key=lambda x: x[1])
                            st.markdown('<div class="proximity-title">📍 Lieux historiques les plus proches (vol d\'oiseau)</div>', unsafe_allow_html=True)
                            chips_html = '<div class="chips">' + "".join(
                                f'<span class="chip purple">📍 {loc} — {d:.0f} km</span>'
                                for loc, d in proximites[:8]
                            ) + '</div>'
                            st.markdown(chips_html, unsafe_allow_html=True)
                            st.caption(
                                "💡 Sélectionnez l'un de ces lieux dans le menu déroulant "
                                "pour voir les recommandations complètes basées sur l'historique."
                            )

                except Exception as e:
                    st.error(f"Erreur API : {e}")
                    st.caption("Vérifiez votre clé API ou la connexion réseau.")

    st.stop()

# ─── Suite normale si lieu trouvé dans l'historique ──────────────────────────
coords_dech = geocode_ptv_cached(
    lieu_choisi,
    df_dech["C.P. déchargement"].mode().iloc[0] if not df_dech["C.P. déchargement"].mode().empty else "",
    df_dech["Pays déchargement"].mode().iloc[0]  if not df_dech["Pays déchargement"].mode().empty else "",
)

with st.spinner(f"🔍 Analyse de {len(df_dech)} missions vers {lieu_choisi}..."):

    records = []
    seen_pairs = set()

    for _, row in df_dech.iterrows():
        date_ref = row["_date_dech"]
        if pd.isna(date_ref):
            continue

        extra_days = 2 if row["_dow_dech"] in (4, 5) else 0
        fwin = fenetre_jours + extra_days

        rem   = row.get("Remorque")
        trac  = row.get("Tracteur")
        chauf = row.get("Chauffeur")

        if has_vehicle and pd.notna(rem) and rem:
            next_ms = df[
                (df["Remorque"] == rem) &
                (df["Date chargement"] > date_ref) &
                (df["Date chargement"] <= date_ref + pd.Timedelta(days=fwin))
            ].head(1)
        else:
            next_ms = df[
                (df["Date chargement"] > date_ref) &
                (df["Date chargement"] <= date_ref + pd.Timedelta(days=1))
            ].head(1)

        for _, nrow in next_ms.iterrows():
            loc_ch = str(nrow["Localité chargement"] or "").strip()
            if not loc_ch or normalize(loc_ch) == loc_norm:
                continue

            prix = nrow["Prix transport"]
            if prix_min > 0 and (pd.isna(prix) or prix < prix_min):
                continue
            if pays_filtre and nrow["Pays chargement"] not in pays_filtre:
                continue

            pair_key = (str(rem), normalize(loc_ch))
            already = pair_key in seen_pairs
            seen_pairs.add(pair_key)

            records.append({
                "loc_ch":    loc_ch,
                "cp_ch":     str(nrow["C.P. chargement"] or "").strip(),
                "pays_ch":   str(nrow["Pays chargement"] or "").strip(),
                "delta_j":   (nrow["Date chargement"] - date_ref).days,
                "prix":      prix,
                "ventes":    nrow["Total des ventes"],
                "produit":   str(nrow["Produit"] or "").strip(),
                "client":    str(nrow["Client facturation"] or "").strip(),
                "chauffeur": str(chauf or "").strip(),
                "remorque":  str(rem or "").strip(),
                "tracteur":  str(trac or "").strip(),
                "dedup":     already,
            })

    mode_label = "Remorque" if has_vehicle else "fenêtre temporelle J+1"
    st.caption(f"ℹ️ Chaînage par {mode_label} — {len(records)} enchaînements analysés")

if not records:
    st.warning("Pas d'enchaînements trouvés dans cette fenêtre temporelle.")
    st.stop()

df_rec = pd.DataFrame(records)

agg = df_rec.groupby(["loc_ch","cp_ch","pays_ch"]).agg(
    frequence       = ("prix", "count"),
    prix_moyen      = ("prix", "mean"),
    ventes_moyennes = ("ventes", "mean"),
    delta_moyen     = ("delta_j", "mean"),
    prix_max        = ("prix", "max"),
    chauffeurs      = ("chauffeur", lambda x: ", ".join(sorted(set(v for v in x if v)))),
    clients         = ("client",   lambda x: ", ".join(sorted(set(v for v in x if v))[:3])),
).reset_index()

top_candidates = agg.sort_values("frequence", ascending=False).head(30).copy()

geocoded_ch = {}
with st.spinner("📡 Géocodage des lieux de rechargement (PTV)..."):
    for _, row in top_candidates.iterrows():
        k = row["loc_ch"]
        if k not in geocoded_ch:
            geocoded_ch[k] = geocode_ptv_cached(row["loc_ch"], row["cp_ch"], row["pays_ch"])

def get_distance(loc_ch, coords_ch):
    if not coords_ch or not coords_dech:
        return None
    if use_ptv_dist and PTV_AVAILABLE:
        d = get_ptv_distance_km(
            coords_dech[0], coords_dech[1],
            coords_ch[0], coords_ch[1]
        )
        if d:
            return d
    return haversine_km(coords_dech[0], coords_dech[1], coords_ch[0], coords_ch[1])

distances = {}
with st.spinner("🛣️ Calcul distances routières PTV..." if use_ptv_dist and PTV_AVAILABLE else ""):
    for _, row in top_candidates.iterrows():
        coords = geocoded_ch.get(row["loc_ch"])
        distances[row["loc_ch"]] = get_distance(row["loc_ch"], coords)

def compute_score(row) -> float:
    freq  = row["frequence"]
    prix  = row["prix_moyen"] if not pd.isna(row["prix_moyen"]) else 0
    delta = row["delta_moyen"] if row["delta_moyen"] > 0 else 0.5

    dist = distances.get(row["loc_ch"])
    if dist is None:
        return freq * (prix / 1000) * (1 / delta) * 0.3
    dist = max(dist, 20)
    return freq * (prix / 1000) * (300 / dist) * (1 / delta)

top_candidates["score"]   = top_candidates.apply(compute_score, axis=1)
top_candidates["dist_km"] = top_candidates["loc_ch"].map(distances)
top_candidates = top_candidates.sort_values("score", ascending=False).head(nb_recos).reset_index(drop=True)

max_score = top_candidates["score"].max()
top_candidates["score_pct"] = (top_candidates["score"] / max_score * 100).round(0).astype(int)

# ─── Affichage recommandations ────────────────────────────────────────────────
st.markdown(f'<div class="section-title">🎯 Recommandations après déchargement à {lieu_choisi.upper()}</div>',
            unsafe_allow_html=True)

r1, r2, r3 = st.columns(3)
with r1:
    st.markdown(f'<div class="kpi"><div class="val">{len(df_dech)}</div><div class="lbl">Missions historiques</div></div>', unsafe_allow_html=True)
with r2:
    st.markdown(f'<div class="kpi"><div class="val">{len(top_candidates)}</div><div class="lbl">Destinations proposées</div></div>', unsafe_allow_html=True)
with r3:
    best_prix = top_candidates.iloc[0]["prix_moyen"] if len(top_candidates) > 0 else 0
    st.markdown(f'<div class="kpi"><div class="val">{best_prix:,.0f}€</div><div class="lbl">Prix moyen #1</div></div>', unsafe_allow_html=True)

st.markdown("")

for i, row in top_candidates.iterrows():
    rank = i + 1
    r_cls = "r1" if rank == 1 else ("r2" if rank == 2 else ("r3" if rank == 3 else ""))
    flag  = PAYS_FLAGS.get(row["pays_ch"], "🌍")

    dist_v   = row["dist_km"]
    dist_str = f"{dist_v:.0f} km {'(route)' if use_ptv_dist and PTV_AVAILABLE and dist_v else '(vol d·oiseau)'}" if dist_v else "distance inconnue"
    prix_str  = f"{row['prix_moyen']:,.0f}€" if not pd.isna(row['prix_moyen']) else "N/A"
    delta_str = f"J+{row['delta_moyen']:.1f}"
    freq_str  = f"{int(row['frequence'])}×"
    badge = '<span class="badge-best">OPTIMAL</span>' if rank == 1 else ""

    sub_parts = []
    if row.get("chauffeurs"): sub_parts.append(row["chauffeurs"][:40])
    if row.get("clients"):    sub_parts.append(row["clients"][:40])
    sub_text = " · ".join(sub_parts) if sub_parts else f"{row['cp_ch']} — {row['pays_ch']}"

    st.markdown(f"""
    <div class="reco {r_cls}">
        <div class="reco-num">{rank:02d}</div>
        <div class="reco-main">
            <div class="reco-loc">{flag} {row['loc_ch']}</div>
            <div class="reco-sub">{sub_text}</div>
            <div class="chips">
                <span class="chip green">💶 {prix_str}</span>
                <span class="chip blue">📏 {dist_str}</span>
                <span class="chip gray">{delta_str}</span>
                <span class="chip orange">📊 {freq_str}</span>
            </div>
            <div class="score-track">
                <div class="score-fill" style="width:{row['score_pct']}%"></div>
            </div>
        </div>
        {badge}
    </div>
    """, unsafe_allow_html=True)

# ─── MODE SCORE MANUEL ────────────────────────────────────────────────────────
st.markdown('<div class="section-title">✏️ Évaluer une destination manuelle</div>', unsafe_allow_html=True)

st.markdown("""
<div class="manual-score-box">
<h3>Je sais où il va recharger — quel est le score ?</h3>
""", unsafe_allow_html=True)

col_m1, col_m2, col_m3 = st.columns([3, 1, 1])
with col_m1:
    dest_manuelle = st.text_input("Ville de rechargement", placeholder="ex: Béziers, Rouen, Liège...")
with col_m2:
    cp_manuel  = st.text_input("Code postal", placeholder="ex: 34500")
with col_m3:
    pays_manuel = st.selectbox("Pays", ["F","B","NL","D","L","E","I","CH","A","GB","PL"])

if dest_manuelle:
    with st.spinner(f"Évaluation de {dest_manuelle}..."):
        coords_dest_m = geocode_ptv_cached(dest_manuelle, cp_manuel, pays_manuel)

        if not coords_dest_m:
            st.warning(f"Impossible de géocoder « {dest_manuelle} »")
        else:
            if coords_dech:
                dist_m = get_distance(dest_manuelle, coords_dest_m)
                if not dist_m:
                    dist_m = haversine_km(coords_dech[0], coords_dech[1], coords_dest_m[0], coords_dest_m[1])
            else:
                dist_m = 300

            norm_dest_m = normalize(dest_manuelle)
            hist_match = df_rec[df_rec["loc_ch"].apply(normalize) == norm_dest_m]
            freq_m  = len(hist_match)
            prix_m  = hist_match["prix"].mean() if freq_m > 0 else df_rec["prix"].mean()
            delta_m = hist_match["delta_j"].mean() if freq_m > 0 else 3.0

            dist_m_safe  = max(dist_m, 20) if dist_m else 300
            prix_m_safe  = prix_m if not pd.isna(prix_m) else 0
            delta_m_safe = delta_m if delta_m > 0 else 1
            score_m = freq_m * (prix_m_safe / 1000) * (300 / dist_m_safe) * (1 / delta_m_safe)
            score_m = max(score_m, 0.01) if freq_m > 0 else 0.01

            pct_vs_best = min(score_m / max_score * 100, 100) if max_score > 0 else 0

            if pct_vs_best >= 70:
                gauge_color, verdict = "#4abf6a", "✅ Excellent choix"
            elif pct_vs_best >= 40:
                gauge_color, verdict = "#bf8a4a", "⚠️ Choix acceptable"
            else:
                gauge_color, verdict = "#bf4a4a", "❌ Sous-optimal"

            flag_m   = PAYS_FLAGS.get(pays_manuel, "🌍")
            dist_str_m = f"{dist_m:.0f} km" if dist_m else "inconnue"
            prix_str_m = f"{prix_m_safe:,.0f}€" if prix_m_safe else "N/A"

            st.markdown(f"""
            <div style="margin-top:0.5rem">
                <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.3rem;font-weight:700;
                            color:#c8cfe8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.4rem">
                    {flag_m} {dest_manuelle}
                </div>
                <div style="color:{gauge_color};font-weight:600;font-size:0.95rem;margin-bottom:0.8rem">
                    {verdict}
                </div>
                <div class="score-gauge">
                    <div class="gauge-bar-bg">
                        <div class="gauge-bar" style="width:{pct_vs_best:.0f}%;background:{gauge_color}"></div>
                    </div>
                    <div class="gauge-val" style="color:{gauge_color}">{pct_vs_best:.0f}%</div>
                </div>
                <div class="chips" style="margin-top:0.5rem">
                    <span class="chip {'green' if freq_m>0 else 'gray'}">📊 {freq_m}× historique</span>
                    <span class="chip blue">📏 {dist_str_m}</span>
                    <span class="chip green">💶 {prix_str_m}</span>
                </div>
            """, unsafe_allow_html=True)

            if freq_m == 0:
                st.markdown("""
                <div style="margin-top:0.6rem;font-size:0.8rem;color:#5c6480;font-style:italic">
                    ℹ️ Cette destination n'apparaît pas dans l'historique — score basé sur distance et prix moyen global.
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="margin-top:0.6rem;font-size:0.8rem;color:#5c6480">
                    Ce trajet a été fait {freq_m}× après un déchargement à {lieu_choisi},
                    délai moyen J+{delta_m:.1f}, prix moyen {prix_str_m}.
                </div>
                """, unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

            equiv_rank = (top_candidates["score"] > score_m).sum() + 1
            if equiv_rank <= len(top_candidates):
                st.info(f"📌 Cette destination équivaudrait au rang **#{equiv_rank}** dans les recommandations.")
            else:
                st.info(f"📌 Cette destination serait classée après les {len(top_candidates)} recommandations affichées.")

st.markdown("</div>", unsafe_allow_html=True)

# ─── Carte ────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">🗺️ Carte des destinations</div>', unsafe_allow_html=True)

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
            "dist":  f"{row['dist_km']:.0f} km" if row['dist_km'] else "?",
            "rang":  i + 1,
        })

if map_data:
    try:
        import pydeck as pdk

        df_map = pd.DataFrame(map_data)
        df_map["radius"] = 1200
        df_map["color"]  = df_map["rang"].apply(
            lambda r: [74, 191, 106, 230] if r == 1 else
                      ([74, 138, 191, 210] if r <= 3 else [60, 80, 100, 180])
        )

        layers = [
            pdk.Layer("ScatterplotLayer", data=df_map,
                get_position="[lon, lat]", get_radius="radius",
                get_fill_color="color", get_line_color=[255,255,255,80],
                stroked=True, line_width_min_pixels=1, pickable=True, auto_highlight=True),
            pdk.Layer("TextLayer", data=df_map,
                get_position="[lon, lat]", get_text="nom", get_size=12,
                get_color=[200,210,230,220], get_anchor="middle",
                get_alignment_baseline="'bottom'", get_pixel_offset=[0,-14]),
        ]

        if coords_dech:
            df_origin = pd.DataFrame([{
                "lat": coords_dech[0], "lon": coords_dech[1],
                "label": lieu_choisi.upper(), "nom": f"Déchargement : {lieu_choisi}",
            }])
            layers += [
                pdk.Layer("ScatterplotLayer", data=df_origin,
                    get_position="[lon, lat]", get_radius=2000,
                    get_fill_color=[191,74,74,240], get_line_color=[255,255,255,200],
                    stroked=True, line_width_min_pixels=2, pickable=True),
                pdk.Layer("TextLayer", data=df_origin,
                    get_position="[lon, lat]", get_text="label", get_size=13,
                    get_color=[220,100,100,255], get_anchor="middle",
                    get_alignment_baseline="'bottom'", get_pixel_offset=[0,-16], font_weight=800),
            ]

        center_lat = coords_dech[0] if coords_dech else df_map["lat"].mean()
        center_lon = coords_dech[1] if coords_dech else df_map["lon"].mean()

        deck = pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=5, pitch=0),
            tooltip={
                "html": "<b>#{rang} — {nom}</b><br>💶 {prix} &nbsp;|&nbsp; 📏 {dist}<br>📊 {freq}× historique",
                "style": {"background":"#141821","color":"#c8cfe8","font-size":"13px",
                          "padding":"10px","font-family":"Barlow Condensed, sans-serif"}
            },
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        )
        st.pydeck_chart(deck, use_container_width=True, height=520)
        st.markdown(
            "<small style='color:#3d4560'>🔴 Lieu de déchargement &nbsp;|&nbsp; 🟢 Top 1 &nbsp;|&nbsp; 🔵 Top 2-3 &nbsp;|&nbsp; ⚫ Autres</small>",
            unsafe_allow_html=True)

    except ImportError:
        st.map(pd.DataFrame(map_data).rename(columns={"lat":"latitude","lon":"longitude"}))

# ─── Tableau ──────────────────────────────────────────────────────────────────
with st.expander("📋 Tableau complet"):
    df_display = top_candidates[["loc_ch","cp_ch","pays_ch","frequence",
                                  "prix_moyen","ventes_moyennes","delta_moyen",
                                  "dist_km","score_pct","chauffeurs","clients"]].copy()
    df_display.columns = ["Lieu chargement","CP","Pays","Fréquence",
                          "Prix moyen (€)","Ventes moy. (€)","Délai moyen (j)",
                          "Distance (km)","Score (%)","Chauffeurs","Clients"]
    for col in ["Prix moyen (€)","Ventes moy. (€)"]:
        df_display[col] = df_display[col].round(0)
    df_display["Délai moyen (j)"] = df_display["Délai moyen (j)"].round(1)
    df_display["Distance (km)"]   = df_display["Distance (km)"].round(0)
    st.dataframe(df_display, hide_index=True, use_container_width=True)

    import io as _io
    buf = _io.BytesIO()
    df_display.to_excel(buf, index=False, engine="openpyxl")
    st.download_button(
        "📥 Exporter Excel",
        data=buf.getvalue(),
        file_name=f"recos_{normalize(lieu_choisi).replace(' ','_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ─── Produits ─────────────────────────────────────────────────────────────────
with st.expander("🧪 Produits typiquement chargés après ce déchargement"):
    produits = df_rec.groupby("produit").agg(
        nb=("prix","count"), prix_moy=("prix","mean")
    ).sort_values("nb", ascending=False).head(15).reset_index()
    produits.columns = ["Produit","Nb missions","Prix moyen (€)"]
    produits["Prix moyen (€)"] = produits["Prix moyen (€)"].round(0)
    st.dataframe(produits, hide_index=True, use_container_width=True)
