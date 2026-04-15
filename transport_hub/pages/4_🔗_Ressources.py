import streamlit as st
import json
import os

RESSOURCES_FILE = "ressources.json"

CATEGORIES = {
    "📊 Excel / Google Sheets": "📊",
    "📄 PDF / Word":            "📄",
}

def load():
    if os.path.exists(RESSOURCES_FILE):
        with open(RESSOURCES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save(data):
    with open(RESSOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

st.set_page_config(page_title="Ressources", page_icon="🔗", layout="wide")

st.markdown("""
<style>
.stApp { background: linear-gradient(160deg, #0F1923 0%, #152A3E 40%, #1B3A5C 100%); }
.res-card {
    background: linear-gradient(145deg, rgba(21,42,62,0.7), rgba(14,27,40,0.9));
    border: 1px solid rgba(74,144,217,0.15);
    border-radius: 14px;
    padding: 1.2rem 1.4rem;
    transition: all 0.3s ease;
    margin-bottom: 0.5rem;
}
.res-card:hover {
    border-color: rgba(74,144,217,0.4);
    box-shadow: 0 8px 30px rgba(74,144,217,0.12);
    transform: translateY(-3px);
}
.res-card a { text-decoration: none; }
.res-title { color: white; font-size: 1rem; font-weight: 600; margin: 0; }
.res-desc  { color: #8E99A9; font-size: 0.83rem; margin: 0.2rem 0 0 0; }
.res-cat   { color: #4A90D9; font-size: 0.75rem; font-weight: 500; margin-bottom: 0.3rem; }
section[data-testid="stSidebar"] { background: linear-gradient(180deg,#0E1B28,#152A3E) !important; }
.stDeployButton, #MainMenu, footer, header { display: none !important; }
</style>
""", unsafe_allow_html=True)

st.markdown('<h2 style="color:white; margin-bottom:0.2rem;">🔗 Ressources</h2>', unsafe_allow_html=True)
st.markdown('<p style="color:#8E99A9; margin-bottom:1.5rem;">Accès rapide aux fichiers et documents partagés</p>', unsafe_allow_html=True)

ressources = load()

# ── Filtres ───────────────────────────────────────────────────
cats_dispo = sorted(set(r["categorie"] for r in ressources)) if ressources else []
filtre = st.selectbox("Filtrer par catégorie", ["Toutes"] + cats_dispo, label_visibility="collapsed") if cats_dispo else "Toutes"

affichees = ressources if filtre == "Toutes" else [r for r in ressources if r["categorie"] == filtre]

# ── Affichage des liens ───────────────────────────────────────
if not affichees:
    st.markdown('<p style="color:#8E99A9; text-align:center; padding:2rem;">Aucune ressource — ajoutez-en ci-dessous ↓</p>', unsafe_allow_html=True)
else:
    cols = st.columns(3)
    for i, r in enumerate(affichees):
        with cols[i % 3]:
            icon = CATEGORIES.get(r["categorie"], "🔗")
            st.markdown(f"""
            <div class="res-card">
                <div class="res-cat">{r['categorie']}</div>
                <a href="{r['url']}" target="_blank">
                    <p class="res-title">{icon} {r['nom']}</p>
                </a>
                <p class="res-desc">{r['description']}</p>
            </div>""", unsafe_allow_html=True)
            if st.button("🗑️", key=f"del_{i}", help="Supprimer"):
                ressources.remove(r)
                save(ressources)
                st.rerun()

st.divider()

# ── Ajouter une ressource ─────────────────────────────────────
st.markdown('<p style="color:#4A90D9; font-weight:600; font-size:0.9rem;">➕ Ajouter une ressource</p>', unsafe_allow_html=True)

a1, a2 = st.columns(2)
with a1:
    nom  = st.text_input("Nom du fichier / document", placeholder="ex: Tarif CBS Béton BE")
    url  = st.text_input("Lien URL", placeholder="https://...")
with a2:
    desc = st.text_input("Description courte", placeholder="ex: Grille tarifaire Belgique 2025")
    cat  = st.selectbox("Catégorie", list(CATEGORIES.keys()))

if st.button("✅ Ajouter", use_container_width=False):
    if nom and url:
        ressources.append({"nom": nom, "url": url, "description": desc, "categorie": cat})
        save(ressources)
        st.success(f"« {nom} » ajouté !")
        st.rerun()
    else:
        st.warning("Nom et URL obligatoires.")