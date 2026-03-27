# pages/5_🗑️_Cache.py
import streamlit as st
from clear_cache import CACHES, afficher_taille, vider_cache, vider_tous

st.set_page_config(page_title="Gestion du Cache", page_icon="🗑️")
st.title("🗑️ Gestion du Cache")

st.markdown("---")

for nom, path in CACHES.items():
    col1, col2 = st.columns([3, 1])
    col1.metric(label=nom.upper(), value=afficher_taille(path))
    if col2.button("Vider", key=f"clear_{nom}"):
        vider_cache(nom, path)
        st.success(f"Cache '{nom}' vidé ✅")
        st.rerun()

st.markdown("---")

if st.button("🗑️ Vider TOUS les caches", type="primary"):
    vider_tous()
    st.success("Tous les caches vidés ✅")
    st.rerun()
