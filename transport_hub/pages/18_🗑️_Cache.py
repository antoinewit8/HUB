# pages/18_🗑️_Cache.py
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
    st.caption(f"Base : `{FIREBASE_URL}`")

    col_fb1, col_fb2 = st.columns(2)

    with col_fb2:
        if st.button("📊 Vérifier Firebase"):
            try:
                r = httpx.get(
                    f"{FIREBASE_URL}/routes.json?shallow=true",
                    timeout=15
                )
                if r.status_code == 200:
                    data = r.json()
                    if data:
                        nb = len(data)
                        st.success(f"✅ {nb} route(s) en base")
                        st.json(data)
                    else:
                        st.info("Base vide — aucune route.")
                else:
                    st.error(f"❌ Statut: `{r.status_code}`\nRéponse: {r.text[:300]}")
            except Exception as e:
                st.error(f"❌ {e}")

    with col_fb1:
        if st.button("🗑️ Vider toutes les routes Firebase", type="primary"):
            try:
                # 1. Shallow listing pour récupérer toutes les clés
                r = httpx.get(
                    f"{FIREBASE_URL}/routes.json?shallow=true",
                    timeout=15
                )
                if r.status_code != 200:
                    st.error(f"❌ Impossible de lire Firebase : {r.status_code}")
                    st.stop()

                data = r.json()

                if not data:
                    st.info("✅ Firebase déjà vide — rien à supprimer.")
                else:
                    keys = list(data.keys())
                    st.info(f"🔄 Suppression de {len(keys)} route(s) en cours...")
                    progress = st.progress(0)
                    errors = []

                    # 2. Suppression clé par clé
                    for i, key in enumerate(keys):
                        try:
                            resp = httpx.delete(
                                f"{FIREBASE_URL}/routes/{key}.json",
                                timeout=10
                            )
                            if resp.status_code not in (200, 204):
                                errors.append(f"{key}: {resp.status_code}")
                        except Exception as e:
                            errors.append(f"{key}: {e}")
                        progress.progress((i + 1) / len(keys))

                    if errors:
                        st.warning(f"⚠️ {len(errors)} erreur(s) : {errors[:5]}")
                    else:
                        st.success(f"✅ {len(keys)} route(s) supprimée(s) avec succès !")

            except Exception as e:
                st.error(f"❌ Erreur : {e}")
            st.rerun()
