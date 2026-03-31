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
                col_date_idx = [i for i, c in enumerate(raw_cols) if any(x in str(c).lower() for x in ['période', 'mois', '0'])][0]
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

                # Nettoyage des lignes de total ou vides
                df = df[df["date_raw"].str.contains(r'\d{4}', na=False)].copy()
                
                # Conversion date (Format be.STAT : 2024M01 ou Janvier 2024)
                df["date"] = pd.to_datetime(df["date_raw"].str.replace('M', '-'), errors='coerce')
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

    # Retourne un DataFrame vide si tout échoue
    return pd.DataFrame(columns=["date", "gasoil_routier", "gasoil_chauffage"])
