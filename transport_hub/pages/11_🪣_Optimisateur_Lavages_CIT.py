"""
Page Streamlit : Optimisateur Lavages Citernes — base stations unifiée
- Fusionne l'historique des lavages (prix pratiqués) et l'annuaire des stations
  (adresses, téléphones…) en une seule base, avec rapprochement exact / approchant
- On choisit une position : adresse tapée OU clic sur la carte
- Stations de la base dans le rayon : utilisées (avec prix) et jamais utilisées (annuaire)
- Nouvelles stations potentielles (OpenStreetMap, + Google Places si clé API),
  recherchées à la demande, après affichage de la carte
- Base géocodée exportable : rechargée comme référentiel, plus besoin de regéocoder

Dépendances (requirements.txt) :
    folium
    streamlit-folium
"""

import io
import re
import json
import time
import math
import html
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
.legende { color: #e8f4fd; font-size: 0.85rem; line-height: 2; }
.legende span.item { display: inline-flex; align-items: center; gap: 6px; margin-right: 16px; }
</style>
""", unsafe_allow_html=True)

UA = {"User-Agent": "CB-Transport-Hub/1.0"}
OSM_RAYON_MAX = 100  # km — au-delà, Overpass devient trop lent

# Statuts de la base unifiée
S_HIST_ANN = "Utilisée · dans l'annuaire"
S_HIST = "Utilisée · hors annuaire"
S_HIST_SEUL = "Utilisée"
S_ANN = "Annuaire · jamais utilisée"

# Couleurs des marqueurs
C_VERT, C_ORANGE, C_ROUGE, C_GRIS = "#00a854", "#f57c00", "#e53935", "#78909c"
C_ANNUAIRE = "#00acc1"
C_PISTE = "#aa00ff"
C_CENTRE = "#e53935"


# ─── Utilitaires ─────────────────────────────────────────────────────────────
def normalize(text) -> str:
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return ""
    text = str(text).upper().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"['\-–.,]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


FORMES_JUR = (r"\b(SA|SAS|SASU|SARL|EURL|SNC|SPRL|SRL|SC|NV|BV|BVBA|VOF|GMBH|AG|KG|CO|"
              r"LTD|SPA|SL|ETS|ETABLISSEMENTS|STE|SOCIETE)\b")


def normalize_nom(text) -> str:
    """Nom comparable : sans accents, ponctuation ni forme juridique."""
    s = re.sub(r"[^A-Z0-9 ]", " ", normalize(text))
    s = re.sub(FORMES_JUR, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cp_norm(cp) -> str:
    """'F-57190' / '57190.0' / 'L-1234' → '57190' / '1234'."""
    if cp is None or (isinstance(cp, float) and np.isnan(cp)):
        return ""
    s = re.sub(r"\.0+$", "", str(cp).strip())
    s = re.sub(r"[^A-Z0-9]", "", normalize(s))
    return re.sub(r"^(F|L|D|B|NL|CH|I|E|A|LU|BE|FR|DE)(?=\d)", "", s)


def similarite(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) >= 5 and len(b) >= 5 and (a in b or b in a):
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


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


def parse_coord(val, borne):
    try:
        v = float(str(val).strip().replace(",", "."))
    except (TypeError, ValueError):
        return np.nan
    return v if -borne <= v <= borne and v != 0 else np.nan


def haversine(lat1, lon1, lat2, lon2):
    """Distance vol d'oiseau en km (vectorisé)."""
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def gmaps_link(lat, lon):
    return f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"


def esc(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    return html.escape(str(v))


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
def geocode_station(nom: str, localite: str, cp: str, pays: str = "", adresse: str = ""):
    """
    Géocode une station, du plus précis au moins précis :
    adresse complète (annuaire) → nom de la station → centre de la commune.
    Un résultat n'est accepté que si le CP ou la localité retournés concordent
    (évite les homonymes ailleurs en Europe).
    Retour : (lat, lon, précision) ou None.
    """
    cp_n, loc_n = cp_norm(cp), normalize(localite)

    def concorde(postcode, city):
        return bool((cp_n and cp_norm(postcode) == cp_n) or (loc_n and normalize(city) == loc_n))

    lieu = f"{cp} {localite} {pays}".strip()

    if adresse and lieu:
        q = f"{adresse}, {lieu}"
        for f in _photon(q, limit=3):
            p = f.get("properties", {})
            if concorde(p.get("postcode"), p.get("city")):
                lon, lat = f["geometry"]["coordinates"]
                return float(lat), float(lon), "adresse"
        for d in _nominatim(q, limit=3):
            a = d.get("address", {})
            ville = a.get("city") or a.get("town") or a.get("village") or a.get("municipality")
            if concorde(a.get("postcode"), ville):
                return float(d["lat"]), float(d["lon"]), "adresse"

    for f in _photon(f"{nom}, {lieu}".strip(" ,"), limit=3):
        p = f.get("properties", {})
        if concorde(p.get("postcode"), p.get("city")):
            lon, lat = f["geometry"]["coordinates"]
            return float(lat), float(lon), "station"

    if not lieu:
        return None
    feats = _photon(lieu, limit=1)
    if feats:
        lon, lat = feats[0]["geometry"]["coordinates"]
        return float(lat), float(lon), "localité"
    res = _nominatim(lieu, limit=1)
    if res:
        return float(res[0]["lat"]), float(res[0]["lon"]), "localité"
    return None


PRECISION_LBL = {
    "annuaire": "Coordonnées de l'annuaire",
    "adresse": "Adresse exacte",
    "station": "Nom de la station",
    "localité": "⚠️ Centre de la commune",
    "échec": "❌ Non géocodée",
}


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


# ─── Fonds de carte et frontières ────────────────────────────────────────────
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}"
FONDS = {
    "Clair": {
        "couches": [
            ("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
             "© OpenStreetMap contributors © CARTO", False, 20),
        ],
        "frontiere": "#003087", "halo": "#ffffff", "point": "#0057A8",
    },
    "Sombre": {
        "couches": [
            (ESRI.format("Canvas/World_Dark_Gray_Base"), "Tiles © Esri", False, 16),
            (ESRI.format("Canvas/World_Dark_Gray_Reference"), "© Esri", True, 16),
        ],
        "frontiere": "#ffd54f", "halo": "#000000", "point": "#8ab4f8",
    },
    "Satellite": {
        "couches": [
            (ESRI.format("World_Imagery"), "Tiles © Esri", False, 18),
            (ESRI.format("Reference/World_Boundaries_and_Places"), "© Esri", True, 18),
        ],
        "frontiere": "#ffd54f", "halo": "#000000", "point": "#ffffff",
    },
}

BORDER_URLS = [
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_boundary_lines_land.geojson",
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_boundary_lines_land.geojson",
]
EUROPE_BBOX = (-11.0, 35.0, 32.0, 62.0)  # ouest, sud, est, nord


def _decimer(ligne, pas=0.003):
    """Allège un tracé (~250 m entre points) pour garder une carte rapide."""
    if len(ligne) < 3:
        return [[round(p[0], 4), round(p[1], 4)] for p in ligne]
    out = [ligne[0]]
    for p in ligne[1:-1]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= pas:
            out.append(p)
    out.append(ligne[-1])
    return [[round(p[0], 4), round(p[1], 4)] for p in out]


@st.cache_data(ttl=30 * 86400, show_spinner="Chargement des frontières…")
def load_borders():
    """Frontières terrestres Natural Earth, limitées à l'Europe. Lève une erreur si indisponible
    (pour ne pas mettre un échec en cache)."""
    w, s, e, n = EUROPE_BBOX
    for url in BORDER_URLS:
        try:
            data = _get_json(url, timeout=40)
        except Exception:
            continue
        lignes = []
        for f in data.get("features", []):
            g = f.get("geometry") or {}
            if g.get("type") == "LineString":
                parts = [g["coordinates"]]
            elif g.get("type") == "MultiLineString":
                parts = g["coordinates"]
            else:
                continue
            for l in parts:
                if any(w <= p[0] <= e and s <= p[1] <= n for p in l):
                    lignes.append(_decimer(l))
        if lignes:
            return {"type": "FeatureCollection", "features": [{
                "type": "Feature", "properties": {},
                "geometry": {"type": "MultiLineString", "coordinates": lignes},
            }]}
    raise RuntimeError("frontières indisponibles")


CSS_CARTE = """
<style>
.cb-icon { background: none; border: none; }
.cb-pill {
  display: inline-block; white-space: nowrap; transform: translate(-50%, -50%);
  padding: 2px 7px; border-radius: 11px; border: 2px solid #fff;
  font: 700 12px/1.25 Arial, Helvetica, sans-serif; color: #fff;
  box-shadow: 0 1px 5px rgba(0,0,0,.55); cursor: pointer;
}
.cb-carre {
  width: 14px; height: 14px; transform: translate(-50%, -50%);
  background: #00acc1; border: 2px solid #fff; border-radius: 3px;
  box-shadow: 0 1px 5px rgba(0,0,0,.55); cursor: pointer;
}
.cb-losange {
  width: 14px; height: 14px; transform: translate(-50%, -50%) rotate(45deg);
  background: #aa00ff; border: 2px solid #fff;
  box-shadow: 0 1px 5px rgba(0,0,0,.55); cursor: pointer;
}
.cb-centre {
  width: 22px; height: 22px; transform: translate(-50%, -50%); border-radius: 50%;
  border: 5px solid #e53935; background: rgba(255,255,255,.9);
  box-shadow: 0 0 0 2px #fff, 0 1px 6px rgba(0,0,0,.6);
}
.leaflet-popup-content { font: 13px/1.45 Arial, Helvetica, sans-serif; }
</style>
"""


def icone(cls, texte="", bg=None):
    style = f' style="background:{bg}"' if bg else ""
    return folium.DivIcon(html=f'<div class="{cls}"{style}>{texte}</div>',
                          icon_size=(0, 0), icon_anchor=(0, 0), class_name="cb-icon")


def base_map(fond: str, frontieres):
    cfg = FONDS[fond]
    m = folium.Map(location=[49.8, 5.5], zoom_start=6, tiles=None, control_scale=True)
    for url, attr, overlay, natif in cfg["couches"]:
        folium.TileLayer(tiles=url, attr=attr, name=fond, overlay=overlay, control=False,
                         max_native_zoom=natif, max_zoom=19).add_to(m)
    if frontieres is not None:
        # Halo large puis trait net : la frontière ressort sur n'importe quel fond
        folium.GeoJson(frontieres, name="Frontières halo", control=False,
                       style_function=lambda f, c=cfg["halo"]: {"color": c, "weight": 7, "opacity": 0.75}).add_to(m)
        folium.GeoJson(frontieres, name="Frontières", control=False,
                       style_function=lambda f, c=cfg["frontiere"]: {"color": c, "weight": 2.6, "opacity": 1}).add_to(m)
    m.get_root().header.add_child(folium.Element(CSS_CARTE))
    return m


# ─── Chargement ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_excel(b: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(b), dtype=str)
    df.columns = df.columns.astype(str).str.strip()
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
    return st_df[st_df["nom"] != ""].reset_index(drop=True)


# ─── Annuaire des stations (fichier adresses) ────────────────────────────────
CHAMPS_ANNUAIRE = {
    "nom": ("Nom de la station *", ["NOM 1", "NOM", "RAISON SOCIALE", "STATION", "SOCIETE", "NAME",
                                    "LIBELLE", "DESIGNATION", "ENSEIGNE", "FOURNISSEUR"]),
    "adresse": ("Adresse (rue)", ["ADRESSE", "ADRESSE 1", "RUE", "STREET", "ADDRESS", "VOIE", "STRASSE"]),
    "cp": ("Code postal", ["CODE POSTAL", "CP", "POSTAL", "ZIP", "POSTCODE", "PLZ"]),
    "localite": ("Localité", ["LOCALITE", "VILLE", "COMMUNE", "CITY", "LOCALITY", "ORT"]),
    "pays": ("Pays", ["PAYS", "COUNTRY", "CODE PAYS", "LAND"]),
    "telephone": ("Téléphone", ["TELEPHONE", "TEL", "PHONE", "GSM", "TELEFON"]),
    "email": ("E-mail", ["EMAIL", "E MAIL", "MAIL", "COURRIEL"]),
    "lat": ("Latitude", ["LATITUDE", "LAT"]),
    "lon": ("Longitude", ["LONGITUDE", "LON", "LNG", "LONG"]),
}


def detect_colonnes(colonnes) -> dict:
    """Associe automatiquement les colonnes du fichier aux champs attendus."""
    norm = {c: normalize(c) for c in colonnes}
    pris, out = set(), {}
    for champ, (_, candidats) in CHAMPS_ANNUAIRE.items():
        meilleur, score_max = None, 0
        for col, n in norm.items():
            if col in pris:
                continue
            for i, cand in enumerate(candidats):
                score = 0
                if n == cand:
                    score = 100 - i
                elif len(cand) >= 4 and cand in n:
                    score = 50 - i
                if score > score_max:
                    meilleur, score_max = col, score
        if meilleur:
            out[champ] = meilleur
            pris.add(meilleur)
    return out


@st.cache_data(show_spinner=False)
def build_annuaire(df_a: pd.DataFrame, mapping: tuple) -> pd.DataFrame:
    mp = dict(mapping)
    out = pd.DataFrame(index=df_a.index)
    for champ in CHAMPS_ANNUAIRE:
        col = mp.get(champ)
        out[champ] = df_a[col].fillna("").astype(str).str.strip() if col else ""
    out["cp"] = out["cp"].str.replace(r"\.0+$", "", regex=True)
    out["lat"] = out["lat"].map(lambda v: parse_coord(v, 90))
    out["lon"] = out["lon"].map(lambda v: parse_coord(v, 180))
    out = out[out["nom"] != ""].copy()
    out["_nn"] = out["nom"].map(normalize_nom)
    out["_cpn"] = out["cp"].map(cp_norm)
    out["_locn"] = out["localite"].map(normalize)
    return out.drop_duplicates(["_nn", "_cpn"]).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def build_base(hist: pd.DataFrame, ann: pd.DataFrame | None) -> pd.DataFrame:
    """
    Base unifiée = historique des lavages + annuaire.
    Rapprochement : même CP et nom proche (≥ 75 %), sinon même localité et nom très proche (≥ 85 %).
    Chaque station de l'annuaire n'est rattachée qu'à une seule station de l'historique.
    """
    hist = hist.copy()
    for c in ["adresse", "telephone", "email", "nom_annuaire", "rapprochement"]:
        hist[c] = ""
    hist["lat_ann"], hist["lon_ann"] = np.nan, np.nan

    if ann is None or ann.empty:
        hist["statut"] = S_HIST_SEUL
        return hist

    hist["_nn"] = hist["nom"].map(normalize_nom)
    hist["_cpn"] = hist["cp"].map(cp_norm)
    hist["_locn"] = hist["localite"].map(normalize)

    candidats = []
    for ai, a in ann.iterrows():
        meilleur = None
        if a["_cpn"]:
            for hi, h in hist[hist["_cpn"] == a["_cpn"]].iterrows():
                s = similarite(a["_nn"], h["_nn"])
                if s >= 0.75 and (meilleur is None or s > meilleur[0]):
                    meilleur = (s, hi, "exact" if s == 1 else "approchant")
        if meilleur is None and a["_locn"]:
            for hi, h in hist[hist["_locn"] == a["_locn"]].iterrows():
                s = similarite(a["_nn"], h["_nn"])
                if s >= 0.85 and (meilleur is None or s > meilleur[0]):
                    meilleur = (s, hi, "même localité")
        if meilleur:
            candidats.append((meilleur[0], ai, meilleur[1], meilleur[2]))

    candidats.sort(key=lambda x: -x[0])
    pris_h, pris_a = set(), set()
    for s, ai, hi, t in candidats:
        if hi in pris_h or ai in pris_a:
            continue
        pris_h.add(hi)
        pris_a.add(ai)
        a = ann.loc[ai]
        for c in ["adresse", "telephone", "email"]:
            hist.at[hi, c] = a[c]
        hist.at[hi, "nom_annuaire"] = a["nom"]
        hist.at[hi, "rapprochement"] = "exact" if t == "exact" else f"{t} ({s:.0%})"
        hist.at[hi, "lat_ann"] = a["lat"]
        hist.at[hi, "lon_ann"] = a["lon"]
        if not hist.at[hi, "pays"] and a["pays"]:
            hist.at[hi, "pays"] = a["pays"]
    hist["statut"] = np.where(hist.index.isin(list(pris_h)), S_HIST_ANN, S_HIST)

    seules = ann[~ann.index.isin(list(pris_a))]
    nouv = pd.DataFrame({
        "_cle": seules["nom"].map(normalize) + "|" + seules["cp"],
        "nom": seules["nom"], "localite": seules["localite"], "cp": seules["cp"], "pays": seules["pays"],
        "nb": 0, "prix_med": np.nan, "prix_min": np.nan, "prix_max": np.nan,
        "dernier_prix": np.nan, "dernier_lavage": pd.NaT,
        "adresse": seules["adresse"], "telephone": seules["telephone"], "email": seules["email"],
        "nom_annuaire": seules["nom"], "rapprochement": "",
        "lat_ann": seules["lat"], "lon_ann": seules["lon"],
        "statut": S_ANN,
    })
    base = pd.concat([hist.drop(columns=["_nn", "_cpn", "_locn"]), nouv], ignore_index=True)
    return base.drop_duplicates("_cle").reset_index(drop=True)


def prepare_pistes(trouves, center, rayon, df_geo):
    """Filtre au rayon, dédoublonne, et marque ce qui est déjà dans la base (historique + annuaire)."""
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
        if df_geo.empty:
            return ""
        d = haversine(r["lat"], r["lon"], df_geo["lat"].values, df_geo["lon"].values)
        proches = df_geo[d < 5].assign(_d=d[d < 5])
        for _, k in proches.iterrows():
            sim = similarite(normalize_nom(r["nom"]), normalize_nom(k["nom"]))
            if k["_d"] < 0.4 or sim > 0.75:
                return k["nom"]
        return ""

    df_new["deja_connue"] = df_new.apply(deja_connue, axis=1)
    return df_new.sort_values("dist_km")


def excel_auto(sheets: dict) -> bytes:
    """Export Excel multi-onglets avec largeurs de colonnes ajustées."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for nom, df in sheets.items():
            df.to_excel(xw, sheet_name=nom[:31], index=False)
            ws = xw.sheets[nom[:31]]
            ws.freeze_panes = "A2"
            for i, col in enumerate(df.columns, start=1):
                largeur = max([len(str(col))] + [len(str(v)) for v in df[col].head(300).tolist()])
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(max(largeur + 2, 8), 50)
    return buf.getvalue()


# ─── En-tête ─────────────────────────────────────────────────────────────────
st.markdown("## 🪣 Optimisateur Lavages Citernes")
st.caption("Choisissez une position (adresse ou clic sur la carte) : stations déjà utilisées avec leurs prix, "
           "stations de l'annuaire jamais utilisées, et nouvelles stations à démarcher.")
st.divider()

c1, c2, c3, c4 = st.columns(4)
with c1:
    lavages_file = st.file_uploader("🧼 Fichier Lavages (obligatoire)", type=["xlsx", "xls"], key="lavages",
                                    help="liste_lavages : N° Dossier, Date, Nom 1, Localité, Code postal, Prix…")
with c2:
    annuaire_file = st.file_uploader("📒 Fichier adresses stations (optionnel)", type=["xlsx", "xls"], key="annuaire",
                                     help="Annuaire des stations de lavage : nom, adresse, CP, localité, téléphone…")
with c3:
    missions_file = st.file_uploader("📋 Fichier Missions CA CIT (optionnel)", type=["xlsx", "xls"], key="missions",
                                     help="Sert à afficher les prix par produit transporté")
with c4:
    ref_file = st.file_uploader("📍 Base / référentiel géocodé (optionnel)", type=["xlsx"], key="ref",
                                help="Export de l'onglet Base stations : évite de regéocoder toutes les stations")

if not lavages_file:
    st.info("👆 Chargez au minimum le fichier lavages pour démarrer")
    st.stop()

try:
    df_l_raw = load_excel(lavages_file.getvalue())
    df_m_raw = load_excel(missions_file.getvalue()) if missions_file else None
    df_a_raw = load_excel(annuaire_file.getvalue()) if annuaire_file else None
except Exception as e:
    st.error(f"❌ Lecture impossible : {e}")
    st.stop()

manquantes = [c for c in ["Nom 1", "Localité", "Code postal"] if c not in df_l_raw.columns]
if manquantes:
    st.error(f"❌ Colonnes manquantes dans le fichier lavages : {', '.join(manquantes)}")
    st.stop()

# ─── Correspondance des colonnes de l'annuaire ───────────────────────────────
df_ann = None
if df_a_raw is not None:
    detect = detect_colonnes(df_a_raw.columns)
    options = ["—"] + list(df_a_raw.columns)
    with st.expander("🔗 Colonnes du fichier adresses (détectées automatiquement — corrigez si besoin)",
                     expanded="nom" not in detect):
        cols = st.columns(3)
        mapping = {}
        for i, (champ, (lbl, _)) in enumerate(CHAMPS_ANNUAIRE.items()):
            defaut = detect.get(champ)
            choix_col = cols[i % 3].selectbox(lbl, options, index=options.index(defaut) if defaut else 0,
                                              key=f"map_{champ}")
            mapping[champ] = None if choix_col == "—" else choix_col
        st.caption(f"{len(df_a_raw)} ligne(s) dans le fichier adresses.")
    if not mapping["nom"]:
        st.warning("Indiquez la colonne « Nom de la station » pour fusionner le fichier adresses.")
    elif not any(mapping[c] for c in ["cp", "localite", "adresse", "lat"]):
        st.warning("Le fichier adresses doit contenir au moins un CP, une localité, une adresse ou des coordonnées.")
    else:
        df_ann = build_annuaire(df_a_raw, tuple(sorted(mapping.items())))

df_lav = build_lavages(df_l_raw, df_m_raw)
df_hist = build_stations(df_lav)
if df_hist.empty:
    st.error("❌ Aucune station exploitable dans le fichier lavages (colonne Nom 1 vide).")
    st.stop()
df_base = build_base(df_hist, df_ann)
has_produit = "Produit" in df_lav.columns
has_ann = df_ann is not None

# ─── Géocodage (référentiel > coordonnées annuaire > géocodage) ─────────────
coords = st.session_state.setdefault("coords", {})

ref_sig = (ref_file.name, ref_file.size) if ref_file else None
if ref_file and st.session_state.get("ref_charge") != ref_sig:
    try:
        ref = load_excel(ref_file.getvalue())
        for _, r in ref.dropna(subset=["cle", "lat", "lon"]).iterrows():
            prec = r.get("precision")
            coords[r["cle"]] = (float(str(r["lat"]).replace(",", ".")), float(str(r["lon"]).replace(",", ".")),
                                prec if isinstance(prec, str) and prec else "référentiel")
        st.session_state["ref_charge"] = ref_sig
    except Exception as e:
        st.warning(f"Référentiel ignoré ({e}) — colonnes attendues : cle, lat, lon, precision")

for k, la, lo in df_base.loc[df_base["lat_ann"].notna() & df_base["lon_ann"].notna(),
                             ["_cle", "lat_ann", "lon_ann"]].itertuples(index=False):
    actuel = coords.get(k)
    if actuel is None or actuel[2] in ("localité", "échec", "station"):
        coords[k] = (float(la), float(lo), "annuaire")

regeo_fait = st.session_state.setdefault("regeo_fait", set())


def a_geocoder(r) -> bool:
    c = coords.get(r["_cle"])
    if c is None:
        return True
    # Position approximative alors qu'on a maintenant l'adresse exacte : on retente une fois
    return c[2] in ("localité", "échec") and bool(r["adresse"]) and r["_cle"] not in regeo_fait


todo = df_base[df_base.apply(a_geocoder, axis=1)]
if not todo.empty:
    bar = st.progress(0, text=f"Géocodage de {len(todo)} station(s)… (une seule fois — exportez ensuite la base)")
    for i, (_, r) in enumerate(todo.iterrows()):
        res = geocode_station(r["nom"], r["localite"], r["cp"], r["pays"], r["adresse"])
        if res:
            coords[r["_cle"]] = res
        elif r["_cle"] not in coords:
            coords[r["_cle"]] = (np.nan, np.nan, "échec")
        regeo_fait.add(r["_cle"])
        bar.progress((i + 1) / len(todo), text=f"Géocodage {i + 1}/{len(todo)} — {r['nom']}")
    bar.empty()

df_base["lat"] = df_base["_cle"].map(lambda k: coords.get(k, (np.nan,) * 3)[0])
df_base["lon"] = df_base["_cle"].map(lambda k: coords.get(k, (np.nan,) * 3)[1])
df_base["precision"] = df_base["_cle"].map(lambda k: coords.get(k, (np.nan,) * 3)[2])
df_geo = df_base.dropna(subset=["lat", "lon"]).copy()

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

sig = None
if center:
    sig = (round(center["lat"], 3), round(center["lon"], 3), rayon, use_osm, bool(use_google and google_key))
pistes_cache = st.session_state.setdefault("pistes_cache", {})
if lancer and sig not in pistes_cache:
    st.session_state["recherche_en_attente"] = sig

# ─── Stations de la base autour (instantané) ─────────────────────────────────
df_proche = pd.DataFrame()
if center and not df_geo.empty:
    df_geo["dist_km"] = haversine(center["lat"], center["lon"], df_geo["lat"], df_geo["lon"])
    df_proche = df_geo[df_geo["dist_km"] <= rayon].sort_values("dist_km").copy()
proche_hist = df_proche[df_proche["nb"] > 0] if not df_proche.empty else pd.DataFrame()
proche_ann = df_proche[df_proche["nb"] == 0] if not df_proche.empty else pd.DataFrame()

res_pistes = pistes_cache.get(sig) if sig else None
df_new = prepare_pistes(res_pistes["trouves"], center, rayon, df_geo) if res_pistes else pd.DataFrame()
df_pistes = df_new[df_new["deja_connue"] == ""] if not df_new.empty else pd.DataFrame()

# ─── KPIs ────────────────────────────────────────────────────────────────────
if center:
    st.markdown(f"### 📍 {center['label']} — rayon {rayon} km")
    k = st.columns(5)
    prix_ok = proche_hist.dropna(subset=["prix_med"]) if not proche_hist.empty else pd.DataFrame()
    prix_zone = prix_ok["prix_med"].median() if not prix_ok.empty else np.nan
    moins_chere = prix_ok.sort_values("prix_med").iloc[0] if not prix_ok.empty else None
    vals = [
        (len(proche_hist), "Stations déjà utilisées"),
        (len(proche_ann) if has_ann else "—", "Annuaire, jamais utilisées"),
        (len(df_pistes) if res_pistes else "—", "Nouvelles pistes"),
        (f"{prix_zone:.0f} €" if pd.notna(prix_zone) else "—", "Prix médian zone"),
        (f"{moins_chere['prix_med']:.0f} €" if moins_chere is not None else "—",
         f"Moins chère : {moins_chere['nom'][:28]}" if moins_chere is not None else "Moins chère"),
    ]
    for col, (v, lbl) in zip(k, vals):
        col.markdown(f'<div class="kpi-box"><div class="kpi-val">{v}</div><div class="kpi-lbl">{lbl}</div></div>',
                     unsafe_allow_html=True)
    if res_pistes and res_pistes["osm_erreur"]:
        st.warning("OpenStreetMap n'a pas répondu à temps — relancez la recherche dans une minute.")
    if use_osm and rayon > OSM_RAYON_MAX:
        st.caption(f"ℹ️ La recherche OpenStreetMap est limitée à {OSM_RAYON_MAX} km pour rester rapide.")

# ─── Carte ───────────────────────────────────────────────────────────────────
cm1, cm2, _ = st.columns([2, 2, 4])
with cm1:
    fond = st.radio("Fond de carte", list(FONDS), horizontal=True, key="fond_carte")
with cm2:
    st.write("")
    show_borders = st.checkbox("Frontières renforcées", value=True)

frontieres = None
if show_borders:
    try:
        frontieres = load_borders()
    except Exception:
        st.caption("⚠️ Tracé des frontières indisponible pour le moment (GitHub injoignable).")

cfg = FONDS[fond]
m = base_map(fond, frontieres)

if center:
    dlat = rayon / 111.0
    dlon = rayon / (111.0 * max(math.cos(math.radians(center["lat"])), 0.1))
    m.fit_bounds([[center["lat"] - dlat, center["lon"] - dlon], [center["lat"] + dlat, center["lon"] + dlon]])
    folium.Circle([center["lat"], center["lon"]], radius=rayon * 1000,
                  color=C_CENTRE, weight=2, dash_array="6 6", fill=True, fill_opacity=0.05).add_to(m)
elif not df_geo.empty:
    m.fit_bounds([[df_geo["lat"].min(), df_geo["lon"].min()], [df_geo["lat"].max(), df_geo["lon"].max()]])

# Stations hors rayon : petits points lisibles (bord blanc)
ids_proches = set(df_proche["_cle"]) if not df_proche.empty else set()
for _, r in df_geo[~df_geo["_cle"].isin(ids_proches)].iterrows():
    remplissage = C_ANNUAIRE if r["nb"] == 0 else cfg["point"]
    folium.CircleMarker([r["lat"], r["lon"]], radius=5, color="#ffffff", weight=1.5,
                        fill=True, fill_color=remplissage, fill_opacity=0.95,
                        tooltip=f"{r['nom']} ({r['localite']})").add_to(m)


def popup_station(r) -> str:
    lignes = [f"<b>{esc(r['nom'])}</b>"]
    if r["adresse"]:
        lignes.append(esc(r["adresse"]))
    lignes.append(f"{esc(r['cp'])} {esc(r['localite'])} {esc(r['pays'])}".strip())
    if r["nb"] > 0:
        p = r["prix_med"]
        prix_txt = "—" if pd.isna(p) else f"{p:.2f} € (min {r['prix_min']:.2f} / max {r['prix_max']:.2f})"
        date_txt = r["dernier_lavage"].strftime("%d/%m/%Y") if pd.notna(r["dernier_lavage"]) else "—"
        lignes.append(f"💶 Prix médian : {prix_txt}")
        lignes.append(f"🧼 {r['nb']} lavage(s) — dernier le {date_txt}")
    else:
        lignes.append("📒 Dans l'annuaire, jamais utilisée — prix à demander")
    if r["telephone"]:
        lignes.append(f"📞 {esc(r['telephone'])}")
    if r["email"]:
        lignes.append(f"✉️ {esc(r['email'])}")
    lignes.append(f"📏 {r['dist_km']:.1f} km")
    if r["precision"] == "localité":
        lignes.append("<i>⚠️ position approximative (centre de la commune)</i>")
    lignes.append(f"<a href='{gmaps_link(r['lat'], r['lon'])}' target='_blank'>Ouvrir dans Google Maps</a>")
    return "<br>".join(lignes)


# Stations jamais utilisées (annuaire) : carré turquoise
for _, r in proche_ann.iterrows():
    folium.Marker([r["lat"], r["lon"]], tooltip=f"📒 {r['nom']} — jamais utilisée",
                  popup=folium.Popup(popup_station(r), max_width=320),
                  icon=icone("cb-carre")).add_to(m)

# Stations utilisées : pastille avec le prix, couleur selon le tiers de prix de la zone
if not proche_hist.empty:
    prix_dispo = proche_hist["prix_med"].dropna()
    q1, q2 = (prix_dispo.quantile(1 / 3), prix_dispo.quantile(2 / 3)) if len(prix_dispo) >= 3 else (np.inf, np.inf)
    for _, r in proche_hist.iterrows():
        p = r["prix_med"]
        couleur = C_GRIS if pd.isna(p) else (C_VERT if p <= q1 else C_ORANGE if p <= q2 else C_ROUGE)
        texte = "? €" if pd.isna(p) else f"{p:.0f} €"
        folium.Marker([r["lat"], r["lon"]], tooltip=f"{r['nom']} — {texte}",
                      popup=folium.Popup(popup_station(r), max_width=320),
                      icon=icone("cb-pill", texte, couleur)).add_to(m)

# Nouvelles pistes : losange violet
if not df_pistes.empty:
    for _, r in df_pistes.iterrows():
        popup = (f"<b>{esc(r['nom'])}</b><br>{esc(r['adresse']) or '(adresse non renseignée)'}<br>"
                 f"🆕 Jamais utilisée — prix à demander<br>📏 {r['dist_km']:.1f} km — source {r['source']}<br>"
                 + (f"📞 {esc(r['telephone'])}<br>" if r["telephone"] else "")
                 + (f"<a href='{esc(r['site'])}' target='_blank'>Site web</a><br>" if r["site"] else "")
                 + f"<a href='{gmaps_link(r['lat'], r['lon'])}' target='_blank'>Ouvrir dans Google Maps</a>")
        folium.Marker([r["lat"], r["lon"]], tooltip=f"🆕 {r['nom']}",
                      popup=folium.Popup(popup, max_width=320),
                      icon=icone("cb-losange")).add_to(m)

if center:
    folium.Marker([center["lat"], center["lon"]], tooltip=center["label"], icon=icone("cb-centre")).add_to(m)

st.caption("🖱️ Cliquez n'importe où sur la carte pour y placer le centre de recherche.")
carte = st_folium(m, height=640, use_container_width=True, returned_objects=["last_clicked"], key="carte_lavages")


def item_leg(forme_css, texte):
    return f'<span class="item"><span style="{forme_css}"></span>{texte}</span>'


pill = "display:inline-block;width:26px;height:14px;border-radius:7px;border:2px solid #fff;background:{}"
st.markdown(
    '<div class="legende">'
    + item_leg(pill.format(C_VERT), "moins cher de la zone")
    + item_leg(pill.format(C_ORANGE), "prix moyen")
    + item_leg(pill.format(C_ROUGE), "plus cher")
    + item_leg(pill.format(C_GRIS), "prix inconnu")
    + item_leg(f"display:inline-block;width:12px;height:12px;border-radius:3px;border:2px solid #fff;background:{C_ANNUAIRE}",
               "annuaire, jamais utilisée")
    + item_leg(f"display:inline-block;width:11px;height:11px;transform:rotate(45deg);border:2px solid #fff;background:{C_PISTE}",
               "nouvelle piste")
    + item_leg(f"display:inline-block;width:12px;height:12px;border-radius:50%;border:4px solid {C_CENTRE};background:#fff",
               "centre de recherche")
    + item_leg(f"display:inline-block;width:10px;height:10px;border-radius:50%;border:2px solid #fff;background:{cfg['point']}",
               "station hors rayon")
    + "</div>",
    unsafe_allow_html=True,
)

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
onglets = ["🧼 Stations dans le rayon", "🆕 Nouvelles pistes"]
if has_produit:
    onglets.append("💶 Prix par produit")
if has_ann:
    onglets.append("🔗 Rapprochement")
onglets.append("🗄️ Base stations")
tabs = st.tabs(onglets)
t_connues, t_pistes = tabs[0], tabs[1]
t_produit = tabs[onglets.index("💶 Prix par produit")] if has_produit else None
t_rappro = tabs[onglets.index("🔗 Rapprochement")] if has_ann else None
t_base = tabs[-1]

with t_connues:
    if not center:
        st.info("Choisissez d'abord une position.")
    elif df_proche.empty:
        st.info(f"Aucune station de la base dans un rayon de {rayon} km. Lancez la recherche de nouvelles stations.")
    else:
        statuts = sorted(df_proche["statut"].unique())
        filtre = st.multiselect("Statut", statuts, default=statuts)
        vue = df_proche[df_proche["statut"].isin(filtre)]
        vue = vue[["statut", "nom", "adresse", "localite", "cp", "dist_km", "nb", "prix_med", "prix_min",
                   "prix_max", "dernier_prix", "dernier_lavage", "telephone", "email", "precision",
                   "lat", "lon"]].copy()
        vue["precision"] = vue["precision"].map(lambda p: PRECISION_LBL.get(p, p))
        vue["maps"] = [gmaps_link(a, b) for a, b in zip(vue["lat"], vue["lon"])]
        st.dataframe(
            vue.drop(columns=["lat", "lon"]), hide_index=True, use_container_width=True,
            column_config={
                "statut": "Statut", "nom": "Station", "adresse": "Adresse", "localite": "Localité", "cp": "CP",
                "dist_km": st.column_config.NumberColumn("Distance (km, vol d'oiseau)", format="%.1f"),
                "nb": st.column_config.NumberColumn("Nb lavages"),
                "prix_med": st.column_config.NumberColumn("Prix médian", format="%.2f €"),
                "prix_min": st.column_config.NumberColumn("Min", format="%.2f €"),
                "prix_max": st.column_config.NumberColumn("Max", format="%.2f €"),
                "dernier_prix": st.column_config.NumberColumn("Dernier prix", format="%.2f €"),
                "dernier_lavage": st.column_config.DateColumn("Dernier lavage", format="DD/MM/YYYY"),
                "telephone": "Téléphone", "email": "E-mail",
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
        with st.expander(f"Résultats écartés car déjà dans la base ({(df_new['deja_connue'] != '').sum()})"):
            st.dataframe(df_new[df_new["deja_connue"] != ""][["nom", "adresse", "source", "deja_connue"]]
                         .rename(columns={"deja_connue": "Correspond à"}), hide_index=True)

if t_produit is not None:
    with t_produit:
        if not center or proche_hist.empty:
            st.info("Aucune station utilisée dans le rayon.")
        else:
            lav_zone = df_lav[df_lav["_cle"].isin(proche_hist["_cle"])].dropna(subset=["_prix"])
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

if t_rappro is not None:
    with t_rappro:
        n_exact = (df_base["rapprochement"] == "exact").sum()
        approchants = df_base[df_base["rapprochement"].str.len() > 0]
        approchants = approchants[approchants["rapprochement"] != "exact"]
        hors_ann = df_base[df_base["statut"] == S_HIST]
        jamais = df_base[df_base["statut"] == S_ANN]
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Rapprochements exacts", int(n_exact))
        r2.metric("Rapprochements approchants", len(approchants))
        r3.metric("Utilisées, absentes de l'annuaire", len(hors_ann))
        r4.metric("Annuaire, jamais utilisées", len(jamais))

        st.markdown("**Rapprochements approchants — à vérifier**")
        if approchants.empty:
            st.caption("Aucun.")
        else:
            st.dataframe(approchants[["nom", "nom_annuaire", "cp", "localite", "rapprochement"]]
                         .rename(columns={"nom": "Nom (historique lavages)", "nom_annuaire": "Nom (annuaire)",
                                          "cp": "CP", "localite": "Localité", "rapprochement": "Type"}),
                         hide_index=True, use_container_width=True)
            st.caption("Si un rapprochement est faux, corrigez le nom ou le CP dans le fichier adresses "
                       "pour qu'il corresponde au « Nom 1 » des lavages.")

        st.markdown("**Stations utilisées mais absentes de l'annuaire**")
        if hors_ann.empty:
            st.caption("Aucune.")
        else:
            st.dataframe(hors_ann[["nom", "cp", "localite", "pays", "nb", "dernier_lavage"]]
                         .sort_values("nb", ascending=False),
                         hide_index=True, use_container_width=True,
                         column_config={"dernier_lavage": st.column_config.DateColumn("Dernier lavage",
                                                                                     format="DD/MM/YYYY")})

with t_base:
    st.markdown("Exportez cette base et rechargez-la au prochain lancement (champ « Base / référentiel ») : "
                "le géocodage devient instantané. Vous pouvez corriger à la main les lat/lon des stations mal placées.")
    base_out = df_base[["_cle", "statut", "nom", "adresse", "cp", "localite", "pays", "telephone", "email",
                        "nb", "prix_med", "prix_min", "prix_max", "dernier_prix", "dernier_lavage",
                        "lat", "lon", "precision", "rapprochement", "nom_annuaire"]].rename(columns={"_cle": "cle"})
    echecs = base_out[base_out["precision"] == "échec"]
    approx = base_out[base_out["precision"] == "localité"]
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Stations dans la base", len(base_out))
    b2.metric("Dont jamais utilisées", int((base_out["nb"] == 0).sum()))
    b3.metric("Position approximative", len(approx))
    b4.metric("Non géocodées", len(echecs))
    if not echecs.empty:
        st.markdown("**Non géocodées**")
        st.dataframe(echecs[["nom", "adresse", "localite", "cp"]], hide_index=True)
    base_xls = base_out.copy()
    base_xls["dernier_lavage"] = base_xls["dernier_lavage"].dt.date
    st.download_button("📥 Télécharger la base stations géocodée", excel_auto({"Base stations": base_xls}),
                       file_name="base_stations_lavage.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ─── Export de la recherche ──────────────────────────────────────────────────
if center and (not df_proche.empty or not df_pistes.empty):
    internes = ["_cle", "lat_ann", "lon_ann"]
    feuilles = {}
    if not proche_hist.empty:
        feuilles["Stations utilisées"] = proche_hist.drop(columns=internes, errors="ignore")
    if not proche_ann.empty:
        feuilles["Annuaire non utilisées"] = proche_ann.drop(
            columns=internes + ["nb", "prix_med", "prix_min", "prix_max", "dernier_prix", "dernier_lavage"],
            errors="ignore")
    if not df_pistes.empty:
        feuilles["Nouvelles pistes"] = df_pistes.drop(columns=["deja_connue"])
    for f in feuilles.values():
        if "dernier_lavage" in f.columns:
            f["dernier_lavage"] = f["dernier_lavage"].dt.date
    st.download_button("📥 Exporter cette recherche (Excel)", excel_auto(feuilles),
                       file_name=f"lavages_autour_{center['lat']:.3f}_{center['lon']:.3f}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
