"""
carte_pays.py — Nouvelle carte "par pays" (km + péages ventilés par pays traversé).

- construire_url_carte() : lien "Voir carte" écrit dans l'Excel, vers la page Streamlit Carte_Pays
- calculer_route_pays()  : appel PTV avec POLYLINE + BORDER_EVENTS + TOLL_COSTS, découpage par pays

Ne modifie rien de l'existant (ptv_router_km, map_server_client, serveur carte).
"""

import os
import json
import math
from urllib.parse import urlencode

import requests

# ============================================================
# CONFIGURATION
# ============================================================
# URL publique de l'app Streamlit (Render). Si vide -> run_km.py garde l'ancienne carte.
APP_BASE_URL = os.getenv("APP_BASE_URL", "").rstrip("/")

# Chemin URL de la page = nom du fichier sans préfixe numérique ni emoji
# pages/Carte_Pays.py  ->  /Carte_Pays
CARTE_PATH = "Carte_Pays"

ROUTING_URL = "https://api.myptv.com/routing/v1/routes"
PROFIL_VEHICULE = os.getenv("PTV_PROFILE", "EUR_TRAILER_TRUCK")  # aligne sur ptv_router_km si différent
DEVISE = "EUR"
TIMEOUT = 60
MAX_POINTS_SEGMENT = 500


# ============================================================
# URL "Voir carte"
# ============================================================
def construire_url_carte(origin, dest, coords_origin, coords_dest, peage=False, super_pref=False):
    """Retourne l'URL de la page Carte_Pays, ou "" si APP_BASE_URL n'est pas configurée."""
    if not APP_BASE_URL or not coords_origin or not coords_dest:
        return ""
    params = {
        "o": origin,
        "d": dest,
        "lo": f"{float(coords_origin[0]):.6f},{float(coords_origin[1]):.6f}",
        "ld": f"{float(coords_dest[0]):.6f},{float(coords_dest[1]):.6f}",
        "p": "1" if peage else "0",
        "sp": "1" if super_pref else "0",
    }
    return f"{APP_BASE_URL}/{CARTE_PATH}?{urlencode(params)}"


# ============================================================
# Clé API (variable d'env, sinon reprise depuis ptv_router_km)
# ============================================================
def _api_key():
    cle = os.getenv("PTV_API_KEY", "")
    if cle:
        return cle
    try:
        from modules import ptv_router_km as r
        for nom in ("PTV_API_KEY", "API_KEY", "PTV_KEY", "APIKEY"):
            if getattr(r, nom, None):
                return getattr(r, nom)
    except Exception:
        pass
    return ""


# ============================================================
# Waypoints (format tolérant : tuple, liste, dict, "lat,lon")
# ============================================================
def normaliser_waypoint(w):
    try:
        if isinstance(w, dict):
            lat = w.get("lat", w.get("latitude"))
            lon = w.get("lon", w.get("lng", w.get("longitude")))
            return (float(lat), float(lon))
        if isinstance(w, (list, tuple)) and len(w) >= 2:
            return (float(w[0]), float(w[1]))
        if isinstance(w, str) and "," in w:
            a, b = w.split(",")[:2]
            return (float(a), float(b))
    except Exception:
        pass
    return None


# ============================================================
# Appel PTV
# ============================================================
def appeler_ptv(lat1, lon1, lat2, lon2, waypoints=None, prohibited_countries=None, peage=True):
    results = ["POLYLINE", "WAYPOINT_EVENTS", "BORDER_EVENTS"]
    if peage:
        results.append("TOLL_COSTS")

    params = [("waypoints", f"{lat1},{lon1}")]
    for w in waypoints or []:
        p = normaliser_waypoint(w)
        if p:
            params.append(("waypoints", f"{p[0]},{p[1]}"))
    params.append(("waypoints", f"{lat2},{lon2}"))
    params += [
        ("profile", PROFIL_VEHICULE),
        ("results", ",".join(results)),
        ("options[currency]", DEVISE),
    ]
    if prohibited_countries:
        params.append(("options[prohibitedCountries]", ",".join(prohibited_countries)))

    r = requests.get(ROUTING_URL, params=params, headers={"apiKey": _api_key()}, timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"PTV {r.status_code} : {r.text[:300]}")
    return r.json()


# ============================================================
# Parsing
# ============================================================
def _montant(obj):
    if not isinstance(obj, dict):
        return 0.0
    for k in ("convertedPrice", "price"):
        v = obj.get(k)
        if isinstance(v, dict) and "price" in v:
            return float(v["price"] or 0)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _peages_par_pays(data):
    costs = ((data.get("toll") or {}).get("costs")) or {}
    res = {}
    for c in costs.get("countries", []) or []:
        cc = c.get("countryCode") or "??"
        res[cc] = res.get(cc, 0.0) + _montant(c)
    total = _montant(costs) or sum(res.values())
    return {k: round(v, 2) for k, v in res.items()}, round(total, 2)


def _est_frontiere(ev):
    return "border" in ev or ev.get("eventType") == "BORDER_EVENT"


def _est_waypoint(ev):
    return "waypoint" in ev or ev.get("eventType") == "WAYPOINT_EVENT"


def _pays_apres_frontiere(ev):
    b = ev.get("border") or {}
    for k in ("toCountryCode", "countryCodeAfter", "enteredCountryCode", "entryCountryCode", "countryCode"):
        if b.get(k):
            return b[k]
    return ev.get("countryCode")


def _haversine(lon1, lat1, lon2, lat2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def _lire_polyline(data):
    p = data.get("polyline")
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            return []
    if isinstance(p, dict):
        return [[float(c[0]), float(c[1])] for c in p.get("coordinates", [])]
    return []


def _alleger(points):
    if len(points) > MAX_POINTS_SEGMENT:
        pas = math.ceil(len(points) / MAX_POINTS_SEGMENT)
        pts = points[::pas]
        if pts[-1] != points[-1]:
            pts.append(points[-1])
        points = pts
    return [[round(x, 5), round(y, 5)] for x, y in points]


def analyser(data, peage=True):
    distance_m = float(data.get("distance", 0))
    events = sorted(data.get("events", []) or [], key=lambda e: e.get("distanceFromStart", 0))

    pays_depart = next((ev.get("countryCode") for ev in events if _est_waypoint(ev) and ev.get("countryCode")), None)
    pays_depart = pays_depart or (events[0].get("countryCode") if events else None) or "??"

    frontieres, courant = [], pays_depart
    for ev in events:
        if not _est_frontiere(ev):
            continue
        vers = _pays_apres_frontiere(ev) or courant
        if vers == courant:
            continue
        frontieres.append({"d": float(ev.get("distanceFromStart", 0)), "de": courant, "vers": vers,
                           "lat": ev.get("latitude"), "lon": ev.get("longitude")})
        courant = vers

    bornes = [0.0] + [f["d"] for f in frontieres] + [distance_m]
    pays_seq = [pays_depart] + [f["vers"] for f in frontieres]
    intervalles = [(pays_seq[i], bornes[i], bornes[i + 1]) for i in range(len(pays_seq))]

    # Découpage du tracé aux frontières
    coords = _lire_polyline(data)
    morceaux = [[] for _ in intervalles]
    if len(coords) >= 2:
        cumul = [0.0]
        for a, b in zip(coords, coords[1:]):
            cumul.append(cumul[-1] + _haversine(a[0], a[1], b[0], b[1]))
        echelle = distance_m / cumul[-1] if cumul[-1] > 0 else 1.0
        j = 0
        morceaux[0].append(coords[0])
        for i in range(1, len(coords)):
            d = cumul[i] * echelle
            while j < len(intervalles) - 1 and d >= intervalles[j][2]:
                morceaux[j].append(coords[i])
                if frontieres[j]["lat"] is None or frontieres[j]["lon"] is None:
                    frontieres[j]["lon"], frontieres[j]["lat"] = coords[i]
                j += 1
                morceaux[j].append(coords[i])
            if morceaux[j][-1] != coords[i]:
                morceaux[j].append(coords[i])

    segments, km_pays = [], {}
    for (pays, debut, fin), pts in zip(intervalles, morceaux):
        if fin - debut < 50:
            continue
        km = (fin - debut) / 1000
        km_pays[pays] = km_pays.get(pays, 0.0) + km
        segments.append({"pays": pays, "km": round(km, 1), "coords": _alleger(pts) if len(pts) >= 2 else []})

    peage_pays, peage_total = _peages_par_pays(data) if peage else ({}, 0.0)

    return {
        "km_total": round(distance_m / 1000, 1),
        "duree_h": round(float(data.get("travelTime", 0)) / 3600, 2),
        "km_pays": {k: round(v, 1) for k, v in km_pays.items()},
        "peage_pays": peage_pays,
        "peage_total": peage_total,
        "segments": segments,
        "frontieres": [{"lat": f["lat"], "lon": f["lon"], "de": f["de"], "vers": f["vers"],
                        "km_depuis_depart": round(f["d"] / 1000, 1)} for f in frontieres],
    }


def calculer_route_pays(lat1, lon1, lat2, lon2, waypoints=None, prohibited_countries=None, peage=True):
    data = appeler_ptv(lat1, lon1, lat2, lon2, waypoints, prohibited_countries, peage)
    return analyser(data, peage)
