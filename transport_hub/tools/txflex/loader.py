# core/loader.py

import pandas as pd
import os

def load_data(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    df = pd.read_excel(path)

    df = df.sort_values(by="Date de création")

    return df
