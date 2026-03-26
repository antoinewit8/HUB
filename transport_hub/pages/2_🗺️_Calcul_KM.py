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

# === Debug persistant ===
if "km_debug" in st.session_state:
    st.info(f"🔍 Dernier debug : {st.session_state['km_debug']}")

uploaded_file = st.file_uploader("📂 Dépose ton fichier Excel", type=["xlsx"])
calculer_peage = st.checkbox("💶 Calculer les frais de péage", value=False)

if uploaded_file and st.button("🚀 Lancer le calcul", type="primary"):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    try:
        st.session_state["km_debug"] = "Calcul lancé..."
        result = run_calcul_km(tmp_path, calculer_peage=calculer_peage)
        st.session_state["km_debug"] = f"Result: success={result.get('success')}, keys={list(result.keys())}"

        if result["success"]:
            with open(result["output_path"], "rb") as f:
                data = f.read()
            st.session_state["km_result_bytes"] = data
            st.session_state["km_result_name"] = uploaded_file.name.replace(".xlsx", "_KM.xlsx")
            st.session_state["km_debug"] = f"OK - {len(data)} bytes sauvés"

            for p in [tmp_path, result["output_path"]]:
                try:
                    os.unlink(p)
                except:
                    pass
        else:
            st.session_state["km_debug"] = f"Echec: {result.get('error')}"
    except Exception as e:
        st.session_state["km_debug"] = f"EXCEPTION: {e}\n{traceback.format_exc()}"

    st.rerun()

# === Download ===
if "km_result_bytes" in st.session_state:
    data = st.session_state["km_result_bytes"]
    if isinstance(data, bytes) and len(data) > 0:
        st.success("🎉 Calcul terminé !")
        st.download_button(
            label="📥 Télécharger le fichier KM",
            data=data,
            file_name=st.session_state["km_result_name"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
