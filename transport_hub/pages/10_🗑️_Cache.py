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
    try:
        r = httpx.get(f"{FIREBASE_URL}/routes.json?shallow=true", timeout=10)
        if r.status_code == 200 and r.json():
            nb_routes = len(r.json())
            st.metric("Routes stockées", nb_routes)
        else:
            st.metric("Routes stockées", 0)
    except Exception as e:
        st.warning(f"Impossible de compter les routes : {e}")
        nb_routes = 0

    col_fb1, col_fb2 = st.columns(2)

    with col_fb1:
        if st.button("🗑️ Vider toutes les routes Firebase", type="primary"):
            try:
                # Récupérer toutes les clés (shallow=true → pas les données)
                r = httpx.get(f"{FIREBASE_URL}/routes.json?shallow=true", timeout=30)
                if r.status_code == 200 and r.json():
                    keys = list(r.json().keys())
                    progress = st.progress(0, text=f"Suppression de {len(keys)} routes...")
                    errors = 0
                    for i, key in enumerate(keys):
                        try:
                            httpx.delete(f"{FIREBASE_URL}/routes/{key}.json", timeout=10)
                        except Exception:
                            errors += 1
                        progress.progress((i + 1) / len(keys),
                                         text=f"Suppression {i+1}/{len(keys)}...")
                    progress.empty()
                    if errors == 0:
                        st.success(f"✅ {len(keys)} routes supprimées de Firebase")
                    else:
                        st.warning(f"⚠️ {len(keys)-errors}/{len(keys)} routes supprimées ({errors} erreurs)")
                else:
                    st.info("Firebase déjà vide.")
            except Exception as e:
                st.error(f"❌ Erreur : {e}")
            st.rerun()

    with col_fb2:
        if st.button("📊 Rafraîchir le comptage"):
            st.rerun()
