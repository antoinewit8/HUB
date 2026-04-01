import os
import sys

KM_DIR = os.path.dirname(os.path.abspath(__file__))

def _inject_path():
    if KM_DIR not in sys.path:
        sys.path.insert(0, KM_DIR)

def run_calcul_km(filepath: str, calculer_peage: bool = False, super_pref: bool = False, progress_callback=None) -> dict:
    _inject_path()

    try:
        from modules.excel_handler_km import read_all_sheets, write_km_results
        from modules.ptv_router_km import calculate_km_route, geocode_address
        from modules.routes_preferentielles import get_waypoints
        from modules.map_server_client import create_route_url, warm_up_server

        import json
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        CACHE_FILE  = os.path.join(KM_DIR, "cache_trajets.json")
        GEOCODE_CACHE_FILE = os.path.join(KM_DIR, "cache_geocode.json")
        MAX_WORKERS = 5  # ← 🚀 PARALLÉLISME
        cache_lock  = threading.Lock()
        geo_lock    = threading.Lock()

        # === Cache trajets ===
        def charger_cache():
            if os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        contenu = f.read().strip()
                        return json.loads(contenu) if contenu else {}
                except json.JSONDecodeError:
                    return {}
            return {}

        def sauvegarder_cache(cache):
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=4, ensure_ascii=False)

        # === 🚀 Cache geocoding ===
        def charger_geocode_cache():
            if os.path.exists(GEOCODE_CACHE_FILE):
                try:
                    with open(GEOCODE_CACHE_FILE, "r", encoding="utf-8") as f:
                        return json.loads(f.read().strip() or "{}")
                except:
                    return {}
            return {}

        def sauvegarder_geocode_cache(gc):
            with open(GEOCODE_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(gc, f, indent=2, ensure_ascii=False)

        def geocode_cached(address, gc):
            with geo_lock:
                if address in gc:
                    return gc[address]
            coords = geocode_address(address)
            if coords:
                with geo_lock:
                    gc[address] = coords
            return coords

        geocode_cache = charger_geocode_cache()

        # === Stats ===
        stats = {
            "total_trajets": 0,
            "trajets_ok": 0,
            "trajets_erreur": 0,
            "total_km": 0.0,
            "total_peage": 0.0,
            "from_cache": 0,
            "resultats": []
        }

        # === Traitement trajet ===
        def traiter_trajet(index, total, route, cache, calculer_peage, super_pref):
            cache_key = f"{route['origin']} || {route['dest']} || super={super_pref}"

            with cache_lock:
                if cache_key in cache:
                    cached = cache[cache_key]
                    if calculer_peage and "prix_peage" not in cached:
                        pass
                    else:
                        return {"row": route["row"], "data": cached, "from_cache": True}

            # 🚀 Geocoding avec cache
            origin_coords = geocode_cached(route["origin"], geocode_cache)
            if not origin_coords:
                return {"row": route["row"], "data": None, "from_cache": False}

            dest_coords = geocode_cached(route["dest"], geocode_cache)
            if not dest_coords:
                return {"row": route["row"], "data": None, "from_cache": False}

            waypoints = get_waypoints(route["origin"], route["dest"])

            data = calculate_km_route(
                origin_coords[0], origin_coords[1],
                dest_coords[0],   dest_coords[1],
                waypoints      = waypoints,
                calculer_peage = calculer_peage,
                super_pref     = super_pref
            )

            if not data:
                return {"row": route["row"], "data": None, "from_cache": False}

            carte_url = create_route_url(
                origin_name = route["origin"],
                dest_name   = route["dest"],
                km          = data["km"],
                duration_h  = data.get("travel_time_h", 0),
                polyline    = data.get("polyline_coords", []),
                prix_peage  = data.get("prix_peage", 0.0),
            )
            data["carte_url"] = carte_url if carte_url else ""

            with cache_lock:
                cache[cache_key] = data
                if index % 10 == 0 or index == total:
                    sauvegarder_cache(cache)

            return {"row": route["row"], "data": data, "from_cache": False}

        # === Exécution principale ===
        warm_up_server()

        wb, sheets_data = read_all_sheets(filepath)
        if not sheets_data:
            return {"success": False, "output_path": "", "error": "Aucune feuille exploitable", "stats": stats}

        cache = charger_cache()

        total_global = sum(len(routes) for _, (ws, routes) in sheets_data.items())
        current_global = 0

        for sheet_name, (ws, routes) in sheets_data.items():
            if not routes:
                continue

            total    = len(routes)
            results  = [None] * total
            futures_map = {}

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                for i, route in enumerate(routes):
                    future = executor.submit(
                        traiter_trajet, i + 1, total, route, cache, calculer_peage, super_pref
                    )
                    futures_map[future] = i

                for future in as_completed(futures_map):
                    idx = futures_map[future]
                    try:
                        res = future.result()
                        results[idx] = res

                        stats["total_trajets"] += 1
                        if res["data"]:
                            stats["trajets_ok"] += 1
                            stats["total_km"] += res["data"].get("km", 0)
                            stats["total_peage"] += res["data"].get("prix_peage", 0) or 0
                            if res.get("from_cache"):
                                stats["from_cache"] += 1
                            if len(stats["resultats"]) < 50:
                                stats["resultats"].append({
                                    "Origine": routes[idx]["origin"],
                                    "Destination": routes[idx]["dest"],
                                    "KM": round(res["data"].get("km", 0), 1),
                                    "Durée (h)": round(res["data"].get("travel_time_h", 0), 2),
                                    "Péage (€)": round(res["data"].get("prix_peage", 0) or 0, 2),
                                    "Cache": "✅" if res.get("from_cache") else "❌"
                                })
                        else:
                            stats["trajets_erreur"] += 1

                    except Exception:
                        results[idx] = {"row": routes[idx]["row"], "data": None, "from_cache": False}
                        stats["trajets_erreur"] += 1

                    current_global += 1
                    if progress_callback:
                        progress_callback(
                            current_global,
                            total_global,
                            f"📍 {routes[idx]['origin']} → {routes[idx]['dest']}"
                        )

            write_km_results(ws, results, calculer_peage)

        sauvegarder_cache(cache)
        sauvegarder_geocode_cache(geocode_cache)  # 🚀 Sauvegarde geocoding

        output_path = filepath.replace(".xlsx", "_KM.xlsx")
        wb.save(output_path)

        return {"success": True, "output_path": output_path, "error": "", "stats": stats}

    except Exception as e:
        return {"success": False, "output_path": "", "error": str(e), "stats": {}}
