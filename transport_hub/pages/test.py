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
    Ventilation du péage par pays : [{"country": "DE", "price": 112.4}, ...].

    Ordre de lecture :
      1. toll.costs.countries          (détail natif PTV)
      2. toll.sections agrégées        (pays sur la section, sur son tollSystem,
                                        ou via costs[].tollSystemIndex → toll.systems)
    Les prix convertis (EUR) priment toujours sur la devise nationale.
    `price` peut être un nombre ou un objet {"price": x, "currency": "DKK"} :
    les deux formes sont gérées.
    """
    def _num(v):
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict) and isinstance(v.get("price"), (int, float)):
            return float(v["price"])
        return None

    def _prix(obj):
        if isinstance(obj, (int, float)):
            return float(obj)
        if not isinstance(obj, dict):
            return None
        conv = _num(obj.get("convertedPrice"))
        if conv is not None:
            return conv
        return _num(obj.get("price"))

    toll = (ptv or {}).get("toll") or {}
    costs = toll.get("costs") or {}
    systems = toll.get("systems") or []

    # 1. Détail natif
    pays = costs.get("countries") or toll.get("countries")
    if pays:
        agrege = {}
        for c in pays:
            cc = c.get("countryCode") or c.get("country")
            montant = _prix(c)
            if cc and montant is not None:
                agrege[cc] = agrege.get(cc, 0.0) + montant
        if agrege:
            return sorted(({"country": k, "price": round(v, 2)} for k, v in agrege.items()),
                          key=lambda x: -x["price"])

    # 2. Agrégation des sections
    def _pays_systeme(idx):
        if isinstance(idx, int) and 0 <= idx < len(systems):
            s = systems[idx] or {}
            return s.get("countryCode") or s.get("country")
        return None

    agrege = {}
    for sec in toll.get("sections") or []:
        ts = sec.get("tollSystem") or {}
        cc_sec = sec.get("countryCode") or ts.get("countryCode") or ts.get("country")
        lignes = sec.get("costs")
        lignes = lignes if isinstance(lignes, list) else [lignes] if lignes else []
        for ligne in lignes:
            cc = cc_sec or _pays_systeme((ligne or {}).get("tollSystemIndex"))
            montant = _prix(ligne)
            if cc and montant is not None:
                agrege[cc] = agrege.get(cc, 0.0) + montant

    return sorted(({"country": k, "price": round(v, 2)} for k, v in agrege.items()),
                  key=lambda x: -x["price"])


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
        lignes = sec.get("costs")
        lignes = lignes if isinstance(lignes, list) else [lignes] if lignes else [{}]
        for ligne in lignes:
            ligne = ligne or {}
            idx = ligne.get("tollSystemIndex")
            sys_ = systems[idx] if isinstance(idx, int) and 0 <= idx < len(systems) else {}
            conv = ligne.get("convertedPrice") or {}
            prix = ligne.get("price")
            rows.append({
                "section": i,
                "libellé": sec.get("displayName") or sys_.get("name") or "",
                "pays (section)": sec.get("countryCode") or "",
                "pays (système)": (sys_ or {}).get("countryCode") or "",
                "prix": prix.get("price") if isinstance(prix, dict) else prix,
                "devise": prix.get("currency") if isinstance(prix, dict) else ligne.get("currency"),
                "prix EUR": conv.get("price"),
            })
    return pd.DataFrame(rows)


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
    t0 = time.time()
    r = requests.post(base + "/api/recalculate", json=body, timeout=120)
    duree = time.time() - t0
    try:
        rep = r.json()
    except ValueError:
        rep = {"_texte_brut": r.text[:3000]}
    return {"status": r.status_code, "duree": duree, "json": rep, "body": body}


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
    results = st.text_input("results", "TOLL_COSTS,TOLL_SECTIONS,TOLL_SYSTEMS",
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

    if srv is None:
        constats.append(("info", "Serveur cartes non testé."))
    elif not srv_ok:
        constats.append(("ko", f"Serveur cartes : {srv.get('erreur') or 'HTTP ' + str(srv.get('status'))}."))
    else:
        d = srv["json"] if isinstance(srv["json"], dict) else {}
        if "toll_by_country" not in d:
            constats.append(("ko", "Le serveur ne renvoie pas toll_by_country : la version déployée "
                                   "sur Render n'est pas celle patchée. Vérifier le fichier "
                                   "tools/km_calcul/map_server_main.py et le dernier déploiement."))
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

        st.markdown("**Réponse du serveur** (tracé masqué)")
        st.code(json.dumps(sans_polyline(d), ensure_ascii=False, indent=2)[:15000], language="json")
        with st.expander("Corps envoyé à /api/recalculate"):
            st.code(json.dumps(srv["body"], ensure_ascii=False, indent=2), language="json")

# ── Code à intégrer ─────────────────────────────────────────────────────────
with tab_code:
    st.markdown(
        "Si le diagnostic est vert côté PTV direct, cette fonction remplace "
        "`_extract_toll_by_country()` dans `tools/km_calcul/map_server_main.py`. "
        "Sortie identique au format déjà lu par `map.html`.")
    src = inspect.getsource(toll_by_country).replace("def toll_by_country(",
                                                     "def _extract_toll_by_country(", 1)
    st.code(src, language="python")
    st.markdown("Dans l'appel PTV du serveur, `results` doit contenir "
                "`POLYLINE,TOLL_COSTS,TOLL_SECTIONS,TOLL_SYSTEMS` et `options[currency]` valoir `EUR`.")
