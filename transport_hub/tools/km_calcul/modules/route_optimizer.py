"""
Logique d'optimisation de route "Super Préférentielle".
Gère l'injection de waypoints de contournement et les paramètres d'évitement.
"""

def get_super_pref_logic(lat_start, lon_start, lat_end, lon_end):
    """
    Détermine les waypoints à ajouter et les éléments à éviter pour le mode Super.
    """
    extra_waypoints = []
    avoid_features = ["TOLL"]

    return extra_waypoints, avoid_features
