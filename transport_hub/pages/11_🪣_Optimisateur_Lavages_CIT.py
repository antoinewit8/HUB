"""
Page Streamlit : Optimisateur Lavages Citernes — recherche autour d'une position
- On choisit une position : adresse tapée OU clic sur la carte
- Stations connues (historique lavages) dans le rayon, avec prix pratiqués
- Nouvelles stations potentielles (OpenStreetMap, + Google Places si clé API),
  recherchées à la demande, après affichage de la carte
- Référentiel géocodé exportable pour ne pas regéocoder à chaque fois

Dépendances à ajouter dans requirements.txt :
    folium
    streamlit-folium
"""

import io
import re
import json
import time
import math
import difflib
import unicodedata
import urllib.request as ureq
import urllib.parse as uparse
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(
    page_title="Optimisateur Lavages CIT",
    page_icon="🪣",
    layout="wide",
)

# ─── Style (identique au reste du HUB) ───────────────────────────────────────
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
.kpi-box .kpi-val { font-size: 1.7rem; font-weight: 700; color: #4a90d9; }
.kpi-box .kpi-lbl { font-size: 0.78rem; color: #8aa4bc; letter-spacing: 0.5px; }

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

UA = {"User-Agent": "CB-Transport-Hub/1.0"}
OSM_RAYON_MAX = 100  # km — au-delà, Overpass devient trop lent

# ─── Utilitaires ─────────────────────────────────────────────────────────────
def normalize(text) -> str:
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return ""
    text = str(text).upper().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"['\-–.,]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_prix(val):
    """'1.234,50 €' / '85,00' / '85.5' → float, sinon NaN."""
    if val is None:
        return np.nan
    s = str(val).strip().replace("€", "").replace("EUR", "").replace("\xa0", "").replace(" ", "")
    if not s or s.lower() == "nan":
        return np.nan
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return np.nan


def haversine(lat1, lon1, lat2, lon2):
    """Distance vol d'oiseau en km (vectorisé)."""
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def gmaps_link(lat, lon):
    return f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"


def _get_json(url, timeout=10):
    req = ureq.Request(url, headers=UA)
    with ureq.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _post_json(url, body: bytes, headers: dict, timeout=30):
    req = ureq.Request(url, data=body, headers={**UA, **headers}, method="POST")
    with ureq.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ─── Géocodage ───────────────────────────────────────────────────────────────
def _photon(query: str, limit: int = 1):
    url = f"https://photon.komoot.io/api/?q={uparse.quote(query)}&limit={limit}&lang=fr"
    try:
        return _get_json(url, timeout=8).get("features", [])
    except Exception:
        return []


def _nominatim(query: str, limit: int = 1):
    url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={uparse.quote(query)}&format=json&limit={limit}&addressdetails=1"
    )
    try:
        return _get_json(url, timeout=8)
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def search_address(query: str):
    """Renvoie jusqu'à 5 propositions {label, lat, lon} pour une adresse tapée."""
    out = []
    for f in _photon(query, limit=5):
        p = f.get("properties", {})
        lon, lat = f["geometry"]["coordinates"]
        rue = " ".join(x for x in [p.get("street"), p.get("housenumber")] if x)
        ville = " ".join(x for x in [p.get("postcode"), p.get("city")] if x)
        parts = [p.get("name"), rue, ville, p.get("country")]
        label = ", ".join(dict.fromkeys(x for x in parts if x)) or query
        out.append({"label": label, "lat": float(lat), "lon": float(lon)})
    if not out:
        for d in _nominatim(query, limit=5):
            out.append({"label": d.get("display_name", query), "lat": float(d["lat"]), "lon": float(d["lon"])})
    return out


@st.cache_data(ttl=30 * 86400, show_spinner=False)
def geocode_station(nom: str, localite: str, cp: str, pays: str = ""):
    """
    Géocode une station. Le résultat par nom n'est accepté que si le CP ou la
    localité retournés correspondent (évite les homonymes ailleurs en Europe).
    Retour : (lat, lon, précision) ou None.
    """
    cp_n, loc_n = normalize(cp), normalize(localite)

    for f in _photon(f"{nom}, {cp} {localite} {pays}".strip(" ,"), limit=3):
        p = f.get("properties", {})
        if normalize(p.get("postcode")) == cp_n or (loc_n and normalize(p.get("city")) == loc_n):
            lon, lat = f["geometry"]["coordinates"]
            return float(lat), float(lon), "station"

    q_loc = f"{cp} {localite} {pays}".strip()
    feats = _photon(q_loc, limit=1)
    if feats:
        lon, lat = feats[0]["geometry"]["coordinates"]
        return float(lat), float(lon), "localité"
    res = _nominatim(q_loc, limit=1)
    if res:
        return float(res[0]["lat"]), float(res[0]["lon"]), "localité"
    return None


# ─── Recherche de nouvelles stations (sans cache Streamlit : appelées en threads) ─
NAME_RX = (
    "tank ?clean|tank ?wash|tankreinig|tankinnenreinig|tankwasch|tankreiniging|"
    "lavage.{0,12}citerne|nettoyage.{0,12}citerne|station de lavage poids|"
    "lavaggio.{0,6}cisterne|limpieza.{0,6}cisternas|cleaning station"
)
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def search_osm(lat: float, lon: float, radius_km: float):
    """Bbox au lieu de 'around' (beaucoup plus rapide), rayon plafonné."""
    r = min(radius_km, OSM_RAYON_MAX)
    dlat = r / 111.0
    dlon = r / (111.0 * max(math.cos(math.radians(lat)), 0.1))
    s, w, n, e = lat - dlat, lon - dlon, lat + dlat, lon + dlon
    query = f"""
[out:json][timeout:25][bbox:{s:.4f},{w:.4f},{n:.4f},{e:.4f}];
(
  nw["name"~"{NAME_RX}",i][!"highway"];
  nw["amenity"="vehicle_wash"]["hgv"~"yes|designated|only"];
  nw["amenity"="truck_wash"];
);
out center tags;
"""
    body = uparse.urlencode({"data": query}).encode()
    data = None
    for url in OVERPASS_URLS:
        try:
            data = _post_json(url, body, {"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
            break
        except Exception:
            continue
    if data is None:
        return None  # None = erreur, [] = aucun résultat

    out = []
    for el in data.get("elements", []):
        t = el.get("tags", {})
        la = el.get("lat") or el.get("center", {}).get("lat")
        lo = el.get("lon") or el.get("center", {}).get("lon")
        if la is None or lo is None:
            continue
        rue = " ".join(x for x in [t.get("addr:street"), t.get("addr:housenumber")] if x)
        ville = " ".join(x for x in [t.get("addr:postcode"), t.get("addr:city")] if x)
        out.append({
            "nom": t.get("name") or t.get("operator") or "Station de lavage PL (sans nom)",
            "adresse": ", ".join(x for x in [rue, ville] if x),
            "lat": float(la), "lon": float(lo),
            "telephone": t.get("phone") or t.get("contact:phone") or "",
            "site": t.get("website") or t.get("contact:website") or "",
            "source": "OpenStreetMap",
        })
    return out


def get_google_key():
    try:
        return st.secrets.get("GOOGLE_PLACES_API_KEY")
    except Exception:
        return None


GOOGLE_TERMES = ["tank cleaning station", "lavage citerne camion", "Tankreinigung", "tankreiniging"]


def _google_terme(terme, lat, lon, radius_km, api_key):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,places.location,"
            "places.nationalPhoneNumber,places.websiteUri"
        ),
    }
    body = json.dumps({
        "textQuery": terme,
        "pageSize": 20,
        "locationBias": {"circle": {
            "center": {"latitude": lat, "longitude": lon},
            "radius": float(min(radius_km * 1000, 50000)),
        }},
    }).encode()
    try:
        data = _post_json("https://places.googleapis.com/v1/places:searchText", body, headers, timeout=12)
    except Exception:
        return []
    out = []
    for p in data.get("places", []):
        loc = p.get("location", {})
        if "latitude" not in loc:
            continue
        out.append({
            "nom": p.get("displayName", {}).get("text", "?"),
            "adresse": p.get("formattedAddress", ""),
            "lat": float(loc["latitude"]), "lon": float(loc["longitude"]),
            "telephone": p.get("nationalPhoneNumber", ""),
            "site": p.get("websiteUri", ""),
            "source": "Google",
        })
    return out


def fetch_new_stations(lat, lon, radius_km, use_osm, google_key):
    """Lance OSM et tous les termes Google en parallèle."""
    t0 = time.time()
    trouves, osm_erreur = [], False
    with ThreadPoolExecutor(max_workers=6) as ex:
        f_osm = ex.submit(search_osm, lat, lon, radius_km) if use_osm else None
        f_g = [ex.submit(_google_terme, t, lat, lon, radius_km, google_key) for t in GOOGLE_TERMES] if google_key else []
        for f in f_g:
            trouves += f.result()
        if f_osm is not None:
            res = f_osm.result()
            if res is None:
                osm_erreur = True
            else:
                trouves += res
    return {"trouves": trouves, "osm_erreur": osm_erreur, "duree": time.time() - t0}


# ─── Chargement ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_excel(b: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(b), dtype=str)
    df.columns = df.columns.str.strip()
    return df


@st.cache_data(show_spinner=False)
def build_lavages(df_l: pd.DataFrame, df_m: pd.DataFrame | None):
    df = df_l.copy()
    for c in ["Nom 1", "Localité", "Code postal", "N° Dossier"]:
        if c in df.columns:
            df[c] = df[c].fillna("").str.strip()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True) if "Date" in df.columns else pd.NaT
    df["_prix"] = df["Prix"].apply(parse_prix) if "Prix" in df.columns else np.nan
    df["_pays"] = df["Pays"].fillna("").str.strip() if "Pays" in df.columns else ""
    df["_cle"] = df["Nom 1"].map(normalize) + "|" + df["Code postal"]

    if df_m is not None and {"N° Dossier", "Produit"}.issubset(df_m.columns) and "N° Dossier" in df.columns:
        prod = df_m[["N° Dossier", "Produit"]].copy()
        prod["N° Dossier"] = prod["N° Dossier"].str.strip()
        prod = prod.drop_duplicates("N° Dossier")
        df = df.merge(prod, on="N° Dossier", how="left")
    return df


@st.cache_data(show_spinner=False)
def build_stations(df: pd.DataFrame) -> pd.DataFrame:
    g = df.sort_values("Date").groupby("_cle", dropna=False)
    st_df = g.agg(
        nom=("Nom 1", "first"),
        localite=("Localité", "first"),
        cp=("Code postal", "first"),
        pays=("_pays", "first"),
        nb=("_cle", "size"),
        prix_med=("_prix", "median"),
        prix_min=("_prix", "min"),
        prix_max=("_prix", "max"),
        dernier_prix=("_prix", "last"),
        dernier_lavage=("Date", "max"),
    ).reset_index()
    return st_df[st_df["nom"] != ""]


def prepare_pistes(trouves, center, rayon, df_st_geo):
    """Filtre au rayon, dédoublonne, et marque ce qui est déjà dans l'historique."""
    if not trouves:
        return pd.DataFrame()
    df_new = pd.DataFrame(trouves)
    df_new["dist_km"] = haversine(center["lat"], center["lon"], df_new["lat"], df_new["lon"])
    df_new = df_new[df_new["dist_km"] <= rayon]
    if df_new.empty:
        return df_new

    gardes = []
    for _, r in df_new.iterrows():
        if all(haversine(r["lat"], r["lon"], g["lat"], g["lon"]) > 0.15 for g in gardes):
            gardes.append(r)
    df_new = pd.DataFrame(gardes)

    def deja_connue(r):
        if df_st_geo.empty:
            return ""
        d = haversine(r["lat"], r["lon"], df_st_geo["lat"].values, df_st_geo["lon"].values)
        proches = df_st_geo[d < 5].assign(_d=d[d < 5])
        for _, k in proches.iterrows():
            sim = difflib.SequenceMatcher(None, normalize(r["nom"]), normalize(k["nom"])).ratio()
            if k["_d"] < 0.4 or sim > 0.75:
                return k["nom"]
        return ""

    df_new["deja_connue"] = df_new.apply(deja_connue, axis=1)
    return df_new.sort_values("dist_km")


# ─── En-tête ─────────────────────────────────────────────────────────────────
st.markdown("## 🪣 Optimisateur Lavages Citernes")
st.caption("Choisissez une position (adresse ou clic sur la carte) : stations déjà utilisées avec leurs prix, et nouvelles stations à démarcher.")
st.divider()

c1, c2, c3 = st.columns(3)
with c1:
    lavages_file = st.file_uploader("🧼 Fichier Lavages (obligatoire)", type=["xlsx", "xls"], key="lavages",
                                    help="liste_lavages : N° Dossier, Date, Nom 1, Localité, Code postal, Prix…")
with c2:
    missions_file = st.file_uploader("📋 Fichier Missions CA CIT (optionnel)", type=["xlsx", "xls"], key="missions",
                                     help="Sert à afficher les prix par produit transporté")
with c3:
    ref_file = st.file_uploader("📍 Référentiel stations géocodé (optionnel)", type=["xlsx"], key="ref",
                                help="Export de l'onglet Référentiel : évite de regéocoder toutes les stations")

if not lavages_file:
    st.info("👆 Chargez au minimum le fichier lavages pour démarrer")
    st.stop()

try:
    df_l_raw = load_excel(lavages_file.getvalue())
    df_m_raw = load_excel(missions_file.getvalue()) if missions_file else None
except Exception as e:
    st.error(f"❌ Lecture impossible : {e}")
    st.stop()

manquantes = [c for c in ["Nom 1", "Localité", "Code postal"] if c not in df_l_raw.columns]
if manquantes:
    st.error(f"❌ Colonnes manquantes dans le fichier lavages : {', '.join(manquantes)}")
    st.stop()

df_lav = build_lavages(df_l_raw, df_m_raw)
df_st = build_stations(df_lav)
has_produit = "Produit" in df_lav.columns

# ─── Géocodage des stations connues (session + référentiel) ─────────────────
coords = st.session_state.setdefault("coords", {})

if ref_file and not st.session_state.get("ref_charge"):
    try:
        ref = load_excel(ref_file.getvalue())
        for _, r in ref.dropna(subset=["cle", "lat", "lon"]).iterrows():
            coords[r["cle"]] = (float(r["lat"]), float(r["lon"]), r.get("precision", "référentiel"))
        st.session_state["ref_charge"] = True
    except Exception as e:
        st.warning(f"Référentiel ignoré ({e}) — colonnes attendues : cle, lat, lon, precision")

a_geocoder = df_st[~df_st["_cle"].isin(coords.keys())]
if not a_geocoder.empty:
    bar = st.progress(0, text=f"Géocodage de {len(a_geocoder)} station(s)… (une seule fois — exportez ensuite le référentiel)")
    for i, (_, r) in enumerate(a_geocoder.iterrows()):
        res = geocode_station(r["nom"], r["localite"], r["cp"], r["pays"])
        coords[r["_cle"]] = res if res else (np.nan, np.nan, "échec")
        bar.progress((i + 1) / len(a_geocoder), text=f"Géocodage {i + 1}/{len(a_geocoder)} — {r['nom']}")
    bar.empty()

df_st["lat"] = df_st["_cle"].map(lambda k: coords.get(k, (np.nan,) * 3)[0])
df_st["lon"] = df_st["_cle"].map(lambda k: coords.get(k, (np.nan,) * 3)[1])
df_st["precision"] = df_st["_cle"].map(lambda k: coords.get(k, (np.nan,) * 3)[2])
df_st_geo = df_st.dropna(subset=["lat", "lon"]).copy()

# ─── Choix de la position ────────────────────────────────────────────────────
st.markdown('<div class="section-title">📍 Position de recherche</div>', unsafe_allow_html=True)

col_a, col_b, col_c = st.columns([3, 1, 1])
with col_a:
    adresse = st.text_input("Adresse, ville ou code postal",
                            placeholder="ex. Zone industrielle, 57190 Florange — ou cliquez sur la carte")
    propositions = search_address(adresse) if adresse.strip() else []
    choix = None
    if propositions:
        choix = st.selectbox("Résultats", propositions, format_func=lambda p: p["label"])
    elif adresse.strip():
        st.warning("Adresse introuvable. Essayez avec le code postal, ou cliquez sur la carte.")
with col_b:
    rayon = st.slider("Rayon (km)", 5, 200, 50, step=5)
with col_c:
    st.write("")
    st.write("")
    if st.button("📍 Centrer ici", use_container_width=True, disabled=choix is None):
        st.session_state["center"] = {"lat": choix["lat"], "lon": choix["lon"], "label": choix["label"]}

center = st.session_state.get("center")
google_key = get_google_key()

col_o1, col_o2, col_o3 = st.columns([2, 2, 2])
with col_o1:
    use_osm = st.checkbox("Source OpenStreetMap", value=True,
                          help=f"Gratuit, mais incomplet. Rayon plafonné à {OSM_RAYON_MAX} km.")
with col_o2:
    use_google = st.checkbox("Source Google Places", value=bool(google_key), disabled=not google_key,
                             help=None if google_key else "Ajoutez GOOGLE_PLACES_API_KEY dans les secrets Streamlit")
with col_o3:
    lancer = st.button("🔎 Chercher de nouvelles stations", use_container_width=True,
                       disabled=not center or not (use_osm or use_google))

# Signature de la recherche : position + rayon + sources
sig = None
if center:
    sig = (round(center["lat"], 3), round(center["lon"], 3), rayon, use_osm, bool(use_google and google_key))
pistes_cache = st.session_state.setdefault("pistes_cache", {})
if lancer and sig not in pistes_cache:
    st.session_state["recherche_en_attente"] = sig

# ─── Stations connues autour (instantané) ────────────────────────────────────
df_proche = pd.DataFrame()
if center and not df_st_geo.empty:
    df_st_geo["dist_km"] = haversine(center["lat"], center["lon"], df_st_geo["lat"], df_st_geo["lon"])
    df_proche = df_st_geo[df_st_geo["dist_km"] <= rayon].sort_values("dist_km").copy()

# Nouvelles pistes : uniquement si déjà cherchées pour cette position
res_pistes = pistes_cache.get(sig) if sig else None
df_new = prepare_pistes(res_pistes["trouves"], center, rayon, df_st_geo) if res_pistes else pd.DataFrame()
df_pistes = df_new[df_new["deja_connue"] == ""] if not df_new.empty else pd.DataFrame()

# ─── KPIs ────────────────────────────────────────────────────────────────────
if center:
    st.markdown(f"### 📍 {center['label']} — rayon {rayon} km")
    k1, k2, k3, k4 = st.columns(4)
    prix_ok = df_proche.dropna(subset=["prix_med"]) if not df_proche.empty else pd.DataFrame()
    prix_zone = prix_ok["prix_med"].median() if not prix_ok.empty else np.nan
    moins_chere = prix_ok.sort_values("prix_med").iloc[0] if not prix_ok.empty else None
    vals = [
        (len(df_proche), "Stations déjà utilisées"),
        (len(df_pistes) if res_pistes else "—", "Nouvelles pistes"),
        (f"{prix_zone:.0f} €" if pd.notna(prix_zone) else "—", "Prix médian zone"),
        (f"{moins_chere['prix_med']:.0f} €" if moins_chere is not None else "—",
         f"Moins chère : {moins_chere['nom'][:28]}" if moins_chere is not None else "Moins chère"),
    ]
    for col, (v, lbl) in zip([k1, k2, k3, k4], vals):
        col.markdown(f'<div class="kpi-box"><div class="kpi-val">{v}</div><div class="kpi-lbl">{lbl}</div></div>',
                     unsafe_allow_html=True)
    if res_pistes and res_pistes["osm_erreur"]:
        st.warning("OpenStreetMap n'a pas répondu à temps — relancez la recherche dans une minute.")
    if use_osm and rayon > OSM_RAYON_MAX:
        st.caption(f"ℹ️ La recherche OpenStreetMap est limitée à {OSM_RAYON_MAX} km pour rester rapide.")

# ─── Carte (affichée tout de suite) ──────────────────────────────────────────
if center:
    m = folium.Map(location=[center["lat"], center["lon"]], zoom_start=9, tiles="CartoDB dark_matter")
    folium.Circle([center["lat"], center["lon"]], radius=rayon * 1000,
                  color="#4a90d9", weight=1, fill=True, fill_opacity=0.04).add_to(m)
    folium.Marker([center["lat"], center["lon"]], tooltip=center["label"],
                  icon=folium.Icon(color="black", icon="crosshairs", prefix="fa")).add_to(m)
elif not df_st_geo.empty:
    m = folium.Map(location=[df_st_geo["lat"].mean(), df_st_geo["lon"].mean()], zoom_start=6,
                   tiles="CartoDB dark_matter")
else:
    m = folium.Map(location=[49.8, 5.5], zoom_start=6, tiles="CartoDB dark_matter")

ids_proches = set(df_proche["_cle"]) if not df_proche.empty else set()
for _, r in df_st_geo[~df_st_geo["_cle"].isin(ids_proches)].iterrows():
    folium.CircleMarker([r["lat"], r["lon"]], radius=3, color="#5a7085", fill=True, fill_opacity=0.7,
                        tooltip=f"{r['nom']} ({r['localite']})").add_to(m)

if not df_proche.empty:
    prix_dispo = df_proche["prix_med"].dropna()
    q1, q2 = (prix_dispo.quantile(1 / 3), prix_dispo.quantile(2 / 3)) if len(prix_dispo) >= 3 else (np.inf, np.inf)
    for _, r in df_proche.iterrows():
        p = r["prix_med"]
        couleur = "gray" if pd.isna(p) else ("green" if p <= q1 else "orange" if p <= q2 else "red")
        prix_txt = "—" if pd.isna(p) else f"{p:.2f} € (min {r['prix_min']:.2f} / max {r['prix_max']:.2f})"
        date_txt = r["dernier_lavage"].strftime("%d/%m/%Y") if pd.notna(r["dernier_lavage"]) else "—"
        approx = "<br><i>⚠️ position approximative (centre de la commune)</i>" if r["precision"] == "localité" else ""
        popup = (f"<b>{r['nom']}</b><br>{r['cp']} {r['localite']}<br>"
                 f"💶 Prix médian : {prix_txt}<br>🧼 {r['nb']} lavage(s) — dernier le {date_txt}<br>"
                 f"📏 {r['dist_km']:.1f} km{approx}<br>"
                 f"<a href='{gmaps_link(r['lat'], r['lon'])}' target='_blank'>Ouvrir dans Google Maps</a>")
        folium.Marker([r["lat"], r["lon"]], tooltip=f"{r['nom']} — {prix_txt.split(' (')[0]}",
                      popup=folium.Popup(popup, max_width=320),
                      icon=folium.Icon(color=couleur, icon="tint", prefix="fa")).add_to(m)

if not df_pistes.empty:
    for _, r in df_pistes.iterrows():
        popup = (f"<b>{r['nom']}</b><br>{r['adresse'] or '(adresse non renseignée)'}<br>"
                 f"🆕 Jamais utilisée — prix à demander<br>📏 {r['dist_km']:.1f} km — source {r['source']}<br>"
                 + (f"📞 {r['telephone']}<br>" if r["telephone"] else "")
                 + (f"<a href='{r['site']}' target='_blank'>Site web</a><br>" if r["site"] else "")
                 + f"<a href='{gmaps_link(r['lat'], r['lon'])}' target='_blank'>Ouvrir dans Google Maps</a>")
        folium.Marker([r["lat"], r["lon"]], tooltip=f"🆕 {r['nom']}",
                      popup=folium.Popup(popup, max_width=320),
                      icon=folium.Icon(color="purple", icon="question", prefix="fa")).add_to(m)

st.caption("🖱️ Cliquez n'importe où sur la carte pour y placer le centre de recherche.")
carte = st_folium(m, height=620, use_container_width=True, returned_objects=["last_clicked"], key="carte_lavages")
st.markdown("<small>🟢 moins cher de la zone &nbsp;|&nbsp; 🟠 prix moyen &nbsp;|&nbsp; 🔴 plus cher &nbsp;|&nbsp; "
            "⚪ prix inconnu &nbsp;|&nbsp; 🟣 nouvelle piste &nbsp;|&nbsp; ⚫ centre de recherche &nbsp;|&nbsp; "
            "points gris : stations connues hors rayon</small>", unsafe_allow_html=True)

# Clic sur la carte → nouveau centre (pas de recherche externe automatique)
clic = (carte or {}).get("last_clicked")
if clic:
    sig_clic = (round(clic["lat"], 5), round(clic["lng"], 5))
    if sig_clic != st.session_state.get("dernier_clic"):
        st.session_state["dernier_clic"] = sig_clic
        st.session_state["center"] = {"lat": clic["lat"], "lon": clic["lng"],
                                      "label": f"Point sélectionné ({clic['lat']:.4f}, {clic['lng']:.4f})"}
        st.rerun()

# Recherche externe : lancée APRÈS l'affichage de la carte, puis rafraîchissement
en_attente = st.session_state.get("recherche_en_attente")
if en_attente and en_attente == sig:
    with st.spinner("Recherche de nouvelles stations… (la carte se met à jour à la fin)"):
        pistes_cache[sig] = fetch_new_stations(
            center["lat"], center["lon"], rayon, use_osm, google_key if use_google else None
        )
    st.session_state["recherche_en_attente"] = None
    st.rerun()

if not center:
    st.info("👆 Tapez une adresse puis « Centrer ici », ou cliquez sur la carte.")
elif not res_pistes:
    st.caption("Les nouvelles stations ne sont cherchées que sur demande : bouton « Chercher de nouvelles stations ».")
else:
    st.caption(f"Recherche de nouvelles stations effectuée en {res_pistes['duree']:.1f} s.")

# ─── Onglets de résultats ────────────────────────────────────────────────────
onglets = ["🧼 Stations connues", "🆕 Nouvelles pistes"]
if has_produit:
    onglets.append("💶 Prix par produit")
onglets.append("🔧 Référentiel")
tabs = st.tabs(onglets)
t_connues, t_pistes = tabs[0], tabs[1]
t_produit = tabs[2] if has_produit else None
t_ref = tabs[-1]

with t_connues:
    if not center:
        st.info("Choisissez d'abord une position.")
    elif df_proche.empty:
        st.info(f"Aucune station de l'historique dans un rayon de {rayon} km. Lancez la recherche de nouvelles stations.")
    else:
        vue = df_proche[["nom", "localite", "cp", "dist_km", "nb", "prix_med", "prix_min", "prix_max",
                         "dernier_prix", "dernier_lavage", "precision"]].copy()
        vue["maps"] = [gmaps_link(a, b) for a, b in zip(df_proche["lat"], df_proche["lon"])]
        st.dataframe(
            vue, hide_index=True, use_container_width=True,
            column_config={
                "nom": "Station", "localite": "Localité", "cp": "CP",
                "dist_km": st.column_config.NumberColumn("Distance (km, vol d'oiseau)", format="%.1f"),
                "nb": st.column_config.NumberColumn("Nb lavages"),
                "prix_med": st.column_config.NumberColumn("Prix médian", format="%.2f €"),
                "prix_min": st.column_config.NumberColumn("Min", format="%.2f €"),
                "prix_max": st.column_config.NumberColumn("Max", format="%.2f €"),
                "dernier_prix": st.column_config.NumberColumn("Dernier prix", format="%.2f €"),
                "dernier_lavage": st.column_config.DateColumn("Dernier lavage", format="DD/MM/YYYY"),
                "precision": "Géocodage",
                "maps": st.column_config.LinkColumn("Maps", display_text="Ouvrir"),
            },
        )

with t_pistes:
    if not center:
        st.info("Choisissez d'abord une position.")
    elif not res_pistes:
        st.info("Cliquez sur « Chercher de nouvelles stations » pour interroger les sources externes.")
    elif df_pistes.empty:
        st.info("Aucune nouvelle station trouvée dans ce rayon. OpenStreetMap est incomplet sur ce type de site : "
                "élargissez le rayon ou activez Google Places.")
    else:
        vue_n = df_pistes[["nom", "adresse", "dist_km", "telephone", "site", "source"]].copy()
        vue_n["prix"] = "À demander"
        vue_n["maps"] = [gmaps_link(a, b) for a, b in zip(df_pistes["lat"], df_pistes["lon"])]
        st.dataframe(
            vue_n, hide_index=True, use_container_width=True,
            column_config={
                "nom": "Station", "adresse": "Adresse",
                "dist_km": st.column_config.NumberColumn("Distance (km)", format="%.1f"),
                "telephone": "Téléphone",
                "site": st.column_config.LinkColumn("Site"),
                "source": "Source", "prix": "Prix",
                "maps": st.column_config.LinkColumn("Maps", display_text="Ouvrir"),
            },
        )
    if not df_new.empty and (df_new["deja_connue"] != "").any():
        with st.expander(f"Résultats écartés car déjà dans l'historique ({(df_new['deja_connue'] != '').sum()})"):
            st.dataframe(df_new[df_new["deja_connue"] != ""][["nom", "adresse", "source", "deja_connue"]]
                         .rename(columns={"deja_connue": "Correspond à"}), hide_index=True)

if t_produit is not None:
    with t_produit:
        if not center or df_proche.empty:
            st.info("Aucune station connue dans le rayon.")
        else:
            lav_zone = df_lav[df_lav["_cle"].isin(df_proche["_cle"])].dropna(subset=["_prix"])
            lav_zone = lav_zone[lav_zone["Produit"].notna()]
            if lav_zone.empty:
                st.info("Pas de lavage avec prix et produit identifiés dans cette zone.")
            else:
                st.markdown("**Prix médian par station et par produit transporté**")
                pivot = lav_zone.pivot_table(index="Produit", columns="Nom 1", values="_prix", aggfunc="median")
                st.dataframe(pivot.style.format("{:.2f} €", na_rep="—").highlight_min(axis=1, color="#1f5e3a"),
                             use_container_width=True)
                st.caption("En vert : station la moins chère pour ce produit dans la zone.")

                st.markdown("**Détail des lavages de la zone**")
                cols_det = [c for c in ["N° Dossier", "Date", "Nom 1", "Localité", "Produit", "Prix",
                                        "Chauffeur", "Tracteur", "Remorque"] if c in lav_zone.columns]
                st.dataframe(lav_zone[cols_det].sort_values("Date", ascending=False),
                             hide_index=True, use_container_width=True)

with t_ref:
    st.markdown("Exportez ce référentiel et rechargez-le au prochain lancement : le géocodage devient instantané. "
                "Vous pouvez corriger à la main les lat/lon des stations mal placées dans le fichier.")
    ref_out = df_st[["_cle", "nom", "localite", "cp", "pays", "lat", "lon", "precision"]].rename(
        columns={"_cle": "cle"})
    echecs = ref_out[ref_out["precision"] == "échec"]
    approx = ref_out[ref_out["precision"] == "localité"]
    r1, r2, r3 = st.columns(3)
    r1.metric("Stations au référentiel", len(ref_out))
    r2.metric("Position approximative", len(approx))
    r3.metric("Non géocodées", len(echecs))
    if not echecs.empty:
        st.dataframe(echecs[["nom", "localite", "cp"]], hide_index=True)
    buf = io.BytesIO()
    ref_out.to_excel(buf, index=False, engine="openpyxl")
    st.download_button("📥 Télécharger le référentiel géocodé", buf.getvalue(),
                       file_name="referentiel_stations_lavage.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ─── Export de la recherche ──────────────────────────────────────────────────
if center and (not df_proche.empty or not df_pistes.empty):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        if not df_proche.empty:
            df_proche.drop(columns=["_cle"]).to_excel(xw, sheet_name="Stations connues", index=False)
        if not df_pistes.empty:
            df_pistes.drop(columns=["deja_connue"]).to_excel(xw, sheet_name="Nouvelles pistes", index=False)
    st.download_button("📥 Exporter cette recherche (Excel)", buf.getvalue(),
                       file_name=f"lavages_autour_{center['lat']:.3f}_{center['lon']:.3f}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
