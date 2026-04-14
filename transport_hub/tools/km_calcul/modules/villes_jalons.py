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
    "Issoire":          (45.5440,  3.2490),   # A75 - ancre axe Massif Central → Nord

    # Ouest (points sur N171, N162, A81)
    "Châteaubriant":    (47.7200, -1.3550),   # N171 contournement
    "Mayenne":          (48.2980, -0.6330),   # N162 sortie
    "Laval":            (48.0850, -0.7340),   # A81 échangeur
    "Le Mans":          (48.0250,  0.2200),   # A28/A81 échangeur
    "Tours":            (47.3940,  0.6860),   # A11/A85 carrefour Centre→Ouest
    "Angers":           (47.4730, -0.5540),   # A11/A87 pivot Grand Ouest

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

    # Normandie → Nord-Est (axes gratuits N154/N31 pour éviter autoroutes Paris)
    "Évreux":           (49.0270,  1.1510),   # N154 axe gratuit nord-ouest Paris
    "Beauvais":         (49.4300,  2.0820),   # N31 axe gratuit
    "Compiègne":        (49.4150,  2.8240),   # N31/A1 axe gratuit
    "Chartres":         (48.4480,  1.4890),   # N10/N23 anti-détour Paris pour Vosges→Ouest

    # Ardennes / Avesnois
    "Vouziers":         (49.3850,  4.6850),   # D946 contournement
    "Hirson":           (49.9230,  4.0830),   # N2/D1029 - évite A26 pour Ardennes
    "Avesnes-sur-Helpe":(50.1240,  3.9310),   # D932 Avesnois - axe direct Cambrai→Ardennes
    "Maubeuge":         (50.2790,  3.9730),   # N2 - axe Belgique évite A26
    "Sedan":            (49.7030,  4.9400),   # N43 - axe Lorraine→Ardennes

    # Est (points sur A31, A4, N4)
    "Commercy":         (48.7550,  5.5700),   # N4 contournement
    "Nancy":            (48.7100,  6.2100),   # A31 échangeur sud
    "Metz":             (49.1200,  6.1770),   # A31/A4 incontournable Est→Nord
    "Verdun":           (49.1750,  5.3650),   # N3/A4 échangeur
    "Épinal":           (48.1850,  6.4350),   # N57 contournement
    "Chaumont":         (48.1050,  5.1200),   # N67 contournement

    # Centre / Champagne
    "Troyes":           (48.3100,  4.1000),   # A5/A26 échangeur
    "Orléans":          (47.9200,  1.9300),   # A10 échangeur nord
    "Châlons-en-Champagne": (48.9580, 4.3660), # A26/A4 carrefour Champagne

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
AXE_VOSGES_OUEST  = ["Vesoul", "Langres", "Troyes", "Orléans", "Chartres", "Le Mans"]
AXE_LIMOUSIN      = ["Tulle", "Limoges", "La Souterraine", "Poitiers"]
AXE_N88           = ["Puy-en-Velay", "Mende", "Rodez", "Cahors"]

# Axe Massif Central est (Aveyron/Cantal) → Grand Ouest : force A75 au lieu de l'A20 Limoges
AXE_MASSIF_CENTRAL_OUEST = ["Issoire", "Tours", "Angers"]

# Axe Ardennes/Avesnois : force les routes locales pour les Ardennes et le Hainaut
AXE_ARDENNES_AVESNOIS = ["Hirson", "Avesnes-sur-Helpe", "Maubeuge"]

# Axe Ouest (Bretagne/Normandie) → Nord-Est (Ardennes/Hainaut) : force N154/N31 gratuits
AXE_OUEST_NORD_EST = ["Évreux", "Beauvais", "Compiègne"]

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
        min(lon_start, lon_end) <= 0.5
    )


def _is_nord_to_ouest(lat_start, lon_start, lat_end, lon_end) -> bool:
    """
    Détecte un trajet Nord (Hauts-de-France/Ardennes/Belgique est) ↔ Ouest (Bretagne/Normandie).
    """
    def is_nord_est(lat, lon):
        return lat >= 49.0 and lon >= 3.5

    def is_ouest(lat, lon):
        return lon <= -0.5 and 47.0 <= lat <= 49.5

    if not ((is_nord_est(lat_start, lon_start) and is_ouest(lat_end, lon_end))
            or (is_nord_est(lat_end, lon_end) and is_ouest(lat_start, lon_start))):
        return False
    return _haversine(lat_start, lon_start, lat_end, lon_end) >= 350


def _is_vosges_to_ouest(lat_start, lon_start, lat_end, lon_end) -> bool:
    """
    Détecte un trajet Vosges/Est (longitude > 5.8) ↔ Ouest (longitude < -0.5).
    Couvre CORCIEUX, XERTIGNY, CLERVAL ↔ MAYENNE, BOUVRON, PONTIVY, ISIGNY...
    """
    def is_est(lat, lon):
        return lon >= 5.8 and 47.0 <= lat <= 49.0

    def is_ouest(lat, lon):
        return lon <= -0.5 and 47.0 <= lat <= 49.5

    if not ((is_est(lat_start, lon_start) and is_ouest(lat_end, lon_end))
            or (is_est(lat_end, lon_end) and is_ouest(lat_start, lon_start))):
        return False
    return _haversine(lat_start, lon_start, lat_end, lon_end) >= 350


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
    return _haversine(lat_start, lon_start, lat_end, lon_end) >= 350


def _is_massif_central_to_ouest(lat_start, lon_start, lat_end, lon_end) -> bool:
    """
    Détecte un trajet depuis le Massif Central est (Aveyron, Cantal, Lozère : lon > 2.0)
    vers le Grand Ouest (lon < 0.5). Force l'axe A75 (Issoire) plutôt que l'A20 (Limoges).
    Couvre ONET-LE-CHÂTEAU, RIOM-ES-MONTAGNES, MENDE ↔ MAYENNE, ISIGNY, L'HERMITAGE, RETIERS...
    """
    def is_massif_est(lat, lon):
        return 44.0 <= lat <= 46.0 and 2.0 <= lon <= 4.5

    def is_grand_ouest(lat, lon):
        return lon <= 0.5 and lat >= 47.0

    if not ((is_massif_est(lat_start, lon_start) and is_grand_ouest(lat_end, lon_end))
            or (is_massif_est(lat_end, lon_end) and is_grand_ouest(lat_start, lon_start))):
        return False
    return _haversine(lat_start, lon_start, lat_end, lon_end) >= 350



def _is_ouest_to_nord_est(lat_start, lon_start, lat_end, lon_end) -> bool:
    """
    Détecte un trajet Grand Ouest (lon < 0) ↔ Nord-Est/Ardennes (lat >= 49.5, lon >= 3.0).
    Force les axes N154/N31 gratuits (Évreux, Beauvais, Compiègne) pour éviter
    que PTV choisisse les autoroutes payantes autour de Paris (A13/A14/A86).
    Couvre DOMFRONT, BOUVRON, CRAON, RETIERS, VITRÉ ↔ PETIT FAYT, ROUVROY, CUINCY...
    """
    def is_ouest(lat, lon):
        return lon < 0.0 and 47.0 <= lat <= 50.5

    def is_nord_est(lat, lon):
        return lat >= 49.5 and lon >= 3.0

    if not ((is_ouest(lat_start, lon_start) and is_nord_est(lat_end, lon_end))
            or (is_ouest(lat_end, lon_end) and is_nord_est(lat_start, lon_start))):
        return False
    return _haversine(lat_start, lon_start, lat_end, lon_end) >= 300


def _is_ardennes_avesnois(lat_start, lon_start, lat_end, lon_end) -> bool:
    """
    Détecte un trajet traversant les Ardennes/Avesnois (zone 49.5-50.5 lat, 3.5-5.5 lon).
    Force les routes locales (N2/D1029) au lieu de l'A26 payante.
    Couvre routes vers/depuis ROUVROY SUR AUDRY, PETIT FAYT, CUINCY...
    Une extrémité doit être en zone Ardennes/Avesnois, l'autre en dehors.
    """
    def is_ardennes(lat, lon):
        return 49.5 <= lat <= 50.6 and 3.5 <= lon <= 5.5

    def is_outside_ardennes(lat, lon):
        # Soit à l'ouest (Bretagne/Normandie/Île-de-France), soit au sud/est (Lorraine, Centre)
        return not is_ardennes(lat, lon)

    if not ((is_ardennes(lat_start, lon_start) and is_outside_ardennes(lat_end, lon_end))
            or (is_ardennes(lat_end, lon_end) and is_outside_ardennes(lat_start, lon_start))):
        return False
    # Garde-fou: ne pas déclencher pour des trajets ultra-courts intra-zone
    return _haversine(lat_start, lon_start, lat_end, lon_end) >= 80


def _is_n88_axis(lat_start, lon_start, lat_end, lon_end) -> bool:
    """
    Détecte un trajet Loire/Auvergne (Saint-Étienne, Roanne) ↔ Sud-Ouest (Tarn-et-Garonne, Lot).
    Force le passage par la N88 gratuite (Le Puy, Mende, Rodez) au lieu de A89-A20.
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
# JALONS CONDITIONNELS
# ==========================================
def _jalon_autorise(ville, lon_start, lon_end, lat_start=None, lat_end=None) -> bool:
    lon_min = min(lon_start, lon_end)
    lon_max = max(lon_start, lon_end)

    if ville in ("Amiens", "Albert", "Rouen"):
        if lon_min < 0.0:
            return False

    if ville == "Saint-Quentin":
        if lat_start is not None and lat_end is not None:
            neither_is_north_east = (
                not (lon_start > 4.0 and lat_start > 49.5) and
                not (lon_end   > 4.0 and lat_end   > 49.5)
            )
            if neither_is_north_east and lon_min < 0.0:
                return False
            if max(lat_start, lat_end) < 50.2 and lon_max < 4.0:
                return False

    if ville == "Dreux":
        if lon_max > 4.0:
            return False

    return True


def _is_lorraine_to_belgique(lat_start, lon_start, lat_end, lon_end) -> bool:
    """
    Détecte un trajet depuis Alsace/Lorraine (lon > 6.0) vers Belgique/Pays-Bas.
    Force Nancy → A31 nord → Metz → Thionville → Belgique.
    """
    def is_lorraine(lat, lon):
        return lon >= 6.0 and 47.5 <= lat <= 49.5

    def is_belgique(lat, lon):
        return lat >= 49.5 and lon < 7.5

    return ((is_lorraine(lat_start, lon_start) and is_belgique(lat_end, lon_end))
            or (is_lorraine(lat_end, lon_end) and is_belgique(lat_start, lon_start)))


def _is_idf_to_ouest(lat_start, lon_start, lat_end, lon_end) -> bool:
    """
    Détecte un trajet depuis IDF/Picardie/Nord (lon 1.5-5.0, lat 48-50.5)
    vers l'Ouest (lon < -0.5). Force le passage par Mayenne/Le Mans.
    """
    def is_idf_nord(lat, lon):
        return 1.5 <= lon <= 5.0 and 48.0 <= lat <= 50.5

    def is_ouest(lat, lon):
        return lon < -0.5 and 47.0 <= lat <= 49.5

    return ((is_idf_nord(lat_start, lon_start) and is_ouest(lat_end, lon_end))
            or (is_idf_nord(lat_end, lon_end) and is_ouest(lat_start, lon_start)))


# Axes pour les nouveaux détecteurs
AXE_LORRAINE_BELGIQUE = ["Nancy", "Metz", "Sedan"]
AXE_IDF_OUEST         = ["Le Mans", "Mayenne"]


# ==========================================
# FONCTION PRINCIPALE
# ==========================================
def _appliquer_axe_force(nom_axe, liste_villes, villes_proches,
                         lat_start, lon_start, lat_end, lon_end,
                         rayon=None):
    """Applique un axe forcé avec le rayon élargi RAYON_AXE_FORCE_KM (ou rayon custom)."""
    if rayon is None:
        rayon = RAYON_AXE_FORCE_KM
    lon_min = min(lon_start, lon_end)
    lon_max = max(lon_start, lon_end)
    lat_min = min(lat_start, lat_end)
    lat_max = max(lat_start, lat_end)
    marge = 0.5

    for ville in liste_villes:
        if any(v[0] == ville for v in villes_proches):
            continue
        if ville not in VILLES_JALONS:
            print(f"      ⚠️  {nom_axe} : ville '{ville}' inconnue dans VILLES_JALONS")
            continue
        if not _jalon_autorise(ville, lon_start, lon_end, lat_start, lat_end):
            print(f"      🚫 {nom_axe} bloqué (zone): {ville}")
            continue
        vlat, vlon = VILLES_JALONS[ville]

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
        if dist_seg <= rayon:
            dist_from_start = _haversine(lat_start, lon_start, vlat, vlon)
            villes_proches.append((ville, vlat, vlon, dist_from_start, dist_seg))
            print(f"      🛣️  {nom_axe} forcé : {ville} ({dist_seg:.0f}km du segment)")
        else:
            print(f"      🛣️  {nom_axe} ignoré : {ville} ({dist_seg:.0f}km > {rayon}km)")


def detecter_villes_jalons(lat_start, lon_start, lat_end, lon_end) -> list:
    print(f"      🧭 Jalons: ({lat_start:.4f}, {lon_start:.4f}) → ({lat_end:.4f}, {lon_end:.4f})")
    villes_proches = []

    # 1. Calcul des flags d'axes (en premier, pour conditionner la detection auto)
    use_nord_ouest          = _is_nord_to_ouest(lat_start, lon_start, lat_end, lon_end)
    use_vosges_ouest        = _is_vosges_to_ouest(lat_start, lon_start, lat_end, lon_end)
    use_limousin            = _is_limousin_axis(lat_start, lon_start, lat_end, lon_end)
    use_massif_central      = _is_massif_central_to_ouest(lat_start, lon_start, lat_end, lon_end)
    use_ouest_nord_est      = _is_ouest_to_nord_est(lat_start, lon_start, lat_end, lon_end)
    use_ardennes            = _is_ardennes_avesnois(lat_start, lon_start, lat_end, lon_end)
    use_n88                 = _is_n88_axis(lat_start, lon_start, lat_end, lon_end)
    use_lorraine_belgique   = _is_lorraine_to_belgique(lat_start, lon_start, lat_end, lon_end)
    use_idf_ouest           = _is_idf_to_ouest(lat_start, lon_start, lat_end, lon_end)

    # Jalons exclus de la detection auto selon le contexte.
    # Si l'axe MASSIF_CENTRAL est actif, les jalons de l'A20/Limousin sont contre-productifs :
    # leur presence incite PTV a rester sur l'A20 au lieu de monter par l'A75 (Issoire->Tours).
    JALONS_EXCLUS_AUTO = set()
    if use_massif_central:
        JALONS_EXCLUS_AUTO.update({"Tulle", "Limoges", "Bellac", "La Souterraine", "Poitiers", "Niort"})

    # 2. Detection auto par proximite au segment direct (rayon strict 10 km)
    lon_min = min(lon_start, lon_end)
    lon_max = max(lon_start, lon_end)
    lat_min = min(lat_start, lat_end)
    lat_max = max(lat_start, lat_end)
    marge = 0.5

    for ville, (vlat, vlon) in VILLES_JALONS.items():
        if ville in JALONS_EXCLUS_AUTO:
            continue
        if not _jalon_autorise(ville, lon_start, lon_end, lat_start, lat_end):
            continue
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

    # 3. Axes forces (rayon elargi pour couvrir les corridors en detour)

    if use_nord_ouest:
        _appliquer_axe_force("NORD-OUEST", AXE_NORD_OUEST, villes_proches,
                             lat_start, lon_start, lat_end, lon_end)

    if use_vosges_ouest:
        _appliquer_axe_force("VOSGES-OUEST", AXE_VOSGES_OUEST, villes_proches,
                             lat_start, lon_start, lat_end, lon_end)

    if use_limousin and not use_massif_central:
        # LIMOUSIN désactivé si MASSIF_CENTRAL actif : évite de forcer l'A20/Limoges
        # quand on veut l'A75 (Issoire) pour les routes Aveyron/Cantal → Grand Ouest
        _appliquer_axe_force("LIMOUSIN", AXE_LIMOUSIN, villes_proches,
                             lat_start, lon_start, lat_end, lon_end)

    if use_massif_central:
        _appliquer_axe_force("MASSIF-CENTRAL-OUEST", AXE_MASSIF_CENTRAL_OUEST, villes_proches,
                             lat_start, lon_start, lat_end, lon_end)

    if use_ouest_nord_est:
        _appliquer_axe_force("OUEST-NORD-EST", AXE_OUEST_NORD_EST, villes_proches,
                             lat_start, lon_start, lat_end, lon_end)

    if use_ardennes:
        _appliquer_axe_force("ARDENNES-AVESNOIS", AXE_ARDENNES_AVESNOIS, villes_proches,
                             lat_start, lon_start, lat_end, lon_end, rayon=30)

    if use_n88:
        _appliquer_axe_force("N88", AXE_N88, villes_proches,
                             lat_start, lon_start, lat_end, lon_end)

    if use_lorraine_belgique:
        # Rayon élargi à 70km : Nancy/Metz peuvent être un crochet volontaire
        _appliquer_axe_force("LORRAINE-BELGIQUE", AXE_LORRAINE_BELGIQUE, villes_proches,
                             lat_start, lon_start, lat_end, lon_end, rayon=70)

    if use_idf_ouest:
        _appliquer_axe_force("IDF-OUEST", AXE_IDF_OUEST, villes_proches,
                             lat_start, lon_start, lat_end, lon_end)

    # N12/N2 : seulement si aucun axe spécifique ne s'est déclenché
    if not (use_nord_ouest or use_vosges_ouest or use_limousin or use_massif_central
            or use_ouest_nord_est or use_ardennes or use_n88 or use_lorraine_belgique or use_idf_ouest):
        lat_max_traj = max(lat_start, lat_end)
        lon_min_traj = min(lon_start, lon_end)
        n12_n2_safe = (lat_max_traj < 49.0) and (lon_min_traj > -0.3)
        if n12_n2_safe:
            if _is_east_west(lat_start, lon_start, lat_end, lon_end):
                _appliquer_axe_force("N12", AXE_N12, villes_proches,
                                     lat_start, lon_start, lat_end, lon_end)
            if _is_north_axis(lat_start, lon_start, lat_end, lon_end):
                _appliquer_axe_force("N2", AXE_N2, villes_proches,
                                     lat_start, lon_start, lat_end, lon_end)
        else:
            print(f"      ⏭️  N12/N2 désactivés (lat_max={lat_max_traj:.2f}, lon_min={lon_min_traj:.2f})")

    # 4. Anti-retour-en-arriere + anti-doublon-extremite
    dist_total = _haversine(lat_start, lon_start, lat_end, lon_end)
    villes_filtrees = []
    for v in villes_proches:
        ville, vlat, vlon, dist_start, dist_seg = v
        dist_to_end = _haversine(vlat, vlon, lat_end, lon_end)
        if dist_start + dist_to_end > dist_total * 1.4:
            print(f"      🚫 {ville} écarté (hors corridor : {dist_start:.0f}+{dist_to_end:.0f} > {dist_total*1.4:.0f})")
            continue
        seuil_extremite = max(40, dist_total * 0.05)
        if dist_start < seuil_extremite:
            print(f"      🚫 {ville} écarté (trop proche du départ : {dist_start:.0f}km)")
            continue
        if dist_to_end < seuil_extremite:
            print(f"      🚫 {ville} écarté (trop proche de l'arrivée : {dist_to_end:.0f}km)")
            continue
        villes_filtrees.append(v)

    # 5. Tri par distance depuis le depart (ordre de parcours)
    villes_filtrees.sort(key=lambda x: x[3])

    # 6. Anti-zigzag
    if len(villes_filtrees) >= 2:
        cleaned = [villes_filtrees[0]]
        for i in range(1, len(villes_filtrees)):
            prev = cleaned[-1]
            curr = villes_filtrees[i]
            saut_progression = curr[3] - prev[3]
            dist_inter = _haversine(prev[1], prev[2], curr[1], curr[2])
            if saut_progression > 200 and dist_inter > saut_progression * 1.3:
                print(f"      🌀 {prev[0]} retiré (zigzag : saut {dist_inter:.0f}km vs progression {saut_progression:.0f}km)")
                cleaned[-1] = curr
            else:
                cleaned.append(curr)
        villes_filtrees = cleaned

    # 7. Elagage : si trop de waypoints, garder ceux les plus proches du segment
    if len(villes_filtrees) > MAX_WAYPOINTS:
        villes_filtrees.sort(key=lambda x: x[4])
        villes_filtrees = villes_filtrees[:MAX_WAYPOINTS]
        villes_filtrees.sort(key=lambda x: x[3])
        print(f"      ✂️  Élagage : limité à {MAX_WAYPOINTS} waypoints")

    # 8. Conversion en strings "lat, lon"
    waypoints = []
    for ville, vlat, vlon, dist_start, dist_seg in villes_filtrees:
        waypoints.append(f"{vlat}, {vlon}")
        print(f"      📌 Jalon retenu : {ville} ({dist_seg:.0f}km du trajet, {dist_start:.0f}km du départ)")

    return waypoints
