# pages/1_🚛_Analyse_TX_FLEX.py
import streamlit as st
import pandas as pd
import io
import subprocess
import tempfile
import shutil
import os
 
# ─── Import depuis le module txflex ────────────────────
from tools.txflex.analyzer import (
    compute_empty_km,
    compute_total_km,
    detect_friday_anomalies
)
 
# ─── Config page ───────────────────────────────────────
st.set_page_config(
    page_title="Analyse TX-FLEX",
    page_icon="🚛",
    layout="wide"
)
 
 
# ─── Détection du vrai format par magic bytes ───────────
def _is_real_xls(data: bytes) -> bool:
    """
    Vérifie si les données sont un vrai .xls (format BIFF/OLE2).
    Magic bytes OLE2 : D0 CF 11 E0 A1 B1 1A E1
    Les .xlsx sont des ZIP et commencent par 50 4B (PK).
    """
    return data[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
 
 
def _convert_xls_bytes_via_libreoffice(data: bytes, filename: str) -> pd.DataFrame:
    """Écrit les bytes sur disque, convertit via LibreOffice, lit le .xlsx produit."""
    libreoffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not libreoffice:
        raise RuntimeError("LibreOffice est introuvable sur ce serveur.")
 
    tmp_dir = tempfile.mkdtemp(prefix="txflex_")
    try:
        # Forcer l'extension .xls pour que LibreOffice reconnaisse le format
        base     = os.path.splitext(filename)[0]
        xls_tmp  = os.path.join(tmp_dir, base + ".xls")
        with open(xls_tmp, "wb") as f:
            f.write(data)
 
        result = subprocess.run(
            [libreoffice, "--headless", "--convert-to", "xlsx",
             xls_tmp, "--outdir", tmp_dir],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Échec conversion LibreOffice : "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
 
        xlsx_path = os.path.join(tmp_dir, base + ".xlsx")
        if not os.path.exists(xlsx_path):
            raise RuntimeError(f"Fichier converti introuvable : {xlsx_path}")
 
        return pd.read_excel(xlsx_path, engine="openpyxl")
 
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
 
 
def read_uploaded_file(file) -> pd.DataFrame:
    """
    Lit un fichier uploadé Streamlit.
    Détecte le VRAI format par magic bytes — ignore l'extension déclarée.
    """
    name = file.name
    ext  = os.path.splitext(name)[1].lower()
 
    if ext == ".csv":
        return pd.read_csv(file)
 
    # Lire les bytes une seule fois
    data = file.read()
 
    if _is_real_xls(data):
        # Vrai format OLE2/BIFF (.xls) — même si renommé en .xlsx
        return _convert_xls_bytes_via_libreoffice(data, name)
    else:
        # Format ZIP → vrai .xlsx, lecture directe openpyxl
        return pd.read_excel(io.BytesIO(data), engine="openpyxl")
 
 
# ─── Header ────────────────────────────────────────────
st.title("🚛 Analyse de Flotte TX-FLEX")
st.caption("Analysez vos fichiers TX-FLEX : KM à vide, alertes vendredis, rapport Excel")
st.divider()
 
# ─── Upload fichiers ───────────────────────────────────
uploaded_files = st.file_uploader(
    "📂 Chargez vos fichiers TX-FLEX (Excel ou CSV)",
    type=["csv", "xls", "xlsx"],
    accept_multiple_files=True,
    help="Sélectionnez plusieurs fichiers d'un coup"
)
 
if not uploaded_files:
    st.info("👆 Chargez au moins un fichier pour démarrer l'analyse")
    st.stop()
 
# ─── Bouton analyse ────────────────────────────────────
if not st.button("🚀 Lancer l'Analyse", type="primary"):
    st.stop()
 
# ─── Traitement ────────────────────────────────────────
resultats_globaux = []
details_trajets   = []
alertes_vendredi  = []
 
progress = st.progress(0, text="Initialisation...")
 
for i, file in enumerate(uploaded_files):
    camion_nom = file.name.split(".")[0].upper()
    progress.progress(
        int((i / len(uploaded_files)) * 100),
        text=f"Analyse de {camion_nom}..."
    )
 
    try:
        df = read_uploaded_file(file)
 
        trajets_vides  = compute_empty_km(df)
        total_vide     = sum(t["km_vide"] for t in trajets_vides)
 
        stats_totales  = compute_total_km(df)
        total_parcouru = stats_totales["total"]
        pct_vide       = (total_vide / total_parcouru * 100) if total_parcouru > 0 else 0
 
        resultats_globaux.append({
            "Camion"              : camion_nom,
            "KM Totaux Parcourus" : total_parcouru,
            "KM Total à Vide"     : total_vide,
            "% à Vide"            : round(pct_vide, 2)
        })
 
        for trajet in trajets_vides:
            trajet["Camion"] = camion_nom
            details_trajets.append(trajet)
 
        for anomalie in detect_friday_anomalies(df):
            if anomalie["alerte"]:
                alertes_vendredi.append({
                    "Camion"      : camion_nom,
                    "Date"        : anomalie["date"],
                    "Heure Fin"   : anomalie["heure_fin"],
                    "KM Totaux"   : anomalie["km_parcourus"],
                    "KM à Vide"   : anomalie["km_vide"],
                    "Nb Activités": anomalie["nb_activites"],
                    "Alerte"      : " + ".join(anomalie["raisons"]),
                    "Villes"      : " -> ".join(anomalie["villes_visitees"])
                })
 
    except Exception as e:
        st.error(f"❌ Erreur sur **{file.name}** : {e}")
 
progress.progress(100, text="✅ Analyse terminée")
 
# ─── DataFrames ────────────────────────────────────────
df_resume   = pd.DataFrame(resultats_globaux)
df_vendredi = pd.DataFrame(alertes_vendredi)
df_details  = pd.DataFrame(details_trajets)
 
if not df_details.empty:
    df_details = df_details[[
        "Camion", "date_depart", "ville_depart",
        "date_arrivee", "ville_arrivee", "km_vide"
    ]]
 
st.success("✅ Analyse terminée avec succès !")
st.divider()
 
# ─── KPI Cards ─────────────────────────────────────────
if not df_resume.empty:
    col1, col2, col3 = st.columns(3)
    col1.metric("🚛 Camions analysés",   len(df_resume))
    col2.metric("📦 KM Totaux",          f"{int(df_resume['KM Totaux Parcourus'].sum()):,}")
    col3.metric("⚠️ KM à Vide",          f"{int(df_resume['KM Total à Vide'].sum()):,}")
 
st.divider()
 
# ─── Tabs résultats ────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "📊 Résumé par camion",
    "⚠️ Alertes Vendredis",
    "🛣️ Détails KM à Vide"
])
 
with tab1:
    st.dataframe(df_resume, use_container_width=True)
 
with tab2:
    if not df_vendredi.empty:
        st.dataframe(df_vendredi, use_container_width=True)
    else:
        st.info("✅ Aucune anomalie détectée les vendredis")
 
with tab3:
    if not df_details.empty:
        st.dataframe(df_details, use_container_width=True)
    else:
        st.info("Aucun trajet à vide détecté")
 
st.divider()
 
# ─── Export Excel ──────────────────────────────────────
output = io.BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    df_resume.to_excel(writer,   sheet_name="Résumé",              index=False)
    if not df_vendredi.empty:
        df_vendredi.to_excel(writer, sheet_name="Vendredis",       index=False)
    if not df_details.empty:
        df_details.to_excel(writer,  sheet_name="Détails KM Vide", index=False)
 
st.download_button(
    label     = "📥 Télécharger le rapport Excel",
    data      = output.getvalue(),
    file_name = "Resultats_Flotte_TXFLEX.xlsx",
    mime      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
