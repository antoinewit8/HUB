"""
Serveur de cartes interactives.
Déployable sur Render.com (gratuit) → URL publique permanente.
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import uvicorn, uuid, json, os, httpx
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(title="Arcelor Route Map Server")

# --- AJOUTEZ CE BLOC ICI ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Autorise tous les sites web (dont votre Streamlit) à appeler cette API
    allow_credentials=True,
    allow_methods=["*"],  # Autorise toutes les méthodes (GET, POST, etc.)
    allow_headers=["*"],
)

# app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

ROUTES_FILE = "data/routes.json"
os.makedirs("data", exist_ok=True)

PTV_API_KEY    = os.environ.get("PTV_API_KEY", "")
MAP_SERVER_URL = os.environ.get("MAP_SERVER_URL", "http://localhost:8000")
FIREBASE_URL   = os.environ.get("FIREBASE_URL", "").rstrip("/")


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES PRÉFÉRENTIELLES
# ══════════════════════════════════════════════════════════════════════════════

PREF_ROUTES_FILE = "routes_preferentielles.json"

def load_pref_routes() -> list:
    """Charge le fichier JSON des routes préférentielles."""
    if not os.path.exists(PREF_ROUTES_FILE):
        return []
    with open(PREF_ROUTES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def find_pref_waypoints(origin: str, dest: str, super_mode: bool = False) -> list:
    """Retourne les waypoints préférentiels pour un trajet, ou []."""
    prefs = load_pref_routes()
    o = origin.strip().lower()
    d = dest.strip().lower()
    for route in prefs:
        if (route["origine"].strip().lower() == o
                and route["destination"].strip().lower() == d):
            
            # Support de la structure enrichie (super_waypoints)
            key = "super_waypoints" if super_mode and "super_waypoints" in route else "waypoints"
            wps_raw = route.get(key, [])
            
            wps = []
            for wp in wps_raw:
                parts = wp.split(",")
                if len(parts) == 2:
                    wps.append({
                        "lat": float(parts[0].strip()),
                        "lng": float(parts[1].strip()),
                    })
            return wps
    return []


# ══════════════════════════════════════════════════════════════════════════════
#  STOCKAGE (Firebase ou fichier local)
# ══════════════════════════════════════════════════════════════════════════════

def load_routes() -> dict:
    """Charge toutes les routes depuis Firebase ou fichier local."""
    if FIREBASE_URL:
        try:
            r = httpx.get(f"{FIREBASE_URL}/routes.json", timeout=30)
            if r.status_code == 200 and r.json():
                return r.json()
        except Exception as e:
            print(f"Erreur lecture Firebase : {e}")
        return {}

    if not os.path.exists(ROUTES_FILE):
        return {}
    with open(ROUTES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_routes(data: dict):
    """Sauvegarde toutes les routes vers Firebase ou fichier local."""
    if FIREBASE_URL:
        try:
            httpx.patch(f"{FIREBASE_URL}/routes.json", json=data, timeout=30)
        except Exception as e:
            print(f"Erreur écriture Firebase : {e}")
        return

    with open(ROUTES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_route(route_id: str) -> dict:
    """Télécharge une seule route depuis Firebase (ultra rapide)."""
    if FIREBASE_URL:
        try:
            r = httpx.get(f"{FIREBASE_URL}/routes/{route_id}.json", timeout=20)
            if r.status_code == 200 and r.json():
                return r.json()
        except Exception as e:
            print(f"Erreur lecture Firebase pour la route {route_id} : {e}")
        return None

    # Fallback local
    routes = load_routes()
    return routes.get(route_id)


# ══════════════════════════════════════════════════════════════════════════════
#  MODÈLES PYDANTIC
# ══════════════════════════════════════════════════════════════════════════════

class RouteCreate(BaseModel):
    origin:         str
    dest:           str
    distance_km:    float
    duration_h:     float
    polyline:       list
    prix_peage:     float = 0.0
    pref_waypoints: list  = []

class RouteRecalc(BaseModel):
    origin:         str
    dest:           str
    avoid_tolls:    bool = False
    avoid_highways: bool = False
    super_pref:     bool = False
    # Etapes posees sur la carte : [[lat, lng], ...] ou [{"lat":..,"lng":..}, ...].
    # Sans ce champ, les etapes ajoutees cote carte etaient ignorees.
    via:            list = []

class WaypointItem(BaseModel):
    lat: float
    lng: float

class RecalcDragRequest(BaseModel):
    waypoints:      List[WaypointItem]
    avoid_tolls:    bool = False
    avoid_highways: bool = False
    super_pref:     bool = False
    route_id:       Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS PTV
# ══════════════════════════════════════════════════════════════════════════════

def _extract_polyline(ptv: dict) -> list:
    """Extrait les coordonnées [[lat, lon], ...] depuis la réponse PTV."""
    polyline_raw = ptv.get("polyline", "")

    if isinstance(polyline_raw, dict):
        if polyline_raw.get("type") == "LineString":
            return [[c[1], c[0]] for c in polyline_raw.get("coordinates", [])]
        if "plain" in polyline_raw:
            raw = polyline_raw["plain"].get("pointsByCoordinates", [])
            return [[raw[i + 1], raw[i]] for i in range(0, len(raw) - 1, 2)]
        if "encodedPolyline" in polyline_raw:
            return _decode_polyline(polyline_raw["encodedPolyline"])
        return []

    if isinstance(polyline_raw, str) and polyline_raw:
        try:
            parsed = json.loads(polyline_raw)
            if isinstance(parsed, dict) and parsed.get("type") == "LineString":
                return [[c[1], c[0]] for c in parsed.get("coordinates", [])]
        except (json.JSONDecodeError, TypeError):
            pass
        return _decode_polyline(polyline_raw)

    return []

def _extract_distance_duration(ptv: dict):
    """Retourne (distance_m, duration_s) depuis la réponse PTV."""
    legs = ptv.get("legs", [])
    if legs:
        distance_m = sum(leg.get("distance", 0) for leg in legs)
        duration_s = sum(leg.get("travelTime", 0) for leg in legs)
    else:
        distance_m = ptv.get("distance", 0)
        duration_s = ptv.get("travelTime", 0)
    return distance_m, duration_s

def _extract_toll_by_country(ptv: dict) -> list:
    """
    Ventilation du peage par pays : [{"country": "DE", "price": 112.4}, ...].

    PTV fournit en principe toll.costs.countries. Si ce bloc manque, on agrege
    les sections de peage, d'ou l'ajout de TOLL_SECTIONS dans les results.
    Les prix convertis priment sur les prix en devise nationale, sinon on
    additionne des DKK avec des EUR.
    """
    def _prix(obj):
        if isinstance(obj, (int, float)):
            return float(obj)
        if not isinstance(obj, dict):
            return None
        conv = obj.get("convertedPrice")
        if isinstance(conv, dict) and conv.get("price") is not None:
            return float(conv["price"])
        if obj.get("price") is not None:
            return float(obj["price"])
        return None

    toll  = ptv.get("toll") or {}
    costs = toll.get("costs") or {}

    pays = costs.get("countries") or toll.get("countries")
    if pays:
        lignes = []
        for c in pays:
            cc = c.get("countryCode") or c.get("country")
            montant = _prix(c)
            if cc and montant is not None:
                lignes.append({"country": cc, "price": round(montant, 2)})
        if lignes:
            return sorted(lignes, key=lambda x: -x["price"])

    agrege = {}
    for sec in toll.get("sections") or []:
        cc = (sec.get("countryCode")
              or (sec.get("tollSystem") or {}).get("countryCode")
              or (sec.get("tollSystem") or {}).get("country"))
        if not cc:
            continue
        c = sec.get("costs")
        montant = sum(_prix(x) or 0.0 for x in c) if isinstance(c, list) else (_prix(c) or 0.0)
        agrege[cc] = agrege.get(cc, 0.0) + montant

    return sorted([{"country": cc, "price": round(v, 2)} for cc, v in agrege.items()],
                  key=lambda x: -x["price"])


def _extract_toll(ptv: dict) -> float:
    """Extrait le prix de péage depuis la réponse PTV."""
    toll_data = ptv.get("toll", {}).get("costs", {})
    if isinstance(toll_data, dict):
        return toll_data.get("convertedPrice", {}).get("price", 0)
    return 0

def _decode_polyline(encoded: str) -> list:
    """Décode Google encoded polyline → [[lat, lon], ...]."""
    coords, index, lat, lng = [], 0, 0, 0
    while index < len(encoded):
        for is_lng in [False, True]:
            shift, result = 0, 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            if is_lng:
                lng += delta
            else:
                lat += delta
        coords.append([lat / 1e5, lng / 1e5])
    return coords

_BROAD_COUNTRY_FILTER = ("FR,BE,LU,DE,ES,NL,GB,IT,CH,AT,PT,"
                         "DK,SE,NO,FI,PL,CZ,SK,HU,SI,HR,RO,BG,IE,GR,EE,LV,LT")

_COUNTRY_WORDS = {
    "france": "FR",
    "belgique": "BE", "belgium": "BE", "belgie": "BE",
    "italie": "IT", "italia": "IT", "italy": "IT",
    "espagne": "ES", "espana": "ES", "spain": "ES",
    "allemagne": "DE", "deutschland": "DE", "germany": "DE",
    "pays-bas": "NL", "nederland": "NL", "netherlands": "NL", "holland": "NL",
    "luxembourg": "LU",
    "suisse": "CH", "switzerland": "CH", "schweiz": "CH",
    "autriche": "AT", "austria": "AT",
    "portugal": "PT",
    "royaume-uni": "GB", "angleterre": "GB", "england": "GB", "uk": "GB",
}

def _country_filter_for(text: str) -> str:
    """Si le texte mentionne un pays connu, restreint le filtre PTV à ce seul pays
    (évite les faux positifs type 'Turin Italie' → Nice). Sinon, filtre large."""
    tokens = text.lower().replace(",", " ").split()
    for word, iso in _COUNTRY_WORDS.items():
        if word in tokens:
            return iso
    return _BROAD_COUNTRY_FILTER

_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)\s*$")

def _parse_coords(texte: str) -> Optional[list]:
    """
    "51.922500,4.479000" -> [51.9225, 4.479].

    Sans ce test, une paire de coordonnees partait au geocodeur comme du texte :
    il renvoyait le lieu le plus proche dans le filtre pays autorise, et
    l'itineraire n'avait plus aucun rapport avec les points demandes.
    """
    m = _COORD_RE.match(texte or "")
    if not m:
        return None
    lat, lng = float(m.group(1)), float(m.group(2))
    if -90 <= lat <= 90 and -180 <= lng <= 180:
        return [lat, lng]
    return None


async def _geocode(address: str) -> Optional[list]:
    """Géocode une adresse ou une paire de coordonnées via PTV → [lat, lng]."""
    coords = _parse_coords(address)
    if coords:
        return coords

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.myptv.com/geocoding/v1/locations/by-text",
            headers={"apiKey": PTV_API_KEY},
            params={"searchText": address, "countryFilter": _country_filter_for(address)},
            timeout=15,
        )
    if resp.status_code != 200:
        return None
    results = resp.json().get("locations", [])
    if not results:
        return None
    loc = results[0]["referencePosition"]
    return [loc["latitude"], loc["longitude"]]

async def _call_ptv(waypoints_list: list, avoid_tolls: bool, avoid_highways: bool, super_pref: bool = False) -> dict:
    """Appel PTV routing v1 GET — waypoints répétés en query string."""
    query_params = [
        ("profile", "EUR_TRAILER_TRUCK"),
        ("results", "POLYLINE,TOLL_COSTS,TOLL_SECTIONS"),
        ("options[currency]", "EUR"),
    ]

    for i, wp_str in enumerate(waypoints_list):
        parts = wp_str.split(",")
        lat = float(parts[0].strip())
        lng = float(parts[1].strip())
        if 0 < i < len(waypoints_list) - 1:
            query_params.append(("waypoints", f"{lat},{lng};radius=5000"))
        else:
            query_params.append(("waypoints", f"{lat},{lng}"))

    avoid = []
    if avoid_tolls or super_pref: avoid.append("TOLL")
    if avoid_highways: avoid.append("HIGHWAYS")
    if avoid:
        query_params.append(("options[avoid]", ",".join(avoid)))

    print(f"PTV QUERY: {query_params}")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.myptv.com/routing/v1/routes",
            headers={"apiKey": PTV_API_KEY},
            params=query_params,
            timeout=30,
        )

    if resp.status_code != 200:
        print(f"PTV ERROR {resp.status_code}: {resp.text[:1000]}")
        raise HTTPException(502, f"PTV error {resp.status_code}: {resp.text[:500]}")

    return resp.json()


# ══════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/geocode")
async def api_geocode(q: str, country: str = ""):
    """Route API pour la recherche d'adresse depuis le frontend."""
    if not q:
        raise HTTPException(status_code=400, detail="Requête vide")

    coords = _parse_coords(q)
    if coords:
        un = {"lat": coords[0], "lng": coords[1], "label": q, "countrycode": ""}
        return {**un, "results": [un]}

    # `country` optionnel : codes ISO2 separes par des virgules (ex. "NL,DK").
    filtre = country or _country_filter_for(q)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.myptv.com/geocoding/v1/locations/by-text",
            headers={"apiKey": PTV_API_KEY},
            params={"searchText": q, "countryFilter": filtre},
            timeout=15,
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Erreur avec l'API PTV")

    results = resp.json().get("locations", [])
    if not results:
        raise HTTPException(status_code=404, detail="Adresse introuvable")

    # On renvoie desormais plusieurs candidats : le frontend choisit, au lieu
    # de subir le premier resultat sans savoir de quel pays il vient.
    sorties = []
    for loc in results[:8]:
        pos = loc.get("referencePosition") or {}
        if pos.get("latitude") is None:
            continue
        addr = loc.get("address") or {}
        label = (addr.get("formattedAddress")
                 or loc.get("formattedAddress")
                 or ", ".join(filter(None, [addr.get("street"), addr.get("postalCode"),
                                            addr.get("city"), addr.get("country")]))
                 or q)
        sorties.append({
            "lat": pos["latitude"], "lng": pos["longitude"], "label": label,
            "countrycode": (addr.get("countryCode") or "").upper(),
        })

    if not sorties:
        raise HTTPException(status_code=404, detail="Adresse introuvable")

    return {**sorties[0], "results": sorties}

# ── Créer une route ──────────────────────────────────────────────────────────
@app.post("/api/create_route")
async def create_route(route: RouteCreate):
    route_id = uuid.uuid4().hex[:8]

    # ✅ CORRIGÉ : route_data créé AVANT d'être utilisé
    route_data = route.dict()
    route_data["polyline_original"] = route.polyline  # immuable, jamais écrasé
    route_data["polyline_current"]  = route.polyline  # modifiable par drag

    routes = {route_id: route_data}
    save_routes(routes)

    url = f"{MAP_SERVER_URL}/carte?id={route_id}"
    return {"url": url, "id": route_id}


# ── Afficher la carte ────────────────────────────────────────────────────────
@app.get("/carte")
async def show_map(request: Request, id: str):
    route = get_route(id)
    if not route:
        raise HTTPException(status_code=404, detail="Trajet introuvable")

    # ✅ Rétrocompat : anciennes routes sans polyline_original
    if "polyline_original" not in route:
        route["polyline_original"] = route.get("polyline", [])
        route["polyline_current"]  = route.get("polyline", [])

    return templates.TemplateResponse("map.html", {
        "request":    request,
        "route":      route,
        "route_id":   id,
        "server_url": MAP_SERVER_URL,
    })


# ── Recalcul standard (origine / destination texte) ─────────────────────────
@app.post("/api/recalculate")
async def recalculate(data: RouteRecalc):
    origin_coords = await _geocode(data.origin)
    dest_coords   = await _geocode(data.dest)

    if not origin_coords or not dest_coords:
        raise HTTPException(status_code=400, detail="Géocodage impossible")

    # Les etapes explicites de l'utilisateur priment sur les jalons preferentiels.
    etapes = []
    for wp in (data.via or []):
        if isinstance(wp, dict) and wp.get("lat") is not None:
            etapes.append({"lat": float(wp["lat"]), "lng": float(wp.get("lng", wp.get("lon")))})
        elif isinstance(wp, (list, tuple)) and len(wp) >= 2:
            etapes.append({"lat": float(wp[0]), "lng": float(wp[1])})

    pref_wps = [] if etapes else find_pref_waypoints(data.origin, data.dest, super_mode=data.super_pref)

    waypoints_list = [f"{origin_coords[0]},{origin_coords[1]}"]
    for wp in (etapes or pref_wps):
        waypoints_list.append(f"{wp['lat']},{wp['lng']}")
    waypoints_list.append(f"{dest_coords[0]},{dest_coords[1]}")

    ptv = await _call_ptv(waypoints_list, data.avoid_tolls, data.avoid_highways, super_pref=data.super_pref)

    distance_m, duration_s = _extract_distance_duration(ptv)
    prix_peage = _extract_toll(ptv)
    coords     = _extract_polyline(ptv)

    return {
        "distance_km":     round(distance_m / 1000, 1),
        "duration_h":      round(duration_s / 3600, 2),
        "prix_peage":      round(prix_peage, 2),
        "toll_by_country": _extract_toll_by_country(ptv),
        "polyline":        coords,
        "origin":          data.origin,
        "dest":            data.dest,
        "pref_waypoints":  pref_wps,
    }


# ── Recalcul drag (waypoints coordonnées) ───────────────────────────────────
@app.post("/api/recalculate_drag")
async def recalculate_drag(data: RecalcDragRequest):
    if len(data.waypoints) < 2:
        raise HTTPException(400, "Il faut au minimum 2 waypoints")

    waypoints_list = [f"{wp.lat},{wp.lng}" for wp in data.waypoints]

    print("="*60)
    print(f"DRAG RECALC — {len(waypoints_list)} waypoints")
    for i, wp in enumerate(waypoints_list):
        print(f"  [{i}] {wp}")
    print("="*60)

    try:
        ptv = await _call_ptv(waypoints_list, data.avoid_tolls, data.avoid_highways)
    except HTTPException as e:
        print(f"PTV a planté : {e.detail}")
        raise
    except Exception as e:
        print(f"ERREUR INATTENDUE : {type(e).__name__}: {e}")
        raise HTTPException(500, f"Erreur interne: {e}")

    distance_m, duration_s = _extract_distance_duration(ptv)
    prix_peage = _extract_toll(ptv)
    coords     = _extract_polyline(ptv)

    print(f"RÉSULTAT PTV : dist={distance_m}m, dur={duration_s}s, peage={prix_peage}, coords={len(coords)} points")

    # ✅ On écrase seulement polyline_current, jamais polyline_original
    if data.route_id and FIREBASE_URL:
        update_data = {
            "polyline_current": coords,
            "distance_km":      round(distance_m / 1000, 1),
            "duration_h":       round(duration_s / 3600, 2),
            "prix_peage":       round(prix_peage, 2),
        }
        try:
            httpx.patch(
                f"{FIREBASE_URL}/routes/{data.route_id}.json",
                json=update_data,
                timeout=10
            )
        except Exception as e:
            print(f"Erreur maj Firebase: {e}")

    return {
        "distance_km":     round(distance_m / 1000, 1),
        "duration_h":      round(duration_s / 3600, 2),
        "prix_peage":      round(prix_peage, 2),
        "toll_by_country": _extract_toll_by_country(ptv),
        "polyline":        coords,
    }


# ── Reset route → retour à l'itinéraire original ─────────────────────────────
@app.post("/api/reset_route/{route_id}")
async def reset_route(route_id: str):
    """Remet polyline_current = polyline_original dans Firebase."""
    if not FIREBASE_URL:
        raise HTTPException(400, "Firebase non configuré")

    try:
        r = httpx.get(
            f"{FIREBASE_URL}/routes/{route_id}/polyline_original.json",
            timeout=10
        )
        if r.status_code != 200 or not r.json():
            raise HTTPException(404, "polyline_original introuvable")

        original = r.json()

        httpx.patch(
            f"{FIREBASE_URL}/routes/{route_id}.json",
            json={"polyline_current": original},
            timeout=10
        )
        return {"status": "reset", "points": len(original)}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur reset: {e}")
    

# ══════════════════════════════════════════════════════════════════════════════
#  LANCEMENT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run("map_server_main:app", host="0.0.0.0", port=8000, reload=False)
