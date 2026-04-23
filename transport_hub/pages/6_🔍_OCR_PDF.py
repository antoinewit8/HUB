import streamlit as st
import tempfile
import os
import io
import subprocess
from pathlib import Path
import shutil

st.set_page_config(page_title="OCR & Amélioration PDF", page_icon="🔍", layout="wide")

# ─── CSS CB Groupe ───────────────────────────────────────────────────────────
st.markdown("""
<style>
:root {
    --cb-navy: #1B3A5C;
    --cb-navy-light: #244B73;
    --cb-navy-dark: #122840;
    --cb-accent: #4A90D9;
    --cb-accent-light: #6BA3E0;
    --cb-white: #FFFFFF;
    --cb-gray-200: #D8DDE6;
    --cb-gray-400: #8E99A9;
    --cb-success: #2ECC71;
    --cb-warning: #F39C12;
    --cb-danger: #E74C3C;
}
.stApp { background: linear-gradient(160deg, #0F1923 0%, #152A3E 40%, #1B3A5C 100%); }
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0E1B28 0%, #152A3E 100%) !important;
    border-right: 1px solid rgba(74,144,217,0.15);
}
.cb-card {
    background: rgba(27,58,92,0.45);
    border: 1px solid rgba(74,144,217,0.2);
    border-radius: 14px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1rem;
}
.cb-card h4 { color: var(--cb-accent-light); margin: 0 0 0.5rem 0; font-size: 0.95rem; }
.stButton > button {
    background: linear-gradient(135deg, var(--cb-navy) 0%, var(--cb-navy-light) 100%) !important;
    color: white !important;
    border: 1px solid rgba(74,144,217,0.3) !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    transition: all 0.3s ease !important;
}
.stButton > button:hover {
    border-color: var(--cb-accent) !important;
    box-shadow: 0 4px 20px rgba(74,144,217,0.25) !important;
    transform: translateY(-2px) !important;
}
[data-testid="stMetricValue"] { color: white !important; }
[data-testid="stMetricLabel"] { color: var(--cb-gray-400) !important; }
</style>
""", unsafe_allow_html=True)

st.title("🔍 Amélioration & OCR de PDF scannés")
st.caption("Améliore la qualité visuelle de vos scans + ajoute une couche texte cherchable")
st.divider()

# ─── Imports lourds ─────────────────────────────────────────────────────────
try:
    from pdf2image import convert_from_bytes
    from PIL import Image, ImageEnhance, ImageFilter
    import img2pdf
    import ocrmypdf
    DEPS_OK = True
except ImportError as e:
    st.error(f"❌ Dépendance manquante : `{e}` — vérifiez `requirements.txt`")
    DEPS_OK = False
    st.stop()

# ─── Langues disponibles ────────────────────────────────────────────────────
def get_available_langs() -> list[str]:
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().splitlines()
        langs = [l.strip() for l in lines if l.strip() and not l.startswith("List") and l.strip() != "osd"]
        return sorted(langs)
    except Exception:
        return ["fra", "eng"]

LANG_LABELS = {
    "fra": "Français", "eng": "Anglais", "deu": "Allemand",
    "nld": "Néerlandais", "spa": "Espagnol", "ita": "Italien",
}
available_langs = get_available_langs()
lang_options = {LANG_LABELS.get(l, l): l for l in available_langs}

# ─── Upload ─────────────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "📂 Chargez votre PDF scanné",
    type=["pdf"],
    help="PDF issu d'un scan — flou, faible contraste, écriture peu lisible"
)

if not uploaded:
    st.info("👆 Chargez un PDF pour démarrer")
    st.stop()

st.success(f"✅ **{uploaded.name}** — {uploaded.size / 1024:.0f} Ko")
st.divider()

# ─── Options ────────────────────────────────────────────────────────────────
st.subheader("⚙️ Paramètres")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown('<div class="cb-card"><h4>🖼️ Amélioration image</h4>', unsafe_allow_html=True)
    enhance = st.checkbox("Activer l'amélioration visuelle", value=True,
                          help="Applique des filtres sur chaque page pour améliorer la lisibilité")
    contrast = st.slider("Contraste", 0.5, 3.0, 1.8, 0.1,
                         help="1.0 = original · >1 = plus contrasté")
    sharpness = st.slider("Netteté", 0.5, 3.0, 2.0, 0.1,
                          help="1.0 = original · >1 = plus net")
    brightness = st.slider("Luminosité", 0.5, 2.0, 1.1, 0.1,
                            help="1.0 = original · >1 = plus lumineux")
    grayscale = st.checkbox("Convertir en niveaux de gris", value=False,
                            help="Réduit le poids du fichier, améliore les scans en N&B")
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="cb-card"><h4>🔍 OCR</h4>', unsafe_allow_html=True)
    do_ocr = st.checkbox("Ajouter couche texte (OCR)", value=True,
                         help="Rend le PDF cherchable et copiable")
    if lang_options:
        selected_label = st.selectbox("Langue", list(lang_options.keys()))
        selected_lang = lang_options[selected_label]
    else:
        selected_lang = "fra"
    deskew = st.checkbox("Redresser les pages (deskew)", value=True)
    rotate = st.checkbox("Rotation automatique", value=False)
    force_ocr = st.checkbox("Forcer l'OCR", value=False,
                            help="Re-OCRise même si du texte existe déjà")
    st.markdown('</div>', unsafe_allow_html=True)

with col3:
    st.markdown('<div class="cb-card"><h4>📄 Sortie</h4>', unsafe_allow_html=True)
    dpi = st.select_slider("Résolution (DPI)", options=[150, 200, 300, 400], value=300,
                           help="300 DPI recommandé — 400 = qualité max mais lent")
    output_type = st.selectbox("Format", ["pdfa", "pdf", "pdfa-2", "pdfa-3"], index=0)
    sidecar = st.checkbox("Générer fichier texte (.txt)", value=False,
                          help="Exporte le texte OCR extrait en parallèle")
    st.markdown('</div>', unsafe_allow_html=True)

st.divider()

# ─── Traitement ─────────────────────────────────────────────────────────────
if st.button("🚀 Lancer le traitement", type="primary"):

    pdf_bytes = uploaded.read()
    output_name = Path(uploaded.name).stem + "_ameliore.pdf"

    progress = st.progress(0, text="Lecture du PDF…")
    status_box = st.empty()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:

            # ── Étape 1 : Conversion PDF → images ──────────────────────────
            progress.progress(10, text="Conversion en images…")
            pages = convert_from_bytes(pdf_bytes, dpi=dpi)
            total_pages = len(pages)
            status_box.info(f"📄 {total_pages} page(s) détectée(s)")

            enhanced_images = []

            for i, page in enumerate(pages):
                pct = 10 + int((i / total_pages) * 50)
                progress.progress(pct, text=f"Amélioration page {i+1}/{total_pages}…")

                if enhance:
                    # Niveaux de gris
                    if grayscale:
                        page = page.convert("L").convert("RGB")

                    # Contraste
                    page = ImageEnhance.Contrast(page).enhance(contrast)

                    # Luminosité
                    page = ImageEnhance.Brightness(page).enhance(brightness)

                    # Netteté
                    page = ImageEnhance.Sharpness(page).enhance(sharpness)

                    # Filtre de netteté supplémentaire si valeur élevée
                    if sharpness >= 2.0:
                        page = page.filter(ImageFilter.SHARPEN)

                enhanced_images.append(page)

            # ── Étape 2 : Recompilation en PDF ─────────────────────────────
            progress.progress(65, text="Recompilation du PDF…")

            image_paths = []
            for i, img in enumerate(enhanced_images):
                img_path = os.path.join(tmpdir, f"page_{i:04d}.jpg")
                img.save(img_path, "JPEG", quality=95, optimize=True)
                image_paths.append(img_path)

            enhanced_pdf_path = os.path.join(tmpdir, "enhanced.pdf")
            with open(enhanced_pdf_path, "wb") as f:
                f.write(img2pdf.convert(image_paths))

            # ── Étape 3 : OCR ──────────────────────────────────────────────
            if do_ocr:
                progress.progress(75, text="OCR en cours…")

                output_path  = os.path.join(tmpdir, "output.pdf")
                sidecar_path = os.path.join(tmpdir, "sidecar.txt") if sidecar else None

                exit_code = ocrmypdf.ocr(
                    enhanced_pdf_path,
                    output_path,
                    language=[selected_lang],
                    deskew=deskew,
                    rotate_pages=rotate,
                    output_type=output_type,
                    optimize=0,          # on a déjà optimisé les images
                    force_ocr=force_ocr,
                    sidecar=sidecar_path,
                    progress_bar=False,
                )

                if exit_code != ocrmypdf.ExitCode.ok:
                    status_box.error(f"OCRmyPDF a retourné le code : {exit_code}")
                    st.stop()

                final_path = output_path
            else:
                final_path = enhanced_pdf_path

            # ── Étape 4 : Résultat ─────────────────────────────────────────
            progress.progress(95, text="Finalisation…")

            with open(final_path, "rb") as f:
                result_bytes = f.read()

            sidecar_text = ""
            if sidecar and do_ocr and sidecar_path and os.path.exists(sidecar_path):
                with open(sidecar_path, "r", encoding="utf-8", errors="ignore") as f:
                    sidecar_text = f.read()

            progress.progress(100, text="✅ Traitement terminé !")
            status_box.success("Traitement terminé avec succès !")

            # ── Résultats ──────────────────────────────────────────────────
            st.divider()
            st.subheader("📥 Résultat")

            m1, m2, m3 = st.columns(3)
            orig_ko   = len(pdf_bytes) / 1024
            result_ko = len(result_bytes) / 1024
            delta     = result_ko - orig_ko
            sign      = "+" if delta > 0 else ""

            m1.metric("Pages traitées", f"{total_pages}")
            m2.metric("Taille originale", f"{orig_ko:.0f} Ko")
            m3.metric("Taille finale", f"{result_ko:.0f} Ko", delta=f"{sign}{delta:.0f} Ko")

            st.download_button(
                label="⬇️ Télécharger le PDF amélioré",
                data=result_bytes,
                file_name=output_name,
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )

            if sidecar_text.strip():
                with st.expander("📝 Texte extrait (sidecar)", expanded=False):
                    st.text_area(
                        "Texte OCR",
                        value=sidecar_text[:5000] + ("…" if len(sidecar_text) > 5000 else ""),
                        height=300,
                    )
                    st.download_button(
                        "⬇️ Télécharger le texte (.txt)",
                        data=sidecar_text.encode("utf-8"),
                        file_name=Path(uploaded.name).stem + "_texte.txt",
                        mime="text/plain",
                    )

    except ocrmypdf.exceptions.PriorOcrFoundError:
        progress.empty()
        st.warning("⚠️ Ce PDF contient déjà une couche texte. Activez **'Forcer l'OCR'** pour le re-traiter.")
    except ocrmypdf.exceptions.MissingDependencyError as e:
        progress.empty()
        st.error(f"❌ Dépendance manquante : {e}")
    except Exception as e:
        progress.empty()
        st.error(f"❌ Erreur : {e}")
        raise e

# ─── Infos ───────────────────────────────────────────────────────────────────
with st.expander("ℹ️ Comment ça fonctionne ?"):
    st.markdown(f"""
**Pipeline de traitement :**
1. 🖼️ Conversion de chaque page PDF en image haute résolution (DPI choisi)
2. ✨ Application des filtres Pillow : contraste, luminosité, netteté
3. 📄 Recompilation en PDF
4. 🔍 OCR via OCRmyPDF + Tesseract (couche texte invisible)

**Langues installées :** `{', '.join(available_langs) or 'aucune détectée'}`

**Conseils :**
- Pour un scan flou : augmenter la **netteté** à 2.5+
- Pour un scan sombre : augmenter la **luminosité** à 1.3+
- Pour un scan avec fond grisâtre : augmenter le **contraste** à 2.0+
- Pour réduire le poids : activer **niveaux de gris** si le document est en N&B
""")
