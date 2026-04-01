"""
Logique d'optimisation de route "Super Préférentielle".
Gère l'injection de waypoints de contournement et les paramètres d'évitement.
"""

def get_super_pref_logic(lat_start, lon_start, lat_end, lon_end):
    """
    Détermine les waypoints à ajouter et les éléments à éviter pour le mode Super.
    """
    extra_waypoints = []
    # En mode Super, on force l'évitement des péages pour privilégier les nationales
    avoid_features = ["TOLL_ROADS"] 

    # 1. Corridor France <-> Italie (Éviter tunnels Fréjus / Mont-Blanc / Gothard)
    # Détection simplifiée par zones géographiques
    is_fr = (41.0 <= lat_start <= 51.5 and -5.0 <= lon_start <= 9.5) or \
            (41.0 <= lat_end <= 51.5 and -5.0 <= lon_end <= 9.5)
    is_it = (36.0 <= lat_start <= 47.5 and 6.0 <= lon_start <= 18.5) or \
            (36.0 <= lat_end <= 47.5 and 6.0 <= lon_end <= 18.5)

    if is_fr and is_it:
        # Si trajet Sud-Ouest/Centre -> Passage par la côte (Vintimille) au lieu des tunnels Alpes
        if min(lat_start, lat_end) < 45.5:
            # Waypoint : Vintimille (Frontière côtière)
            extra_waypoints.append((43.7912, 7.6075))
        else:
            # Si trajet Nord/Est -> Forcer passage par l'Autriche (Brenner) pour éviter tunnels et Suisse
            # Waypoint : Innsbruck / Brenner
            extra_waypoints.append((47.2636, 11.4012))

    # 2. Transit Suisse (Si départ et arrivée hors Suisse mais trajet risquant de la traverser)
    is_ch = lambda lat, lon: 45.8 <= lat <= 47.8 and 5.9 <= lon <= 10.5
    if not is_ch(lat_start, lon_start) and not is_ch(lat_end, lon_end):
        # La traversée de la Suisse est déjà largement évitée par les points Brenner ou Vintimille
        # On peut ajouter ici d'autres points de contournement si nécessaire
        pass

    return extra_waypoints, avoid_features