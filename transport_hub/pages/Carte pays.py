import os
import sys
import math
import streamlit as st
import pandas as pd
import pydeck as pdk

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KM_DIR = os.path.join(ROOT, "tools", "km_calcul")
for p in (ROOT, KM_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from modules.carte_pays import calculer_route_pays  # noqa: E402

st.set_page_config(page_title="Carte trajet par pays", page_icon="🗺️", layout="wide")

NOMS_PAYS = {
    "BE": "Belgique", "LU": "Luxembourg", "FR": "France", "DE": "Allemagne", "NL": "Pays-Bas",
    "CH": "Suisse", "IT": "Italie", "ES": "Espagne", "AT": "Autriche", "PL": "Pologne",
    "CZ": "Tchéquie", "PT": "Portugal", "GB": "Royaume-Uni", "DK": "Danemark",
}
COULEURS = {
    "BE": [230, 57, 70], "LU": [0, 161, 222], "FR": [29, 53, 140], "DE": [255, 183, 3],
    "NL": [251, 133, 0], "CH": [155, 93, 229], "IT": [42, 157, 143], "ES": [200, 160, 40],
    "AT": [200, 80, 120], "PL": [110, 110, 110],
}
SECOURS = [[90, 170, 90], [170, 90, 170], [90, 140, 200], [200, 120, 60], [60, 160, 160]]
_attribuees = {}


def couleur(cc):
    if cc in COULEURS:
        return COULEURS[cc]
    if cc not in _attribuees:
        _attribuees[cc] = SECOURS[len(_attribuees) % len(SECOURS)]
    return _attribuees[cc]


def nom_pays(cc):
    return f"{NOMS_PAYS.get(cc, cc)} ({cc})"


def lire_coords(txt):
    try:
        a, b = str(txt).split(",")[:2]
        return float(a), float(b)
    except Exception:
        return None


def vue_initiale(points):
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    etendue = max(max(lons) - min(lons), (max(lats) - min(lats)) * 1.6, 0.01)
    return pdk.ViewState(
        latitude=(min(lats) + max(lats)) / 2,
        longitude=(min(lons) + max(lons)) / 2,
        zoom=max(3.0, min(12.0, 8.0 - math.log2(etendue))),
    )


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def calcul_cache(origin, dest, lo, ld, peage, super_pref):
    """Même logique que run_km : géocodage + routes apprises + jalons (mode SUPER)."""
    co = lire_coords(lo)
    cd = lire_coords(ld)
    if not co or not cd:
        from modules.ptv_router_km import geocode_address
        co = co or geocode_address(origin)
        cd = cd or geocode_address(dest)
    if not co or not cd:
        raise ValueError("Impossible de localiser le départ ou l'arrivée.")

    waypoints, prohibited = [], []
    try:
        from modules.routes_preferentielles import get_waypoints
        wp = get_waypoints(origin, dest, auto_jalons=super_pref)
        waypoints = wp.get("waypoints", [])
        prohibited = wp.get("prohibited_countries", [])
    except Exception:
        pass

    res = calculer_route_pays(co[0], co[1], cd[0], cd[1], waypoints, prohibited, peage)
    res["depart"] = {"lat": co[0], "lon": co[1]}
    res["arrivee"] = {"lat": cd[0], "lon": cd[1]}
    return res


# ============================================================
# Paramètres URL
# ============================================================
qp = st.query_params
origin = qp.get("o", "")
dest = qp.get("d", "")
lo = qp.get("lo", "")
ld = qp.get("ld", "")
peage = qp.get("p", "1") == "1"
super_pref = qp.get("sp", "0") == "1"

st.title("🗺️ Trajet détaillé par pays")

if not (origin or lo) or not (dest or ld):
    st.info("Ouvre cette page via le lien « Voir carte » du fichier KM.")
    st.stop()

st.markdown(f"🚛 **{origin or lo}** → **{dest or ld}**")

with st.spinner("Calcul du trajet par pays..."):
    try:
        route = calcul_cache(origin, dest, lo, ld, peage, super_pref)
    except Exception as e:
        st.error(f"❌ Calcul impossible : {e}")
        st.stop()

segments = route["segments"]
frontieres = route["frontieres"]
km_pays = route["km_pays"]
peage_pays = route["peage_pays"]

# ============================================================
# Indicateurs
# ============================================================
c1, c2, c3, c4 = st.columns(4)
c1.metric("📏 KM total", f"{route['km_total']:,.1f} km")
c2.metric("⏱️ Durée", f"{route['duree_h']:.2f} h")
c3.metric("💶 Péage total", f"{route['peage_total']:,.2f} €" if peage else "—")
c4.metric("🌍 Pays traversés", len(km_pays))

st.markdown("🛣️ " + " → ".join(f"**{s['pays']}** ({s['km']:,.1f} km)" for s in segments))

# ============================================================
# Carte
# ============================================================
trace, tous_points = [], []
for s in segments:
    if len(s["coords"]) < 2:
        continue
    p = peage_pays.get(s["pays"], 0.0)
    trace.append({
        "path": s["coords"],
        "color": couleur(s["pays"]),
        "titre": nom_pays(s["pays"]),
        "detail": (f"{s['km']:,.1f} km sur ce tronçon<br/>"
                   f"{km_pays.get(s['pays'], 0):,.1f} km au total dans ce pays<br/>"
                   + (f"Péage pays : {p:,.2f} €" if peage else "Péage non calculé")),
    })
    tous_points.extend(s["coords"])

extremites = [
    {"position": [route["depart"]["lon"], route["depart"]["lat"]], "color": [34, 160, 80],
     "titre": "Départ", "detail": origin},
    {"position": [route["arrivee"]["lon"], route["arrivee"]["lat"]], "color": [200, 30, 40],
     "titre": "Arrivée", "detail": dest},
]
points_frontieres = [
    {"position": [f["lon"], f["lat"]], "color": [255, 255, 255],
     "titre": f"Frontière {f['de']} → {f['vers']}", "detail": f"à {f['km_depuis_depart']:,.1f} km du départ"}
    for f in frontieres if f.get("lat") is not None and f.get("lon") is not None
]
if not tous_points:
    tous_points = [e["position"] for e in extremites]

st.pydeck_chart(
    pdk.Deck(
        layers=[
            pdk.Layer("PathLayer", data=trace, get_path="path", get_color="color",
                      width_min_pixels=5, rounded=True, pickable=True),
            pdk.Layer("ScatterplotLayer", data=points_frontieres, get_position="position",
                      get_fill_color="color", get_line_color=[30, 30, 30], stroked=True,
                      line_width_min_pixels=2, radius_min_pixels=6, pickable=True),
            pdk.Layer("ScatterplotLayer", data=extremites, get_position="position",
                      get_fill_color="color", get_line_color=[255, 255, 255], stroked=True,
                      line_width_min_pixels=2, radius_min_pixels=9, pickable=True),
        ],
        initial_view_state=vue_initiale(tous_points),
        map_style="light",
        tooltip={"html": "<b>{titre}</b><br/>{detail}",
                 "style": {"backgroundColor": "#1f2937", "color": "white", "fontSize": "13px"}},
    ),
    use_container_width=True,
    height=560,
)

legende = " ".join(
    f"<span style='margin-right:14px;'><span style='display:inline-block;width:14px;height:14px;"
    f"border-radius:3px;vertical-align:middle;margin-right:6px;"
    f"background:rgb({couleur(cc)[0]},{couleur(cc)[1]},{couleur(cc)[2]});'></span>{nom_pays(cc)}</span>"
    for cc in km_pays
)
st.markdown(legende + " &nbsp; ⚪ frontière &nbsp; 🟢 départ &nbsp; 🔴 arrivée", unsafe_allow_html=True)

# ============================================================
# Tableau par pays
# ============================================================
st.markdown("### 🌍 KM et péages par pays")

lignes = []
for cc, km in km_pays.items():
    p = peage_pays.get(cc, 0.0)
    lignes.append({
        "Pays": nom_pays(cc),
        "KM": km,
        "% KM": round(km / route["km_total"] * 100, 1) if route["km_total"] else 0.0,
        "Péage €": p,
        "€/km péage": round(p / km, 3) if km else None,
    })
for cc, p in peage_pays.items():
    if cc not in km_pays:
        lignes.append({"Pays": nom_pays(cc), "KM": 0.0, "% KM": 0.0, "Péage €": p, "€/km péage": None})

df = pd.DataFrame(lignes)
if not peage:
    df = df.drop(columns=["Péage €", "€/km péage"])

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "KM": st.column_config.NumberColumn("KM", format="%.1f"),
        "% KM": st.column_config.ProgressColumn("% KM", format="%.1f %%", min_value=0, max_value=100),
        "Péage €": st.column_config.NumberColumn("Péage €", format="%.2f €"),
        "€/km péage": st.column_config.NumberColumn("€/km péage", format="%.3f €"),
    },
)

ecart = round(route["km_total"] - sum(km_pays.values()), 1)
if abs(ecart) > 1:
    st.warning(f"⚠️ Écart de {ecart} km entre le total et la somme par pays.")

if frontieres:
    with st.expander(f"🚧 Passages de frontière ({len(frontieres)})"):
        st.dataframe(
            pd.DataFrame([{"De": nom_pays(f["de"]), "Vers": nom_pays(f["vers"]),
                           "KM depuis départ": f["km_depuis_depart"]} for f in frontieres]),
            use_container_width=True, hide_index=True,
        )
