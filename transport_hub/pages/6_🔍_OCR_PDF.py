import streamlit as st
import tempfile
import os
import io
import subprocess
from pathlib import Path
import shutil

st.set_page_config(page_title="OCR PDF", page_icon="🔍", layout="wide")
st.title("🔍 OCR de PDF scannés")
st.caption("Rend vos PDFs scannés cherchables et copiables grâce à OCRmyPDF + Tesseract")
st.divider()

import ocrmypdf


# ─── Langues disponibles ────────────────────────────────────────────────────
def get_available_langs() -> list[str]:
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().splitlines()
        langs = [l.strip() for l in lines if l.strip() and not l.startswith("List")]
        # Retirer 'osd' (orientation), garder langues utiles
        langs = [l for l in langs if l != "osd"]
        return sorted(langs)
    except Exception:
        return ["fra", "eng"]


LANG_LABELS = {
    "fra": "Français",
    "eng": "Anglais",
    "deu": "Allemand",
    "nld": "Néerlandais",
    "spa": "Espagnol",
    "ita": "Italien",
    "por": "Portugais",
}

available_langs = get_available_langs()
lang_options = {LANG_LABELS.get(l, l): l for l in available_langs}

# ─── Upload ─────────────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "📂 Chargez votre PDF scanné",
    type=["pdf"],
    help="PDF issu d'un scan ou d'une photo — sans couche texte"
)

if not uploaded:
    st.info("👆 Chargez un PDF pour démarrer l'OCR")
    st.stop()

st.success(f"✅ Fichier chargé : **{uploaded.name}** ({uploaded.size / 1024:.0f} Ko)")
st.divider()

# ─── Options ────────────────────────────────────────────────────────────────
st.subheader("⚙️ Options OCR")

col1, col2 = st.columns(2)

with col1:
    if lang_options:
        selected_label = st.selectbox(
            "🌐 Langue du document",
            options=list(lang_options.keys()),
            index=0,
            help="Langue principale du document (améliore la précision OCR)"
        )
        selected_lang = lang_options[selected_label]
    else:
        selected_lang = "fra"
        st.info("Langue par défaut : Français")

    deskew = st.checkbox(
        "📐 Redresser les pages (deskew)",
        value=True,
        help="Corrige l'inclinaison des pages scannées"
    )
    rotate = st.checkbox(
        "🔄 Rotation automatique des pages",
        value=False,
        help="Détecte et corrige l'orientation de chaque page"
    )
    clean = st.checkbox(
        "🧹 Nettoyer le scan (unpaper)",
        value=False,
        help="Supprime le bruit, les taches et bordures sales du scan"
    )
    clean_final = st.checkbox(
        "✨ Appliquer le nettoyage au PDF final",
        value=False,
        help="Le nettoyage est visible dans le PDF (pas seulement pour l'OCR)"
    )

with col2:
    output_type = st.selectbox(
        "📄 Format de sortie",
        options=["pdfa", "pdf", "pdfa-1", "pdfa-2", "pdfa-3"],
        index=0,
        help="PDF/A : format archivage long terme recommandé"
    )
    optimize = st.slider(
        "🗜️ Niveau d'optimisation",
        min_value=0, max_value=3, value=1,
        help="0 = aucune compression · 3 = compression maximale (lent)"
    )
    force_ocr = st.checkbox(
        "⚡ Forcer l'OCR (même si texte existant)",
        value=False,
        help="Re-OCRise même les pages qui ont déjà du texte"
    )

st.divider()

# ─── Lancement ──────────────────────────────────────────────────────────────
if st.button("🚀 Lancer l'OCR", type="primary"):

    pdf_bytes = uploaded.read()
    output_name = Path(uploaded.name).stem + "_OCR.pdf"

    progress = st.progress(0, text="Préparation…")
    status_box = st.empty()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path  = os.path.join(tmpdir, "input.pdf")
            output_path = os.path.join(tmpdir, "output.pdf")
            sidecar_path = os.path.join(tmpdir, "sidecar.txt")

            # Écriture du PDF source
            with open(input_path, "wb") as f:
                f.write(pdf_bytes)

            progress.progress(10, text="Lancement OCRmyPDF…")

            exit_code = ocrmypdf.ocr(
                input_path,
                output_path,
                language=[selected_lang],
                deskew=deskew,
                rotate_pages=rotate,
                output_type=output_type,
                optimize=0,            # ← 0 = aucune compression des images
                jpeg_quality=100,      # ← qualité JPEG maximale
                png_quality=100,       # ← qualité PNG maximale  
                force_ocr=force_ocr,
                sidecar=sidecar_path,
                progress_bar=False,
            )
            progress.progress(90, text="Finalisation…")

            if exit_code == ocrmypdf.ExitCode.ok:
                with open(output_path, "rb") as f:
                    result_bytes = f.read()

                # Texte extrait (sidecar)
                sidecar_text = ""
                if os.path.exists(sidecar_path):
                    with open(sidecar_path, "r", encoding="utf-8", errors="ignore") as f:
                        sidecar_text = f.read()

                progress.progress(100, text="✅ OCR terminé !")
                status_box.success(f"OCR réussi — {len(result_bytes) / 1024:.0f} Ko générés")

                st.divider()
                st.subheader("📥 Résultat")

                col_dl, col_info = st.columns([1, 2])
                with col_dl:
                    st.download_button(
                        label="⬇️ Télécharger le PDF OCRisé",
                        data=result_bytes,
                        file_name=output_name,
                        mime="application/pdf",
                        type="primary"
                    )

                with col_info:
                    original_size = len(pdf_bytes) / 1024
                    result_size   = len(result_bytes) / 1024
                    delta = result_size - original_size
                    sign  = "+" if delta > 0 else ""
                    st.metric("Taille originale",  f"{original_size:.0f} Ko")
                    st.metric("Taille OCRisée",    f"{result_size:.0f} Ko",
                              delta=f"{sign}{delta:.0f} Ko")

                # Aperçu du texte extrait
                if sidecar_text.strip():
                    with st.expander("📝 Aperçu du texte extrait (sidecar)", expanded=False):
                        st.text_area(
                            label="Texte OCR",
                            value=sidecar_text[:5000] + ("…" if len(sidecar_text) > 5000 else ""),
                            height=300,
                        )
                        st.download_button(
                            label="⬇️ Télécharger le texte brut (.txt)",
                            data=sidecar_text.encode("utf-8"),
                            file_name=Path(uploaded.name).stem + "_texte.txt",
                            mime="text/plain"
                        )

            else:
                progress.progress(100)
                status_box.error(f"OCRmyPDF a retourné le code : {exit_code}")

    except ocrmypdf.exceptions.PriorOcrFoundError:
        progress.empty()
        st.warning(
            "⚠️ Ce PDF contient déjà une couche texte. "
            "Activez **'Forcer l'OCR'** pour le re-traiter."
        )
    except ocrmypdf.exceptions.MissingDependencyError as e:
        progress.empty()
        st.error(f"❌ Dépendance manquante : {e}")
        st.info("Installez le pack Tesseract pour la langue choisie :\n"
                "`apt-get install tesseract-ocr-fra` (exemple pour le français)")
    except Exception as e:
        progress.empty()
        st.error(f"❌ Erreur inattendue : {e}")

# ─── Notes bas de page ───────────────────────────────────────────────────────
with st.expander("ℹ️ Infos & dépendances"):
    st.markdown(f"""
**OCRmyPDF** version `{ocrmypdf.__version__}` — moteur OCR : **Tesseract**

**Langues installées :** `{', '.join(available_langs) or 'aucune détectée'}`

Pour ajouter une langue (ex. français) sur le serveur :
```bash
apt-get install tesseract-ocr-fra
```

**Options clés :**
- `deskew` : redresse les pages penchées (scan de travers)
- `rotate_pages` : détecte et corrige l'orientation
- `optimize 0-3` : compresse les images du PDF final
- `force_ocr` : re-OCRise même si du texte existe déjà
- `sidecar` : génère un `.txt` du texte extrait en parallèle
""")
