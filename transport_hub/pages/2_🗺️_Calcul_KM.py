import streamlit as st
import os
import tempfile
import sys
import traceback
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

st.set_page_config(page_title="Calcul KM PTV", page_icon="🗺️", layout="wide")
st.title("🗺️ Calcul de distances PTV")
st.markdown("---")

# === Upload ===
uploaded_file = st.file_uploader("📂 Dépose ton fichier Excel", type=["xlsx"])
calculer_peage = st.checkbox("💶 Calculer les frais de péage", value=False)
super_pref = st.checkbox("🚀 Mode SUPER PRÉFÉRENTIEL (évite tunnels/péages)", value=False)

if uploaded_file:
    # Sauvegarder en session pour survivre au rerun
    st.session_state["uploaded_bytes"] = uploaded_file.read()
    uploaded_file.seek(0)  # reset pour réutilisation

if st.session_state.get("uploaded_bytes") and st.button("🚀 Lancer le calcul", type="primary"):
    # 🔄 Réinitialiser le state pour effacer les anciens résultats avant de commencer
    for key in ["km_result_bytes", "km_result_name", "km_stats"]:
        st.session_state.pop(key, None)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(st.session_state["uploaded_bytes"])
        tmp_path = tmp.name

    try:
        from tools.km_calcul.run_km import run_calcul_km

        # === Barre de progression ===
        progress_bar = st.progress(0)
        status_text = st.empty()

        def on_progress(current, total, message):
            pct = current / total if total > 0 else 0
            progress_bar.progress(pct)
            status_text.markdown(f"**⚙️ Traitement : {current}/{total}** — {message}")

        result = run_calcul_km(tmp_path, calculer_peage, super_pref=super_pref, progress_callback=on_progress)

        if result["success"]:
            progress_bar.progress(1.0)
            status_text.markdown("**✅ Terminé avec succès !**")
            
            with open(result["output_path"], "rb") as f:
                result_bytes = f.read()
            
            if not result_bytes:
                raise ValueError("Le fichier généré est vide.")

            st.session_state["km_result_bytes"] = result_bytes
            st.session_state["km_result_name"] = os.path.basename(result["output_path"])
            st.session_state["km_stats"] = result.get("stats", {})
            os.unlink(result["output_path"])
        else:
            st.error(f"⚠️ Échec : {result['error']}")
            status_text.markdown(f"❌ **Erreur :** {result['error']}")
            progress_bar.empty()

    except Exception as e:
        st.error(f"❌ EXCEPTION: {e}")
        st.code(traceback.format_exc())
    finally:
        os.unlink(tmp_path)

# === Résultats ===
if "km_result_bytes" in st.session_state:
    data = st.session_state["km_result_bytes"]
    stats = st.session_state.get("km_stats", {})

    if isinstance(data, bytes) and len(data) > 0:
        st.success("🎉 Calcul terminé !")

        # === Stats résumé ===
        if stats:
            st.markdown("### 📊 Résumé")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("✅ Trajets OK", stats.get("trajets_ok", 0))
            col2.metric("❌ Erreurs", stats.get("trajets_erreur", 0))
            col3.metric("📏 Total KM", f"{stats.get('total_km', 0):,.0f} km")
            col4.metric("💶 Total Péage", f"{stats.get('total_peage', 0):,.2f} €")

            st.markdown(f"🗄️ **{stats.get('from_cache', 0)}** trajets depuis le cache")

            # === Aperçu tableau ===
            resultats = stats.get("resultats", [])
            if resultats:
                st.markdown("### 🔍 Aperçu des résultats")
                df = pd.DataFrame(resultats)
                st.dataframe(df, use_container_width=True, hide_index=True)

        # === Téléchargement ===
        st.markdown("---")
        st.download_button(
            label="📥 Télécharger le fichier KM",
            data=data,
            file_name=st.session_state["km_result_name"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # === Bouton reset ===
        if st.button("🔄 Nouveau calcul"):
            for key in ["km_result_bytes", "km_result_name", "km_stats"]:
                st.session_state.pop(key, None)
            st.rerun()
