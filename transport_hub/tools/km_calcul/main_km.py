import os
import time
import json
import threading
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from modules.ptv_router_km import calculate_km_route, geocode_address
from modules.excel_handler_km import read_all_sheets, write_km_results
from modules.routes_preferentielles import get_waypoints
from modules.map_server_client import create_route_url, warm_up_server
from dotenv import load_dotenv

load_dotenv()

CHEMIN_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE    = os.path.join(CHEMIN_SCRIPT, "cache_trajets.json")
MAX_WORKERS   = 1

cache_lock = threading.Lock()
print_lock  = threading.Lock()   # ← nouveau


def flush(lines: list[str]):
    """Affiche toutes les lignes d'un trajet d'un seul coup."""
    with print_lock:
        print("\n".join(lines))


# ── Cache ──────────────────────────────────────────────────────────────────
def charger_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                contenu = f.read().strip()
                return json.loads(contenu) if contenu else {}
        except json.JSONDecodeError as e:
            print(f"⚠️ Cache corrompu ({e}) → réinitialisation")
            import shutil
            shutil.copy(CACHE_FILE, CACHE_FILE + ".bak")
            return {}
    return {}

def sauvegarder_cache(cache):
    snapshot = copy.deepcopy(cache)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=4, ensure_ascii=False)


# ── Traitement complet : calcul + carte dans la foulée ────────────────────
def traiter_trajet(index, total, route, cache, calculer_peage, super_pref=False):
    log = [f"\n[{index}/{total}] {route['label']}"]   # ← buffer de logs

    cache_key = f"{route['origin']} || {route['dest']} || super={super_pref}"

    with cache_lock:
        if cache_key in cache:
            cached = cache[cache_key]
            if calculer_peage and "prix_peage" not in cached:
                log.append(f"   🔄 Cache sans péage → recalcul forcé...")
            else:
                label = f"{cached['km']} km" + (f" | 💶 {cached.get('prix_peage', 0)} €" if calculer_peage else "")
                log.append(f"   ⚡ Cache : {label}")
                flush(log)
                return {"row": route["row"], "data": cached}

    # ── Géocodage ─────────────────────────────────────────────────────────
    origin_coords = geocode_address(route["origin"])
    if not origin_coords:
        log.append(f"   ❌ Géocodage échoué: {route['origin']}")
        flush(log)
        return {"row": route["row"], "data": None}

    dest_coords = geocode_address(route["dest"])
    if not dest_coords:
        log.append(f"   ❌ Géocodage échoué: {route['dest']}")
        flush(log)
        return {"row": route["row"], "data": None}

    waypoints = get_waypoints(route["origin"], route["dest"])

    # ── Calcul itinéraire ─────────────────────────────────────────────────
    data = calculate_km_route(
        origin_coords[0], origin_coords[1],
        dest_coords[0],   dest_coords[1],
        waypoints      = waypoints,
        calculer_peage = calculer_peage,
        super_pref     = super_pref
    )

    if not data:
        log.append(f"   ❌ Échec calcul route")
        flush(log)
        return {"row": route["row"], "data": None}

    label = f"{data['km']} km" + (f" | 💶 {data.get('prix_peage', 0)} €" if calculer_peage else "")
    log.append(f"   ✅ {label}")

    # ── Carte générée immédiatement après ─────────────────────────────────
    carte_url = create_route_url(
        origin_name = route["origin"],
        dest_name   = route["dest"],
        km          = data["km"],
        duration_h  = data.get("travel_time_h", 0),
        polyline    = data.get("polyline_coords", []),
        prix_peage  = data.get("prix_peage", 0.0),
    )

    data["carte_url"] = carte_url if carte_url else ""
    log.append(f"   🗺️  Carte OK" if carte_url else f"   ⚠️  Carte échouée")

    # ── Flush groupé ──────────────────────────────────────────────────────
    flush(log)

    # ── Sauvegarde cache ──────────────────────────────────────────────────
    with cache_lock:
        cache[cache_key] = data
        if index % 10 == 0 or index == total:
            sauvegarder_cache(cache)

    return {"row": route["row"], "data": data}


# ── MAIN ──────────────────────────────────────────────────────────────────
def main():
    filepath = input("📁 Chemin du fichier Excel: ").strip().strip('"').strip("'")
    
    # Normalise le chemin en absolu IMMÉDIATEMENT
    filepath = os.path.abspath(filepath)
    
    if not os.path.exists(filepath):
        print(f"❌ Fichier introuvable : {filepath}")
        return
    
    choix_peage    = input("💶 Calculer les frais de péage ? (o/n) : ").strip().lower()
    calculer_peage = choix_peage in ('o', 'oui')

    choix_super    = input("🚀 Activer le mode SUPER PRÉFÉRENTIEL ? (o/n) : ").strip().lower()
    super_pref     = choix_super in ('o', 'oui')

    print("\n🔌 Réveil du serveur de cartes...")
    warm_up_server()
    print("✅ Serveur prêt !\n")

    print("\n📖 Lecture de toutes les feuilles...")
    wb, sheets_data = read_all_sheets(filepath)

    if not sheets_data:
        print("❌ Aucune feuille exploitable trouvée")
        return

    cache = charger_cache()

    for sheet_name, (ws, routes) in sheets_data.items():
        if not routes:
            print(f"\n📄 Feuille '{sheet_name}' : aucune route, skip")
            continue

        total = len(routes)
        print(f"\n{'='*60}")
        print(f"📄 Feuille '{sheet_name}' : {total} routes | workers={MAX_WORKERS}")
        print(f"{'='*60}")

        results     = [None] * total
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
                    results[idx] = future.result()
                except Exception as e:
                    with print_lock:
                        print(f"   🔴 Erreur trajet {idx+1}: {e}")
                    results[idx] = {"row": routes[idx]["row"], "data": None}

        write_km_results(ws, results, calculer_peage)

    sauvegarder_cache(cache)

    # ── Génération du chemin de sortie ROBUSTE ──
    dossier = os.path.dirname(filepath)
    nom     = os.path.basename(filepath)
    base, ext = os.path.splitext(nom)  # gère .xlsx .XLSX .Xlsx etc.
    output_name = f"{base}_KM{ext}"
    output_path = os.path.join(dossier, output_name)

    wb.save(output_path)
    print(f"\n📂 Dossier : {dossier}")
    print(f"🎉 Terminé ! Excel sauvegardé : {output_name}")
    print(f"📍 Chemin complet : {output_path}")



if __name__ == "__main__":
    main()
