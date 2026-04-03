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
    try:
        # 🔄 Réinitialisation propre des états de résultats
        for key in ["km_result_bytes", "km_result_name", "km_stats"]:
            st.session_state.pop(key, None)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(st.session_state["uploaded_bytes"])
            tmp_path = tmp.name

        from tools.km_calcul.run_km import run_calcul_km

        progress_bar = st.progress(0)
        status_text = st.empty()

        def on_progress(current, total, message):
            pct = current / total if total > 0 else 0
            progress_bar.progress(pct)
            status_text.markdown(f"**⚙️ Progression : {current}/{total}** — {message}")

        # Lancement du calcul avec gestion batch interne (via run_km)
        result = run_calcul_km(
            tmp_path, 
            calculer_peage, 
            super_pref=super_pref, 
            progress_callback=on_progress
        )

        if result["success"]:
            progress_bar.progress(1.0)
            status_text.success("**✅ Calcul terminé ! Préparation du téléchargement...**")
            
            with open(result["output_path"], "rb") as f:
                result_bytes = f.read()
            
            if not result_bytes:
                st.error("❌ Le fichier de sortie est vide ou corrompu.")
            else:
                st.session_state["km_result_bytes"] = result_bytes
                st.session_state["km_result_name"] = os.path.basename(result["output_path"])
                st.session_state["km_stats"] = result.get("stats", {})
                
                # Nettoyage fichier temporaire de sortie
                if os.path.exists(result["output_path"]):
                    os.unlink(result["output_path"])
                
                st.rerun() # 🚀 Force l'affichage des résultats
        else:
            st.error(f"⚠️ Le calcul a été interrompu : {result.get('error')}")
            st.code(result.get('error', ''))  # ← AJOUTE ÇA
            status_text.warning("Certains trajets ont pu être sauvegardés dans le cache. Réessayez pour compléter.")

        # Nettoyage fichier source temporaire
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    except Exception as e:
        st.error(f"❌ Une erreur critique est survenue durant le traitement.")
        st.warning(f"Détail : {str(e)}")
        st.code(traceback.format_exc())

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

            # === Détail des erreurs ===
            if stats.get("erreurs_detail"):
                with st.expander("🔍 Détail des erreurs"):
                    for err in stats["erreurs_detail"]:
                        st.text(err)

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
