"""
Page Streamlit : Planning Plateaux — Vue planeur
==================================================
Objectif : permettre à un nouveau planeur de lire le planning d'un coup d'œil.
Le fichier source est un export *au niveau activité* : chaque ligne est UNE
activité (chargement ou déchargement) rattachée à un N° Dossier. La page
reconstruit les dossiers (jambe chargement → jambe déchargement) et propose :

  • Filtrage par dimension : Chauffeur / Tracteur (immat.) / Remorque
    → sélection précise OU "tout confondu" (multiselect vide).
  • Tractionnaires : détectés par "TRA" dans "Départ. tracteur".
    Le reste = flotte CB. Filtre Tous / Flotte CB / Tractionnaires,
    badge TRA toujours visible (y compris en tout confondu).
  • Regroupements géographiques : ≥2 chargements OU ≥2 déchargements le même
    jour dans le même département → alertes (réflexe planning).
  • Deux vues : "Par jour" (worklist charg | déch) et "Par ressource" (swimlane).
  • Carte EN HAUT : affichée directement, avec panneau pays en surimpression.
    Communes frontalières remappées vers le pays logistique (ex: Bazeilles → BE).

Colonnes source attendues (ordre indicatif, résolution robuste par nom) :
  N° Dossier | Activité | Date | Heure | Type de transport | Nom 1 | Nom 2 |
  Adresse | Numéro | Code pays | Département | Code postal | Localité |
  Produit | Chauffeur | Départ. tracteur | Immat. tracteur | Remorque
"""

import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import re
import os
import sys
import io
import json
import importlib.util as _ilu
import types as _types
import urllib.request as _ureq
import urllib.parse as _uparse

# ─── Import PTV (même mécanisme que la page Optimisateur) ─────────────────────
def _load_ptv(project_root: str):
    if "modules" not in sys.modules:
        pkg = _types.ModuleType("modules")
        pkg.__path__ = [project_root]
        pkg.__package__ = "modules"
        sys.modules["modules"] = pkg
    for mod_name, filename in [
        ("modules.route_optimizer", "route_optimizer.py"),
        ("modules.villes_jalons",   "villes_jalons.py"),
    ]:
        if mod_name not in sys.modules:
            path = os.path.join(project_root, filename)
            if os.path.exists(path):
                spec = _ilu.spec_from_file_location(mod_name, path)
                mod  = _ilu.module_from_spec(spec)
                mod.__package__ = "modules"
                sys.modules[mod_name] = mod
                try:
                    spec.loader.exec_module(mod)
                except Exception:
                    pass
    ptv_path = os.path.join(project_root, "ptv_router_km.py")
    if not os.path.exists(ptv_path):
        return None
    spec = _ilu.spec_from_file_location("modules.ptv_router_km", ptv_path)
    mod  = _ilu.module_from_spec(spec)
    mod.__package__ = "modules"
    sys.modules["modules.ptv_router_km"] = mod
    spec.loader.exec_module(mod)
    return mod

_HERE  = os.path.dirname(os.path.abspath(__file__))
_ROOTS = [_HERE, os.path.dirname(_HERE)]

PTV_AVAILABLE = False
_ptv_mod = None
for _root in _ROOTS:
    if os.path.exists(os.path.join(_root, "ptv_router_km.py")):
        try:
            _ptv_mod = _load_ptv(_root)
            if _ptv_mod:
                PTV_AVAILABLE = True
                break
        except Exception:
            pass

if PTV_AVAILABLE and _ptv_mod:
    geocode_by_postal_code = _ptv_mod.geocode_by_postal_code
    _geocode_by_text       = _ptv_mod._geocode_by_text
    PAYS_TO_ISO            = _ptv_mod.PAYS_TO_ISO
    GPS_FIXES              = _ptv_mod.GPS_FIXES
else:
    PAYS_TO_ISO = {}
    GPS_FIXES   = {}

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Planning Plateaux", page_icon="🗂️", layout="wide")

# ─── Style ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600;700&family=Barlow:wght@300;400;500;600&display=swap');

:root{
  --bg:#0e1016; --panel:#141821; --panel2:#11151d;
  --line:#222838; --line2:#1a2030;
  --txt:#cdd4ea; --muted:#5b6480; --faint:#3a4258;
  --charg:#4abf6a; --charg-d:#1b2b1f; --charg-l:#2d5a3d;
  --dech:#4a8abf;  --dech-d:#152230;  --dech-l:#1e3a5a;
  --tra:#c79a4e;   --tra-d:#241c10;   --tra-l:#5a4520;
  --alert:#c0584e; --alert-d:#241312; --alert-l:#5a2a26;
}
[data-testid="stAppViewContainer"]{ background:var(--bg); }
[data-testid="stSidebar"]{ background:#090b11; }
*{ font-family:'Barlow', sans-serif; }
.block-container{ padding-top:1.4rem; }

.hero{
  background:var(--panel); border:1px solid var(--line);
  border-radius:8px; padding:1.4rem 1.8rem; margin-bottom:1.2rem;
  display:flex; align-items:flex-end; justify-content:space-between; gap:1rem;
}
.hero h1{
  font-family:'Barlow Condensed',sans-serif; color:var(--txt);
  font-size:2.05rem; font-weight:700; margin:0; letter-spacing:.6px;
  text-transform:uppercase; line-height:1;
}
.hero p{ color:var(--muted); font-size:.88rem; margin:.4rem 0 0; }
.badge{
  display:inline-block; font-family:'Barlow Condensed',sans-serif; font-weight:600;
  font-size:.68rem; letter-spacing:1.4px; text-transform:uppercase;
  padding:3px 11px; border-radius:3px; white-space:nowrap;
}
.badge.ptv{ background:var(--charg-d); border:1px solid var(--charg-l); color:var(--charg); }
.badge.ptv.off{ background:var(--alert-d); border:1px solid var(--alert-l); color:var(--alert); }

.kgrid{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:.7rem; margin-bottom:1.2rem; }
.kpi{ background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:.8rem 1rem; }
.kpi .v{ font-family:'Barlow Condensed',sans-serif; font-size:1.85rem; font-weight:700; color:var(--txt); line-height:1; }
.kpi .l{ font-size:.66rem; color:var(--faint); text-transform:uppercase; letter-spacing:1.4px; margin-top:5px; }
.kpi.tra .v{ color:var(--tra); }

.sect{
  font-family:'Barlow Condensed',sans-serif; font-size:.72rem; color:var(--faint);
  text-transform:uppercase; letter-spacing:2.6px; margin:1.6rem 0 .7rem;
  padding-bottom:.45rem; border-bottom:1px solid var(--line2);
  display:flex; justify-content:space-between; align-items:baseline;
}
.sect .hint{ color:var(--faint); letter-spacing:1px; font-size:.66rem; }

/* Panneau pays — cartes empilées, grandes et lisibles */
.pays-panel{
  display:flex; flex-direction:column; gap:.45rem;
  font-family:'Barlow Condensed',sans-serif;
}
.pays-panel .pp-title{
  font-size:.58rem; font-weight:700; letter-spacing:2.5px; text-transform:uppercase;
  color:#3a4258; margin-bottom:.1rem; padding-left:.1rem;
}
.pp-card{
  background:#141821; border:1px solid #222838; border-radius:7px;
  padding:.55rem .75rem .5rem;
  display:flex; flex-direction:column; gap:0;
}
.pp-card-top{
  display:flex; align-items:baseline; gap:.45rem;
}
.pp-flag{ font-size:1.3rem; line-height:1; }
.pp-code{
  font-family:'Barlow Condensed',sans-serif; font-weight:700;
  font-size:1.35rem; letter-spacing:.5px; color:#cdd4ea; line-height:1;
}
.pp-val{
  font-family:'Barlow Condensed',sans-serif; font-weight:700;
  font-size:2.1rem; color:#4abf6a; line-height:1; margin-left:auto;
}
.pp-val.d{ color:#4a8abf; }
.pp-val.both{ color:#cdd4ea; }
.pp-detail{
  font-size:.68rem; color:#3a4258; font-weight:600; letter-spacing:.2px;
  margin-top:.22rem; padding-top:.22rem; border-top:1px solid #1a2030;
  line-height:1.4;
}
.pp-detail span{ color:#5b6480; }

/* Jour : en-tête + colonnes */
.dayhead{
  font-family:'Barlow Condensed',sans-serif; color:var(--txt);
  font-size:1.3rem; font-weight:700; text-transform:uppercase; letter-spacing:.5px;
  margin:1.1rem 0 .5rem; padding-bottom:.3rem; border-bottom:1px solid var(--line);
  display:flex; align-items:baseline; gap:.7rem;
}
.dayhead .cnt{ font-size:.72rem; color:var(--muted); letter-spacing:1px; font-weight:500; }
.coltag{
  font-family:'Barlow Condensed',sans-serif; font-size:.7rem; font-weight:700;
  letter-spacing:2px; text-transform:uppercase; margin:.2rem 0 .55rem;
}
.coltag.c{ color:var(--charg); } .coltag.d{ color:var(--dech); }

.card{
  background:var(--panel); border:1px solid var(--line); border-radius:6px;
  padding:.7rem .85rem; margin-bottom:.55rem; display:grid;
  grid-template-columns:auto 1fr; gap:.7rem; align-items:start;
}
.card.c{ border-color:var(--charg-l); }
.card.d{ border-color:var(--dech-l); }
.card .hour{
  font-family:'Barlow Condensed',sans-serif; font-size:1.25rem; font-weight:700;
  line-height:1; padding-top:1px; min-width:3.1rem;
}
.card.c .hour{ color:var(--charg); } .card.d .hour{ color:var(--dech); }
.card .hour .dno{ display:block; font-size:.6rem; font-weight:500; color:var(--faint); letter-spacing:.5px; margin-top:3px; }
.card .loc{
  font-family:'Barlow Condensed',sans-serif; font-size:1.08rem; font-weight:600;
  color:var(--txt); text-transform:uppercase; letter-spacing:.3px; line-height:1.05;
}
.card .site{ font-size:.78rem; color:var(--muted); margin-top:1px; }
.card .leg{ font-size:.73rem; color:var(--faint); margin-top:3px; }
.card .leg b{ color:var(--muted); font-weight:600; }

.tags{ display:flex; flex-wrap:wrap; gap:5px; margin-top:.5rem; }
.tag{
  font-family:'Barlow Condensed',sans-serif; font-size:.68rem; font-weight:600;
  letter-spacing:.3px; padding:1px 6px; border-radius:3px; border:1px solid var(--line);
  color:var(--muted); background:var(--panel2);
}
.tag.tra{ color:var(--tra); border-color:var(--tra-l); background:var(--tra-d); }
.tag.cb{ color:var(--charg); border-color:var(--charg-l); background:var(--charg-d); }
.tag.prod{ color:var(--txt); }

/* Swimlane par ressource */
.lane{ background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:.65rem .85rem; margin-bottom:.55rem; }
.lane .who{
  font-family:'Barlow Condensed',sans-serif; font-size:1.05rem; font-weight:700;
  color:var(--txt); text-transform:uppercase; letter-spacing:.4px; display:flex; gap:.6rem; align-items:center;
}
.lane .who .meta{ font-size:.68rem; color:var(--faint); font-weight:500; letter-spacing:1px; text-transform:none; }
.flow{ display:flex; flex-wrap:wrap; gap:6px; margin-top:.5rem; }
.stop{
  font-size:.72rem; font-family:'Barlow Condensed',sans-serif; font-weight:600;
  padding:3px 9px; border-radius:3px; border:1px solid; letter-spacing:.3px; white-space:nowrap;
}
.stop.c{ color:var(--charg); border-color:var(--charg-l); background:var(--charg-d); }
.stop.d{ color:var(--dech); border-color:var(--dech-l); background:var(--dech-d); }
.stop .t{ opacity:.7; font-weight:500; margin-right:5px; }

/* Vue Par jour — disposition Lignes */
.rows{ border:1px solid var(--line); border-radius:7px; overflow:hidden; margin-bottom:.5rem; }
.row{ display:grid; grid-template-columns:108px minmax(0,1.5fr) 16px minmax(0,1.5fr) minmax(0,1.4fr);
      gap:.45rem .75rem; align-items:center; padding:.42rem .75rem; border-bottom:1px solid var(--line2); }
.row:last-child{ border-bottom:none; }
.row:nth-child(odd){ background:var(--panel2); }
.row .c1{ display:flex; flex-direction:column; gap:3px; align-items:flex-start; }
.row .c1 .dos{ font-family:'Barlow Condensed',sans-serif; font-weight:600; font-size:.7rem; letter-spacing:1px; color:var(--faint); }
.leg2{ display:grid; grid-template-columns:auto auto minmax(0,1fr); gap:.4rem; align-items:baseline; min-width:0; }
.leg2 .lh{ font-family:'Barlow Condensed',sans-serif; font-weight:700; font-size:.9rem; white-space:nowrap; letter-spacing:.3px; }
.leg2.c .lh{ color:var(--charg); } .leg2.d .lh{ color:var(--dech); }
.leg2 .ll{ font-family:'Barlow Condensed',sans-serif; font-weight:600; font-size:.9rem; color:var(--txt); text-transform:uppercase; letter-spacing:.2px; white-space:nowrap; }
.leg2 .ls{ font-size:.72rem; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0; }
.leg2.off{ display:block; grid-template-columns:none; color:var(--faint); font-size:.74rem; font-style:italic; }
.rarrow{ color:var(--faint); font-size:.85rem; text-align:center; }
.row .res{ display:flex; flex-wrap:wrap; gap:3px; }
.dens-compact .row{ padding:.28rem .65rem; }
.dens-compact .leg2 .lh, .dens-compact .leg2 .ll{ font-size:.82rem; }
.dens-compact .leg2 .ls{ font-size:.68rem; }
.dens-large .row{ padding:.62rem .85rem; gap:.5rem .9rem; }
.dens-large .leg2 .lh, .dens-large .leg2 .ll{ font-size:1.02rem; }
.dens-large .leg2 .ls{ font-size:.78rem; }
@media(max-width:820px){
  .row{ grid-template-columns:1fr; gap:.18rem; }
  .rarrow{ display:none; }
}

/* Vue Cartes */
.trips{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:.5rem; margin-bottom:.5rem; }
.trip{ background:var(--panel2); border:1px solid var(--line2); border-radius:7px; padding:.5rem .65rem .55rem; }
.trip-h{ display:flex; justify-content:space-between; align-items:center; gap:.4rem; margin-bottom:.3rem; flex-wrap:wrap; }
.trip-h .dos{ font-family:'Barlow Condensed',sans-serif; font-weight:600; font-size:.72rem; letter-spacing:1.2px; color:var(--faint); }
.trip-tags{ display:flex; flex-wrap:wrap; gap:3px; }
.leg{ display:grid; grid-template-columns:auto 1fr; column-gap:.65rem; align-items:baseline; padding:.08rem 0; }
.leg .lh{ font-family:'Barlow Condensed',sans-serif; font-weight:700; font-size:.9rem; line-height:1.25; white-space:nowrap; letter-spacing:.3px; }
.leg.c .lh{ color:var(--charg); } .leg.d .lh{ color:var(--dech); }
.leg .ll{ grid-column:2; font-family:'Barlow Condensed',sans-serif; font-weight:600; font-size:.95rem; color:var(--txt); text-transform:uppercase; letter-spacing:.2px; line-height:1.25; }
.leg .ls{ grid-column:2; font-size:.72rem; color:var(--muted); line-height:1.25; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.leg.off{ display:block; grid-template-columns:none; font-size:.72rem; font-style:italic; color:var(--faint); padding:.12rem 0; }
.arrow{ color:var(--faint); font-size:.78rem; line-height:1; margin:.1rem 0 .15rem .15rem; }

/* Regroupements */
.cluster{
  background:var(--alert-d); border:1px solid var(--alert-l); border-radius:6px;
  padding:.7rem .95rem; margin-bottom:.5rem;
}
.cluster .ch{ font-family:'Barlow Condensed',sans-serif; font-weight:700; font-size:1rem; color:#e6a59d; text-transform:uppercase; letter-spacing:.5px; }
.cluster .cs{ font-size:.76rem; color:#b08580; margin-top:3px; }
.cluster.d{ background:var(--dech-d); border-color:var(--dech-l); }
.cluster.d .ch{ color:#9cc4e6; } .cluster.d .cs{ color:#7d9ab0; }
.legendline{ color:var(--faint); font-size:.74rem; margin-top:.4rem; }
.legendline b.c{ color:var(--charg); } .legendline b.d{ color:var(--dech); } .legendline b.x{ color:var(--alert); }
</style>
""", unsafe_allow_html=True)

# ─── Communes frontalières → pays logistique (override d'affichage carte) ─────
# Ces communes sont encodées côté client avec le pays source (FR) mais
# logistiquement rattachées à un autre pays pour le compteur carte.
# Format : { normalize(localite) : "CODE_PAYS_LOGISTIQUE" }
COMMUNES_PAYS_LOGISTIQUE = {
    # Ardennes 08 – zone Sedan/Carignan frontalière Belgique
    "bazeilles":         "BE",
    "carignan":          "BE",
    "mouzon":            "BE",
    "remilly aillicourt":"BE",
    "douzy":             "BE",
    "sedan":             "BE",
    # Moselle 57 – zone frontalière Luxembourg
    "thionville":        "LU",
    "yutz":              "LU",
    "metzange":          "LU",
    # Ajoutez ici d'autres communes si besoin
}

# ─── Utilitaires ─────────────────────────────────────────────────────────────
def normalize(text) -> str:
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return ""
    text = str(text).upper().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"['\-–/]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def normalize_key(text) -> str:
    """Version minuscule pour les clés dict."""
    if not text:
        return ""
    text = str(text).lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"['\-–/]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def _norm_col(c) -> str:
    c = unicodedata.normalize("NFD", str(c))
    c = "".join(ch for ch in c if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]", "", c.lower())

def find_col(cols, *candidates):
    nmap = {}
    for c in cols:
        nmap.setdefault(_norm_col(c), c)
    for cand in candidates:
        nc = _norm_col(cand)
        if nc in nmap:
            return nmap[nc]
    for cand in candidates:
        nc = _norm_col(cand)
        if not nc:
            continue
        for k, v in nmap.items():
            if nc in k or k in nc:
                return v
    return None

def classify_activite(v) -> str:
    n = normalize(v)
    if not n:
        return "?"
    if "DECH" in n or "LIVR" in n or "UNLOAD" in n or n.startswith("D"):
        return "D"
    if "CHARG" in n or "ENLEV" in n or "LOAD" in n or n.startswith("C") or n.startswith("E"):
        return "C"
    return "?"

def parse_heure(v):
    if v is None:
        return "", 99.0
    s = str(v).strip()
    m = re.search(r"(\d{1,2})\s*[:hH]\s*(\d{0,2})", s)
    if m:
        h = int(m.group(1)); mi = int(m.group(2) or 0)
        return f"{h:02d}:{mi:02d}", h + mi / 60.0
    try:
        f = float(s.replace(",", "."))
        if 0 <= f < 1:
            h = int(f * 24); mi = int(round((f * 24 - h) * 60))
            return f"{h:02d}:{mi:02d}", h + mi / 60.0
    except Exception:
        pass
    return s[:5], 99.0

PAYS_MAP_DISPLAY = {
    "F":"France","FR":"France","B":"Belgium","BE":"Belgium","NL":"Netherlands",
    "D":"Germany","DE":"Germany","L":"Luxembourg","LU":"Luxembourg","E":"Spain","ES":"Spain",
    "I":"Italy","IT":"Italy","CH":"Switzerland","A":"Austria","AT":"Austria",
    "GB":"United Kingdom","UK":"United Kingdom","PL":"Poland","P":"Portugal","PT":"Portugal",
}
PAYS_FLAGS = {
    "F":"🇫🇷","FR":"🇫🇷","B":"🇧🇪","BE":"🇧🇪","NL":"🇳🇱","D":"🇩🇪","DE":"🇩🇪",
    "L":"🇱🇺","LU":"🇱🇺","E":"🇪🇸","ES":"🇪🇸","I":"🇮🇹","IT":"🇮🇹","CH":"🇨🇭",
    "A":"🇦🇹","AT":"🇦🇹","GB":"🇬🇧","UK":"🇬🇧","PL":"🇵🇱","P":"🇵🇹","PT":"🇵🇹",
}
DEPT_NOM = {
    "59":"Nord","62":"Pas-de-Calais","80":"Somme","02":"Aisne","60":"Oise","76":"Seine-Maritime",
    "27":"Eure","75":"Paris","77":"Seine-et-Marne","93":"Seine-St-Denis","51":"Marne","54":"Meurthe-et-M.",
    "57":"Moselle","67":"Bas-Rhin","69":"Rhône","13":"Bouches-du-Rh.","33":"Gironde","31":"Hte-Garonne",
    "44":"Loire-Atl.","35":"Ille-et-V.","49":"Maine-et-L.","53":"Mayenne","72":"Sarthe","85":"Vendée",
}

def pays_logistique(localite: str, pays_source: str) -> str:
    """Renvoie le code pays logistique : override frontalier si connu, sinon pays source normalisé."""
    key = normalize_key(localite)
    if key in COMMUNES_PAYS_LOGISTIQUE:
        return COMMUNES_PAYS_LOGISTIQUE[key]
    # Normalise FR/F → FR, BE/B → BE, etc.
    p = (pays_source or "").upper().strip()
    MAP = {"F": "FR", "B": "BE", "D": "DE", "E": "ES", "I": "IT",
           "L": "LU", "A": "AT", "P": "PT", "UK": "GB"}
    return MAP.get(p, p) if p else "??"

# ─── Géocodage ───────────────────────────────────────────────────────────────
def _photon(query: str):
    url = f"https://photon.komoot.io/api/?q={_uparse.quote(query)}&limit=1&lang=fr"
    try:
        req = _ureq.Request(url, headers={"User-Agent": "CB-Transport-Hub/1.0"})
        with _ureq.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        ft = data.get("features", [])
        if ft:
            c = ft[0]["geometry"]["coordinates"]
            return float(c[1]), float(c[0])
    except Exception:
        pass
    return None

def _nominatim(query: str):
    url = f"https://nominatim.openstreetmap.org/search?q={_uparse.quote(query)}&format=json&limit=1"
    try:
        req = _ureq.Request(url, headers={"User-Agent": "CB-Transport-Hub/1.0"})
        with _ureq.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None

@st.cache_data(show_spinner=False, ttl=86400)
def geocode_cached(ville: str, cp: str, pays: str):
    ville = (ville or "").strip()
    if not ville and not cp:
        return None
    ville_exp = re.sub(r'\bST\b', 'SAINT', ville, flags=re.IGNORECASE)
    ville_exp = re.sub(r'\bSTE\b', 'SAINTE', ville_exp, flags=re.IGNORECASE)
    pays_u = (pays or "").upper()
    pays_label = PAYS_MAP_DISPLAY.get(pays_u, pays) if pays else ""

    if PTV_AVAILABLE:
        fix_key = ville.strip().lower()
        if fix_key in GPS_FIXES:
            return GPS_FIXES[fix_key]
        if cp and pays_u:
            iso = PAYS_TO_ISO.get((pays_label or "").lower())
            if not iso and len(pays_u) == 2:
                iso = pays_u
            if iso:
                r = geocode_by_postal_code(cp, iso)
                if r:
                    return r
        for v in ([ville_exp, ville] if ville_exp != ville else [ville]):
            for q in filter(None, [
                f"{v}, {cp}, {pays_label}" if cp and pays_label else None,
                f"{v}, {pays_label}" if pays_label else None, v or None]):
                r = _geocode_by_text(q)
                if r:
                    return r
    else:
        for v in ([ville_exp, ville] if ville_exp != ville else [ville]):
            for q in filter(None, [
                f"{v}, {cp}, {pays_label}" if cp and pays_label else None,
                f"{v}, {pays_label}" if pays_label else None, v or None]):
                r = _photon(q) or _nominatim(q)
                if r:
                    return r
    return None

# ─── Chargement / préparation ─────────────────────────────────────────────────
def smart_to_datetime(s):
    s = s.fillna("").astype(str).str.strip()
    a = pd.to_datetime(s, errors="coerce", dayfirst=True)
    b = pd.to_datetime(s, errors="coerce", dayfirst=False)

    def span_days(x):
        x = x.dropna()
        return (x.max() - x.min()).days if len(x) > 1 else 0

    na_a, na_b = int(a.isna().sum()), int(b.isna().sum())
    if na_a != na_b:
        return (a, "jour/mois") if na_a < na_b else (b, "mois/jour")
    if span_days(a) == span_days(b):
        return a, "jour/mois (défaut)"
    return (a, "jour/mois") if span_days(a) < span_days(b) else (b, "mois/jour")

@st.cache_data(show_spinner=False)
def load_activites(file_bytes):
    df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
    df.columns = df.columns.str.strip()
    cols = list(df.columns)

    C = {
        "dossier":    find_col(cols, "N° Dossier", "No Dossier", "Dossier", "N Dossier"),
        "activite":   find_col(cols, "Activité", "Activite", "Activ"),
        "date":       find_col(cols, "Date"),
        "heure":      find_col(cols, "Heure"),
        "type_tr":    find_col(cols, "Type de transport", "Type transport"),
        "nom1":       find_col(cols, "Nom 1", "Nom1", "Nom"),
        "nom2":       find_col(cols, "Nom 2", "Nom2"),
        "adresse":    find_col(cols, "Adresse"),
        "numero":     find_col(cols, "Numéro", "Numero", "No"),
        "pays":       find_col(cols, "Code pays", "Pays"),
        "dept":       find_col(cols, "Département", "Departement", "Dept"),
        "cp":         find_col(cols, "Code postal", "CP"),
        "localite":   find_col(cols, "Localité", "Localite", "Ville"),
        "produit":    find_col(cols, "Produit"),
        "chauffeur":  find_col(cols, "Chauffeur"),
        "depart_trac":find_col(cols, "Départ. tracteur", "Depart tracteur", "Depart. tracteur", "Départ tracteur"),
        "immat":      find_col(cols, "Immat. tracteur", "Immat tracteur", "Immatriculation", "Immat"),
        "remorque":   find_col(cols, "Remorque"),
    }

    def col(key):
        c = C[key]
        return df[c] if c and c in df.columns else pd.Series([None] * len(df))

    out = pd.DataFrame()
    out["dossier"]    = col("dossier").fillna("").astype(str).str.strip()
    out["_act_raw"]   = col("activite").fillna("").astype(str).str.strip()
    out["type"]       = out["_act_raw"].apply(classify_activite)
    out["date"], _date_order = smart_to_datetime(col("date"))
    he = col("heure").apply(parse_heure)
    out["heure"]      = he.apply(lambda x: x[0])
    out["_hval"]      = he.apply(lambda x: x[1])
    out["type_tr"]    = col("type_tr").fillna("").astype(str).str.strip()
    n1 = col("nom1").fillna("").astype(str).str.strip()
    n2 = col("nom2").fillna("").astype(str).str.strip()
    out["site"]       = (n1 + " " + n2).str.strip().replace(r"\s+", " ", regex=True)
    out["localite"]   = col("localite").fillna("").astype(str).str.strip()
    out["cp"]         = col("cp").fillna("").astype(str).str.strip()
    out["dept"]       = col("dept").fillna("").astype(str).str.strip()
    out["pays"]       = col("pays").fillna("").astype(str).str.strip().str.upper()
    out["produit"]    = col("produit").fillna("").astype(str).str.strip()
    out["chauffeur"]  = col("chauffeur").fillna("").astype(str).str.strip()
    out["depart_trac"]= col("depart_trac").fillna("").astype(str).str.strip()
    out["immat"]      = col("immat").fillna("").astype(str).str.strip()
    out["remorque"]   = col("remorque").fillna("").astype(str).str.strip()

    cp2 = out["cp"].str.extract(r"^(\d{2})", expand=False)
    out["dept"] = out["dept"].where(out["dept"].str.len() > 0, cp2).fillna("")

    out["is_tra"] = out["depart_trac"].str.upper().str.contains("TRA", na=False)

    # Pays logistique (avec overrides communes frontalières)
    out["pays_logi"] = out.apply(
        lambda r: pays_logistique(r["localite"], r["pays"]), axis=1)

    out["_dt"] = out["date"] + pd.to_timedelta(
        out["_hval"].where(out["_hval"] < 30, 0), unit="h")

    out = out[out["dossier"] != ""].copy()
    out = out.sort_values(["date", "_hval"], na_position="last").reset_index(drop=True)

    act_distinct = (df[C["activite"]].dropna().astype(str).str.strip().value_counts()
                    if C["activite"] else pd.Series(dtype=int))
    return out, C, act_distinct, _date_order

def build_dossier_legs(df):
    legs = {}
    for dos, g in df.groupby("dossier"):
        ch = g[g["type"] == "C"].sort_values("_hval")
        de = g[g["type"] == "D"].sort_values("_hval")
        c0 = ch.iloc[0] if len(ch) else None
        d0 = de.iloc[-1] if len(de) else None
        legs[dos] = {
            "c_loc": c0["localite"] if c0 is not None else "",
            "c_date": c0["date"]    if c0 is not None else pd.NaT,
            "c_cp":   c0["cp"]      if c0 is not None else "",
            "c_pays": c0["pays"]    if c0 is not None else "",
            "d_loc":  d0["localite"]if d0 is not None else "",
            "d_date": d0["date"]    if d0 is not None else pd.NaT,
            "d_cp":   d0["cp"]      if d0 is not None else "",
            "d_pays": d0["pays"]    if d0 is not None else "",
        }
    return legs

def build_trips(d):
    trips = []
    for dos, g in d.groupby("dossier"):
        ch = g[g["type"] == "C"].sort_values("_hval")
        de = g[g["type"] == "D"].sort_values("_hval")
        c  = ch.iloc[0]  if len(ch) else None
        dd = de.iloc[-1] if len(de) else None
        base = c if c is not None else dd
        if base is None:
            continue
        trips.append({
            "dossier": dos,
            "has_c": c is not None, "has_d": dd is not None,
            "c_date": c["date"]   if c is not None else pd.NaT,
            "c_heure":c["heure"]  if c is not None else "",
            "c_loc":  c["localite"]if c is not None else "",
            "c_dept": c["dept"]   if c is not None else "",
            "c_pays": c["pays"]   if c is not None else "",
            "c_site": c["site"]   if c is not None else "",
            "d_date": dd["date"]  if dd is not None else pd.NaT,
            "d_heure":dd["heure"] if dd is not None else "",
            "d_loc":  dd["localite"]if dd is not None else "",
            "d_dept": dd["dept"]  if dd is not None else "",
            "d_pays": dd["pays"]  if dd is not None else "",
            "d_site": dd["site"]  if dd is not None else "",
            "chauffeur": base["chauffeur"], "immat": base["immat"],
            "remorque": base["remorque"],   "depart_trac": base["depart_trac"],
            "is_tra": bool(g["is_tra"].any()),
            "produit": (c["produit"] if c is not None and c["produit"] else base["produit"]),
            "plan_date": (c["date"]  if c is not None else dd["date"]),
            "plan_hval": float(c["_hval"] if c is not None else dd["_hval"]),
        })
    return trips

def html(s: str):
    st.markdown("\n".join(line.lstrip() for line in s.splitlines()), unsafe_allow_html=True)

# ─── Header ──────────────────────────────────────────────────────────────────
ptv_badge = ('<span class="badge ptv">PTV routing actif</span>' if PTV_AVAILABLE
             else '<span class="badge ptv off">PTV indisponible — géocodage OSM</span>')
st.markdown(f"""
<div class="hero">
  <div>
    <h1>🗂️ Planning Plateaux</h1>
    <p>Vue planeur — chargements &amp; déchargements par chauffeur, tracteur ou remorque, flotte CB et tractionnaires confondus.</p>
  </div>
  {ptv_badge}
</div>
""", unsafe_allow_html=True)

up = st.file_uploader("📋 Fichier des activités (chargements / déchargements)", type=["xlsx", "xls"])
if not up:
    st.info("👆 Chargez l'export des activités pour démarrer. "
            "Chaque ligne = une activité (chargement ou déchargement) rattachée à un N° Dossier.")
    st.stop()

df, COLS, ACT_DISTINCT, DATE_ORDER = load_activites(up.read())
if df.empty:
    st.error("Aucune ligne exploitable (colonne « N° Dossier » introuvable ou vide).")
    st.stop()

legs = build_dossier_legs(df)

with st.expander("🔧 Debug — colonnes détectées & valeurs Activité"):
    st.write("**Colonnes mappées :**", {k: v for k, v in COLS.items()})
    st.write("**Valeurs distinctes de « Activité » :**")
    st.dataframe(ACT_DISTINCT.rename("Nb").reset_index().rename(columns={"index": "Activité"}),
                 hide_index=True, use_container_width=True)
    n_unknown = int((df["type"] == "?").sum())
    if n_unknown:
        st.warning(f"⚠️ {n_unknown} activité(s) non classées. Vérifie le mapping ci-dessus.")
    _dd = df["date"].dropna()
    if not _dd.empty:
        st.write(f"**Format de date détecté :** `{DATE_ORDER}` — "
                 f"du {_dd.min().strftime('%d/%m/%Y')} au {_dd.max().strftime('%d/%m/%Y')} "
                 f"({_dd.dt.date.nunique()} jours).")

# ─── Filtres ─────────────────────────────────────────────────────────────────
st.markdown('<div class="sect">🎛️ Filtres planning <span class="hint">multiselect vide = tout confondu</span></div>',
            unsafe_allow_html=True)

f1, f2, f3 = st.columns([1.1, 1.1, 1])
with f1:
    dimension = st.radio("Dimension", ["Chauffeur", "Tracteur (immat.)", "Remorque"], horizontal=True)
    dim_col = {"Chauffeur": "chauffeur", "Tracteur (immat.)": "immat", "Remorque": "remorque"}[dimension]
with f2:
    flotte = st.radio("Périmètre", ["Tous", "Flotte CB", "Tractionnaires"], horizontal=True)
with f3:
    vue = st.radio("Vue", ["Par jour", "Par ressource"], horizontal=True)

df_scope = df.copy()
if flotte == "Flotte CB":
    df_scope = df_scope[~df_scope["is_tra"]]
elif flotte == "Tractionnaires":
    df_scope = df_scope[df_scope["is_tra"]]

options = sorted([v for v in df_scope[dim_col].dropna().unique() if str(v).strip()])
g1, g2 = st.columns([2.2, 1])
with g1:
    sel = st.multiselect(f"{dimension} — laisser vide pour tout confondu", options)
with g2:
    dts = df_scope["date"].dropna()
    if not dts.empty:
        dmin, dmax = dts.min().date(), dts.max().date()
        date_range = st.date_input("Période", value=(dmin, dmax),
                                    min_value=dmin, max_value=dmax, format="DD/MM/YYYY")
    else:
        date_range = None

dfx = df_scope.copy()
if sel:
    dfx = dfx[dfx[dim_col].isin(sel)]

def _range_bounds(dr):
    if dr is None:
        return None, None
    if isinstance(dr, (list, tuple)):
        if len(dr) == 0:
            return None, None
        if len(dr) == 1:
            return dr[0], dr[0]
        return dr[0], dr[1]
    return dr, dr

_lo, _hi = _range_bounds(date_range)
if _lo is not None:
    d0 = pd.Timestamp(_lo)
    d1 = pd.Timestamp(_hi) + pd.Timedelta(days=1)
    dfx = dfx[(dfx["date"] >= d0) & (dfx["date"] < d1)]

if dfx.empty:
    avail = sorted(df_scope["date"].dropna().dt.date.unique())
    if avail:
        lst = ", ".join(d.strftime("%d/%m/%Y") for d in avail[:15]) + (" …" if len(avail) > 15 else "")
        st.warning(f"Aucune activité sur cette sélection. Dates disponibles : {lst}")
    else:
        st.warning("Aucune activité ne correspond à ces filtres.")
    st.stop()

# ─── KPIs ────────────────────────────────────────────────────────────────────
n_charg = int((dfx["type"] == "C").sum())
n_dech  = int((dfx["type"] == "D").sum())
n_tra   = int(dfx["is_tra"].sum())

# ════════════════════════════════════════════════════════════════════════════════
# ─── CARTE (EN HAUT, AFFICHAGE DIRECT) ───────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="sect">🗺️ Carte des activités '
            '<span class="hint">taille &amp; chiffre = nb de dossiers · vert charg · bleu déch · arcs = liaisons</span></div>',
            unsafe_allow_html=True)

MAX_GEO = 120

# ── Options carte ─────────────────────────────────────────────────────────────
mc1, mc2, mc3, mc4 = st.columns([1.3, 1, 1, 1.5])
with mc1:
    dates_opt = sorted(dfx["date"].dropna().dt.date.unique())
    date_lbls = ["Toutes les dates"] + [d.strftime("%d/%m/%Y") for d in dates_opt]
    msel_date = st.selectbox("Date (carte)", date_lbls)
with mc2:
    show_mode = st.radio("Afficher", ["Les deux", "Chargements", "Déchargements"], horizontal=True)
with mc3:
    show_arcs = st.checkbox("Relier les points (arcs)", value=True)
with mc4:
    loc_opts = sorted({l for l in dfx["localite"] if str(l).strip()})
    focus_choice = st.selectbox("🔎 Isoler un point", ["— tout afficher"] + loc_opts)

dmap = dfx.copy()
if msel_date != "Toutes les dates":
    chosen = pd.to_datetime(msel_date, format="%d/%m/%Y").date()
    dmap = dmap[dmap["date"].dt.date == chosen]

if dmap.empty:
    st.info("Aucune activité pour ces filtres carte.")
else:
    clicked_norm = None
    try:
        _state = st.session_state.get("planmap")
        if _state and "selection" in _state:
            _objs = _state["selection"]["objects"]
            _pts  = _objs.get("pts") if isinstance(_objs, dict) else None
            if _pts:
                clicked_norm = _pts[0].get("loc_norm")
    except Exception:
        clicked_norm = None

    focus_norm = clicked_norm or (normalize(focus_choice) if focus_choice != "— tout afficher" else None)

    # ── Agrégat par lieu + type ───────────────────────────────────────────────
    agg = (dmap.assign(loc_norm=dmap["localite"].apply(normalize))
               .groupby(["loc_norm", "type"])
               .agg(localite=("localite", "first"), cp=("cp", "first"),
                    pays=("pays", "first"), pays_logi=("pays_logi", "first"),
                    dept=("dept", "first"),
                    camions=("dossier", "nunique"),
                    dossiers=("dossier", lambda s: ", ".join(sorted(set(s))[:10])))
               .reset_index())
    agg = agg[agg["localite"].str.strip() != ""]
    agg = agg.sort_values("camions", ascending=False).head(MAX_GEO)

    coords_cache, points = {}, []
    with st.spinner(f"📡 Géocodage de {len(agg)} lieux…"):
        for _, row in agg.iterrows():
            key = (row["loc_norm"], row["cp"], row["pays"])
            if key not in coords_cache:
                coords_cache[key] = geocode_cached(row["localite"], row["cp"], row["pays"])
            c = coords_cache[key]
            if c:
                n = int(row["camions"])
                points.append({
                    "nom": row["localite"], "loc_norm": row["loc_norm"], "label": str(n),
                    "camions": n, "typ": "Chargement" if row["type"] == "C" else "Déchargement",
                    "pays": row["pays"], "pays_logi": row["pays_logi"],
                    "dossiers": row["dossiers"],
                    "lat": c[0], "lon": c[1],
                    "radius": 900 + (n ** 0.5) * 1150,
                    "color": [74, 191, 106, 215] if row["type"] == "C" else [74, 138, 191, 215],
                    "type_code": row["type"],
                })

    # ── Arcs ─────────────────────────────────────────────────────────────────
    arcs = []
    for dos in dmap["dossier"].unique():
        lg = legs.get(dos, {})
        cn, dn = normalize(lg.get("c_loc", "")), normalize(lg.get("d_loc", ""))
        ck = (cn, lg.get("c_cp", ""), lg.get("c_pays", ""))
        dk = (dn, lg.get("d_cp", ""), lg.get("d_pays", ""))
        cc = coords_cache.get(ck) or (geocode_cached(lg.get("c_loc",""), lg.get("c_cp",""), lg.get("c_pays","")) if lg.get("c_loc") else None)
        dc = coords_cache.get(dk) or (geocode_cached(lg.get("d_loc",""), lg.get("d_cp",""), lg.get("d_pays","")) if lg.get("d_loc") else None)
        if cc and dc:
            arcs.append({"sl": cc[1], "sla": cc[0], "tl": dc[1], "tla": dc[0],
                         "dos": dos, "cn": cn, "dn": dn, "w": 1.6})

    # ── Application options (isolation > filtre type) ─────────────────────────
    if focus_norm:
        arcs_draw = [a for a in arcs if a["cn"] == focus_norm or a["dn"] == focus_norm]
        related   = {focus_norm} | {a["cn"] for a in arcs_draw} | {a["dn"] for a in arcs_draw}
        points    = [p for p in points if p["loc_norm"] in related]
        for a in arcs_draw:
            a["w"] = 3.0
        for p in points:
            if p["loc_norm"] == focus_norm:
                p["radius"] *= 1.5
                p["color"]   = p["color"][:3] + [255]
        foc_name = next((p["nom"] for p in points if p["loc_norm"] == focus_norm), focus_choice)
        st.info(f"🔎 Point isolé : **{foc_name}** — {len(arcs_draw)} liaison(s).")
    else:
        arcs_draw = arcs if show_arcs else []
        if show_mode == "Chargements":
            points = [p for p in points if p["type_code"] == "C"]
        elif show_mode == "Déchargements":
            points = [p for p in points if p["type_code"] == "D"]

    # ── Panneau pays ──────────────────────────────────────────────────────────
    # Comptage camions par pays logistique, avec détail des communes override
    def build_pays_panel(points_list, show_mode_param):
        """
        Renvoie un dict pays_logi → {total, details: [(loc, n)]}
        details = communes dont le pays_logi diffère du pays source (overrides frontaliers).
        """
        from collections import defaultdict
        pays_total  = defaultdict(int)
        pays_detail = defaultdict(list)   # pays → [(localite, n)]
        
        for p in points_list:
            pl   = p.get("pays_logi", p.get("pays", "??"))
            ps   = p.get("pays", "??")
            n    = p["camions"]
            pays_total[pl] += n
            # Si override frontalier : pays_logi != pays source normalisé
            ps_norm = pays_logistique("__no_override__", ps)  # juste normalisation
            if pl != ps_norm:  # commune remappée → on l'indique en détail
                pays_detail[pl].append((p["nom"], n))
        
        return pays_total, pays_detail

    # ── Initialisation avant le bloc conditionnel ──────────────────────────
    _render_map = False
    col_map_ref = None

    if points:
        pays_total, pays_detail = build_pays_panel(points, show_mode)

        title_mode = {"Les deux": "Tous", "Chargements": "Charg.", "Déchargements": "Déch."}[show_mode]

        from collections import defaultdict
        pays_rows = defaultdict(list)
        for _, row in dmap.iterrows():
            pl = row.get("pays_logi", row.get("pays", "??"))
            pays_rows[pl].append(row)

        if "pp_selected_pays" not in st.session_state:
            st.session_state["pp_selected_pays"] = None

        col_panel, col_map = st.columns([1, 5])
        col_map_ref = col_map  # ← référence gardée hors du with

        with col_panel:
            val_color = "#4a8abf" if show_mode == "Déchargements" else "#cdd4ea" if show_mode == "Les deux" else "#4abf6a"

            st.markdown(f"""
<style>
.pp-btn-wrap {{
    margin-bottom: .5rem;
    position: relative;
}}
.pp-btn-wrap [data-testid="stBaseButton-secondary"] {{
    position: absolute !important;
    inset: 0 !important;
    width: 100% !important;
    height: 100% !important;
    opacity: 0 !important;
    cursor: pointer !important;
    z-index: 2 !important;
    padding: 0 !important;
    margin: 0 !important;
    border: none !important;
    background: transparent !important;
}}
.pp-card-btn {{
    background: #141821;
    border: 1.5px solid #222838;
    border-radius: 10px;
    padding: 1rem 1.1rem .85rem;
    cursor: pointer;
    transition: border-color .15s, background .15s;
    font-family: 'Barlow Condensed', sans-serif;
    display: flex;
    flex-direction: column;
    gap: .15rem;
    min-height: 88px;
    position: relative;
    z-index: 1;
}}
.pp-card-btn:hover {{
    border-color: #3a4a6a;
    background: #1a2030;
}}
.pp-btn-wrap.active .pp-card-btn {{
    border-color: {val_color};
    background: #1a2b1f;
    box-shadow: 0 0 0 1px {val_color}33;
}}
.pp-row-top {{
    display: flex;
    align-items: baseline;
    gap: .5rem;
}}
.pp-flag {{ font-size: 1.6rem; line-height: 1; }}
.pp-code {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.5rem;
    font-weight: 700;
    color: #cdd4ea;
    letter-spacing: .5px;
    line-height: 1;
}}
.pp-num {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 2.4rem;
    font-weight: 800;
    color: {val_color};
    line-height: 1;
    margin-left: auto;
}}
.pp-detail-line {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: .75rem;
    font-weight: 600;
    color: #4a5470;
    letter-spacing: .2px;
    line-height: 1.4;
    margin-top: .3rem;
    border-top: 1px solid #1a2030;
    padding-top: .3rem;
}}
</style>""", unsafe_allow_html=True)

            st.markdown(
                f'<div style="font-size:.58rem;font-weight:700;letter-spacing:2.5px;'
                f'text-transform:uppercase;color:#3a4258;margin-bottom:.5rem;'
                f'font-family:\'Barlow Condensed\',sans-serif;">🚛 Camions · {title_mode}</div>',
                unsafe_allow_html=True)

            pays_order = sorted(pays_total.keys(), key=lambda k: -pays_total[k])
            for pays_code in pays_order:
                total     = pays_total[pays_code]
                flag      = PAYS_FLAGS.get(pays_code, "🏳️")
                details   = pays_detail.get(pays_code, [])
                is_active = st.session_state["pp_selected_pays"] == pays_code

                detail_html = ""
                if details:
                    parts = [f"+{n} {loc}" for loc, n in details[:4]]
                    detail_html = '<div class="pp-detail-line">⤷ ' + "  ·  ".join(parts) + '</div>'

                active_cls = "active" if is_active else ""
                st.markdown(f"""
<div class="pp-btn-wrap {active_cls}">
  <div class="pp-card-btn">
    <div class="pp-row-top">
      <span class="pp-flag">{flag}</span>
      <span class="pp-code">{pays_code}</span>
      <span class="pp-num">{total}</span>
    </div>
    {detail_html}
  </div>""", unsafe_allow_html=True)

                if st.button("\u200b", key=f"pp_btn_{pays_code}", use_container_width=True):
                    st.session_state["pp_selected_pays"] = (None if is_active else pays_code)
                    st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)

        with col_map:
            _render_map = True  # ← assigné ici, dans le bon contexte

        # ── Détail pays (sous la carte, pleine largeur) ────────────────────
        sel_pays = st.session_state.get("pp_selected_pays")
        if sel_pays and sel_pays in pays_rows:
            flag_s = PAYS_FLAGS.get(sel_pays, "🏳️")
            rows_sel = pays_rows[sel_pays]

            detail_records = []
            for row in rows_sel:
                dos = row["dossier"]
                lg  = legs.get(dos, {})
                detail_records.append({
                    "N° Dossier":  dos,
                    "Type":        "Chargement" if row["type"] == "C" else (
                                   "Déchargement" if row["type"] == "D" else "?"),
                    "Date":        row["date"].strftime("%d/%m/%Y") if pd.notna(row["date"]) else "—",
                    "Heure":       row["heure"] or "—",
                    "Localité":    row["localite"] or "—",
                    "Chauffeur":   row["chauffeur"] or "—",
                    "Tracteur":    row["immat"] or "—",
                    "Remorque":    row["remorque"] or "—",
                    "Flotte":      "TRA" if row["is_tra"] else "CB",
                    "Charg. →":    lg.get("c_loc", "—"),
                    "→ Déch.":     lg.get("d_loc", "—"),
                })

            df_detail = pd.DataFrame(detail_records).sort_values(["Date", "Heure", "N° Dossier"])
            n_dos = df_detail["N° Dossier"].nunique()
            st.markdown(
                f'<div class="sect">{flag_s} Détail {sel_pays} '
                f'<span class="hint">{n_dos} dossiers · {len(df_detail)} activités</span></div>',
                unsafe_allow_html=True)
            st.dataframe(df_detail, hide_index=True, use_container_width=True,
                         height=min(420, 38 + len(df_detail) * 36))

    else:
        st.info("Aucun lieu géocodé (vérifie le périmètre, ou PTV/OSM indisponible).")

    if _render_map and col_map_ref is not None and points:
        with col_map_ref:
            try:
                import pydeck as pdk
                dfp = pd.DataFrame(points)
                layers = [
                    pdk.Layer("ScatterplotLayer", data=dfp, id="pts",
                              get_position="[lon, lat]", get_radius="radius",
                              radius_min_pixels=8, radius_max_pixels=48,
                              get_fill_color="color", get_line_color=[255,255,255,110],
                              stroked=True, line_width_min_pixels=1, pickable=True,
                              auto_highlight=True),
                    pdk.Layer("TextLayer", data=dfp, get_position="[lon, lat]",
                              get_text="label", get_size=14, get_color=[10,14,18,255],
                              get_anchor="middle", get_alignment_baseline="'center'", font_weight=800),
                    pdk.Layer("TextLayer", data=dfp, get_position="[lon, lat]",
                              get_text="nom", get_size=11, get_color=[200,210,230,210],
                              get_anchor="middle", get_alignment_baseline="'bottom'",
                              get_pixel_offset=[0,-16]),
                ]
                if arcs_draw:
                    layers.insert(0, pdk.Layer("ArcLayer", data=pd.DataFrame(arcs_draw),
                        get_source_position="[sl, sla]", get_target_position="[tl, tla]",
                        get_source_color=[74,191,106,150], get_target_color=[74,138,191,170],
                        get_width="w", width_min_pixels=1))
                deck = pdk.Deck(
                    layers=layers,
                    initial_view_state=pdk.ViewState(
                        latitude=dfp["lat"].mean(),
                        longitude=dfp["lon"].mean(),
                        zoom=5, pitch=25),
                    tooltip={"html": "<b>{nom}</b><br>{typ} · <b>{camions}</b> dossier(s)<br>"
                                     "<span style='color:#8a93ad'>Dossiers : {dossiers}</span>",
                             "style": {"background":"#141821","color":"#cdd4ea",
                                       "font-family":"Barlow Condensed, sans-serif","padding":"9px"}},
                    map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
                )
                try:
                    st.pydeck_chart(deck, use_container_width=True, height=680,
                                    key="planmap", selection_mode="single-object", on_select="rerun")
                except TypeError:
                    st.pydeck_chart(deck, use_container_width=True, height=680)
                    st.caption("💡 Clic-pour-isoler indisponible sur cette version de Streamlit.")
                if len(agg) >= MAX_GEO and not focus_norm:
                    st.caption(f"Géocodage limité aux {MAX_GEO} lieux les plus actifs.")
            except ImportError:
                st.map(pd.DataFrame(points).rename(columns={"lat":"latitude","lon":"longitude"}))

# ─── Regroupements géographiques ─────────────────────────────────────────────
st.markdown('<div class="sect">📍 Regroupements géographiques <span class="hint">≥2 activités même jour · même département</span></div>',
            unsafe_allow_html=True)

clusters = []
for (d, dept, typ), g in dfx[dfx["dept"].str.len() > 0].groupby(
        [dfx["date"].dt.date, "dept", "type"]):
    if typ == "?" or len(g) < 2:
        continue
    clusters.append({
        "date": d, "dept": dept, "type": typ, "n": len(g),
        "pays": g["pays"].mode().iloc[0] if not g["pays"].mode().empty else "",
        "lieux": ", ".join(sorted(set(x for x in g["localite"] if x))[:6]),
    })
clusters.sort(key=lambda c: (-c["n"], c["date"]))

if clusters:
    cc = st.columns(2)
    for i, cl in enumerate(clusters[:12]):
        kind = "Chargements" if cl["type"] == "C" else "Déchargements"
        cls  = "" if cl["type"] == "C" else "d"
        flag = PAYS_FLAGS.get(cl["pays"], "")
        dnom = DEPT_NOM.get(cl["dept"], "")
        dlbl = f"Dépt {cl['dept']}" + (f" · {dnom}" if dnom else "")
        with cc[i % 2]:
            html(f"""
            <div class="cluster {cls}">
              <div class="ch">{flag} {cl['n']} {kind} — {dlbl}</div>
              <div class="cs">{cl['date'].strftime('%d/%m/%Y')} · {cl['lieux']}</div>
            </div>""")
    if len(clusters) > 12:
        st.caption(f"… et {len(clusters) - 12} autre(s) regroupement(s).")
else:
    st.caption("Aucune concentration ≥2 activités sur un même jour/département dans ce périmètre.")

# ─── Helpers tags ressources ──────────────────────────────────────────────────
def _badge(t):
    if t["is_tra"]:
        dep = (t["depart_trac"] or "").strip()
        extra = "" if (not dep or dep.upper() == "TRA") else f" · {dep}"
        return f'<span class="tag tra">TRA{extra}</span>'
    return '<span class="tag cb">CB</span>'

def _tags(t, with_badge=True):
    tg = [_badge(t)] if with_badge else []
    if t["chauffeur"]: tg.append(f'<span class="tag">👤 {t["chauffeur"]}</span>')
    if t["immat"]:     tg.append(f'<span class="tag">🚚 {t["immat"]}</span>')
    if t["remorque"]:  tg.append(f'<span class="tag">📦 {t["remorque"]}</span>')
    if t["produit"]:   tg.append(f'<span class="tag prod">🧪 {t["produit"][:22]}</span>')
    return "".join(tg)

def _ddate(t):
    diff = (pd.notna(t["d_date"]) and
            (pd.isna(t["plan_date"]) or t["d_date"].date() != t["plan_date"].date()))
    return f' · {t["d_date"].strftime("%d/%m")}' if diff else ""

# ════════════════════════════════════════════════════════════════════════════════
# ─── VUE PAR JOUR (dans un expander) ─────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════════
with st.expander(f"📅 Planning par jour — {vue}", expanded=False):

    if vue == "Par jour":
        lc1, lc2, _sp = st.columns([1.1, 1.5, 2])
        with lc1:
            layout = st.radio("Disposition", ["Lignes", "Cartes"], horizontal=True, key="layout_pj")
        with lc2:
            densite = st.select_slider("Densité", options=["Compact", "Normal", "Large"],
                                       value="Normal", key="dens_pj")
        dens_cls = {"Compact": "dens-compact", "Normal": "dens-normal", "Large": "dens-large"}[densite]

        df_sel = df_scope[df_scope[dim_col].isin(sel)] if sel else df_scope
        trips  = build_trips(df_sel)
        _lo2, _hi2 = _range_bounds(date_range)
        if _lo2 is not None:
            d0t, d1t = pd.Timestamp(_lo2), pd.Timestamp(_hi2)
            trips = [t for t in trips if pd.notna(t["plan_date"]) and d0t <= t["plan_date"] <= d1t]

        if not trips:
            st.warning("Aucun dossier sur cette période.")
        else:
            from collections import defaultdict
            by_day = defaultdict(list)
            for t in trips:
                by_day[t["plan_date"].date()].append(t)

            for day in sorted(by_day.keys()):
                day_trips = sorted(by_day[day], key=lambda t: t["plan_hval"])
                n_full = sum(1 for t in day_trips if t["has_c"] and t["has_d"])
                html(f'<div class="dayhead">{pd.Timestamp(day).strftime("%A %d %B %Y").capitalize()}'
                     f'<span class="cnt">{len(day_trips)} dossiers · {n_full} avec charg.+déch.</span></div>')

                if layout == "Cartes":
                    parts = ['<div class="trips">']
                    for t in day_trips:
                        cflag, dflag = PAYS_FLAGS.get(t["c_pays"], ""), PAYS_FLAGS.get(t["d_pays"], "")
                        cdept = f' · {t["c_dept"]}' if t["c_dept"] else ""
                        ddept = f' · {t["d_dept"]}' if t["d_dept"] else ""
                        leg_c = (f'<div class="leg c"><span class="lh">{t["c_heure"] or "—"}</span>'
                                 f'<span class="ll">{cflag} {(t["c_loc"] or "?").upper()}{cdept}</span>'
                                 f'<span class="ls">{t["c_site"] or "—"}</span></div>') if t["has_c"] \
                                else '<div class="leg c off">— chargement hors période —</div>'
                        leg_d = (f'<div class="leg d"><span class="lh">{t["d_heure"] or "—"}{_ddate(t)}</span>'
                                 f'<span class="ll">{dflag} {(t["d_loc"] or "?").upper()}{ddept}</span>'
                                 f'<span class="ls">{t["d_site"] or "—"}</span></div>') if t["has_d"] \
                                else '<div class="leg d off">— déchargement hors période —</div>'
                        parts.append(
                            f'<div class="trip"><div class="trip-h">'
                            f'<span class="dos">N° {t["dossier"]}</span>'
                            f'<span class="trip-tags">{_tags(t)}</span></div>'
                            f'{leg_c}<div class="arrow">↓</div>{leg_d}</div>')
                    parts.append('</div>')
                    html("".join(parts))

                else:  # Lignes
                    parts = [f'<div class="rows {dens_cls}">']
                    for t in day_trips:
                        cflag, dflag = PAYS_FLAGS.get(t["c_pays"], ""), PAYS_FLAGS.get(t["d_pays"], "")
                        cdept = f' · {t["c_dept"]}' if t["c_dept"] else ""
                        ddept = f' · {t["d_dept"]}' if t["d_dept"] else ""
                        cell_c = (f'<div class="leg2 c"><span class="lh">{t["c_heure"] or "—"}</span>'
                                  f'<span class="ll">{cflag} {(t["c_loc"] or "?").upper()}{cdept}</span>'
                                  f'<span class="ls">{t["c_site"] or ""}</span></div>') if t["has_c"] \
                                 else '<div class="leg2 off">— chargement hors période —</div>'
                        cell_d = (f'<div class="leg2 d"><span class="lh">{t["d_heure"] or "—"}{_ddate(t)}</span>'
                                  f'<span class="ll">{dflag} {(t["d_loc"] or "?").upper()}{ddept}</span>'
                                  f'<span class="ls">{t["d_site"] or ""}</span></div>') if t["has_d"] \
                                 else '<div class="leg2 off">— déchargement hors période —</div>'
                        parts.append(
                            f'<div class="row">'
                            f'<div class="c1"><span class="dos">N° {t["dossier"]}</span>{_badge(t)}</div>'
                            f'{cell_c}<div class="rarrow">→</div>{cell_d}'
                            f'<div class="res">{_tags(t, with_badge=False)}</div></div>')
                    parts.append('</div>')
                    html("".join(parts))

    # ── Vue PAR RESSOURCE (swimlane) ──────────────────────────────────────────
    else:
        st.markdown(f'<div class="sect">🚚 Planning par {dimension.lower()} '
                    f'<span class="hint">enchaînement chronologique des activités</span></div>',
                    unsafe_allow_html=True)

        resources = [r for r in dfx[dim_col].dropna().unique() if str(r).strip()]
        resources = sorted(resources, key=lambda r: -len(dfx[dfx[dim_col] == r]))
        MAX_LANES = 40
        for r in resources[:MAX_LANES]:
            gr = dfx[dfx[dim_col] == r].sort_values(["date", "_hval"])
            is_tra = bool(gr["is_tra"].any())
            nb = len(gr)
            meta_bits = []
            if dim_col != "chauffeur":
                chs = sorted(set(x for x in gr["chauffeur"] if x))
                if chs:
                    meta_bits.append("👤 " + ", ".join(chs[:3]))
            if dim_col != "remorque":
                rms = sorted(set(x for x in gr["remorque"] if x))
                if rms:
                    meta_bits.append("📦 " + ", ".join(rms[:3]))
            tra_badge = '<span class="tag tra" style="font-size:.66rem">TRA</span>' if is_tra else ''
            stops = ""
            for _, row in gr.iterrows():
                kl = "c" if row["type"] == "C" else ("d" if row["type"] == "D" else "")
                dlabel = row["date"].strftime("%d/%m") if pd.notna(row["date"]) else "—"
                stops += (f'<span class="stop {kl}"><span class="t">{dlabel} {row["heure"]}</span>'
                          f'{row["localite"].upper() or "?"}</span>')
            html(f"""
            <div class="lane">
              <div class="who">{tra_badge}{r}
                <span class="meta">· {nb} activités{(" · " + " · ".join(meta_bits)) if meta_bits else ""}</span></div>
              <div class="flow">{stops}</div>
            </div>""")
        if len(resources) > MAX_LANES:
            st.caption(f"Affichage des {MAX_LANES} ressources les plus actives. "
                       "Affine via le multiselect pour le reste.")

# ─── Tableau & export ────────────────────────────────────────────────────────
with st.expander("📋 Tableau détaillé + export"):
    show = dfx.copy()
    show["Type"]   = show["type"].map({"C":"Chargement","D":"Déchargement","?":"?"})
    show["Flotte"] = np.where(show["is_tra"], "Tractionnaire", "CB")
    show["Date"]   = show["date"].dt.strftime("%d/%m/%Y")
    table = show[["Date","heure","Type","dossier","localite","dept","pays",
                  "site","produit","chauffeur","immat","remorque","Flotte","depart_trac"]].rename(columns={
        "heure":"Heure","dossier":"N° Dossier","localite":"Localité","dept":"Dépt",
        "pays":"Pays","site":"Site","produit":"Produit","chauffeur":"Chauffeur",
        "immat":"Immat. tracteur","remorque":"Remorque","depart_trac":"Départ. tracteur"})
    st.dataframe(table, hide_index=True, use_container_width=True)

    buf = io.BytesIO()
    table.to_excel(buf, index=False, engine="openpyxl")
    st.download_button("📥 Exporter Excel", data=buf.getvalue(),
                       file_name="planning_plateaux.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
