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
        import time
        
        # TEST 1 : Import seul
        st.session_state["km_debug"] = "Step 1: imports..."
        from tools.km_calcul.modules.map_server_client import warm_up_server
        from tools.km_calcul.modules.excel_handler_km import read_all_sheets
        st.session_state["km_debug"] = "Step 2: imports OK"
        
        # TEST 2 : Lecture Excel
        wb, sheets_data = read_all_sheets(tmp_path)
        nb = sum(len(r) for _, (_, r) in sheets_data.items()) if sheets_data else 0
        st.session_state["km_debug"] = f"Step 3: Excel OK - {nb} routes trouvées"
        
        # TEST 3 : Warm up (souvent le coupable)
        # COMMENTE SI ÇA BLOQUE ICI
        # warm_up_server()
        # st.session_state["km_debug"] = "Step 4: warm_up OK"
        
        os.unlink(tmp_path)
        
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
