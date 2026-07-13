"""
6____Tractionnaires_KM.py
──────────────────────────────────────────────────────────────────
Outil TX-FLEX : Analyse Tractionnaires — KM PTV + CA + Rentabilité
──────────────────────────────────────────────────────────────────
Entrée : Export tractionnaires (.xlsx)
  Colonnes : Tractionnaire, Chauffeur, Véhicule, Remorque, Dossier,
             Référence, Type transport, CMR, Date chargement,
             CP chargement, Localité chargement, Pays chargement,
             Date déchargement, CP déchargement, Localité déchargement,
             Pays déchargement, Statut facturation, Ventes totales,
             Département vente, Client

Sorties :
  • Tableau détail dossiers avec KM PTV estimés
  • Résumé par tractionnaire / par véhicule : dossiers, KM, CA, rentabilité
  • Export Excel

Nouveau :
  • Filtres Véhicule / Chauffeur dans le tableau détail
  • Sélection Tractionnaire + Véhicule pour le calcul PTV (cascade)
  • Toggle KM à vide (économie d'appels PTV)
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
import datetime as _dt
from typing import Optional, Tuple, List
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

MOIS_FR = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
           "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

# ══════════════════════════════════════════════════════════════════
#  UTILITAIRES
# ══════════════════════════════════════════════════════════════════

def _norm_col(s: str) -> str:
    s = str(s).strip().lower()
    for src, dst in [("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("â", "a"),
                     ("ô", "o"), ("û", "u"), ("î", "i"), ("ù", "u"), ("ç", "c")]:
        s = s.replace(src, dst)
    return re.sub(r"[^a-z0-9]", "", s)


def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols_lower = {_norm_col(c): c for c in df.columns}
    for cand in candidates:
        key = _norm_col(cand)
        if key in cols_lower:
            return cols_lower[key]
    return None


def _clean(v) -> str:
    v = str(v or "").strip()
    return "" if v.lower() in ("nan", "none") else v


def _to_float(s) -> float:
    try:
        return float(str(s).replace(",", ".").replace("\u00a0", "")
                     .replace(" ", "").replace("€", "").strip())
    except Exception:
        return 0.0


def _opts(series: pd.Series) -> List[str]:
    """Options triées, sans vides ni 'nan'."""
    return sorted({v for v in series.dropna().astype(str)
                   if v.strip() and v.strip().lower() != "nan"})


# ══════════════════════════════════════════════════════════════════
#  GEOCODAGE
# ══════════════════════════════════════════════════════════════════

def _ptv_by_text(query: str) -> Optional[Tuple[float, float]]:
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


def _ptv_by_postal_code(cp: str, iso2: str) -> Optional[Tuple[float, float]]:
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


def geocode_with_fallback(ville: str, cp: str, pays: str) -> Optional[Tuple[float, float]]:
    pays_full = PAYS_MAP.get(pays.upper(), pays) if pays else ""
    iso2      = PAYS_TO_ISO2.get(pays.upper(), pays.upper() if len(pays) == 2 else "")

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


# ══════════════════════════════════════════════════════════════════
#  CALCUL ROUTE PTV
# ══════════════════════════════════════════════════════════════════

def calculate_route(coords_list: list) -> Optional[dict]:
    if len(coords_list) < 2:
        return None
    query_params = [("profile", VEHICLE), ("results", "POLYLINE")]
    for lat, lon in coords_list:
        query_params.append(("waypoints", f"{lat},{lon}"))
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                f"{PTV_BASE_URL}/routes",
                headers=HEADERS, params=query_params, timeout=30,
            )
            if resp.status_code != 200:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                return None
            data = resp.json()
            return {"km": round(data.get("distance", 0) / 1000, 1)}
        except Exception:
            time.sleep(RETRY_DELAY)
    return None


# ══════════════════════════════════════════════════════════════════
#  PARSING
# ══════════════════════════════════════════════════════════════════

TRACT_COL_CANDIDATES = {
    "tractionnaire":   ["Tractionnaire"],
    "chauffeur":       ["Chauffeur"],
    "vehicule":        ["Véhicule", "Vehicule"],
    "remorque":        ["Remorque"],
    "dossier":         ["Dossier", "N° Dossier"],
    "reference":       ["Référence", "Reference"],
    "type_transport":  ["Type de transport", "Type transport"],
    "cmr":             ["CMR"],
    "date_charg":      ["Date chargement", "Date Chargement"],
    "cp_charg":        ["C.P. chargement", "CP chargement"],
    "localite_charg":  ["Localité chargement", "Localite chargement"],
    "pays_charg":      ["Pays chargement"],
    "date_decharg":    ["Date déchargement", "Date dechargement"],
    "cp_decharg":      ["C.P. déchargement", "CP dechargement"],
    "localite_decharg": ["Localité déchargement", "Localite dechargement"],
    "pays_decharg":    ["Pays déchargement", "Pays dechargement"],
    "statut":          ["Statut facturation", "Statut"],
    "ventes_totales":  ["Ventes totales", "Total ventes", "CA"],
    "dept_vente":      ["Département vente", "Dept vente"],
    "client":          ["Client"],
}


def parse_tractionnaires(file) -> pd.DataFrame:
    df = pd.read_excel(file, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    cols_lower = {_norm_col(c): c for c in df.columns}
    col_map = {}
    for role, candidates in TRACT_COL_CANDIDATES.items():
        found = None
        for cand in candidates:
            key = _norm_col(cand)
            if key in cols_lower:
                found = cols_lower[key]
                break
        col_map[role] = found

    critiques = ["tractionnaire", "dossier", "localite_charg", "localite_decharg"]
    manquantes = [r for r in critiques if col_map.get(r) is None]
    if manquantes:
        st.warning(f"⚠️ Colonnes non détectées : {manquantes} — Colonnes dispo : {list(df.columns)}")

    rename = {v: k for k, v in col_map.items() if v}
    df = df.rename(columns=rename)
    for col in TRACT_COL_CANDIDATES:
        if col not in df.columns:
            df[col] = ""

    df["dossier"] = df["dossier"].astype(str).str.strip()
    df = df[df["dossier"].notna() & (df["dossier"] != "") & (df["dossier"] != "nan")]
    df = df[df["dossier"].str.match(r"^\d+", na=False)]

    df["ventes_totales"] = df["ventes_totales"].apply(_to_float)

    for col in ["tractionnaire", "chauffeur", "vehicule", "remorque",
                "localite_charg", "cp_charg", "pays_charg",
                "localite_decharg", "cp_decharg", "pays_decharg",
                "statut", "client"]:
        df[col] = df[col].apply(_clean)

    df["_date_charg_dt"] = pd.to_datetime(
        df["date_charg"].astype(str).str.strip().str[:10], format="%Y-%m-%d", errors="coerce"
    )
    df["_date_decharg_dt"] = pd.to_datetime(
        df["date_decharg"].astype(str).str.strip().str[:10], format="%Y-%m-%d", errors="coerce"
    )
    df["_date_dt"] = df["_date_charg_dt"]

    # Dates formatées pour affichage (fallback = valeur brute si non parsable)
    df["date_charg_fmt"] = df["_date_charg_dt"].dt.strftime("%d/%m/%Y")
    df["date_charg_fmt"] = df["date_charg_fmt"].fillna(df["date_charg"].apply(_clean))
    df["date_decharg_fmt"] = df["_date_decharg_dt"].dt.strftime("%d/%m/%Y")
    df["date_decharg_fmt"] = df["date_decharg_fmt"].fillna(df["date_decharg"].apply(_clean))

    return df


# ══════════════════════════════════════════════════════════════════
#  CALCUL KM PTV
# ══════════════════════════════════════════════════════════════════

def compute_km(df: pd.DataFrame, progress_cb=None, calc_vide: bool = True) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Géocode tous les points uniques et calcule :
    - km_ptv  : km chargement → déchargement par dossier
    - km_vide : déchargement → chargement suivant, par véhicule, ordre chronologique

    calc_vide=False : saute entièrement le calcul des km à vide (économie d'appels PTV).

    Retourne (df_enrichi, df_vide).
    """
    df = df.copy()

    # ── Géocodage de tous les points uniques ──────────────────
    points = set()
    for _, row in df.iterrows():
        if row["localite_charg"] or row["cp_charg"]:
            points.add((_clean(row["localite_charg"]), _clean(row["cp_charg"]), _clean(row["pays_charg"])))
        if row["localite_decharg"] or row["cp_decharg"]:
            points.add((_clean(row["localite_decharg"]), _clean(row["cp_decharg"]), _clean(row["pays_decharg"])))

    geo_cache = {}
    total = len(points)
    for i, (ville, cp, pays) in enumerate(points):
        if progress_cb:
            progress_cb(f"🌍 Géocodage {i+1}/{total} : {ville} {cp}...", (i + 1) / max(total, 1) * 0.3)
        coords = geocode_with_fallback(ville, cp, pays)
        geo_cache[(ville, cp, pays)] = coords
        if coords is None:
            st.warning(f"⚠️ Géocodage échoué : {ville}, {cp}, {pays}")

    # ── Km chargés par dossier ────────────────────────────────
    km_results = []
    total_dos = len(df)
    for i, (_, row) in enumerate(df.iterrows()):
        if progress_cb:
            progress_cb(
                f"📍 KM chargé dossier {row['dossier']} ({i+1}/{total_dos})...",
                0.3 + (i + 1) / max(total_dos, 1) * (0.7 if not calc_vide else 0.4),
            )
        c_ch = geo_cache.get((_clean(row["localite_charg"]), _clean(row["cp_charg"]), _clean(row["pays_charg"])))
        c_de = geo_cache.get((_clean(row["localite_decharg"]), _clean(row["cp_decharg"]), _clean(row["pays_decharg"])))
        if c_ch and c_de:
            res = calculate_route([c_ch, c_de])
            km_results.append(res["km"] if res else None)
        else:
            km_results.append(None)
    df["km_ptv"] = km_results

    # ── Km à vide par véhicule ────────────────────────────────
    df["_sort_key"] = df["_date_decharg_dt"].fillna(df["_date_charg_dt"])
    vide_legs = []

    if calc_vide:
        vehicules = [v for v in df["vehicule"].unique() if v and v != "nan"]
        nb_veh = len(vehicules)

        for v_idx, vehicule in enumerate(vehicules):
            grp = df[df["vehicule"] == vehicule].sort_values("_sort_key").reset_index(drop=True)

            for i in range(len(grp) - 1):
                row_cur  = grp.iloc[i]
                row_next = grp.iloc[i + 1]

                # Point de départ = déchargement du dossier courant
                c_de = geo_cache.get((
                    _clean(row_cur["localite_decharg"]),
                    _clean(row_cur["cp_decharg"]),
                    _clean(row_cur["pays_decharg"]),
                ))
                # Point d'arrivée = chargement du dossier suivant
                c_ch = geo_cache.get((
                    _clean(row_next["localite_charg"]),
                    _clean(row_next["cp_charg"]),
                    _clean(row_next["pays_charg"]),
                ))

                if c_de and c_ch:
                    if progress_cb:
                        progress_cb(
                            f"⚡ KM vide {vehicule} : {row_cur['localite_decharg']} → {row_next['localite_charg']}...",
                            0.7 + (v_idx + 1) / max(nb_veh, 1) * 0.3,
                        )
                    res = calculate_route([c_de, c_ch])
                    km_vide = res["km"] if res else None
                else:
                    km_vide = None

                vide_legs.append({
                    "vehicule":        vehicule,
                    "tractionnaire":   row_cur.get("tractionnaire", ""),
                    "dossier_depart":  row_cur["dossier"],
                    "dossier_arrivee": row_next["dossier"],
                    "ville_depart":    row_cur["localite_decharg"],
                    "ville_arrivee":   row_next["localite_charg"],
                    "date_depart":     row_cur["_sort_key"].strftime("%d/%m/%Y") if pd.notna(row_cur["_sort_key"]) else "",
                    "km_vide":         km_vide,
                })

    df_vide = pd.DataFrame(vide_legs)

    if not df_vide.empty:
        km_vide_by_dos = df_vide.groupby("dossier_depart")["km_vide"].sum()
        df["km_vide"] = df["dossier"].map(km_vide_by_dos).fillna(0)
    else:
        df["km_vide"] = 0.0

    df["km_total_complet"] = df["km_ptv"].fillna(0) + df["km_vide"]

    return df, df_vide


# ══════════════════════════════════════════════════════════════════
#  RESUMES
# ══════════════════════════════════════════════════════════════════

def build_resume(df: pd.DataFrame, cle: str, label: str) -> pd.DataFrame:
    """Résumé agrégé (KM + CA + rentabilité) sur une clé : tractionnaire ou vehicule."""
    res = df.groupby(cle, as_index=False).agg(
        Dossiers   = ("dossier",         "count"),
        KM_Charges = ("km_ptv",          "sum"),
        KM_Vide    = ("km_vide",         "sum"),
        CA_Total   = ("ventes_totales",  "sum"),
    ).round(1)
    res["KM Complet"]       = (res["KM_Charges"] + res["KM_Vide"]).round(1)
    res["% KM Vide"]        = (res["KM_Vide"] / res["KM Complet"].replace(0, np.nan) * 100).round(1)
    res["CA moy/dossier"]   = (res["CA_Total"] / res["Dossiers"].replace(0, np.nan)).round(0)
    res["Rentabilité €/km"] = (res["CA_Total"] / res["KM Complet"].replace(0, np.nan)).round(2)
    res = res.rename(columns={
        cle: label,
        "KM_Charges": "KM Chargés",
        "KM_Vide": "KM À Vide",
        "CA_Total": "CA Total (€)",
    }).sort_values("CA Total (€)", ascending=False)
    return res


# ══════════════════════════════════════════════════════════════════
#  EXPORT EXCEL
# ══════════════════════════════════════════════════════════════════

def export_excel(df_detail: pd.DataFrame,
                 df_resume_tract: pd.DataFrame,
                 df_resume_veh: Optional[pd.DataFrame] = None,
                 df_vide: Optional[pd.DataFrame] = None) -> bytes:
    output = io.BytesIO()
    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:

            # Feuille détail
            col_rename_detail = {
                "tractionnaire":    "Tractionnaire",
                "chauffeur":        "Chauffeur",
                "vehicule":         "Véhicule",
                "remorque":         "Remorque",
                "dossier":          "N° Dossier",
                "client":           "Client",
                "statut":           "Statut facturation",
                "date_charg_fmt":   "Date chargement",
                "localite_charg":   "Localité chargement",
                "date_decharg_fmt": "Date déchargement",
                "localite_decharg": "Localité déchargement",
                "ventes_totales":   "Ventes totales (€)",
                "km_ptv":           "KM Chargé",
                "km_vide":          "KM À Vide",
                "km_total_complet": "KM Complet",
                "rentabilite":      "Rentabilité €/km",
            }
            df_d = df_detail.copy()
            df_d["rentabilite"] = (
                df_d["ventes_totales"] / df_d["km_total_complet"].replace(0, np.nan)
            ).round(2)
            cols = [c for c in col_rename_detail if c in df_d.columns]
            df_d = df_d[cols].rename(columns=col_rename_detail).fillna("")
            df_d.to_excel(writer, sheet_name="Détail dossiers", index=False)
            _style_sheet(writer.sheets["Détail dossiers"], len(df_d))

            # Feuille résumé tractionnaires
            df_resume_tract.to_excel(writer, sheet_name="Résumé tractionnaires", index=False)
            _style_sheet(writer.sheets["Résumé tractionnaires"], len(df_resume_tract))

            # Feuille résumé véhicules
            if df_resume_veh is not None and not df_resume_veh.empty:
                df_resume_veh.to_excel(writer, sheet_name="Résumé véhicules", index=False)
                _style_sheet(writer.sheets["Résumé véhicules"], len(df_resume_veh))

            # Feuille km à vide
            if df_vide is not None and not df_vide.empty:
                vide_rename = {
                    "vehicule": "Véhicule", "tractionnaire": "Tractionnaire",
                    "dossier_depart": "Dossier départ", "dossier_arrivee": "Dossier arrivée",
                    "ville_depart": "Ville départ", "ville_arrivee": "Ville arrivée",
                    "date_depart": "Date", "km_vide": "KM à vide",
                }
                df_v = df_vide[[c for c in vide_rename if c in df_vide.columns]].rename(columns=vide_rename).fillna("")
                df_v.to_excel(writer, sheet_name="KM À Vide Détail", index=False)
                _style_sheet(writer.sheets["KM À Vide Détail"], len(df_v))

    except Exception as e:
        st.error(f"❌ Erreur génération Excel : {e}")
        return b""

    return output.getvalue()


def _style_sheet(ws, nb_rows: int):
    HEADER_FILL = PatternFill("solid", fgColor="1F3864")
    HEADER_FONT = Font(bold=True, color="FFFFFF")
    ALT_FILL    = PatternFill("solid", fgColor="EEF2F7")
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
    for row_idx in range(2, nb_rows + 2):
        if row_idx % 2 == 0:
            for cell in ws[row_idx]:
                cell.fill = ALT_FILL
    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 55)


# ══════════════════════════════════════════════════════════════════
#  INTERFACE STREAMLIT
# ══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Tractionnaires KM + CA", page_icon="🚛", layout="wide")

st.title("🚛 Analyse Tractionnaires — KM PTV + CA")
st.caption("Calcule les km estimés PTV et analyse le CA par tractionnaire / véhicule.")

if not PTV_API_KEY or PTV_API_KEY == "METS_TA_CLE_ICI":
    st.error("⚠️ Clé PTV_API_KEY non configurée.")

st.divider()

file_tract = st.file_uploader("📋 Export tractionnaires (.xlsx)", type=["xlsx"])

if file_tract:
    with st.spinner("📂 Lecture du fichier..."):
        try:
            df = parse_tractionnaires(file_tract)
        except Exception as e:
            st.error(f"❌ Erreur lecture : {e}")
            st.stop()

    if df.empty:
        st.error("❌ Aucun dossier valide détecté dans le fichier.")
        st.stop()

    # ── Période détectée ──────────────────────────────────────
    dates_valides = df["_date_dt"].dropna()
    if not dates_valides.empty:
        d_min, d_max = dates_valides.min(), dates_valides.max()
        if d_min.month == d_max.month and d_min.year == d_max.year:
            periode_label = f"{MOIS_FR[d_min.month]} {d_min.year}"
        else:
            periode_label = f"{d_min.strftime('%d/%m/%Y')} → {d_max.strftime('%d/%m/%Y')}"
    else:
        periode_label = "Période inconnue"

    # ── KPIs globaux ──────────────────────────────────────────
    st.markdown(f"### 📊 Aperçu — {periode_label}")
    ca_total = df["ventes_totales"].sum()
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("📁 Dossiers",       len(df))
    k2.metric("🏢 Tractionnaires", df["tractionnaire"].nunique())
    k3.metric("🚛 Véhicules",      len(_opts(df["vehicule"])))
    k4.metric("💶 CA Total",       f"{ca_total:,.0f} €")
    k5.metric("📈 CA moy/dossier", f"{ca_total / len(df):,.0f} €" if len(df) else "—")

    st.divider()

    # ══════════════════════════════════════════════════════════
    #  FILTRES TABLEAU DÉTAIL
    # ══════════════════════════════════════════════════════════
    st.markdown("### 📋 Tableau détail")

    tract_dispo = _opts(df["tractionnaire"])

    f1, f2 = st.columns(2)
    with f1:
        filtre_tract = st.multiselect(
            "🏢 Tractionnaire :", options=tract_dispo, default=[],
            placeholder="Tous les tractionnaires", key="flt_tract",
        )
    with f2:
        # Cascade : véhicules restreints aux tractionnaires sélectionnés
        _base_veh = df[df["tractionnaire"].isin(filtre_tract)] if filtre_tract else df
        veh_dispo = _opts(_base_veh["vehicule"])
        filtre_veh = st.multiselect(
            "🚛 Véhicule :", options=veh_dispo, default=[],
            placeholder="Tous les camions", key="flt_veh",
        )

    f3, f4 = st.columns(2)
    with f3:
        _base_chf = _base_veh[_base_veh["vehicule"].isin(filtre_veh)] if filtre_veh else _base_veh
        chauff_dispo = _opts(_base_chf["chauffeur"])
        filtre_chauff = st.multiselect(
            "👤 Chauffeur :", options=chauff_dispo, default=[],
            placeholder="Tous les chauffeurs", key="flt_chauff",
        )
    with f4:
        statuts_dispo = _opts(df["statut"])
        filtre_statut = st.multiselect(
            "📄 Statut facturation :", options=statuts_dispo, default=[],
            placeholder="Tous", key="flt_statut",
        )

    df_display = df.copy()
    if filtre_tract:
        df_display = df_display[df_display["tractionnaire"].isin(filtre_tract)]
    if filtre_veh:
        df_display = df_display[df_display["vehicule"].isin(filtre_veh)]
    if filtre_chauff:
        df_display = df_display[df_display["chauffeur"].isin(filtre_chauff)]
    if filtre_statut:
        df_display = df_display[df_display["statut"].isin(filtre_statut)]

    # KPIs filtre
    if filtre_tract or filtre_veh or filtre_chauff or filtre_statut:
        _ca_f = df_display["ventes_totales"].sum()
        _nd_f = len(df_display)
        fk1, fk2, fk3, fk4, fk5 = st.columns(5)
        fk1.metric("📁 Dossiers sélectionnés", _nd_f)
        fk2.metric("🚛 Véhicules",             len(_opts(df_display["vehicule"])))
        fk3.metric("💶 CA sélection",           f"{_ca_f:,.0f} €")
        fk4.metric("📈 CA moy/dossier",         f"{_ca_f/_nd_f:,.0f} €" if _nd_f else "—")
        fk5.metric("% du CA total",             f"{_ca_f/ca_total*100:.1f}%" if ca_total else "—")

    # Tableau
    cols_show = {
        "dossier": "N° Dossier", "tractionnaire": "Tractionnaire",
        "chauffeur": "Chauffeur", "vehicule": "Véhicule", "remorque": "Remorque",
        "client": "Client", "statut": "Statut",
        "date_charg_fmt": "Date chargement", "localite_charg": "Chargement",
        "date_decharg_fmt": "Date déchargement", "localite_decharg": "Déchargement",
        "ventes_totales": "CA (€)",
    }
    df_table = df_display.sort_values("_date_charg_dt", na_position="last")
    df_table = df_table[[c for c in cols_show if c in df_table.columns]].rename(columns=cols_show)
    st.dataframe(df_table, use_container_width=True, height=380)

    st.divider()

    # ── Résumés CA (sans KM) ─────────────────────────────────
    r_tab1, r_tab2 = st.tabs(["🏢 Résumé par tractionnaire", "🚛 Résumé par véhicule"])

    with r_tab1:
        df_res_t = df_display.groupby("tractionnaire", as_index=False).agg(
            Dossiers  = ("dossier",        "count"),
            Véhicules = ("vehicule",        pd.Series.nunique),
            CA_Total  = ("ventes_totales",  "sum"),
        ).round(1)
        df_res_t["CA moy/dossier"] = (df_res_t["CA_Total"] / df_res_t["Dossiers"]).round(0)
        df_res_t = df_res_t.rename(columns={"tractionnaire": "Tractionnaire", "CA_Total": "CA Total (€)"})
        df_res_t = df_res_t.sort_values("CA Total (€)", ascending=False)
        st.dataframe(df_res_t, use_container_width=True)

    with r_tab2:
        df_res_v = df_display[df_display["vehicule"] != ""].groupby("vehicule", as_index=False).agg(
            Dossiers      = ("dossier",        "count"),
            Tractionnaire = ("tractionnaire",   lambda s: ", ".join(sorted({x for x in s if x}))),
            CA_Total      = ("ventes_totales",  "sum"),
        ).round(1)
        df_res_v["CA moy/dossier"] = (df_res_v["CA_Total"] / df_res_v["Dossiers"]).round(0)
        df_res_v = df_res_v.rename(columns={"vehicule": "Véhicule", "CA_Total": "CA Total (€)"})
        df_res_v = df_res_v.sort_values("CA Total (€)", ascending=False)
        st.dataframe(df_res_v, use_container_width=True)

    st.divider()

    # ══════════════════════════════════════════════════════════
    #  CALCUL PTV — sélection tractionnaire + véhicule
    # ══════════════════════════════════════════════════════════
    st.markdown("### 🗺️ Calcul KM via PTV")
    st.caption(
        "⚠️ Le périmètre PTV est indépendant des filtres du tableau : "
        "les km à vide se calculent sur la chronologie **complète** de chaque camion "
        "(un filtre statut fausserait l'enchaînement)."
    )

    p1, p2 = st.columns(2)
    with p1:
        tract_ptv = st.multiselect(
            "🏢 Tractionnaires à calculer :",
            options=tract_dispo, default=[],
            placeholder="Tous les tractionnaires", key="ptv_tract",
        )
    with p2:
        _base_ptv_veh = df[df["tractionnaire"].isin(tract_ptv)] if tract_ptv else df
        veh_ptv_dispo = _opts(_base_ptv_veh["vehicule"])
        veh_ptv = st.multiselect(
            "🚛 Véhicules à calculer :",
            options=veh_ptv_dispo, default=[],
            placeholder="Tous les camions du périmètre", key="ptv_veh",
        )

    c1, c2 = st.columns([1, 2])
    with c1:
        calc_vide = st.toggle("⚡ Calculer les KM à vide", value=True, key="ptv_calc_vide")
    with c2:
        if st.button("✅ Reprendre la sélection du tableau", use_container_width=False):
            st.session_state["ptv_tract"] = list(filtre_tract)
            st.session_state["ptv_veh"]   = list(filtre_veh)
            st.rerun()

    # Construction du périmètre PTV
    df_ptv_scope = df.copy()
    if tract_ptv:
        df_ptv_scope = df_ptv_scope[df_ptv_scope["tractionnaire"].isin(tract_ptv)]
    if veh_ptv:
        df_ptv_scope = df_ptv_scope[df_ptv_scope["vehicule"].isin(veh_ptv)]

    selection_faite = bool(tract_ptv or veh_ptv)
    if not selection_faite:
        df_ptv_scope = pd.DataFrame(columns=df.columns)

    if selection_faite:
        nb_dos  = len(df_ptv_scope)
        nb_veh  = len(_opts(df_ptv_scope["vehicule"]))
        # Estimation grossière du nombre d'appels PTV
        nb_pts  = len(set(
            list(zip(df_ptv_scope["localite_charg"], df_ptv_scope["cp_charg"], df_ptv_scope["pays_charg"])) +
            list(zip(df_ptv_scope["localite_decharg"], df_ptv_scope["cp_decharg"], df_ptv_scope["pays_decharg"]))
        ))
        nb_legs_vide = max(nb_dos - nb_veh, 0) if calc_vide else 0
        st.info(
            f"ℹ️ **{nb_dos} dossiers** · **{nb_veh} camion(s)** · "
            f"~{nb_pts} géocodages + {nb_dos} routes chargées"
            + (f" + ~{nb_legs_vide} routes à vide" if calc_vide else " (km à vide désactivés)")
        )

    btn_ptv = st.button("🚀 Lancer le calcul PTV", disabled=(not selection_faite or df_ptv_scope.empty),
                        type="primary")

    if btn_ptv and selection_faite and not df_ptv_scope.empty:
        progress_bar = st.progress(0.0)
        status_text  = st.empty()

        def _progress(msg, pct=None):
            status_text.text(msg)
            if pct is not None:
                progress_bar.progress(min(max(pct, 0.0), 1.0))

        try:
            df_ptv_result, df_vide_result = compute_km(
                df_ptv_scope, progress_cb=_progress, calc_vide=calc_vide
            )
            st.session_state["df_ptv_result"]  = df_ptv_result
            st.session_state["df_vide_result"] = df_vide_result
            progress_bar.progress(1.0)
            status_text.success("✅ Calcul PTV terminé !")
        except Exception as e:
            st.error(f"❌ Erreur calcul PTV : {e}")

    # ══════════════════════════════════════════════════════════
    #  RESULTATS PTV
    # ══════════════════════════════════════════════════════════
    if "df_ptv_result" in st.session_state:
        df_r      = st.session_state["df_ptv_result"]
        df_vide_r = st.session_state.get("df_vide_result", pd.DataFrame())

        st.divider()
        st.markdown("### 📈 Résultats KM")

        # ── Filtres sur les résultats ─────────────────────────
        rf1, rf2, rf3 = st.columns([2, 2, 1])
        with rf1:
            res_tract_dispo = _opts(df_r["tractionnaire"])
            res_f_tract = st.multiselect(
                "🏢 Filtrer résultats — Tractionnaire :", options=res_tract_dispo,
                default=[], placeholder="Tous", key="res_flt_tract",
            )
        with rf2:
            _base_res = df_r[df_r["tractionnaire"].isin(res_f_tract)] if res_f_tract else df_r
            res_veh_dispo = _opts(_base_res["vehicule"])
            res_f_veh = st.multiselect(
                "🚛 Filtrer résultats — Véhicule :", options=res_veh_dispo,
                default=[], placeholder="Tous", key="res_flt_veh",
            )
        with rf3:
            st.write("")
            if st.button("🗑️ Effacer résultats"):
                st.session_state.pop("df_ptv_result", None)
                st.session_state.pop("df_vide_result", None)
                st.rerun()

        df_rf = df_r.copy()
        if res_f_tract:
            df_rf = df_rf[df_rf["tractionnaire"].isin(res_f_tract)]
        if res_f_veh:
            df_rf = df_rf[df_rf["vehicule"].isin(res_f_veh)]

        df_vide_rf = df_vide_r.copy()
        if not df_vide_rf.empty:
            if res_f_tract:
                df_vide_rf = df_vide_rf[df_vide_rf["tractionnaire"].isin(res_f_tract)]
            if res_f_veh:
                df_vide_rf = df_vide_rf[df_vide_rf["vehicule"].isin(res_f_veh)]

        km_charges  = df_rf["km_ptv"].sum()
        km_vide_sum = df_rf["km_vide"].sum()
        km_complet  = km_charges + km_vide_sum
        ca_sum      = df_rf["ventes_totales"].sum()
        rent        = ca_sum / km_complet if km_complet > 0 else 0
        pct_vide    = km_vide_sum / km_complet * 100 if km_complet > 0 else 0
        dos_ok      = int(df_rf["km_ptv"].notna().sum())

        rk1, rk2, rk3, rk4, rk5, rk6 = st.columns(6)
        rk1.metric("📁 Dossiers calculés", f"{dos_ok} / {len(df_rf)}")
        rk2.metric("📏 KM Chargés",         f"{km_charges:,.0f} km")
        rk3.metric("⚡ KM À Vide",           f"{km_vide_sum:,.0f} km")
        rk4.metric("🔄 KM Complet",          f"{km_complet:,.0f} km")
        rk5.metric("% À Vide",               f"{pct_vide:.1f}%")
        rk6.metric("📈 Rentabilité",         f"{rent:.2f} €/km")

        tab1, tab2, tab3, tab4 = st.tabs([
            "📋 Détail dossiers", "🏢 Résumé tractionnaires",
            "🚛 Résumé véhicules", "⚡ Détail KM à vide",
        ])

        with tab1:
            df_detail_show = df_rf.copy()
            df_detail_show["rentabilite"] = (
                df_detail_show["ventes_totales"] / df_detail_show["km_total_complet"].replace(0, np.nan)
            ).round(2)
            # Tri chronologique par camion : reflète l'enchaînement réel des tournées
            df_detail_show = df_detail_show.sort_values(
                ["vehicule", "_date_charg_dt"], na_position="last"
            )
            cols_det = {
                "dossier": "N° Dossier", "tractionnaire": "Tractionnaire",
                "chauffeur": "Chauffeur", "vehicule": "Véhicule", "client": "Client",
                "date_charg_fmt": "Date chargement", "localite_charg": "Chargement",
                "date_decharg_fmt": "Date déchargement", "localite_decharg": "Déchargement",
                "ventes_totales": "CA (€)", "km_ptv": "KM Chargé",
                "km_vide": "KM À Vide", "km_total_complet": "KM Complet", "rentabilite": "€/km",
            }
            df_det_tab = df_detail_show[[c for c in cols_det if c in df_detail_show.columns]].rename(columns=cols_det)
            st.dataframe(df_det_tab, use_container_width=True, height=400)

        with tab2:
            df_res_ptv_t = build_resume(df_rf, "tractionnaire", "Tractionnaire")
            st.dataframe(df_res_ptv_t, use_container_width=True)

        with tab3:
            df_veh_scope = df_rf[df_rf["vehicule"] != ""]
            if not df_veh_scope.empty:
                df_res_ptv_v = build_resume(df_veh_scope, "vehicule", "Véhicule")
                st.dataframe(df_res_ptv_v, use_container_width=True)
            else:
                df_res_ptv_v = pd.DataFrame()
                st.info("Aucun véhicule renseigné sur les dossiers calculés.")

        with tab4:
            if not df_vide_rf.empty:
                st.dataframe(
                    df_vide_rf.rename(columns={
                        "vehicule": "Véhicule", "tractionnaire": "Tractionnaire",
                        "dossier_depart": "Dossier départ", "dossier_arrivee": "Dossier arrivée",
                        "ville_depart": "Ville départ", "ville_arrivee": "Ville arrivée",
                        "date_depart": "Date", "km_vide": "KM à vide",
                    }),
                    use_container_width=True,
                )
            else:
                st.info("Aucun km à vide calculé.")

        # ── Export ────────────────────────────────────────────
        st.divider()
        excel_bytes = export_excel(df_rf, df_res_ptv_t, df_res_ptv_v, df_vide_rf)
        if excel_bytes:
            st.download_button(
                label="📥 Télécharger le rapport Excel",
                data=excel_bytes,
                file_name="Rapport_Tractionnaires_KM.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )

else:
    st.markdown("""
    #### Comment utiliser cet outil

    1. **Chargez l'export tractionnaires** (.xlsx)
    2. Consultez l'**aperçu global** et les résumés CA (tractionnaire / véhicule)
    3. Filtrez le tableau par **tractionnaire, véhicule, chauffeur ou statut**
    4. Dans la section PTV, sélectionnez les **tractionnaires et/ou camions** à calculer,
       puis lancez le calcul
    5. Filtrez les résultats et **téléchargez le rapport Excel**

    > ⚠️ Les KM à vide s'appuient sur la chronologie complète de chaque camion.
    > Ne filtre pas sur le statut de facturation avant un calcul PTV : l'enchaînement
    > déchargement → chargement suivant serait faussé.

    > ⚙️ La clé PTV doit être configurée dans `.env` (`PTV_API_KEY`).
    """)
