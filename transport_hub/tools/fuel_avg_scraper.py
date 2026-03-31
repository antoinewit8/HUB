import pandas as pd
import requests
import os
from datetime import datetime

def get_statbel_data(view_id: str = "90a3de47-97fc-4870-9936-f55ed85f15fd") -> pd.DataFrame:
    """
    Récupère les données de prix depuis be.STAT via l'ID de la vue.
    Fallback sur data/fuel_avg.csv si le site est inaccessible.
    Vues suggérées :
    - 90a3de47-97fc-4870-9936-f55ed85f15fd (Mensuel)
    - 939c67bb-39fa-4f49-9d05-c446187bef1d (Quotidien complet)
    - cee4903e-c302-45be-9e43-e4b724ffb592 (30 derniers jours)
    """
    url = f"https://bestat.statbel.fgov.be/bestat/crosstable.xhtml?view={view_id}"
    # Utilisation d'un chemin relatif au projet
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "fuel_avg.csv")
    
    try:
        # Utilisation d'une session pour maintenir les cookies JSF
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
        }
        
        response = session.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            # On force l'utilisation de l'analyseur 'lxml' si disponible pour plus de robustesse
            dfs = pd.read_html(response.text, decimal=',', thousands='.', flavor='bs4')
            if dfs:
                df = dfs[0]
                
                # Nettoyage des noms de colonnes
                raw_cols = df.columns.tolist()
                clean_mapping = {}
                
                # Identification de la colonne de date
                col_date_idx = [i for i, c in enumerate(raw_cols) if any(x in str(c).lower() for x in ['période', 'mois', 'jour', 'date', '0'])][0]
                date_col_name = raw_cols[col_date_idx]
                clean_mapping[date_col_name] = "date_raw"

                # Mapping des autres colonnes (types de diesel/gasoil)
                for col in raw_cols:
                    if col == date_col_name: continue
                    # Nettoyage : "Gasoil de chauffage Extra (> 2000 l)" -> "Chauffage Extra >2000L"
                    name = str(col).replace("Gasoil de chauffage", "Chauff.").replace("(litres)", "").replace(" l", "L")
                    name = name.replace("  ", " ").strip()
                    clean_mapping[col] = name

                df = df.rename(columns=clean_mapping)

                # Nettoyage des lignes (on garde ce qui ressemble à une date ou un code temporel)
                df = df[df["date_raw"].str.contains(r'\d', na=False)].copy()
                
                # Conversion date flexible (gère 2024M01, DD/MM/YYYY, etc.)
                df["date"] = pd.to_datetime(
                    df["date_raw"].str.replace('M', '-'), 
                    dayfirst=True, 
                    errors='coerce'
                )
                df = df.dropna(subset=["date"]).sort_values("date")
                
                # On garde 'date' en premier, puis toutes les autres colonnes nettoyées
                cols_to_keep = ["date"] + [v for k, v in clean_mapping.items() if v != "date_raw"]
                
                # Pour la compatibilité avec les KPIs existants, on s'assure qu'une colonne s'appelle 'gasoil_routier'
                if "Diesel" in df.columns:
                    df = df.rename(columns={"Diesel": "gasoil_routier"})
                
                return df[cols_to_keep]

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

    return pd.DataFrame()

def get_monthly_averages() -> pd.DataFrame:
    """Maintient la compatibilité avec l'existant."""
    return get_statbel_data("90a3de47-97fc-4870-9936-f55ed85f15fd")

def get_daily_prices(full_history: bool = False) -> pd.DataFrame:
    """Récupère les prix journaliers (30j ou complet)."""
    view_id = "939c67bb-39fa-4f49-9d05-c446187bef1d" if full_history else "cee4903e-c302-45be-9e43-e4b724ffb592"
    return get_statbel_data(view_id)
