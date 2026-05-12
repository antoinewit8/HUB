"""
Page Streamlit — Enrichissement des codes postaux manquants
Détecte les lignes sans CP destination (et optionnellement origine),
interroge l'API PTV pour récupérer le bon CP, et réécrit le fichier Excel.
"""

import streamlit as st
import os
import sys
import tempfile
import io
import time
import requests
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

st.set_page_config(page_title="Enrichissement CP", page_icon="📮", layout="wide")

# ─────────────────────────────────────────────────────────────────────────────
# STYLE CB GROUPE
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0d1b2a; }
[data-testid="stSidebar"] { background: #0d1b2a; }
h1, h2, h3, .stMarkdown p { color: #e8eaf6; }
.stat-card {
    background: #1a2a3a; border: 1px solid #2F5496;
    border-radius: 10px; padding: 18px 24px; text-align: center;
    margin: 6px;
}
.stat-card .val { font-size: 2rem; font-weight: 700; color: #4fc3f7; }
.stat-card .lbl { font-size: 0.85rem; color: #90a4ae; margin-top: 4px; }
.stButton > button {
    background: #2F5496; color: white; border: none;
    border-radius: 8px; padding: 10px 28px; font-weight: 600;
}
.stButton > button:hover { background: #1a3a6e; }
</style>
""", unsafe_allow_html=True)

st.title("📮 Enrichissement des Codes Postaux")
st.markdown("Détecte les destinations (et origines) sans code postal et les complète via l'API PTV.")
st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────
PTV_API_KEY = os.environ.get("PTV_API_KEY", "")
GEOCODE_URL = "https://api.myptv.com/geocoding/v1"

PAYS_MAP = {
    "FR": "France", "BE": "Belgium", "DE": "Germany", "NL": "Netherlands",
    "LU": "Luxembourg", "IT": "Italy", "ES": "Spain", "PT": "Portugal",
    "GB": "United Kingdom", "CH": "Switzerland", "AT": "Austria",
    "PL": "Poland", "CZ": "Czech Republic", "HU": "Hungary",
    "RO": "Romania", "BG": "Bulgaria", "SK": "Slovakia", "SI": "Slovenia",
    "HR": "Croatia", "DK": "Denmark", "SE": "Sweden", "NO": "Norway",
    "FI": "Finland", "IE": "Ireland", "GR": "Greece",
    "F": "France", "B": "Belgium", "D": "Germany", "I": "Italy",
    "E": "Spain", "L": "Luxembourg", "A": "Austria", "P": "Portugal",
}
# Inverse : nom pays → ISO
PAYS_TO_ISO = {v.lower(): k for k, v in PAYS_MAP.items() if len(k) == 2}
PAYS_TO_ISO.update({
    "france": "FR", "belgique": "BE", "allemagne": "DE", "pays-bas": "NL",
    "luxembourg": "LU", "italie": "IT", "espagne": "ES", "portugal": "PT",
    "suisse": "CH", "autriche": "AT", "pologne": "PL", "tchéquie": "CZ",
    "hongrie": "HU", "roumanie": "RO", "bulgarie": "BG", "croatie": "HR",
    "danemark": "DK", "suède": "SE", "norvège": "NO", "finlande": "FI",
    "irlande": "IE", "grèce": "GR",
})

CP_LENGTHS = {
    "FR": 5, "F": 5, "BE": 4, "B": 4, "DE": 5, "D": 5,
    "IT": 5, "I": 5, "ES": 5, "E": 5, "PL": 5, "CZ": 5,
    "HR": 5, "SK": 5, "GR": 5, "SE": 5, "FI": 5, "NL": 4,
    "AT": 4, "A": 4, "CH": 4, "HU": 4, "DK": 4, "SI": 4,
    "NO": 4, "LU": 4, "L": 4, "PT": 7, "P": 7, "RO": 6,
}

ORIG_PAYS_KW = ["pays", "country", "country of origin", "orig cntry", "pays départ", "pays depart", "pays origine"]
ORIG_CP_KW   = ["code postal", "cp", "postal code", "postal code origin", "orig reg", "cp départ", "cp depart", "code postal origine"]
ORIG_VILLE_KW= ["ville", "city", "city of origin", "orig zone txt", "localité", "localite", "origin", "depart", "départ", "origine", "ville départ", "ville depart"]
DEST_PAYS_KW = ["pays", "country", "country of destination", "dest cntry", "pays destination", "dest pays"]
DEST_CP_KW   = ["département", "departement", "code postal", "cp", "postal code", "postal code destination", "dest reg", "cp destination", "cp dech", "cp déchargement"]
DEST_VILLE_KW= ["ville2", "ville", "city", "city of destination", "dest zone txt", "destination", "ville destination", "ville dest"]
ORIGIN_GROUP_KW = ["depart", "départ", "origin", "origine", "chargement", "loading"]
DEST_GROUP_KW   = ["destination", "dest", "arrivée", "arrivee", "livraison", "delivery", "unloading"]

MAX_RETRIES = 3
RETRY_DELAY = 1.5

# ─────────────────────────────────────────────────────────────────────────────
# UTILITAIRES
# ─────────────────────────────────────────────────────────────────────────────
import re
import unicodedata

def normalize(val):
    if val is None:
        return ""
    val = str(val).strip().lower()
    val = unicodedata.normalize("NFD", val)
    val = "".join(c for c in val if unicodedata.category(c) != "Mn")
    return re.sub(r'\s+', ' ', val).strip()


def pays_to_iso(pays_str: str) -> str:
    if not pays_str:
        return "FR"
    p = pays_str.strip().upper()
    if p in PAYS_MAP:
        return p
    iso = PAYS_TO_ISO.get(pays_str.strip().lower(), "")
    return iso or "FR"


def pad_cp(cp: str, iso: str) -> str:
    if not cp:
        return ""
    target = CP_LENGTHS.get(iso, 5)
    if target == 0:
        return cp
    cp = cp.zfill(target)
    return cp


# ─────────────────────────────────────────────────────────────────────────────
# DÉTECTION COLONNES (réutilise la même logique qu'excel_handler_km)
# ─────────────────────────────────────────────────────────────────────────────

def detect_header_row(ws, max_scan=15):
    all_kw = set()
    for lst in [ORIG_PAYS_KW, ORIG_CP_KW, ORIG_VILLE_KW, DEST_PAYS_KW, DEST_CP_KW, DEST_VILLE_KW]:
        all_kw.update(lst)
    best_row, best_score = None, 0
    for r in range(1, min(max_scan + 1, ws.max_row + 1)):
        score = sum(1 for c in range(1, ws.max_column + 1) if normalize(ws.cell(r, c).value) in all_kw)
        if score > best_score:
            best_score, best_row = score, r
    return best_row if best_score >= 2 else None


def detect_groups(ws, header_row):
    if header_row <= 1:
        return {}
    group_row = header_row - 1
    merge_map = {}
    for mr in ws.merged_cells.ranges:
        if mr.min_row <= group_row <= mr.max_row:
            val = ws.cell(mr.min_row, mr.min_col).value
            for c in range(mr.min_col, mr.max_col + 1):
                merge_map[c] = val
    groups, current = {}, None
    for col in range(1, ws.max_column + 1):
        val = normalize(merge_map.get(col, ws.cell(group_row, col).value))
        if any(k in val for k in ORIGIN_GROUP_KW):
            current = "origin"
        elif any(k in val for k in DEST_GROUP_KW):
            current = "dest"
        elif val:
            current = None
        if current:
            groups[col] = current
    return groups


def map_columns(ws):
    header_row = detect_header_row(ws)
    if not header_row:
        return None, None, None
    groups = detect_groups(ws, header_row)
    headers = {c: normalize(ws.cell(header_row, c).value)
               for c in range(1, ws.max_column + 1)
               if ws.cell(header_row, c).value}

    ROLES = {
        "orig_pays":  (ORIG_PAYS_KW,  "origin"),
        "orig_cp":    (ORIG_CP_KW,    "origin"),
        "orig_ville": (ORIG_VILLE_KW, "origin"),
        "dest_pays":  (DEST_PAYS_KW,  "dest"),
        "dest_cp":    (DEST_CP_KW,    "dest"),
        "dest_ville": (DEST_VILLE_KW, "dest"),
    }
    mapping, used = {}, set()
    for role, (kws, side) in ROLES.items():
        # Passe 1 : avec groupe
        for col, hval in headers.items():
            if col in used:
                continue
            if groups.get(col) == side and hval in kws:
                mapping[role] = col
                used.add(col)
                break
        # Passe 2 : sans groupe
        if role not in mapping:
            for col, hval in headers.items():
                if col in used:
                    continue
                if hval in kws:
                    mapping[role] = col
                    used.add(col)
                    break

    return mapping, header_row, header_row + 1


# ─────────────────────────────────────────────────────────────────────────────
# GÉOCODAGE PTV → CP
# ─────────────────────────────────────────────────────────────────────────────

def fetch_cp_from_ptv(ville: str, iso: str) -> str | None:
    """
    Interroge l'API PTV geocoding pour trouver le code postal
    d'une ville. Retourne le CP en string ou None.
    """
    if not PTV_API_KEY or PTV_API_KEY == "":
        return None

    headers = {"apiKey": PTV_API_KEY}
    params  = {"searchText": ville, "countryFilter": iso}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(
                f"{GEOCODE_URL}/locations/by-text",
                headers=headers,
                params=params,
                timeout=10,
            )
            if r.status_code == 429:
                time.sleep(RETRY_DELAY * attempt)
                continue
            if r.status_code in (400, 404):
                return None
            r.raise_for_status()
            data = r.json()
            locs = data.get("locations", [])
            if not locs:
                return None

            ville_norm = normalize(ville)
            # Cherche le meilleur match : ville trouvée + pas une rue
            for loc in locs:
                addr = loc.get("address", {})
                city_norm = normalize(addr.get("city", ""))
                cp        = addr.get("postalCode", "")
                street    = addr.get("street", "")

                if not cp:
                    continue
                city_match = (ville_norm in city_norm or city_norm in ville_norm)
                not_street = ville_norm not in normalize(street)
                if city_match and not_street:
                    return pad_cp(cp, iso)

            # Fallback : premier résultat avec CP
            for loc in locs:
                cp = loc.get("address", {}).get("postalCode", "")
                if cp:
                    return pad_cp(cp, iso)
            return None

        except Exception:
            time.sleep(RETRY_DELAY)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSE DU FICHIER
# ─────────────────────────────────────────────────────────────────────────────

def analyser_fichier(wb):
    """
    Parcourt toutes les feuilles et retourne la liste des lignes
    sans code postal destination (et/ou origine).
    """
    resultats = []  # {sheet, row, mapping, ville_dest, pays_dest, cp_col, iso}

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        mapping, header_row, data_start = map_columns(ws)
        if not mapping:
            continue
        if "dest_ville" not in mapping:
            continue

        iso_col   = mapping.get("dest_pays")
        cp_col    = mapping.get("dest_cp")
        ville_col = mapping["dest_ville"]

        for row in range(data_start, ws.max_row + 1):
            ville = str(ws.cell(row, ville_col).value or "").strip()
            cp    = str(ws.cell(row, cp_col).value    or "").strip() if cp_col else ""
            pays  = str(ws.cell(row, iso_col).value   or "").strip() if iso_col else "France"

            if not ville:
                continue
            if cp:  # CP déjà présent → skip
                continue

            iso = pays_to_iso(pays)
            resultats.append({
                "sheet":    sheet_name,
                "row":      row,
                "ville":    ville,
                "pays":     pays,
                "iso":      iso,
                "cp_col":   cp_col,
                "mapping":  mapping,
                "header_row": header_row,
            })

    return resultats


# ─────────────────────────────────────────────────────────────────────────────
# UI PRINCIPALE
# ─────────────────────────────────────────────────────────────────────────────

uploaded = st.file_uploader("📂 Dépose ton fichier Excel", type=["xlsx"])

col1, col2 = st.columns(2)
with col1:
    creer_colonne = st.checkbox("➕ Créer la colonne CP si absente", value=True,
        help="Si la feuille n'a pas de colonne CP destination, on en crée une à droite de la colonne ville.")
with col2:
    enrichir_origine = st.checkbox("🔄 Enrichir aussi les origines sans CP", value=False)

if uploaded:
    raw_bytes = uploaded.read()
    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes))

    # ── Analyse ──
    lignes_manquantes = analyser_fichier(wb)

    # Stats
    total_manquant = len(lignes_manquantes)
    sheets_touch   = len(set(r["sheet"] for r in lignes_manquantes))
    villes_uniques = len(set((r["ville"], r["iso"]) for r in lignes_manquantes))

    st.markdown("### 📊 Analyse du fichier")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="stat-card"><div class="val">{total_manquant}</div><div class="lbl">Lignes sans CP dest.</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="stat-card"><div class="val">{villes_uniques}</div><div class="lbl">Villes uniques à géocoder</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="stat-card"><div class="val">{sheets_touch}</div><div class="lbl">Feuilles concernées</div></div>', unsafe_allow_html=True)

    if total_manquant == 0:
        st.success("✅ Toutes les destinations ont déjà un code postal !")
    else:
        # Aperçu des lignes manquantes
        with st.expander(f"👁️ Voir les {total_manquant} lignes sans CP destination", expanded=False):
            preview = []
            for r in lignes_manquantes[:100]:
                preview.append({
                    "Feuille": r["sheet"],
                    "Ligne": r["row"],
                    "Ville destination": r["ville"],
                    "Pays": r["pays"],
                    "ISO": r["iso"],
                })
            import pandas as pd
            st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)
            if total_manquant > 100:
                st.caption(f"... et {total_manquant - 100} autres lignes non affichées.")

        if not PTV_API_KEY:
            st.error("❌ Clé PTV_API_KEY non configurée. L'enrichissement automatique est impossible.")
            st.info("💡 Tu peux quand même télécharger l'aperçu pour identifier les villes à corriger manuellement.")
        else:
            st.markdown("---")
            if st.button("🚀 Lancer l'enrichissement", type="primary"):

                # Dédoublonner les (ville, iso) pour minimiser les appels API
                cache_cp: dict[tuple, str] = {}  # (ville_norm, iso) → cp
                unique_pairs = list({(r["ville"], r["iso"]) for r in lignes_manquantes})

                progress = st.progress(0)
                status   = st.empty()
                log_area = st.empty()
                logs = []

                total_unique = len(unique_pairs)
                trouvés, non_trouvés = 0, 0

                for i, (ville, iso) in enumerate(unique_pairs):
                    pct = (i + 1) / total_unique
                    progress.progress(pct)
                    status.markdown(f"**🔍 Géocodage {i+1}/{total_unique}** — {ville} ({iso})")

                    key = (normalize(ville), iso)
                    if key in cache_cp:
                        trouvés += 1
                        continue

                    cp = fetch_cp_from_ptv(ville, iso)
                    cache_cp[key] = cp or ""

                    if cp:
                        trouvés += 1
                        logs.append(f"✅ {ville} ({iso}) → **{cp}**")
                    else:
                        non_trouvés += 1
                        logs.append(f"⚠️ {ville} ({iso}) → non trouvé")

                    if logs:
                        log_area.markdown("\n".join(logs[-15:]))

                    time.sleep(0.15)  # Anti rate-limit

                status.markdown(f"**✅ Géocodage terminé** — {trouvés} trouvés, {non_trouvés} non trouvés")

                # ── Écriture dans le workbook ──
                # On recharge pour éviter les problèmes d'état
                wb2 = openpyxl.load_workbook(io.BytesIO(raw_bytes))

                cp_font   = Font(color="1F6B2E", bold=True)
                cp_fill   = PatternFill("solid", fgColor="E8F5E9")
                miss_font = Font(color="B71C1C")
                miss_fill = PatternFill("solid", fgColor="FFEBEE")

                écrites, manquées = 0, 0

                for r_info in lignes_manquantes:
                    ws2      = wb2[r_info["sheet"]]
                    mapping  = r_info["mapping"]
                    row      = r_info["row"]
                    ville    = r_info["ville"]
                    iso      = r_info["iso"]
                    cp_col   = r_info["cp_col"]
                    key      = (normalize(ville), iso)
                    cp_found = cache_cp.get(key, "")

                    # Si pas de colonne CP et option activée → créer à droite de ville
                    if not cp_col and creer_colonne:
                        ville_col = mapping["dest_ville"]
                        # Cherche si colonne CP a déjà été créée pour cette feuille
                        hdr_row   = r_info["header_row"]
                        # Regarde la colonne suivante
                        next_col = ville_col + 1
                        hdr_val  = normalize(ws2.cell(hdr_row, next_col).value)
                        if hdr_val not in ("cp", "code postal", "postal code"):
                            # Insérer header
                            ws2.insert_cols(next_col)
                            ws2.cell(hdr_row, next_col).value = "CP Destination"
                            ws2.cell(hdr_row, next_col).font  = Font(bold=True, color="FFFFFF")
                            ws2.cell(hdr_row, next_col).fill  = PatternFill("solid", fgColor="2F5496")
                            ws2.cell(hdr_row, next_col).alignment = Alignment(horizontal="center")
                        cp_col = next_col
                        # Mettre à jour le mapping pour les autres lignes de cette feuille
                        for other in lignes_manquantes:
                            if other["sheet"] == r_info["sheet"] and other["cp_col"] is None:
                                other["cp_col"] = cp_col

                    if not cp_col:
                        continue

                    cell = ws2.cell(row, cp_col)
                    if cp_found:
                        cell.value = cp_found
                        cell.font  = cp_font
                        cell.fill  = cp_fill
                        écrites += 1
                    else:
                        cell.value = "?"
                        cell.font  = miss_font
                        cell.fill  = miss_fill
                        manquées += 1

                # ── Export ──
                out_buf = io.BytesIO()
                wb2.save(out_buf)
                out_buf.seek(0)

                st.markdown("---")
                st.success(f"✅ **{écrites}** codes postaux écrits — ⚠️ **{manquées}** non trouvés (marqués `?`)")

                fname = uploaded.name.replace(".xlsx", "_CP_enrichi.xlsx")
                st.download_button(
                    label="⬇️ Télécharger le fichier enrichi",
                    data=out_buf,
                    file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

                if manquées > 0:
                    st.info("💡 Les cellules marquées `?` (en rouge) sont les villes non trouvées. "
                            "Tu peux les compléter manuellement ou les ajouter dans `GPS_FIXES`.")
else:
    st.info("📂 Dépose un fichier Excel pour démarrer l'analyse.")
