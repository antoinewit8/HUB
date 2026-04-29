# pages/5_🗑️_Cache.py
import streamlit as st
import os
import httpx
from dotenv import load_dotenv
from clear_cache import CACHES, afficher_taille, vider_cache, vider_tous

load_dotenv()
FIREBASE_URL = os.environ.get("FIREBASE_URL", "").rstrip("/")

st.set_page_config(page_title="Gestion du Cache", page_icon="🗑️")
st.title("🗑️ Gestion du Cache")
st.markdown("---")

# ── Caches locaux ─────────────────────────────────────────────────────────────
st.markdown("### 📁 Caches locaux")
for nom, path in CACHES.items():
    col1, col2 = st.columns([3, 1])
    col1.metric(label=nom.upper(), value=afficher_taille(path))
    if col2.button("Vider", key=f"clear_{nom}"):
        vider_cache(nom, path)
        st.success(f"Cache '{nom}' vidé ✅")
        st.rerun()

st.markdown("---")
if st.button("🗑️ Vider TOUS les caches locaux", type="primary"):
    vider_tous()
    st.success("Tous les caches vidés ✅")
    st.rerun()

# ── Firebase ──────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### 🔥 Firebase Realtime Database")

if not FIREBASE_URL:
    st.warning("⚠️ FIREBASE_URL non configurée dans les secrets.")
else:
    col_fb1, col_fb2 = st.columns(2)

    with col_fb1:
        if st.button("🗑️ Vider toutes les routes Firebase", type="primary"):
            try:
                # Écrire null sur le nœud /routes — Firebase supprime tout
                r = httpx.put(
                    f"{FIREBASE_URL}/routes.json",
                    content=b"null",
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                if r.status_code == 200:
                    st.success("✅ Firebase vidé — toutes les routes supprimées")
                else:
                    st.error(f"❌ Erreur Firebase : {r.status_code} — {r.text[:300]}")
            except Exception as e:
                st.error(f"❌ Erreur : {e}")
            st.rerun()

    with col_fb2:
        if st.button("📊 Vérifier Firebase"):
            try:
                # Tenter de lire juste le premier niveau
                r = httpx.get(
                    f"{FIREBASE_URL}/routes.json?shallow=true&limitToFirst=5",
                    timeout=15
                )
                st.write("Statut:", r.status_code)
                st.write("Réponse:", str(r.text[:500]))
            except Exception as e:
                st.error(f"❌ {e}")
