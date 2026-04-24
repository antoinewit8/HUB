# core/loader.py
 
import pandas as pd
import os
import subprocess
import tempfile
import shutil
 
 
def _convert_xls_to_xlsx(xls_path: str) -> str:
    """
    Convertit un fichier .xls en .xlsx via LibreOffice (sans xlrd).
    Retourne le chemin du fichier .xlsx temporaire créé.
    Lève une RuntimeError si LibreOffice est introuvable ou si la conversion échoue.
    """
    libreoffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not libreoffice:
        raise RuntimeError(
            "LibreOffice est introuvable sur ce système.\n"
            "Solution : convertissez vos fichiers .xls en .xlsx manuellement\n"
            "(Excel → Fichier → Enregistrer sous → .xlsx), puis relancez l'analyse."
        )
 
    tmp_dir = tempfile.mkdtemp(prefix="txflex_")
    try:
        result = subprocess.run(
            [libreoffice, "--headless", "--convert-to", "xlsx", xls_path, "--outdir", tmp_dir],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"LibreOffice n'a pas pu convertir {os.path.basename(xls_path)}.\n"
                f"Détail : {result.stderr.strip() or result.stdout.strip()}"
            )
 
        basename  = os.path.splitext(os.path.basename(xls_path))[0]
        xlsx_path = os.path.join(tmp_dir, basename + ".xlsx")
 
        if not os.path.exists(xlsx_path):
            raise RuntimeError(
                f"Fichier converti introuvable : {xlsx_path}\n"
                f"Sortie LibreOffice : {result.stdout.strip()}"
            )
 
        return xlsx_path
 
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
 
 
def load_data(path: str) -> pd.DataFrame:
    """
    Charge un fichier Excel TX-FLEX (.xls ou .xlsx) en DataFrame.
 
    - .xls  → conversion automatique via LibreOffice (pas besoin de xlrd)
    - .xlsx → lecture directe avec openpyxl
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Fichier introuvable : {path}")
 
    ext     = os.path.splitext(path)[1].lower()
    tmp_dir = None
 
    try:
        if ext == ".xls":
            xlsx_path = _convert_xls_to_xlsx(path)
            tmp_dir   = os.path.dirname(xlsx_path)
            df        = pd.read_excel(xlsx_path, engine="openpyxl")
        elif ext in (".xlsx", ".xlsm"):
            df = pd.read_excel(path, engine="openpyxl")
        else:
            df = pd.read_excel(path)
 
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
 
    # Validation colonne clé
    if "Date de création" not in df.columns:
        raise ValueError(
            f"Colonne 'Date de création' introuvable dans {os.path.basename(path)}.\n"
            f"Colonnes présentes : {list(df.columns)}"
        )
 
    df = df.sort_values(by="Date de création").reset_index(drop=True)
    return df
