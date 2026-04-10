"""
Villes-jalons automatiques pour forcer les axes routiers PL.
Si le trajet passe à moins de 35km d'une ville-jalon, elle devient waypoint.
"""

import math

# ==========================================
# VILLES-JALONS (lat, lon)
# ==========================================

VILLES_JALONS = {
    # Sud / Massif Central (points sur N88, A75, RN)
    "Puy-en-Velay":     (45.0540,  3.8530),   # N88 sortie sud
    "Mende":            (44.5060,  3.4710),   # N88 contournement
    "Rodez":            (44.3660,  2.6050),   # RN88 échangeur nord

    # Ouest (points sur N171, N162, A81)
    "Châteaubriant":    (47.7200, -1.3550),   # N171 contournement
    "Mayenne":          (48.2980, -0.6330),   # N162 sortie
    "Laval":            (48.0850, -0.7340),   # A81 échangeur
    "Le Mans":          (48.0250,  0.2200),   # A28/A81 échangeur

    # Normandie / N12
    "Alençon":          (48.4450,  0.1150),   # N12 contournement
    "Argentan":         (48.7380, -0.0050),   # N26 échangeur
    "Dreux":            (48.7250,  1.3900),   # N12 contournement sud

    # Nord (points sur A1, A26, N2, N44)
    "Amiens":           (49.8700,  2.3350),   # A29/A16 échangeur
    "Albert":           (50.0050,  2.6350),   # D929/N29 contournement
    "Bapaume":          (50.1100,  2.8550),   # A1 sortie Bapaume
    "Cambrai":          (50.1900,  3.2100),   # A26 échangeur
    "Laon":             (49.5780,  3.6450),   # N2 contournement est
    "Soissons":         (49.3700,  3.3450),   # N2 contournement sud

    # Ardennes
    "Vouziers":         (49.3850,  4.6850),   # D946 contournement

    # Est (points sur A31, A4, N4)
    "Commercy":         (48.7550,  5.5700),   # N4 contournement
    "Nancy":            (48.7100,  6.2100),   # A31 échangeur sud
    "Verdun":           (49.1750,  5.3650),   # N3/A4 échangeur
    "Épinal":           (48.1850,  6.4350),   # N57 contournement
    "Chaumont":         (48.1050,  5.1200),   # N67 contournement

    # Centre / Champagne
    "Troyes":           (48.3100,  4.1000),   # A5/A26 échangeur
    "Orléans":          (47.9200,  1.9300),   # A10 échangeur nord

    # ── AJOUTS : axes Vosges ↔ ouest (N57/N4) ──
    "Vesoul":           (47.6240,  6.1550),   # N57/N19 contournement
    "Langres":          (47.8650,  5.3350),   # N19/A31 échangeur

    # ── AJOUTS : axes Champagne / nord-est ──
    "Reims-sud":        (49.2000,  4.0500),   # A4/A26 échangeur Reims-sud
    "Saint-Quentin":    (49.8400,  3.2800),   # A26/A29 échangeur

    # ── AJOUTS : axe nord ↔ ouest via Normandie (A29/A28) ──
    "Rouen":            (49.4430,  1.0990),   # A28/A29/A13 échangeur

    # ── AJOUTS : Bretagne / N12-N137 ──
    "Rennes":           (48.0830, -1.6800),   # N12/N137/N157 échangeur
    "Vitré":            (48.1240, -1.2100),   # A81 sortie

    # ── AJOUTS : axe N145/A20 (Cantal/Limousin ↔ ouest) ──
    "Limoges":          (45.8340,  1.2620),   # A20/N145 échangeur nord
    "La Souterraine":   (46.2370,  1.4870),   # N145 contournement
    "Bellac":           (46.1230,  1.0480),   # N147 contournement
    "Tulle":            (45.2650,  1.7690),   # A89 échangeur

    # ── AJOUTS : axe N10/N137 (Bretagne ↔ sud-ouest) ──
    "Poitiers":         (46.5800,  0.3400),   # A10/N147 échangeur
    "Niort":            (46.3230, -0.4640),   # A83/A10 échangeur
    "Angoulême":        (45.6480,  0.1560),   # N10 contournement

    # ── AJOUTS : axe N20/A20 (sud-ouest) ──
    "Cahors":           (44.4480,  1.4410),   # A20/N20 contournement
    "Brive":            (45.1590,  1.5320),   # A20/A89 échangeur

    # ── AJOUTS : axe Jura (N5/N57) Haute-Savoie ↔ Vosges ──
    "Champagnole":      (46.7450,  5.9130),   # N5 jurassienne
    "Pontarlier":       (46.9050,  6.3550),   # N57 contournement
}

# ==========================================
# AXES STRATÉGIQUES
# ==========================================

AXE_N12 = ["Dreux", "Alençon", "Mayenne", "Laval"]
AXE_N2  = ["Soissons", "Laon", "Cambrai"]

# Nouveaux axes : ordre = sens de parcours géographique
AXE_NORD_OUEST    = ["Saint-Quentin", "Amiens", "Rouen", "Alençon", "Mayenne"]
AXE_VOSGES_OUEST  = ["Vesoul", "Langres", "Troyes", "Orléans", "Le Mans"]
AXE_LIMOUSIN      = ["Tulle", "Limoges", "La Souterraine", "Poitiers"]
AXE_N88           = ["Puy-en-Velay", "Mende", "Rodez", "Cahors"]

RAYON_DETECTION_KM = 10        # détection auto par projection : strict pour éviter les faux positifs
RAYON_AXE_FORCE_KM = 45        # axes forcés : large pour couvrir les corridors qui font détour
MAX_WAYPOINTS      = 6         # max waypoints retournés (PTV gère mal les longues listes)


# ==========================================
# HAVERSINE
# ==========================================
def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ==========================================
# DISTANCE POINT → SEGMENT
# ==========================================
def _distance_point_to_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return _haversine(px, py, ax, ay)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    proj_lat = ax + t * dx
    proj_lon = ay + t * dy
    return _haversine(px, py, proj_lat, proj_lon)


# ==========================================
# DÉTECTION AXES
# ==========================================
def _is_east_west(lat_start, lon_start, lat_end, lon_end) -> bool:
    lat_moy = (lat_start + lat_end) / 2
    delta_lon = abs(lon_end - lon_start)
    delta_lat = abs(lat_end - lat_start)
    return (47.5 <= lat_moy <= 49.5
            and delta_lon > 2.0
            and delta_lon > delta_lat * 1.5)


def _is_north_axis(lat_start, lon_start, lat_end, lon_end) -> bool:
    """
    Trajet à composante nord ET nettement vers l'ouest.
    Resserré pour ne plus se déclencher sur Lille→Strasbourg ou PETIT FAYT→Italie.
    """
    lat_max = max(lat_start, lat_end)
    delta_lon = lon_end - lon_start  # signé : positif = vers l'est, négatif = vers l'ouest
    return lat_max >= 49.0 and abs(delta_lon) > 2.0 and (
        # extrémité ouest doit être vraiment à l'ouest
        min(lon_start, lon_end) <= 0.5
    )


def _is_nord_to_ouest(lat_start, lon_start, lat_end, lon_end) -> bool:
    """
    Détecte un trajet Nord (Hauts-de-France/Ardennes/Belgique est) ↔ Ouest (Bretagne/Normandie).
    Une extrémité doit être au nord-est, l'autre franchement à l'ouest, et le trajet doit
    être assez long pour justifier un détour par les corridors A26-A29.
    """
    def is_nord_est(lat, lon):
        return lat >= 49.5 and lon >= 3.5
    def is_ouest(lat, lon):
        return lon <= -0.5 and 47.0 <= lat <= 49.5
    if not ((is_nord_est(lat_start, lon_start) and is_ouest(lat_end, lon_end))
            or (is_nord_est(lat_end, lon_end) and is_ouest(lat_start, lon_start))):
        return False
    # Garde-fou : trajet assez long
    return _haversine(lat_start, lon_start, lat_end, lon_end) >= 400


def _is_vosges_to_ouest(lat_start, lon_start, lat_end, lon_end) -> bool:
    """
    Détecte un trajet Vosges/Est (longitude > 5.8) ↔ Ouest (longitude < -0.5).
    Couvre CORCIEUX, XERTIGNY, CLERVAL ↔ MAYENNE, BOUVRON, PONTIVY...
    """
    def is_est(lat, lon):
        return lon >= 5.8 and 47.0 <= lat <= 49.0
    def is_ouest(lat, lon):
        return lon <= -0.5 and 47.0 <= lat <= 49.0
    if not ((is_est(lat_start, lon_start) and is_ouest(lat_end, lon_end))
            or (is_est(lat_end, lon_end) and is_ouest(lat_start, lon_start))):
        return False
    return _haversine(lat_start, lon_start, lat_end, lon_end) >= 400


def _is_limousin_axis(lat_start, lon_start, lat_end, lon_end) -> bool:
    """
    Détecte un trajet Cantal/Aveyron/Limousin (sud du Massif Central) ↔ Normandie/Bretagne.
    Couvre RIOM ES MONTAGNES, ONET-LE-CHÂTEAU ↔ MAYENNE, BOUVRON, ISIGNY...
    """
    def is_sud(lat, lon):
        return 44.0 <= lat <= 45.7 and 1.5 <= lon <= 3.5
    def is_nord_ouest(lat, lon):
        return lat >= 47.5 and lon <= 0.0
    if not ((is_sud(lat_start, lon_start) and is_nord_ouest(lat_end, lon_end))
            or (is_sud(lat_end, lon_end) and is_nord_ouest(lat_start, lon_start))):
        return False
    return _haversine(lat_start, lon_start, lat_end, lon_end) >= 400


def _is_n88_axis(lat_start, lon_start, lat_end, lon_end) -> bool:
    """
    Détecte un trajet Loire/Auvergne (Saint-Étienne, Roanne) ↔ Sud-Ouest (Tarn-et-Garonne, Lot).
    Force le passage par la N88 gratuite (Le Puy, Mende, Rodez) au lieu de A89-A20.
    Couvre ANDREZIEUX → MONTAUBAN et trajets similaires.
    """
    def is_loire_auvergne(lat, lon):
        return 45.0 <= lat <= 46.2 and 3.5 <= lon <= 5.0
    def is_sud_ouest(lat, lon):
        return 43.5 <= lat <= 44.8 and 0.5 <= lon <= 2.5
    if not ((is_loire_auvergne(lat_start, lon_start) and is_sud_ouest(lat_end, lon_end))
            or (is_loire_auvergne(lat_end, lon_end) and is_sud_ouest(lat_start, lon_start))):
        return False
    return _haversine(lat_start, lon_start, lat_end, lon_end) >= 250


# ==========================================
# FONCTION PRINCIPALE
# ==========================================
def _appliquer_axe_force(nom_axe, liste_villes, villes_proches,
                         lat_start, lon_start, lat_end, lon_end):
    """Applique un axe forcé avec le rayon élargi RAYON_AXE_FORCE_KM."""
    lon_min = min(lon_start, lon_end)
    lon_max = max(lon_start, lon_end)
    lat_min = min(lat_start, lat_end)
    lat_max = max(lat_start, lat_end)
    # Marge : on accepte les villes légèrement en dehors du rectangle (max 0.5° = ~50 km)
    marge = 0.5

    for ville in liste_villes:
        if any(v[0] == ville for v in villes_proches):
            continue
        if ville not in VILLES_JALONS:
            print(f"      ⚠️  {nom_axe} : ville '{ville}' inconnue dans VILLES_JALONS")
            continue
        vlat, vlon = VILLES_JALONS[ville]
        # Garde-fou : la ville doit être dans le rectangle élargi départ↔arrivée
        if vlon < lon_min - marge or vlon > lon_max + marge:
            print(f"      🚷 {nom_axe} hors zone : {ville} (lon {vlon:.2f} hors [{lon_min:.2f},{lon_max:.2f}])")
            continue
        if vlat < lat_min - marge or vlat > lat_max + marge:
            print(f"      🚷 {nom_axe} hors zone : {ville} (lat {vlat:.2f} hors [{lat_min:.2f},{lat_max:.2f}])")
            continue
        dist_seg = _distance_point_to_segment(
            vlat, vlon,
            lat_start, lon_start,
            lat_end, lon_end
        )
        if dist_seg <= RAYON_AXE_FORCE_KM:
            dist_from_start = _haversine(lat_start, lon_start, vlat, vlon)
            villes_proches.append((ville, vlat, vlon, dist_from_start, dist_seg))
            print(f"      🛣️  {nom_axe} forcé : {ville} ({dist_seg:.0f}km du segment)")
        else:
            print(f"      🛣️  {nom_axe} ignoré : {ville} ({dist_seg:.0f}km > {RAYON_AXE_FORCE_KM}km)")


def detecter_villes_jalons(lat_start, lon_start, lat_end, lon_end) -> list:
    print(f"      🧭 Jalons: ({lat_start:.4f}, {lon_start:.4f}) → ({lat_end:.4f}, {lon_end:.4f})")
    villes_proches = []

    # 1. Détection auto par proximité au segment direct (rayon strict 10 km)
    lon_min = min(lon_start, lon_end)
    lon_max = max(lon_start, lon_end)
    lat_min = min(lat_start, lat_end)
    lat_max = max(lat_start, lat_end)
    marge = 0.5
    for ville, (vlat, vlon) in VILLES_JALONS.items():
        # Filtre rectangle : la ville doit être (à peu près) entre départ et arrivée
        if vlon < lon_min - marge or vlon > lon_max + marge:
            continue
        if vlat < lat_min - marge or vlat > lat_max + marge:
            continue
        dist = _distance_point_to_segment(
            vlat, vlon,
            lat_start, lon_start,
            lat_end, lon_end
        )
        if dist <= RAYON_DETECTION_KM:
            dist_from_start = _haversine(lat_start, lon_start, vlat, vlon)
            villes_proches.append((ville, vlat, vlon, dist_from_start, dist))

    # 2. Axes forcés (rayon élargi pour couvrir les corridors en détour)
    use_nord_ouest    = _is_nord_to_ouest(lat_start, lon_start, lat_end, lon_end)
    use_vosges_ouest  = _is_vosges_to_ouest(lat_start, lon_start, lat_end, lon_end)
    use_limousin      = _is_limousin_axis(lat_start, lon_start, lat_end, lon_end)
    use_n88           = _is_n88_axis(lat_start, lon_start, lat_end, lon_end)

    if use_nord_ouest:
        _appliquer_axe_force("NORD-OUEST", AXE_NORD_OUEST, villes_proches,
                             lat_start, lon_start, lat_end, lon_end)

    if use_vosges_ouest:
        _appliquer_axe_force("VOSGES-OUEST", AXE_VOSGES_OUEST, villes_proches,
                             lat_start, lon_start, lat_end, lon_end)

    if use_limousin:
        _appliquer_axe_force("LIMOUSIN", AXE_LIMOUSIN, villes_proches,
                             lat_start, lon_start, lat_end, lon_end)

    if use_n88:
        _appliquer_axe_force("N88", AXE_N88, villes_proches,
                             lat_start, lon_start, lat_end, lon_end)

    # N12/N2 : seulement si aucun axe spécifique ne s'est déclenché
    if not (use_nord_ouest or use_vosges_ouest or use_limousin or use_n88):
        if _is_east_west(lat_start, lon_start, lat_end, lon_end):
            _appliquer_axe_force("N12", AXE_N12, villes_proches,
                                 lat_start, lon_start, lat_end, lon_end)
        if _is_north_axis(lat_start, lon_start, lat_end, lon_end):
            _appliquer_axe_force("N2", AXE_N2, villes_proches,
                                 lat_start, lon_start, lat_end, lon_end)

    # 3. Anti-retour-en-arrière + anti-doublon-extrémité
    dist_total = _haversine(lat_start, lon_start, lat_end, lon_end)
    villes_filtrees = []
    for v in villes_proches:
        ville, vlat, vlon, dist_start, dist_seg = v
        dist_to_end = _haversine(vlat, vlon, lat_end, lon_end)
        # 3a. Le waypoint doit être "entre" départ et arrivée
        if dist_start + dist_to_end > dist_total * 1.4:
            print(f"      🚫 {ville} écarté (hors corridor : {dist_start:.0f}+{dist_to_end:.0f} > {dist_total*1.4:.0f})")
            continue
        # 3b. Le waypoint doit être assez loin des extrémités (sinon inutile)
        seuil_extremite = max(40, dist_total * 0.05)
        if dist_start < seuil_extremite:
            print(f"      🚫 {ville} écarté (trop proche du départ : {dist_start:.0f}km)")
            continue
        if dist_to_end < seuil_extremite:
            print(f"      🚫 {ville} écarté (trop proche de l'arrivée : {dist_to_end:.0f}km)")
            continue
        villes_filtrees.append(v)

    # 4. Tri par distance depuis le départ (ordre de parcours)
    villes_filtrees.sort(key=lambda x: x[3])

    # 5. Anti-zigzag : retirer les waypoints qui font reculer après être avancé
    # Si un waypoint à dist_start = X est suivi d'un waypoint à dist_start = Y >> X
    # avec un saut > 200km, c'est probablement que le premier était hors corridor
    if len(villes_filtrees) >= 2:
        cleaned = [villes_filtrees[0]]
        for i in range(1, len(villes_filtrees)):
            prev = cleaned[-1]
            curr = villes_filtrees[i]
            saut_progression = curr[3] - prev[3]
            # Vérifier que les deux waypoints sont "alignés" : la distance entre eux
            # doit être proche de la différence de leurs progressions (= sur le même axe)
            dist_inter = _haversine(prev[1], prev[2], curr[1], curr[2])
            # Si dist_inter > 1.5 * saut_progression, ils ne sont pas alignés
            if saut_progression > 200 and dist_inter > saut_progression * 1.3:
                print(f"      🌀 {prev[0]} retiré (zigzag : saut {dist_inter:.0f}km vs progression {saut_progression:.0f}km)")
                cleaned[-1] = curr
            else:
                cleaned.append(curr)
        villes_filtrees = cleaned

    # 6. Élagage : si trop de waypoints, garder ceux les plus proches du segment
    if len(villes_filtrees) > MAX_WAYPOINTS:
        villes_filtrees.sort(key=lambda x: x[4])
        villes_filtrees = villes_filtrees[:MAX_WAYPOINTS]
        villes_filtrees.sort(key=lambda x: x[3])
        print(f"      ✂️  Élagage : limité à {MAX_WAYPOINTS} waypoints")

    # 7. Conversion en strings "lat, lon"
    waypoints = []
    for ville, vlat, vlon, dist_start, dist_seg in villes_filtrees:
        waypoints.append(f"{vlat}, {vlon}")
        print(f"      📌 Jalon retenu : {ville} ({dist_seg:.0f}km du trajet, {dist_start:.0f}km du départ)")

    return waypoints
