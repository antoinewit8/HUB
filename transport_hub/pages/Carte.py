import os
import time
import unicodedata
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from jinja2 import Template

# ─── Config ───────────────────────────────────────────────────────────────────
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

MAP_SERVER_URL = os.environ.get("MAP_SERVER_URL", "https://hub-m36x.onrender.com").rstrip("/")

# Incrémenter à chaque changement de structure de session_state -> purge auto
STATE_VERSION = "carte_manuelle/3"

st.set_page_config(page_title="Carte Manuelle", page_icon="🗺️", layout="wide")

# ─── CSS ──────────────────────────────────────────────────────────────────────
# FIX : l'ancien CSS forçait iframe à 100vh alors que components.html imposait
# 1250px -> iframe tronquée ou vide selon l'écran. Une seule hauteur fait foi,
# et on réserve la place de la barre d'actions.
st.markdown(
    """
    <style>
      .block-container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; }
      header, #MainMenu, footer { display: none !important; }
      section[data-testid="stMain"] > div:first-child { padding: 0 !important; }
      div[data-testid="stVerticalBlock"] { gap: 0.2rem !important; }
      iframe[title="streamlit.components.v1.html"],
      iframe[title="components.html"] {
          display: block !important; border: none !important;
          width: 100% !important; height: calc(100vh - 96px) !important;
      }
      div[data-testid="stForm"] { border: none; padding: 1rem 1.2rem 0.4rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Purge d'état obsolète ────────────────────────────────────────────────────
if st.session_state.get("_state_version") != STATE_VERSION:
    for k in ("calc", "origine", "dest", "avoid_tolls", "avoid_highways",
              "polyline_original", "server_ready"):
        st.session_state.pop(k, None)
    st.session_state["_state_version"] = STATE_VERSION

st.session_state.setdefault("calc", None)
st.session_state.setdefault("origine", "")
st.session_state.setdefault("dest", "")
st.session_state.setdefault("avoid_tolls", False)
st.session_state.setdefault("avoid_highways", False)
st.session_state.setdefault("polyline_original", [])


# ─── Géocodage : préparation du libellé ──────────────────────────────────────
# FIX : l'ancienne version ajoutait ", Belgium" à tout libellé sans virgule.
# Une ville étrangère sans pays, un code postal, un nom composé partaient donc
# se faire géocoder en Belgique -> itinéraire complètement à côté.
_PAYS = {
    "france": "France", "belgique": "Belgium", "belgium": "Belgium", "belgie": "Belgium",
    "italie": "Italy", "italia": "Italy", "italy": "Italy",
    "espagne": "Spain", "espana": "Spain", "spain": "Spain",
    "allemagne": "Germany", "deutschland": "Germany", "germany": "Germany",
    "pays-bas": "Netherlands", "paysbas": "Netherlands", "nederland": "Netherlands",
    "netherlands": "Netherlands", "hollande": "Netherlands", "holland": "Netherlands",
    "luxembourg": "Luxembourg", "letzebuerg": "Luxembourg",
    "suisse": "Switzerland", "switzerland": "Switzerland", "schweiz": "Switzerland",
    "autriche": "Austria", "austria": "Austria", "osterreich": "Austria",
    "portugal": "Portugal", "pologne": "Poland", "poland": "Poland", "polska": "Poland",
    "tchequie": "Czechia", "czechia": "Czechia", "slovaquie": "Slovakia",
    "hongrie": "Hungary", "hungary": "Hungary", "slovenie": "Slovenia",
    "croatie": "Croatia", "roumanie": "Romania", "bulgarie": "Bulgaria",
    "danemark": "Denmark", "denmark": "Denmark", "suede": "Sweden", "sweden": "Sweden",
    "norvege": "Norway", "finlande": "Finland", "irlande": "Ireland", "ireland": "Ireland",
    "royaume-uni": "United Kingdom", "angleterre": "United Kingdom",
    "england": "United Kingdom", "uk": "United Kingdom", "gb": "United Kingdom",
    "maroc": "Morocco", "turquie": "Turkey", "turkey": "Turkey",
}

# Codes ISO acceptés en fin de libellé (ex : "Vercelli IT")
_ISO = {
    "be": "Belgium", "fr": "France", "lu": "Luxembourg", "nl": "Netherlands",
    "de": "Germany", "it": "Italy", "es": "Spain", "pt": "Portugal",
    "ch": "Switzerland", "at": "Austria", "pl": "Poland", "cz": "Czechia",
    "sk": "Slovakia", "hu": "Hungary", "si": "Slovenia", "hr": "Croatia",
    "ro": "Romania", "bg": "Bulgaria", "dk": "Denmark", "se": "Sweden",
    "no": "Norway", "fi": "Finland", "ie": "Ireland",
}


def _plat(txt: str) -> str:
    """minuscules sans accents ni ponctuation de bord."""
    t = unicodedata.normalize("NFKD", txt)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower().strip(" .,;")


def format_location(loc: str, pays_defaut: str) -> str:
    """Construit un libellé géocodable. Ne force jamais un pays si l'utilisateur
    en a mis un, et n'invente pas de pays sur un libellé déjà virgulé."""
    loc = " ".join(loc.split())
    if not loc:
        return loc

    # Coordonnées brutes "50.63, 5.57" -> on laisse tel quel
    parts = [p.strip() for p in loc.split(",")]
    if len(parts) == 2:
        try:
            float(parts[0])
            float(parts[1])
            return f"{parts[0]},{parts[1]}"
        except ValueError:
            pass

    # Libellé déjà virgulé : on respecte, sauf si le dernier segment n'est pas un pays
    if "," in loc:
        dernier = _plat(parts[-1])
        if dernier in _PAYS or dernier in _ISO or len(dernier) > 2:
            return loc
        return f"{loc}, {pays_defaut}"

    mots = loc.split()
    if len(mots) >= 2:
        fin = _plat(mots[-1])
        if fin in _PAYS:
            return f"{' '.join(mots[:-1])}, {_PAYS[fin]}"
        if fin in _ISO:
            return f"{' '.join(mots[:-1])}, {_ISO[fin]}"
        # "Pays-Bas" / "Royaume-Uni" écrits en deux mots
        fin2 = _plat(" ".join(mots[-2:]))
        if fin2 in _PAYS:
            return f"{' '.join(mots[:-2])}, {_PAYS[fin2]}"

    return f"{loc}, {pays_defaut}"


# ─── Warm up ──────────────────────────────────────────────────────────────────
# FIX : l'ancienne boucle bloquait jusqu'à 60 s à chaque premier affichage et
# avalait toutes les exceptions. Mise en cache + except explicite.
@st.cache_data(ttl=600, show_spinner=False)
def warm_up_server(url: str) -> bool:
    for _ in range(3):
        try:
            if requests.get(f"{url}/health", timeout=12).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(4)
    return False


with st.spinner("Réveil du serveur carte…"):
    server_ready = warm_up_server(MAP_SERVER_URL)


# ─── Appel serveur ────────────────────────────────────────────────────────────
def calculer(origine: str, dest: str, tolls: bool, highways: bool):
    payload = {
        "origin": origine,
        "dest": dest,
        "avoid_tolls": tolls,
        "avoid_highways": highways,
    }
    resp = requests.post(f"{MAP_SERVER_URL}/api/recalculate", json=payload, timeout=90)
    if resp.status_code != 200:
        raise RuntimeError(f"Serveur {resp.status_code} — {resp.text[:200]}")
    return resp.json()


def reset_carte():
    st.session_state["calc"] = None
    st.session_state["polyline_original"] = []


# ─── Affichage carte ──────────────────────────────────────────────────────────
if st.session_state["calc"]:
    calc = st.session_state["calc"]

    # FIX : barre d'actions au-dessus de la carte. Sans elle, une fois un trajet
    # calculé la page ne proposait plus aucun moyen de revenir au formulaire :
    # ni reset, ni redéfinition du départ/arrivée.
    c1, c2, c3 = st.columns([6, 1.4, 1.4])
    with c1:
        st.markdown(
            f"**{st.session_state['origine']}** → **{st.session_state['dest']}**"
            + ("  ·  sans péage" if st.session_state["avoid_tolls"] else "")
            + ("  ·  sans autoroute" if st.session_state["avoid_highways"] else "")
        )
    with c2:
        st.button("Modifier le trajet", use_container_width=True,
                  on_click=reset_carte, key="btn_modifier")
    with c3:
        st.button("Tout effacer", use_container_width=True, type="primary",
                  on_click=reset_carte, key="btn_reset")

    try:
        map_html_path = Path(__file__).parent.parent / "map.html"
        html_template = map_html_path.read_text(encoding="utf-8")

        polyline = calc.get("polyline", [])
        # FIX : les trois clés recevaient la même valeur, donc map.html ne pouvait
        # pas distinguer le tracé courant du tracé d'origine (retour arrière mort).
        original = st.session_state["polyline_original"] or polyline
        st.session_state["polyline_original"] = original

        html_final = Template(html_template).render(
            route={
                "origin": st.session_state["origine"],
                "dest": st.session_state["dest"],
                "polyline": polyline,
                "polyline_current": polyline,
                "polyline_original": original,
                "distance_km": calc.get("distance_km", ""),
                "duration_h": calc.get("duration_h", ""),
                "prix_peage": calc.get("prix_peage", 0.0),
                # FIX : map.html recalcule lui-même après un déplacement de point ;
                # sans ces deux clés il repartait toujours en mode "péages autorisés".
                "avoid_tolls": st.session_state["avoid_tolls"],
                "avoid_highways": st.session_state["avoid_highways"],
            },
            route_id=calc.get("route_id", "manual"),
            server_url=MAP_SERVER_URL,
        )

        components.html(html_final, height=1000, scrolling=False)

    except FileNotFoundError:
        st.error("map.html introuvable à la racine du projet.")
    except Exception as e:
        st.error(f"Erreur chargement map.html : {e}")

# ─── Formulaire ───────────────────────────────────────────────────────────────
else:
    if not server_ready:
        st.warning(
            f"Le serveur carte ({MAP_SERVER_URL}) ne répond pas encore. "
            "Le premier calcul peut échouer, relancez-le une fois.",
            icon="⚠️",
        )

    with st.form("form_carte", clear_on_submit=False):
        st.markdown("### Calculer un itinéraire")

        c1, c2 = st.columns(2)
        with c1:
            # FIX : champs préremplis avec le trajet précédent -> on peut corriger
            # un seul des deux points au lieu de tout retaper.
            origine = st.text_input("Départ", value=st.session_state["origine"],
                                    placeholder="Liège  ·  57000 Metz, France  ·  Vercelli IT")
        with c2:
            destination = st.text_input("Arrivée", value=st.session_state["dest"],
                                        placeholder="Nieuport  ·  Rotterdam, Netherlands")

        c3, c4, c5 = st.columns([1.2, 1.2, 1.6])
        with c3:
            avoid_tolls = st.checkbox("Éviter les péages", value=st.session_state["avoid_tolls"])
        with c4:
            avoid_highways = st.checkbox("Éviter les autoroutes",
                                         value=st.session_state["avoid_highways"])
        with c5:
            pays_defaut = st.selectbox(
                "Pays par défaut",
                ["Belgium", "France", "Luxembourg", "Netherlands", "Germany", "Italy", "Spain"],
                index=0,
                help="Appliqué uniquement quand vous ne précisez pas le pays.",
            )

        submitted = st.form_submit_button("Calculer l'itinéraire", use_container_width=True)

    if submitted:
        if not origine.strip() or not destination.strip():
            st.error("Renseignez le départ et l'arrivée.")
        else:
            o = format_location(origine, pays_defaut)
            d = format_location(destination, pays_defaut)
            st.caption(f"Géocodage demandé : {o}  →  {d}")

            with st.spinner("Calcul en cours…"):
                try:
                    data = calculer(o, d, avoid_tolls, avoid_highways)
                    if not data.get("polyline"):
                        st.error("Le serveur n'a renvoyé aucun tracé pour ces deux points.")
                    else:
                        st.session_state["calc"] = data
                        st.session_state["origine"] = o
                        st.session_state["dest"] = d
                        st.session_state["avoid_tolls"] = avoid_tolls
                        st.session_state["avoid_highways"] = avoid_highways
                        st.session_state["polyline_original"] = data["polyline"]
                        st.rerun()
                except requests.Timeout:
                    st.error("Le serveur n'a pas répondu dans les 90 s. Relancez le calcul.")
                except requests.RequestException as e:
                    st.error(f"Connexion impossible : {e}")
                except RuntimeError as e:
                    st.error(str(e))
