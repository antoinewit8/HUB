import streamlit as st
import os
import tempfile
import sys
import traceback
import pandas as pd
import time
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

st.set_page_config(page_title="Calcul KM PTV", page_icon="🗺️", layout="wide")
st.title("🗺️ Calcul de distances PTV")
st.markdown("---")

# === Upload ===
uploaded_file = st.file_uploader("📂 Dépose ton fichier Excel", type=["xlsx"])
calculer_peage = st.checkbox("💶 Calculer les frais de péage", value=False)
super_pref = st.checkbox("🚀 Mode SUPER PRÉFÉRENTIEL (évite tunnels/péages)", value=False)

if uploaded_file:
    st.session_state["uploaded_bytes"] = uploaded_file.read()
    uploaded_file.seek(0)

# === Lancement du calcul dans un thread ===
if st.session_state.get("uploaded_bytes") and st.button("🚀 Lancer le calcul", type="primary"):
    for key in ["km_result_bytes", "km_result_name", "km_stats", "calcul_result", "calcul_error"]:
        st.session_state.pop(key, None)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(st.session_state["uploaded_bytes"])
        tmp_path = tmp.name

    st.session_state["calcul_en_cours"] = True
    st.session_state["calcul_progress"] = (0, 1, "Démarrage...")
    st.session_state["tmp_path"] = tmp_path
    st.session_state["calcul_peage"] = calculer_peage
    st.session_state["calcul_super_pref"] = super_pref

    def run_in_thread():
        try:
            from tools.km_calcul.run_km import run_calcul_km

            def on_progress(current, total, message):
                st.session_state["calcul_progress"] = (current, total, message)

            result = run_calcul_km(
                st.session_state["tmp_path"],
                st.session_state["calcul_peage"],
                super_pref=st.session_state["calcul_super_pref"],
                progress_callback=on_progress,
            )
            st.session_state["calcul_result"] = result
        except Exception as e:
            st.session_state["calcul_error"] = traceback.format_exc()
        finally:
            st.session_state["calcul_en_cours"] = False

    t = threading.Thread(target=run_in_thread, daemon=True)
    t.start()
    st.rerun()

# === Affichage pendant le calcul ===
if st.session_state.get("calcul_en_cours"):
    current, total, message = st.session_state.get("calcul_progress", (0, 1, "..."))
    pct = current / total if total > 0 else 0

    st.info("⚙️ Calcul en cours... Ne fermez pas cette page.")
    st.progress(min(pct, 1.0))
    st.markdown(f"**⚙️ Progression : {current}/{total}** — {message}")

    time.sleep(1)
    st.rerun()  # ← maintient le WebSocket vivant et rafraîchit la progression

# === Post-traitement quand le thread est terminé ===
if not st.session_state.get("calcul_en_cours") and "calcul_result" in st.session_state:
    result   = st.session_state.pop("calcul_result")
    tmp_path = st.session_state.pop("tmp_path", None)

    if st.session_state.get("calcul_error"):
        st.error("❌ Une erreur critique est survenue durant le traitement.")
        st.code(st.session_state.pop("calcul_error"))
    elif result and result["success"]:
        try:
            with open(result["output_path"], "rb") as f:
                result_bytes = f.read()

            if not result_bytes:
                st.error("❌ Le fichier de sortie est vide ou corrompu.")
            else:
                st.session_state["km_result_bytes"] = result_bytes
                st.session_state["km_result_name"]  = os.path.basename(result["output_path"])
                st.session_state["km_stats"]        = result.get("stats", {})

                if os.path.exists(result["output_path"]):
                    os.unlink(result["output_path"])
        except Exception as e:
            st.error(f"⚠️ Erreur lecture résultat : {e}")
    else:
        st.error(f"⚠️ Le calcul a été interrompu : {result.get('error') if result else 'inconnu'}")
        if result:
            st.code(result.get("error", ""))

    if tmp_path and os.path.exists(tmp_path):
        os.unlink(tmp_path)


# === Résultats ===
if "km_result_bytes" in st.session_state:
    data  = st.session_state["km_result_bytes"]
    stats = st.session_state.get("km_stats", {})

    if isinstance(data, bytes) and len(data) > 0:
        st.success("🎉 Calcul terminé !")

        if stats:
            st.markdown("### 📊 Résumé")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("✅ Trajets OK",   stats.get("trajets_calcules", 0))
            col2.metric("❌ Erreurs",      stats.get("trajets_erreur", 0))
            col3.metric("📏 Total KM",     f"{stats.get('total_km', 0):,.0f} km")
            col4.metric("💶 Total Péage",  f"{stats.get('total_peage', 0):,.2f} €")

            st.markdown(f"🗄️ **{stats.get('from_cache', 0)}** trajets depuis le cache")

            if stats.get("erreurs_detail"):
                with st.expander("🔍 Détail des erreurs"):
                    for err in stats["erreurs_detail"]:
                        st.text(err)

            resultats = stats.get("resultats", [])
            if resultats:
                st.markdown("### 🔍 Aperçu des résultats")
                df = pd.DataFrame(resultats)
                st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.download_button(
            label="📥 Télécharger le fichier KM",
            data=data,
            file_name=st.session_state["km_result_name"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        if st.button("🔄 Nouveau calcul"):
            for key in ["km_result_bytes", "km_result_name", "km_stats"]:
                st.session_state.pop(key, None)
            st.rerun()
