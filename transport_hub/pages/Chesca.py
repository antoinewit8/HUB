# -*- coding: utf-8 -*-
"""
HUB — Carte Chesca
Colle le message de suivi Chesca : la page parse chaque ligne, géolocalise
les sites et affiche la carte + le tableau de dispatch.

Dépendances : streamlit, pandas, pydeck, requests
Emplacement : pages/12_🗺️_Carte_Chesca.py
"""

import json
import re
import unicodedata
from datetime import date

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Carte Chesca", page_icon="🗺️", layout="wide")

CARTO_DARK = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = {"User-Agent": "CB-HUB-Chesca/1.0 (dispatch tool)"}

STATUTS = {
    "sur_dech":    {"label": "Sur place déchargement", "rgb": [240, 162,  60]},
    "sur_charg":   {"label": "Sur place chargement",   "rgb": [107, 203, 139]},
    "swap":        {"label": "Échange remorque",       "rgb": [227, 112, 127]},
    "lavage":      {"label": "Lavage",                 "rgb": [168, 143, 227]},
    "route_dech":  {"label": "En route déchargement",  "rgb": [ 79, 179, 201]},
    "route_charg": {"label": "En route chargement",    "rgb": [ 86, 168, 118]},
    "route":       {"label": "En route",               "rgb": [110, 150, 170]},
    "repos":       {"label": "Repos 45h",              "rgb": [ 95, 121, 130]},
    "inconnu":     {"label": "Position inconnue",      "rgb": [135, 148, 160]},
}
ORDRE = ["sur_dech", "sur_charg", "swap", "lavage",
         "route_dech", "route_charg", "route", "repos", "inconnu"]

# ─────────────────────────────────────────────────────────────────────────────
# RÉFÉRENTIEL DES SITES
# clé = nom normalisé (minuscule, sans accent, sans tiret)
# valeur = (libellé propre, pays, lat, lon, alerte éventuelle)
# ─────────────────────────────────────────────────────────────────────────────

GEO = {
    "grunenbach":            ("Grünenbach", "DE", 47.6167,  9.9333, ""),
    "reims":                 ("Reims", "FR", 49.2583,  4.0317, ""),
    "sottevast":             ("Sottevast", "FR", 49.5333, -1.6167, ""),
    "clery petit":           ("Cléry-le-Petit", "FR", 49.3667, 5.1667, ""),
    "clery le petit":        ("Cléry-le-Petit", "FR", 49.3667, 5.1667, ""),
    "sarre union":           ("Sarre-Union", "FR", 48.9333, 7.0833, ""),
    "kampen":                ("Kampen", "NL", 52.5553, 5.9111, ""),
    "bernkastel":            ("Bernkastel-Kues", "DE", 49.9167, 7.0667, ""),
    "bernkastel kues":       ("Bernkastel-Kues", "DE", 49.9167, 7.0667, ""),
    "jouy":                  ("Jouy", "FR", 48.5167, 1.5667,
                              "Homonyme : Jouy (28) retenu — vérifier Jouy-en-Josas / Jouy-aux-Arches"),
    "la chapelle d andaine": ("La Chapelle-d'Andaine", "FR", 48.5500, -0.4333, ""),
    "la chapelle dandaine":  ("La Chapelle-d'Andaine", "FR", 48.5500, -0.4333, ""),
    "belleville":            ("Belleville-sur-Loire", "FR", 47.5117, 2.8500,
                              "Homonyme : Belleville-sur-Loire retenu — vérifier Belleville-en-Beaujolais"),
    "mayenne":               ("Mayenne", "FR", 48.3000, -0.6167, ""),
    "gent":                  ("Gand", "BE", 51.0543, 3.7174, ""),
    "gand":                  ("Gand", "BE", 51.0543, 3.7174, ""),
    "woergl":                ("Wörgl", "AT", 47.4833, 12.0667, ""),
    "worgl":                 ("Wörgl", "AT", 47.4833, 12.0667, ""),
    "faenza":                ("Faenza", "IT", 44.2853, 11.8833, ""),
    "nantes":                ("Nantes", "FR", 47.2184, -1.5536, ""),
    "valence":               ("Valence", "FR", 44.9333, 4.8917, ""),
    "chevrieres":            ("Chevrières", "FR", 49.3500, 2.6833,
                              "Homonyme : Chevrières (60) retenu — vérifier Chevrières (42)"),
    "rouvroy sur audry":     ("Rouvroy-sur-Audry", "FR", 49.8000, 4.4667, ""),
    "manage":                ("Manage", "BE", 50.5000, 4.2333, ""),
    "vienne":                ("Vienne", "FR", 45.5254, 4.8745,
                              "Homonyme : Vienne (38) retenu — vérifier s'il s'agit de Wien (AT)"),
    "baleycourt":            ("Baleycourt", "FR", 49.1500, 5.3167, ""),
    "montauban":             ("Montauban", "FR", 44.0181, 1.3556, ""),
    "langenlonsheim":        ("Langenlonsheim", "DE", 49.9000, 7.9000, ""),
    "monheim":               ("Monheim am Rhein", "DE", 51.0917, 6.8917,
                              "Homonyme : Monheim am Rhein retenu — vérifier Monheim (Bavière)"),
    "dalfsen":               ("Dalfsen", "NL", 52.5089, 6.2578, ""),
    "werbomont":             ("Werbomont", "BE", 50.3667, 5.6500, ""),
}

# ─────────────────────────────────────────────────────────────────────────────
# PARSING
# ─────────────────────────────────────────────────────────────────────────────

JOURS = {
    "monday": "lundi", "tuesday": "mardi", "wednesday": "mercredi",
    "thursday": "jeudi", "friday": "vendredi", "saturday": "samedi",
    "sunday": "dimanche", "tomorrow": "demain", "today": "aujourd'hui",
}

LINE_RE = re.compile(r"^\s*([A-Z0-9][A-Z0-9 \-]{3,12}?)\s*[–—−-]\s*(.+)$")
PLATE_RE = re.compile(r"^[A-Z0-9]{5,10}$")
HEURE_RE = re.compile(r"(\d{1,2})\s*[:h]\s*(\d{2})")
KM_RE = re.compile(r"(\d{2,4})\s*km", re.I)
SUR_PLACE_RE = re.compile(r"\b(he is at|is at the|is at|just arrived|in process|is in)\b")
EN_ROUTE_RE = re.compile(r"\b(heading|driving|towards|direction|left to go)\b")


def norm(txt: str) -> str:
    """minuscule, sans accent, sans ponctuation, espaces simples."""
    t = unicodedata.normalize("NFKD", txt or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().replace("'", " ").replace("’", " ").replace("-", " ")
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def detecte_statut(txt: str) -> str:
    t = txt.lower()
    if "clean" in t:
        return "lavage"
    if "swap" in t or "changing trailer" in t:
        return "swap"
    if "break" in t or re.search(r"\b45\s*h\b", t):
        return "repos"

    sur_place = bool(SUR_PLACE_RE.search(t))
    en_route = bool(EN_ROUTE_RE.search(t))
    dech = ("unload" in t) or ("deliver" in t)
    charg = ("load" in t) and ("unload" not in t)

    if dech:
        return "sur_dech" if (sur_place and not en_route) else "route_dech"
    if charg:
        return "sur_charg" if (sur_place and "just loaded" not in t) else "route_charg"
    if en_route:
        return "route"
    return "inconnu"


def nettoie_lieu(brut: str) -> str:
    s = (brut or "").strip(" .,;:")
    s = re.sub(r"\b(the|place|point|area|city)\b", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" .,;:")
    return s


def extrait_lieu(txt: str):
    """Nom de lieu brut trouvé dans la ligne, ou None."""
    for seg in re.split(r"[–—−]|\s-\s", txt):
        s = seg.strip()
        m = re.search(r"\bdirection of\s+(.+)$", s, re.I)
        if m:
            return nettoie_lieu(m.group(1))
        m = re.search(r"\bin\s+(.+)$", s, re.I)
        if m:
            return nettoie_lieu(m.group(1))
    return None


def extrait_eta(txt: str) -> str:
    """ETA lisible : jour + heure quand le jour précède l'heure, sinon heure seule."""
    t = txt.lower()

    heures = [(m.start(), f"{int(m.group(1)):02d}:{m.group(2)}")
              for m in HEURE_RE.finditer(t)]
    jour, pos_jour = None, 10 ** 6
    for en, fr in JOURS.items():
        m = re.search(rf"\b{en}\b", t)
        if m and m.start() < pos_jour:
            jour, pos_jour = fr, m.start()
    km = KM_RE.search(t)

    parts = []
    if heures:
        h = " – ".join(x[1] for x in heures[:2])
        parts.append(f"{jour} {h}" if (jour and pos_jour < heures[0][0]) else h)
    elif "morning" in t:
        parts.append(f"{jour} matin".strip() if jour else "matin")
    elif "evening" in t or "night" in t:
        parts.append(f"{jour} soir".strip() if jour else "soir")
    elif jour:
        parts.append(jour)

    if km:
        parts.append(f"≈ {km.group(1)} km")

    if not parts:
        if "in process" in t or re.search(r"\bnow\b", t):
            parts.append("en cours")
        elif "waiting" in t:
            parts.append("en attente")
        elif "just arrived" in t:
            parts.append("arrivé")
        elif SUR_PLACE_RE.search(t):
            parts.append("sur place")

    # livraison reportée au lendemain malgré une ETA du jour
    if heures and re.search(r"(deliver|park)[^.]{0,60}(tomorrow|morning)", t):
        parts.append("livraison demain matin")

    return " · ".join(parts)


@st.cache_data(show_spinner=False, ttl=60 * 60 * 24)
def geocode_web(nom: str):
    """Fallback Nominatim pour un lieu absent du référentiel."""
    try:
        r = requests.get(
            NOMINATIM,
            params={"q": nom, "format": "json", "limit": 1,
                    "countrycodes": "fr,be,lu,de,nl,it,es,at,ch,pl,cz"},
            headers=UA, timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        d = data[0]
        pays = d.get("display_name", "").split(",")[-1].strip()[:2].upper()
        return (nom.title(), pays, float(d["lat"]), float(d["lon"]),
                "Géocodage automatique — à vérifier")
    except Exception:
        return None


def resout_lieu(brut: str, autoriser_web: bool):
    if not brut:
        return None
    cle = norm(brut)
    if cle in GEO:
        return GEO[cle]
    for k, v in GEO.items():
        if cle.startswith(k) or k.startswith(cle):
            return v
    if autoriser_web:
        return geocode_web(brut)
    return None


def parse_message(texte: str, autoriser_web: bool):
    lignes_ok, lignes_ko = [], []
    for ligne in texte.splitlines():
        if not ligne.strip():
            continue
        m = LINE_RE.match(ligne.strip())
        if not m:
            lignes_ko.append(ligne.strip())
            continue
        plaque = m.group(1).replace(" ", "").upper()
        reste = m.group(2).strip()
        if not PLATE_RE.match(plaque):
            lignes_ko.append(ligne.strip())
            continue

        statut = detecte_statut(reste)
        brut = extrait_lieu(reste)
        geo = resout_lieu(brut, autoriser_web)

        if geo is None:
            ville = brut or "Non précisé"
            pays, lat, lon = "—", None, None
            note = "Lieu non reconnu" if brut else "Aucune destination dans le message"
            if brut is None and statut not in ("repos", "lavage", "swap"):
                statut = "inconnu"
        else:
            ville, pays, lat, lon, note = geo

        lignes_ok.append({
            "Tracteur": plaque,
            "Statut": statut,
            "Site": ville,
            "Pays": pays,
            "ETA": extrait_eta(reste),
            "Lat": lat,
            "Lon": lon,
            "Alerte": note,
            "Message": reste,
        })
    return pd.DataFrame(lignes_ok), lignes_ko


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  .block-container {padding-top: 2.2rem;}
  h1, h2, h3 {font-family: 'Barlow Condensed', 'Segoe UI', sans-serif;
              letter-spacing: .01em; text-transform: uppercase;}
  .legende span {display:inline-block; margin-right:14px; font-size:12px;
                 font-family:'IBM Plex Mono', monospace;}
  .legende i {display:inline-block; width:10px; height:10px; border-radius:50%;
              margin-right:6px;}
</style>
""", unsafe_allow_html=True)

st.title("Carte Chesca")
st.caption("Colle le message de suivi tel quel — une ligne par tracteur, "
           "format `PLAQUE – he is heading unloading in Ville – ETA`.")

col_in, col_opt = st.columns([3, 1])
with col_in:
    texte = st.text_area(
        "Message Chesca", height=220, key="msg",
        placeholder="B205ADN – he is heading unloading in Grunenbach – should be there tomorrow around 11:30",
    )
with col_opt:
    autoriser_web = st.toggle(
        "Géocodage web", value=True,
        help="Interroge Nominatim (OpenStreetMap) pour les sites absents du référentiel.")
    rayon = st.slider("Taille des points", 4, 20, 9)
    lancer = st.button("Générer la carte", type="primary", use_container_width=True)

if lancer and texte.strip():
    df_parse, rejets = parse_message(texte, autoriser_web)
    st.session_state["chesca_df"] = df_parse
    st.session_state["chesca_rejets"] = rejets

df = st.session_state.get("chesca_df")
if df is None or df.empty:
    st.info("Aucune donnée. Colle le message et clique sur **Générer la carte**.")
    st.stop()

rejets = st.session_state.get("chesca_rejets", [])
if rejets:
    with st.expander(f"⚠ {len(rejets)} ligne(s) non reconnue(s)"):
        for r in rejets:
            st.code(r, language=None)

# ── Filtres ─────────────────────────────────────────────────────────────────
presents = [s for s in ORDRE if s in set(df["Statut"])]
choix = st.multiselect(
    "Statuts affichés",
    options=presents,
    default=presents,
    format_func=lambda s: f"{STATUTS[s]['label']} ({(df['Statut'] == s).sum()})",
)
vue = df[df["Statut"].isin(choix)].copy()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Tracteurs", len(vue))
c2.metric("Sites", vue.dropna(subset=["Lat"])["Site"].nunique())
c3.metric("Sans position", int(vue["Lat"].isna().sum()))
c4.metric("À vérifier", int((vue["Alerte"].fillna("").str.len() > 0).sum()))

# ── Carte ───────────────────────────────────────────────────────────────────
carte = vue.dropna(subset=["Lat", "Lon"]).copy()
if not carte.empty:
    grp = (carte.groupby(["Site", "Pays", "Lat", "Lon"], as_index=False)
                .agg(Tracteurs=("Tracteur", lambda x: " · ".join(sorted(x))),
                     Nb=("Tracteur", "size"),
                     Statut=("Statut", "first"),
                     Detail=("ETA", lambda x: " / ".join(v for v in x if v))))
    grp["color"] = grp["Statut"].map(lambda s: STATUTS[s]["rgb"] + [220])
    grp["radius"] = (rayon * 1000) * (1 + 0.35 * (grp["Nb"] - 1))

    points = pdk.Layer(
        "ScatterplotLayer",
        data=grp,
        get_position="[Lon, Lat]",
        get_fill_color="color",
        get_radius="radius",
        radius_min_pixels=6,
        radius_max_pixels=30,
        stroked=True,
        get_line_color=[10, 20, 26],
        line_width_min_pixels=1,
        pickable=True,
    )
    etiquettes = pdk.Layer(
        "TextLayer",
        data=grp,
        get_position="[Lon, Lat]",
        get_text="Site",
        get_size=11,
        get_color=[210, 228, 234],
        get_pixel_offset=[0, -18],
        billboard=True,
    )
    st.pydeck_chart(pdk.Deck(
        layers=[points, etiquettes],
        initial_view_state=pdk.ViewState(
            latitude=float(grp["Lat"].mean()),
            longitude=float(grp["Lon"].mean()),
            zoom=4.6, pitch=0,
        ),
        map_style=CARTO_DARK,
        tooltip={"html": "<b>{Site}</b> ({Pays})<br/>{Tracteurs}<br/>{Detail}",
                 "style": {"backgroundColor": "#0E222B", "color": "#DDEAEE",
                           "fontSize": "12px"}},
    ), use_container_width=True)

    legende = " ".join(
        f"<span><i style='background:rgb({','.join(map(str, STATUTS[s]['rgb']))})'></i>"
        f"{STATUTS[s]['label']}</span>" for s in choix
    )
    st.markdown(f"<div class='legende'>{legende}</div>", unsafe_allow_html=True)
else:
    st.warning("Aucun site géolocalisé dans la sélection.")

# ── Tableau éditable ────────────────────────────────────────────────────────
st.subheader("Dispatch")
st.caption("Corrige une commune ou des coordonnées dans le tableau, "
           "puis clique sur Appliquer les corrections.")

vue["_ordre"] = vue["Statut"].map({s: i for i, s in enumerate(ORDRE)})
vue = vue.sort_values(["_ordre", "Site", "Tracteur"]).drop(columns="_ordre")

edit = st.data_editor(
    vue[["Tracteur", "Statut", "Site", "Pays", "ETA", "Lat", "Lon", "Alerte", "Message"]],
    hide_index=True,
    use_container_width=True,
    height=460,
    column_config={
        "Statut": st.column_config.SelectboxColumn(options=ORDRE, width="medium"),
        "Lat": st.column_config.NumberColumn(format="%.4f"),
        "Lon": st.column_config.NumberColumn(format="%.4f"),
        "Alerte": st.column_config.TextColumn(width="medium"),
        "Message": st.column_config.TextColumn(width="large"),
    },
    key="editeur",
)

if st.button("Appliquer les corrections"):
    base = st.session_state["chesca_df"].set_index("Tracteur")
    base.update(edit.set_index("Tracteur"))
    st.session_state["chesca_df"] = base.reset_index()
    st.rerun()

# ── Exports ─────────────────────────────────────────────────────────────────
e1, e2 = st.columns(2)
e1.download_button(
    "Export CSV",
    edit.to_csv(index=False, sep=";").encode("utf-8-sig"),
    file_name=f"chesca_{date.today():%Y%m%d}.csv",
    mime="text/csv",
    use_container_width=True,
)

nouveaux = {
    norm(r["Site"]): [r["Site"], r["Pays"], r["Lat"], r["Lon"], ""]
    for _, r in edit.dropna(subset=["Lat", "Lon"]).iterrows()
    if norm(r["Site"]) not in GEO
}
e2.download_button(
    f"Nouveaux sites ({len(nouveaux)})",
    json.dumps(nouveaux, ensure_ascii=False, indent=2).encode("utf-8"),
    file_name="nouveaux_sites.json",
    mime="application/json",
    disabled=not nouveaux,
    use_container_width=True,
    help="À recoller dans le dictionnaire GEO pour éviter un géocodage web la prochaine fois.",
)
