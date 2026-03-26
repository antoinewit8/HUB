"""
Wrapper callable depuis Streamlit / Core Brain.
Gère le path pour que les imports relatifs de main_km fonctionnent.
"""

import os
import sys

# === Injection du chemin km_calcul dans sys.path ===
KM_DIR = os.path.dirname(os.path.abspath(__file__))

def _inject_path():
    if KM_DIR not in sys.path:
        sys.path.insert(0, KM_DIR)

def run_calcul_km(filepath: str, calculer_peage: bool = False, progress_callback=None) -> dict:
    """
    Point d'entrée principal pour le calcul KM.

    Args:
        filepath: Chemin absolu vers le fichier Excel source
        calculer_peage: True pour inclure les frais de péage
        progress_callback: fonction(current, total, message) optionnelle

    Returns:
        dict {
            "success": bool,
            "output_path": str,
            "error": str,
            "stats": dict
        }
    """
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
        MAX_WORKERS = 1
        cache_lock  = threading.Lock()

        # === Cache ===
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
        def traiter_trajet(index, total, route, cache, calculer_peage):
            cache_key = f"{route['origin']} || {route['dest']}"
            from_cache = False

            with cache_lock:
                if cache_key in cache:
                    cached = cache[cache_key]
                    if calculer_peage and "prix_peage" not in cached:
                        pass
                    else:
                        return {"row": route["row"], "data": cached, "from_cache": True}

            origin_coords = geocode_address(route["origin"])
            if not origin_coords:
                return {"row": route["row"], "data": None, "from_cache": False}

            dest_coords = geocode_address(route["dest"])
            if not dest_coords:
                return {"row": route["row"], "data": None, "from_cache": False}

            waypoints = get_waypoints(route["origin"], route["dest"])

            data = calculate_km_route(
                origin_coords[0], origin_coords[1],
                dest_coords[0],   dest_coords[1],
                waypoints      = waypoints,
                calculer_peage = calculer_peage
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

        # Compter total global pour la progression
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
                        traiter_trajet, i + 1, total, route, cache, calculer_peage
                    )
                    futures_map[future] = i

                for future in as_completed(futures_map):
                    idx = futures_map[future]
                    try:
                        res = future.result()
                        results[idx] = res

                        # === Mise à jour stats ===
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

                    # === Callback progression ===
                    current_global += 1
                    if progress_callback:
                        progress_callback(
                            current_global,
                            total_global,
                            f"📍 {routes[idx]['origin']} → {routes[idx]['dest']}"
                        )

            write_km_results(ws, results, calculer_peage)

        sauvegarder_cache(cache)

        output_path = filepath.replace(".xlsx", "_KM.xlsx")
        wb.save(output_path)

        return {"success": True, "output_path": output_path, "error": "", "stats": stats}

    except Exception as e:
        return {"success": False, "output_path": "", "error": str(e), "stats": {}}
