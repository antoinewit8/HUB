"""
4b____Renta_Departements_CA.py
──────────────────────────────────────────────────────────────────
Rentabilité par DÉPARTEMENT de déchargement — fichier CA seul
──────────────────────────────────────────────────────────────────
Entrée :
  • Fichier CA (.xlsx) — colonnes utilisées :
      N° Dossier, Date chargement, Type de transport, Client facturation,
      Localité/C.P./Pays chargement, Localité/C.P./Pays déchargement,
      Département déchargement, Etat vente, Prix transport, Total des ventes

Sortie :
  • KM chargés par dossier (PTV, chargement → déchargement)
  • Rentabilité €/km par département de déchargement
  • Export Excel / CSV

⚠️ Limite : le fichier CA ne contient pas le chauffeur/tracteur, donc les
   KM À VIDE ne peuvent pas être chaînés. Pour ça il faut le fichier missions
   (page « Analyse Missions + CA + Calcul KM »).
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

load_dotenv()

# ══════════════════════════════════════════════════════════════════
#  CONFIG PTV
# ══════════════════════════════════════════════════════════════════

PTV_API_KEY  = os.environ.get("PTV_API_KEY", "METS_TA_CLE_ICI")
PTV_BASE_URL = "https://api.myptv.com/routing/v1"
GEOCODE_URL  = "https://api.myptv.com/geocoding/v1"
HEADERS      = {"apiKey": PTV_API_KEY}
MAX_RETRIES  = 3
RETRY_DELAY  = 2
MAX_WORKERS  = 4
VEHICLE      = "EUR_TRAILER_TRUCK"

try:
    from excel_handler_km import PAYS_MAP, parse_origin_from_parts
    _IMPORTS_OK = True
except ImportError:
    _IMPORTS_OK = False
    PAYS_MAP = {
        "F": "France", "B": "Belgium", "D": "Germany", "L": "Luxembourg",
        "NL": "Netherlands", "E": "Spain", "I": "Italy", "CH": "Switzerland",
        "GB": "United Kingdom", "A": "Austria", "P": "Portugal",
        "FR": "France", "BE": "Belgium", "DE": "Germany", "LU": "Luxembourg",
        "IT": "Italy", "ES": "Spain", "AT": "Austria", "PT": "Portugal",
    }

    def parse_origin_from_parts(city, cp, country):
        pays_full = PAYS_MAP.get(str(country).strip().upper(), country)
        return ", ".join(p for p in [city, cp, pays_full] if p and p != "nan")


PAYS_TO_ISO2 = {
    "F": "FR", "B": "BE", "D": "DE", "L": "LU", "I": "IT",
    "E": "ES", "A": "AT", "P": "PT", "CH": "CH", "GB": "GB",
    "NL": "NL", "FR": "FR", "BE": "BE", "DE": "DE", "LU": "LU",
    "IT": "IT", "ES": "ES", "AT": "AT", "PT": "PT",
}

PAYS_LABELS = {
    "F": "🇫🇷 France", "B": "🇧🇪 Belgique", "L": "🇱🇺 Luxembourg",
    "NL": "🇳🇱 Pays-Bas", "D": "🇩🇪 Allemagne", "CH": "🇨🇭 Suisse",
    "I": "🇮🇹 Italie", "E": "🇪🇸 Espagne", "GB": "🇬🇧 Royaume-Uni",
    "A": "🇦🇹 Autriche", "P": "🇵🇹 Portugal",
}

# ══════════════════════════════════════════════════════════════════
#  BASES DE CALCUL DU CA
#  Total des ventes = Prix transport + Suppléments + S.G. + Heures d'attente
# ══════════════════════════════════════════════════════════════════

BASES_CA = {
    "💶 Total des ventes":            "total_vente",
    "🚚 Prix transport seul":         "prix_transport",
    "⛽ Prix transport + S.G.":       "prix_sg",
    "➕ Prix transport + suppléments": "prix_supp",
}

BASES_AIDE = {
    "total_vente":    "Prix transport + suppléments + S.G. + heures d'attente (facturation totale).",
    "prix_transport": "Prix transport nu, hors surcharge gasoil, suppléments et attente — "
                      "mesure la performance tarifaire pure de la ligne.",
    "prix_sg":        "Prix transport + surcharge gasoil, hors suppléments et attente.",
    "prix_supp":      "Prix transport + suppléments, hors surcharge gasoil et attente.",
}


# ══════════════════════════════════════════════════════════════════
#  DÉPARTEMENTS FRANÇAIS
# ══════════════════════════════════════════════════════════════════

DEPT_NOMS = {
    "01": "Ain", "02": "Aisne", "03": "Allier", "04": "Alpes-de-Haute-Provence",
    "05": "Hautes-Alpes", "06": "Alpes-Maritimes", "07": "Ardèche", "08": "Ardennes",
    "09": "Ariège", "10": "Aube", "11": "Aude", "12": "Aveyron",
    "13": "Bouches-du-Rhône", "14": "Calvados", "15": "Cantal", "16": "Charente",
    "17": "Charente-Maritime", "18": "Cher", "19": "Corrèze",
    "2A": "Corse-du-Sud", "2B": "Haute-Corse",
    "21": "Côte-d'Or", "22": "Côtes-d'Armor", "23": "Creuse", "24": "Dordogne",
    "25": "Doubs", "26": "Drôme", "27": "Eure", "28": "Eure-et-Loir",
    "29": "Finistère", "30": "Gard", "31": "Haute-Garonne", "32": "Gers",
    "33": "Gironde", "34": "Hérault", "35": "Ille-et-Vilaine", "36": "Indre",
    "37": "Indre-et-Loire", "38": "Isère", "39": "Jura", "40": "Landes",
    "41": "Loir-et-Cher", "42": "Loire", "43": "Haute-Loire", "44": "Loire-Atlantique",
    "45": "Loiret", "46": "Lot", "47": "Lot-et-Garonne", "48": "Lozère",
    "49": "Maine-et-Loire", "50": "Manche", "51": "Marne", "52": "Haute-Marne",
    "53": "Mayenne", "54": "Meurthe-et-Moselle", "55": "Meuse", "56": "Morbihan",
    "57": "Moselle", "58": "Nièvre", "59": "Nord", "60": "Oise",
    "61": "Orne", "62": "Pas-de-Calais", "63": "Puy-de-Dôme", "64": "Pyrénées-Atlantiques",
    "65": "Hautes-Pyrénées", "66": "Pyrénées-Orientales", "67": "Bas-Rhin", "68": "Haut-Rhin",
    "69": "Rhône", "70": "Haute-Saône", "71": "Saône-et-Loire", "72": "Sarthe",
    "73": "Savoie", "74": "Haute-Savoie", "75": "Paris", "76": "Seine-Maritime",
    "77": "Seine-et-Marne", "78": "Yvelines", "79": "Deux-Sèvres", "80": "Somme",
    "81": "Tarn", "82": "Tarn-et-Garonne", "83": "Var", "84": "Vaucluse",
    "85": "Vendée", "86": "Vienne", "87": "Haute-Vienne", "88": "Vosges",
    "89": "Yonne", "90": "Territoire de Belfort", "91": "Essonne", "92": "Hauts-de-Seine",
    "93": "Seine-Saint-Denis", "94": "Val-de-Marne", "95": "Val-d'Oise",
    "971": "Guadeloupe", "972": "Martinique", "973": "Guyane",
    "974": "La Réunion", "976": "Mayotte",
}

PAYS_FRANCE = {"F", "FR", "FRA", "FRANCE"}


def normalize_cp_fr(cp):
    cp = re.sub(r"[^0-9A-Za-z]", "", str(cp or "").strip()).upper()
    if not cp or cp == "NAN":
        return ""
    if cp.isdigit() and len(cp) == 4:
        cp = "0" + cp
    return cp


def extract_departement(cp, pays):
    """Code département FR ('01'..'95', '2A', '2B', '971'...) ou None."""
    pays_n = str(pays or "").strip().upper()
    cp_n   = normalize_cp_fr(cp)

    if not cp_n:
        return None
    if pays_n not in PAYS_FRANCE:
        if pays_n not in ("", "NAN", "NONE"):
            return None
        if not (cp_n.isdigit() and len(cp_n) == 5):
            return None

    if cp_n.startswith("2A"):
        return "2A"
    if cp_n.startswith("2B"):
        return "2B"
    if cp_n.startswith("20") and cp_n.isdigit() and len(cp_n) == 5:
        return "2A" if int(cp_n) < 20200 else "2B"
    if cp_n[:2] in ("97", "98") and len(cp_n) >= 3:
        return cp_n[:3]
    if len(cp_n) >= 2:
        return cp_n[:2]
    return None


def dept_label(code):
    if not code:
        return ""
    nom = DEPT_NOMS.get(code, "")
    return f"{code} — {nom}" if nom else str(code)


# ══════════════════════════════════════════════════════════════════
#  PTV — GÉOCODAGE + ROUTE
# ══════════════════════════════════════════════════════════════════

def _ptv_by_text(query):
    if not query:
        return None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                f"{GEOCODE_URL}/locations/by-text",
                params={"searchText": query},
                headers=HEADERS, timeout=15,
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


def _ptv_by_postal_code(cp, iso2):
    if not cp or not iso2:
        return None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                f"{GEOCODE_URL}/locations/by-postal-code",
                params={"postalCode": cp, "countryCode": iso2},
                headers=HEADERS, timeout=15,
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


def geocode_point(ville, cp, pays):
    pays      = str(pays or "").strip().upper()
    pays_full = PAYS_MAP.get(pays, pays)
    iso2      = PAYS_TO_ISO2.get(pays, pays if len(pays) == 2 else "")
    cp        = str(cp or "").strip()
    ville     = str(ville or "").strip()

    if ville and cp and pays_full:
        r = _ptv_by_text(f"{ville}, {cp}, {pays_full}")
        if r:
            return r
    if cp and iso2:
        r = _ptv_by_postal_code(cp, iso2)
        if r:
            return r
    if ville and pays_full:
        r = _ptv_by_text(f"{ville}, {pays_full}")
        if r:
            return r
    return None


def calculate_km(coord_a, coord_b):
    if not coord_a or not coord_b:
        return None
    params = [
        ("profile", VEHICLE),
        ("waypoints", f"{coord_a[0]},{coord_a[1]}"),
        ("waypoints", f"{coord_b[0]},{coord_b[1]}"),
    ]
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                f"{PTV_BASE_URL}/routes", headers=HEADERS,
                params=params, timeout=30,
            )
            if resp.status_code == 429:
                time.sleep(RETRY_DELAY * attempt)
                continue
            if resp.status_code != 200:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                return None
            data = resp.json()
            return {
                "km":            round(data.get("distance", 0) / 1000, 1),
                "travel_time_h": round(data.get("travelTime", 0) / 3600, 2),
            }
        except Exception:
            time.sleep(RETRY_DELAY)
    return None


# ══════════════════════════════════════════════════════════════════
#  PARSING FICHIER CA
# ══════════════════════════════════════════════════════════════════

def _norm_col(s):
    s = str(s).strip().lower()
    for src, dst in [("é","e"),("è","e"),("ê","e"),("à","a"),("â","a"),
                     ("ô","o"),("û","u"),("î","i"),("ù","u"),("ç","c")]:
        s = s.replace(src, dst)
    return re.sub(r"[^a-z0-9]", "", s)


CA_COLS = {
    "dossier":          ["N° Dossier", "N°Dossier", "Dossier"],
    "reference":        ["Référence", "Reference"],
    "date_charg":       ["Date chargement", "Date Chargement"],
    "departement_int":  ["Département"],
    "type_transport":   ["Type de transport"],
    "type_dossier":     ["Type de dossier"],
    "client":           ["Client facturation", "Client"],
    "pays_client":      ["Pays client fac"],
    "adr_charg":        ["Adresse chargement"],
    "localite_charg":   ["Localité chargement", "Localite chargement"],
    "cp_charg":         ["C.P. chargement", "CP chargement"],
    "dept_charg_src":   ["Département chargement", "Departement chargement"],
    "pays_charg":       ["Pays chargement"],
    "adr_decharg":      ["Adresse déchargement", "Adresse dechargement"],
    "localite_decharg": ["Localité déchargement", "Localite dechargement"],
    "cp_decharg":       ["C.P. déchargement", "CP dechargement"],
    "dept_decharg_src": ["Département déchargement", "Departement dechargement"],
    "pays_decharg":     ["Pays déchargement", "Pays dechargement"],
    "produit":          ["Produit"],
    "type_produit":     ["Type produit"],
    "etat_vente":       ["Etat vente", "État vente"],
    "prix_transport":   ["Prix transport"],
    "supplements":      ["Suppléments", "Supplements"],
    "sg":               ["S.G.", "SG"],
    "heures_attente":   ["Heures d'attente"],
    "total_vente":      ["Total des ventes", "Total ventes"],
    "total_achat":      ["Total des achats", "Total achats"],
}


def to_float(s):
    try:
        return float(
            str(s).replace(",", ".").replace("\xa0", "")
            .replace(" ", "").replace("€", "").strip()
        )
    except Exception:
        return 0.0


def parse_ca(file):
    df = pd.read_excel(file, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    cols_lower = {_norm_col(c): c for c in df.columns}

    col_map = {}
    for role, candidates in CA_COLS.items():
        found = None
        for cand in candidates:
            key = _norm_col(cand)
            if key in cols_lower:
                found = cols_lower[key]
                break
        col_map[role] = found

    manquantes = [r for r in ("dossier", "total_vente", "cp_decharg", "pays_decharg")
                  if col_map.get(r) is None]
    if manquantes:
        st.error(
            f"❌ Colonnes indispensables non trouvées : {manquantes}\n\n"
            f"Colonnes du fichier : {list(df.columns)}"
        )
        st.stop()

    df = df.rename(columns={v: k for k, v in col_map.items() if v})
    for col in CA_COLS:
        if col not in df.columns:
            df[col] = ""

    df["dossier"] = df["dossier"].astype(str).str.strip()
    df = df[df["dossier"].str.match(r"^\d+", na=False)].copy()

    for c in ("prix_transport", "supplements", "sg", "heures_attente",
              "total_vente", "total_achat"):
        df[c] = df[c].apply(to_float)

    def _c(v):
        v = str(v or "").strip()
        return "" if v.lower() in ("nan", "none") else v

    for c in ("localite_charg", "cp_charg", "pays_charg",
              "localite_decharg", "cp_decharg", "pays_decharg",
              "client", "etat_vente", "type_transport", "produit"):
        df[c] = df[c].apply(_c)

    df["pays_charg"]   = df["pays_charg"].str.upper()
    df["pays_decharg"] = df["pays_decharg"].str.upper()

    df["date_dt"] = pd.to_datetime(df["date_charg"], errors="coerce")
    df["mois"]    = df["date_dt"].dt.to_period("M").astype(str)

    # Département : recalculé depuis CP + pays (fiable), repli sur la colonne source
    df["dept_decharg"] = df.apply(
        lambda r: extract_departement(r["cp_decharg"], r["pays_decharg"]), axis=1
    )
    df["dept_charg"] = df.apply(
        lambda r: extract_departement(r["cp_charg"], r["pays_charg"]), axis=1
    )
    df["dept_label"] = df["dept_decharg"].map(
        lambda c: dept_label(c) if c else "🌍 Hors France"
    )

    df["marge"]     = df["total_vente"] - df["total_achat"]
    df["prix_sg"]   = df["prix_transport"] + df["sg"]
    df["prix_supp"] = df["prix_transport"] + df["supplements"]

    return df.reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════
#  CALCUL PTV (multi-thread + cache)
# ══════════════════════════════════════════════════════════════════

def run_ptv(df, status, bar):
    geo_cache   = st.session_state.setdefault("_geo_ca", {})
    route_cache = st.session_state.setdefault("_route_ca", {})

    pts_charg   = list(zip(df["localite_charg"], df["cp_charg"], df["pays_charg"]))
    pts_decharg = list(zip(df["localite_decharg"], df["cp_decharg"], df["pays_decharg"]))
    tous_pts    = {p for p in pts_charg + pts_decharg if p[0] or p[1]}
    a_geocoder  = [p for p in tous_pts if p not in geo_cache]

    echecs_geo = []
    if a_geocoder:
        status.text(f"🌍 Géocodage de {len(a_geocoder)} points (sur {len(tous_pts)})...")
        done = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = {ex.submit(geocode_point, *p): p for p in a_geocoder}
            for fut in as_completed(futs):
                p = futs[fut]
                try:
                    geo_cache[p] = fut.result()
                except Exception:
                    geo_cache[p] = None
                if geo_cache[p] is None:
                    echecs_geo.append(p)
                done += 1
                bar.progress(min(done / max(len(a_geocoder), 1) * 0.45, 0.45))
                if done % 5 == 0 or done == len(a_geocoder):
                    status.text(f"🌍 Géocodage {done}/{len(a_geocoder)} — {p[0]} {p[1]}")

    # ── Paires OD uniques ──
    paires = []
    for pc, pd_ in zip(pts_charg, pts_decharg):
        ca_, cb_ = geo_cache.get(pc), geo_cache.get(pd_)
        if ca_ and cb_:
            key = (ca_, cb_)
            if key not in route_cache:
                paires.append(key)
    paires = list(dict.fromkeys(paires))

    if paires:
        status.text(f"📍 Calcul de {len(paires)} trajets PTV...")
        done = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = {ex.submit(calculate_km, k[0], k[1]): k for k in paires}
            for fut in as_completed(futs):
                k = futs[fut]
                try:
                    route_cache[k] = fut.result()
                except Exception:
                    route_cache[k] = None
                done += 1
                bar.progress(0.45 + min(done / max(len(paires), 1) * 0.55, 0.55))
                if done % 5 == 0 or done == len(paires):
                    status.text(f"📍 Trajets {done}/{len(paires)}")

    kms, heures = [], []
    for pc, pd_ in zip(pts_charg, pts_decharg):
        ca_, cb_ = geo_cache.get(pc), geo_cache.get(pd_)
        res = route_cache.get((ca_, cb_)) if (ca_ and cb_) else None
        kms.append(res["km"] if res else np.nan)
        heures.append(res["travel_time_h"] if res else np.nan)

    out = df.copy()
    out["km"]      = kms
    out["heures"]  = heures
    out["renta"]   = (out["total_vente"] / out["km"].replace(0, np.nan)).round(2)
    return out, echecs_geo


# ══════════════════════════════════════════════════════════════════
#  AGRÉGATION PAR DÉPARTEMENT
# ══════════════════════════════════════════════════════════════════

def build_dept_stats(df, base_col="total_vente"):
    d = df[df["dept_decharg"].notna() & (df["dept_decharg"].astype(str) != "")].copy()
    if d.empty:
        return pd.DataFrame()

    if "km" not in d.columns:
        d["km"] = np.nan
    d["km"] = pd.to_numeric(d["km"], errors="coerce")

    if base_col not in d.columns:
        base_col = "total_vente"
    d["_base"] = pd.to_numeric(d[base_col], errors="coerce").fillna(0.0)

    g = d.groupby("dept_decharg", as_index=False).agg(
        nb_dossiers    = ("dossier",        "count"),
        km             = ("km",             "sum"),
        prix_transport = ("prix_transport", "sum"),
        total_vente    = ("total_vente",    "sum"),
        base           = ("_base",          "sum"),
        nb_clients     = ("client",         "nunique"),
    )
    g["km"]        = g["km"].round(0)
    g["renta"]     = (g["base"] / g["km"].replace(0, np.nan)).round(2)
    g["ca_moyen"]  = (g["base"] / g["nb_dossiers"].replace(0, np.nan)).round(0)
    g["km_moyen"]  = (g["km"] / g["nb_dossiers"].replace(0, np.nan)).round(0)
    _tot           = g["base"].sum()
    g["pct_ca"]    = (g["base"] / _tot * 100).round(1) if _tot else np.nan
    g["nom_dept"]  = g["dept_decharg"].map(lambda c: DEPT_NOMS.get(c, "—"))
    return g.sort_values("base", ascending=False).reset_index(drop=True)


DEPT_RENAME = {
    "dept_decharg":   "Dépt",
    "nom_dept":       "Département",
    "nb_dossiers":    "Nb Dossiers",
    "nb_clients":     "Nb Clients",
    "km":             "KM Chargés",
    "km_moyen":       "KM moy/dossier",
    "prix_transport": "Prix Transport (€)",
    "total_vente":    "Total Vente (€)",
    "base":           "CA retenu (€)",
    "ca_moyen":       "CA retenu moy/dossier (€)",
    "pct_ca":         "% du CA retenu",
    "renta":          "Renta €/km",
}

DEPT_ORDER = [
    "dept_decharg", "nom_dept", "nb_dossiers", "nb_clients",
    "km", "km_moyen", "prix_transport", "total_vente", "base",
    "ca_moyen", "pct_ca", "renta",
]


def format_dept(df_dept, avec_km=True, base_col="total_vente"):
    """Met en forme le tableau départements. La colonne « CA retenu » n'est
    affichée que si la base est composite (sinon elle doublonnerait)."""
    if df_dept.empty:
        return df_dept
    cols = DEPT_ORDER if avec_km else [
        c for c in DEPT_ORDER if c not in ("km", "km_moyen", "renta")
    ]
    if base_col in ("total_vente", "prix_transport"):
        cols = [c for c in cols if c != "base"]
    cols = [c for c in cols if c in df_dept.columns]
    return df_dept[cols].rename(columns=DEPT_RENAME)


# ══════════════════════════════════════════════════════════════════
#  EXPORT EXCEL
# ══════════════════════════════════════════════════════════════════

def _style(ws, nb_rows):
    for cell in ws[1]:
        cell.fill      = PatternFill("solid", fgColor="1F3864")
        cell.font      = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center")
    for i in range(2, nb_rows + 2):
        if i % 2 == 0:
            for cell in ws[i]:
                cell.fill = PatternFill("solid", fgColor="EEF2F7")
    for col in ws.columns:
        w = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(w + 4, 55)


def export_excel(df_dept, df_detail, base_col="total_vente"):
    out = io.BytesIO()
    try:
        with pd.ExcelWriter(out, engine="openpyxl") as wr:
            if not df_dept.empty:
                d = format_dept(df_dept, avec_km=True, base_col=base_col).fillna("")
                d.to_excel(wr, sheet_name="Renta Départements", index=False)
                _style(wr.sheets["Renta Départements"], len(d))

            det_rename = {
                "dossier":          "N° Dossier",
                "date_charg":       "Date chargement",
                "client":           "Client",
                "type_transport":   "Type transport",
                "localite_charg":   "Ville chargement",
                "pays_charg":       "Pays charg.",
                "localite_decharg": "Ville déchargement",
                "cp_decharg":       "CP déch.",
                "dept_decharg":     "Dépt déch.",
                "pays_decharg":     "Pays déch.",
                "km":               "KM Chargés",
                "prix_transport":   "Prix Transport (€)",
                "supplements":      "Suppléments (€)",
                "sg":               "S.G. (€)",
                "heures_attente":   "Heures attente (€)",
                "total_vente":      "Total Vente (€)",
                "renta_base":       "Renta €/km",
                "etat_vente":       "État vente",
            }
            cols = [c for c in det_rename if c in df_detail.columns]
            dd = df_detail[cols].rename(columns=det_rename).fillna("")
            dd.to_excel(wr, sheet_name="Détail dossiers", index=False)
            _style(wr.sheets["Détail dossiers"], len(dd))
    except Exception as e:
        st.error(f"❌ Erreur Excel : {e}")
        return b""
    return out.getvalue()


# ══════════════════════════════════════════════════════════════════
#  INTERFACE
# ══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Renta Départements (CA)", page_icon="🇫🇷", layout="wide")

st.title("🇫🇷 Rentabilité par département")
st.caption("Analyse à partir du seul fichier CA — km chargés calculés via PTV (chargement → déchargement).")

if not PTV_API_KEY or PTV_API_KEY == "METS_TA_CLE_ICI":
    st.error("⚠️ Clé PTV_API_KEY non configurée — le calcul des km ne fonctionnera pas.")

file_ca = st.file_uploader("💶 Fichier CA (.xlsx)", type=["xlsx"])

if not file_ca:
    st.info(
        "Charge le fichier CA. Colonnes utilisées : *N° Dossier, Date chargement, "
        "Localité / C.P. / Pays chargement et déchargement, Client facturation, "
        "Etat vente, Prix transport, Total des ventes*."
    )
    st.warning(
        "⚠️ **KM à vide indisponibles ici.** Le fichier CA ne contient ni chauffeur ni "
        "tracteur : impossible de chaîner les dossiers pour détecter les trajets à vide. "
        "La rentabilité affichée est donc en **€/km chargé**. Pour le €/km complet, "
        "utilise la page « Analyse Missions + CA + Calcul KM » avec le fichier missions."
    )
    st.stop()

with st.spinner("📂 Lecture du fichier..."):
    df = parse_ca(file_ca)

if df.empty:
    st.error("Aucune ligne exploitable dans le fichier.")
    st.stop()

# ── Période ──
MOIS_FR = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
           "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
dv = df["date_dt"].dropna()
if not dv.empty:
    d_min, d_max = dv.min(), dv.max()
    periode = (f"{MOIS_FR[d_min.month]} {d_min.year}"
               if (d_min.month, d_min.year) == (d_max.month, d_max.year)
               else f"{d_min:%d/%m/%Y} → {d_max:%d/%m/%Y}")
else:
    periode = "Période inconnue"

st.markdown(f"### 📊 Aperçu — {periode}")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("📁 Dossiers",        len(df))
c2.metric("🇫🇷 Déch. France",   int(df["dept_decharg"].notna().sum()))
c3.metric("🗺️ Départements",    int(df["dept_decharg"].nunique()))
c4.metric("👥 Clients",         df["client"].nunique())
c5.metric("💶 Total Ventes",    f"{df['total_vente'].sum():,.0f} €")

st.divider()

# ══════════════════════════════════════════════════════════════════
#  FILTRES
# ══════════════════════════════════════════════════════════════════

st.markdown("### 🎛️ Filtres")

f1, f2, f3, f4 = st.columns(4)
with f1:
    pays_dispo = sorted([p for p in df["pays_decharg"].unique() if p])
    f_pays = st.multiselect(
        "Pays de déchargement", options=pays_dispo, default=["F"] if "F" in pays_dispo else [],
        format_func=lambda p: PAYS_LABELS.get(p, p),
        placeholder="Tous les pays",
    )
with f2:
    etats = sorted([e for e in df["etat_vente"].unique() if e])
    f_etat = st.multiselect(
        "État vente", options=etats, default=[],
        placeholder="Tous les états",
    )
with f3:
    types = sorted([t for t in df["type_transport"].unique() if t])
    f_type = st.multiselect(
        "Type de transport", options=types, default=[],
        placeholder="Tous les types",
    )
with f4:
    clients = sorted([c for c in df["client"].unique() if c])
    f_client = st.multiselect(
        "Client", options=clients, default=[],
        placeholder="Tous les clients",
    )

g1, g2 = st.columns([2, 3])
with g1:
    mois_dispo = sorted([m for m in df["mois"].unique() if m and m != "NaT"])
    f_mois = st.multiselect(
        "📅 Mois de chargement", options=mois_dispo, default=[],
        placeholder="Tous les mois",
    )
with g2:
    base_choix = st.radio(
        "💰 Base de calcul de la rentabilité",
        options=list(BASES_CA.keys()),
        index=0,
        horizontal=True,
    )
    base_col   = BASES_CA[base_choix]
    base_label = base_choix.split(" ", 1)[1]

_tot_tv  = df["total_vente"].sum()
_tot_bas = df[base_col].sum()
st.caption(
    f"**{base_label}** — {BASES_AIDE[base_col]} "
    f"Soit {_tot_bas:,.0f} € sur {_tot_tv:,.0f} € facturés "
    f"({(_tot_bas / _tot_tv * 100 if _tot_tv else 0):.1f} % du total)."
)

dff = df.copy()
if f_pays:
    dff = dff[dff["pays_decharg"].isin(f_pays)]
if f_etat:
    dff = dff[dff["etat_vente"].isin(f_etat)]
if f_type:
    dff = dff[dff["type_transport"].isin(f_type)]
if f_client:
    dff = dff[dff["client"].isin(f_client)]
if f_mois:
    dff = dff[dff["mois"].isin(f_mois)]

st.info(
    f"**{len(dff)} dossiers** retenus · "
    f"**{dff[base_col].sum():,.0f} €** ({base_label}) · "
    f"**{int(dff['dept_decharg'].nunique())} départements** de déchargement."
)

if dff.empty:
    st.stop()

st.divider()

# ══════════════════════════════════════════════════════════════════
#  CALCUL PTV
# ══════════════════════════════════════════════════════════════════

st.markdown("### 🗺️ Calcul des KM (PTV)")

pts_uniques = len({
    p for p in
    list(zip(dff["localite_charg"], dff["cp_charg"], dff["pays_charg"])) +
    list(zip(dff["localite_decharg"], dff["cp_decharg"], dff["pays_decharg"]))
    if p[0] or p[1]
})
st.caption(
    f"≈ {pts_uniques} points à géocoder et jusqu'à {len(dff)} trajets — "
    f"le cache évite de recalculer entre deux exécutions."
)

cb1, cb2 = st.columns([1, 3])
with cb1:
    go = st.button("🚀 Lancer le calcul PTV", type="primary")
with cb2:
    if st.button("🗑️ Vider le cache PTV"):
        st.session_state.pop("_geo_ca", None)
        st.session_state.pop("_route_ca", None)
        st.session_state.pop("_res_ca", None)
        st.success("Cache vidé.")

if go:
    bar    = st.progress(0.0)
    status = st.empty()
    t0     = time.time()
    res, echecs = run_ptv(dff, status, bar)
    bar.progress(1.0)
    status.success(
        f"✅ Terminé en {time.time() - t0:.0f}s — "
        f"{res['km'].notna().sum()}/{len(res)} dossiers avec km."
    )
    st.session_state["_res_ca"] = res
    if echecs:
        with st.expander(f"⚠️ {len(echecs)} points non géocodés"):
            st.dataframe(
                pd.DataFrame(echecs, columns=["Localité", "CP", "Pays"]),
                use_container_width=True,
            )

# ══════════════════════════════════════════════════════════════════
#  RÉSULTATS
# ══════════════════════════════════════════════════════════════════

res = st.session_state.get("_res_ca")

if res is None:
    st.warning(
        "Lance le calcul PTV pour obtenir la rentabilité €/km. "
        "En attendant, voici le CA par département :"
    )
    dep0 = build_dept_stats(dff, base_col)
    if not dep0.empty:
        st.dataframe(
            format_dept(dep0, avec_km=False, base_col=base_col),
            use_container_width=True, height=500,
        )
    st.stop()

# Réapplique les filtres courants sur le résultat mis en cache
res = res[res["dossier"].isin(dff["dossier"])].copy()

# Rentabilité par dossier recalculée sur la base retenue
res["renta_base"] = (
    pd.to_numeric(res[base_col], errors="coerce") /
    pd.to_numeric(res["km"], errors="coerce").replace(0, np.nan)
).round(2)

st.divider()
st.markdown(f"### 📈 Résultats — base : {base_label}")

km_tot    = pd.to_numeric(res["km"], errors="coerce").fillna(0).sum()
base_tot  = res[base_col].sum()
ca_tot    = res["total_vente"].sum()
pt_tot    = res["prix_transport"].sum()
renta     = base_tot / km_tot if km_tot else 0
renta_tv  = ca_tot / km_tot if km_tot else 0
sans_km   = int(res["km"].isna().sum())

r1, r2, r3, r4, r5 = st.columns(5)
r1.metric("📏 KM Chargés",     f"{km_tot:,.0f} km")
r2.metric("🚚 Prix Transport", f"{pt_tot:,.0f} €")
r3.metric("💶 Total Ventes",   f"{ca_tot:,.0f} €")
r4.metric(
    "📈 Renta globale", f"{renta:.2f} €/km",
    delta=(None if base_col == "total_vente"
           else f"{renta - renta_tv:+.2f} vs total ventes"),
    delta_color="off",
)
r5.metric("⚠️ Sans km",        sans_km)

if sans_km:
    st.caption(f"{sans_km} dossier(s) sans km (géocodage ou routage échoué) — exclus des moyennes €/km.")

tab1, tab2, tab3 = st.tabs([
    "🇫🇷 Par département",
    "📋 Détail dossiers",
    "👥 Par client",
])

with tab1:
    dep = build_dept_stats(res, base_col)

    if dep.empty:
        st.info("Aucun déchargement en France dans la sélection.")
    else:
        t1, t2, t3 = st.columns([1, 1, 2])
        with t1:
            min_dos = st.number_input(
                "Nb dossiers min", min_value=1, max_value=50, value=1, step=1,
                help="Masque les départements trop peu représentés.",
            )
        with t2:
            tri = st.selectbox(
                "Trier par",
                ["Renta €/km", "CA retenu (€)", "Nb Dossiers", "KM Chargés",
                 "CA retenu moy/dossier (€)", "Dépt"],
                index=0,
            )
        with t3:
            asc = st.radio("Ordre", ["Décroissant", "Croissant"],
                           horizontal=True, index=0) == "Croissant"

        depv = dep[dep["nb_dossiers"] >= min_dos].copy()

        if depv.empty:
            st.warning("Aucun département au-dessus du seuil.")
        else:
            col_tri = {v: k for k, v in DEPT_RENAME.items()}.get(tri, "renta")
            depv = depv.sort_values(col_tri, ascending=asc, na_position="last").reset_index(drop=True)

            val = depv[depv["renta"].notna()]
            if not val.empty:
                best  = val.sort_values("renta", ascending=False).iloc[0]
                worst = val.sort_values("renta", ascending=True).iloc[0]
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("🥇 Meilleur", f"{best['renta']:.2f} €/km",
                          f"{best['dept_decharg']} — {best['nom_dept']}")
                m2.metric("🥉 Moins bon", f"{worst['renta']:.2f} €/km",
                          f"{worst['dept_decharg']} — {worst['nom_dept']}")
                m3.metric("🗺️ Départements", len(depv))
                m4.metric("📁 Dossiers", int(depv["nb_dossiers"].sum()))

            st.dataframe(
                format_dept(depv, avec_km=True, base_col=base_col),
                use_container_width=True, height=520,
                column_config={
                    "Renta €/km":                st.column_config.NumberColumn(format="%.2f €"),
                    "Total Vente (€)":           st.column_config.NumberColumn(format="%.0f €"),
                    "Prix Transport (€)":        st.column_config.NumberColumn(format="%.0f €"),
                    "CA retenu (€)":             st.column_config.NumberColumn(format="%.0f €"),
                    "CA retenu moy/dossier (€)": st.column_config.NumberColumn(format="%.0f €"),
                    "% du CA retenu":            st.column_config.NumberColumn(format="%.1f %%"),
                },
            )

            ch = depv[depv["renta"].notna()].copy()
            if not ch.empty:
                ch["Dépt"] = ch["dept_decharg"] + " " + ch["nom_dept"]
                st.bar_chart(ch.set_index("Dépt")["renta"], height=320)
                st.caption(
                    f"Rentabilité €/km chargé par département de déchargement — "
                    f"base : {base_label}."
                )

            st.markdown("##### 🔍 Détail d'un département")
            dep_sel = st.selectbox(
                "Département", options=depv["dept_decharg"].tolist(),
                format_func=dept_label,
            )
            det = res[res["dept_decharg"] == dep_sel]
            st.dataframe(
                det[[c for c in [
                    "dossier", "date_charg", "client", "localite_charg", "pays_charg",
                    "localite_decharg", "cp_decharg", "km", "prix_transport",
                    "supplements", "sg", "total_vente", "renta_base",
                ] if c in det.columns]].rename(columns={
                    "dossier":          "N° Dossier",
                    "date_charg":       "Date",
                    "client":           "Client",
                    "localite_charg":   "Ville charg.",
                    "pays_charg":       "Pays charg.",
                    "localite_decharg": "Ville déch.",
                    "cp_decharg":       "CP",
                    "km":               "KM",
                    "prix_transport":   "Prix Transport €",
                    "supplements":      "Suppl. €",
                    "sg":               "S.G. €",
                    "total_vente":      "Total Vente €",
                    "renta_base":       "€/km",
                }),
                use_container_width=True, height=320,
            )

with tab2:
    st.dataframe(
        res[[c for c in [
            "dossier", "date_charg", "client", "type_transport",
            "localite_charg", "pays_charg", "localite_decharg", "cp_decharg",
            "dept_label", "km", "prix_transport", "supplements", "sg",
            "heures_attente", "total_vente", "renta_base", "etat_vente",
        ] if c in res.columns]].rename(columns={
            "dossier":          "N° Dossier",
            "date_charg":       "Date chargement",
            "client":           "Client",
            "type_transport":   "Type",
            "localite_charg":   "Ville charg.",
            "pays_charg":       "Pays charg.",
            "localite_decharg": "Ville déch.",
            "cp_decharg":       "CP déch.",
            "dept_label":       "Département déch.",
            "km":               "KM Chargés",
            "prix_transport":   "Prix Transport €",
            "supplements":      "Suppl. €",
            "sg":               "S.G. €",
            "heures_attente":   "Attente €",
            "total_vente":      "Total Vente €",
            "renta_base":       "€/km",
            "etat_vente":       "État vente",
        }),
        use_container_width=True, height=520,
    )
    st.caption(f"La colonne €/km est calculée sur : {base_label}.")

with tab3:
    res["_base"] = pd.to_numeric(res[base_col], errors="coerce").fillna(0.0)
    cl = res.groupby("client", as_index=False).agg(
        nb_dossiers = ("dossier",        "count"),
        km          = ("km",             "sum"),
        prix        = ("prix_transport", "sum"),
        ca          = ("total_vente",    "sum"),
        base        = ("_base",          "sum"),
        nb_depts    = ("dept_decharg",   "nunique"),
    )
    cl["renta"]    = (cl["base"] / cl["km"].replace(0, np.nan)).round(2)
    cl["ca_moyen"] = (cl["base"] / cl["nb_dossiers"]).round(0)
    cl["km"]       = cl["km"].round(0)
    cl = cl.sort_values("base", ascending=False)
    if base_col in ("total_vente", "prix_transport"):
        cl = cl.drop(columns=["base"])
    st.dataframe(
        cl.rename(columns={
            "client":      "Client",
            "nb_dossiers": "Nb Dossiers",
            "nb_depts":    "Nb Dépts livrés",
            "km":          "KM Chargés",
            "prix":        "Prix Transport €",
            "ca":          "Total Vente €",
            "base":        "CA retenu €",
            "ca_moyen":    "CA retenu moy/dossier €",
            "renta":       "Renta €/km",
        }),
        use_container_width=True, height=480,
    )
    st.caption(f"Rentabilité calculée sur : {base_label}.")

st.divider()

dep_final = build_dept_stats(res, base_col)
_suffixe  = {"total_vente": "ventes", "prix_transport": "prix_transport",
             "prix_sg": "prix_sg", "prix_supp": "prix_supp"}[base_col]

e1, e2 = st.columns(2)
with e1:
    st.download_button(
        "📥 Rapport Excel",
        data=export_excel(dep_final, res, base_col=base_col),
        file_name=f"Renta_Departements_{_suffixe}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
with e2:
    if not dep_final.empty:
        st.download_button(
            "📥 CSV départements",
            data=format_dept(dep_final, base_col=base_col)
                 .to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            file_name=f"Renta_departements_{_suffixe}.csv",
            mime="text/csv",
        )

st.caption(
    f"ℹ️ Rentabilité en **€/km chargé** sur la base « {base_label} », trajet direct "
    "chargement → déchargement calculé par PTV (profil EUR_TRAILER_TRUCK 44t). "
    "Les km à vide nécessitent le fichier missions (chauffeur + chronologie)."
)
