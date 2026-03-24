import os
import json

# ==========================================
# FICHIERS CACHE À GÉRER
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CACHES = {
    "trajets":    os.path.join(BASE_DIR, "cache_trajets.json"),
    "geocodage":  os.path.join(BASE_DIR, "cache_geocodage.json"),
}


def afficher_taille(path: str) -> str:
    if not os.path.exists(path):
        return "absent"
    
    taille = os.path.getsize(path)
    taille_str = f"{taille / 1024:.1f} Ko"
    
    # Lecture sécurisée
    try:
        with open(path, "r", encoding="utf-8") as f:
            contenu = f.read().strip()
            if not contenu:
                return f"vide ({taille_str})"
            data = json.loads(contenu)
            nb = len(data) if isinstance(data, (dict, list)) else "?"
            return f"{nb} entrées ({taille_str})"
    except json.JSONDecodeError:
        return f"⚠️ CORROMPU ({taille_str}) — à vider"



def vider_cache(nom: str, path: str) -> None:
    if os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f)
        print(f"   ✅ Cache '{nom}' vidé")
    else:
        print(f"   ⚠️ Cache '{nom}' introuvable : {path}")


def menu():
    print("\n" + "="*45)
    print("   🗑️  GESTIONNAIRE DE CACHE")
    print("="*45)

    # Affiche l'état actuel
    for nom, path in CACHES.items():
        print(f"   [{nom}] → {afficher_taille(path)}")

    print("\nQue veux-tu faire ?")
    print("   1. Vider uniquement le cache TRAJETS")
    print("   2. Vider uniquement le cache GÉOCODAGE")
    print("   3. Vider TOUS les caches")
    print("   0. Quitter")

    choix = input("\nTon choix : ").strip()

    if choix == "1":
        vider_cache("trajets", CACHES["trajets"])

    elif choix == "2":
        vider_cache("geocodage", CACHES["geocodage"])

    elif choix == "3":
        for nom, path in CACHES.items():
            vider_cache(nom, path)

    elif choix == "0":
        print("   👋 Annulé")
        return

    else:
        print("   ❌ Choix invalide")
        return

    print("\n   🔄 Relance main_km.py pour recalculer depuis zéro.")


if __name__ == "__main__":
    menu()
