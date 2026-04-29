"""
4____Cartes_Itineraires.py
──────────────────────────
Page autonome : calcul PTV + carte Leaflet fixe.
Aucun lien avec run_km.py ou excel_handler_km.py.
"""

import streamlit as st
import sys
import os
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

KM_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "tools", "km_calcul"))
sys.path.insert(0, KM_DIR)

st.set_page_config(page_title="Cartes Itinéraires", page_icon="🗺️", layout="wide")

# ─── DEBUG ───────────────────────────────────────────────────────────────────
with st.expander("🔧 Debug info", expanded=False):
    st.write("**__file__**:", __file__)
    st.write("**KM_DIR**:", KM_DIR)
    st.write("**KM_DIR existe**:", os.path.exists(KM_DIR))
    if os.path.exists(KM_DIR):
        st.write("**Contenu KM_DIR**:", os.listdir(KM_DIR))
        modules_dir = os.path.join(KM_DIR, "modules")
        st.write("**modules/ existe**:", os.path.exists(modules_dir))
        if os.path.exists(modules_dir):
            st.write("**Contenu modules/**:", os.listdir(modules_dir))
    st.write("**sys.path**:", sys.path[:5])

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #f0f4fb; }
div[data-testid="stVerticalBlock"] > div { gap: 0.3rem; }
</style>
""", unsafe_allow_html=True)

st.markdown("### 🗺️ Cartes Itinéraires PTV")
st.markdown("*Calcule et visualise tous les itinéraires — carte fixe, tracé instantané*")
st.markdown("---")

# ─── Upload + options ────────────────────────────────────────────────────────
uploaded = st.file_uploader("📂 Fichier Excel source (même format que Calcul KM)", type=["xlsx"])
if uploaded:
    st.session_state["cartes_xlsx_bytes"] = uploaded.read()
    # Reset résultats si nouveau fichier
    for k in ["cartes_routes", "cartes_sel_idx"]:
        st.session_state.pop(k, None)

col_opt1, col_opt2 = st.columns(2)
with col_opt1:
    calculer_peage = st.checkbox("💶 Calculer les frais de péage", value=False)
with col_opt2:
    max_workers = st.slider("⚡ Calculs en parallèle", 1, 4, 2)

# ─── Bouton calcul ───────────────────────────────────────────────────────────
if st.session_state.get("cartes_xlsx_bytes") and st.button("🚀 Calculer et afficher les cartes", type="primary"):
    import tempfile

    try:
        from modules.excel_handler_km import read_all_sheets
        from modules.ptv_router_km import calculate_km_route, geocode_address
        from modules.routes_preferentielles import get_waypoints
    except ImportError as e:
        st.error(f"❌ Import impossible : {e}")
        st.stop()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(st.session_state["cartes_xlsx_bytes"])
        tmp_path = tmp.name

    wb, sheets_data = read_all_sheets(tmp_path)
    os.unlink(tmp_path)

    # Compter le total
    total = sum(len(routes) for _, (_, routes) in sheets_data.items())
    if total == 0:
        st.warning("⚠️ Aucun trajet détecté dans le fichier.")
        st.stop()

    routes_calculees = []
    lock = threading.Lock()

    with st.status(f"⚙️ Calcul de {total} itinéraires...", expanded=True) as status:
        progress = st.progress(0)
        status_txt = st.empty()
        done = [0]

        def calculer_trajet(route, sheet_name):
            origin = route["origin"]
            dest   = route["dest"]

            coords_o = geocode_address(origin)
            coords_d = geocode_address(dest)
            if not coords_o or not coords_d:
                return None

            try:
                waypoints = get_waypoints(origin, dest)
            except Exception:
                waypoints = []

            data = calculate_km_route(
                coords_o[0], coords_o[1],
                coords_d[0], coords_d[1],
                waypoints=waypoints,
                calculer_peage=calculer_peage,
            )
            if not data or not data.get("polyline_coords"):
                return None

            return {
                "label":  f"{origin} → {dest}",
                "origin": origin,
                "dest":   dest,
                "km":     data.get("km", 0),
                "peage":  data.get("prix_peage", 0.0),
                "coords": data["polyline_coords"],
                "sheet":  sheet_name,
            }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for sheet_name, (_, routes) in sheets_data.items():
                for route in routes:
                    f = executor.submit(calculer_trajet, route, sheet_name)
                    futures[f] = route

            for f in as_completed(futures):
                route = futures[f]
                done[0] += 1
                pct = done[0] / total
                progress.progress(min(pct, 1.0))
                status_txt.markdown(
                    f"**{done[0]}/{total}** — {route['origin']} → {route['dest']}"
                )
                try:
                    result = f.result()
                    if result:
                        with lock:
                            routes_calculees.append(result)
                except Exception:
                    pass

        if routes_calculees:
            status.update(label=f"✅ {len(routes_calculees)}/{total} itinéraires calculés", state="complete")
        else:
            status.update(label="❌ Aucun itinéraire calculé", state="error")

    if routes_calculees:
        # Trier par sheet puis par ordre d'apparition
        routes_calculees.sort(key=lambda r: (r["sheet"], r["label"]))
        st.session_state["cartes_routes"] = routes_calculees
        st.session_state["cartes_sel_idx"] = 0
        st.rerun()

# ─── Affichage carte + liste ─────────────────────────────────────────────────
if "cartes_routes" not in st.session_state:
    if not st.session_state.get("cartes_xlsx_bytes"):
        st.info("👆 Charge un fichier Excel pour commencer.")
    st.stop()

routes = st.session_state["cartes_routes"]

if "cartes_sel_idx" not in st.session_state:
    st.session_state["cartes_sel_idx"] = 0

col_liste, col_carte = st.columns([1, 3], gap="small")

# ─── Liste gauche ─────────────────────────────────────────────────────────────
with col_liste:
    st.markdown(f"**{len(routes)} itinéraire{'s' if len(routes)>1 else ''}**")
    filtre = st.text_input("🔍", placeholder="Filtrer...", label_visibility="collapsed")

    routes_vis = [
        (i, r) for i, r in enumerate(routes)
        if not filtre or filtre.lower() in r["label"].lower()
    ]

    if not routes_vis:
        st.warning("Aucun résultat.")
    else:
        for real_idx, r in routes_vis:
            is_sel  = real_idx == st.session_state["cartes_sel_idx"]
            km_s    = f"{r['km']:.0f} km" if r["km"] else "—"
            peage_s = f" · {r['peage']:.2f}€" if r["peage"] else ""
            label   = f"{'▶ ' if is_sel else ''}{r['origin']} → {r['dest']}\n{km_s}{peage_s}"
            if st.button(label, key=f"cr_{real_idx}", use_container_width=True,
                         type="primary" if is_sel else "secondary"):
                st.session_state["cartes_sel_idx"] = real_idx
                st.rerun()

# ─── Carte droite — Leaflet fixe ──────────────────────────────────────────────
with col_carte:
    sel = min(st.session_state["cartes_sel_idx"], len(routes) - 1)
    r_sel = routes[sel]

    all_coords = [c for r in routes for c in r["coords"]]
    center_lat = sum(c[0] for c in all_coords) / len(all_coords)
    center_lon = sum(c[1] for c in all_coords) / len(all_coords)

    routes_js = json.dumps([
        {"origin": r["origin"], "dest": r["dest"],
         "km": r["km"], "peage": r["peage"], "coords": r["coords"]}
        for r in routes
    ])

    carte_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family:'Segoe UI',sans-serif; }}
    #map {{ height:580px; width:100%; border-radius:14px;
            box-shadow:0 4px 24px rgba(26,67,160,0.15); }}
    .info-panel {{
      background:white; padding:10px 14px; border-radius:10px;
      font-size:13px; line-height:1.6;
      box-shadow:0 2px 10px rgba(0,0,0,0.15);
      min-width:180px; max-width:280px;
    }}
    .info-panel strong {{ color:#1a3360; }}
    .info-panel .km   {{ color:#2F5496; font-weight:700; }}
    .info-panel .peage {{ color:#c0392b; font-size:12px; }}
    .mk {{ width:28px; height:28px; border-radius:50% 50% 50% 0;
           transform:rotate(-45deg); display:flex; align-items:center;
           justify-content:center; font-weight:800; font-size:12px;
           color:white; border:2px solid white;
           box-shadow:0 2px 6px rgba(0,0,0,0.3); }}
    .mk span {{ transform:rotate(45deg); }}
    .mk-A {{ background:#27ae60; }} .mk-B {{ background:#e74c3c; }}
  </style>
</head>
<body>
<div id="map"></div>
<script>
  var ROUTES = {routes_js};
  var currentLine=null, markerA=null, markerB=null, infoCtrl=null;

  var map = L.map('map').setView([{center_lat},{center_lon}], 6);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution:'© OpenStreetMap', maxZoom:18
  }}).addTo(map);

  var iconA = L.divIcon({{className:'',
    html:'<div class="mk mk-A"><span>A</span></div>',
    iconSize:[28,28],iconAnchor:[14,28],popupAnchor:[0,-30]}});
  var iconB = L.divIcon({{className:'',
    html:'<div class="mk mk-B"><span>B</span></div>',
    iconSize:[28,28],iconAnchor:[14,28],popupAnchor:[0,-30]}});

  function showRoute(idx) {{
    var r = ROUTES[idx];
    if (!r || !r.coords || !r.coords.length) return;

    if (currentLine) {{ map.removeLayer(currentLine); currentLine=null; }}
    if (markerA)     {{ map.removeLayer(markerA);     markerA=null; }}
    if (markerB)     {{ map.removeLayer(markerB);     markerB=null; }}
    if (infoCtrl)    {{ map.removeControl(infoCtrl);  infoCtrl=null; }}

    currentLine = L.polyline(r.coords, {{
      color:'#1a4fa0', weight:5, opacity:0.9, smoothFactor:1.2
    }}).addTo(map);
    map.fitBounds(currentLine.getBounds().pad(0.1));

    markerA = L.marker(r.coords[0], {{icon:iconA}}).addTo(map)
      .bindPopup('<b>🟢 Départ</b><br>' + r.origin);
    markerB = L.marker(r.coords[r.coords.length-1], {{icon:iconB}}).addTo(map)
      .bindPopup('<b>🔴 Arrivée</b><br>' + r.dest);

    infoCtrl = L.control({{position:'bottomright'}});
    infoCtrl.onAdd = function() {{
      var d = L.DomUtil.create('div','info-panel');
      var km_s  = r.km    ? '<span class="km">📏 '+r.km.toFixed(1)+' km</span>' : '';
      var pe_s  = r.peage ? '<br><span class="peage">🛣️ '+r.peage.toFixed(2)+' €</span>' : '';
      d.innerHTML = '<strong>'+r.origin+'</strong><br>→ <strong>'+r.dest+'</strong><br>'+km_s+pe_s;
      return d;
    }};
    infoCtrl.addTo(map);
  }}

  showRoute({sel});

  window.addEventListener('message', function(e) {{
    if (e.data && typeof e.data.route_idx === 'number') {{
      showRoute(e.data.route_idx);
    }}
  }});
</script>
</body>
</html>"""

    st.components.v1.html(carte_html, height=600, scrolling=False)
    st.caption(
        f"**{r_sel['origin']}** → **{r_sel['dest']}**  ·  📏 {r_sel['km']:.1f} km"
        + (f"  ·  🛣️ {r_sel['peage']:.2f} €" if r_sel['peage'] else "")
    )
