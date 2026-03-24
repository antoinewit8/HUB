# core/config.py
# Centralise toute la configuration de l'application

from dotenv import load_dotenv
import os

load_dotenv()

# ── Infos générales ──────────────────────────────────────────
APP_NAME    = os.getenv("APP_NAME", "Transport Hub")
VERSION     = os.getenv("VERSION", "1.0.0")

# ── Chemins ──────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(BASE_DIR, "data")
LOGS_DIR   = os.path.join(BASE_DIR, "logs")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# ── Paramètres métier (modifiables ici uniquement) ────────────
SEUIL_ALERTE_CARBURANT = 0.10   # 10% de dépassement = alerte
SEUIL_ALERTE_KM        = 5000   # km avant révision = alerte
