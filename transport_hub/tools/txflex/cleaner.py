# core/cleaner.py
import pandas as pd

def clean_data(df):
    """Nettoyage de base : colonnes, dates, tri. Sans filtre activités."""
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    df["Date de création"] = pd.to_datetime(
        df["Date de création"], dayfirst=True, errors="coerce"
    )

    df = df.dropna(subset=["Date de création"])
    df = df.sort_values("Date de création").reset_index(drop=True)

    return df


def filter_activities(df):
    """Filtre uniquement les lignes chargement / déchargement."""
    mask = df["Activité / Enregistrement"].str.lower().str.contains(
        "charg|décharg", na=False
    )
    return df[mask].copy()
