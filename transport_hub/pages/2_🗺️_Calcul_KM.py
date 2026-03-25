import streamlit as st
import os
import tempfile
import sys
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.km_calcul.run_km import run_calcul_km

st.set_page_config(page_title="Calcul KM PTV", page_icon="🗺️", layout="wide")
st.title("🗺️ Calcul de distances PTV")
st.markdown("---")

# === Init session state ===
if "km_running" not in st.session_state:
    st.session_state["km_running"] = False
if "km_result_bytes" not in st.session_state:
    st.session_state["km_result_bytes"] = None
if "km_result_name" not in st.session_state:
    st.session_state["km_result_name"] = None
if "km_error" not in st.session_state:
    st.session_state["km_error"] = None

uploaded_file = st.file_uploader("📂 Dépose ton fichier Excel", type=["xlsx"])
calculer_peage = st.checkbox("💶 Calculer les frais de péage", value=False)

# === Lancer le calcul ===
if uploaded_file and st.button("🚀 Lancer le calcul", type="primary"):
    # Reset
    st.session_state["km_result_bytes"] = None
    st.session_state["km_error"] = None

    # Sauvegarder le fichier uploadé
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    try:
        with st.spinner("⏳ Calcul en cours via PTV..."):
            result = run_calcul_km(tmp_path, calculer_peage=calculer_peage)

        if result["success"]:
            with open(result["output_path"], "rb") as f:
                st.session_state["km_result_bytes"] = f.read()
            st.session_state["km_result_name"] = uploaded_file.name.replace(".xlsx", "_KM.xlsx")
            # Nettoyage output
            try:
                os.unlink(result["output_path"])
            except:
                pass
        else:
            st.session_state["km_error"] = result["error"]

    except Exception as e:
        st.session_state["km_error"] = f"{e}\n{traceback.format_exc()}"

    # Nettoyage temp
    try:
        os.unlink(tmp_path)
    except:
        pass

    # Force rerun pour afficher le résultat
    st.rerun()

# === Affichage résultat (PERSISTE après rerun) ===
if st.session_state["km_result_bytes"]:
    st.success("🎉 Calcul terminé !")
    st.download_button(
        label="📥 Télécharger le fichier KM",
        data=st.session_state["km_result_bytes"],
        file_name=st.session_state["km_result_name"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if st.session_state["km_error"]:
    st.error(f"❌ Erreur : {st.session_state['km_error']}")
