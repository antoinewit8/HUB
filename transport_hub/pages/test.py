"""
Test péages PTV — ventilation par pays.

Page de diagnostic avant intégration dans la Carte Manuelle.
Deux appels sur le même trajet, comparés côte à côte :

  1. PTV Developer en direct (depuis Python, la clé ne quitte pas le serveur
     Streamlit) → vérité terrain : structure réelle du bloc `toll`.
  2. Le serveur cartes Render (/api/recalculate) → ce que la carte reçoit
     vraiment : la clé `toll_by_country` est-elle là, et juste ?

La fonction `toll_by_country()` ci-dessous produit exactement le format lu par
map.html : [{"country": "DE", "price": 112.4}, ...] trié par montant décroissant.
Une fois validée ici, elle se colle telle quelle dans map_server_main.py à la
place de `_extract_toll_by_country()`.
"""

import inspect
import json
import os
import re
import time

import pandas as pd
import requests
import streamlit as st

try:
    st.set_page_config(page_title="Test péages PTV", page_icon="🧪", layout="wide")
except Exception:
    pass  # déjà défini par le hub

RESULT_SCHEMA = "peages_v1"
PTV_URL = "https://api.myptv.com/routing/v1/routes"
NAVY, ROYAL = "#003087", "#0057A8"

PRESETS = {
    "Liège → Rotterdam (BE, NL)":            [(50.6326, 5.5797), (51.9225, 4.4792)],
    "Bettembourg → München (LU, DE)":        [(49.5186, 6.1022), (48.1374, 11.5755)],
    "Liège → Lyon (BE, LU, FR)":             [(50.6326, 5.5797), (45.7640, 4.8357)],
    "Bettembourg → Wien (LU, DE, AT)":       [(49.5186, 6.1022), (48.2082, 16.3738)],
    "Liège → Randers (BE, NL, DE, DK)":      [(50.6326, 5.5797), (56.4607, 10.0364)],
    "Bettembourg → Milano (LU, FR, CH, IT)": [(49.5186, 6.1022), (45.4642, 9.1900)],
}
CUSTOM = "Trajet personnalisé"

DEFAULT_VEHICLE = """vehicle[emissionStandard]=EURO_6
vehicle[co2EmissionClass]=1
vehicle[totalPermittedWeight]=40000
vehicle[numberOfAxles]=5"""


# ════════════════════════════════════════════════════════════════════════════
#  EXTRACTION — fonction à reprendre telle quelle dans map_server_main.py
# ════════════════════════════════════════════════════════════════════════════

def toll_by_country(ptv: dict) -> list:
    """
    Ventilation du péage par pays : [{"country": "BE", "price": 43.35}, ...].

    Structure PTV Developer v1 constatée (réponse du 16/09/2026) :
      toll.costs.countries[] = {countryCode, price: {price, currency},
                                convertedPrice: {price, currency}}
      toll.sections[]        = {countryCode, tollSystemIndex, displayName,
                                costs: [{price, currency, convertedPrice: {...}}]}
      toll.systems[]         = {name, operatorName, tariffVersion}  (pas de pays)

    1. toll.costs.countries (détail natif, somme = total PTV)
    2. repli : agrégation de toll.sections par countryCode
    Le prix converti (EUR, via options[currency]=EUR) prime toujours.
    """
    def _montant(obj):
        if not isinstance(obj, dict):
            return None
        for cle in ("convertedPrice", "price"):
            v = obj.get(cle)
            if isinstance(v, dict):
                v = v.get("price")
            if isinstance(v, (int, float)):
                return float(v)
        return None

    toll = (ptv or {}).get("toll") or {}
    agrege = {}

    for c in (toll.get("costs") or {}).get("countries") or []:
        cc, m = c.get("countryCode"), _montant(c)
        if cc and m is not None:
            agrege[cc] = agrege.get(cc, 0.0) + m

    if not agrege:
        for sec in toll.get("sections") or []:
            cc = sec.get("countryCode")
            if not cc:
                continue
            for ligne in sec.get("costs") or []:
                m = _montant(ligne)
                if m is not None:
                    agrege[cc] = agrege.get(cc, 0.0) + m

    return sorted(({"country": k, "price": round(v, 2)} for k, v in agrege.items()),
                  key=lambda x: -x["price"])


def km_by_country(ptv: dict) -> list:
    """
    Kilomètres parcourus par pays : [{"country": "BE", "km": 168.2}, ...].

    PTV ne fournit pas ce total : on le reconstitue à partir des événements.
      - WAYPOINT_EVENTS : le premier événement (distanceFromStart = 0) porte le
        countryCode du départ.
      - BORDER_EVENTS   : chaque passage de frontière porte distanceFromStart
        et border.countryCode = pays dans lequel on entre.
    La distance totale est découpée entre ces jalons ; la somme des pays est
    donc égale à la distance de la route (aux arrondis près).
    """
    total_m = ptv.get("distance") or 0
    events = sorted((e for e in (ptv.get("events") or []) if isinstance(e, dict)),
                    key=lambda e: e.get("distanceFromStart") or 0)
    if not total_m or not events:
        return []   # pas d'événements reçus : ventilation inconnue

    def _pays_entree(e):
        b = e.get("border")
        if isinstance(b, dict):
            return b.get("countryCode") or e.get("countryCode")
        return None

    # Pays de départ : premier événement non-frontière, sinon repli sur la
    # première section de péage, sinon inconnu
    depart = None
    for e in events:
        if "border" not in e and e.get("countryCode"):
            depart = e["countryCode"]
            break
    if not depart:
        secs = ((ptv.get("toll") or {}).get("sections") or [])
        premiere_frontiere = next((e for e in events if "border" in e), None)
        if secs and not premiere_frontiere:
            depart = secs[0].get("countryCode")
    depart = depart or "??"

    agrege, pays, debut = {}, depart, 0
    for e in events:
        entree = _pays_entree(e)
        if not entree:
            continue
        d = e.get("distanceFromStart") or 0
        if d > debut:
            agrege[pays] = agrege.get(pays, 0) + (d - debut)
        pays, debut = entree, max(d, debut)
    if total_m > debut:
        agrege[pays] = agrege.get(pays, 0) + (total_m - debut)

    return sorted(({"country": k, "km": round(v / 1000, 1)} for k, v in agrege.items() if v > 0),
                  key=lambda x: -x["km"])


# ════════════════════════════════════════════════════════════════════════════
#  OUTILS DE DIAGNOSTIC (page uniquement)
# ════════════════════════════════════════════════════════════════════════════

def _secret(name: str) -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, "")


_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)\s*$")


def resoudre_point(texte: str):
    """'lat,lon' direct, sinon Nominatim. Renvoie (lat, lon, libellé) ou None."""
    m = _COORD_RE.match(texte or "")
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon, f"{lat:.5f},{lon:.5f}"
    if not (texte or "").strip():
        return None
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": texte, "format": "json", "limit": 1},
            headers={"User-Agent": "CBGroupe-HUB-test-peages"},
            timeout=15,
        )
        r.raise_for_status()
        res = r.json()
        if res:
            return float(res[0]["lat"]), float(res[0]["lon"]), res[0].get("display_name", texte)
    except Exception:
        pass
    return None


def total_ptv(ptv: dict):
    costs = ((ptv or {}).get("toll") or {}).get("costs") or {}
    conv = costs.get("convertedPrice")
    if isinstance(conv, dict) and isinstance(conv.get("price"), (int, float)):
        return float(conv["price"])
    prices = costs.get("prices") or []
    eur = [p.get("price") for p in prices if isinstance(p, dict) and p.get("currency") == "EUR"]
    if eur:
        return float(sum(eur))
    return None


def source_ventilation(ptv: dict) -> str:
    toll = (ptv or {}).get("toll") or {}
    if (toll.get("costs") or {}).get("countries") or toll.get("countries"):
        return "toll.costs.countries (détail natif PTV)"
    if toll.get("sections"):
        return "agrégation de toll.sections (repli)"
    return "aucune — pas de bloc toll exploitable"


def table_sections(ptv: dict) -> pd.DataFrame:
    toll = (ptv or {}).get("toll") or {}
    systems = toll.get("systems") or []
    rows = []
    for i, sec in enumerate(toll.get("sections") or []):
        idx = sec.get("tollSystemIndex")
        sys_ = systems[idx] if isinstance(idx, int) and 0 <= idx < len(systems) else {}
        for ligne in sec.get("costs") or [{}]:
            conv = (ligne or {}).get("convertedPrice") or {}
            rows.append({
                "section": i,
                "pays": sec.get("countryCode") or "",
                "libellé": sec.get("displayName") or "",
                "système": sys_.get("name") or "",
                "tarif": sys_.get("tariffVersion") or "",
                "km": round((sec.get("calculatedDistance") or 0) / 1000, 1),
                "prix": (ligne or {}).get("price"),
                "devise": (ligne or {}).get("currency"),
                "prix EUR": conv.get("price"),
                "approximé": sec.get("approximated"),
            })
    df = pd.DataFrame(rows)
    if not df.empty and df["km"].gt(0).any():
        df["€/km"] = (df["prix EUR"].fillna(df["prix"]) / df["km"].where(df["km"] > 0)).round(3)
    return df


def appel_ptv(points, api_key, results, vehicle_lines, avoid_tolls):
    params = [("waypoints", f"{lat},{lon}") for lat, lon in points]
    params += [
        ("results", results),
        ("profile", "EUR_TRAILER_TRUCK"),
        ("options[currency]", "EUR"),
    ]
    if avoid_tolls:
        params.append(("options[avoid]", "TOLL"))
    for line in vehicle_lines:
        if "=" in line:
            k, v = line.split("=", 1)
            if k.strip():
                params.append((k.strip(), v.strip()))
    t0 = time.time()
    r = requests.get(PTV_URL, params=params, headers={"apiKey": api_key}, timeout=60)
    duree = time.time() - t0
    try:
        body = r.json()
    except ValueError:
        body = {"_texte_brut": r.text[:3000]}
    return {"status": r.status_code, "duree": duree, "json": body, "params": params}


def empreinte_serveur(base: str) -> dict:
    """
    Identifie la version qui tourne sur Render sans y avoir accès :
    la version patchée a ajouté le paramètre `country` à /api/geocode.
    """
    out = {"openapi": False, "endpoints": [], "geocode_country": None, "erreur": None}
    try:
        r = requests.get(base + "/openapi.json", timeout=30)
        if r.status_code != 200:
            out["erreur"] = f"/openapi.json → HTTP {r.status_code}"
            return out
        spec = r.json()
        out["openapi"] = True
        paths = spec.get("paths") or {}
        out["endpoints"] = sorted(paths)
        params = ((paths.get("/api/geocode") or {}).get("get") or {}).get("parameters") or []
        out["geocode_country"] = any(p.get("name") == "country" for p in params)
    except Exception as e:
        out["erreur"] = str(e)
    return out


def sonde_geocode(base: str, texte: str, attendu) -> dict:
    """Envoie 'lat,lon' à /api/geocode pour voir où le serveur le place réellement."""
    out = {"envoyé": texte, "attendu": list(attendu), "reçu": None, "écart_km": None, "erreur": None}
    try:
        r = requests.get(base + "/api/geocode", params={"q": texte}, timeout=30)
        if r.status_code != 200:
            out["erreur"] = f"HTTP {r.status_code} — {r.text[:150]}"
            return out
        d = r.json()
        if isinstance(d.get("results"), list) and d["results"]:
            d = d["results"][0]
        lat, lng = d.get("lat"), d.get("lng", d.get("lon"))
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            out["reçu"] = [lat, lng]
            out["écart_km"] = round(dist_km(attendu, (lat, lng)), 1)
    except Exception as e:
        out["erreur"] = str(e)
    return out


def dist_km(a, b) -> float:
    from math import radians, sin, cos, asin, sqrt
    la1, lo1, la2, lo2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(h))


def appel_serveur(server_url, points, avoid_tolls):
    base = server_url.rstrip("/")
    try:
        requests.get(base + "/", timeout=90)  # réveil Render
    except Exception:
        pass
    o, d, via = points[0], points[-1], points[1:-1]
    body = {
        "origin": f"{o[0]:.6f},{o[1]:.6f}",
        "dest": f"{d[0]:.6f},{d[1]:.6f}",
        "origin_coords": [o[0], o[1]],
        "dest_coords": [d[0], d[1]],
        "via": [[p[0], p[1]] for p in via],
        "waypoints": [f"{p[0]:.6f},{p[1]:.6f}" for p in via],
        "avoid_tolls": avoid_tolls,
        "avoid_highways": False,
    }
    empreinte = empreinte_serveur(base)
    t0 = time.time()
    r = requests.post(base + "/api/recalculate", json=body, timeout=120)
    duree = time.time() - t0
    try:
        rep = r.json()
    except ValueError:
        rep = {"_texte_brut": r.text[:3000]}
    sondes = [sonde_geocode(base, body["origin"], o), sonde_geocode(base, body["dest"], d)]
    return {"status": r.status_code, "duree": duree, "json": rep, "body": body,
            "empreinte": empreinte, "sondes": sondes}


def df_pays(lignes) -> pd.DataFrame:
    if not lignes:
        return pd.DataFrame(columns=["country", "price"])
    return pd.DataFrame(lignes)[["country", "price"]]


def sans_polyline(d):
    if not isinstance(d, dict):
        return d
    out = dict(d)
    for k in ("polyline", "coordinates", "geometry"):
        if k in out and isinstance(out[k], (list, str)):
            n = len(out[k])
            out[k] = f"<{n} éléments masqués>"
    return out


# ════════════════════════════════════════════════════════════════════════════
#  INTERFACE
# ════════════════════════════════════════════════════════════════════════════

st.markdown(
    f"""<style>
    .pt-head {{ border-bottom: 3px solid {NAVY}; padding-bottom: .4rem; margin-bottom: 1rem; }}
    .pt-head h1 {{ color: {NAVY}; margin: 0; font-size: 1.9rem; }}
    .pt-head p {{ color: #4a5568; margin: .2rem 0 0; }}
    .pt-ok {{ color: #1e7b34; font-weight: 600; }}
    .pt-ko {{ color: #b3261e; font-weight: 600; }}
    </style>
    <div class="pt-head"><h1>Test péages PTV par pays</h1>
    <p>Même trajet envoyé à PTV en direct et au serveur cartes, pour valider la ventilation
    avant de la brancher dans la Carte Manuelle.</p></div>""",
    unsafe_allow_html=True,
)

# Purge d'un état d'une ancienne version de la page
if st.session_state.get("peage_test", {}).get("schema") != RESULT_SCHEMA:
    st.session_state.pop("peage_test", None)

c1, c2 = st.columns([3, 2])

with c1:
    choix = st.selectbox("Trajet", list(PRESETS) + [CUSTOM])
    if choix == CUSTOM:
        dep = st.text_input("Départ (adresse ou lat,lon)", "Liège, Belgique")
        arr = st.text_input("Arrivée (adresse ou lat,lon)", "Rotterdam, Nederland")
        via_txt = st.text_area("Étapes (une par ligne, facultatif)", "", height=80)
    avoid_tolls = st.checkbox("Éviter les péages", value=False,
                              help="Utile pour vérifier que la ventilation tombe bien à zéro.")

with c2:
    key_env = _secret("PTV_API_KEY")
    srv_env = _secret("MAP_SERVER_URL")
    test_ptv = st.checkbox("Appeler PTV en direct", value=True)
    if key_env:
        st.caption("Clé PTV trouvée dans les secrets / variables d'environnement.")
        api_key = key_env
    else:
        api_key = st.text_input("Clé PTV", type="password",
                                help="Absente des secrets : saisie pour cette session uniquement.")
    test_srv = st.checkbox("Appeler le serveur cartes (/api/recalculate)", value=True)
    server_url = st.text_input("URL du serveur cartes", srv_env,
                               placeholder="https://xxx.onrender.com")

with st.expander("Paramètres PTV"):
    results = st.text_input("results", "TOLL_COSTS,TOLL_SECTIONS,TOLL_SYSTEMS,BORDER_EVENTS,WAYPOINT_EVENTS",
                            help="TOLL_COSTS est indispensable. TOLL_SECTIONS et TOLL_SYSTEMS "
                                 "servent au repli par sections.")
    use_vehicle = st.checkbox("Envoyer les paramètres véhicule", value=False,
                              help="Désactivé = profil EUR_TRAILER_TRUCK seul, comme le serveur "
                                   "actuel. Activer pour mesurer l'effet sur DE, AT et NL.")
    vehicle_txt = st.text_area("Une ligne par paramètre", DEFAULT_VEHICLE, height=110,
                               disabled=not use_vehicle)

lancer = st.button("Lancer le test", type="primary", use_container_width=True)

if lancer:
    try:
        # Points
        if choix == CUSTOM:
            bruts = [dep] + [l for l in via_txt.splitlines() if l.strip()] + [arr]
            points, libelles = [], []
            with st.spinner("Géocodage…"):
                for b in bruts:
                    p = resoudre_point(b)
                    if not p:
                        st.error(f"Point introuvable : « {b} ». Saisissez-le en lat,lon.")
                        st.stop()
                    points.append((p[0], p[1]))
                    libelles.append(p[2])
        else:
            points = PRESETS[choix]
            libelles = [f"{a:.4f},{b:.4f}" for a, b in points]

        res = {"schema": RESULT_SCHEMA, "trajet": choix, "points": points,
               "libelles": libelles, "ptv": None, "srv": None}

        if test_ptv:
            if not api_key:
                st.error("Clé PTV manquante : ajoutez PTV_API_KEY aux secrets ou saisissez-la.")
            else:
                with st.spinner("Appel PTV…"):
                    lignes = vehicle_txt.splitlines() if use_vehicle else []
                    res["ptv"] = appel_ptv(points, api_key, results, lignes, avoid_tolls)

        if test_srv:
            if not server_url:
                st.error("URL du serveur cartes manquante.")
            else:
                with st.spinner("Réveil et appel du serveur cartes (jusqu'à 1 min si Render dort)…"):
                    try:
                        res["srv"] = appel_serveur(server_url, points, avoid_tolls)
                    except Exception as e:
                        res["srv"] = {"status": None, "duree": 0, "json": {}, "erreur": str(e)}

        st.session_state["peage_test"] = res
    except Exception as e:
        st.session_state.pop("peage_test", None)
        st.error(f"Échec du test : {e}")

res = st.session_state.get("peage_test")
if not res:
    st.info("Choisissez un trajet et lancez le test.")
    st.stop()

st.caption(" / ".join(res["libelles"]))

ptv = res.get("ptv")
srv = res.get("srv")
ptv_ok = bool(ptv and ptv["status"] == 200)
srv_ok = bool(srv and srv.get("status") == 200)
lignes_ptv = toll_by_country(ptv["json"]) if ptv_ok else None
km_ptv_pays = km_by_country(ptv["json"]) if ptv_ok else None

tab_diag, tab_ptv, tab_srv, tab_code = st.tabs(
    ["Diagnostic", "PTV direct", "Serveur cartes", "Code à intégrer"])

# ── Diagnostic ──────────────────────────────────────────────────────────────
with tab_diag:
    constats = []

    if ptv is None:
        constats.append(("info", "PTV direct non testé."))
    elif not ptv_ok:
        constats.append(("ko", f"PTV répond {ptv['status']}. Détail dans l'onglet PTV direct "
                               "(souvent un paramètre véhicule ou un results non reconnu)."))
    else:
        total = total_ptv(ptv["json"])
        somme = sum(l["price"] for l in lignes_ptv)
        constats.append(("ok", f"PTV direct : {len(lignes_ptv)} pays, source "
                               f"{source_ventilation(ptv['json'])}."))
        if total is not None and lignes_ptv:
            ecart = somme - total
            if abs(ecart) <= 0.05:
                constats.append(("ok", f"Somme par pays {somme:.2f} € = total PTV {total:.2f} €."))
            else:
                constats.append(("ko", f"Somme par pays {somme:.2f} € ≠ total PTV {total:.2f} € "
                                       f"(écart {ecart:+.2f} €). Vérifier le tableau des sections."))
        elif total and not lignes_ptv:
            constats.append(("ko", f"PTV facture {total:.2f} € mais aucune ventilation n'est "
                                   "exploitable. Envoyez-moi le JSON brut de l'onglet PTV direct."))

    if ptv_ok:
        j = ptv["json"]
        dist_ptv = (j.get("distance") or 0) / 1000
        if not km_ptv_pays:
            constats.append(("ko", "Aucun km par pays : ajoutez BORDER_EVENTS,WAYPOINT_EVENTS dans results."))
        else:
            somme_km = sum(r["km"] for r in km_ptv_pays)
            inconnu = any(r["country"] == "??" for r in km_ptv_pays)
            niveau = "ok" if abs(somme_km - dist_ptv) <= 0.3 and not inconnu else "ko"
            constats.append((niveau, "Km par pays : " + ", ".join("%s %.1f" % (r["country"], r["km"]) for r in km_ptv_pays) 
                                     + f" = {somme_km:.1f} km pour {dist_ptv:.1f} km de route"
                                     + (" — pays de départ non identifié" if inconnu else "") + "."))
        if (j.get("toll") or {}).get("costs", {}).get("containsApproximatedSections"):
            constats.append(("ko", "PTV signale des sections de péage approximées : montant indicatif."))
        if j.get("violated"):
            constats.append(("ko", "violated = true : le trajet enfreint une restriction du profil "
                                   "véhicule (tonnage, interdiction PL…). Montant à prendre avec prudence."))
        for w in j.get("warnings") or []:
            det = w.get("details") or {}
            constats.append(("info", f"Avertissement PTV {w.get('warningCode')} "
                                     + (f"({', '.join(f'{k}: {v}' for k, v in det.items())})" if det else "")))

    if srv is None:
        constats.append(("info", "Serveur cartes non testé."))
    elif not srv_ok:
        constats.append(("ko", f"Serveur cartes : {srv.get('erreur') or 'HTTP ' + str(srv.get('status'))}."))
    else:
        d = srv["json"] if isinstance(srv["json"], dict) else {}
        emp = srv.get("empreinte") or {}

        if ptv_ok:
            km_ptv = (ptv["json"].get("distance") or 0) / 1000
            km_srv = d.get("distance_km")
            if isinstance(km_srv, (int, float)) and km_ptv > 0:
                ecart = (km_srv - km_ptv) / km_ptv * 100
                if abs(ecart) > 5:
                    constats.append(("ko", f"Le serveur ne calcule pas le même trajet : {km_srv:.1f} km "
                                           f"contre {km_ptv:.1f} km en PTV direct ({ecart:+.0f} %). "
                                           "Ses péages sont donc faux, pas seulement non ventilés."))
                else:
                    constats.append(("ok", f"Même trajet : {km_srv:.1f} km contre {km_ptv:.1f} km."))
            t_ptv = total_ptv(ptv["json"])
            try:
                t_srv = float(d.get("prix_peage"))
            except (TypeError, ValueError):
                t_srv = None
            if t_ptv is not None and t_srv is not None and abs(t_srv - t_ptv) > 0.5:
                constats.append(("ko", f"Total péage serveur {t_srv:.2f} € contre {t_ptv:.2f} € en PTV direct."))

        for sd in srv.get("sondes") or []:
            if sd.get("écart_km") is not None and sd["écart_km"] > 1:
                constats.append(("ko", f"/api/geocode place « {sd['envoyé']} » à {sd['écart_km']:.0f} km "
                                       f"du point réel ({sd['reçu'][0]:.4f},{sd['reçu'][1]:.4f}) : "
                                       "les coordonnées sont traitées comme une adresse."))

        if "km_by_country" not in d:
            constats.append(("ko", "Le serveur ne renvoie pas km_by_country : déployer le nouveau "
                                   "map_server_main.py sur Cartes-bot-."))
        elif km_ptv_pays is not None:
            a_ = {r["country"]: r["km"] for r in km_ptv_pays}
            b_ = {r.get("country"): r.get("km") for r in d["km_by_country"] or []}
            ecarts = [cc for cc in set(a_) | set(b_) if abs((a_.get(cc) or 0) - (b_.get(cc) or 0)) > 0.5]
            constats.append(("ko", f"Km par pays serveur ≠ PTV direct sur : {', '.join(sorted(ecarts))}.")
                            if ecarts else ("ok", "Km par pays identiques entre serveur et PTV direct."))

        if "toll_by_country" not in d:
            if emp.get("geocode_country") is True:
                constats.append(("ko", "Le serveur tourne bien en version patchée (geocode accepte "
                                       "`country`), mais /api/recalculate renvoie une réponse sans "
                                       "toll_by_country. Cause probable : réponse servie depuis un "
                                       "cache de routes antérieur au patch, ou `return` anticipé "
                                       "avant l'ajout de la clé."))
            elif emp.get("geocode_country") is False:
                constats.append(("ko", "Le serveur tourne sur l'ANCIENNE version (geocode sans "
                                       "`country`). Le patch n'est pas déployé : commit non poussé, "
                                       "build Render en échec, ou Start Command qui lance un autre "
                                       "fichier que tools/km_calcul/map_server_main.py."))
            else:
                constats.append(("ko", "Le serveur ne renvoie pas toll_by_country et sa version n'a "
                                       "pas pu être identifiée ("
                                       + (emp.get("erreur") or "openapi indisponible")
                                       + "). Vérifier le dernier déploiement Render."))
        elif not d["toll_by_country"]:
            constats.append(("ko" if lignes_ptv else "ok",
                             "toll_by_country présent mais vide"
                             + (" alors que PTV ventile : results du serveur sans TOLL_SECTIONS "
                                "ou extracteur à remplacer." if lignes_ptv else ".")))
        else:
            constats.append(("ok", f"toll_by_country présent : {len(d['toll_by_country'])} pays."))
            if lignes_ptv is not None:
                a = {l["country"]: l["price"] for l in lignes_ptv}
                b = {l.get("country"): l.get("price") for l in d["toll_by_country"]}
                diffs = [cc for cc in set(a) | set(b)
                         if abs((a.get(cc) or 0) - (b.get(cc) or 0)) > 0.05]
                if not diffs:
                    constats.append(("ok", "Serveur et PTV direct identiques pays par pays."))
                else:
                    constats.append(("ko", f"Écarts serveur / PTV direct sur : {', '.join(sorted(diffs))}. "
                                           "Cause probable : paramètres véhicule différents, "
                                           "ou cache de route côté serveur."))

    for niveau, txt in constats:
        {"ok": st.success, "ko": st.error, "info": st.info}[niveau](txt)

    if km_ptv_pays:
        st.markdown("**Kilomètres par pays (PTV direct)**")
        dfk = pd.DataFrame(km_ptv_pays).rename(columns={"country": "Pays", "km": "Km"})
        st.bar_chart(dfk.set_index("Pays"), color="#16a085")

    if lignes_ptv:
        st.markdown("**Ventilation PTV direct**")
        dfp = df_pays(lignes_ptv).rename(columns={"country": "Pays", "price": "Péage (€)"})
        st.bar_chart(dfp.set_index("Pays"), color=ROYAL)

# ── PTV direct ──────────────────────────────────────────────────────────────
with tab_ptv:
    if ptv is None:
        st.info("Non testé.")
    else:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("HTTP", ptv["status"])
        m2.metric("Durée", f"{ptv['duree']:.1f} s")
        if ptv_ok:
            j = ptv["json"]
            m3.metric("Distance", f"{(j.get('distance') or 0) / 1000:,.1f} km".replace(",", " "))
            t = total_ptv(j)
            m4.metric("Péage total", f"{t:.2f} €" if t is not None else "—")

            toll = j.get("toll") or {}
            st.markdown("**Structure reçue**")
            st.write({
                "toll présent": bool(toll),
                "clés de toll": sorted(toll.keys()),
                "clés de toll.costs": sorted((toll.get("costs") or {}).keys()),
                "costs.countries": len((toll.get("costs") or {}).get("countries") or []),
                "sections": len(toll.get("sections") or []),
                "systems": len(toll.get("systems") or []),
                "source utilisée": source_ventilation(j),
            })

            st.markdown("**toll_by_country** (format attendu par map.html)")
            st.code(json.dumps(lignes_ptv, ensure_ascii=False, indent=2), language="json")

            st.markdown("**km_by_country** (format attendu par map.html)")
            st.code(json.dumps(km_ptv_pays, ensure_ascii=False, indent=2), language="json")
            ev = [{"km depuis départ": round((e.get("distanceFromStart") or 0) / 1000, 1),
                   "pays": e.get("countryCode"),
                   "type": "frontière" if "border" in e else ", ".join(k for k in e if k not in
                           ("latitude", "longitude", "distanceFromStart", "travelTimeFromStart",
                            "countryCode", "utcOffset")) or "—",
                   "entrée": (e.get("border") or {}).get("countryCode")}
                  for e in j.get("events") or []]
            if ev:
                with st.expander(f"Événements PTV ({len(ev)})"):
                    st.dataframe(pd.DataFrame(ev), use_container_width=True, hide_index=True)

            dfs = table_sections(j)
            if not dfs.empty:
                st.markdown("**Sections de péage**")
                st.dataframe(dfs, use_container_width=True, hide_index=True)

            with st.expander("Bloc toll brut"):
                st.code(json.dumps(toll, ensure_ascii=False, indent=2)[:30000], language="json")
        else:
            st.code(json.dumps(ptv["json"], ensure_ascii=False, indent=2)[:5000], language="json")

        with st.expander("Paramètres envoyés (clé masquée)"):
            st.code("\n".join(f"{k}={v}" for k, v in ptv["params"]))

        st.download_button("Télécharger la réponse PTV complète (JSON)",
                           json.dumps(ptv["json"], ensure_ascii=False, indent=2),
                           file_name="ptv_toll_test.json", mime="application/json")

# ── Serveur cartes ──────────────────────────────────────────────────────────
with tab_srv:
    if srv is None:
        st.info("Non testé.")
    elif srv.get("erreur"):
        st.error(srv["erreur"])
    else:
        d = srv["json"] if isinstance(srv["json"], dict) else {}
        m1, m2, m3 = st.columns(3)
        m1.metric("HTTP", srv["status"])
        m2.metric("Durée", f"{srv['duree']:.1f} s")
        pp = d.get("prix_peage")
        try:
            m3.metric("prix_peage", f"{float(pp):.2f} €")
        except (TypeError, ValueError):
            m3.metric("prix_peage", str(pp))

        emp = srv.get("empreinte") or {}
        with st.expander("Version du serveur (openapi.json)", expanded=not ("toll_by_country" in d)):
            st.write({
                "openapi lisible": emp.get("openapi"),
                "geocode accepte country (= patch)": emp.get("geocode_country"),
                "endpoints": emp.get("endpoints"),
                "erreur": emp.get("erreur"),
            })

        present = "toll_by_country" in d
        st.markdown(
            f"Clé <code>toll_by_country</code> : "
            f"<span class='{'pt-ok' if present else 'pt-ko'}'>{'présente' if present else 'absente'}</span>",
            unsafe_allow_html=True)

        if present and lignes_ptv is not None:
            comp = df_pays(lignes_ptv).rename(columns={"price": "PTV direct"}).merge(
                df_pays(d["toll_by_country"]).rename(columns={"price": "Serveur"}),
                on="country", how="outer").fillna(0.0)
            comp["Écart"] = (comp["Serveur"] - comp["PTV direct"]).round(2)
            st.dataframe(comp.rename(columns={"country": "Pays"}),
                         use_container_width=True, hide_index=True)

        if srv.get("sondes"):
            st.markdown("**Géocodage des coordonnées par le serveur**")
            st.dataframe(pd.DataFrame(srv["sondes"]), use_container_width=True, hide_index=True)

        st.download_button(
            "Télécharger le diagnostic serveur (JSON)",
            json.dumps({"empreinte": emp, "sondes": srv.get("sondes"), "corps": srv["body"],
                        "reponse": sans_polyline(d),
                        "ptv_direct": {"distance_km": (ptv["json"].get("distance") or 0) / 1000,
                                       "total": total_ptv(ptv["json"]),
                                       "toll_by_country": lignes_ptv} if ptv_ok else None},
                       ensure_ascii=False, indent=2),
            file_name="diagnostic_serveur_cartes.json", mime="application/json")

        st.markdown("**Réponse du serveur** (tracé masqué)")
        st.code(json.dumps(sans_polyline(d), ensure_ascii=False, indent=2)[:15000], language="json")
        with st.expander("Corps envoyé à /api/recalculate"):
            st.code(json.dumps(srv["body"], ensure_ascii=False, indent=2), language="json")

        st.download_button(
            "Télécharger le diagnostic serveur (JSON)",
            json.dumps({
                "http": srv.get("status"),
                "empreinte": emp,
                "cles_reponse": sorted(d.keys()),
                "toll_by_country_present": "toll_by_country" in d,
                "reponse_sans_trace": sans_polyline(d),
                "corps_envoye": srv.get("body"),
                "ptv_direct_toll_by_country": lignes_ptv,
            }, ensure_ascii=False, indent=2),
            file_name="serveur_toll_test.json", mime="application/json")

# ── Code à intégrer ─────────────────────────────────────────────────────────
with tab_code:
    st.markdown(
        "Si le diagnostic est vert côté PTV direct, cette fonction remplace "
        "`_extract_toll_by_country()` dans `tools/km_calcul/map_server_main.py`. "
        "Sortie identique au format déjà lu par `map.html`.")
    src = inspect.getsource(toll_by_country).replace("def toll_by_country(",
                                                     "def _extract_toll_by_country(", 1)
    st.code(src, language="python")
    st.code(inspect.getsource(km_by_country).replace("def km_by_country(",
                                                     "def _extract_km_by_country(", 1), language="python")
    st.markdown("Dans l'appel PTV du serveur, `results` doit contenir "
                "`POLYLINE,TOLL_COSTS` (TOLL_SECTIONS en option, pour le repli) et `options[currency]` valoir `EUR`.")
