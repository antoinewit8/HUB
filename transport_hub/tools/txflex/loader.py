import pandas as pd
import os
 
def load_data(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Fichier introuvable : {path}")
 
    ext = os.path.splitext(path)[1].lower()
 
    # Sélection automatique du moteur selon l'extension
    # .xls  → engine="xlrd"  (anciens fichiers Excel 97-2003)
    # .xlsx → engine="openpyxl" (Excel 2007+)
    if ext == ".xls":
        try:
            df = pd.read_excel(path, engine="xlrd")
        except ImportError:
            raise ImportError(
                "Le fichier est au format .xls (ancien Excel).\n"
                "Installez xlrd : pip install xlrd>=2.0.1\n"
                "Ou convertissez vos fichiers en .xlsx avant l'analyse."
            )
    elif ext in (".xlsx", ".xlsm"):
        df = pd.read_excel(path, engine="openpyxl")
    else:
        # Tentative générique
        df = pd.read_excel(path)
 
    if "Date de création" not in df.columns:
        raise ValueError(
            f"Colonne 'Date de création' introuvable dans {os.path.basename(path)}.\n"
            f"Colonnes trouvées : {list(df.columns)}"
        )
 
    df = df.sort_values(by="Date de création").reset_index(drop=True)
 
    return df
