# core/analyzer.py

import pandas as pd

def parse_dates(s):
    """Convertit correctement les dates de série Excel et les chaînes de caractères"""
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_datetime("1899-12-30") + pd.to_timedelta(s, unit="D")
    return pd.to_datetime(s, dayfirst=True, errors="coerce")

# ─── Seuils ───────────────────────────────────────────
SEUIL_KM_VENDREDI        = 250
SEUIL_ACTIVITES_VENDREDI = 5
SEUIL_KM_VIDE_ALERTE     = 100
SEUIL_KM_VIDE_MIN        = 5

# ─── Utilitaire partagé ───────────────────────────────
def _simplify_activity(act):
    act = str(act).lower().strip()
    if "décharg" in act:
        return "dechargement"
    if any(x in act for x in ["chargement", "charger", "chargé"]):
        return "chargement"
    return act

def _deduplicate(df):
    """Supprime les doublons TX-FLEX : même KM + même type d'activité."""
    df = df.copy()
    df["_act_simple"] = df["Activité / Enregistrement"].apply(_simplify_activity)
    df = df.drop_duplicates(subset=["KM", "_act_simple"], keep="first")
    df = df.sort_values("Date de création").reset_index(drop=True)
    return df

# ─── Fonctions principales ────────────────────────────
def compute_empty_km(df):
    """
    Calcule les km à vide entre chaque Déchargement → Chargement.
    (VERSION STABLE VALIDÉE)
    """
    empty_km_list    = []
    last_unload      = None
    waiting_for_load = False

    df = df.copy()
    df["Date de création"] = parse_dates(df["Date de création"])
    df = df.sort_values("Date de création").reset_index(drop=True)
    df = _deduplicate(df)

    for _, row in df.iterrows():
        activity = str(row["Activité / Enregistrement"]).lower().strip()
        km       = row["KM"]

        if pd.isna(km):
            continue

        if "décharg" in activity:
            last_unload = {
                "km":    km,
                "date":  row["Date de création"],
                "ville": str(row.get("Position de ville", "")).strip()
            }
            waiting_for_load = True

        elif "décharg" not in activity \
                and any(x in activity for x in ["chargement", "charger", "chargé"]) \
                and waiting_for_load \
                and last_unload is not None:

            empty_km = km - last_unload["km"]

            if empty_km >= SEUIL_KM_VIDE_MIN:
                alerte = empty_km >= SEUIL_KM_VIDE_ALERTE
                empty_km_list.append({
                    "date_depart":   last_unload["date"],
                    "date_arrivee":  row["Date de création"],
                    "ville_depart":  last_unload["ville"],
                    "ville_arrivee": str(row.get("Position de ville", "")).strip(),
                    "km_vide":       empty_km,
                    "alerte":        alerte,
                    "raison":        f"Trajet à vide de {empty_km} km" if alerte else ""
                })

            last_unload      = None
            waiting_for_load = False

    return empty_km_list

def compute_total_km(df):
    """
    Calcule les km totaux du mois.
    """
    df = df.copy()
    df["Date de création"] = parse_dates(df["Date de création"])
    df_km = df[df["KM"].notna() & (df["KM"] > 0)].sort_values("Date de création")

    if df_km.empty:
        return {"km_debut": 0, "km_fin": 0, "total": 0}

    km_debut = int(df_km["KM"].iloc[0])
    km_fin   = int(df_km["KM"].iloc[-1])

    return {
        "km_debut": km_debut,
        "km_fin":   km_fin,
        "total":    km_fin - km_debut
    }

def detect_friday_anomalies(df):
    """
    Analyse chaque vendredi :
    Calcule STRICTEMENT les km à vide générés par un déchargement le vendredi.
    (Ne compte pas les trajets à vide commencés le jeudi !)
    """
    alerts = []
    df = df.copy()
    df["Date de création"] = parse_dates(df["Date de création"])
    
    df_dedup = _deduplicate(df)
    df_dedup["jour"] = df_dedup["Date de création"].dt.date
    df_dedup["dow"]  = df_dedup["Date de création"].dt.dayofweek

    vendredis = df_dedup[df_dedup["dow"] == 4]["jour"].unique()

    for vendredi in vendredis:
        # On ne regarde QUE les événements de ce vendredi
        group = df_dedup[df_dedup["jour"] == vendredi].sort_values("Date de création")

        if group.empty:
            continue

        km_vals  = group["KM"].dropna()
        km_debut = km_vals.iloc[0]  if not km_vals.empty else 0
        km_fin   = km_vals.iloc[-1] if not km_vals.empty else 0
        km_total = km_fin - km_debut

        # --- NOUVEAU CALCUL : Comme un exploitant ---
        km_vide_jour = 0
        last_unload_km = None
        is_empty = False

        for _, row in group.iterrows():
            act = str(row["Activité / Enregistrement"]).lower().strip()
            km = row["KM"]

            if pd.isna(km):
                continue

            if "décharg" in act:
                is_empty = True
                last_unload_km = km  # Le camion est vide à partir d'ici
                
            elif any(x in act for x in ["chargement", "charger", "chargé"]):
                if is_empty and last_unload_km is not None:
                    km_vide_jour += (km - last_unload_km)
                is_empty = False
                last_unload_km = None

        # Si la journée se termine et que le camion n'a pas rechargé (retour dépôt)
        if is_empty and last_unload_km is not None:
            if km_fin > last_unload_km:
                km_vide_jour += (km_fin - last_unload_km)
        # --------------------------------------------

        nb_activites = len(group)
        heure_fin    = group["Date de création"].iloc[-1].strftime("%H:%M")

        villes = []
        for _, row in group.iterrows():
            v = str(row.get("Position de ville", "")).strip()
            if v and v != "nan" and v not in villes:
                villes.append(v)

        alerte_km        = km_total >= SEUIL_KM_VENDREDI
        alerte_activites = nb_activites >= SEUIL_ACTIVITES_VENDREDI and km_total > 50
        alerte_vide      = km_vide_jour >= 40  # J'ai mis 40km pour capter le retour de 46km !

        raisons = []
        if alerte_vide:
            raisons.append(f"KM à vide ce vendredi ({int(km_vide_jour)} km)")
        if alerte_km:
            raisons.append(f"KM totaux élevés ({int(km_total)} km)")
        if alerte_activites:
            raisons.append(f"Nb activités élevé ({nb_activites})")

        is_alert = alerte_vide or alerte_km or alerte_activites

        alerts.append({
            "date":            str(vendredi),
            "km_parcourus":    km_total,
            "km_vide":         int(km_vide_jour),
            "nb_activites":    nb_activites,
            "heure_fin":       heure_fin,
            "villes_visitees": villes,
            "alerte":          is_alert,
            "raisons":         raisons
        })

    return alerts