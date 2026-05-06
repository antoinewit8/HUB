"""
6____Renta_Benne.py
──────────────────────────────────────────────────────────────────
Outil Rentabilité Benne — 1 fichier source, 1 tracteur
──────────────────────────────────────────────────────────────────
Entrée :
  • Fichier Benne (.xlsx) — colonnes attendues :
      Date, Chargement (ville/adresse), CP chargement, Pays chargement,
      Déchargement (ville/adresse), CP déchargement, Pays déchargement,
      Prix transport (€)
    → Toutes les colonnes sont détectées automatiquement par mots-clés.

Sorties :
  • KPIs globaux : CA, km chargés, km à vide, rentabilité €/km
  • Tableau détaillé par ligne (dossier/rotation)
  • Résumé par période (semaine / mois)
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
from dotenv import load_dotenv
from openpyxl import load_workbook
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
VEHICLE      = "EUR_TRAILER_TRUCK"

PAYS_MAP = {
    "F": "France", "B": "Belgium", "D": "Germany", "L": "Luxembourg",
    "NL": "Netherlands", "E": "Spain", "I": "Italy", "CH": "Switzerland",
    "GB": "United Kingdom", "A": "Austria", "P": "Portugal",
    "FR": "France", "BE": "Belgium", "DE": "Germany", "LU": "Luxembourg",
    "IT": "Italy", "ES": "Spain", "AT": "Austria", "PT": "Portugal",
}

PAYS_TO_ISO2 = {
    "F": "FR", "B": "BE", "D": "DE", "L": "LU", "I": "IT",
    "E": "ES", "A": "AT", "P": "PT", "CH": "CH", "GB": "GB",
    "NL": "NL", "FR": "FR", "BE": "BE", "DE": "DE", "LU": "LU",
    "IT": "IT", "ES": "ES", "AT": "AT", "PT": "PT",
}

# ══════════════════════════════════════════════════════════════════
#  UTILS
# ══════════════════════════════════════════════════════════════════

def _norm_col(s):
    s = str(s).strip().lower()
    for src, dst in [("é","e"),("è","e"),("ê","e"),("à","a"),("â","a"),
                     ("ô","o"),("û","u"),("î","i"),("ù","u"),("ç","c")]:
        s = s.replace(src, dst)
    return re.sub(r"[^a-z0-9]", "", s)


def detect_col(df, keywords):
    """Détecte une colonne par liste de mots-clés (exact d'abord, contenance ensuite)."""
    cols_lower = {_norm_col(c): c for c in df.columns}
    for kw in sorted(keywords, key=len, reverse=True):
        kw_n = _norm_col(kw)
        if kw_n in cols_lower:
            return cols_lower[kw_n]
    for col in df.columns:
        col_n = _norm_col(col)
        for kw in sorted(keywords, key=len, reverse=True):
            kw_n = _norm_col(kw)
            if kw_n in col_n:
                return col
    return None


def to_float(s):
    try:
        return float(
            str(s).replace(",", ".").replace("\xa0", "").replace(" ", "")
            .replace("€", "").strip()
        )
    except Exception:
        return 0.0


def _clean(v):
    v = str(v or "").strip()
    return "" if v.lower() in ("nan", "none") else v


# ══════════════════════════════════════════════════════════════════
#  GEOCODAGE PTV
# ══════════════════════════════════════════════════════════════════

def _ptv_by_text(query):
    if not query:
        return None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                f"{GEOCODE_URL}/locations/by-text",
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


def _ptv_by_postal_code(cp, iso2):
    if not cp or not iso2:
        return None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                f"{GEOCODE_URL}/locations/by-postal-code",
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


@st.cache_data(show_spinner=False)
def geocode_stop(ville, cp, pays):
    """Géocode un stop avec fallback cp → texte. Caché par Streamlit."""
    pays_u   = pays.upper() if pays else ""
    pays_full = PAYS_MAP.get(pays_u, pays)
    iso2      = PAYS_TO_ISO2.get(pays_u, pays_u if len(pays_u) == 2 else "")

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
    if ville:
        r = _ptv_by_text(ville)
        if r:
            return r
    return None


def calculate_route_km(coord_a, coord_b):
    """Calcule la distance PTV entre deux coordonnées GPS. Retourne les km ou None."""
    if not coord_a or not coord_b:
        return None
    query_params = [
        ("profile",    VEHICLE),
        ("waypoints",  f"{coord_a[0]},{coord_a[1]}"),
        ("waypoints",  f"{coord_b[0]},{coord_b[1]}"),
    ]
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
            return round(data.get("distance", 0) / 1000, 1)
        except Exception:
            time.sleep(RETRY_DELAY)
    return None


# ══════════════════════════════════════════════════════════════════
#  PARSING FICHIER BENNE
# ══════════════════════════════════════════════════════════════════

BENNE_COL_CANDIDATES = {
    "date":           ["Date", "Date chargement", "Date transport"],
    "ref":            ["N° Dossier", "N°Dossier", "Référence", "Ref", "Dossier", "N°"],
    "ville_charg":    ["Chargement", "Ville chargement", "Localité chargement",
                       "Localite chargement", "Lieu chargement"],
    "cp_charg":       ["CP chargement", "Code postal chargement", "C.P. chargement",
                       "Code postal charge", "CP charge"],
    "pays_charg":     ["Pays chargement", "Pays charge"],
    "ville_decharg":  ["Déchargement", "Dechargement", "Ville déchargement",
                       "Localité déchargement", "Localite dechargement",
                       "Lieu déchargement", "Lieu dechargement"],
    "cp_decharg":     ["CP déchargement", "CP dechargement", "Code postal déchargement",
                       "C.P. déchargement", "Code postal decharge"],
    "pays_decharg":   ["Pays déchargement", "Pays dechargement", "Pays decharge"],
    "prix":           ["Prix transport", "Prix Transport", "Prix", "CA", "Chiffre affaires",
                       "Montant", "Prix €", "Total vente", "Total ventes"],
    "client":         ["Client", "Client facturation", "Nom client"],
    "produit":        ["Produit", "Marchandise", "Nature"],
    "chauffeur":      ["Chauffeur", "Driver", "Conducteur"],
    "tracteur":       ["Tracteur", "Immat. tracteur", "Immatriculation", "Plaque"],
}


def parse_benne(file):
    """
    Lit le fichier benne et retourne un DataFrame normalisé.
    Chaque ligne = 1 rotation (1 chargement → 1 déchargement).
    """
    df = pd.read_excel(file, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    # Détection colonnes
    col_map = {}
    for role, candidates in BENNE_COL_CANDIDATES.items():
        col_map[role] = detect_col(df, candidates)

    # Rapport des colonnes manquantes critiques
    critiques = ["date", "ville_charg", "ville_decharg", "prix"]
    manquantes = [r for r in critiques if col_map.get(r) is None]
    if manquantes:
        st.warning(
            f"⚠️ Colonnes non détectées : **{manquantes}**\n\n"
            f"Colonnes disponibles dans le fichier : `{list(df.columns)}`"
        )

    # Renommage
    rename = {v: k for k, v in col_map.items() if v}
    df = df.rename(columns=rename)

    # Colonnes manquantes → vide
    for col in BENNE_COL_CANDIDATES.keys():
        if col not in df.columns:
            df[col] = ""

    # Nettoyage
    df = df[df["ville_charg"].notna() & (df["ville_charg"].str.strip() != "") &
            (df["ville_charg"].str.lower() != "nan")]
    df = df[df["ville_decharg"].notna() & (df["ville_decharg"].str.strip() != "") &
            (df["ville_decharg"].str.lower() != "nan")]

    # Parsing date
    df["date_dt"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")

    # Parsing prix
    df["prix_float"] = df["prix"].apply(to_float)

    # Nettoyage champs texte
    for col in ["ville_charg", "cp_charg", "pays_charg",
                "ville_decharg", "cp_decharg", "pays_decharg",
                "client", "produit", "chauffeur", "tracteur", "ref"]:
        df[col] = df[col].apply(_clean)

    # Pays par défaut si vide → "BE" (benne CBS Béton = surtout Belgique/France)
    df["pays_charg"]   = df["pays_charg"].apply(  lambda v: v if v else "B")
    df["pays_decharg"] = df["pays_decharg"].apply(lambda v: v if v else "B")

    df = df.reset_index(drop=True)
    df["_idx"] = df.index  # identifiant ligne pour jointure

    return df


# ══════════════════════════════════════════════════════════════════
#  CALCUL KM VIA PTV
# ══════════════════════════════════════════════════════════════════

def compute_km_benne(df, progress_cb=None):
    """
    Pour chaque ligne du fichier :
      1. Géocode chargement et déchargement
      2. Calcule km chargés (charg → décharg)
      3. Calcule km à vide (décharg[i] → charg[i+1]) en ordre chronologique

    Retourne df enrichi avec colonnes km_charge, km_vide, coords_charg, coords_decharg.
    """
    df = df.copy().sort_values("date_dt").reset_index(drop=True)

    # ── 1. Géocodage de tous les points uniques ──
    points = {}
    for _, row in df.iterrows():
        for prefix in ("charg", "decharg"):
            key = (
                _clean(str(row.get(f"ville_{prefix}", ""))),
                _clean(str(row.get(f"cp_{prefix}",    ""))),
                _clean(str(row.get(f"pays_{prefix}",  ""))).upper(),
            )
            if key not in points:
                points[key] = None

    total_geo = len(points)
    geo_keys  = list(points.keys())

    for i, key in enumerate(geo_keys):
        ville, cp, pays = key
        label = f"{ville} {cp}".strip() or "(inconnu)"
        if progress_cb:
            progress_cb(f"🌍 Géocodage {i+1}/{total_geo} : {label}…", i / total_geo)
        coords = geocode_stop(ville, cp, pays)
        points[key] = coords
        if coords is None and (ville or cp):
            st.warning(f"⚠️ Géocodage échoué : **{label}** ({pays})")

    # ── 2. Km chargés par ligne ──
    km_charges = []
    for i, row in df.iterrows():
        key_ch = (
            _clean(str(row.get("ville_charg",  ""))),
            _clean(str(row.get("cp_charg",     ""))),
            _clean(str(row.get("pays_charg",   ""))).upper(),
        )
        key_de = (
            _clean(str(row.get("ville_decharg",  ""))),
            _clean(str(row.get("cp_decharg",     ""))),
            _clean(str(row.get("pays_decharg",   ""))).upper(),
        )
        c_ch = points.get(key_ch)
        c_de = points.get(key_de)
        df.at[i, "_coords_charg"]  = str(c_ch) if c_ch else ""
        df.at[i, "_coords_decharg"] = str(c_de) if c_de else ""

        if progress_cb:
            progress_cb(
                f"📍 Km chargé ligne {i+1}/{len(df)} : "
                f"{row.get('ville_charg','?')} → {row.get('ville_decharg','?')}…",
                (total_geo + i) / (total_geo + len(df) * 2),
            )
        km = calculate_route_km(c_ch, c_de)
        km_charges.append(km)

    df["km_charge"] = km_charges

    # ── 3. Km à vide entre lignes consécutives ──
    km_vides = [None] * len(df)
    vide_detail = []  # pour le tableau détail

    for i in range(len(df) - 1):
        key_de_actuel = (
            _clean(str(df.at[i,   "ville_decharg"])),
            _clean(str(df.at[i,   "cp_decharg"])),
            _clean(str(df.at[i,   "pays_decharg"])).upper(),
        )
        key_ch_suivant = (
            _clean(str(df.at[i+1, "ville_charg"])),
            _clean(str(df.at[i+1, "cp_charg"])),
            _clean(str(df.at[i+1, "pays_charg"])).upper(),
        )
        c_fin   = points.get(key_de_actuel)
        c_debut = points.get(key_ch_suivant)

        ville_fin   = df.at[i,   "ville_decharg"]
        ville_debut = df.at[i+1, "ville_charg"]

        if progress_cb:
            progress_cb(
                f"⚡ Km à vide {i+1}/{len(df)-1} : "
                f"{ville_fin} → {ville_debut}…",
                (total_geo + len(df) + i) / (total_geo + len(df) * 2),
            )

        km_v = calculate_route_km(c_fin, c_debut)
        km_vides[i] = km_v

        vide_detail.append({
            "ligne_depart":  i + 1,
            "ligne_arrivee": i + 2,
            "ville_depart":  ville_fin,
            "ville_arrivee": ville_debut,
            "date_depart":   df.at[i,   "date_dt"],
            "date_arrivee":  df.at[i+1, "date_dt"],
            "km_vide":       km_v,
        })

    df["km_vide"] = km_vides

    # Rentabilité par ligne
    df["km_complet"] = df["km_charge"].fillna(0) + df["km_vide"].fillna(0)
    df["renta_km"]   = (
        df["prix_float"] / df["km_complet"].replace(0, np.nan)
    ).round(3)

    return df, pd.DataFrame(vide_detail)


# ══════════════════════════════════════════════════════════════════
#  EXPORT EXCEL
# ══════════════════════════════════════════════════════════════════

def export_excel_benne(df_result, df_vide, df_periode):
    output = io.BytesIO()

    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:

            # ── Feuille principale ──
            col_rename_main = {
                "date":          "Date",
                "ref":           "Réf / Dossier",
                "client":        "Client",
                "produit":       "Produit",
                "chauffeur":     "Chauffeur",
                "tracteur":      "Tracteur",
                "ville_charg":   "Chargement",
                "ville_decharg": "Déchargement",
                "prix_float":    "Prix Transport (€)",
                "km_charge":     "KM Chargés",
                "km_vide":       "KM À Vide",
                "km_complet":    "KM Complet",
                "renta_km":      "Renta €/km",
            }
            cols_dispo = [c for c in col_rename_main if c in df_result.columns]
            df_exp = df_result[cols_dispo].copy()
            df_exp = df_exp.rename(columns=col_rename_main).fillna("")
            df_exp.to_excel(writer, sheet_name="Rotations", index=False)
            _style_sheet(writer.sheets["Rotations"], len(df_exp))

            # ── Résumé par période ──
            if not df_periode.empty:
                df_periode.to_excel(writer, sheet_name="Résumé Période", index=False)
                _style_sheet(writer.sheets["Résumé Période"], len(df_periode))

            # ── KM à vide détail ──
            if not df_vide.empty:
                vide_rename = {
                    "ligne_depart":  "Ligne départ",
                    "ligne_arrivee": "Ligne arrivée",
                    "ville_depart":  "Ville départ",
                    "ville_arrivee": "Ville arrivée",
                    "date_depart":   "Date départ",
                    "date_arrivee":  "Date arrivée",
                    "km_vide":       "KM À Vide",
                }
                df_vide_exp = df_vide[[c for c in vide_rename if c in df_vide.columns]].copy()
                df_vide_exp = df_vide_exp.rename(columns=vide_rename).fillna("")
                df_vide_exp.to_excel(writer, sheet_name="KM À Vide Détail", index=False)
                _style_sheet(writer.sheets["KM À Vide Détail"], len(df_vide_exp))

    except Exception as e:
        st.error(f"❌ Erreur génération Excel : {e}")
        return b""

    return output.getvalue()


def _style_sheet(ws, nb_rows):
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
#  RÉSUMÉ PAR PÉRIODE
# ══════════════════════════════════════════════════════════════════

def make_resume_periode(df, group_by="semaine"):
    """Génère un résumé agrégé par semaine ou par mois."""
    df = df.copy()
    df = df[df["date_dt"].notna()]

    if group_by == "semaine":
        df["_periode"] = df["date_dt"].dt.to_period("W").astype(str)
        label_col = "Semaine"
    else:
        df["_periode"] = df["date_dt"].dt.to_period("M").astype(str)
        label_col = "Mois"

    agg = df.groupby("_periode", as_index=False).agg(
        Rotations      = ("prix_float",  "count"),
        CA_Total       = ("prix_float",  "sum"),
        KM_Charges     = ("km_charge",   "sum"),
        KM_Vide        = ("km_vide",     "sum"),
    ).round(1)

    agg["KM_Complet"]     = agg["KM_Charges"] + agg["KM_Vide"]
    agg["Pct_Vide"]       = (
        agg["KM_Vide"] / agg["KM_Complet"].replace(0, np.nan) * 100
    ).round(1)
    agg["Renta_km"]       = (
        agg["CA_Total"] / agg["KM_Complet"].replace(0, np.nan)
    ).round(3)
    agg["CA_moy_rotation"] = (
        agg["CA_Total"] / agg["Rotations"].replace(0, np.nan)
    ).round(0)

    agg = agg.rename(columns={
        "_periode":      label_col,
        "Rotations":     "Nb Rotations",
        "CA_Total":      "CA (€)",
        "KM_Charges":    "KM Chargés",
        "KM_Vide":       "KM À Vide",
        "KM_Complet":    "KM Complet",
        "Pct_Vide":      "% À Vide",
        "Renta_km":      "Renta €/km",
        "CA_moy_rotation": "CA moy/rotation (€)",
    })

    return agg


# ══════════════════════════════════════════════════════════════════
#  INTERFACE STREAMLIT
# ══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Rentabilité Benne", page_icon="🪣", layout="wide")

st.title("🪣 Rentabilité Benne")
st.caption("Analyse des rotations benne : CA, km chargés, km à vide, rentabilité €/km.")

if not PTV_API_KEY or PTV_API_KEY == "METS_TA_CLE_ICI":
    st.error("⚠️ Clé PTV_API_KEY non configurée. Le calcul de distances ne fonctionnera pas.")

st.divider()

# ── Upload ──
st.markdown("#### 📂 Fichier Benne")
st.markdown(
    "Le fichier doit contenir une ligne par rotation avec au minimum : "
    "**date**, **ville chargement**, **ville déchargement**, **prix transport**."
)
file_benne = st.file_uploader(
    "Dépose ton fichier Excel benne (.xlsx)",
    type=["xlsx"],
    key="benne",
)

st.divider()

# ── Parse & affichage immédiat ──
if file_benne:

    with st.spinner("📂 Lecture du fichier…"):
        try:
            df_raw = parse_benne(file_benne)
        except Exception as e:
            st.error(f"❌ Erreur lecture fichier : {e}")
            st.stop()

    # ── Période ──
    dates_val = df_raw["date_dt"].dropna()
    if not dates_val.empty:
        MOIS_FR = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                   "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
        d_min = dates_val.min()
        d_max = dates_val.max()
        if d_min.month == d_max.month and d_min.year == d_max.year:
            periode_label = f"{MOIS_FR[d_min.month]} {d_min.year}"
        else:
            periode_label = f"{d_min.strftime('%d/%m/%Y')} → {d_max.strftime('%d/%m/%Y')}"
    else:
        periode_label = "Période inconnue"

    # ── KPIs aperçu (sans PTV) ──
    st.markdown(f"### 📊 Aperçu — {periode_label}")

    ca_total    = df_raw["prix_float"].sum()
    nb_rot      = len(df_raw)
    ca_moy      = ca_total / nb_rot if nb_rot > 0 else 0
    tracteurs   = df_raw["tracteur"].replace("", np.nan).dropna().unique()
    chauffeurs  = df_raw["chauffeur"].replace("", np.nan).dropna().unique()

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("🔄 Rotations",       nb_rot)
    k2.metric("💶 CA Total",        f"{ca_total:,.0f} €")
    k3.metric("📈 CA moy/rotation", f"{ca_moy:,.0f} €")
    k4.metric("🚜 Tracteur(s)",     len(tracteurs) if len(tracteurs) > 0 else "—")
    k5.metric("👤 Chauffeur(s)",    len(chauffeurs) if len(chauffeurs) > 0 else "—")

    st.divider()

    # ── Tableau consolidé ──
    st.markdown("### 📋 Tableau des rotations")

    # Filtres
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        villes_charg_dispo = sorted(df_raw["ville_charg"].replace("", np.nan).dropna().unique())
        filtre_charg = st.multiselect(
            "📍 Filtrer par lieu de chargement :",
            options=villes_charg_dispo,
            default=[],
            placeholder="Tous",
        )
    with fc2:
        villes_decharg_dispo = sorted(df_raw["ville_decharg"].replace("", np.nan).dropna().unique())
        filtre_decharg = st.multiselect(
            "📍 Filtrer par lieu de déchargement :",
            options=villes_decharg_dispo,
            default=[],
            placeholder="Tous",
        )
    with fc3:
        clients_dispo = sorted(df_raw["client"].replace("", np.nan).dropna().unique())
        filtre_client = st.multiselect(
            "🏢 Filtrer par client :",
            options=clients_dispo,
            default=[],
            placeholder="Tous les clients",
        )

    df_display = df_raw.copy()
    if filtre_charg:
        df_display = df_display[df_display["ville_charg"].isin(filtre_charg)]
    if filtre_decharg:
        df_display = df_display[df_display["ville_decharg"].isin(filtre_decharg)]
    if filtre_client:
        df_display = df_display[df_display["client"].isin(filtre_client)]

    cols_show = ["date", "ref", "client", "produit", "ville_charg", "ville_decharg",
                 "prix_float", "chauffeur", "tracteur"]

    st.dataframe(
        df_display[[c for c in cols_show if c in df_display.columns]].rename(columns={
            "date":          "Date",
            "ref":           "Réf",
            "client":        "Client",
            "produit":       "Produit",
            "ville_charg":   "Chargement",
            "ville_decharg": "Déchargement",
            "prix_float":    "Prix (€)",
            "chauffeur":     "Chauffeur",
            "tracteur":      "Tracteur",
        }),
        use_container_width=True,
        height=380,
    )

    st.divider()

    # ══════════════════════════════════════════════════════════
    #  CALCUL KM VIA PTV
    # ══════════════════════════════════════════════════════════

    st.markdown("### 🗺️ Calcul KM via PTV")
    st.info(
        f"ℹ️ Le calcul va géocoder les arrêts et calculer les km PTV pour les "
        f"**{nb_rot} rotations** du fichier. Les km à vide sont calculés entre chaque "
        f"déchargement et le chargement suivant (ordre chronologique)."
    )

    btn_ptv = st.button("🚀 Lancer le calcul PTV", type="primary")

    if btn_ptv:
        for key in ["df_result_benne", "df_vide_benne"]:
            st.session_state.pop(key, None)

        progress_bar = st.progress(0)
        status_text  = st.empty()

        def _progress(msg, pct=0.0):
            status_text.text(msg)
            progress_bar.progress(min(float(pct), 1.0))

        try:
            df_result, df_vide = compute_km_benne(df_raw, progress_cb=_progress)
            progress_bar.progress(1.0)
            status_text.success("✅ Calcul PTV terminé !")
            st.session_state["df_result_benne"] = df_result
            st.session_state["df_vide_benne"]   = df_vide
        except Exception as e:
            st.error(f"❌ Erreur durant le calcul PTV : {e}")

    # ── Affichage résultats PTV ──
    if "df_result_benne" in st.session_state:
        df_result = st.session_state["df_result_benne"]
        df_vide   = st.session_state.get("df_vide_benne", pd.DataFrame())

        st.divider()
        st.markdown("### 📈 Résultats KM")

        km_ch_sum   = df_result["km_charge"].sum()
        km_vide_sum = df_result["km_vide"].fillna(0).sum()
        km_complet  = km_ch_sum + km_vide_sum
        pct_vide    = (km_vide_sum / km_complet * 100) if km_complet > 0 else 0
        ca_total_r  = df_result["prix_float"].sum()
        rent_global = ca_total_r / km_complet if km_complet > 0 else 0

        kp1, kp2, kp3, kp4, kp5, kp6 = st.columns(6)
        kp1.metric("📏 KM Chargés",      f"{km_ch_sum:,.0f} km")
        kp2.metric("⚡ KM À Vide",        f"{km_vide_sum:,.0f} km")
        kp3.metric("🔄 KM Total complet", f"{km_complet:,.0f} km")
        kp4.metric("% À Vide",            f"{pct_vide:.1f}%")
        kp5.metric("💶 CA Total",         f"{ca_total_r:,.0f} €")
        kp6.metric("📈 Rentabilité",      f"{rent_global:.3f} €/km")

        st.divider()

        # ── Tabs ──
        tab1, tab2, tab3, tab4 = st.tabs([
            "📋 Détail rotations",
            "📅 Résumé semaine",
            "📆 Résumé mois",
            "⚡ KM à vide détail",
        ])

        with tab1:
            cols_res = ["date", "ref", "client", "produit",
                        "ville_charg", "ville_decharg",
                        "prix_float", "km_charge", "km_vide", "km_complet", "renta_km"]
            st.dataframe(
                df_result[[c for c in cols_res if c in df_result.columns]].rename(columns={
                    "date":          "Date",
                    "ref":           "Réf",
                    "client":        "Client",
                    "produit":       "Produit",
                    "ville_charg":   "Chargement",
                    "ville_decharg": "Déchargement",
                    "prix_float":    "Prix (€)",
                    "km_charge":     "KM Chargés",
                    "km_vide":       "KM À Vide",
                    "km_complet":    "KM Complet",
                    "renta_km":      "Renta €/km",
                }),
                use_container_width=True,
                height=400,
            )

        with tab2:
            df_sem = make_resume_periode(df_result, group_by="semaine")
            st.dataframe(df_sem, use_container_width=True)

        with tab3:
            df_mois = make_resume_periode(df_result, group_by="mois")
            st.dataframe(df_mois, use_container_width=True)

        with tab4:
            if not df_vide.empty:
                st.dataframe(
                    df_vide.rename(columns={
                        "ligne_depart":  "Ligne départ",
                        "ligne_arrivee": "Ligne arrivée",
                        "ville_depart":  "Ville départ",
                        "ville_arrivee": "Ville arrivée",
                        "date_depart":   "Date départ",
                        "date_arrivee":  "Date arrivée",
                        "km_vide":       "KM À Vide",
                    }),
                    use_container_width=True,
                )
            else:
                st.info("Aucun trajet à vide détecté.")

        st.divider()

        # ── Export ──
        df_mois_exp = make_resume_periode(df_result, group_by="mois")
        excel_bytes = export_excel_benne(df_result, df_vide, df_mois_exp)

        st.download_button(
            label="📥 Télécharger le rapport Excel",
            data=excel_bytes,
            file_name="Rapport_Renta_Benne.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

        if st.button("🔄 Nouveau calcul"):
            for key in ["df_result_benne", "df_vide_benne"]:
                st.session_state.pop(key, None)
            st.rerun()

else:
    st.markdown("""
    #### Comment utiliser cet outil

    1. **Chargez le fichier Excel benne** — une ligne par rotation avec :
       - `Date` de la rotation
       - `Chargement` : ville/lieu de chargement + CP + pays
       - `Déchargement` : ville/lieu de déchargement + CP + pays
       - `Prix transport` : CA de la rotation (€)
       - *(optionnel)* `Client`, `Produit`, `Chauffeur`, `Tracteur`, `Réf`

    2. Consultez le **tableau des rotations** et utilisez les filtres

    3. Cliquez sur **Lancer le calcul PTV** pour obtenir :
       - Les **km chargés** par rotation (chargement → déchargement)
       - Les **km à vide** entre chaque déchargement et le chargement suivant
       - La **rentabilité €/km** par rotation et par période

    4. **Téléchargez le rapport Excel** (rotations + résumé mensuel + détail km à vide)

    ---
    > ⚙️ La clé PTV doit être configurée dans `.env` (`PTV_API_KEY`).
    """)
