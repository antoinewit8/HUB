"""
4____Missions_CA_KM.py
──────────────────────────────────────────────────────────────────
Outil TX-FLEX : Analyse Missions + CA + Calcul KM PTV
──────────────────────────────────────────────────────────────────
Entrées :
  • Fichier Missions  (.xlsx) — colonnes : N°Dossier, Activité, Date, Heure,
                                Nom1, Adresse, Numéro, Code pays, CP, Localité,
                                Chauffeur, Immat. tracteur
  • Fichier CA        (.xlsx) — colonnes : N°Dossier, Prix transport, Total vente

Sorties :
  • Tableau consolidé par chauffeur/dossier avec stops + CA
  • Calcul PTV : km totaux (chaîne complète) + km à vide (DECHARGER→CHARGER)
  • Export Excel
──────────────────────────────────────────────────────────────────
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
import os
import io
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

load_dotenv()

# ══════════════════════════════════════════════════════════════════
#  CONFIG PTV
# ══════════════════════════════════════════════════════════════════

PTV_API_KEY  = os.environ.get("PTV_API_KEY", "")
PTV_BASE_URL = "https://api.myptv.com/routing/v1"
HEADERS      = {"apiKey": PTV_API_KEY}
MAX_RETRIES  = 3
RETRY_DELAY  = 2
MAX_WORKERS  = 4
VEHICLE      = "EUR_TRAILER_TRUCK"

# ══════════════════════════════════════════════════════════════════
#  RÉUTILISATION DES CONSTANTES DE excel_handler_km
#  (PAYS_MAP, CP_LENGTHS, ZONE_CORRECTIONS, CITY_CORRECTIONS, GPS_FIXES_ORIGIN)
#  et des fonctions de ptv_router_km (geocode_address)
# ══════════════════════════════════════════════════════════════════

try:
    from excel_handler_km import (
        PAYS_MAP, CP_LENGTHS, ZONE_CORRECTIONS,
        CITY_CORRECTIONS, GPS_FIXES_ORIGIN,
        parse_origin_from_parts,
    )
    from ptv_router_km import geocode_address as _ptv_geocode_address
    _IMPORTS_OK = True
except ImportError:
    _IMPORTS_OK = False
    # Fallback minimal si l'import échoue (exécution hors package TX-FLEX)
    PAYS_MAP = {
        "F": "France", "B": "Belgium", "D": "Germany", "L": "Luxembourg",
        "NL": "Netherlands", "E": "Spain", "I": "Italy", "CH": "Switzerland",
        "GB": "United Kingdom", "A": "Austria", "P": "Portugal",
        "FR": "France", "BE": "Belgium", "DE": "Germany", "LU": "Luxembourg",
    }
    CP_LENGTHS        = {}
    ZONE_CORRECTIONS  = {}
    CITY_CORRECTIONS  = {}
    GPS_FIXES_ORIGIN  = {}

    def parse_origin_from_parts(city, cp, country):
        pays_full = PAYS_MAP.get(str(country).strip().upper(), country)
        return ", ".join(p for p in [city, cp, pays_full] if p and p != "nan")

    def _ptv_geocode_address(address):
        return None


@st.cache_data(show_spinner=False)
def geocode_address(address: str):
    """
    Délègue à ptv_router_km.geocode_address (même logique :
    GPS_FIXES → by-postal-code → by-text).
    """
    address = str(address).strip()
    if not address or address.lower() in ("nan", ""):
        return None
    return _ptv_geocode_address(address)


# Correspondance code court → ISO2 pour l'endpoint by-postal-code
PAYS_TO_ISO2 = {
    "F": "FR", "B": "BE", "D": "DE", "L": "LU", "I": "IT",
    "E": "ES", "A": "AT", "P": "PT", "CH": "CH", "GB": "GB",
    "NL": "NL", "FR": "FR", "BE": "BE", "DE": "DE", "LU": "LU",
    "IT": "IT", "ES": "ES", "AT": "AT", "PT": "PT",
}

def _ptv_by_text(query: str) -> tuple | None:
    """Appel direct PTV by-text, sans cache."""
    if not query:
        return None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                "https://api.myptv.com/geocoding/v1/locations/by-text",
                params={"searchText": query},
                headers=HEADERS,
                timeout=15,
            )
            if resp.status_code == 429:
                time.sleep(RETRY_DELAY * attempt)
                continue
            if resp.status_code != 200:
                return None
            locs = resp.json().get("locations", [])
            if locs:
                pos = locs[0]["referencePosition"]
                return (pos["latitude"], pos["longitude"])
            return None
        except Exception:
            time.sleep(RETRY_DELAY)
    return None


def _ptv_by_postal_code(cp: str, iso2: str) -> tuple | None:
    """Appel direct PTV by-postal-code, sans cache."""
    if not cp or not iso2:
        return None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                "https://api.myptv.com/geocoding/v1/locations/by-postal-code",
                params={"postalCode": cp, "countryCode": iso2},
                headers=HEADERS,
                timeout=15,
            )
            if resp.status_code == 429:
                time.sleep(RETRY_DELAY * attempt)
                continue
            if resp.status_code in (400, 404):
                return None
            if resp.status_code != 200:
                return None
            locs = resp.json().get("locations", [])
            if locs:
                pos = locs[0]["referencePosition"]
                return (pos["latitude"], pos["longitude"])
            return None
        except Exception:
            time.sleep(RETRY_DELAY)
    return None


def geocode_with_fallback(adresse_complete: str, ville: str, cp: str, pays: str) -> tuple | None:
    """
    Géocodage en cascade — appels directs PTV sans cache intermédiaire :
    1. ville + CP + pays  (le plus fiable : pas de bruit de rue)
    2. CP seul via by-postal-code
    3. ville + pays
    4. Adresse complète en dernier recours
    Retourne (lat, lon) ou None.
    """
    pays_full = PAYS_MAP.get(pays.upper(), pays) if pays else ""
    iso2      = PAYS_TO_ISO2.get(pays.upper(), pays.upper() if len(pays) == 2 else "")

    # Niveau 1 : ville + CP + pays (requête propre, très bien géocodée par PTV)
    if ville and cp and pays_full:
        r = _ptv_by_text(f"{ville}, {cp}, {pays_full}")
        if r: return r

    # Niveau 2 : by-postal-code (endpoint dédié, très fiable)
    if cp and iso2:
        r = _ptv_by_postal_code(cp, iso2)
        if r: return r

    # Niveau 3 : ville + pays
    if ville and pays_full:
        r = _ptv_by_text(f"{ville}, {pays_full}")
        if r: return r

    # Niveau 4 : adresse complète (parfois trop de bruit pour PTV)
    if adresse_complete:
        r = _ptv_by_text(adresse_complete)
        if r: return r

    return None


def build_address_string(row: pd.Series) -> str:
    """
    Construit une adresse géocodable depuis les colonnes exactes de l'export missions :
      Localité (M) + Code postal (L) + Code pays (J) → via parse_origin_from_parts
      + préfixe rue si Adresse (H) et/ou Numéro (I) présents.

    Réutilise PAYS_MAP, CP_LENGTHS, CITY_CORRECTIONS de excel_handler_km.
    """
    def clean(v): 
        v = str(v or "").strip()
        return "" if v.lower() in ("nan", "none") else v

    ville   = clean(row.get("localite",    ""))
    cp      = clean(row.get("code_postal", ""))
    pays    = clean(row.get("code_pays",   "")).upper()
    adresse = clean(row.get("adresse",     ""))
    numero  = clean(row.get("numero",      ""))
    nom     = clean(row.get("nom1",        ""))

    # Construction via parse_origin_from_parts (gère PAYS_MAP + CP_LENGTHS + corrections)
    addr = parse_origin_from_parts(ville, cp, pays)

    # Rue = "Numéro Adresse" si les deux sont présents
    rue = " ".join(p for p in [numero, adresse] if p).strip()

    if rue and addr:
        addr = f"{rue}, {addr}"
    elif rue:
        addr = rue

    # Fallback sur le nom de l'entreprise si rien d'autre
    return addr if addr else nom


# ══════════════════════════════════════════════════════════════════
#  CALCUL ROUTE PTV
# ══════════════════════════════════════════════════════════════════

def calculate_route(coords_list: list) -> dict | None:
    """
    Calcule un itinéraire PTV pour une liste de coordonnées (lat, lon).
    Retourne {"km": float, "travel_time_h": float} ou None.
    """
    if len(coords_list) < 2:
        return None

    query_params = [
        ("profile", VEHICLE),
        ("results", "NONE"),
    ]
    for i, (lat, lon) in enumerate(coords_list):
        if 0 < i < len(coords_list) - 1:
            query_params.append(("waypoints", f"{lat},{lon};radius=5000"))
        else:
            query_params.append(("waypoints", f"{lat},{lon}"))

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                f"{PTV_BASE_URL}/routes",
                headers=HEADERS,
                params=query_params,
                timeout=30,
            )
            if resp.status_code != 200:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                return None
            data = resp.json()
            return {
                "km":           round(data.get("distance", 0) / 1000, 1),
                "travel_time_h": round(data.get("travelTime", 0) / 3600, 2),
            }
        except Exception:
            time.sleep(RETRY_DELAY)
    return None


# ══════════════════════════════════════════════════════════════════
#  PARSING FICHIER MISSIONS
# ══════════════════════════════════════════════════════════════════

ACTIVITE_KEYWORDS = {
    "charger":       "CHARGEMENT",
    "chargement":    "CHARGEMENT",
    "décharger":     "DECHARGEMENT",
    "dechargement":  "DECHARGEMENT",
    "déchargement":  "DECHARGEMENT",
    "decharger":     "DECHARGEMENT",
    "douane":        "DOUANE",
    "transit":       "DOUANE",
}

def normalize_activite(val: str) -> str:
    v = str(val).strip().lower()
    for kw, mapped in ACTIVITE_KEYWORDS.items():
        if kw in v:
            return mapped
    return str(val).strip().upper()


def _norm_col(s: str) -> str:
    """Normalise un nom de colonne : minuscules, sans accents, sans caractères spéciaux."""
    s = str(s).strip().lower()
    for src, dst in [("é","e"),("è","e"),("ê","e"),("à","a"),("â","a"),
                     ("ô","o"),("û","u"),("î","i"),("ù","u"),("ç","c")]:
        s = s.replace(src, dst)
    return re.sub(r"[^a-z0-9]", "", s)


def detect_col(df: pd.DataFrame, keywords: list) -> str | None:
    """Trouve la première colonne dont le nom normalisé correspond à un mot-clé (exact ou contenance)."""
    for col in df.columns:
        col_n = _norm_col(col)
        for kw in keywords:
            kw_n = _norm_col(kw)
            if kw_n == col_n or kw_n in col_n:
                return col
    return None


# ── Noms de colonnes exacts de l'export missions ───────────────────────────
# A: N° Dossier  B: Activité    C: Date        D: Heure
# E: Type de transport          F: Nom 1        G: Nom 2
# H: Adresse     I: Numéro      J: Code pays    K: Département
# L: Code postal M: Localité    N: Produit
# O: Chauffeur   Q: Immat. tracteur  R: Remorque

MISSIONS_COL_CANDIDATES = {
    "dossier":     ["N° Dossier", "N°Dossier", "N Dossier", "Dossier", "ndossier"],
    "activite":    ["Activité", "Activite", "Activité / Enregistrement"],
    "date":        ["Date"],
    "heure":       ["Heure"],
    "transport":   ["Type de transport", "Type transport"],
    "nom1":        ["Nom 1", "Nom1", "Nom"],
    "nom2":        ["Nom 2", "Nom2"],
    "adresse":     ["Adresse", "Address"],
    "numero":      ["Numéro", "Numero", "N°"],
    "code_pays":   ["Code pays", "Code Pays", "Pays", "Country"],
    "departement": ["Département", "Departement"],
    "code_postal": ["Code postal", "Code Postal", "Code Postal "],
    "localite":    ["Localité", "Localite", "Ville", "City"],
    "produit":     ["Produit"],
    "chauffeur":   ["Chauffeur", "Driver"],
    "tracteur":    ["Immat. tracteur", "Immat tracteur", "Immat.tracteur",
                    "Tracteur", "Immatriculation"],
    "remorque":    ["Remorque"],
}


def parse_missions(file) -> pd.DataFrame:
    """
    Parse le fichier missions en mappant exactement les colonnes de l'export
    (N° Dossier / Activité / Date / Heure / Nom 1 / Adresse / Numéro /
     Code pays / Code postal / Localité / Chauffeur / Immat. tracteur).
    """
    df = pd.read_excel(file, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    # ── Mapping : correspondance exacte insensible casse d'abord, fallback partiel ──
    cols_lower = {_norm_col(c): c for c in df.columns}

    col_map = {}
    for role, candidates in MISSIONS_COL_CANDIDATES.items():
        found = None
        # 1. Correspondance exacte normalisée
        for cand in candidates:
            key = _norm_col(cand)
            if key in cols_lower:
                found = cols_lower[key]
                break
        # 2. Fallback : contenance
        if not found:
            found = detect_col(df, candidates)
        col_map[role] = found

    # Avertissement colonnes manquantes importantes
    critiques = ["dossier", "activite", "date", "heure", "code_pays", "code_postal", "localite"]
    manquantes = [r for r in critiques if col_map.get(r) is None]
    if manquantes:
        st.warning(f"⚠️ Colonnes non détectées dans le fichier missions : {manquantes}\n"
                   f"Colonnes disponibles : {list(df.columns)}")

    # Renommage
    rename = {v: k for k, v in col_map.items() if v}
    df = df.rename(columns=rename)

    # Colonnes absentes → chaîne vide
    for col in MISSIONS_COL_CANDIDATES.keys():
        if col not in df.columns:
            df[col] = ""

    # ── Nettoyage lignes ───────────────────────────────────────
    df["dossier"] = df["dossier"].str.strip()
    df = df[df["dossier"].notna() & (df["dossier"] != "") & (df["dossier"] != "nan")]
    df = df[df["dossier"].str.match(r"^\d+", na=False)]

    df["activite_norm"] = df["activite"].apply(normalize_activite)

    # ── Date + Heure → datetime ────────────────────────────────
    try:
        df["datetime"] = pd.to_datetime(
            df["date"].str.strip() + " " + df["heure"].str.strip(),
            dayfirst=True, errors="coerce"
        )
    except Exception:
        df["datetime"] = pd.NaT

    # ── Adresse complète géocodable ────────────────────────────
    df["adresse_complete"] = df.apply(build_address_string, axis=1)

    return df


# ══════════════════════════════════════════════════════════════════
#  PARSING FICHIER CA
# ══════════════════════════════════════════════════════════════════

# Noms de colonnes exacts du fichier CA
# N° Dossier | Référence | Date chargement | Département | Type de transport |
# Type de dossier | Client facturation | Pays client fac |
# Adresse chargement | Localité chargement | C.P. chargement | ... |
# Produit | Type produit | Etat vente | Prix transport | Suppléments |
# S.G. | Heures d'attente | Total des ventes

CA_COL_CANDIDATES = {
    "dossier":        ["N° Dossier", "N°Dossier", "Dossier"],
    "prix_transport": ["Prix transport", "Prix Transport"],
    "total_vente":    ["Total des ventes", "Total ventes", "Total des vente"],
    "client":         ["Client facturation", "Client Facturation", "Client"],
    "etat_vente":     ["Etat vente", "État vente", "Etat"],
    "supplements":    ["Suppléments", "Supplements"],
    "sg":             ["S.G.", "SG"],
    "heures_attente": ["Heures d'attente", "Heures attente"],
    "date_charg":     ["Date chargement", "Date Chargement"],
    "type_transport": ["Type de transport", "Type transport"],
}


def parse_ca(file) -> pd.DataFrame:
    """
    Parse le fichier CA avec mapping exact des colonnes de l'export.
    Colonnes clés : N° Dossier / Prix transport / Total des ventes /
                    Client facturation / Etat vente
    """
    df = pd.read_excel(file, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    cols_lower = {_norm_col(c): c for c in df.columns}

    col_map = {}
    for role, candidates in CA_COL_CANDIDATES.items():
        found = None
        for cand in candidates:
            key = _norm_col(cand)
            if key in cols_lower:
                found = cols_lower[key]
                break
        col_map[role] = found

    # Avertissement si colonnes CA critiques manquantes
    critiques_ca = ["dossier", "prix_transport", "total_vente"]
    manquantes_ca = [r for r in critiques_ca if col_map.get(r) is None]
    if manquantes_ca:
        st.warning(f"⚠️ Colonnes CA non détectées : {manquantes_ca} — "
                   f"Colonnes disponibles : {list(df.columns)}")

    rename = {v: k for k, v in col_map.items() if v}
    df = df.rename(columns=rename)

    for col in CA_COL_CANDIDATES.keys():
        if col not in df.columns:
            df[col] = ""

    df["dossier"] = df["dossier"].str.strip()
    df = df[df["dossier"].notna() & (df["dossier"] != "") & (df["dossier"] != "nan")]
    df = df[df["dossier"].str.match(r"^\d+", na=False)]

    def to_float(s):
        try:
            return float(str(s).replace(",", ".").replace(" ", "").replace(" ", "").replace("€", "").strip())
        except Exception:
            return 0.0

    df["prix_transport"] = df["prix_transport"].apply(to_float)
    df["total_vente"]    = df["total_vente"].apply(to_float)

    # Déduplique par dossier (somme si multi-lignes)
    df_agg = df.groupby("dossier", as_index=False).agg(
        prix_transport=("prix_transport", "sum"),
        total_vente=("total_vente", "sum"),
        client=("client", "first"),
        etat_vente=("etat_vente", "first"),
    )

    return df_agg


# ══════════════════════════════════════════════════════════════════
#  CONSOLIDATION
# ══════════════════════════════════════════════════════════════════

def consolidate(df_missions: pd.DataFrame, df_ca: pd.DataFrame) -> pd.DataFrame:
    """
    Construit le tableau consolidé par dossier :
    - Séquence de stops ordonnée par datetime
    - CA joint par N° Dossier
    - Chauffeur / tracteur
    """
    rows = []

    for dossier, grp in df_missions.groupby("dossier"):
        grp = grp.sort_values("datetime").reset_index(drop=True)

        # Chauffeur / tracteur (premier non-vide)
        chauffeur = next((v for v in grp["chauffeur"] if v and v not in ("nan", "")), "")
        tracteur  = next((v for v in grp["tracteur"]  if v and v not in ("nan", "")), "")

        # Séquence des stops
        stops = []
        for _, r in grp.iterrows():
            stops.append({
                "activite":  r["activite_norm"],
                "datetime":  r["datetime"],
                "adresse":   r["adresse_complete"],
                "localite":  r.get("localite", ""),
                "nom":       r.get("nom1", ""),
                # champs bruts pour le fallback géocodage en cascade
                "ville_raw": str(r.get("localite",    "") or "").strip(),
                "cp_raw":    str(r.get("code_postal", "") or "").strip(),
                "pays_raw":  str(r.get("code_pays",   "") or "").strip().upper(),
            })

        # Résumé textuel des stops
        stop_labels = " → ".join(
            f"[{s['activite']}] {s['localite'] or s['nom'] or s['adresse']}"
            for s in stops
        )

        # Dates
        dates_valides = [s["datetime"] for s in stops if pd.notna(s["datetime"])]
        date_debut = min(dates_valides).strftime("%d/%m/%Y") if dates_valides else ""
        date_fin   = max(dates_valides).strftime("%d/%m/%Y") if dates_valides else ""

        rows.append({
            "dossier":    dossier,
            "chauffeur":  chauffeur,
            "tracteur":   tracteur,
            "date_debut": date_debut,
            "date_fin":   date_fin,
            "nb_stops":   len(stops),
            "stops_texte": stop_labels,
            "stops_data": stops,  # on garde pour le calcul PTV
        })

    df_cons = pd.DataFrame(rows)

    # Join CA
    df_cons = df_cons.merge(df_ca[["dossier", "prix_transport", "total_vente", "client", "etat_vente"]],
                            on="dossier", how="left")
    df_cons["prix_transport"] = df_cons["prix_transport"].fillna(0.0)
    df_cons["total_vente"]    = df_cons["total_vente"].fillna(0.0)

    return df_cons


# ══════════════════════════════════════════════════════════════════
#  CALCUL KM PAR CHAUFFEUR (PTV)
# ══════════════════════════════════════════════════════════════════

def compute_ptv_for_driver(df_cons: pd.DataFrame, chauffeur: str,
                            progress_cb=None) -> list:
    """
    Pour un chauffeur donné :
    1. Trie ses dossiers par date de début
    2. Calcule km totaux par dossier (tous les stops)
    3. Calcule km à vide entre DECHARGER → CHARGER suivant (inter-dossiers inclus)

    Retourne une liste de dicts enrichis.
    """
    df_ch = df_cons[df_cons["chauffeur"] == chauffeur].copy()
    df_ch = df_ch.sort_values("date_debut").reset_index(drop=True)

    results = []

    # Aplatir tous les stops du chauffeur dans l'ordre chronologique
    all_stops_flat = []
    for _, row in df_ch.iterrows():
        for s in row["stops_data"]:
            all_stops_flat.append({
                "dossier":   row["dossier"],
                "activite":  s["activite"],
                "datetime":  s["datetime"],
                "adresse":   s["adresse"],
                "localite":  s["localite"],
                "ville_raw": s.get("ville_raw", ""),
                "cp_raw":    s.get("cp_raw",    ""),
                "pays_raw":  s.get("pays_raw",  ""),
            })

    # Trier globalement par datetime
    all_stops_flat.sort(key=lambda x: x["datetime"] if pd.notna(x["datetime"]) else pd.Timestamp.max)

    # ── Géocodage de tous les stops uniques ──────────────────
    unique_addresses = list({s["adresse"] for s in all_stops_flat if s["adresse"]})
    geo_cache = {}

    total_geo = len(unique_addresses)
    # Construire un dict adresse_complete → (ville, cp, pays) pour le fallback
    addr_meta = {}
    for s in all_stops_flat:
        if s["adresse"] not in addr_meta:
            addr_meta[s["adresse"]] = (
                s.get("ville_raw", ""),
                s.get("cp_raw",    ""),
                s.get("pays_raw",  ""),
            )

    for i, addr in enumerate(unique_addresses):
        if progress_cb:
            progress_cb(f"🌍 Géocodage {i+1}/{total_geo} : {addr[:50]}...")
        ville_r, cp_r, pays_r = addr_meta.get(addr, ("", "", ""))
        coords = geocode_with_fallback(addr, ville_r, cp_r, pays_r)
        geo_cache[addr] = coords
        if coords is None:
            st.warning(f"⚠️ Géocodage échoué (tous niveaux) : {addr}")

    # ── Calcul km totaux par dossier ──────────────────────────
    dossier_km = {}
    for _, row in df_ch.iterrows():
        dos = row["dossier"]
        stops = row["stops_data"]
        coords_seq = []
        for s in stops:
            c = geo_cache.get(s["adresse"])
            if c:
                coords_seq.append(c)

        if len(coords_seq) >= 2:
            if progress_cb:
                progress_cb(f"📍 Calcul km dossier {dos}...")
            res = calculate_route(coords_seq)
            dossier_km[dos] = res["km"] if res else None
        else:
            dossier_km[dos] = None

    # ── Calcul km à vide (DECHARGER → CHARGER suivant) ───────
    empty_legs = []  # {"dossier_depart", "dossier_arrivee", "from_addr", "to_addr", "km_vide"}

    last_decharge = None  # {"dossier", "adresse", "coords", "localite"}

    for stop in all_stops_flat:
        act  = stop["activite"]
        addr = stop["adresse"]
        coords = geo_cache.get(addr)

        if act == "DECHARGEMENT":
            last_decharge = {
                "dossier":  stop["dossier"],
                "adresse":  addr,
                "coords":   coords,
                "localite": stop["localite"],
            }

        elif act == "CHARGEMENT" and last_decharge is not None:
            # Km à vide entre le dernier déchargement et ce chargement
            if last_decharge["coords"] and coords:
                if progress_cb:
                    progress_cb(f"⚡ Km à vide : {last_decharge['localite']} → {stop['localite']}...")
                res = calculate_route([last_decharge["coords"], coords])
                km_vide = res["km"] if res else None
            else:
                km_vide = None

            empty_legs.append({
                "dossier_depart":  last_decharge["dossier"],
                "dossier_arrivee": stop["dossier"],
                "from_addr":       last_decharge["adresse"],
                "from_localite":   last_decharge["localite"],
                "to_addr":         addr,
                "to_localite":     stop["localite"],
                "km_vide":         km_vide,
            })
            last_decharge = None  # reset

    # ── Assemblage résultats par dossier ──────────────────────
    for _, row in df_ch.iterrows():
        dos = row["dossier"]

        # Km à vide imputés à ce dossier (départ = ce dossier)
        km_vide_total = sum(
            leg["km_vide"] for leg in empty_legs
            if leg["dossier_depart"] == dos and leg["km_vide"] is not None
        )
        vide_details = [
            leg for leg in empty_legs if leg["dossier_depart"] == dos
        ]

        results.append({
            "dossier":       dos,
            "chauffeur":     chauffeur,
            "tracteur":      row["tracteur"],
            "date_debut":    row["date_debut"],
            "date_fin":      row["date_fin"],
            "client":        row.get("client", ""),
            "etat_vente":    row.get("etat_vente", ""),
            "stops_texte":   row["stops_texte"],
            "nb_stops":      row["nb_stops"],
            "prix_transport": row["prix_transport"],
            "total_vente":   row["total_vente"],
            "km_total":      dossier_km.get(dos),
            "km_vide":       km_vide_total if km_vide_total > 0 else None,
            "vide_details":  vide_details,
        })

    return results


# ══════════════════════════════════════════════════════════════════
#  EXPORT EXCEL
# ══════════════════════════════════════════════════════════════════

def export_excel(df_result: pd.DataFrame, df_vide: pd.DataFrame) -> bytes:
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # ── Feuille principale ────────────────────────────────
        cols_main = [
            "chauffeur", "tracteur", "dossier", "date_debut", "date_fin",
            "client", "etat_vente", "nb_stops", "stops_texte",
            "km_total", "km_vide",
            "prix_transport", "total_vente",
        ]
        df_export = df_result[[c for c in cols_main if c in df_result.columns]].copy()
        df_export.columns = [
            "Chauffeur", "Tracteur", "N° Dossier", "Date début", "Date fin",
            "Client", "État vente", "Nb stops", "Séquence stops",
            "KM Total (PTV)", "KM À Vide (PTV)",
            "Prix Transport (€)", "Total Vente (€)",
        ][:len(df_export.columns)]

        df_export.to_excel(writer, sheet_name="Missions & CA", index=False)

        ws = writer.sheets["Missions & CA"]
        _style_sheet(ws, len(df_export))

        # ── Feuille résumé par chauffeur ──────────────────────
        df_resume = df_result.groupby("chauffeur", as_index=False).agg(
            nb_dossiers   = ("dossier",         "count"),
            km_total      = ("km_total",         "sum"),
            km_vide       = ("km_vide",           "sum"),
            prix_transport= ("prix_transport",    "sum"),
            total_vente   = ("total_vente",       "sum"),
        ).round(1)
        df_resume.columns = ["Chauffeur", "Nb Dossiers", "KM Total", "KM À Vide",
                              "Prix Transport (€)", "Total Vente (€)"]
        df_resume.to_excel(writer, sheet_name="Résumé Chauffeurs", index=False)
        _style_sheet(writer.sheets["Résumé Chauffeurs"], len(df_resume))

        # ── Feuille km à vide détail ──────────────────────────
        if not df_vide.empty:
            df_vide_exp = df_vide.copy()
            df_vide_exp.columns = [
                "Chauffeur", "Dossier départ", "Dossier arrivée",
                "Ville départ", "Ville arrivée", "KM à vide"
            ]
            df_vide_exp.to_excel(writer, sheet_name="KM À Vide Détail", index=False)
            _style_sheet(writer.sheets["KM À Vide Détail"], len(df_vide_exp))

    return output.getvalue()


def _style_sheet(ws, nb_rows: int):
    HEADER_FILL = PatternFill("solid", fgColor="1F3864")
    HEADER_FONT = Font(bold=True, color="FFFFFF")
    ALT_FILL    = PatternFill("solid", fgColor="EEF2F7")

    for cell in ws[1]:
        cell.fill      = HEADER_FILL
        cell.font      = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

    for row_idx in range(2, nb_rows + 2):
        if row_idx % 2 == 0:
            for cell in ws[row_idx]:
                cell.fill = ALT_FILL

    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 60)


# ══════════════════════════════════════════════════════════════════
#  INTERFACE STREAMLIT
# ══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Missions & CA + KM PTV", page_icon="📦", layout="wide")

st.title("📦 Analyse Missions + CA + Calcul KM")
st.caption("Consolide les missions, le chiffre d'affaires et calcule les kilomètres via PTV.")

# ── Vérification clé PTV ──────────────────────────────────────────
if not PTV_API_KEY or PTV_API_KEY == "METS_TA_CLE_ICI":
    st.error("⚠️ Clé PTV_API_KEY non configurée. Le calcul de distances ne fonctionnera pas.")

st.divider()

# ── Upload ────────────────────────────────────────────────────────
col_up1, col_up2 = st.columns(2)
with col_up1:
    st.markdown("#### 📋 Fichier Missions")
    file_missions = st.file_uploader("Export missions (.xlsx)", type=["xlsx"], key="missions")
with col_up2:
    st.markdown("#### 💶 Fichier CA")
    file_ca = st.file_uploader("Export CA (.xlsx)", type=["xlsx"], key="ca")

st.divider()

# ── Parsing & Consolidation ───────────────────────────────────────
if file_missions and file_ca:

    with st.spinner("📂 Lecture des fichiers..."):
        try:
            df_missions = parse_missions(file_missions)
            df_ca_raw   = parse_ca(file_ca)
        except Exception as e:
            st.error(f"❌ Erreur lecture fichiers : {e}")
            st.stop()

    with st.expander("🔍 Debug colonnes détectées", expanded=False):
        st.markdown("**Fichier Missions** — colonnes brutes :")
        _df_m_raw = pd.read_excel(file_missions, dtype=str, nrows=2)
        st.write(list(_df_m_raw.columns))
        st.markdown("**Fichier CA** — colonnes brutes :")
        _df_ca_raw2 = pd.read_excel(file_ca, dtype=str, nrows=2)
        st.write(list(_df_ca_raw2.columns))
        st.markdown("**Fichier CA** — 3 premières lignes :")
        st.dataframe(_df_ca_raw2)
        st.markdown(f"**CA parsé** — colonnes : `{list(df_ca_raw.columns)}`")
        st.dataframe(df_ca_raw.head(5))

    df_cons = consolidate(df_missions, df_ca_raw)

    # ── KPIs rapides ──────────────────────────────────────────
    st.markdown("### 📊 Aperçu")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("📁 Dossiers", len(df_cons))
    k2.metric("🚛 Chauffeurs",    df_cons["chauffeur"].nunique())
    k3.metric("📍 Stops totaux",  int(df_cons["nb_stops"].sum()))
    k4.metric("💶 CA Total (Prix transp.)", f"{df_cons['prix_transport'].sum():,.0f} €")
    k5.metric("💶 CA Total (Total vente)",  f"{df_cons['total_vente'].sum():,.0f} €")

    st.divider()

    # ── Tableau consolidé (sans KM pour l'instant) ────────────
    st.markdown("### 📋 Tableau consolidé")

    # Filtre chauffeur
    chauffeurs_dispo = sorted(df_cons["chauffeur"].dropna().unique().tolist())
    chauffeurs_dispo = [c for c in chauffeurs_dispo if c and c != "nan"]

    filtre_chauffeur = st.multiselect(
        "Filtrer par chauffeur :",
        options=chauffeurs_dispo,
        default=[],
        placeholder="Tous les chauffeurs"
    )

    df_display = df_cons.copy()
    if filtre_chauffeur:
        df_display = df_display[df_display["chauffeur"].isin(filtre_chauffeur)]

    cols_show = ["dossier", "chauffeur", "tracteur", "date_debut", "date_fin",
                 "client", "etat_vente", "nb_stops", "stops_texte",
                 "prix_transport", "total_vente"]

    st.dataframe(
        df_display[[c for c in cols_show if c in df_display.columns]].rename(columns={
            "dossier": "N° Dossier", "chauffeur": "Chauffeur", "tracteur": "Tracteur",
            "date_debut": "Date début", "date_fin": "Date fin", "client": "Client",
            "etat_vente": "État vente", "nb_stops": "Nb stops",
            "stops_texte": "Séquence stops",
            "prix_transport": "Prix Transport (€)", "total_vente": "Total Vente (€)",
        }),
        use_container_width=True,
        height=400,
    )

    st.divider()

    # ── Calcul PTV ────────────────────────────────────────────
    st.markdown("### 🗺️ Calcul KM via PTV")

    chauffeurs_ptv = st.multiselect(
        "Sélectionner les chauffeurs pour le calcul PTV :",
        options=chauffeurs_dispo,
        default=[],
        placeholder="Sélectionner des chauffeurs..."
    )

    if chauffeurs_ptv:
        st.info(
            f"ℹ️ Le calcul PTV va géocoder tous les stops et calculer les routes pour "
            f"**{len(df_cons[df_cons['chauffeur'].isin(chauffeurs_ptv)])} dossiers** "
            f"({len(chauffeurs_ptv)} chauffeur(s)). Cela peut prendre quelques minutes."
        )

    btn_ptv = st.button(
        "🚀 Lancer le calcul PTV",
        disabled=(not chauffeurs_ptv),
        type="primary",
    )

    if btn_ptv and chauffeurs_ptv:
        all_results = []
        all_vide    = []

        progress_bar = st.progress(0)
        status_text  = st.empty()

        total_ch = len(chauffeurs_ptv)

        for ch_idx, chauffeur in enumerate(chauffeurs_ptv):
            status_text.text(f"⏳ Chauffeur {ch_idx+1}/{total_ch} : {chauffeur}")

            def _progress(msg):
                status_text.text(msg)

            try:
                res = compute_ptv_for_driver(df_cons, chauffeur, progress_cb=_progress)
                all_results.extend(res)

                # Extraire km à vide détails
                for r in res:
                    for leg in r.get("vide_details", []):
                        all_vide.append({
                            "chauffeur":       chauffeur,
                            "dossier_depart":  leg["dossier_depart"],
                            "dossier_arrivee": leg["dossier_arrivee"],
                            "from_localite":   leg["from_localite"],
                            "to_localite":     leg["to_localite"],
                            "km_vide":         leg["km_vide"],
                        })

            except Exception as e:
                st.error(f"❌ Erreur chauffeur {chauffeur} : {e}")

            progress_bar.progress(int((ch_idx + 1) / total_ch * 100))

        status_text.success("✅ Calcul PTV terminé !")
        progress_bar.progress(100)

        df_result = pd.DataFrame(all_results)
        df_vide   = pd.DataFrame(all_vide)

        st.session_state["df_result"] = df_result
        st.session_state["df_vide"]   = df_vide

    # ── Affichage résultats PTV ───────────────────────────────
    if "df_result" in st.session_state:
        df_result = st.session_state["df_result"]
        df_vide   = st.session_state.get("df_vide", pd.DataFrame())

        st.divider()
        st.markdown("### 📈 Résultats KM")

        # KPIs PTV
        km_total_sum = df_result["km_total"].sum()
        km_vide_sum  = df_result["km_vide"].sum()
        pct_vide     = (km_vide_sum / km_total_sum * 100) if km_total_sum > 0 else 0

        kp1, kp2, kp3, kp4 = st.columns(4)
        kp1.metric("📏 KM Totaux (PTV)", f"{km_total_sum:,.0f} km")
        kp2.metric("⚡ KM À Vide",        f"{km_vide_sum:,.0f} km")
        kp3.metric("% À Vide",            f"{pct_vide:.1f}%")
        kp4.metric("💶 CA Total",          f"{df_result['total_vente'].sum():,.0f} €")

        # Tableau résultats
        tab1, tab2, tab3 = st.tabs(["📋 Détail dossiers", "👤 Résumé par chauffeur", "⚡ Détail KM à vide"])

        with tab1:
            cols_res = ["dossier", "chauffeur", "tracteur", "date_debut", "client",
                        "stops_texte", "km_total", "km_vide", "prix_transport", "total_vente"]
            st.dataframe(
                df_result[[c for c in cols_res if c in df_result.columns]].rename(columns={
                    "dossier": "N° Dossier", "chauffeur": "Chauffeur", "tracteur": "Tracteur",
                    "date_debut": "Date", "client": "Client", "stops_texte": "Séquence",
                    "km_total": "KM Total", "km_vide": "KM À Vide",
                    "prix_transport": "Prix Transport €", "total_vente": "Total Vente €"
                }),
                use_container_width=True, height=400
            )

        with tab2:
            df_resume_ptv = df_result.groupby("chauffeur", as_index=False).agg(
                Dossiers      = ("dossier",        "count"),
                KM_Total      = ("km_total",        "sum"),
                KM_Vide       = ("km_vide",          "sum"),
                Prix_Transport= ("prix_transport",   "sum"),
                Total_Vente   = ("total_vente",      "sum"),
            ).round(1)
            df_resume_ptv.columns = ["Chauffeur", "Nb Dossiers", "KM Total",
                                      "KM À Vide", "Prix Transport €", "Total Vente €"]
            st.dataframe(df_resume_ptv, use_container_width=True)

        with tab3:
            if not df_vide.empty:
                st.dataframe(
                    df_vide.rename(columns={
                        "chauffeur": "Chauffeur", "dossier_depart": "Dossier départ",
                        "dossier_arrivee": "Dossier arrivée",
                        "from_localite": "Ville départ", "to_localite": "Ville arrivée",
                        "km_vide": "KM à vide"
                    }),
                    use_container_width=True
                )
            else:
                st.info("Aucun trajet à vide détecté.")

        # ── Export ────────────────────────────────────────────
        st.divider()
        excel_bytes = export_excel(df_result, df_vide)
        st.download_button(
            label="📥 Télécharger le rapport Excel",
            data=excel_bytes,
            file_name="Rapport_Missions_CA_KM.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

elif file_missions and not file_ca:
    st.info("📂 Fichier missions chargé. En attente du fichier CA...")
elif file_ca and not file_missions:
    st.info("📂 Fichier CA chargé. En attente du fichier missions...")
else:
    st.markdown("""
    #### Comment utiliser cet outil

    1. **Chargez le fichier Missions** (export avec N°Dossier, Activité, stops, chauffeur)
    2. **Chargez le fichier CA** (export avec N°Dossier, Prix transport, Total vente)
    3. Consultez le **tableau consolidé** par dossier
    4. Sélectionnez les chauffeurs et **lancez le calcul PTV** pour obtenir :
       - Les km totaux par dossier (toute la chaîne de stops)
       - Les km à vide entre chaque déchargement et le rechargement suivant
    5. **Téléchargez le rapport Excel**

    > ⚙️ La clé PTV doit être configurée dans le fichier `.env` (`PTV_API_KEY`).
    """)
