import pandas as pd
import requests
import os
from datetime import datetime

def get_monthly_averages() -> pd.DataFrame:
    """
    Récupère les moyennes mensuelles du gasoil depuis be.STAT (Statbel).
    Fallback sur data/fuel_avg.csv si le site est inaccessible.
    """
    url = "https://bestat.economie.fgov.be/bestat/crosstable.xhtml?view=90a3de47-97fc-4870-9936-f55ed85f15fd"
    csv_path = "data/fuel_avg.csv"
    
    try:
        # Tentative de lecture HTML (pd.read_html gère souvent les tableaux simples même en JSF)
        # On utilise des headers pour éviter d'être bloqué
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            dfs = pd.read_html(response.text, decimal=',', thousands='.')
            if dfs:
                df = dfs[0]
                
                # Nettoyage standard pour be.STAT
                # Colonnes attendues : 0: Période, 2: Gasoil chauffage (>2000L), 3: Diesel routier
                df = df.iloc[:, [0, 2, 3]]
                df.columns = ["date_raw", "gasoil_chauffage", "gasoil_routier"]
                
                # Nettoyage des lignes de total ou vides
                df = df[df["date_raw"].str.contains(r'\d{4}', na=False)].copy()
                
                # Conversion date (Format be.STAT : 2024M01 ou Janvier 2024)
                # On simplifie pour le DataFrame
                df["date"] = pd.to_datetime(df["date_raw"].str.replace('M', '-'), errors='coerce')
                df = df.dropna(subset=["date"]).sort_values("date")
                
                return df[["date", "gasoil_routier", "gasoil_chauffage"]]

    except Exception as e:
        print(f"DEBUG: Erreur scraping be.STAT : {e}")

    # ── FALLBACK SUR CSV LOCAL ──
    if os.path.exists(csv_path):
        try:
            df_local = pd.read_csv(csv_path)
            if "date" in df_local.columns:
                df_local["date"] = pd.to_datetime(df_local["date"])
                return df_local.sort_values("date")
        except Exception as e:
            print(f"DEBUG: Erreur lecture CSV local : {e}")

    # Retourne un DataFrame vide si tout échoue
    return pd.DataFrame(columns=["date", "gasoil_routier", "gasoil_chauffage"])
