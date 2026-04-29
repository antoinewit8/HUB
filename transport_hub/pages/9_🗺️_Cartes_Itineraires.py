import streamlit as st
import sys
import os
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="Cartes Itinéraires", page_icon="🗺️", layout="wide")

KM_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools", "km_calcul"))
if KM_DIR not in sys.path:
    sys.path.insert(0, KM_DIR)

st.title("🗺️ Cartes Itinéraires PTV")
st.divider()

# ─── État global ─────────────────────────────────────────────────────────────
if "ci_routes" not in st.session_state:
    st.session_state["ci_routes"] = []
if "ci_sel" not in st.session_state:
    st.session_state["ci_sel"] = 0

# ─── Phase 1 : Upload + calcul ───────────────────────────────────────────────
if not st.session_state["ci_routes"]:

    uploaded = st.file_uploader("📂 Fichier Excel source", type=["xlsx"])
    c1, c2 = st.columns(2)
    calculer_peage = c1.checkbox("💶 Calculer les péages", value=False)
    max_workers    = c2.slider("⚡ Calculs en parallèle", 1, 4, 2)

    if uploaded and st.button("🚀 Calculer les itinéraires", type="primary"):
        import tempfile

        try:
            from modules.excel_handler_km import read_all_sheets
            from modules.ptv_router_km import calculate_km_route, geocode_address
            from modules.routes_preferentielles import get_waypoints
        except ImportError as e:
            st.error(f"❌ Import impossible : {e}")
            st.stop()

        raw = uploaded.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        wb, sheets_data = read_all_sheets(tmp_path)
        os.unlink(tmp_path)

        total = sum(len(r) for _, (_, r) in sheets_data.items())
        if total == 0:
            st.warning("⚠️ Aucun trajet détecté.")
            st.stop()

        routes_ok = []
        lock = threading.Lock()
        prog = st.progress(0, text="Calcul en cours...")
        done = [0]

        def calc(route, sheet):
            o = geocode_address(route["origin"])
            d = geocode_address(route["dest"])
            if not o or not d:
                return None
            try:
                wp = get_waypoints(route["origin"], route["dest"])
            except Exception:
                wp = []
            data = calculate_km_route(o[0], o[1], d[0], d[1],
                                      waypoints=wp, calculer_peage=calculer_peage)
            if not data or not data.get("polyline_coords"):
                return None
            return {
                "label":  f"{route['origin']} → {route['dest']}",
                "origin": route["origin"],
                "dest":   route["dest"],
                "km":     data.get("km", 0),
                "peage":  data.get("prix_peage", 0.0),
                "coords": data["polyline_coords"],
            }

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(calc, r, s): r
                       for s, (_, rs) in sheets_data.items() for r in rs}
            for f in as_completed(futures):
                done[0] += 1
                ro = futures[f]
                prog.progress(done[0] / total,
                              text=f"{done[0]}/{total} — {ro['origin']} → {ro['dest']}")
                try:
                    res = f.result()
                    if res:
                        with lock:
                            routes_ok.append(res)
                except Exception:
                    pass

        prog.empty()

        if not routes_ok:
            st.error("❌ Aucun itinéraire calculé.")
        else:
            routes_ok.sort(key=lambda r: r["label"])
            st.session_state["ci_routes"] = routes_ok
            st.session_state["ci_sel"] = 0
            st.rerun()

# ─── Phase 2 : Affichage carte ───────────────────────────────────────────────
else:
    routes = st.session_state["ci_routes"]

    # Bouton reset
    if st.button("🔄 Nouveau calcul"):
        st.session_state["ci_routes"] = []
        st.session_state["ci_sel"] = 0
        st.rerun()

    # Sélecteur
    labels = [
        f"{r['origin']} → {r['dest']}  |  {r['km']:.0f} km"
        + (f"  ·  {r['peage']:.2f} €" if r['peage'] else "")
        for r in routes
    ]
    sel = st.selectbox(
        f"📋 {len(routes)} itinéraire{'s' if len(routes) > 1 else ''}",
        range(len(routes)),
        format_func=lambda i: labels[i],
        index=st.session_state["ci_sel"],
    )
    # Mettre à jour l'index sans rerun — la carte se met à jour via JS
    st.session_state["ci_sel"] = sel

    r = routes[sel]
    st.caption(
        f"**{r['origin']}** → **{r['dest']}**  ·  📏 {r['km']:.1f} km"
        + (f"  ·  🛣️ {r['peage']:.2f} €" if r['peage'] else "")
    )

    # Carte
    all_coords = [c for ro in routes for c in ro["coords"]]
    center_lat = sum(c[0] for c in all_coords) / len(all_coords)
    center_lon = sum(c[1] for c in all_coords) / len(all_coords)
    routes_js  = json.dumps([
        {"origin": ro["origin"], "dest": ro["dest"],
         "km": ro["km"], "peage": ro["peage"], "coords": ro["coords"]}
        for ro in routes
    ])

    carte_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    #map {{ height:700px; width:100%; border-radius:12px;
            box-shadow:0 4px 20px rgba(0,0,0,0.15); }}
    .panel {{ background:white; padding:10px 14px; border-radius:10px;
              font-size:13px; line-height:1.7;
              box-shadow:0 2px 10px rgba(0,0,0,0.15); max-width:280px; }}
    .panel b {{ color:#1a3360; }}
    .km {{ color:#2F5496; font-weight:700; }}
    .mk {{ width:26px; height:26px; border-radius:50% 50% 50% 0;
           transform:rotate(-45deg); display:flex; align-items:center;
           justify-content:center; font-weight:800; font-size:12px;
           color:white; border:2px solid white;
           box-shadow:0 2px 5px rgba(0,0,0,0.3); }}
    .mk span {{ transform:rotate(45deg); }}
    .A {{ background:#27ae60; }} .B {{ background:#e74c3c; }}
  </style>
</head>
<body>
<div id="map"></div>
<script>
  var ROUTES = {routes_js};
  var line=null, mA=null, mB=null, info=null;

  var map = L.map('map').setView([{center_lat},{center_lon}], 6);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
    {{attribution:'© OpenStreetMap',maxZoom:18}}).addTo(map);

  var iA = L.divIcon({{className:'',html:'<div class="mk A"><span>A</span></div>',iconSize:[26,26],iconAnchor:[13,26]}});
  var iB = L.divIcon({{className:'',html:'<div class="mk B"><span>B</span></div>',iconSize:[26,26],iconAnchor:[13,26]}});

  function show(idx) {{
    var r = ROUTES[idx];
    if (!r || !r.coords.length) return;
    if (line) map.removeLayer(line);
    if (mA)   map.removeLayer(mA);
    if (mB)   map.removeLayer(mB);
    if (info) map.removeControl(info);
    line = L.polyline(r.coords,{{color:'#1a4fa0',weight:5,opacity:0.9}}).addTo(map);
    map.fitBounds(line.getBounds().pad(0.08));
    mA = L.marker(r.coords[0],{{icon:iA}}).addTo(map).bindPopup('<b>🟢 '+r.origin+'</b>');
    mB = L.marker(r.coords[r.coords.length-1],{{icon:iB}}).addTo(map).bindPopup('<b>🔴 '+r.dest+'</b>');
    info = L.control({{position:'bottomright'}});
    info.onAdd = function() {{
      var d = L.DomUtil.create('div','panel');
      d.innerHTML = '<b>'+r.origin+'</b><br>→ <b>'+r.dest+'</b><br>'
        +(r.km?'<span class="km">📏 '+r.km.toFixed(1)+' km</span>':'')
        +(r.peage?'<br>🛣️ '+r.peage.toFixed(2)+' €':'');
      return d;
    }};
    info.addTo(map);
  }}

  show({sel});

  window.addEventListener('message', function(e) {{
    if (e.data && typeof e.data.idx === 'number') show(e.data.idx);
  }});
</script>
</body>
</html>"""

    st.components.v1.html(carte_html, height=720, scrolling=False)

    # ─── Tableau récapitulatif sous la carte ─────────────────────────────────
    st.divider()
    st.markdown("#### 📋 Récapitulatif des trajets")

    import pandas as pd

    total_km    = sum(r["km"]    for r in routes if r["km"])
    total_peage = sum(r["peage"] for r in routes if r["peage"])

    col_t1, col_t2, col_t3 = st.columns(3)
    col_t1.metric("📦 Trajets", len(routes))
    col_t2.metric("📏 Total KM", f"{total_km:,.0f} km")
    if total_peage:
        col_t3.metric("🛣️ Total Péage", f"{total_peage:,.2f} €")

    df = pd.DataFrame([
        {
            "N°":          i + 1,
            "Chargement":  r["origin"],
            "Déchargement": r["dest"],
            "KM":          f"{r['km']:.1f}" if r["km"] else "—",
            "Péage (€)":   f"{r['peage']:.2f}" if r["peage"] else "—",
        }
        for i, r in enumerate(routes)
    ])

    # Surligner la ligne sélectionnée
    def highlight_sel(row):
        return ["background-color: #dce6f9; font-weight: bold"
                if row["N°"] == sel + 1
                else "" for _ in row]

    st.dataframe(
        df.style.apply(highlight_sel, axis=1),
        use_container_width=True,
        hide_index=True,
        height=min(400, 38 * len(routes) + 40),
    )
