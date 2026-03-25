import streamlit as st
import os
import tempfile
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.km_calcul.run_km import run_calcul_km

st.set_page_config(page_title="Calcul KM PTV", page_icon="🗺️", layout="wide")

st.title("🗺️ Calcul de distances PTV")
st.markdown("---")

# === Upload ===
uploaded_file = st.file_uploader(
    "📂 Dépose ton fichier Excel",
    type=["xlsx"],
    help="Le fichier doit contenir les colonnes Origine / Destination"
)

calculer_peage = st.checkbox("💶 Calculer les frais de péage", value=False)

if uploaded_file and st.button("🚀 Lancer le calcul", type="primary"):

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    with st.spinner("⏳ Calcul des distances en cours via PTV..."):
        result = run_calcul_km(tmp_path, calculer_peage=calculer_peage)

    if result["success"]:
        st.success("🎉 Calcul terminé !")

        # ── Lire le fichier EN BYTES dans session_state ──
        with open(result["output_path"], "rb") as f:
            st.session_state["km_result_bytes"] = f.read()
            st.session_state["km_result_name"]  = uploaded_file.name.replace(".xlsx", "_KM.xlsx")

        # Nettoyage des 2 fichiers temp
        for p in [tmp_path, result["output_path"]]:
            try:
                os.unlink(p)
            except:
                pass
    else:
        st.error(f"❌ Erreur : {result['error']}")
        try:
            os.unlink(tmp_path)
        except:
            pass

# ── Bouton téléchargement PERSISTANT (hors du bloc button) ──
if "km_result_bytes" in st.session_state:
    st.download_button(
        label     = "📥 Télécharger le fichier KM",
        data      = st.session_state["km_result_bytes"],
        file_name = st.session_state["km_result_name"],
        mime      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
