# clear_cache.py
import os
import json
import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CACHES = {
    "trajets":   os.path.join(BASE_DIR, "cache_trajets.json"),
    "geocodage": os.path.join(BASE_DIR, "cache_geocodage.json"),
}


def afficher_taille(path: str) -> str:
    if not os.path.exists(path):
        return "absent"
    taille = os.path.getsize(path)
    taille_str = f"{taille / 1024:.1f} Ko"
    try:
        with open(path, "r", encoding="utf-8") as f:
            contenu = f.read().strip()
            if not contenu:
                return f"vide ({taille_str})"
            data = json.loads(contenu)
            nb = len(data) if isinstance(data, (dict, list)) else "?"
            return f"{nb} entrées ({taille_str})"
    except json.JSONDecodeError:
        return f"⚠️ CORROMPU ({taille_str})"


def vider_cache(nom: str, path: str) -> bool:
    if os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return True
    return False


def vider_tous():
    for nom, path in CACHES.items():
        vider_cache(nom, path)
