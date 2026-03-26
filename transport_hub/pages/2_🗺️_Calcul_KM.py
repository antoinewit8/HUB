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
        st.session_state["km_debug"] = "Step 1: imports..."
        from tools.km_calcul.modules.map_server_client import warm_up_server
        from tools.km_calcul.modules.excel_handler_km import read_all_sheets
        from tools.km_calcul.modules.ptv_router_km import geocode_address
        st.session_state["km_debug"] = "Step 2: imports OK"

        wb, sheets_data = read_all_sheets(tmp_path)
        nb = sum(len(r) for _, (_, r) in sheets_data.items()) if sheets_data else 0
        st.session_state["km_debug"] = f"Step 3: Excel OK - {nb} routes"

        # TEST warm_up avec timeout
        import time
        t0 = time.time()
        warm_up_server()
        st.session_state["km_debug"] = f"Step 4: warm_up OK ({time.time()-t0:.1f}s)"

        # TEST géocodage simple
        import requests as req
        t0 = time.time()
        key = os.environ.get("PTV_API_KEY", "MANQUANTE")
        key_info = f"{key[:8]}... (len={len(key)})"
        resp = req.get(
            "https://api.myptv.com/geocoding/v1/locations/by-text",
            params={"searchText": "Paris, France"},
            headers={"apiKey": key},
            timeout=15
        )
        st.session_state["km_debug"] = (
            f"Step 5: status={resp.status_code} | key={key_info} | "
            f"body={resp.text[:200]} ({time.time()-t0:.1f}s)"
        )


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
